"""
Pathfinder V3 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

키워드 발굴 시스템
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from enum import Enum
import sys
import os
from pathlib import Path
import subprocess
import json
import sqlite3
import logging

# 로거 설정
logger = logging.getLogger(__name__)

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from core_services.sql_builder import validate_table_name, get_table_columns, select_column_safely
from backend_utils.error_handlers import handle_exceptions
from backend_utils.cache import cached, invalidate_cache
from schemas.response import success_response, error_response

router = APIRouter()

# 카테고리 통합 매핑 (중복 카테고리 → 표준 카테고리)
CATEGORY_MAPPING = {
    # 안면비대칭 계열
    "안면비대칭_교정": "안면비대칭",
    "안면비대칭교정": "안면비대칭",

    # 피부/여드름 계열
    "여드름_피부": "피부/여드름",
    "여드름/피부": "피부/여드름",
    "피부": "피부/여드름",
    "여드름": "피부/여드름",

    # 교통사고 계열
    "교통사고_입원": "교통사고",
    "교통사고입원": "교통사고",

    # 탈모 계열
    "탈모_모발": "탈모",
    "탈모모발": "탈모",

    # 통증 계열
    "통증_디스크": "통증/디스크",
    "통증": "통증/디스크",
    "디스크": "통증/디스크",

    # 면역/보약 계열
    "면역_보약": "면역/보약",
    "면역보약": "면역/보약",
    "보약": "면역/보약",

    # 갱년기 계열
    "갱년기_호르몬": "갱년기",
    "갱년기호르몬": "갱년기",

    # 소화/위장 계열
    "소화불량_위장": "소화/위장",
    "소화불량": "소화/위장",
    "소화기": "소화/위장",
    "위장": "소화/위장",

    # 알레르기/아토피 계열
    "알레르기_아토피": "알레르기/아토피",
    "아토피": "알레르기/아토피",
    "알레르기": "알레르기/아토피",

    # 수험생/집중력 계열
    "수험생_집중력": "수험생/집중력",
    "집중력": "수험생/집중력",
    "수험생": "수험생/집중력",

    # 두통/어지럼 계열
    "두통_어지럼증": "두통/어지럼",
    "두통어지럼증": "두통/어지럼",
    "두통": "두통/어지럼",
    "어지럼증": "두통/어지럼",

    # 불면증/수면 계열
    "불면증_수면": "불면증/수면",
    "불면증": "불면증/수면",
    "수면": "불면증/수면",

    # 리프팅/탄력 계열
    "리프팅_탄력": "리프팅/탄력",
    "리프팅/성형": "리프팅/탄력",
    "리프팅": "리프팅/탄력",

    # 다한증/냉증 계열
    "다한증_냉증": "다한증/냉증",
    "다한증": "다한증/냉증",
    "냉증": "다한증/냉증",

    # 스트레스/자율신경 계열
    "자율신경_스트레스": "스트레스/자율신경",
    "자율신경": "스트레스/자율신경",
    "스트레스": "스트레스/자율신경",

    # 여성건강/산후조리 계열
    "산후조리_여성": "여성건강/산후조리",
    "산후조리": "여성건강/산후조리",
    "여성건강": "여성건강/산후조리",

    # 야간진료 계열
    "야간진료_접근성": "야간진료",

    # 다이어트 계열
    "다이어트/비만": "다이어트",
    "비만": "다이어트",

    # 추나 → 통증/디스크
    "추나": "통증/디스크",

    # 지역명 → 기타
    "지역명": "기타",
}

# [최적화] 역매핑 사전 - 표준 카테고리 → DB 카테고리 목록 (O(1) 조회)
_REVERSE_CATEGORY_MAPPING: Dict[str, List[str]] = {}

def _build_reverse_category_mapping():
    """역매핑 사전 초기화 (모듈 로드 시 한 번만 실행)"""
    global _REVERSE_CATEGORY_MAPPING
    _REVERSE_CATEGORY_MAPPING.clear()

    for db_cat, std_cat in CATEGORY_MAPPING.items():
        if std_cat not in _REVERSE_CATEGORY_MAPPING:
            _REVERSE_CATEGORY_MAPPING[std_cat] = [std_cat]  # 표준 카테고리 자체 포함
        _REVERSE_CATEGORY_MAPPING[std_cat].append(db_cat)

    # 중복 제거
    for key in _REVERSE_CATEGORY_MAPPING:
        _REVERSE_CATEGORY_MAPPING[key] = list(set(_REVERSE_CATEGORY_MAPPING[key]))

# 모듈 로드 시 역매핑 생성
_build_reverse_category_mapping()


def calculate_kei(keyword_data: dict) -> float:
    """
    KEI (Keyword Effectiveness Index) 계산

    공식: KEI = (search_volume / max(1, difficulty)) * 10

    높을수록 효율적인 키워드 (검색량 대비 경쟁이 낮음)
    - KEI >= 50: 매우 효율적 (S급)
    - KEI >= 30: 효율적 (A급)
    - KEI >= 15: 보통 (B급)
    - KEI < 15: 비효율적 (C급)
    """
    search_volume = keyword_data.get('search_volume') or 0
    difficulty = keyword_data.get('difficulty') or 50

    # 0으로 나누기 방지
    difficulty = max(1, difficulty)

    kei = (search_volume / difficulty) * 10
    return round(kei, 2)


def calculate_likelihood_score(keyword_data: dict) -> int:
    """
    키워드의 실제 순위 달성 가능성을 0-100 점수로 계산

    고려 요소:
    1. 난이도(difficulty): 낮을수록 높은 점수 (30점)
    2. 기회도(opportunity): 높을수록 높은 점수 (25점)
    3. 검색량(search_volume): 적당한 범위가 최적 (20점)
    4. 현재 순위(current_rank): 이미 순위권이면 높은 점수 (15점)
    5. 트렌드(trend_status): 상승 추세면 추가 점수 (10점)
    """
    score = 0

    # 1. 난이도 점수 (0-30점): 낮을수록 좋음
    difficulty = keyword_data.get('difficulty') or 50
    if difficulty <= 20:
        score += 30
    elif difficulty <= 35:
        score += 25
    elif difficulty <= 50:
        score += 20
    elif difficulty <= 70:
        score += 10
    else:
        score += 5

    # 2. 기회도 점수 (0-25점): 높을수록 좋음
    opportunity = keyword_data.get('opportunity') or 50
    if opportunity >= 80:
        score += 25
    elif opportunity >= 65:
        score += 20
    elif opportunity >= 50:
        score += 15
    elif opportunity >= 35:
        score += 10
    else:
        score += 5

    # 3. 검색량 점수 (0-20점): 50-500 범위가 최적
    search_volume = keyword_data.get('search_volume') or 0
    if 50 <= search_volume <= 500:
        score += 20  # 최적 범위
    elif 30 <= search_volume < 50 or 500 < search_volume <= 1000:
        score += 15
    elif 10 <= search_volume < 30 or 1000 < search_volume <= 2000:
        score += 10
    elif search_volume > 2000:
        score += 5  # 너무 높으면 경쟁이 심함
    else:
        score += 3  # 너무 낮음

    # 4. 현재 순위 점수 (0-15점)
    current_rank = keyword_data.get('current_rank')
    if current_rank:
        if current_rank <= 3:
            score += 15  # TOP 3
        elif current_rank <= 10:
            score += 12  # TOP 10
        elif current_rank <= 30:
            score += 8
        elif current_rank <= 50:
            score += 5
        else:
            score += 2
    # 순위 없음: 0점 (아직 시작 안함)

    # 5. 트렌드 점수 (0-10점)
    trend_status = keyword_data.get('trend_status') or 'stable'
    if trend_status == 'rising':
        score += 10
    elif trend_status == 'stable':
        score += 5
    else:  # falling
        score += 0

    return min(score, 100)


def normalize_category(category: str) -> str:
    """카테고리를 표준 형식으로 정규화"""
    if not category:
        return "기타"
    return CATEGORY_MAPPING.get(category, category)

def get_category_variants(standard_category: str) -> List[str]:
    """
    표준 카테고리에 매핑되는 모든 DB 카테고리 반환
    [최적화] O(n) → O(1) - 역매핑 사전 사용
    """
    return _REVERSE_CATEGORY_MAPPING.get(standard_category, [standard_category])


@router.get("/live-status")
async def get_live_status() -> Dict[str, Any]:
    """
    Pathfinder 실시간 상태 조회

    Returns:
        - status: idle, running, completed
        - mode: total_war, legion
        - message: 상태 메시지
        - recent_logs: 최근 로그 라인 (최대 50줄)
    """
    try:
        from services.file_watcher import get_file_watcher

        file_watcher = get_file_watcher()
        if file_watcher:
            status = file_watcher.get_status()
            recent_logs = file_watcher.get_recent_logs(50)
            return {
                **status,
                'recent_logs': recent_logs
            }
        else:
            return {
                'status': 'idle',
                'message': '대기 중',
                'mode': None,
                'recent_logs': []
            }
    except Exception as e:
        return {
            'status': 'error',
            'message': str(e),
            'recent_logs': []
        }


class PathfinderMode(str, Enum):
    TOTAL_WAR = "total_war"
    LEGION = "legion"

class PathfinderRequest(BaseModel):
    mode: PathfinderMode
    target: Optional[int] = 500
    save_db: bool = True

@router.get("/stats")
@cached(ttl=300)
@handle_exceptions
async def get_pathfinder_stats(
    apply_filter: bool = True,
    days: Optional[int] = Query(None, ge=1, le=365, description="조회 기간 (1-365일)")
) -> Dict[str, Any]:
    """
    Pathfinder 통계 조회
    """
    # 기본 반환값 (테이블이 없거나 에러 시 사용)
    default_response = {
        "total": 0,
        "s_grade": 0,
        "a_grade": 0,
        "b_grade": 0,
        "c_grade": 0,
        "categories": {},
        "sources": {},
        "trends": {
            "rising": 0,
            "falling": 0,
            "stable": 0
        }
    }

    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if not cursor.fetchone():
            conn.close()
            return default_response

        # [Phase 8] SQL Injection 방지 - 파라미터 바인딩 사용
        # 쿼리 조건 및 파라미터 구성
        where_conditions = ["1=1"]
        params = []

        # 등급 필터
        if apply_filter:
            where_conditions.append("grade IN ('S', 'A')")

        # 날짜 필터 (파라미터 바인딩)
        if days:
            where_conditions.append("created_at >= datetime('now', ?)")
            params.append(f"-{days} days")

        where_clause = " AND ".join(where_conditions)

        # 통계 조회
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_grade,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_grade,
                SUM(CASE WHEN grade = 'B' THEN 1 ELSE 0 END) as b_grade,
                SUM(CASE WHEN grade = 'C' THEN 1 ELSE 0 END) as c_grade
            FROM keyword_insights
            WHERE {where_clause}
        """, params)
        stats = cursor.fetchone()

        # 카테고리별 통계 (통합 매핑 적용)
        cursor.execute(f"""
            SELECT
                category,
                COUNT(*) as total,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_grade,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_grade
            FROM keyword_insights
            WHERE {where_clause}
            GROUP BY category
        """, params)
        categories = {}
        for row in cursor.fetchall():
            if row[0]:  # None 카테고리 제외
                # 카테고리 정규화 (중복 통합)
                normalized_cat = normalize_category(row[0])
                if normalized_cat in categories:
                    # 기존 카테고리에 합산
                    categories[normalized_cat]["total"] += row[1]
                    categories[normalized_cat]["s_grade"] += row[2] or 0
                    categories[normalized_cat]["a_grade"] += row[3] or 0
                else:
                    categories[normalized_cat] = {
                        "total": row[1],
                        "s_grade": row[2] or 0,
                        "a_grade": row[3] or 0
                    }

        # 소스별 통계
        cursor.execute(f"""
            SELECT source, COUNT(*) as count
            FROM keyword_insights
            WHERE {where_clause}
            GROUP BY source
        """, params)
        sources = {row[0]: row[1] for row in cursor.fetchall() if row[0]}

        # 트렌드 통계
        cursor.execute(f"""
            SELECT
                SUM(CASE WHEN trend_status = 'rising' THEN 1 ELSE 0 END) as rising,
                SUM(CASE WHEN trend_status = 'falling' THEN 1 ELSE 0 END) as falling,
                SUM(CASE WHEN trend_status = 'stable' THEN 1 ELSE 0 END) as stable
            FROM keyword_insights
            WHERE {where_clause}
        """, params)
        trend_stats = cursor.fetchone()

        conn.close()

        return {
            "total": stats[0] if stats and stats[0] else 0,
            "s_grade": stats[1] if stats and stats[1] else 0,
            "a_grade": stats[2] if stats and stats[2] else 0,
            "b_grade": stats[3] if stats and stats[3] else 0,
            "c_grade": stats[4] if stats and stats[4] else 0,
            "categories": categories,
            "sources": sources,
            "trends": {
                "rising": trend_stats[0] if trend_stats and trend_stats[0] else 0,
                "falling": trend_stats[1] if trend_stats and trend_stats[1] else 0,
                "stable": trend_stats[2] if trend_stats and trend_stats[2] else 0
            }
        }

    except Exception as e:
        logger.error(f"[Pathfinder Stats] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"통계 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

@router.get("/keywords")
@handle_exceptions
async def get_keywords(
    grade: Optional[str] = None,
    category: Optional[str] = None,
    source: Optional[str] = None,
    trend_status: Optional[str] = None,
    max_age_days: Optional[int] = Query(
        default=60, ge=0, le=3650,
        description="이 일수 이상 갱신 안 된 키워드 숨김 (0=무제한, 기본 60일)",
    ),
    include_low_volume: bool = Query(
        default=False,
        description="search_volume<50인 저신뢰 키워드 포함 (기본 False)",
    ),
    limit: int = Query(default=200, ge=1, le=1000, description="최대 조회 수"),
    offset: int = Query(default=0, ge=0, description="건너뛸 항목 수")
) -> List[Dict[str, Any]]:
    """키워드 목록 조회.

    [Q12] 운영자가 max_age_days/include_low_volume 토글로 stale·저품질 노이즈 제거 가능.
    cron 자동 archive 안 쓰고, UI 필터로만 노출 제어.
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if not cursor.fetchone():
            conn.close()
            return []

        # SQL 인젝션 방지를 위한 파라미터 바인딩
        filters = []
        params = []
        if grade:
            filters.append("grade = ?")
            params.append(grade)
        if category:
            variants = get_category_variants(category)
            placeholders = ",".join(["?" for _ in variants])
            filters.append(f"category IN ({placeholders})")
            params.extend(variants)
        if source:
            filters.append("source = ?")
            params.append(source)
        if trend_status:
            filters.append("trend_status = ?")
            params.append(trend_status)

        # [Q12] stale 필터 — 마지막 created_at(=발굴/갱신 시각)이 N일 이내만
        if max_age_days and max_age_days > 0:
            filters.append(
                "ki.created_at >= datetime('now', ?)"
            )
            params.append(f"-{max_age_days} days")

        # [Q12] 저신뢰 키워드 필터 — search_volume<50은 신뢰도 부족
        if not include_low_volume:
            filters.append("(ki.search_volume IS NOT NULL AND ki.search_volume >= 50)")

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""
        params.extend([limit, offset])

        # rank_history에서 최신 순위 정보 서브쿼리
        cursor.execute(f"""
            SELECT
                ki.keyword, ki.search_volume, ki.competition,
                ki.difficulty, ki.opportunity, ki.grade, ki.category,
                ki.source, ki.trend_status, ki.created_at, ki.kei,
                ki.memo, ki.user_tags,
                rh.rank as current_rank,
                rh.status as rank_status
            FROM keyword_insights ki
            LEFT JOIN (
                SELECT keyword, rank, status,
                    ROW_NUMBER() OVER (
                        PARTITION BY keyword
                        ORDER BY COALESCE(date, checked_at) DESC
                    ) as rn
                FROM rank_history
                WHERE status = 'found' AND rank > 0
            ) rh ON ki.keyword = rh.keyword AND rh.rn = 1
            {where_clause}
            ORDER BY
                CASE ki.grade
                    WHEN 'S' THEN 1
                    WHEN 'A' THEN 2
                    WHEN 'B' THEN 3
                    ELSE 4
                END,
                ki.search_volume DESC
            LIMIT ? OFFSET ?
        """, params)

        keywords = []
        for row in cursor.fetchall():
            kw = dict(row)
            # 카테고리 정규화
            kw['category'] = normalize_category(kw.get('category', '기타'))
            # user_tags JSON 파싱
            try:
                kw['user_tags'] = json.loads(kw.get('user_tags') or '[]')
            except (json.JSONDecodeError, TypeError):
                kw['user_tags'] = []
            # memo 기본값
            kw['memo'] = kw.get('memo') or ''
            # [Phase 1.2] Likelihood Score 계산
            kw['likelihood_score'] = calculate_likelihood_score(kw)
            # [Phase 6.2] KEI 동적 계산 (DB에 없거나 0인 경우)
            if not kw.get('kei') or kw['kei'] == 0:
                kw['kei'] = calculate_kei(kw)
            keywords.append(kw)

        conn.close()

        return keywords

    except Exception as e:
        logger.error(f"[Pathfinder Keywords] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"키워드 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/keywords/export-all")
async def export_all_keywords(
    grade: Optional[str] = None,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    전체 키워드 일괄 내보내기 (limit 없음)
    - 필터 적용 가능 (등급, 카테고리)
    - 순위 정보 포함
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 필터 조건 구성
        filters = []
        params = []
        if grade:
            filters.append("ki.grade = ?")
            params.append(grade)
        if category:
            variants = get_category_variants(category)
            placeholders = ",".join(["?" for _ in variants])
            filters.append(f"ki.category IN ({placeholders})")
            params.extend(variants)

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""

        cursor.execute(f"""
            SELECT
                ki.keyword, ki.search_volume, ki.competition,
                ki.difficulty, ki.opportunity, ki.grade, ki.category,
                ki.source, ki.trend_status, ki.created_at, ki.kei,
                rh.rank as current_rank
            FROM keyword_insights ki
            LEFT JOIN (
                SELECT keyword, rank,
                    ROW_NUMBER() OVER (
                        PARTITION BY keyword
                        ORDER BY COALESCE(date, checked_at) DESC
                    ) as rn
                FROM rank_history
                WHERE status = 'found' AND rank > 0
            ) rh ON ki.keyword = rh.keyword AND rh.rn = 1
            {where_clause}
            ORDER BY
                CASE ki.grade
                    WHEN 'S' THEN 1
                    WHEN 'A' THEN 2
                    WHEN 'B' THEN 3
                    ELSE 4
                END,
                ki.search_volume DESC
        """, params)

        keywords = []
        for row in cursor.fetchall():
            kw = dict(row)
            kw['category'] = normalize_category(kw.get('category', '기타'))
            # [Phase 6.2] KEI 동적 계산
            if not kw.get('kei') or kw['kei'] == 0:
                kw['kei'] = calculate_kei(kw)
            # Likelihood Score 계산
            kw['likelihood_score'] = calculate_likelihood_score(kw)
            keywords.append(kw)

        conn.close()

        return keywords

    except Exception as e:
        logger.error(f"[Pathfinder Export All] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"키워드 내보내기 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/run")
async def run_pathfinder(
    request: PathfinderRequest,
    background_tasks: BackgroundTasks
) -> Dict[str, str]:
    """
    Pathfinder 실행 (백그라운드)

    [안정성 개선] asyncio.create_subprocess_exec() 사용으로 비블로킹 실행

    ⚠️ 주의: 이 엔드포인트는 실험적입니다.
    안정적인 실행을 위해서는 터미널에서 직접 실행하는 것을 권장합니다.
    """
    import asyncio

    try:
        script_name = "pathfinder_v3_complete.py" if request.mode == PathfinderMode.TOTAL_WAR else "pathfinder_v3_legion.py"
        script_path = os.path.join(parent_dir, script_name)

        # 스크립트 파일 존재 확인
        if not os.path.exists(script_path):
            raise HTTPException(
                status_code=404,
                detail=f"스크립트를 찾을 수 없습니다: {script_path}\n\n터미널에서 직접 실행하세요:\npython {script_name} --save-db"
            )

        cmd = ["python", script_path]
        if request.mode == PathfinderMode.LEGION:
            cmd.extend(["--target", str(request.target)])
        if request.save_db:
            cmd.append("--save-db")

        # 로그 파일 경로
        log_path = os.path.join(parent_dir, "pathfinder_run.log")

        # [안정성 개선] 비동기 백그라운드 실행
        async def run_pathfinder_async():
            from datetime import datetime
            try:
                with open(log_path, 'w', encoding='utf-8') as log_file:
                    log_file.write(f"=== Pathfinder 실행 시작 ===\n")
                    log_file.write(f"명령어: {' '.join(cmd)}\n")
                    log_file.write(f"시작 시간: {datetime.now().isoformat()}\n\n")

                # 비동기 subprocess 생성
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    cwd=parent_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                )

                # 출력을 실시간으로 로그 파일에 기록
                with open(log_path, 'a', encoding='utf-8') as log_file:
                    while True:
                        line = await process.stdout.readline()
                        if not line:
                            break
                        log_file.write(line.decode('utf-8', errors='replace'))
                        log_file.flush()

                    # 프로세스 완료 대기
                    return_code = await process.wait()
                    log_file.write(f"\n\n=== 실행 완료 (exit code: {return_code}) ===\n")
                    log_file.write(f"종료 시간: {datetime.now().isoformat()}\n")

            except Exception as e:
                with open(log_path, 'a', encoding='utf-8') as log_file:
                    log_file.write(f"\n\n=== 에러 발생 ===\n{str(e)}\n")

        # 백그라운드 태스크로 비동기 함수 실행
        asyncio.create_task(run_pathfinder_async())

        return {
            "status": "started",
            "message": f"⚠️ 백그라운드 실행 시작됨\n\n안정적인 실행을 위해 터미널 사용을 권장합니다:\npython {script_name} --save-db\n\n로그: {log_path}",
            "mode": request.mode.value,
            "log_file": log_path,
            "recommended_command": f"python {script_name} --save-db"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/clusters")
async def get_keyword_clusters(min_cluster_size: int = 3) -> List[Dict[str, Any]]:
    """
    키워드 클러스터 조회
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if not cursor.fetchone():
            conn.close()
            return []

        # 간단한 클러스터링: 카테고리별 그룹화
        cursor.execute("""
            SELECT
                category,
                COUNT(*) as count,
                GROUP_CONCAT(keyword, ', ') as keywords,
                SUM(search_volume) as total_volume,
                AVG(CASE grade
                    WHEN 'S' THEN 4
                    WHEN 'A' THEN 3
                    WHEN 'B' THEN 2
                    ELSE 1
                END) as avg_grade
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
            GROUP BY category
            HAVING count >= ?
            ORDER BY count DESC
        """, (min_cluster_size,))

        # 카테고리 통합을 위해 딕셔너리로 먼저 수집
        cluster_map = {}
        for row in cursor.fetchall():
            if row[0]:  # None 카테고리 제외
                normalized_cat = normalize_category(row[0])
                keywords_list = row[2].split(', ') if row[2] else []

                if normalized_cat in cluster_map:
                    # 기존 클러스터에 합산
                    cluster_map[normalized_cat]["keyword_count"] += row[1]
                    cluster_map[normalized_cat]["keywords"].extend(keywords_list)
                    cluster_map[normalized_cat]["total_search_volume"] += row[3] if row[3] else 0
                    cluster_map[normalized_cat]["_grade_sum"] += (row[4] if row[4] else 0) * row[1]
                    cluster_map[normalized_cat]["_count_for_avg"] += row[1]
                else:
                    cluster_map[normalized_cat] = {
                        "cluster_name": normalized_cat,
                        "keyword_count": row[1],
                        "keywords": keywords_list,
                        "total_search_volume": row[3] if row[3] else 0,
                        "_grade_sum": (row[4] if row[4] else 0) * row[1],
                        "_count_for_avg": row[1]
                    }

        # 클러스터 리스트 생성 및 평균 품질 계산
        clusters = []
        for cat, data in cluster_map.items():
            avg_quality = data["_grade_sum"] / data["_count_for_avg"] if data["_count_for_avg"] > 0 else 0
            clusters.append({
                "cluster_name": data["cluster_name"],
                "keyword_count": data["keyword_count"],
                "keywords": data["keywords"][:10],  # 상위 10개만
                "total_search_volume": data["total_search_volume"],
                "avg_quality": round(avg_quality, 2)
            })

        # 키워드 수 기준 정렬
        clusters.sort(key=lambda x: x["keyword_count"], reverse=True)

        conn.close()
        return clusters

    except Exception as e:
        logger.error(f"[Pathfinder Clusters] Error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"클러스터 조회 실패: {str(e)}")
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


class KeywordUpdate(BaseModel):
    grade: Optional[str] = None
    category: Optional[str] = None
    memo: Optional[str] = None
    user_tags: Optional[List[str]] = None


@router.patch("/keywords/{keyword}")
async def update_keyword(keyword: str, update: KeywordUpdate) -> Dict[str, str]:
    """
    키워드 정보 업데이트
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 키워드 존재 여부 확인
        cursor.execute("SELECT keyword FROM keyword_insights WHERE keyword = ?", (keyword,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail=f"키워드 '{keyword}'을(를) 찾을 수 없습니다")

        # 업데이트할 필드 구성
        updates = []
        params: List[Any] = []
        if update.grade:
            updates.append("grade = ?")
            params.append(update.grade)
        if update.category:
            updates.append("category = ?")
            params.append(update.category)
        if update.memo is not None:
            updates.append("memo = ?")
            params.append(update.memo)
        if update.user_tags is not None:
            updates.append("user_tags = ?")
            params.append(json.dumps(update.user_tags, ensure_ascii=False))

        if not updates:
            conn.close()
            return {"status": "success", "message": "업데이트할 항목이 없습니다"}

        params.append(keyword)
        cursor.execute(f"""
            UPDATE keyword_insights
            SET {', '.join(updates)}
            WHERE keyword = ?
        """, params)

        conn.commit()
        conn.close()

        # [Phase A-2] S/A급으로 변경 시 이벤트 발행 → 순위 추적 자동 등록
        if update.grade and update.grade in ['S', 'A']:
            try:
                from services.event_bus import emit_keyword_discovered
                import asyncio
                asyncio.create_task(emit_keyword_discovered(keyword, update.grade, "pathfinder"))
            except Exception as event_error:
                logger.warning(f"이벤트 발행 실패: {event_error}")

        return {
            "status": "success",
            "message": f"'{keyword}' 키워드가 업데이트되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.delete("/keywords/{keyword}")
async def delete_keyword(keyword: str) -> Dict[str, str]:
    """
    키워드 삭제
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 키워드 존재 여부 확인
        cursor.execute("SELECT keyword FROM keyword_insights WHERE keyword = ?", (keyword,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail=f"키워드 '{keyword}'을(를) 찾을 수 없습니다")

        cursor.execute("DELETE FROM keyword_insights WHERE keyword = ?", (keyword,))
        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": f"'{keyword}' 키워드가 삭제되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/export")
async def export_keywords(
    grade: Optional[str] = None,
    format: str = "json"
) -> Dict[str, Any]:
    """
    키워드 내보내기 (JSON/CSV)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 필터 조건
        filters = []
        params: List[str] = []
        if grade:
            filters.append("grade = ?")
            params.append(grade)

        where_clause = "WHERE " + " AND ".join(filters) if filters else ""

        cursor.execute(f"""
            SELECT
                keyword, search_volume, competition,
                difficulty, opportunity, grade, category,
                source, trend_status, created_at, kei
            FROM keyword_insights
            {where_clause}
            ORDER BY grade, search_volume DESC
        """, params)

        keywords = [dict(row) for row in cursor.fetchall()]
        conn.close()

        if format == "csv":
            import csv
            from io import StringIO
            output = StringIO()
            if keywords:
                writer = csv.DictWriter(output, fieldnames=keywords[0].keys())
                writer.writeheader()
                writer.writerows(keywords)
            return {
                "status": "success",
                "format": "csv",
                "count": len(keywords),
                "data": output.getvalue()
            }
        else:
            return {
                "status": "success",
                "format": "json",
                "count": len(keywords),
                "data": keywords
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 4.0] 콘텐츠 캘린더 자동 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/content-calendar")
async def generate_content_calendar(weeks: int = 12) -> Dict[str, Any]:
    """
    [Phase 4.0] 키워드 클러스터 기반 콘텐츠 캘린더 생성

    S/A 등급 키워드를 클러스터링하여 12주간의 콘텐츠 발행 계획을 생성합니다.

    Args:
        weeks: 캘린더 기간 (기본 12주)

    Returns:
        - weekly_plan: 주차별 콘텐츠 계획
        - summary: 전체 요약 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # S/A 등급 키워드 조회
        cursor.execute("""
            SELECT keyword, category, search_volume, grade
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
            AND status != 'archived'
            ORDER BY search_volume DESC
        """)
        keywords = cursor.fetchall()
        conn.close()

        if not keywords:
            return {
                "weekly_plan": [],
                "summary": {"total_keywords": 0, "total_traffic": 0},
                "message": "S/A 등급 키워드가 없습니다. Pathfinder를 실행해주세요."
            }

        # 카테고리별 그룹화
        category_keywords = {}
        for kw, cat, volume, grade in keywords:
            category = cat or '기타'
            if category not in category_keywords:
                category_keywords[category] = []
            category_keywords[category].append({
                "keyword": kw,
                "volume": volume or 0,
                "grade": grade
            })

        # 주차별 계획 생성
        weekly_plan = []
        categories = list(category_keywords.keys())
        total_traffic = 0

        from datetime import datetime, timedelta
        start_date = datetime.now()

        for week in range(1, weeks + 1):
            week_start = start_date + timedelta(weeks=week - 1)
            week_end = week_start + timedelta(days=6)

            # 이번 주에 다룰 카테고리 선택 (순환)
            category_idx = (week - 1) % len(categories)
            main_category = categories[category_idx]
            category_kws = category_keywords[main_category]

            # 이번 주 키워드 선택 (상위 3개)
            week_keywords = category_kws[:3] if len(category_kws) >= 3 else category_kws
            week_traffic = sum(kw['volume'] for kw in week_keywords)
            total_traffic += week_traffic

            # 콘텐츠 유형 제안
            content_types = []
            if week_traffic > 5000:
                content_types = ["블로그 심층 분석", "유튜브 영상"]
            elif week_traffic > 1000:
                content_types = ["블로그 포스팅", "인스타그램 카드뉴스"]
            else:
                content_types = ["블로그 포스팅", "네이버 카페 글"]

            weekly_plan.append({
                "week": week,
                "week_start": week_start.strftime("%Y-%m-%d"),
                "week_end": week_end.strftime("%Y-%m-%d"),
                "category": main_category,
                "keywords": week_keywords,
                "estimated_traffic": week_traffic,
                "content_types": content_types,
                "priority": "high" if week_traffic > 3000 else "medium" if week_traffic > 1000 else "low"
            })

            # 사용한 키워드 제거 (다음 순환에서 다른 키워드 사용)
            category_keywords[main_category] = category_kws[3:]
            if not category_keywords[main_category]:
                # 키워드 소진되면 원래 목록 복원
                category_keywords[main_category] = [
                    {"keyword": kw, "volume": vol or 0, "grade": g}
                    for kw, cat, vol, g in keywords if (cat or '기타') == main_category
                ]

        return {
            "weekly_plan": weekly_plan,
            "summary": {
                "total_weeks": weeks,
                "total_keywords": len(keywords),
                "total_categories": len(categories),
                "estimated_total_traffic": total_traffic,
                "categories": list(categories)
            }
        }

    except Exception as e:
        logger.error(f"[content-calendar] {str(e)}")
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
# 키워드 기반 콘텐츠 아웃라인 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class OutlineRequest(BaseModel):
    keywords: List[str]
    cluster_name: Optional[str] = None
    category: Optional[str] = None


@router.post("/generate-outline")
async def generate_keyword_outline(request: OutlineRequest) -> Dict[str, Any]:
    """
    [Phase 4.0] 키워드 기반 콘텐츠 아웃라인 생성

    캘린더의 주별 키워드를 기반으로 블로그/SNS 콘텐츠 아웃라인을 생성합니다.

    Args:
        keywords: 타겟 키워드 리스트
        cluster_name: 클러스터명 (선택)
        category: 카테고리 (선택)

    Returns:
        생성된 콘텐츠 아웃라인
    """
    try:
        keywords = request.keywords
        cluster_name = request.cluster_name or "콘텐츠"
        category = request.category or "일반"

        if not keywords:
            raise HTTPException(status_code=400, detail="키워드가 필요합니다")

        # AI로 아웃라인 생성 시도
        try:
            from services.ai_client import ai_generate_json

            prompt = f"""당신은 한의원 마케팅 전문가입니다.
다음 키워드들을 모두 자연스럽게 포함하는 블로그 콘텐츠 아웃라인을 작성해주세요.

타겟 키워드: {', '.join(keywords[:5])}
클러스터명: {cluster_name}
카테고리: {category}

다음 JSON 형식으로 답변해주세요:
{{
    "title": "SEO 최적화된 블로그 제목 (60자 이내)",
    "hook": "도입부 훅 (독자의 관심을 끄는 질문이나 문장)",
    "sections": [
        {{"heading": "섹션 제목", "key_points": ["핵심 포인트1", "핵심 포인트2"]}},
        {{"heading": "섹션 제목", "key_points": ["핵심 포인트1", "핵심 포인트2"]}},
        {{"heading": "섹션 제목", "key_points": ["핵심 포인트1", "핵심 포인트2"]}}
    ],
    "cta": "행동 유도 문구",
    "meta_description": "검색 결과에 표시될 메타 설명 (160자 이내)"
}}

중요: JSON만 출력하세요. 다른 텍스트는 포함하지 마세요."""

            outline = ai_generate_json(prompt, temperature=0.7, max_tokens=1000)

            if outline:
                outline["keywords"] = keywords[:5]
                outline["cluster_name"] = cluster_name
                outline["source"] = "ai"

                return {"outline": outline, "success": True}

        except Exception as e:
            logger.warning(f"[generate-outline] AI 실패, 템플릿 사용: {e}")

        # Gemini 실패 시 기본 템플릿 사용
        main_keyword = keywords[0] if keywords else "한의원"
        outline = {
            "title": f"{main_keyword} 완벽 가이드: 전문가가 알려드리는 핵심 정보",
            "hook": f"{main_keyword}에 대해 궁금하셨나요? 전문가의 상세한 설명을 확인해보세요.",
            "sections": [
                {
                    "heading": f"{main_keyword}이란?",
                    "key_points": ["기본 개념 설명", "일반적인 오해 바로잡기"]
                },
                {
                    "heading": f"{main_keyword}의 장점",
                    "key_points": ["첫 번째 장점", "두 번째 장점", "세 번째 장점"]
                },
                {
                    "heading": "규림한의원에서의 치료 과정",
                    "key_points": ["초진 상담", "맞춤 치료 계획", "사후 관리"]
                }
            ],
            "cta": "지금 바로 무료 상담을 예약하세요!",
            "meta_description": f"{main_keyword} 관련 정보를 청주 규림한의원에서 상세히 안내해드립니다. 전문가 상담 예약 가능.",
            "keywords": keywords[:5],
            "cluster_name": cluster_name,
            "source": "template"
        }

        return {"outline": outline, "success": True}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[generate-outline] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 5.0] 스캔 히스토리 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/scan-history")
async def get_scan_history(
    limit: int = 50,
    offset: int = 0,
    scan_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    스캔 실행 히스토리 조회

    Args:
        limit: 조회 개수
        offset: 시작 위치
        scan_type: 스캔 타입 필터 (legion, total_war, etc.)

    Returns:
        스캔 실행 기록 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='scan_runs'")
        if not cursor.fetchone():
            conn.close()
            return {"runs": [], "total": 0, "message": "스캔 기록이 없습니다."}

        # 필터 구성
        where_clause = ""
        params = []
        if scan_type:
            where_clause = "WHERE scan_type = ?"
            params.append(scan_type)

        # 전체 개수
        cursor.execute(f"SELECT COUNT(*) FROM scan_runs {where_clause}", params)
        total = cursor.fetchone()[0]

        # 스캔 기록 조회
        params.extend([limit, offset])
        cursor.execute(f"""
            SELECT
                id, scan_type, mode, target_count,
                started_at, completed_at, status,
                total_keywords, new_keywords, updated_keywords,
                s_grade_count, a_grade_count, b_grade_count, c_grade_count,
                sources_json, categories_json, top_keywords_json,
                error_message, execution_time_seconds, notes
            FROM scan_runs
            {where_clause}
            ORDER BY started_at DESC
            LIMIT ? OFFSET ?
        """, params)

        runs = []
        for row in cursor.fetchall():
            run = dict(row)
            # JSON 파싱
            try:
                run['sources'] = json.loads(run.get('sources_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                run['sources'] = {}
            try:
                run['categories'] = json.loads(run.get('categories_json') or '{}')
            except (json.JSONDecodeError, TypeError):
                run['categories'] = {}
            try:
                run['top_keywords'] = json.loads(run.get('top_keywords_json') or '[]')
            except (json.JSONDecodeError, TypeError):
                run['top_keywords'] = []

            # JSON 필드 제거 (중복 방지)
            run.pop('sources_json', None)
            run.pop('categories_json', None)
            run.pop('top_keywords_json', None)

            runs.append(run)

        conn.close()

        return {
            "runs": runs,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        logger.error(f"[scan-history] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/scan-history/{run_id}")
async def get_scan_run_detail(run_id: int) -> Dict[str, Any]:
    """
    특정 스캔 실행의 상세 정보 및 해당 스캔에서 수집된 키워드 조회

    Args:
        run_id: 스캔 실행 ID

    Returns:
        스캔 상세 정보 + 수집된 키워드 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거 - 스캔 기록 조회
        columns = """id, scan_type, mode, target_count, started_at, completed_at, status,
                     total_keywords, new_keywords, s_grade_count, a_grade_count, b_grade_count, c_grade_count,
                     sources_json, categories_json, top_keywords_json, error_message, execution_time_seconds, notes"""
        cursor.execute(f"""
            SELECT {columns} FROM scan_runs WHERE id = ?
        """, (run_id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            raise HTTPException(status_code=404, detail="스캔 기록을 찾을 수 없습니다")

        run = dict(row)
        # JSON 파싱
        try:
            run['sources'] = json.loads(run.get('sources_json') or '{}')
        except (json.JSONDecodeError, TypeError):
            run['sources'] = {}
        try:
            run['categories'] = json.loads(run.get('categories_json') or '{}')
        except (json.JSONDecodeError, TypeError):
            run['categories'] = {}
        try:
            run['top_keywords'] = json.loads(run.get('top_keywords_json') or '[]')
        except (json.JSONDecodeError, TypeError):
            run['top_keywords'] = []

        run.pop('sources_json', None)
        run.pop('categories_json', None)
        run.pop('top_keywords_json', None)

        # 해당 스캔에서 수집/업데이트된 키워드 조회
        cursor.execute("""
            SELECT keyword, grade, search_volume, category, kei, created_at
            FROM keyword_insights
            WHERE scan_run_id = ? OR last_scan_run_id = ?
            ORDER BY
                CASE grade WHEN 'S' THEN 1 WHEN 'A' THEN 2 WHEN 'B' THEN 3 ELSE 4 END,
                search_volume DESC
            LIMIT 200
        """, (run_id, run_id))

        keywords = [dict(row) for row in cursor.fetchall()]
        conn.close()

        return {
            "run": run,
            "keywords": keywords,
            "keyword_count": len(keywords)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[scan-history/{run_id} Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/scan-history")
async def create_scan_run(
    scan_type: str,
    mode: str = "unknown",
    target_count: int = 0,
    notes: Optional[str] = None
) -> Dict[str, Any]:
    """
    새 스캔 실행 기록 생성 (스캔 시작 시 호출)

    Args:
        scan_type: 스캔 타입 (legion, total_war, pathfinder, etc.)
        mode: 실행 모드
        target_count: 목표 개수
        notes: 메모

    Returns:
        생성된 스캔 ID
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO scan_runs (scan_type, mode, target_count, notes, status)
            VALUES (?, ?, ?, ?, 'running')
        """, (scan_type, mode, target_count, notes))

        run_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return {"run_id": run_id, "status": "running", "message": "스캔 기록 생성됨"}

    except Exception as e:
        logger.error(f"[create-scan-run] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.put("/scan-history/{run_id}")
async def update_scan_run(
    run_id: int,
    status: Optional[str] = None,
    total_keywords: Optional[int] = None,
    new_keywords: Optional[int] = None,
    updated_keywords: Optional[int] = None,
    s_grade_count: Optional[int] = None,
    a_grade_count: Optional[int] = None,
    b_grade_count: Optional[int] = None,
    c_grade_count: Optional[int] = None,
    sources_json: Optional[str] = None,
    categories_json: Optional[str] = None,
    top_keywords_json: Optional[str] = None,
    error_message: Optional[str] = None,
    execution_time_seconds: Optional[int] = None
) -> Dict[str, Any]:
    """
    스캔 실행 기록 업데이트 (스캔 완료 시 호출)
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        updates = []
        params = []

        if status:
            updates.append("status = ?")
            params.append(status)
            if status == 'completed':
                updates.append("completed_at = CURRENT_TIMESTAMP")
        if total_keywords is not None:
            updates.append("total_keywords = ?")
            params.append(total_keywords)
        if new_keywords is not None:
            updates.append("new_keywords = ?")
            params.append(new_keywords)
        if updated_keywords is not None:
            updates.append("updated_keywords = ?")
            params.append(updated_keywords)
        if s_grade_count is not None:
            updates.append("s_grade_count = ?")
            params.append(s_grade_count)
        if a_grade_count is not None:
            updates.append("a_grade_count = ?")
            params.append(a_grade_count)
        if b_grade_count is not None:
            updates.append("b_grade_count = ?")
            params.append(b_grade_count)
        if c_grade_count is not None:
            updates.append("c_grade_count = ?")
            params.append(c_grade_count)
        if sources_json:
            updates.append("sources_json = ?")
            params.append(sources_json)
        if categories_json:
            updates.append("categories_json = ?")
            params.append(categories_json)
        if top_keywords_json:
            updates.append("top_keywords_json = ?")
            params.append(top_keywords_json)
        if error_message:
            updates.append("error_message = ?")
            params.append(error_message)
        if execution_time_seconds is not None:
            updates.append("execution_time_seconds = ?")
            params.append(execution_time_seconds)

        if updates:
            params.append(run_id)
            cursor.execute(f"""
                UPDATE scan_runs SET {', '.join(updates)} WHERE id = ?
            """, params)
            conn.commit()

        conn.close()

        return {"run_id": run_id, "updated": True}

    except Exception as e:
        logger.error(f"[update-scan-run] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 5.1] 증분 스캔 시스템
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class IncrementalScanRequest(BaseModel):
    """증분 스캔 요청"""
    categories: Optional[List[str]] = None    # 특정 카테고리만 스캔 (선택)
    max_per_category: int = 50                # 카테고리당 최대 수집량
    skip_recent_hours: int = 24               # N시간 이내 스캔된 카테고리 스킵


@router.post("/incremental-scan")
async def start_incremental_scan(
    background_tasks: BackgroundTasks,
    request: IncrementalScanRequest
) -> Dict[str, Any]:
    """
    [Phase 5.1] 증분 스캔 실행

    마지막 스캔 이후 새로운 키워드만 빠르게 수집합니다.
    - 카테고리별 마지막 스캔 시간 추적
    - 새 키워드만 저장 (기존 키워드 업데이트)
    - 5분 이내 완료 목표

    Args:
        request: 증분 스캔 설정

    Returns:
        스캔 시작 정보
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 카테고리별 마지막 스캔 시간 조회
        cursor.execute("""
            SELECT category, MAX(created_at) as last_scan
            FROM keyword_insights
            GROUP BY category
        """)
        category_last_scans = {
            row['category']: row['last_scan']
            for row in cursor.fetchall()
        }

        # 스캔할 카테고리 결정
        from datetime import datetime, timedelta
        now = datetime.now()
        cutoff = now - timedelta(hours=request.skip_recent_hours)

        categories_to_scan = []

        if request.categories:
            # 지정된 카테고리만
            categories_to_scan = request.categories
        else:
            # 모든 카테고리 중 최근 스캔되지 않은 것
            all_categories = list(CATEGORY_MAPPING.values())
            all_categories = list(set(all_categories))  # 중복 제거

            for cat in all_categories:
                last_scan = category_last_scans.get(cat)
                if not last_scan:
                    categories_to_scan.append(cat)
                else:
                    try:
                        last_scan_dt = datetime.strptime(last_scan[:19], '%Y-%m-%d %H:%M:%S')
                        if last_scan_dt < cutoff:
                            categories_to_scan.append(cat)
                    except (ValueError, TypeError):
                        categories_to_scan.append(cat)

        conn.close()

        if not categories_to_scan:
            return {
                'status': 'skipped',
                'message': '모든 카테고리가 최근에 스캔되었습니다.',
                'skip_recent_hours': request.skip_recent_hours
            }

        # 백그라운드에서 스캔 실행
        script_path = os.path.join(parent_dir, "pathfinder_v3_complete.py")

        if not os.path.exists(script_path):
            raise HTTPException(status_code=500, detail="Pathfinder 스크립트를 찾을 수 없습니다")

        # 증분 스캔 명령어 구성
        cmd = [
            "python", script_path,
            "--save-db",
            "--max-per-category", str(request.max_per_category),
            "--incremental"  # 증분 모드 플래그
        ]

        if request.categories:
            cmd.extend(["--categories", ",".join(request.categories)])

        background_tasks.add_task(subprocess.run, cmd, cwd=parent_dir)

        return {
            'status': 'started',
            'message': f'증분 스캔 시작 ({len(categories_to_scan)}개 카테고리)',
            'categories_to_scan': categories_to_scan[:10],  # 상위 10개만 표시
            'total_categories': len(categories_to_scan),
            'max_per_category': request.max_per_category
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[incremental-scan] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.get("/scan-status")
async def get_scan_status() -> Dict[str, Any]:
    """
    [Phase 5.1] 스캔 상태 조회

    현재 진행 중인 스캔과 카테고리별 마지막 스캔 정보를 반환합니다.

    Returns:
        스캔 상태 정보
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 진행 중인 스캔 확인
        cursor.execute("""
            SELECT id, scan_type, mode, started_at, status
            FROM scan_runs
            WHERE status = 'running'
            ORDER BY started_at DESC
            LIMIT 1
        """)
        running_scan = cursor.fetchone()

        # 카테고리별 마지막 스캔 통계
        cursor.execute("""
            SELECT
                category,
                COUNT(*) as keyword_count,
                MAX(created_at) as last_scan,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_count,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_count
            FROM keyword_insights
            GROUP BY category
            ORDER BY last_scan DESC
        """)

        categories = []
        from datetime import datetime, timedelta
        now = datetime.now()

        for row in cursor.fetchall():
            cat = dict(row)
            last_scan = cat.get('last_scan')

            # 스캔 필요 여부 판단
            needs_scan = False
            if not last_scan:
                needs_scan = True
            else:
                try:
                    last_scan_dt = datetime.strptime(last_scan[:19], '%Y-%m-%d %H:%M:%S')
                    if (now - last_scan_dt) > timedelta(hours=24):
                        needs_scan = True
                except (ValueError, TypeError):
                    needs_scan = True

            cat['needs_scan'] = needs_scan
            categories.append(cat)

        # 전체 통계
        cursor.execute("""
            SELECT
                COUNT(*) as total_keywords,
                SUM(CASE WHEN grade = 'S' THEN 1 ELSE 0 END) as s_count,
                SUM(CASE WHEN grade = 'A' THEN 1 ELSE 0 END) as a_count,
                MAX(created_at) as last_scan
            FROM keyword_insights
        """)
        stats = dict(cursor.fetchone())

        conn.close()

        return {
            'running_scan': dict(running_scan) if running_scan else None,
            'categories': categories,
            'total_stats': stats,
            'categories_needing_scan': sum(1 for c in categories if c['needs_scan'])
        }

    except Exception as e:
        logger.error(f"[scan-status] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 5.1] AI 콘텐츠 생성 제안 시스템
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/content-suggestions")
async def get_content_suggestions(
    limit: int = 5,
    category: Optional[str] = None
) -> Dict[str, Any]:
    """
    [Phase 5.1] AI 기반 콘텐츠 제안

    트렌드 키워드와 경쟁사 약점을 분석하여 콘텐츠 아이디어를 자동 생성합니다.

    분석 요소:
    - 상승 트렌드 키워드 (rising)
    - 고검색량 S/A급 키워드
    - 경쟁사 약점 키워드
    - 계절/시기별 키워드

    Args:
        limit: 제안 개수 (기본 5개)
        category: 특정 카테고리 필터 (선택)

    Returns:
        콘텐츠 제안 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        suggestions = []

        # 1. 상승 트렌드 키워드 기반 제안
        query = """
            SELECT keyword, category, search_volume, grade, trend_status
            FROM keyword_insights
            WHERE trend_status = 'rising'
              AND grade IN ('S', 'A', 'B')
        """
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY search_volume DESC LIMIT 3"

        cursor.execute(query, params)
        rising_keywords = [dict(row) for row in cursor.fetchall()]

        for kw in rising_keywords:
            suggestions.append({
                'type': 'trend',
                'priority': 'high',
                'keyword': kw['keyword'],
                'category': kw['category'],
                'search_volume': kw['search_volume'],
                'title_idea': f"[트렌드] {kw['keyword']} - 지금 주목받는 이유",
                'content_type': 'blog',
                'reason': f"검색량 상승 중인 {kw['grade']}급 키워드입니다. 빠른 콘텐츠 제작 추천.",
                'suggested_topics': [
                    f"{kw['keyword']}란 무엇인가?",
                    f"{kw['keyword']} 효과와 주의사항",
                    f"{kw['keyword']} 실제 후기 및 경험담"
                ]
            })

        # 2. 고검색량 키워드 기반 제안
        query = """
            SELECT keyword, category, search_volume, grade
            FROM keyword_insights
            WHERE grade IN ('S', 'A')
              AND search_volume >= 1000
        """
        params = []
        if category:
            query += " AND category = ?"
            params.append(category)
        query += " ORDER BY search_volume DESC LIMIT 3"

        cursor.execute(query, params)
        high_volume_keywords = [dict(row) for row in cursor.fetchall()]

        for kw in high_volume_keywords:
            if not any(s['keyword'] == kw['keyword'] for s in suggestions):
                suggestions.append({
                    'type': 'high_volume',
                    'priority': 'medium',
                    'keyword': kw['keyword'],
                    'category': kw['category'],
                    'search_volume': kw['search_volume'],
                    'title_idea': f"[인기] {kw['keyword']} 완벽 가이드",
                    'content_type': 'blog',
                    'reason': f"검색량 {kw['search_volume']:,}의 {kw['grade']}급 키워드입니다.",
                    'suggested_topics': [
                        f"{kw['keyword']} 기본 정보",
                        f"{kw['keyword']} 비용과 과정",
                        f"{kw['keyword']} 선택 시 주의점"
                    ]
                })

        # 3. 경쟁사 약점 기반 제안
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitor_weaknesses'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT DISTINCT weakness_type, suggested_keywords
                FROM competitor_weaknesses
                WHERE suggested_keywords IS NOT NULL
                ORDER BY discovered_at DESC
                LIMIT 3
            """)
            weaknesses = cursor.fetchall()

            for weakness in weaknesses:
                weakness_type = weakness[0]
                suggested_kws = weakness[1]

                if suggested_kws:
                    try:
                        kws = json.loads(suggested_kws) if isinstance(suggested_kws, str) else suggested_kws
                        if kws and len(kws) > 0:
                            main_kw = kws[0] if isinstance(kws[0], str) else kws[0].get('keyword', '')
                            if main_kw and not any(s['keyword'] == main_kw for s in suggestions):
                                suggestions.append({
                                    'type': 'competitor_gap',
                                    'priority': 'high',
                                    'keyword': main_kw,
                                    'category': weakness_type,
                                    'search_volume': 0,
                                    'title_idea': f"[차별화] 경쟁사가 놓친 {weakness_type} 포인트",
                                    'content_type': 'blog',
                                    'reason': f"경쟁사 약점인 '{weakness_type}' 분야에서 차별화 기회입니다.",
                                    'suggested_topics': [
                                        f"우리 {weakness_type}의 차별점",
                                        f"고객이 원하는 {weakness_type} 서비스",
                                        f"{weakness_type} 관련 실제 사례"
                                    ]
                                })
                    except (json.JSONDecodeError, TypeError, KeyError, IndexError):
                        pass

        conn.close()

        # 우선순위 정렬 및 제한
        priority_order = {'high': 0, 'medium': 1, 'low': 2}
        suggestions.sort(key=lambda x: priority_order.get(x['priority'], 2))
        suggestions = suggestions[:limit]

        return {
            'status': 'success',
            'suggestions': suggestions,
            'count': len(suggestions),
            'generated_at': datetime.now().isoformat()
        }

    except Exception as e:
        logger.error(f"[content-suggestions] {str(e)}")
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
# [Phase 6.2] KEI (Keyword Effectiveness Index) API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@router.get("/keywords/top-kei")
async def get_top_kei_keywords(
    limit: int = 20,
    min_volume: int = 10
) -> Dict[str, Any]:
    """
    [Phase 6.2] KEI 상위 키워드 조회

    KEI가 높은 키워드는 검색량 대비 경쟁이 낮아 공략하기 좋은 키워드입니다.

    Args:
        limit: 최대 개수 (기본 20)
        min_volume: 최소 검색량 (기본 10)

    Returns:
        KEI 상위 키워드 목록
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                keyword, search_volume, difficulty, opportunity,
                grade, category, kei,
                CASE
                    WHEN kei IS NULL OR kei = 0 THEN
                        ROUND((COALESCE(search_volume, 0) * 10.0) / MAX(1, COALESCE(difficulty, 50)), 2)
                    ELSE kei
                END as calculated_kei
            FROM keyword_insights
            WHERE search_volume >= ?
            AND status != 'archived'
            ORDER BY calculated_kei DESC
            LIMIT ?
        """, (min_volume, limit))

        keywords = []
        for row in cursor.fetchall():
            kw = dict(row)
            kw['category'] = normalize_category(kw.get('category', '기타'))
            # KEI 등급 부여
            kei = kw['calculated_kei'] or 0
            if kei >= 50:
                kw['kei_grade'] = 'S'
            elif kei >= 30:
                kw['kei_grade'] = 'A'
            elif kei >= 15:
                kw['kei_grade'] = 'B'
            else:
                kw['kei_grade'] = 'C'
            keywords.append(kw)

        conn.close()

        return {
            "status": "success",
            "keywords": keywords,
            "count": len(keywords),
            "description": "KEI가 높을수록 검색량 대비 경쟁이 낮아 공략하기 좋은 키워드입니다."
        }

    except Exception as e:
        logger.error(f"[top-kei] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


@router.post("/keywords/recalculate-kei")
async def recalculate_kei_values() -> Dict[str, Any]:
    """
    [Phase 6.2] 모든 키워드의 KEI 값 일괄 재계산

    DB에 저장된 모든 키워드에 대해 KEI 값을 재계산하여 업데이트합니다.
    공식: KEI = (search_volume / max(1, difficulty)) * 10

    Returns:
        재계산 결과 통계
    """
    try:
        db = DatabaseManager()
        conn = None
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # KEI 일괄 업데이트
        cursor.execute("""
            UPDATE keyword_insights
            SET kei = ROUND((COALESCE(search_volume, 0) * 10.0) / MAX(1, COALESCE(difficulty, 50)), 2)
            WHERE search_volume IS NOT NULL
        """)

        updated_count = cursor.rowcount
        conn.commit()

        # 통계 조회
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                ROUND(AVG(kei), 2) as avg_kei,
                ROUND(MAX(kei), 2) as max_kei,
                ROUND(MIN(kei), 2) as min_kei,
                SUM(CASE WHEN kei >= 50 THEN 1 ELSE 0 END) as s_grade_count,
                SUM(CASE WHEN kei >= 30 AND kei < 50 THEN 1 ELSE 0 END) as a_grade_count,
                SUM(CASE WHEN kei >= 15 AND kei < 30 THEN 1 ELSE 0 END) as b_grade_count,
                SUM(CASE WHEN kei < 15 THEN 1 ELSE 0 END) as c_grade_count
            FROM keyword_insights
            WHERE kei IS NOT NULL
        """)
        stats = dict(cursor.fetchone() or {})
        conn.close()

        return {
            "status": "success",
            "message": f"{updated_count}개 키워드의 KEI가 재계산되었습니다.",
            "updated_count": updated_count,
            "statistics": stats
        }

    except Exception as e:
        logger.error(f"[recalculate-kei] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass
