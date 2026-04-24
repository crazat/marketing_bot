"""
Lead Manager API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

YouTube, TikTok, Naver 리드 관리
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from enum import Enum
import sys
import os
from pathlib import Path
import sqlite3
import re

# [Phase 8] 경로 설정 중앙화
import setup_paths
from setup_paths import PROJECT_ROOT, get_api_key, get_config_path

from db.database import DatabaseManager
from services.lead_scorer import get_lead_scorer, get_trust_scorer
from services.contact_extractor import get_contact_extractor
from core_services.sql_builder import (
    get_table_columns, validate_table_name, SQLInjectionError,
    select_column_safely, validate_column_name
)
from backend_utils.error_handlers import handle_exceptions, safe_db_operation
from backend_utils.logger import get_router_logger
from backend_utils.database import db_conn  # [U5] 공용 DB 컨텍스트 매니저
from schemas.response import success_response, error_response, paginated_response

router = APIRouter()
logger = get_router_logger('leads')

# [UX 개선] 리드 정렬에 허용된 컬럼 정의
ALLOWED_LEAD_SORT_COLUMNS = {
    'created_at',
    'updated_at',
    'status',
    'score',
    'title',
    'platform',
    'author',
    'scraped_at',
}

# [UX 개선] 인플루언서 테이블용 정렬 컬럼
ALLOWED_INFLUENCER_SORT_COLUMNS = {
    'created_at',
    'updated_at',
    'status',
    'followers',
    'relevance_score',
    'avg_engagement',
    'name',
}


def _validate_sort_params(sort_by: str, order: str) -> tuple:
    """
    [UX 개선] 정렬 파라미터 검증
    허용되지 않은 컬럼이나 잘못된 방향은 기본값으로 대체
    """
    if sort_by not in ALLOWED_LEAD_SORT_COLUMNS:
        sort_by = 'created_at'
    if order.lower() not in ('asc', 'desc'):
        order = 'desc'
    return sort_by, order.upper()


def _get_sort_column(sort_by: str, columns: List[str], column_mapping: Dict[str, str]) -> str:
    """
    [UX 개선] 정렬 컬럼 결정 - 실제 테이블 컬럼으로 매핑

    Args:
        sort_by: 사용자가 요청한 정렬 컬럼
        columns: 테이블에 존재하는 컬럼 목록
        column_mapping: 추상 컬럼명 -> 실제 컬럼명 매핑

    Returns:
        실제 사용할 컬럼명
    """
    # 매핑된 컬럼명 확인
    actual_column = column_mapping.get(sort_by, sort_by)

    # 컬럼이 테이블에 존재하는지 확인
    if actual_column in columns:
        return actual_column

    # fallback: created_at 또는 scraped_at
    if 'created_at' in columns:
        return 'created_at'
    if 'scraped_at' in columns:
        return 'scraped_at'

    return 'id'  # 최종 fallback


class Platform(str, Enum):
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    NAVER = "naver"
    INSTAGRAM = "instagram"

class LeadStatus(str, Enum):
    PENDING = "pending"
    CONTACTED = "contacted"
    REPLIED = "replied"
    CONVERTED = "converted"
    REJECTED = "rejected"

class LeadUpdate(BaseModel):
    status: LeadStatus
    notes: Optional[str] = None
    follow_up_date: Optional[str] = None  # YYYY-MM-DD 형식
    contact_info: Optional[str] = None
    expected_revenue: Optional[int] = None  # 예상 매출 (원)
    actual_revenue: Optional[int] = None  # 실제 매출 (원)
    source_keyword: Optional[str] = None  # 출처 키워드
    source_content: Optional[str] = None  # 출처 콘텐츠 URL

class BatchLeadUpdate(BaseModel):
    """배치 리드 업데이트 요청"""
    lead_ids: List[int]
    status: LeadStatus
    notes: Optional[str] = None


def _get_table_columns(cursor, table_name: str) -> List[str]:
    """
    테이블의 컬럼 목록 조회 (SQL 인젝션 방지)

    Args:
        cursor: DB 커서
        table_name: 테이블명 (화이트리스트 검증됨)

    Returns:
        컬럼명 리스트
    """
    return get_table_columns(cursor, table_name)


def _ensure_mentions_columns(cursor):
    """
    [Phase 4.0] mentions 테이블에 필요한 컬럼 추가
    - expected_revenue: 예상 매출
    - actual_revenue: 실제 매출
    - source_keyword: 출처 키워드
    - source_content: 출처 콘텐츠 URL
    - stage_timestamps: 단계별 타임스탬프 (JSON)
    """
    columns = _get_table_columns(cursor, 'mentions')

    new_columns = [
        ('expected_revenue', 'INTEGER DEFAULT 0'),
        ('actual_revenue', 'INTEGER DEFAULT 0'),
        ('source_keyword', 'TEXT'),
        ('source_content', 'TEXT'),
        ('stage_timestamps', 'TEXT DEFAULT "{}"'),
    ]

    for col_name, col_def in new_columns:
        if col_name not in columns:
            try:
                cursor.execute(f"ALTER TABLE mentions ADD COLUMN {col_name} {col_def}")
                logger.info(f"마이그레이션: mentions 테이블에 {col_name} 컬럼 추가됨")
            except Exception as e:
                logger.debug(f"마이그레이션: {col_name} 컬럼이 이미 존재할 수 있음: {e}")


def _update_stage_timestamp(cursor, lead_id: int, new_status: str):
    """
    [Phase 4.0] 리드 상태 변경 시 타임스탬프 기록
    병목 분석을 위한 단계별 시간 추적
    """
    import json
    from datetime import datetime

    # 현재 타임스탬프 조회
    cursor.execute("SELECT stage_timestamps FROM mentions WHERE id = ?", (lead_id,))
    row = cursor.fetchone()

    if row and row[0]:
        try:
            timestamps = json.loads(row[0])
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning(f"JSON 파싱 실패: {e}")
            timestamps = {}
    else:
        timestamps = {}

    # 새 상태의 타임스탬프 기록
    timestamps[new_status] = datetime.now().isoformat()

    # 업데이트
    cursor.execute(
        "UPDATE mentions SET stage_timestamps = ? WHERE id = ?",
        (json.dumps(timestamps), lead_id)
    )


def _normalize_platform(source: str) -> str:
    """source 값을 표준화된 플랫폼 키로 변환"""
    source_lower = source.lower() if source else ''
    if 'youtube' in source_lower:
        return 'youtube'
    elif 'tiktok' in source_lower:
        return 'tiktok'
    elif 'instagram' in source_lower:
        return 'instagram'
    elif 'naver' in source_lower or source_lower in ('blog', 'cafe', 'kin'):
        return 'naver'
    elif 'carrot' in source_lower:
        return 'carrot'
    elif 'influencer' in source_lower:
        return 'influencer'
    else:
        return source_lower or 'other'


def _find_qa_matches(cursor, lead_text: str, max_matches: int = 3) -> List[Dict[str, Any]]:
    """[S4] lead_service.find_qa_matches로 위임 — thin wrapper."""
    from services.lead_service import find_qa_matches as _svc
    return _svc(cursor, lead_text, max_matches=max_matches)


def _enrich_leads(leads: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    [Phase 4.0] 리드에 스코어, 신뢰도, 연락처 정보 추가

    Args:
        leads: 리드 딕셔너리 리스트

    Returns:
        enriched 리드 리스트
    """
    # 스코어 계산
    scorer = get_lead_scorer()
    scored_leads = scorer.batch_score(leads)

    # 신뢰도 점수 계산
    trust_scorer = get_trust_scorer()
    scored_leads = trust_scorer.batch_calculate(scored_leads)

    # 연락처 자동 추출
    contact_extractor = get_contact_extractor()
    for lead in scored_leads:
        full_text = f"{lead.get('title', '')} {lead.get('content', '')} {lead.get('summary', '')}"
        contacts = contact_extractor.extract_contacts(full_text)
        lead['extracted_contacts'] = contacts
        # 기존 contact_info가 비어있으면 자동 추출 결과로 채움
        if not lead.get('contact_info') and contacts.get('has_contact'):
            lead['contact_info'] = contact_extractor.format_contact_info(contacts)

    return scored_leads


@router.get("/stats")
@handle_exceptions
async def get_lead_stats() -> Dict[str, Any]:
    """[U5] 리드 통계 — LeadRepository 위임 + 동적 컬럼 활용.

    Returns:
        플랫폼별, 상태별 리드 통계
    """
    default_response = {'total': 0, 'by_platform': {}, 'by_status': {}}

    from repositories import LeadRepository
    db = DatabaseManager()
    repo = LeadRepository(db.db_path)

    # 테이블 존재 여부 (컬럼 집합이 비어 있으면 테이블 없음)
    cols = repo.columns()
    if not cols:
        return success_response(default_response)

    total = repo.count()
    by_status = repo.group_by_status()

    # 플랫폼별: 컬럼명 동적 판정 (platform 또는 source)
    platform_col = 'platform' if 'platform' in cols else 'source'
    by_platform: Dict[str, int] = {}
    with db_conn(db.db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            f"SELECT {platform_col}, COUNT(*) FROM mentions "
            f"WHERE {platform_col} IS NOT NULL GROUP BY {platform_col}"
        )
        for row in cur.fetchall():
            if row[0]:
                key = _normalize_platform(row[0])
                by_platform[key] = by_platform.get(key, 0) + row[1]

    return success_response({
        'total': total if total else 0,
        'by_platform': by_platform,
        'by_status': by_status,
    })


@router.get("/conversion-rates")
async def get_conversion_rates() -> Dict[str, Any]:
    """
    플랫폼별 전환율 조회

    Returns:
        플랫폼별 전환율 (연락→응답, 응답→전환, 전체 전환율)
    """
    default_response = {
        'total': {'contacted': 0, 'replied': 0, 'converted': 0, 'total': 0},
        'by_platform': {}
    }

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return default_response

        # 컬럼 확인
        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # 플랫폼별 상태 집계
        cursor.execute(f"""
            SELECT
                {platform_col},
                status,
                COUNT(*) as count
            FROM mentions
            WHERE status IS NOT NULL
            GROUP BY {platform_col}, status
        """)

        platform_stats: Dict[str, Dict[str, int]] = {}
        for row in cursor.fetchall():
            platform = _normalize_platform(row[0] or 'other')
            status = row[1]
            count = row[2]

            if platform not in platform_stats:
                platform_stats[platform] = {
                    'pending': 0, 'contacted': 0, 'replied': 0,
                    'converted': 0, 'rejected': 0, 'total': 0
                }
            platform_stats[platform][status] = platform_stats[platform].get(status, 0) + count
            platform_stats[platform]['total'] += count

        conn.close()

        # 전환율 계산
        by_platform = {}
        total_stats = {'contacted': 0, 'replied': 0, 'converted': 0, 'total': 0}

        for platform, stats in platform_stats.items():
            total = stats['total']
            contacted = stats.get('contacted', 0) + stats.get('replied', 0) + stats.get('converted', 0)
            replied = stats.get('replied', 0) + stats.get('converted', 0)
            converted = stats.get('converted', 0)

            by_platform[platform] = {
                'total': total,
                'contacted': contacted,
                'replied': replied,
                'converted': converted,
                'contact_rate': round((contacted / total * 100) if total > 0 else 0, 1),
                'reply_rate': round((replied / contacted * 100) if contacted > 0 else 0, 1),
                'conversion_rate': round((converted / total * 100) if total > 0 else 0, 1),
            }

            total_stats['total'] += total
            total_stats['contacted'] += contacted
            total_stats['replied'] += replied
            total_stats['converted'] += converted

        # 전체 전환율
        total = total_stats['total']
        contacted = total_stats['contacted']
        replied = total_stats['replied']
        converted = total_stats['converted']

        return {
            'total': {
                'total': total,
                'contacted': contacted,
                'replied': replied,
                'converted': converted,
                'contact_rate': round((contacted / total * 100) if total > 0 else 0, 1),
                'reply_rate': round((replied / contacted * 100) if contacted > 0 else 0, 1),
                'conversion_rate': round((converted / total * 100) if total > 0 else 0, 1),
            },
            'by_platform': by_platform
        }

    except Exception as e:
        logger.error(f"conversion-rates 오류: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"전환율 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/score-distribution")
async def get_lead_score_distribution() -> Dict[str, Any]:
    """
    [Phase 1.3] 리드 점수 분포 통계

    Returns:
        등급별 리드 수, 평균 점수 등
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {
                'by_grade': {'hot': 0, 'warm': 0, 'cool': 0, 'cold': 0},
                'average_score': 0,
                'total_scored': 0
            }

        # 모든 리드 가져오기 (최근 1000개)
        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'
        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'

        cursor.execute(f"""
            SELECT id, {platform_col}, title, {summary_col}, {date_col}, url
            FROM mentions
            ORDER BY {date_col} DESC
            LIMIT 1000
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                'by_grade': {'hot': 0, 'warm': 0, 'cool': 0, 'cold': 0},
                'average_score': 0,
                'total_scored': 0
            }

        # [Phase 2 최적화] 배치 스코어 계산
        scorer = get_lead_scorer()
        by_grade = {'hot': 0, 'warm': 0, 'cool': 0, 'cold': 0}
        total_score = 0

        # 리드 리스트 생성
        leads = [
            {
                'id': row[0],
                'platform': row[1],
                'title': row[2],
                'content': row[3],
                'created_at': row[4],
                'url': row[5]
            }
            for row in rows
        ]

        # 배치 스코어 계산
        results = scorer.batch_score(leads)
        for result in results:
            grade = result['grade']
            by_grade[grade] = by_grade.get(grade, 0) + 1
            total_score += result['score']

        average_score = round(total_score / len(rows), 1) if rows else 0

        return {
            'by_grade': by_grade,
            'average_score': average_score,
            'total_scored': len(rows),
            'grade_labels': {
                'hot': '🔴 Hot Lead (즉시 연락)',
                'warm': '🟡 Warm Lead (1일 내)',
                'cool': '🟢 Cool Lead (주간)',
                'cold': '⚪ Cold Lead (보관)'
            }
        }

    except Exception as e:
        print(f"[leads/score-distribution Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"점수 분포 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/quality-stats")
async def get_lead_quality_stats() -> Dict[str, Any]:
    """
    [Phase 4.0] 리드 품질 통계

    Returns:
        신뢰도 분포, 연락처 보유율, 품질 요약
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {
                'trust_distribution': {'trusted': 0, 'review': 0, 'suspicious': 0},
                'contact_rate': 0,
                'total_leads': 0,
                'leads_with_contact': 0,
                'quality_score': 0
            }

        # 모든 리드 가져오기 (최근 500개)
        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'
        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        author_col = 'author' if 'author' in columns else 'target_name'

        cursor.execute(f"""
            SELECT id, {platform_col}, title, {summary_col}, {date_col}, url, {author_col}
            FROM mentions
            ORDER BY {date_col} DESC
            LIMIT 500
        """)
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {
                'trust_distribution': {'trusted': 0, 'review': 0, 'suspicious': 0},
                'contact_rate': 0,
                'total_leads': 0,
                'leads_with_contact': 0,
                'quality_score': 0
            }

        # 리드 데이터 구성
        leads = [
            {
                'id': row[0],
                'platform': row[1],
                'title': row[2],
                'content': row[3],
                'created_at': row[4],
                'url': row[5],
                'author': row[6]
            }
            for row in rows
        ]

        # 신뢰도 계산
        trust_scorer = get_trust_scorer()
        trust_distribution = {'trusted': 0, 'review': 0, 'suspicious': 0}
        total_trust_score = 0

        for lead in leads:
            result = trust_scorer.calculate_trust_score(lead)
            trust_distribution[result['trust_level']] += 1
            total_trust_score += result['trust_score']

        # 연락처 보유율 계산
        contact_extractor = get_contact_extractor()
        leads_with_contact = 0

        for lead in leads:
            full_text = f"{lead.get('title', '')} {lead.get('content', '')}"
            contacts = contact_extractor.extract_contacts(full_text)
            if contacts.get('has_contact'):
                leads_with_contact += 1

        total_leads = len(leads)
        contact_rate = round((leads_with_contact / total_leads * 100), 1) if total_leads > 0 else 0
        avg_trust_score = round(total_trust_score / total_leads, 1) if total_leads > 0 else 0

        # 전체 품질 점수 (0-100)
        # 신뢰 리드 비율(40%) + 연락처 보유율(30%) + 평균 신뢰도(30%)
        trusted_ratio = (trust_distribution['trusted'] / total_leads * 100) if total_leads > 0 else 0
        quality_score = round(
            (trusted_ratio * 0.4) +
            (contact_rate * 0.3) +
            (avg_trust_score * 0.3),
            1
        )

        return {
            'trust_distribution': trust_distribution,
            'contact_rate': contact_rate,
            'total_leads': total_leads,
            'leads_with_contact': leads_with_contact,
            'avg_trust_score': avg_trust_score,
            'quality_score': quality_score,
            'trust_labels': {
                'trusted': '🟢 신뢰',
                'review': '🟡 확인 필요',
                'suspicious': '🔴 의심'
            }
        }

    except Exception as e:
        print(f"[leads/quality-stats Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"품질 통계 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/list")
@handle_exceptions
async def get_leads(
    platform: Optional[Platform] = None,
    status: Optional[LeadStatus] = None,
    category: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500, description="최대 조회 수"),
    offset: int = Query(default=0, ge=0, description="건너뛸 항목 수"),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, score, title, author, platform)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> Dict[str, Any]:
    """
    리드 목록 조회 (정렬 지원)
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 테이블 존재 여부 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if not cursor.fetchone():
        conn.close()
        return success_response({
            "leads": [],
            "message": "mentions 테이블이 존재하지 않습니다. 먼저 리드를 수집해주세요."
        })

    # 컬럼 확인
    columns = _get_table_columns(cursor, 'mentions')

    # 필터 조건 구성
    filters = []
    params = []

    platform_col = select_column_safely(columns, 'platform', 'source', 'source')
    if platform:
        filters.append(f"{platform_col} = ?")
        params.append(platform.value)

    if status and 'status' in columns:
        filters.append("status = ?")
        params.append(status.value)

    if category:
        category_col = select_column_safely(columns, 'category', 'keyword', 'keyword')
        filters.append(f"{category_col} = ?")
        params.append(category)

    where_clause = "WHERE " + " AND ".join(filters) if filters else ""

    # 컬럼 매핑 - select_column_safely 사용
    date_col = select_column_safely(columns, 'created_at', 'scraped_at', 'created_at')
    summary_col = select_column_safely(columns, 'summary', 'content', 'content')
    category_col = select_column_safely(columns, 'category', 'keyword', 'keyword')
    author_col = select_column_safely(columns, 'author', 'target_name', 'author')

    # 노트 관련 컬럼
    notes_col = 'notes' if 'notes' in columns else "''"
    follow_up_col = 'follow_up_date' if 'follow_up_date' in columns else "NULL"
    contact_col = 'contact_info' if 'contact_info' in columns else "''"

    # [Phase 4.0] 새 컬럼들
    expected_rev_col = 'expected_revenue' if 'expected_revenue' in columns else '0'
    actual_rev_col = 'actual_revenue' if 'actual_revenue' in columns else '0'
    source_kw_col = 'source_keyword' if 'source_keyword' in columns else "NULL"
    source_ct_col = 'source_content' if 'source_content' in columns else "NULL"
    stage_ts_col = 'stage_timestamps' if 'stage_timestamps' in columns else "'{}'"

    # [UX 개선] 정렬 파라미터 적용
    validated_sort, validated_order = _validate_sort_params(sort_by, order)
    column_mapping = {
        'created_at': date_col,
        'updated_at': date_col,
        'author': author_col,
        'platform': platform_col,
    }
    actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)

    # score 정렬은 Python에서 처리 (DB에서는 기본 정렬 사용)
    if validated_sort == 'score':
        db_order_clause = f"ORDER BY {date_col} DESC"
    else:
        db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

    cursor.execute(f"""
        SELECT
            id,
            {platform_col} as platform,
            COALESCE(status, 'pending') as status,
            title,
            url,
            {summary_col} as summary,
            {category_col} as category,
            {author_col} as author,
            {date_col} as created_at,
            {date_col} as updated_at,
            0 as sentiment_score,
            0 as priority_score,
            {notes_col} as notes,
            {follow_up_col} as follow_up_date,
            {contact_col} as contact_info,
            {expected_rev_col} as expected_revenue,
            {actual_rev_col} as actual_revenue,
            {source_kw_col} as source_keyword,
            {source_ct_col} as source_content,
            {stage_ts_col} as stage_timestamps
        FROM mentions
        {where_clause}
        {db_order_clause}
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    rows = cursor.fetchall()
    conn.close()

    # [Phase 1.3] 리드 스코어링 적용
    leads = [
        {
            "id": row[0],
            "platform": row[1],
            "status": row[2],
            "title": row[3],
            "url": row[4],
            "summary": row[5],
            "category": row[6],
            "author": row[7],
            "created_at": row[8],
            "updated_at": row[9],
            "content": row[5],  # summary를 content로도 사용 (스코어링용)
            "notes": row[12] or '',
            "follow_up_date": row[13],
            "contact_info": row[14] or '',
            "expected_revenue": row[15] or 0,
            "actual_revenue": row[16] or 0,
            "source_keyword": row[17],
            "source_content": row[18],
            "stage_timestamps": row[19] or '{}'
        }
        for row in rows
    ]

    # [Phase 4.0] 리드 enrichment (스코어, 신뢰도, 연락처)
    enriched_leads = _enrich_leads(leads)

    # [UX 개선] score 정렬인 경우에만 점수순 정렬 적용
    if validated_sort == 'score':
        reverse = validated_order == 'DESC'
        enriched_leads.sort(key=lambda x: x.get('score', 0), reverse=reverse)

    return success_response(enriched_leads)


@router.get("/youtube")
async def get_youtube_leads(
    status: Optional[LeadStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, score, title, author)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """YouTube 리드 조회 (정렬 지원)"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # youtube, youtube_comment 등 모두 포함하도록 LIKE 패턴 사용
        filters = [f"{platform_col} LIKE ?"]
        params = ['youtube%']

        if status and 'status' in columns:
            filters.append("status = ?")
            params.append(status.value)

        where_clause = "WHERE " + " AND ".join(filters)

        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        category_col = 'category' if 'category' in columns else 'keyword'
        author_col = 'author' if 'author' in columns else 'target_name'

        # [UX 개선] 정렬 파라미터 적용
        validated_sort, validated_order = _validate_sort_params(sort_by, order)
        column_mapping = {
            'created_at': date_col,
            'updated_at': date_col,
            'author': author_col,
        }
        actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)

        # score 정렬은 Python에서 처리 (DB에서는 기본 정렬 사용)
        if validated_sort == 'score':
            db_order_clause = f"ORDER BY {date_col} DESC"
        else:
            db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                COALESCE(status, 'pending') as status,
                title,
                url,
                {summary_col} as summary,
                {category_col} as category,
                {author_col} as author,
                {date_col} as created_at,
                {date_col} as updated_at,
                0 as sentiment_score,
                0 as priority_score
            FROM mentions
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        # 리드 데이터 구성
        leads = [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "content": row[5]  # summary를 content로도 사용 (스코어링용)
            }
            for row in rows
        ]

        # [Phase 4.0] 리드 enrichment (스코어, 신뢰도, 연락처)
        enriched_leads = _enrich_leads(leads)

        # [UX 개선] score 정렬인 경우에만 점수순 정렬 적용
        if validated_sort == 'score':
            reverse = validated_order == 'DESC'
            enriched_leads.sort(key=lambda x: x.get('score', 0), reverse=reverse)

        return enriched_leads

    except Exception as e:
        print(f"[leads/youtube Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"YouTube 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/tiktok")
async def get_tiktok_leads(
    status: Optional[LeadStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, score, title, author)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """TikTok 리드 조회 (정렬 지원)"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # tiktok, tiktok_comment 등 모두 포함하도록 LIKE 패턴 사용
        filters = [f"{platform_col} LIKE ?"]
        params = ['tiktok%']

        if status and 'status' in columns:
            filters.append("status = ?")
            params.append(status.value)

        where_clause = "WHERE " + " AND ".join(filters)

        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        category_col = 'category' if 'category' in columns else 'keyword'
        author_col = 'author' if 'author' in columns else 'target_name'

        # [UX 개선] 정렬 파라미터 적용
        validated_sort, validated_order = _validate_sort_params(sort_by, order)
        column_mapping = {
            'created_at': date_col,
            'updated_at': date_col,
            'author': author_col,
        }
        actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)

        # score 정렬은 Python에서 처리 (DB에서는 기본 정렬 사용)
        if validated_sort == 'score':
            db_order_clause = f"ORDER BY {date_col} DESC"
        else:
            db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                COALESCE(status, 'pending') as status,
                title,
                url,
                {summary_col} as summary,
                {category_col} as category,
                {author_col} as author,
                {date_col} as created_at,
                {date_col} as updated_at,
                0 as sentiment_score,
                0 as priority_score
            FROM mentions
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        # 리드 데이터 구성
        leads = [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "content": row[5]  # summary를 content로도 사용 (스코어링용)
            }
            for row in rows
        ]

        # [Phase 4.0] 리드 enrichment (스코어, 신뢰도, 연락처)
        enriched_leads = _enrich_leads(leads)

        # [UX 개선] score 정렬인 경우에만 점수순 정렬 적용
        if validated_sort == 'score':
            reverse = validated_order == 'DESC'
            enriched_leads.sort(key=lambda x: x.get('score', 0), reverse=reverse)

        return enriched_leads

    except Exception as e:
        print(f"[leads/tiktok Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"TikTok 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/naver")
async def get_naver_leads(
    status: Optional[LeadStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, score, title, author)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """Naver 리드 조회 (블로그/카페) (정렬 지원)"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # naver_cafe, naver_blog, blog, cafe, kin, naver 등 모두 포함
        filters = [f"({platform_col} LIKE 'naver%' OR {platform_col} IN ('blog', 'cafe', 'kin'))"]
        params = []

        if status and 'status' in columns:
            filters.append("status = ?")
            params.append(status.value)

        where_clause = "WHERE " + " AND ".join(filters)

        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        category_col = 'category' if 'category' in columns else 'keyword'
        author_col = 'author' if 'author' in columns else 'target_name'

        # [UX 개선] 정렬 파라미터 적용
        validated_sort, validated_order = _validate_sort_params(sort_by, order)
        column_mapping = {
            'created_at': date_col,
            'updated_at': date_col,
            'author': author_col,
        }
        actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)

        # score 정렬은 Python에서 처리 (DB에서는 기본 정렬 사용)
        if validated_sort == 'score':
            db_order_clause = f"ORDER BY {date_col} DESC"
        else:
            db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                COALESCE(status, 'pending') as status,
                title,
                url,
                {summary_col} as summary,
                {category_col} as category,
                {author_col} as author,
                {date_col} as created_at,
                {date_col} as updated_at,
                0 as sentiment_score,
                0 as priority_score
            FROM mentions
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        # 리드 데이터 구성
        leads = [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "content": row[5]  # summary를 content로도 사용 (스코어링용)
            }
            for row in rows
        ]

        # [Phase 4.0] 리드 enrichment (스코어, 신뢰도, 연락처)
        enriched_leads = _enrich_leads(leads)

        # [UX 개선] score 정렬인 경우에만 점수순 정렬 적용
        if validated_sort == 'score':
            reverse = validated_order == 'DESC'
            enriched_leads.sort(key=lambda x: x.get('score', 0), reverse=reverse)

        return enriched_leads

    except Exception as e:
        print(f"[leads/naver Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"네이버 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.patch("/{lead_id}")
async def update_lead(lead_id: int, update_data: LeadUpdate) -> Dict[str, str]:
    """
    리드 상태 업데이트

    [Phase 4.0] 추가 필드:
    - expected_revenue: 예상 매출
    - actual_revenue: 실제 매출
    - source_keyword: 출처 키워드
    - source_content: 출처 콘텐츠 URL
    - stage_timestamps: 자동 기록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 새 컬럼 마이그레이션 확인
        _ensure_mentions_columns(cursor)
        columns = _get_table_columns(cursor, 'mentions')

        # 상태 업데이트
        update_fields = ["status = ?"]
        params = [update_data.status.value]

        if 'updated_at' in columns:
            update_fields.append("updated_at = datetime('now')")

        if update_data.notes is not None and 'notes' in columns:
            update_fields.append("notes = ?")
            params.append(update_data.notes)

        if update_data.follow_up_date is not None and 'follow_up_date' in columns:
            update_fields.append("follow_up_date = ?")
            params.append(update_data.follow_up_date)

        if update_data.contact_info is not None and 'contact_info' in columns:
            update_fields.append("contact_info = ?")
            params.append(update_data.contact_info)

        # [Phase 4.0] 새 필드들 처리
        if update_data.expected_revenue is not None and 'expected_revenue' in columns:
            update_fields.append("expected_revenue = ?")
            params.append(update_data.expected_revenue)

        if update_data.actual_revenue is not None and 'actual_revenue' in columns:
            update_fields.append("actual_revenue = ?")
            params.append(update_data.actual_revenue)

        if update_data.source_keyword is not None and 'source_keyword' in columns:
            update_fields.append("source_keyword = ?")
            params.append(update_data.source_keyword)

        if update_data.source_content is not None and 'source_content' in columns:
            update_fields.append("source_content = ?")
            params.append(update_data.source_content)

        params.append(lead_id)

        cursor.execute(f"""
            UPDATE mentions
            SET {', '.join(update_fields)}
            WHERE id = ?
        """, params)

        # [Phase 4.0] 상태 변경 타임스탬프 기록 (병목 분석용)
        if 'stage_timestamps' in columns:
            _update_stage_timestamp(cursor, lead_id, update_data.status.value)

        conn.commit()
        conn.close()

        return {
            'status': 'success',
            'message': f'리드 #{lead_id} 상태 업데이트 완료'
        }

    except Exception as e:
        print(f"[leads/update Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"리드 업데이트 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.patch("/batch")
async def batch_update_leads(update_data: BatchLeadUpdate) -> Dict[str, Any]:
    """[S2] LeadRepository.bulk_update_status로 위임.

    notes 파라미터는 Repository에서 지원하지 않으므로 별도 처리.
    """
    if not update_data.lead_ids:
        raise HTTPException(status_code=400, detail="업데이트할 리드 ID가 없습니다")

    try:
        from repositories import LeadRepository
        db = DatabaseManager()
        repo = LeadRepository(db.db_path)

        # 메인 일괄 상태 업데이트 (Repository 위임)
        updated_count = repo.bulk_update_status(list(update_data.lead_ids), update_data.status.value)

        # notes가 있으면 개별 업데이트 (Repository.update 활용)
        if update_data.notes:
            for lid in update_data.lead_ids:
                repo.update(lid, {"notes": update_data.notes})

        # 실패한 ID 확인
        existing_ids = set()
        for lid in update_data.lead_ids:
            if repo.get(lid) is not None:
                existing_ids.add(lid)
        failed_ids = [lid for lid in update_data.lead_ids if lid not in existing_ids]

        return {
            'status': 'success',
            'message': f'{updated_count}개 리드 상태 업데이트 완료',
            'updated_count': updated_count,
            'failed_ids': failed_ids,
            'new_status': update_data.status.value
        }

    except Exception as e:
        logger.error(f"[leads/batch Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"배치 업데이트 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/categories")
async def get_lead_categories() -> List[Dict[str, Any]]:
    """
    리드 카테고리별 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        category_col = 'category' if 'category' in columns else 'keyword'

        # 카테고리별 통계
        cursor.execute(f"""
            SELECT
                {category_col} as category,
                COUNT(*) as total,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) as contacted,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE {category_col} IS NOT NULL AND {category_col} != ''
            GROUP BY {category_col}
            ORDER BY total DESC
        """)

        categories = []
        for row in cursor.fetchall():
            categories.append({
                'category': row[0],
                'total': row[1],
                'pending': row[2] or 0,
                'contacted': row[3] or 0,
                'converted': row[4] or 0
            })

        conn.close()
        return categories

    except Exception as e:
        print(f"[leads/categories Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"카테고리 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/carrot")
async def get_carrot_leads(
    status: Optional[LeadStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, title, author)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """당근마켓 리드 조회 (정렬 지원)"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # carrot, carrot_daangn 등 모두 포함하도록 LIKE 패턴 사용
        filters = [f"{platform_col} LIKE ?"]
        params = ['carrot%']

        if status and 'status' in columns:
            filters.append("status = ?")
            params.append(status.value)

        where_clause = "WHERE " + " AND ".join(filters)

        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        category_col = 'category' if 'category' in columns else 'keyword'
        author_col = 'author' if 'author' in columns else 'target_name'

        # [UX 개선] 정렬 파라미터 적용
        validated_sort, validated_order = _validate_sort_params(sort_by, order)
        column_mapping = {
            'created_at': date_col,
            'updated_at': date_col,
            'author': author_col,
        }
        actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)
        db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                COALESCE(status, 'pending') as status,
                title,
                url,
                {summary_col} as summary,
                {category_col} as category,
                {author_col} as author,
                {date_col} as created_at,
                {date_col} as updated_at,
                0 as sentiment_score,
                0 as priority_score
            FROM mentions
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "priority_score": row[11]
            }
            for row in rows
        ]

    except Exception as e:
        print(f"[leads/carrot Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"당근마켓 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/influencer")
async def get_influencer_leads(
    status: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="relevance_score", description="정렬 기준 (relevance_score, followers, avg_engagement, created_at, name)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """
    인플루언서 리드 조회 (정렬 지원)

    Note: ambassador_v2.py가 저장하는 influencers 테이블에서 조회
    influencers 테이블 status: discovered, contacted, negotiating, collaborated, declined
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # influencers 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='influencers'")
        if not cursor.fetchone():
            conn.close()
            return []

        # 필터 조건 구성
        filters = []
        params = []

        if status:
            filters.append("status = ?")
            params.append(status)

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""

        # [UX 개선] 정렬 파라미터 검증 (인플루언서 전용)
        validated_sort = sort_by if sort_by in ALLOWED_INFLUENCER_SORT_COLUMNS else 'relevance_score'
        validated_order = order.upper() if order.lower() in ('asc', 'desc') else 'DESC'
        db_order_clause = f"ORDER BY {validated_sort} {validated_order}, created_at DESC"

        cursor.execute(f"""
            SELECT
                id,
                platform,
                COALESCE(status, 'discovered') as status,
                name as title,
                profile_url as url,
                COALESCE(notes, '') as summary,
                COALESCE(content_categories, '[]') as category,
                handle as author,
                created_at,
                updated_at,
                COALESCE(avg_engagement, 0) as sentiment_score,
                COALESCE(relevance_score, 0) as priority_score,
                COALESCE(followers, 0) as followers,
                COALESCE(sponsored_experience, 0) as sponsored_experience
            FROM influencers
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "priority_score": row[11],
                "followers": row[12],
                "sponsored_experience": row[13]
            }
            for row in rows
        ]

    except Exception as e:
        print(f"[leads/influencer Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"인플루언서 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/instagram")
async def get_instagram_leads(
    status: Optional[LeadStatus] = None,
    limit: int = Query(default=100, ge=1, le=500),
    # [UX 개선] 정렬 파라미터 추가
    sort_by: str = Query(default="created_at", description="정렬 기준 (created_at, status, score, title, author)"),
    order: str = Query(default="desc", regex="^(asc|desc)$", description="정렬 방향 (asc, desc)"),
) -> List[Dict[str, Any]]:
    """Instagram 리드 조회 (정렬 지원)"""
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return []

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'

        # instagram, instagram_api, instagram_limited_google 등 모두 포함하도록 LIKE 패턴 사용
        filters = [f"{platform_col} LIKE ?"]
        params = ['instagram%']

        if status and 'status' in columns:
            filters.append("status = ?")
            params.append(status.value)

        where_clause = "WHERE " + " AND ".join(filters)

        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'
        category_col = 'category' if 'category' in columns else 'keyword'
        author_col = 'author' if 'author' in columns else 'target_name'

        # [UX 개선] 정렬 파라미터 적용
        validated_sort, validated_order = _validate_sort_params(sort_by, order)
        column_mapping = {
            'created_at': date_col,
            'updated_at': date_col,
            'author': author_col,
        }
        actual_sort_col = _get_sort_column(validated_sort, columns, column_mapping)

        # score 정렬은 Python에서 처리 (DB에서는 기본 정렬 사용)
        if validated_sort == 'score':
            db_order_clause = f"ORDER BY {date_col} DESC"
        else:
            db_order_clause = f"ORDER BY {actual_sort_col} {validated_order}"

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                COALESCE(status, 'pending') as status,
                title,
                url,
                {summary_col} as summary,
                {category_col} as category,
                {author_col} as author,
                {date_col} as created_at,
                {date_col} as updated_at,
                0 as sentiment_score,
                0 as priority_score
            FROM mentions
            {where_clause}
            {db_order_clause}
            LIMIT ?
        """, params + [limit])

        rows = cursor.fetchall()
        conn.close()

        # 리드 데이터 구성
        leads = [
            {
                "id": row[0],
                "platform": row[1],
                "status": row[2],
                "title": row[3],
                "url": row[4],
                "summary": row[5],
                "category": row[6],
                "author": row[7],
                "created_at": row[8],
                "updated_at": row[9],
                "sentiment_score": row[10],
                "content": row[5]  # summary를 content로도 사용 (스코어링용)
            }
            for row in rows
        ]

        # [Phase 4.0] 리드 enrichment (스코어, 신뢰도, 연락처)
        enriched_leads = _enrich_leads(leads)

        # [UX 개선] score 정렬인 경우에만 점수순 정렬 적용
        if validated_sort == 'score':
            reverse = validated_order == 'DESC'
            enriched_leads.sort(key=lambda x: x.get('score', 0), reverse=reverse)

        return enriched_leads

    except Exception as e:
        print(f"[leads/instagram Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Instagram 리드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 리드 전환 추적 - ROI 측정 기반
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class LeadConversionCreate(BaseModel):
    """리드 전환 데이터 생성"""
    lead_id: int
    keyword: Optional[str] = None
    platform: Optional[str] = None
    revenue: float = 0.0
    notes: Optional[str] = None


class LeadConversionUpdate(BaseModel):
    """리드 전환 데이터 수정"""
    revenue: Optional[float] = None
    notes: Optional[str] = None


def _ensure_lead_conversions_table(cursor):
    """lead_conversions 테이블 생성 (없으면)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_conversions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            keyword TEXT,
            platform TEXT,
            revenue REAL DEFAULT 0,
            notes TEXT,
            conversion_date TEXT DEFAULT (datetime('now', 'localtime')),
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    # 키워드별 집계를 위한 인덱스
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_conversions_keyword
        ON lead_conversions(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_conversions_platform
        ON lead_conversions(platform)
    """)


@router.post("/conversions")
async def add_lead_conversion(data: LeadConversionCreate) -> Dict[str, Any]:
    """
    [Phase 4.0] 리드 전환 기록 추가

    리드가 실제 고객으로 전환되었을 때 매출 정보를 기록합니다.
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_lead_conversions_table(cursor)

        # 리드 존재 확인 및 정보 가져오기
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            columns = _get_table_columns(cursor, 'mentions')
            platform_col = 'platform' if 'platform' in columns else 'source'
            keyword_col = 'keyword' if 'keyword' in columns else 'category'

            cursor.execute(f"""
                SELECT id, {platform_col}, {keyword_col}
                FROM mentions WHERE id = ?
            """, (data.lead_id,))
            lead = cursor.fetchone()

            if not lead:
                conn.close()
                raise HTTPException(status_code=404, detail="리드를 찾을 수 없습니다")

            # 리드 정보로 기본값 설정
            platform = data.platform or _normalize_platform(lead[1] or '')
            keyword = data.keyword or lead[2]
        else:
            platform = data.platform or 'unknown'
            keyword = data.keyword

        # 전환 기록 추가
        cursor.execute("""
            INSERT INTO lead_conversions (lead_id, keyword, platform, revenue, notes)
            VALUES (?, ?, ?, ?, ?)
        """, (data.lead_id, keyword, platform, data.revenue, data.notes))

        conversion_id = cursor.lastrowid

        # 리드 상태를 converted로 업데이트
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            columns = _get_table_columns(cursor, 'mentions')
            if 'status' in columns:
                cursor.execute("""
                    UPDATE mentions SET status = 'converted' WHERE id = ?
                """, (data.lead_id,))

        conn.commit()
        conn.close()

        # [Phase A-3] 리드 전환 이벤트 발행
        try:
            from services.event_bus import event_bus, EventType
            import asyncio
            asyncio.create_task(event_bus.emit_async(
                EventType.LEAD_CONVERTED,
                {
                    "lead_id": data.lead_id,
                    "conversion_id": conversion_id,
                    "keyword": keyword,
                    "platform": platform,
                    "revenue": data.revenue,
                },
                "lead_manager"
            ))
        except Exception as event_error:
            print(f"[leads] 이벤트 발행 실패: {event_error}")

        return {
            "success": True,
            "conversion_id": conversion_id,
            "message": "전환 기록이 추가되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[leads/conversions Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"전환 기록 추가 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/conversion-tracking")
async def get_conversion_tracking() -> Dict[str, Any]:
    """
    [Phase 4.0] 리드 전환 추적 통계

    키워드별, 플랫폼별 ROI 분석 데이터를 제공합니다.

    Returns:
        - 전체 전환 수 및 총 매출
        - 키워드별 전환/매출 (ROI 분석용)
        - 플랫폼별 전환/매출
        - 최근 30일 일별 추이
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_lead_conversions_table(cursor)

        # 전체 통계
        cursor.execute("""
            SELECT
                COUNT(*) as total_conversions,
                COALESCE(SUM(revenue), 0) as total_revenue
            FROM lead_conversions
        """)
        overall = cursor.fetchone()

        # 키워드별 통계 (상위 20개)
        cursor.execute("""
            SELECT
                keyword,
                COUNT(*) as conversions,
                COALESCE(SUM(revenue), 0) as revenue,
                ROUND(AVG(revenue), 0) as avg_revenue
            FROM lead_conversions
            WHERE keyword IS NOT NULL AND keyword != ''
            GROUP BY keyword
            ORDER BY revenue DESC
            LIMIT 20
        """)
        by_keyword = [
            {
                "keyword": row[0],
                "conversions": row[1],
                "revenue": row[2],
                "avg_revenue": row[3]
            }
            for row in cursor.fetchall()
        ]

        # 플랫폼별 통계
        cursor.execute("""
            SELECT
                platform,
                COUNT(*) as conversions,
                COALESCE(SUM(revenue), 0) as revenue,
                ROUND(AVG(revenue), 0) as avg_revenue
            FROM lead_conversions
            WHERE platform IS NOT NULL AND platform != ''
            GROUP BY platform
            ORDER BY revenue DESC
        """)
        by_platform = [
            {
                "platform": row[0],
                "conversions": row[1],
                "revenue": row[2],
                "avg_revenue": row[3]
            }
            for row in cursor.fetchall()
        ]

        # 최근 30일 일별 추이
        cursor.execute("""
            SELECT
                DATE(conversion_date) as date,
                COUNT(*) as conversions,
                COALESCE(SUM(revenue), 0) as revenue
            FROM lead_conversions
            WHERE conversion_date >= date('now', '-30 days')
            GROUP BY DATE(conversion_date)
            ORDER BY date DESC
        """)
        daily_trend = [
            {
                "date": row[0],
                "conversions": row[1],
                "revenue": row[2]
            }
            for row in cursor.fetchall()
        ]

        # 키워드별 리드 수 조회 (ROI 계산용)
        keyword_leads = {}
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if cursor.fetchone():
            columns = _get_table_columns(cursor, 'mentions')
            keyword_col = 'keyword' if 'keyword' in columns else 'category'

            cursor.execute(f"""
                SELECT {keyword_col}, COUNT(*)
                FROM mentions
                WHERE {keyword_col} IS NOT NULL AND {keyword_col} != ''
                GROUP BY {keyword_col}
            """)
            for row in cursor.fetchall():
                keyword_leads[row[0]] = row[1]

        # 키워드별 전환율 계산
        for kw_data in by_keyword:
            keyword = kw_data["keyword"]
            total_leads = keyword_leads.get(keyword, 0)
            kw_data["total_leads"] = total_leads
            kw_data["conversion_rate"] = round(
                (kw_data["conversions"] / total_leads * 100) if total_leads > 0 else 0, 1
            )

        conn.close()

        return {
            "overview": {
                "total_conversions": overall[0] or 0,
                "total_revenue": overall[1] or 0,
                "avg_revenue_per_conversion": round(overall[1] / overall[0], 0) if overall[0] > 0 else 0
            },
            "by_keyword": by_keyword,
            "by_platform": by_platform,
            "daily_trend": daily_trend
        }

    except Exception as e:
        print(f"[leads/conversion-tracking Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"전환 추적 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/{lead_id}/conversions")
async def get_lead_conversions(lead_id: int) -> List[Dict[str, Any]]:
    """
    [Phase 4.0] 특정 리드의 전환 기록 조회
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_lead_conversions_table(cursor)

        cursor.execute("""
            SELECT id, lead_id, keyword, platform, revenue, notes,
                   conversion_date, created_at
            FROM lead_conversions
            WHERE lead_id = ?
            ORDER BY conversion_date DESC
        """, (lead_id,))

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                "id": row[0],
                "lead_id": row[1],
                "keyword": row[2],
                "platform": row[3],
                "revenue": row[4],
                "notes": row[5],
                "conversion_date": row[6],
                "created_at": row[7]
            }
            for row in rows
        ]

    except Exception as e:
        print(f"[leads/{lead_id}/conversions Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"전환 기록 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] Hot Lead 자동 알림 시스템
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_lead_alerts_table(cursor):
    """lead_alerts 테이블 생성 (없으면)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lead_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            alert_type TEXT NOT NULL,
            message TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            read_at TEXT,
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_alerts_lead_id
        ON lead_alerts(lead_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_lead_alerts_is_read
        ON lead_alerts(is_read)
    """)


@router.get("/pending-alerts")
async def get_pending_alerts() -> Dict[str, Any]:
    """
    [Phase 4.0] 긴급 리드 알림 조회

    Hot Lead 발생 및 24시간 미연락 리마인더를 제공합니다.

    Returns:
        - hot_leads: 새로 발견된 Hot Lead (점수 80점 이상, 최근 24시간)
        - overdue_leads: 24시간 이상 pending 상태인 Hot Lead
        - total_alerts: 총 알림 수
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_lead_alerts_table(cursor)

        # mentions 테이블 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {
                "hot_leads": [],
                "overdue_leads": [],
                "total_alerts": 0
            }

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'
        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'
        summary_col = 'summary' if 'summary' in columns else 'content'

        # 최근 24시간 내 pending 상태의 리드 조회
        cursor.execute(f"""
            SELECT id, {platform_col}, title, {summary_col}, url, {date_col}, status
            FROM mentions
            WHERE status = 'pending'
            ORDER BY {date_col} DESC
            LIMIT 100
        """)
        pending_rows = cursor.fetchall()
        conn.close()

        if not pending_rows:
            return {
                "hot_leads": [],
                "overdue_leads": [],
                "total_alerts": 0
            }

        # 리드 데이터 구성 및 점수 계산
        from datetime import datetime, timedelta
        scorer = get_lead_scorer()
        now = datetime.now()

        hot_leads = []
        overdue_leads = []

        for row in pending_rows:
            lead = {
                "id": row[0],
                "platform": row[1],
                "title": row[2],
                "summary": row[3],
                "content": row[3],  # 스코어링용
                "url": row[4],
                "created_at": row[5],
                "status": row[6]
            }

            # 점수 계산
            scored = scorer.score(lead)
            score = scored.get('score', 0)
            grade = scored.get('grade', 'cold')

            if grade == 'hot':  # 80점 이상
                # 생성 시간 파싱
                try:
                    if lead['created_at']:
                        created = datetime.fromisoformat(lead['created_at'].replace('Z', '+00:00').replace(' ', 'T'))
                        hours_ago = (now - created.replace(tzinfo=None)).total_seconds() / 3600
                    else:
                        hours_ago = 0
                except (ValueError, TypeError, AttributeError):
                    hours_ago = 0

                lead_info = {
                    "id": lead["id"],
                    "platform": _normalize_platform(lead["platform"] or ''),
                    "title": lead["title"],
                    "score": score,
                    "hours_pending": round(hours_ago, 1),
                    "url": lead["url"],
                    "created_at": lead["created_at"]
                }

                if hours_ago >= 24:
                    overdue_leads.append(lead_info)
                else:
                    hot_leads.append(lead_info)

        # 긴급도 순 정렬
        hot_leads.sort(key=lambda x: x['score'], reverse=True)
        overdue_leads.sort(key=lambda x: x['hours_pending'], reverse=True)

        return {
            "hot_leads": hot_leads[:10],  # 상위 10개
            "overdue_leads": overdue_leads[:10],
            "total_alerts": len(hot_leads) + len(overdue_leads)
        }

    except Exception as e:
        print(f"[leads/pending-alerts Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"알림 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 플랫폼별 응답 템플릿
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 플랫폼별 기본 응답 템플릿
DEFAULT_TEMPLATES = {
    "cafe": {
        "first_contact": {
            "title": "맘카페 첫 연락",
            "content": """안녕하세요, {author}님! 👋

{title}에 대해 관심을 갖고 계시는군요.

저희 규림한의원에서 관련 상담을 도와드릴 수 있습니다.
편하신 시간에 무료 상담 예약해주세요!

📞 전화: 043-XXX-XXXX
📍 위치: 청주시 OO구 OO동

감사합니다! 🙏"""
        },
        "follow_up": {
            "title": "맘카페 팔로업",
            "content": """안녕하세요, {author}님!

이전에 문의하신 내용 관련해서 연락드립니다.
혹시 추가로 궁금하신 점 있으시면 언제든 말씀해주세요.

이번 달 특별 이벤트도 진행 중이니 참고해주세요! ✨"""
        }
    },
    "youtube": {
        "first_contact": {
            "title": "YouTube 첫 연락",
            "content": """안녕하세요! 영상 잘 봤습니다 👍

{title} 관련해서 궁금하신 점이 있으시면
댓글이나 DM으로 편하게 문의해주세요!

더 자세한 정보는 저희 채널에서 확인하실 수 있습니다.
구독과 좋아요 부탁드려요! 🙏"""
        }
    },
    "tiktok": {
        "first_contact": {
            "title": "TikTok 첫 연락",
            "content": """안녕하세요! 👋✨

영상 관심 가져주셔서 감사해요!
더 많은 정보가 필요하시면 프로필 링크 확인해주세요 🔗

#청주한의원 #규림한의원"""
        }
    },
    "instagram": {
        "first_contact": {
            "title": "Instagram 첫 연락",
            "content": """안녕하세요! 💚

게시물에 관심 가져주셔서 감사합니다!
궁금하신 점은 DM으로 편하게 문의해주세요.

프로필 링크에서 더 많은 정보 확인하실 수 있어요! ✨"""
        }
    },
    "carrot": {
        "first_contact": {
            "title": "당근마켓 첫 연락",
            "content": """안녕하세요!

{title} 관련 문의 주셨네요.
청주 지역에서 가까우시면 방문 상담도 가능합니다.

채팅으로 편하게 문의주세요! 😊"""
        }
    },
    "naver": {
        "first_contact": {
            "title": "네이버 첫 연락",
            "content": """안녕하세요, {author}님!

{title}에 관심 가져주셔서 감사합니다.
블로그에 더 자세한 정보가 있으니 참고해주세요.

추가 문의사항은 댓글이나 전화로 연락 주세요!
📞 043-XXX-XXXX"""
        }
    }
}


def _ensure_response_templates_table(cursor):
    """response_templates 테이블 생성 (없으면)"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS response_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            template_type TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            is_default INTEGER DEFAULT 0,
            usage_count INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            updated_at TEXT DEFAULT (datetime('now', 'localtime'))
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_response_templates_platform
        ON response_templates(platform, template_type)
    """)


@router.get("/suggest-response")
async def suggest_response(
    platform: str,
    template_type: str = "first_contact",
    lead_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    [Phase 4.0] 플랫폼별 응답 템플릿 추천

    Args:
        platform: 플랫폼 (cafe, youtube, tiktok, instagram, carrot, naver)
        template_type: 템플릿 유형 (first_contact, follow_up)
        lead_id: 리드 ID (있으면 리드 정보로 템플릿 채움)

    Returns:
        추천 템플릿 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_response_templates_table(cursor)

        # 플랫폼 정규화
        platform = _normalize_platform(platform)

        # 리드 정보 조회 (있으면)
        lead_info = {"author": "고객님", "title": ""}
        if lead_id:
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
            if cursor.fetchone():
                columns = _get_table_columns(cursor, 'mentions')
                author_col = 'author' if 'author' in columns else 'target_name'

                cursor.execute(f"""
                    SELECT title, {author_col}
                    FROM mentions WHERE id = ?
                """, (lead_id,))
                row = cursor.fetchone()
                if row:
                    lead_info["title"] = row[0] or ""
                    lead_info["author"] = row[1] or "고객님"

        # 사용자 정의 템플릿 조회
        cursor.execute("""
            SELECT id, title, content, usage_count
            FROM response_templates
            WHERE platform = ? AND template_type = ?
            ORDER BY usage_count DESC
            LIMIT 5
        """, (platform, template_type))
        custom_templates = [
            {
                "id": row[0],
                "title": row[1],
                "content": row[2].format(**lead_info) if row[2] else "",
                "usage_count": row[3],
                "is_custom": True
            }
            for row in cursor.fetchall()
        ]

        conn.close()

        # 기본 템플릿
        default_templates = []
        if platform in DEFAULT_TEMPLATES:
            platform_templates = DEFAULT_TEMPLATES[platform]
            if template_type in platform_templates:
                tpl = platform_templates[template_type]
                try:
                    content = tpl["content"].format(**lead_info)
                except KeyError:
                    content = tpl["content"]

                default_templates.append({
                    "id": None,
                    "title": tpl["title"],
                    "content": content,
                    "usage_count": 0,
                    "is_custom": False
                })

        # 사용자 정의 템플릿 + 기본 템플릿
        all_templates = custom_templates + default_templates

        return {
            "platform": platform,
            "template_type": template_type,
            "templates": all_templates,
            "lead_info": lead_info
        }

    except Exception as e:
        print(f"[leads/suggest-response Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"템플릿 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class ResponseTemplateCreate(BaseModel):
    """응답 템플릿 생성"""
    platform: str
    template_type: str = "first_contact"
    title: str
    content: str


@router.post("/response-templates")
async def create_response_template(data: ResponseTemplateCreate) -> Dict[str, Any]:
    """
    [Phase 4.0] 응답 템플릿 생성
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_response_templates_table(cursor)

        platform = _normalize_platform(data.platform)

        cursor.execute("""
            INSERT INTO response_templates (platform, template_type, title, content)
            VALUES (?, ?, ?, ?)
        """, (platform, data.template_type, data.title, data.content))

        template_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "success": True,
            "template_id": template_id,
            "message": "템플릿이 생성되었습니다"
        }

    except Exception as e:
        print(f"[leads/response-templates Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"템플릿 생성 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/response-templates/{template_id}/use")
async def use_response_template(template_id: int) -> Dict[str, Any]:
    """
    [Phase 4.0] 템플릿 사용 기록 (사용 횟수 증가)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE response_templates
            SET usage_count = usage_count + 1, updated_at = datetime('now', 'localtime')
            WHERE id = ?
        """, (template_id,))

        conn.commit()
        conn.close()

        return {"success": True}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [P2-1] 전환 트렌드 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/conversion-trends")
async def get_conversion_trends(days: int = 30) -> Dict[str, Any]:
    """
    [P2-1] 일별 전환 트렌드 조회

    Args:
        days: 조회할 일수 (기본 30일)

    Returns:
        daily_trends: 일별 전환 데이터
        summary: 기간 요약 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # mentions 테이블 존재 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {"daily_trends": [], "summary": {}}

        # 컬럼 확인
        cursor.execute("PRAGMA table_info(mentions)")
        cols = [row[1] for row in cursor.fetchall()]
        date_col = 'created_at' if 'created_at' in cols else 'scraped_at'
        has_status = 'status' in cols

        if not has_status:
            conn.close()
            return {"daily_trends": [], "summary": {}}

        # 일별 상태 변화 집계
        cursor.execute(f"""
            SELECT
                DATE({date_col}) as date,
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'contacted' THEN 1 ELSE 0 END) as contacted,
                SUM(CASE WHEN status = 'replied' THEN 1 ELSE 0 END) as replied,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                SUM(CASE WHEN status = 'rejected' THEN 1 ELSE 0 END) as rejected
            FROM mentions
            WHERE {date_col} >= DATE('now', '-{days} days')
            GROUP BY DATE({date_col})
            ORDER BY date DESC
        """)

        rows = cursor.fetchall()

        daily_trends = []
        total_leads = 0
        total_contacted = 0
        total_converted = 0

        for row in rows:
            date, leads, contacted, replied, converted, rejected = row
            daily_trends.append({
                "date": date,
                "total_leads": leads or 0,
                "contacted": contacted or 0,
                "replied": replied or 0,
                "converted": converted or 0,
                "rejected": rejected or 0,
                "conversion_rate": round((converted or 0) / leads * 100, 1) if leads > 0 else 0
            })
            total_leads += leads or 0
            total_contacted += contacted or 0
            total_converted += converted or 0

        # 주별 집계
        cursor.execute(f"""
            SELECT
                strftime('%Y-%W', {date_col}) as week,
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted
            FROM mentions
            WHERE {date_col} >= DATE('now', '-{days} days')
            GROUP BY strftime('%Y-%W', {date_col})
            ORDER BY week DESC
            LIMIT 8
        """)

        weekly_rows = cursor.fetchall()
        weekly_trends = []
        for row in weekly_rows:
            week, leads, converted = row
            weekly_trends.append({
                "week": week,
                "total_leads": leads or 0,
                "converted": converted or 0,
                "conversion_rate": round((converted or 0) / leads * 100, 1) if leads > 0 else 0
            })

        conn.close()

        return {
            "daily_trends": daily_trends[:14],  # 최근 14일만
            "weekly_trends": weekly_trends,
            "summary": {
                "period_days": days,
                "total_leads": total_leads,
                "total_contacted": total_contacted,
                "total_converted": total_converted,
                "overall_conversion_rate": round(total_converted / total_leads * 100, 1) if total_leads > 0 else 0
            }
        }

    except Exception as e:
        print(f"[conversion-trends Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 병목 분석 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/bottleneck-analysis")
async def get_bottleneck_analysis() -> Dict[str, Any]:
    """
    [Phase 4.0] 리드 파이프라인 병목 분석

    각 단계별 소요 시간을 분석하여 병목 구간을 발견합니다.

    Returns:
        - stage_durations: 단계별 평균 소요 시간 (시간 단위)
        - bottleneck: 가장 오래 걸리는 단계
        - recommendations: 개선 권장사항
    """
    try:
        import json
        from datetime import datetime

        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # mentions 테이블 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {"stage_durations": {}, "bottleneck": None, "recommendations": []}

        columns = _get_table_columns(cursor, 'mentions')
        if 'stage_timestamps' not in columns:
            conn.close()
            return {"stage_durations": {}, "bottleneck": None, "recommendations": []}

        # 타임스탬프가 있는 리드 조회
        cursor.execute("""
            SELECT stage_timestamps, status
            FROM mentions
            WHERE stage_timestamps IS NOT NULL AND stage_timestamps != '{}'
            ORDER BY created_at DESC
            LIMIT 500
        """)

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return {"stage_durations": {}, "bottleneck": None, "recommendations": []}

        # 단계별 소요 시간 계산
        stage_order = ['pending', 'contacted', 'replied', 'converted']
        stage_durations = {
            'pending_to_contacted': [],
            'contacted_to_replied': [],
            'replied_to_converted': []
        }

        for row in rows:
            try:
                timestamps = json.loads(row[0])
                if len(timestamps) < 2:
                    continue

                # 각 단계 사이의 시간 계산
                for i, stage in enumerate(stage_order[:-1]):
                    next_stage = stage_order[i + 1]
                    if stage in timestamps and next_stage in timestamps:
                        t1 = datetime.fromisoformat(timestamps[stage])
                        t2 = datetime.fromisoformat(timestamps[next_stage])
                        duration_hours = (t2 - t1).total_seconds() / 3600
                        if duration_hours >= 0:  # 음수 제외
                            stage_durations[f'{stage}_to_{next_stage}'].append(duration_hours)
            except (ValueError, TypeError, KeyError):
                continue

        # 평균 계산
        avg_durations = {}
        for key, values in stage_durations.items():
            if values:
                avg_durations[key] = round(sum(values) / len(values), 1)
            else:
                avg_durations[key] = None

        # 병목 구간 찾기
        bottleneck = None
        max_duration = 0
        for key, duration in avg_durations.items():
            if duration and duration > max_duration:
                max_duration = duration
                bottleneck = key

        # 권장사항 생성
        recommendations = []
        if bottleneck:
            if 'pending_to_contacted' in bottleneck:
                if max_duration > 24:
                    recommendations.append("첫 연락까지 평균 24시간 이상 소요 - Hot Lead 알림 활성화 권장")
                if max_duration > 48:
                    recommendations.append("긴급: 자동 리마인더 설정으로 리드 이탈 방지 필요")
            elif 'contacted_to_replied' in bottleneck:
                if max_duration > 72:
                    recommendations.append("응답 대기 시간이 김 - 팔로업 메시지 전략 개선 필요")
            elif 'replied_to_converted' in bottleneck:
                if max_duration > 168:  # 1주일
                    recommendations.append("전환까지 시간이 김 - 클로징 스크립트 개선 권장")

        return {
            "stage_durations": avg_durations,
            "bottleneck": bottleneck,
            "max_duration_hours": max_duration,
            "sample_size": len([r for r in rows if r[0] and r[0] != '{}']),
            "recommendations": recommendations,
            "stage_labels": {
                "pending_to_contacted": "발견 → 첫 연락",
                "contacted_to_replied": "첫 연락 → 응답",
                "replied_to_converted": "응답 → 전환"
            }
        }

    except Exception as e:
        print(f"[bottleneck-analysis Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] ROI 분석 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/roi-analysis")
async def get_roi_analysis() -> Dict[str, Any]:
    """
    [Phase 4.0] 마케팅 ROI 분석

    채널별, 키워드별 투자 대비 수익을 분석합니다.

    Returns:
        - overall_roi: 전체 ROI
        - by_platform: 플랫폼별 ROI
        - by_keyword: 키워드별 ROI (상위 10개)
        - insights: 인사이트
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # mentions 테이블 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {"overall_roi": {}, "by_platform": [], "by_keyword": [], "insights": []}

        columns = _get_table_columns(cursor, 'mentions')
        platform_col = 'platform' if 'platform' in columns else 'source'
        keyword_col = 'source_keyword' if 'source_keyword' in columns else 'category'

        has_revenue = 'expected_revenue' in columns and 'actual_revenue' in columns

        if not has_revenue:
            conn.close()
            return {
                "overall_roi": {"message": "매출 데이터가 없습니다. 리드에 예상/실제 매출을 입력해주세요."},
                "by_platform": [],
                "by_keyword": [],
                "insights": ["아직 매출 데이터가 입력되지 않았습니다."]
            }

        # 전체 ROI
        cursor.execute(f"""
            SELECT
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                SUM(COALESCE(expected_revenue, 0)) as total_expected,
                SUM(COALESCE(actual_revenue, 0)) as total_actual
            FROM mentions
        """)
        overall = cursor.fetchone()

        # 플랫폼별 ROI
        cursor.execute(f"""
            SELECT
                {platform_col} as platform,
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                SUM(COALESCE(expected_revenue, 0)) as expected,
                SUM(COALESCE(actual_revenue, 0)) as actual
            FROM mentions
            WHERE {platform_col} IS NOT NULL
            GROUP BY {platform_col}
            ORDER BY actual DESC
        """)

        by_platform = []
        for row in cursor.fetchall():
            platform = _normalize_platform(row[0] or '')
            leads = row[1] or 0
            converted = row[2] or 0
            expected = row[3] or 0
            actual = row[4] or 0

            by_platform.append({
                "platform": platform,
                "total_leads": leads,
                "converted": converted,
                "conversion_rate": round(converted / leads * 100, 1) if leads > 0 else 0,
                "expected_revenue": expected,
                "actual_revenue": actual,
                "avg_revenue_per_lead": round(actual / leads, 0) if leads > 0 else 0,
                "avg_revenue_per_conversion": round(actual / converted, 0) if converted > 0 else 0
            })

        # 키워드별 ROI (source_keyword 기준)
        cursor.execute(f"""
            SELECT
                {keyword_col} as keyword,
                COUNT(*) as total_leads,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted,
                SUM(COALESCE(expected_revenue, 0)) as expected,
                SUM(COALESCE(actual_revenue, 0)) as actual
            FROM mentions
            WHERE {keyword_col} IS NOT NULL AND {keyword_col} != ''
            GROUP BY {keyword_col}
            ORDER BY actual DESC
            LIMIT 10
        """)

        by_keyword = []
        for row in cursor.fetchall():
            keyword = row[0]
            leads = row[1] or 0
            converted = row[2] or 0
            expected = row[3] or 0
            actual = row[4] or 0

            by_keyword.append({
                "keyword": keyword,
                "total_leads": leads,
                "converted": converted,
                "conversion_rate": round(converted / leads * 100, 1) if leads > 0 else 0,
                "expected_revenue": expected,
                "actual_revenue": actual,
                "avg_revenue_per_lead": round(actual / leads, 0) if leads > 0 else 0
            })

        conn.close()

        # 인사이트 생성
        insights = []
        total_actual = overall[3] or 0
        total_converted = overall[1] or 0

        if by_platform:
            best_platform = max(by_platform, key=lambda x: x['avg_revenue_per_lead'])
            if best_platform['avg_revenue_per_lead'] > 0:
                insights.append(
                    f"💡 {best_platform['platform']}이(가) 리드당 평균 매출이 가장 높습니다 "
                    f"(₩{best_platform['avg_revenue_per_lead']:,.0f})"
                )

        if by_keyword:
            best_keyword = max(by_keyword, key=lambda x: x['conversion_rate'])
            if best_keyword['conversion_rate'] > 0:
                insights.append(
                    f"🎯 '{best_keyword['keyword']}' 키워드의 전환율이 가장 높습니다 "
                    f"({best_keyword['conversion_rate']}%)"
                )

        return {
            "overall_roi": {
                "total_leads": overall[0] or 0,
                "total_converted": total_converted,
                "conversion_rate": round(total_converted / overall[0] * 100, 1) if overall[0] > 0 else 0,
                "total_expected_revenue": overall[2] or 0,
                "total_actual_revenue": total_actual,
                "avg_revenue_per_conversion": round(total_actual / total_converted, 0) if total_converted > 0 else 0
            },
            "by_platform": by_platform,
            "by_keyword": by_keyword,
            "insights": insights
        }

    except Exception as e:
        print(f"[roi-analysis Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 목표 달성 예상일 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/goal-forecast")
async def get_goal_forecast(
    goal_type: str = "conversions",  # conversions, revenue, leads
    target_value: int = 10,
    days_history: int = 30
) -> Dict[str, Any]:
    """
    [Phase 4.0] 목표 달성 예상일 계산

    과거 데이터를 기반으로 목표 달성까지 필요한 일수를 예측합니다.

    Args:
        goal_type: 목표 유형 (conversions, revenue, leads)
        target_value: 목표값
        days_history: 분석할 과거 일수

    Returns:
        - current_value: 현재 값
        - daily_average: 일일 평균
        - days_to_goal: 목표까지 예상 일수
        - expected_date: 예상 달성일
    """
    try:
        from datetime import datetime, timedelta

        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # mentions 테이블 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
        if not cursor.fetchone():
            conn.close()
            return {"error": "데이터가 없습니다"}

        columns = _get_table_columns(cursor, 'mentions')
        date_col = 'created_at' if 'created_at' in columns else 'scraped_at'

        # 목표 유형별 쿼리
        if goal_type == "conversions":
            cursor.execute(f"""
                SELECT
                    DATE({date_col}) as date,
                    SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as value
                FROM mentions
                WHERE {date_col} >= DATE('now', '-{days_history} days')
                GROUP BY DATE({date_col})
                ORDER BY date DESC
            """)
            current_query = "SELECT COUNT(*) FROM mentions WHERE status = 'converted'"
            metric_name = "전환"

        elif goal_type == "revenue":
            if 'actual_revenue' not in columns:
                conn.close()
                return {"error": "매출 데이터가 없습니다"}

            cursor.execute(f"""
                SELECT
                    DATE({date_col}) as date,
                    SUM(COALESCE(actual_revenue, 0)) as value
                FROM mentions
                WHERE {date_col} >= DATE('now', '-{days_history} days')
                GROUP BY DATE({date_col})
                ORDER BY date DESC
            """)
            current_query = "SELECT SUM(COALESCE(actual_revenue, 0)) FROM mentions"
            metric_name = "매출"

        else:  # leads
            cursor.execute(f"""
                SELECT
                    DATE({date_col}) as date,
                    COUNT(*) as value
                FROM mentions
                WHERE {date_col} >= DATE('now', '-{days_history} days')
                GROUP BY DATE({date_col})
                ORDER BY date DESC
            """)
            current_query = "SELECT COUNT(*) FROM mentions"
            metric_name = "리드"

        daily_data = cursor.fetchall()

        # 현재 값 조회
        cursor.execute(current_query)
        current_value = cursor.fetchone()[0] or 0

        conn.close()

        if not daily_data:
            return {
                "goal_type": goal_type,
                "metric_name": metric_name,
                "target_value": target_value,
                "current_value": current_value,
                "daily_average": 0,
                "days_to_goal": None,
                "expected_date": None,
                "message": "충분한 데이터가 없습니다"
            }

        # 일일 평균 계산
        total_value = sum(row[1] or 0 for row in daily_data)
        days_with_data = len(daily_data)
        daily_average = total_value / days_with_data if days_with_data > 0 else 0

        # 목표까지 남은 값
        remaining = target_value - current_value

        if remaining <= 0:
            return {
                "goal_type": goal_type,
                "metric_name": metric_name,
                "target_value": target_value,
                "current_value": current_value,
                "daily_average": round(daily_average, 1),
                "days_to_goal": 0,
                "expected_date": datetime.now().strftime("%Y-%m-%d"),
                "message": "🎉 목표 달성 완료!"
            }

        # 예상 일수 계산
        if daily_average > 0:
            days_to_goal = remaining / daily_average
            expected_date = datetime.now() + timedelta(days=days_to_goal)

            return {
                "goal_type": goal_type,
                "metric_name": metric_name,
                "target_value": target_value,
                "current_value": current_value,
                "remaining": remaining,
                "daily_average": round(daily_average, 1),
                "days_to_goal": round(days_to_goal, 1),
                "expected_date": expected_date.strftime("%Y-%m-%d"),
                "message": f"현재 속도로 약 {round(days_to_goal)}일 후 목표 달성 예상"
            }
        else:
            return {
                "goal_type": goal_type,
                "metric_name": metric_name,
                "target_value": target_value,
                "current_value": current_value,
                "remaining": remaining,
                "daily_average": 0,
                "days_to_goal": None,
                "expected_date": None,
                "message": "일일 평균이 0입니다. 더 많은 활동이 필요합니다."
            }

    except Exception as e:
        print(f"[goal-forecast Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 키워드-리드 귀속 (Attribution) API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_keyword_lead_attribution_table(cursor):
    """keyword_lead_attribution 테이블 생성"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS keyword_lead_attribution (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            lead_id INTEGER NOT NULL,
            attribution_type TEXT DEFAULT 'direct',  -- direct, assisted, organic
            created_at TEXT DEFAULT (datetime('now', 'localtime')),
            FOREIGN KEY (lead_id) REFERENCES mentions(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kla_keyword ON keyword_lead_attribution(keyword)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_kla_lead_id ON keyword_lead_attribution(lead_id)
    """)


class KeywordAttribution(BaseModel):
    """키워드 귀속 생성"""
    keyword: str
    lead_id: int
    attribution_type: str = "direct"


@router.post("/keyword-attribution")
async def add_keyword_attribution(data: KeywordAttribution) -> Dict[str, Any]:
    """
    [Phase 4.0] 키워드-리드 귀속 추가

    특정 리드가 어떤 키워드를 통해 유입되었는지 기록합니다.

    Args:
        data: 키워드, 리드 ID, 귀속 유형

    Returns:
        생성된 귀속 ID
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_keyword_lead_attribution_table(cursor)

        # 중복 체크
        cursor.execute("""
            SELECT id FROM keyword_lead_attribution
            WHERE keyword = ? AND lead_id = ?
        """, (data.keyword, data.lead_id))

        if cursor.fetchone():
            conn.close()
            return {"success": False, "message": "이미 귀속이 존재합니다"}

        cursor.execute("""
            INSERT INTO keyword_lead_attribution (keyword, lead_id, attribution_type)
            VALUES (?, ?, ?)
        """, (data.keyword, data.lead_id, data.attribution_type))

        attribution_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {
            "success": True,
            "attribution_id": attribution_id,
            "message": "키워드 귀속이 추가되었습니다"
        }

    except Exception as e:
        print(f"[keyword-attribution Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/keyword-lead-analysis")
async def get_keyword_lead_analysis() -> Dict[str, Any]:
    """
    [Phase 4.0] 키워드별 리드 분석

    키워드별로 얼마나 많은 리드가 유입되었는지 분석합니다.

    Returns:
        - by_keyword: 키워드별 리드 수 및 전환율
        - top_keywords: 상위 키워드
        - attribution_types: 귀속 유형별 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_keyword_lead_attribution_table(cursor)

        # 키워드별 리드 수 및 전환
        cursor.execute("""
            SELECT
                kla.keyword,
                COUNT(DISTINCT kla.lead_id) as total_leads,
                COUNT(DISTINCT CASE WHEN m.status = 'converted' THEN kla.lead_id END) as converted,
                kla.attribution_type
            FROM keyword_lead_attribution kla
            LEFT JOIN mentions m ON kla.lead_id = m.id
            GROUP BY kla.keyword, kla.attribution_type
            ORDER BY total_leads DESC
            LIMIT 30
        """)

        keyword_stats = {}
        for row in cursor.fetchall():
            keyword = row[0]
            if keyword not in keyword_stats:
                keyword_stats[keyword] = {
                    "keyword": keyword,
                    "total_leads": 0,
                    "converted": 0,
                    "direct": 0,
                    "assisted": 0,
                    "organic": 0
                }

            keyword_stats[keyword]["total_leads"] += row[1]
            keyword_stats[keyword]["converted"] += row[2] or 0
            keyword_stats[keyword][row[3]] = row[1]

        # 전환율 계산
        by_keyword = []
        for stats in keyword_stats.values():
            stats["conversion_rate"] = round(
                (stats["converted"] / stats["total_leads"] * 100)
                if stats["total_leads"] > 0 else 0, 1
            )
            by_keyword.append(stats)

        # 상위 키워드 (리드 수 기준)
        by_keyword.sort(key=lambda x: x["total_leads"], reverse=True)
        top_keywords = by_keyword[:10]

        # 귀속 유형별 통계
        cursor.execute("""
            SELECT attribution_type, COUNT(*) as count
            FROM keyword_lead_attribution
            GROUP BY attribution_type
        """)
        attribution_types = {row[0]: row[1] for row in cursor.fetchall()}

        conn.close()

        return {
            "by_keyword": by_keyword,
            "top_keywords": top_keywords,
            "attribution_types": attribution_types,
            "total_attributions": sum(attribution_types.values())
        }

    except Exception as e:
        print(f"[keyword-lead-analysis Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# =====================================
# [P3-2] 품질 트렌드 API
# =====================================

# 캐싱용 변수
_quality_trend_cache: Dict[str, Any] = {}
_cache_timestamp: float = 0
_cache_ttl: int = 300  # 5분

def _get_cached_quality_trend() -> Optional[Dict[str, Any]]:
    """캐시된 품질 트렌드 데이터 반환"""
    import time
    global _cache_timestamp
    if time.time() - _cache_timestamp < _cache_ttl:
        return _quality_trend_cache.get('data')
    return None

def _set_quality_trend_cache(data: Dict[str, Any]):
    """품질 트렌드 데이터 캐싱"""
    import time
    global _quality_trend_cache, _cache_timestamp
    _quality_trend_cache['data'] = data
    _cache_timestamp = time.time()


@router.get("/quality-trends")
async def get_quality_trends(days: int = 14) -> Dict[str, Any]:
    """
    [P3-2] 일별 품질 트렌드 API

    최근 N일간의 리드 품질 트렌드를 반환합니다.
    - 일별 평균 신뢰도 점수
    - 일별 연락처 보유율
    - 일별 리드 등급 분포

    Args:
        days: 조회할 일수 (기본 14일)

    Returns:
        일별 품질 트렌드 데이터 (5분 캐싱)
    """
    # 캐시 확인
    cached = _get_cached_quality_trend()
    if cached and cached.get('days') == days:
        cached['from_cache'] = True
        return cached

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 일별 품질 통계
        cursor.execute("""
            SELECT
                DATE(created_at) as date,
                COUNT(*) as total,
                AVG(COALESCE(trust_score, 50)) as avg_trust,
                SUM(CASE WHEN contact_info IS NOT NULL AND contact_info != '' THEN 1 ELSE 0 END) as with_contact,
                SUM(CASE WHEN trust_level = 'trusted' THEN 1 ELSE 0 END) as trusted_count,
                SUM(CASE WHEN trust_level = 'review' THEN 1 ELSE 0 END) as review_count,
                SUM(CASE WHEN trust_level = 'suspicious' THEN 1 ELSE 0 END) as suspicious_count
            FROM mentions
            WHERE created_at >= DATE('now', '-' || ? || ' days')
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """, (days,))

        daily_data = []
        for row in cursor.fetchall():
            date, total, avg_trust, with_contact, trusted, review, suspicious = row
            contact_rate = round((with_contact / total * 100) if total > 0 else 0, 1)
            daily_data.append({
                'date': date,
                'total': total,
                'avg_trust_score': round(avg_trust, 1) if avg_trust else 50,
                'contact_rate': contact_rate,
                'distribution': {
                    'trusted': trusted or 0,
                    'review': review or 0,
                    'suspicious': suspicious or 0
                }
            })

        # 전체 기간 요약
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                AVG(COALESCE(trust_score, 50)) as avg_trust,
                SUM(CASE WHEN contact_info IS NOT NULL AND contact_info != '' THEN 1 ELSE 0 END) as with_contact
            FROM mentions
            WHERE created_at >= DATE('now', '-' || ? || ' days')
        """, (days,))

        summary_row = cursor.fetchone()
        total, avg_trust, with_contact = summary_row
        summary = {
            'total_leads': total or 0,
            'avg_trust_score': round(avg_trust, 1) if avg_trust else 50,
            'contact_rate': round((with_contact / total * 100) if total and total > 0 else 0, 1)
        }

        conn.close()

        result = {
            'days': days,
            'daily_trends': daily_data,
            'summary': summary,
            'from_cache': False
        }

        # 캐시 저장
        _set_quality_trend_cache(result)

        return result

    except Exception as e:
        print(f"[quality-trends Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/platform-quality")
async def get_platform_quality_comparison() -> Dict[str, Any]:
    """
    [P3-2] 플랫폼별 품질 비교 API

    각 플랫폼의 리드 품질을 비교합니다.
    - 플랫폼별 평균 신뢰도
    - 플랫폼별 연락처 보유율
    - 플랫폼별 전환율

    Returns:
        플랫폼별 품질 비교 데이터
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 플랫폼별 품질 통계
        cursor.execute("""
            SELECT
                platform,
                COUNT(*) as total,
                AVG(COALESCE(trust_score, 50)) as avg_trust,
                SUM(CASE WHEN contact_info IS NOT NULL AND contact_info != '' THEN 1 ELSE 0 END) as with_contact,
                SUM(CASE WHEN trust_level = 'trusted' THEN 1 ELSE 0 END) as trusted_count,
                SUM(CASE WHEN trust_level = 'suspicious' THEN 1 ELSE 0 END) as suspicious_count,
                SUM(CASE WHEN status = 'converted' THEN 1 ELSE 0 END) as converted_count
            FROM mentions
            GROUP BY platform
            ORDER BY total DESC
        """)

        platform_data = []
        for row in cursor.fetchall():
            platform, total, avg_trust, with_contact, trusted, suspicious, converted = row
            if total == 0:
                continue

            contact_rate = round((with_contact / total * 100), 1)
            trusted_rate = round((trusted / total * 100), 1) if trusted else 0
            suspicious_rate = round((suspicious / total * 100), 1) if suspicious else 0
            conversion_rate = round((converted / total * 100), 1) if converted else 0

            # 품질 점수 계산 (신뢰도 + 연락처율 + 전환율)
            quality_score = round(
                (avg_trust or 50) * 0.5 +
                contact_rate * 0.3 +
                conversion_rate * 20 * 0.2
            , 1)

            platform_data.append({
                'platform': platform or 'unknown',
                'total': total,
                'avg_trust_score': round(avg_trust, 1) if avg_trust else 50,
                'contact_rate': contact_rate,
                'trusted_rate': trusted_rate,
                'suspicious_rate': suspicious_rate,
                'conversion_rate': conversion_rate,
                'quality_score': quality_score
            })

        # 품질 점수 순 정렬
        platform_data.sort(key=lambda x: x['quality_score'], reverse=True)

        # 최고/최저 품질 플랫폼
        best_platform = platform_data[0] if platform_data else None
        worst_platform = platform_data[-1] if len(platform_data) > 1 else None

        conn.close()

        return {
            'platforms': platform_data,
            'best_platform': best_platform,
            'worst_platform': worst_platform,
            'total_platforms': len(platform_data)
        }

    except Exception as e:
        print(f"[platform-quality Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ============================================================
# [Phase 5.0] AI 기반 응답 생성
# ============================================================

class AIResponseRequest(BaseModel):
    """AI 응답 생성 요청"""
    lead_id: int
    response_type: str = "first_contact"  # first_contact, follow_up, closing
    tone: str = "professional"  # professional, friendly, casual
    include_promotion: bool = False
    custom_instructions: Optional[str] = None


@router.post("/generate-ai-response")
async def generate_ai_response(request: AIResponseRequest) -> Dict[str, Any]:
    """
    [Phase 5.0] Gemini AI 기반 개인화된 응답 메시지 생성

    리드 정보(콘텐츠 제목, 본문, 플랫폼, 고객 정보)를 분석하여
    맥락에 맞는 자연스러운 첫 접촉 메시지를 생성합니다.

    Args:
        lead_id: 리드 ID
        response_type: 응답 유형 (first_contact, follow_up, closing)
        tone: 어조 (professional, friendly, casual)
        include_promotion: 프로모션 정보 포함 여부
        custom_instructions: 사용자 지정 지시사항

    Returns:
        생성된 응답 메시지와 분석 결과
    """
    from services.ai_client import ai_generate, ai_generate_json

    try:
        import json

        # 리드 정보 조회
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        columns = _get_table_columns(cursor, 'mentions')
        author_col = 'author' if 'author' in columns else 'target_name'

        cursor.execute(f"""
            SELECT id, platform, title, content, {author_col} as author,
                   lead_score, trust_score, notes
            FROM mentions
            WHERE id = ?
        """, (request.lead_id,))

        lead = cursor.fetchone()
        if not lead:
            conn.close()
            raise HTTPException(status_code=404, detail="리드를 찾을 수 없습니다")

        lead_data = dict(lead)

        # 업체 프로필 로드 (있으면)
        business_profile = {}
        profile_path = Path(__file__).parent.parent.parent / "config" / "business_profile.json"
        if profile_path.exists():
            with open(profile_path, 'r', encoding='utf-8') as f:
                business_profile = json.load(f)

        # [Phase 8] Q&A 매칭 - 헬퍼 함수로 분리
        lead_text = f"{lead_data.get('title', '')} {lead_data.get('content', '')}"
        qa_matches = _find_qa_matches(cursor, lead_text, max_matches=3)

        conn.close()

        # 어조별 지시사항
        tone_instructions = {
            "professional": "전문적이고 신뢰감 있는 어조로 작성하세요.",
            "friendly": "친근하고 따뜻한 어조로 작성하세요.",
            "casual": "편안하고 가벼운 어조로 작성하세요."
        }

        # 응답 유형별 지시사항
        type_instructions = {
            "first_contact": "처음 연락하는 상황입니다. 자연스럽게 대화를 시작하고, 고객의 관심사에 공감을 표현하세요.",
            "follow_up": "이전에 연락한 적 있는 고객입니다. 이전 대화를 참고하여 후속 연락을 하세요.",
            "closing": "관심을 보인 고객에게 최종 결정을 유도하는 메시지입니다. 긴박감을 주되 압박하지 마세요."
        }

        # [Phase 7.0] Q&A 참조 텍스트 생성
        qa_reference_text = ""
        if qa_matches:
            qa_items = []
            for qa in qa_matches:
                qa_items.append(f"  - 질문 패턴: {qa['question_pattern']}\n    참조 응답: {qa['standard_answer'][:200]}")
            qa_reference_text = f"""
## 참조 Q&A (고객 질문에 매칭된 표준 응답)
다음 Q&A를 참고하되, 그대로 복사하지 말고 맥락에 맞게 자연스럽게 활용하세요:
{chr(10).join(qa_items)}
"""

        # 업체 정보 추출 (business_profile.json 구조 지원)
        business_data = business_profile.get('business', business_profile)
        business_name = business_data.get('name', '한의원')
        business_region = business_data.get('region', '')
        business_address = business_data.get('address', '')

        # 프롬프트 구성
        prompt = f"""당신은 한의원 마케팅 전문가입니다. 잠재 고객에게 보낼 응답 메시지를 작성해주세요.

## 고객 정보
- 플랫폼: {lead_data.get('platform', '알 수 없음')}
- 고객명/닉네임: {lead_data.get('author', '고객님')}
- 관심 주제: {lead_data.get('title', '')[:200] if lead_data.get('title') else '일반 문의'}
- 고객 글 내용: {lead_data.get('content', '')[:500] if lead_data.get('content') else '내용 없음'}
- 리드 점수: {lead_data.get('lead_score', 'N/A')}
- 신뢰도 점수: {lead_data.get('trust_score', 'N/A')}

## 업체 정보
- 업체명: {business_name}
- 지역: {business_region}
- 주소: {business_address}
{qa_reference_text}

## 작성 지침
1. {tone_instructions.get(request.tone, tone_instructions['professional'])}
2. {type_instructions.get(request.response_type, type_instructions['first_contact'])}
3. 고객의 글 내용을 참고하여 맥락에 맞는 응답을 작성하세요.
4. 200자 이내로 간결하게 작성하세요.
5. 자연스럽고 스팸처럼 느껴지지 않게 작성하세요.
6. 구체적인 가격이나 과장된 효과는 언급하지 마세요.
{"7. 현재 진행 중인 프로모션이나 이벤트를 자연스럽게 언급하세요." if request.include_promotion else ""}
{f"8. 추가 지시사항: {request.custom_instructions}" if request.custom_instructions else ""}

## 출력 형식
응답 메시지만 작성하세요. 설명이나 부연 설명은 필요 없습니다.
"""

        # AI API 호출
        generated_message = ai_generate(prompt, temperature=0.7, max_tokens=500)

        # 메시지 분석 (키워드 추출)
        analysis_prompt = f"""다음 메시지를 분석하여 JSON 형식으로 결과를 반환하세요:

메시지: {generated_message}

JSON 형식:
{{
  "sentiment": "positive/neutral/negative",
  "key_points": ["핵심 포인트 1", "핵심 포인트 2"],
  "call_to_action": "행동 유도 문구 (있으면)",
  "improvement_suggestions": ["개선 제안 1"]
}}

JSON만 반환하세요.
"""

        analysis = ai_generate_json(analysis_prompt, temperature=0.1, max_tokens=300)
        if not analysis:
            analysis = {"error": "분석 파싱 실패"}

        # [Phase 7.0] Q&A 매칭 정보 정리
        qa_matches_info = []
        for qa in qa_matches:
            qa_matches_info.append({
                "id": qa.get('id'),
                "pattern": qa.get('question_pattern'),
                "category": qa.get('question_category'),
                "match_score": qa.get('match_score'),
                "answer_preview": qa.get('standard_answer', '')[:100]
            })

        return {
            "success": True,
            "lead_id": request.lead_id,
            "response_type": request.response_type,
            "tone": request.tone,
            "generated_message": generated_message,
            "character_count": len(generated_message),
            "analysis": analysis,
            "lead_info": {
                "platform": lead_data.get('platform'),
                "author": lead_data.get('author'),
                "title": lead_data.get('title', '')[:100] if lead_data.get('title') else None
            },
            "qa_matches": qa_matches_info,
            "qa_used": len(qa_matches_info) > 0
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[generate-ai-response Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/duplicates")
@handle_exceptions
async def get_duplicate_leads() -> Dict[str, Any]:
    """
    [Phase 6.1] 중복 리드 감지

    URL 기반으로 중복 리드를 감지하여 그룹화하여 반환합니다.

    Returns:
        중복 리드 그룹 목록 (URL별로 그룹화)
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 테이블 존재 여부 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='mentions'")
    if not cursor.fetchone():
        conn.close()
        return success_response({
            "total_duplicates": 0,
            "duplicate_groups": [],
            "duplicate_lead_ids": []
        })

    # 컬럼 확인
    columns = _get_table_columns(cursor, 'mentions')
    platform_col = select_column_safely(columns, 'platform', 'source', 'source')
    date_col = select_column_safely(columns, 'created_at', 'scraped_at', 'created_at')
    author_col = select_column_safely(columns, 'author', 'target_name', 'author')

    # 중복 URL 찾기 (2개 이상 존재하는 URL)
    cursor.execute("""
        SELECT url, COUNT(*) as count
        FROM mentions
        WHERE url IS NOT NULL AND url != ''
        GROUP BY url
        HAVING COUNT(*) > 1
        ORDER BY count DESC
    """)

    duplicate_urls = cursor.fetchall()

    if not duplicate_urls:
        conn.close()
        return success_response({
            "total_duplicates": 0,
            "duplicate_groups": [],
            "duplicate_lead_ids": []
        })

    # 각 중복 그룹의 상세 정보 조회
    duplicate_groups = []
    all_duplicate_ids = []

    for dup_row in duplicate_urls:
        url = dup_row['url']
        count = dup_row['count']

        cursor.execute(f"""
            SELECT
                id,
                {platform_col} as platform,
                title,
                url,
                COALESCE(status, 'pending') as status,
                {author_col} as author,
                {date_col} as created_at
            FROM mentions
            WHERE url = ?
            ORDER BY {date_col} DESC
        """, (url,))

        leads_in_group = [dict(row) for row in cursor.fetchall()]

        # 첫 번째를 원본, 나머지를 중복으로 표시
        for i, lead in enumerate(leads_in_group):
            lead['is_original'] = (i == 0)
            if i > 0:
                all_duplicate_ids.append(lead['id'])

        duplicate_groups.append({
            "url": url,
            "count": count,
            "leads": leads_in_group
        })

    conn.close()

    return success_response({
        "total_duplicates": len(all_duplicate_ids),
        "total_groups": len(duplicate_groups),
        "duplicate_groups": duplicate_groups,
        "duplicate_lead_ids": all_duplicate_ids
    })


@router.post("/merge-duplicates")
@handle_exceptions
async def merge_duplicate_leads(merge_ids: List[int], keep_id: int) -> Dict[str, Any]:
    """
    [Phase 6.1] 중복 리드 병합

    여러 중복 리드를 하나로 병합합니다.
    keep_id의 리드를 유지하고 나머지는 archived 상태로 변경합니다.

    Args:
        merge_ids: 병합할 리드 ID 목록
        keep_id: 유지할 리드 ID

    Returns:
        병합 결과
    """
    if keep_id not in merge_ids:
        raise HTTPException(status_code=400, detail="keep_id must be in merge_ids")

    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        # 나머지 리드들을 archived 상태로 변경
        ids_to_archive = [id for id in merge_ids if id != keep_id]

        if ids_to_archive:
            placeholders = ','.join('?' * len(ids_to_archive))
            cursor.execute(f"""
                UPDATE mentions
                SET status = 'archived',
                    notes = COALESCE(notes, '') || ' [중복으로 병합됨 → ID: {keep_id}]'
                WHERE id IN ({placeholders})
            """, ids_to_archive)

            conn.commit()

        conn.close()

        return success_response({
            "success": True,
            "kept_id": keep_id,
            "archived_ids": ids_to_archive,
            "archived_count": len(ids_to_archive)
        })

    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"병합 실패: {str(e)}")


class ContactHistoryCreate(BaseModel):
    """컨택 히스토리 생성 요청"""
    lead_id: int
    contact_type: str = "comment"  # comment, dm, email, call
    content: str
    platform: Optional[str] = None
    template_id: Optional[int] = None
    notes: Optional[str] = None


@router.get("/{lead_id}/contact-history")
@handle_exceptions
async def get_contact_history(lead_id: int) -> Dict[str, Any]:
    """
    [Phase 6.1] 리드별 컨택 히스토리 조회

    Args:
        lead_id: 리드 ID

    Returns:
        컨택 히스토리 목록
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 테이블 존재 여부 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contact_history'")
    if not cursor.fetchone():
        conn.close()
        return success_response({
            "lead_id": lead_id,
            "history": [],
            "total": 0
        })

    cursor.execute("""
        SELECT
            id, lead_id, contact_type, content, platform,
            template_id, status, response, created_at,
            responded_at, notes
        FROM contact_history
        WHERE lead_id = ?
        ORDER BY created_at DESC
    """, (lead_id,))

    rows = cursor.fetchall()
    history = [dict(row) for row in rows]

    conn.close()

    return success_response({
        "lead_id": lead_id,
        "history": history,
        "total": len(history)
    })


@router.post("/contact-history")
@handle_exceptions
async def add_contact_history(request: ContactHistoryCreate) -> Dict[str, Any]:
    """
    [Phase 6.1] 컨택 히스토리 추가

    리드에 대한 컨택 기록을 추가합니다.

    Args:
        request: 컨택 히스토리 생성 요청

    Returns:
        생성된 컨택 히스토리
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 테이블 생성 (없으면)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS contact_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lead_id INTEGER NOT NULL,
            contact_type TEXT NOT NULL DEFAULT 'comment',
            content TEXT,
            platform TEXT,
            template_id INTEGER,
            status TEXT DEFAULT 'sent',
            response TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            responded_at TIMESTAMP,
            notes TEXT,
            FOREIGN KEY (lead_id) REFERENCES mentions(id) ON DELETE CASCADE
        )
    ''')

    # 컨택 히스토리 추가
    cursor.execute("""
        INSERT INTO contact_history (lead_id, contact_type, content, platform, template_id, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        request.lead_id,
        request.contact_type,
        request.content,
        request.platform,
        request.template_id,
        request.notes
    ))

    history_id = cursor.lastrowid

    # 리드 상태를 contacted로 업데이트
    cursor.execute("""
        UPDATE mentions
        SET status = CASE WHEN status = 'pending' THEN 'contacted' ELSE status END
        WHERE id = ?
    """, (request.lead_id,))

    conn.commit()
    conn.close()

    return success_response({
        "success": True,
        "id": history_id,
        "lead_id": request.lead_id,
        "message": "컨택 히스토리가 추가되었습니다"
    })


@router.put("/contact-history/{history_id}/response")
@handle_exceptions
async def update_contact_response(history_id: int, response: str, status: str = "replied") -> Dict[str, Any]:
    """
    [Phase 6.1] 컨택 응답 기록

    컨택에 대한 응답을 기록합니다.

    Args:
        history_id: 컨택 히스토리 ID
        response: 응답 내용
        status: 상태 (replied, converted, rejected)

    Returns:
        업데이트 결과
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE contact_history
        SET response = ?, status = ?, responded_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (response, status, history_id))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="컨택 히스토리를 찾을 수 없습니다")

    # 해당 리드의 상태도 업데이트
    cursor.execute("""
        UPDATE mentions
        SET status = ?
        WHERE id = (SELECT lead_id FROM contact_history WHERE id = ?)
    """, (status, history_id))

    conn.commit()
    conn.close()

    return success_response({
        "success": True,
        "history_id": history_id,
        "status": status,
        "message": "응답이 기록되었습니다"
    })


# ============================================
# [Phase 7.0] 통합 리드 프로필 API
# ============================================

class UnifiedContactCreate(BaseModel):
    """통합 연락처 생성 요청"""
    display_name: str
    lead_ids: List[int]  # 연결할 리드 ID 목록
    primary_platform: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


class UnifiedContactUpdate(BaseModel):
    """통합 연락처 수정 요청"""
    display_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    notes: Optional[str] = None
    tags: Optional[List[str]] = None


@router.get("/unified-contacts")
@handle_exceptions
async def get_unified_contacts(
    limit: int = 50,
    offset: int = 0,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """
    [Phase 7.0] 통합 연락처 목록 조회

    Returns:
        통합 연락처 목록 (연결된 리드 수 포함)
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    base_query = """
        SELECT uc.*,
               (SELECT COUNT(*) FROM mentions m WHERE m.unified_contact_id = uc.id) as linked_leads_count
        FROM unified_contacts uc
    """

    if search:
        base_query += " WHERE uc.display_name LIKE ? OR uc.email LIKE ?"
        cursor.execute(
            base_query + " ORDER BY uc.last_interaction_at DESC LIMIT ? OFFSET ?",
            (f"%{search}%", f"%{search}%", limit, offset)
        )
    else:
        cursor.execute(
            base_query + " ORDER BY uc.last_interaction_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        )

    contacts = []
    for row in cursor.fetchall():
        contact = dict(row)
        try:
            contact['tags'] = json.loads(contact.get('tags', '[]'))
        except (json.JSONDecodeError, TypeError):
            contact['tags'] = []
        contacts.append(contact)

    cursor.execute("SELECT COUNT(*) FROM unified_contacts")
    total = cursor.fetchone()[0]
    conn.close()

    return success_response({
        "contacts": contacts,
        "total": total,
        "limit": limit,
        "offset": offset
    })


@router.post("/unified-contacts")
@handle_exceptions
async def create_unified_contact(data: UnifiedContactCreate) -> Dict[str, Any]:
    """
    [Phase 7.0] 통합 연락처 생성 및 리드 연결

    여러 리드를 하나의 통합 연락처로 그룹핑합니다.
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    try:
        # 통합 연락처 생성
        tags_json = json.dumps(data.tags or [], ensure_ascii=False)
        cursor.execute("""
            INSERT INTO unified_contacts
            (display_name, primary_platform, email, phone, notes, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (data.display_name, data.primary_platform, data.email, data.phone, data.notes, tags_json))

        contact_id = cursor.lastrowid

        # [성능 최적화] 리드 연결 - 배치 업데이트로 N+1 쿼리 방지
        if data.lead_ids:
            placeholders = ','.join('?' * len(data.lead_ids))
            cursor.execute(f"""
                UPDATE mentions SET unified_contact_id = ? WHERE id IN ({placeholders})
            """, [contact_id] + list(data.lead_ids))

            # 총 상호작용 수 업데이트
            cursor.execute(
                "UPDATE unified_contacts SET total_interactions = ? WHERE id = ?",
                (len(data.lead_ids), contact_id)
            )

        conn.commit()
        conn.close()

        return success_response({
            "success": True,
            "contact_id": contact_id,
            "linked_leads": len(data.lead_ids),
            "message": f"통합 연락처 '{data.display_name}'가 생성되었습니다"
        })

    except Exception as e:
        conn.rollback()
        conn.close()
        raise HTTPException(status_code=500, detail=f"생성 실패: {str(e)}")


@router.get("/unified-contacts/{contact_id}")
@handle_exceptions
async def get_unified_contact_detail(contact_id: int) -> Dict[str, Any]:
    """
    [Phase 7.0] 통합 연락처 상세 조회

    연결된 모든 리드 정보와 상호작용 히스토리를 반환합니다.
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 통합 연락처 조회
    # [Phase 7] SELECT * 제거
    cursor.execute("""
        SELECT id, display_name, primary_platform, primary_identifier, email, phone,
               notes, tags, total_interactions, last_interaction_at, created_at, updated_at
        FROM unified_contacts WHERE id = ?
    """, (contact_id,))
    contact = cursor.fetchone()

    if not contact:
        conn.close()
        raise HTTPException(status_code=404, detail="통합 연락처를 찾을 수 없습니다")

    contact_dict = dict(contact)
    try:
        contact_dict['tags'] = json.loads(contact_dict.get('tags', '[]'))
    except (json.JSONDecodeError, TypeError):
        contact_dict['tags'] = []

    # 연결된 리드 조회
    columns = _get_table_columns(cursor, 'mentions')
    author_col = 'author' if 'author' in columns else 'target_name'

    cursor.execute(f"""
        SELECT id, platform, title, {author_col} as author, lead_score, status, created_at
        FROM mentions
        WHERE unified_contact_id = ?
        ORDER BY created_at DESC
    """, (contact_id,))

    linked_leads = [dict(row) for row in cursor.fetchall()]

    # 컨택 히스토리 조회 (있는 경우)
    contact_history = []
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='contact_history'")
    if cursor.fetchone():
        lead_ids = [lead['id'] for lead in linked_leads]
        if lead_ids:
            placeholders = ','.join('?' * len(lead_ids))
            # [Phase 7] SELECT * 제거
            cursor.execute(f"""
                SELECT id, lead_id, contact_type, content, platform, template_id,
                       status, response, created_at, responded_at, notes
                FROM contact_history
                WHERE lead_id IN ({placeholders})
                ORDER BY created_at DESC LIMIT 20
            """, lead_ids)
            contact_history = [dict(row) for row in cursor.fetchall()]

    conn.close()

    # 플랫폼별 통계
    platform_stats = {}
    for lead in linked_leads:
        platform = lead.get('platform', 'unknown')
        platform_stats[platform] = platform_stats.get(platform, 0) + 1

    return success_response({
        "contact": contact_dict,
        "linked_leads": linked_leads,
        "contact_history": contact_history,
        "platform_stats": platform_stats,
        "total_leads": len(linked_leads)
    })


@router.put("/unified-contacts/{contact_id}")
@handle_exceptions
async def update_unified_contact(contact_id: int, data: UnifiedContactUpdate) -> Dict[str, Any]:
    """
    [Phase 7.0] 통합 연락처 수정
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM unified_contacts WHERE id = ?", (contact_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="통합 연락처를 찾을 수 없습니다")

    updates = []
    params = []

    if data.display_name is not None:
        updates.append("display_name = ?")
        params.append(data.display_name)
    if data.email is not None:
        updates.append("email = ?")
        params.append(data.email)
    if data.phone is not None:
        updates.append("phone = ?")
        params.append(data.phone)
    if data.notes is not None:
        updates.append("notes = ?")
        params.append(data.notes)
    if data.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(data.tags, ensure_ascii=False))

    if updates:
        updates.append("updated_at = CURRENT_TIMESTAMP")
        params.append(contact_id)
        cursor.execute(f"UPDATE unified_contacts SET {', '.join(updates)} WHERE id = ?", params)
        conn.commit()

    conn.close()

    return success_response({
        "success": True,
        "message": "통합 연락처가 수정되었습니다"
    })


@router.post("/unified-contacts/{contact_id}/link")
@handle_exceptions
async def link_lead_to_unified_contact(contact_id: int, lead_id: int) -> Dict[str, Any]:
    """
    [Phase 7.0] 리드를 통합 연락처에 연결
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM unified_contacts WHERE id = ?", (contact_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="통합 연락처를 찾을 수 없습니다")

    cursor.execute("SELECT id FROM mentions WHERE id = ?", (lead_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="리드를 찾을 수 없습니다")

    cursor.execute(
        "UPDATE mentions SET unified_contact_id = ? WHERE id = ?",
        (contact_id, lead_id)
    )

    # 총 상호작용 수 업데이트
    cursor.execute("""
        UPDATE unified_contacts
        SET total_interactions = (SELECT COUNT(*) FROM mentions WHERE unified_contact_id = ?),
            last_interaction_at = CURRENT_TIMESTAMP
        WHERE id = ?
    """, (contact_id, contact_id))

    conn.commit()
    conn.close()

    return success_response({
        "success": True,
        "message": "리드가 통합 연락처에 연결되었습니다"
    })


@router.post("/unified-contacts/{contact_id}/unlink")
@handle_exceptions
async def unlink_lead_from_unified_contact(contact_id: int, lead_id: int) -> Dict[str, Any]:
    """
    [Phase 7.0] 리드를 통합 연락처에서 연결 해제
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE mentions SET unified_contact_id = NULL WHERE id = ? AND unified_contact_id = ?",
        (lead_id, contact_id)
    )

    # 총 상호작용 수 업데이트
    cursor.execute("""
        UPDATE unified_contacts
        SET total_interactions = (SELECT COUNT(*) FROM mentions WHERE unified_contact_id = ?)
        WHERE id = ?
    """, (contact_id, contact_id))

    conn.commit()
    conn.close()

    return success_response({
        "success": True,
        "message": "리드가 통합 연락처에서 연결 해제되었습니다"
    })


@router.delete("/unified-contacts/{contact_id}")
@handle_exceptions
async def delete_unified_contact(contact_id: int) -> Dict[str, Any]:
    """
    [Phase 7.0] 통합 연락처 삭제

    연결된 리드는 삭제되지 않고 연결만 해제됩니다.
    """
    db = DatabaseManager()
    conn = None
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 먼저 연결된 리드들의 unified_contact_id를 NULL로
    cursor.execute(
        "UPDATE mentions SET unified_contact_id = NULL WHERE unified_contact_id = ?",
        (contact_id,)
    )

    cursor.execute("DELETE FROM unified_contacts WHERE id = ?", (contact_id,))
    conn.commit()
    conn.close()

    return success_response({
        "success": True,
        "message": "통합 연락처가 삭제되었습니다"
    })
