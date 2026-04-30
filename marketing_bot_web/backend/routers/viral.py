"""
Viral Hunter API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

바이럴 타겟 발굴 및 댓글 생성

[Phase 4.0] 개선사항
- 비동기 일괄 검증 (asyncio + aiohttp)
- 동시 요청 제한 (Semaphore)
- 검증 결과 캐싱 (1시간)
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional, Literal
import sys
import os
from pathlib import Path
import subprocess
import json
import asyncio
import sqlite3
import logging
import threading
from datetime import datetime, timedelta
from functools import lru_cache
import time

logger = logging.getLogger(__name__)

# aiohttp는 선택적 의존성 (없으면 동기 방식 폴백)
try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

# httpx 비동기 HTTP 클라이언트
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

# [U3] 검증 결과 캐시는 services/viral_service.VerificationCache로 이관됨.
# 기존 API 호환을 위해 thin wrapper 유지.
from services.viral_service import _verification_cache as _svc_verification_cache


def _get_cached_verification(url: str) -> Optional[Dict[str, Any]]:
    """캐시된 검증 결과 — services.viral_service.VerificationCache로 위임."""
    return _svc_verification_cache.get(url)


def _set_cache_verification(url: str, result: Dict[str, Any]):
    """검증 결과를 캐시에 저장 — services.viral_service.VerificationCache로 위임."""
    _svc_verification_cache.set(url, result)


# [AA4] Idempotency 캐시 — 프로세스 로컬. key → 처리 시점(epoch).
# 10분 TTL로 오래된 항목은 /action 호출 시 청소.
_idempotency_cache: Dict[str, float] = {}

# [코드 품질 개선] 공통 경로 설정 사용
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, backend_dir)
import setup_paths
parent_dir = str(setup_paths.PROJECT_ROOT)

from db.database import DatabaseManager
from viral_hunter import ViralHunter, ViralTarget
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response
from urllib.parse import urlencode, urlparse, urlunparse, parse_qs

router = APIRouter()

VIRAL_CORE_CATEGORIES = [
    "\ub2e4\uc774\uc5b4\ud2b8",
    "\uad50\ud1b5\uc0ac\uace0",
    "\ud53c\ubd80",
    "\ube44\ub300\uce6d/\uad50\uc815",
    "\uccb4\ud615\uad50\uc815",
    "\ub9ac\ud504\ud305/\ud0c4\ub825",
    "\uacbd\uc7c1\uc0ac_\uc5ed\uacf5\ub7b5",
]


def _latest_legion_scan_id(cursor: sqlite3.Cursor) -> int:
    try:
        cursor.execute(
            """
            SELECT id
            FROM scan_runs
            WHERE mode LIKE '%legion%' AND status = 'completed'
            ORDER BY completed_at DESC, id DESC
            LIMIT 1
            """
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0
    except Exception:
        return 0


def _apply_work_scope_sql(
    cursor: sqlite3.Cursor,
    work_scope: Optional[str],
    where: List[str],
    params: List[Any],
) -> None:
    scope = work_scope or "latest_legion"
    if scope == "all_backlog":
        return
    if scope == "latest_legion":
        scan_id = _latest_legion_scan_id(cursor)
        if scan_id:
            where.append("source_scan_run_id = ?")
            params.append(scan_id)
    if scope in ("latest_legion", "core"):
        where.append(f"category IN ({','.join(['?'] * len(VIRAL_CORE_CATEGORIES))})")
        params.extend(VIRAL_CORE_CATEGORIES)


def _apply_work_scope_filters(cursor: sqlite3.Cursor, filters: Dict[str, Any], work_scope: Optional[str]) -> None:
    scope = work_scope or "latest_legion"
    if scope == "all_backlog":
        return
    if scope in ("latest_legion", "core") and not filters.get("category"):
        filters["include_categories"] = VIRAL_CORE_CATEGORIES
    if scope == "latest_legion":
        scan_id = _latest_legion_scan_id(cursor)
        if scan_id:
            filters["source_scan_run_id"] = scan_id

# [성능 최적화] ViralHunter 싱글톤 인스턴스
_viral_hunter_instance: Optional[ViralHunter] = None

def get_viral_hunter() -> ViralHunter:
    """ViralHunter 싱글톤 인스턴스 반환 (매 요청마다 생성 방지)"""
    global _viral_hunter_instance
    if _viral_hunter_instance is None:
        _viral_hunter_instance = ViralHunter()
    return _viral_hunter_instance


def get_db_path():
    """DatabaseManager에서 db_path 가져오기"""
    return DatabaseManager().db_path


# =======================================================================
# UTM 추적 설정 [Phase 4.0 투명성 개선]
# =======================================================================
# UTM 매개변수는 자체 마케팅 활동의 효과를 측정하기 위해 사용됩니다.
# 수집 정보: 유입 경로(source), 매체 유형(medium), 캠페인명(campaign)
# 이 정보는 어떤 콘텐츠가 효과적인지 분석하는 데만 사용됩니다.
# [T2] UTM 관련 로직(UTM_TRACKING_ENABLED 상수, _generate_utm_url, UTMRequest 등)은
# routers/viral_utm.py로 이관됨. 필요 시 `from routers.viral_utm import ...`로 사용.


def _create_lead_from_viral(db: DatabaseManager, target_id: str) -> bool:
    """
    [Phase 4.0] 바이럴 타겟을 리드(mentions)로 자동 등록

    승인된 바이럴 타겟의 정보를 mentions 테이블에 리드로 추가합니다.
    source_module='viral_hunter'로 표시하여 출처를 명확히 합니다.

    Args:
        db: DatabaseManager 인스턴스
        target_id: viral_targets 테이블의 ID

    Returns:
        리드 생성 성공 여부
    """
    import sqlite3
    conn = None
    try:
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 바이럴 타겟 정보 조회 — matched_keywords 포함 (실제 키워드 추적용)
        cursor.execute("""
            SELECT id, platform, title, url, author, category, content,
                   discovered_at, generated_comment, matched_keywords
            FROM viral_targets
            WHERE id = ?
        """, (target_id,))
        target = cursor.fetchone()

        if not target:
            return False

        (target_id_val, platform, title, url, author, category, content,
         discovered_at, comment, matched_keywords_json) = target

        # 실제 키워드 추출: matched_keywords JSON의 첫 요소.
        # 카테고리 라벨이 keyword 자리에 들어가던 버그 픽스 — 키워드별 ROI 계산의 전제 조건.
        actual_keyword = ''
        if matched_keywords_json:
            try:
                kws = json.loads(matched_keywords_json) if isinstance(matched_keywords_json, str) else matched_keywords_json
                if isinstance(kws, list) and kws:
                    actual_keyword = str(kws[0]).strip()
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        if not actual_keyword:
            actual_keyword = (category or '').strip()  # 폴백: 키워드 추출 실패 시에만 카테고리

        # [Q11] 카테고리 정규화 — keyword_insights/legacy 값이 mentions로 흘러들어와도 표준 11종으로
        try:
            from services.category_normalizer import normalize_category
            normalized_category = normalize_category(category)
        except ImportError:
            normalized_category = category or '기타'

        # mentions 테이블 컬럼 체크 (source_module, source_target_id)
        cursor.execute("PRAGMA table_info(mentions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'source_module' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_module TEXT DEFAULT NULL")
        if 'source_target_id' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_target_id TEXT DEFAULT NULL")

        # 중복 체크 (같은 URL이 이미 있는지)
        cursor.execute("SELECT id FROM mentions WHERE url = ?", (url,))
        if cursor.fetchone():
            return False  # 이미 존재함

        # 리드 등록
        platform_mapped = platform.lower() if platform else 'viral'
        if 'youtube' in platform_mapped:
            platform_mapped = 'youtube'
        elif 'tiktok' in platform_mapped:
            platform_mapped = 'tiktok'
        elif 'naver' in platform_mapped or 'blog' in platform_mapped or 'cafe' in platform_mapped:
            platform_mapped = 'naver'
        elif 'instagram' in platform_mapped:
            platform_mapped = 'instagram'

        # source_target_id로 viral_targets와 연결 — 양방향 추적용
        cursor.execute("""
            INSERT INTO mentions (
                platform, title, url, summary, content,
                author, category, keyword, status,
                source_module, source_target_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'viral_hunter', ?, datetime('now', 'localtime'))
        """, (
            platform_mapped,
            title or '',
            url or '',
            content[:500] if content else '',  # summary
            content or '',
            author or '',
            normalized_category,   # 표준 11종으로 정규화된 카테고리
            actual_keyword,        # 실제 키워드 (이전 버그: category가 들어갔음)
            target_id_val,         # source_target_id 채움 (이전: NULL이었음)
        ))

        conn.commit()
        return True

    except Exception as e:
        print(f"[viral→lead Error] {str(e)}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()


TargetAction = Literal["approve", "skip", "delete"]
PrioritizeSortBy = Literal["priority_score", "freshness", "engagement"]


class CommentGenerateRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)
    style: str = Field("default", description="댓글 스타일 (default, empathy, informative, experience, question, recommendation)")


class TargetActionRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)
    action: TargetAction
    comment: Optional[str] = Field(None, max_length=2000)
    # [D2] skip 액션에 사유 태그 (도메인/작성자 감점 학습용)
    skip_reason: Optional[str] = Field(None, max_length=50)
    skip_note: Optional[str] = Field(None, max_length=500)
    # [AA4] Idempotency 키 — 오프라인 큐 중복 방지
    idempotency_key: Optional[str] = Field(None, max_length=64)


class TargetFeedbackRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)
    rating: Literal["good", "needs_edit", "bad"]
    reason: Optional[str] = Field(None, max_length=80)
    corrected_comment: Optional[str] = Field(None, max_length=2000)
    staff_user: Optional[str] = Field("staff", max_length=80)


class BulkActionByFilterRequest(BaseModel):
    """[F3] 필터 조건으로 매칭되는 전체 타겟에 대한 대량 액션."""
    action: TargetAction
    # 필터 (GET /targets와 동일)
    status: str = "pending"
    category: Optional[str] = None
    date_filter: Optional[str] = None
    platforms: Optional[List[str]] = None
    comment_status: Optional[str] = None
    min_scan_count: Optional[int] = None
    search: Optional[str] = None
    scan_batch: Optional[str] = None
    # AI 분류 필터 — 골든 큐 안전장치 (직원이 280건 골든타겟에만 일괄 작업 가능)
    ai_ad_label: Optional[str] = None
    specialty_match: Optional[str] = None
    post_region: Optional[str] = None
    min_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    # 안전장치
    max_affected: int = Field(default=10000, ge=1, le=100000)
    dry_run: bool = False
    # 선택: skip 사유 (모든 타겟에 공통 적용)
    skip_reason: Optional[str] = Field(None, max_length=50)


class VerifyTargetRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)


class BatchCommentRequest(BaseModel):
    """[Phase 5.1] 댓글 배치 생성 요청"""
    target_ids: Optional[List[str]] = None  # 특정 타겟 ID 목록 (없으면 자동 선택)
    category: Optional[str] = Field(None, max_length=50)  # 카테고리 필터
    batch_size: int = Field(20, ge=1, le=100)  # 배치 크기 (1-100개)
    prioritize_by: PrioritizeSortBy = "priority_score"  # 정렬 기준


# Quality feedback and ops audit tables are created lazily so existing DBs migrate in place.
def _ensure_quality_ops_tables(conn: sqlite3.Connection) -> None:
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS viral_target_feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id TEXT NOT NULL,
            rating TEXT NOT NULL,
            reason TEXT,
            corrected_comment TEXT,
            staff_user TEXT DEFAULT 'staff',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_viral_target_feedback_target
        ON viral_target_feedback(target_id, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_viral_target_feedback_rating
        ON viral_target_feedback(rating, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            actor TEXT DEFAULT 'system',
            action TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            entity_id TEXT,
            before_json TEXT,
            after_json TEXT,
            metadata_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_entity
        ON audit_events(entity_type, entity_id, created_at DESC)
        """
    )
    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_action
        ON audit_events(action, created_at DESC)
        """
    )
    conn.commit()


def _fetch_target_snapshot(cursor: sqlite3.Cursor, target_id: str) -> Dict[str, Any]:
    cursor.execute(
        """
        SELECT id, title, url, platform, category, comment_status, priority_score,
               generated_comment, source_scan_run_id, matched_keyword, matched_keyword_grade
        FROM viral_targets
        WHERE id = ?
        """,
        (target_id,),
    )
    row = cursor.fetchone()
    if not row:
        return {}
    keys = [
        "id", "title", "url", "platform", "category", "comment_status", "priority_score",
        "generated_comment", "source_scan_run_id", "matched_keyword", "matched_keyword_grade",
    ]
    return dict(zip(keys, row))


def _write_audit_event(
    conn: sqlite3.Connection,
    action: str,
    entity_type: str,
    entity_id: str,
    before: Optional[Dict[str, Any]] = None,
    after: Optional[Dict[str, Any]] = None,
    metadata: Optional[Dict[str, Any]] = None,
    actor: str = "staff",
) -> None:
    _ensure_quality_ops_tables(conn)
    conn.execute(
        """
        INSERT INTO audit_events (
            actor, action, entity_type, entity_id, before_json, after_json, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            actor,
            action,
            entity_type,
            entity_id,
            json.dumps(before or {}, ensure_ascii=False),
            json.dumps(after or {}, ensure_ascii=False),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    conn.commit()


# [Phase 4.0] 댓글 가능 여부 검증 함수
def _verify_url_commentable(url: str, platform: str) -> Dict[str, Any]:
    """
    URL에 접속하여 댓글 가능 여부를 확인

    Args:
        url: 확인할 URL
        platform: 플랫폼 (youtube, naver, instagram 등)

    Returns:
        {
            'accessible': bool,        # URL 접근 가능 여부
            'commentable': bool,       # 댓글 가능 여부
            'reason': str,             # 상태 설명
            'verified_at': str         # 확인 시간
        }
    """
    import requests
    from datetime import datetime

    result = {
        'accessible': False,
        'commentable': False,
        'reason': '확인 중...',
        'verified_at': datetime.now().isoformat()
    }

    try:
        # URL 접근 확인 (5초 타임아웃)
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=5, allow_redirects=True)

        if response.status_code == 200:
            result['accessible'] = True
            html_content = response.text.lower()

            # 플랫폼별 댓글 가능 여부 확인
            if 'youtube' in platform.lower():
                # YouTube: 댓글 비활성화 패턴 확인
                if 'comments are turned off' in html_content or '댓글이 사용 중지되었습니다' in html_content:
                    result['commentable'] = False
                    result['reason'] = '댓글이 비활성화됨'
                elif 'comments' in html_content or 'comment' in html_content:
                    result['commentable'] = True
                    result['reason'] = '댓글 작성 가능'
                else:
                    result['commentable'] = False
                    result['reason'] = '댓글 영역 없음'

            elif 'kin' in platform.lower():
                # 네이버 지식인: 답변 가능 여부 확인
                if '질문마감' in html_content or '채택완료' in html_content:
                    result['commentable'] = False
                    result['reason'] = '질문 마감됨 (채택 완료)'
                elif '삭제된 질문' in html_content:
                    result['commentable'] = False
                    result['reason'] = '삭제된 질문'
                elif '답변' in html_content:
                    result['commentable'] = True
                    result['reason'] = '답변 작성 가능'
                else:
                    result['commentable'] = True
                    result['reason'] = '답변 가능 추정'

            elif 'naver' in platform.lower() or 'blog' in platform.lower() or 'cafe' in platform.lower():
                # 네이버 블로그/카페: 댓글 영역 확인
                if '회원만 볼 수 있는' in html_content or '멤버에게만 공개' in html_content:
                    result['commentable'] = False
                    result['reason'] = '회원 전용 게시글'
                elif '삭제된 게시글' in html_content:
                    result['commentable'] = False
                    result['reason'] = '삭제된 게시글'
                elif '댓글' in html_content or 'comment' in html_content:
                    if '댓글을 작성하려면 로그인' in html_content:
                        result['commentable'] = True
                        result['reason'] = '댓글 가능 (로그인 필요)'
                    elif '댓글 작성 불가' in html_content or '댓글 기능을 사용할 수 없' in html_content:
                        result['commentable'] = False
                        result['reason'] = '댓글이 비활성화됨'
                    else:
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                else:
                    result['commentable'] = False
                    result['reason'] = '댓글 영역 없음'

            elif 'instagram' in platform.lower():
                # Instagram: 로그인 필요하므로 기본적으로 확인만
                result['commentable'] = True
                result['reason'] = '확인 필요 (로그인 후)'

            elif 'tiktok' in platform.lower():
                # TikTok: 댓글 영역 확인
                if '댓글' in html_content or 'comment' in html_content:
                    result['commentable'] = True
                    result['reason'] = '댓글 작성 가능'
                else:
                    result['commentable'] = False
                    result['reason'] = '댓글 영역 확인 불가'

            else:
                # 기타 플랫폼: 기본 확인
                if '댓글' in html_content or 'comment' in html_content:
                    result['commentable'] = True
                    result['reason'] = '댓글 영역 발견'
                else:
                    result['commentable'] = False
                    result['reason'] = '댓글 영역 없음'

        elif response.status_code == 404:
            result['reason'] = '페이지를 찾을 수 없음 (삭제됨)'

        elif response.status_code == 403:
            result['reason'] = '접근 권한 없음'

        else:
            result['reason'] = f'HTTP 오류 ({response.status_code})'

    except requests.exceptions.Timeout:
        result['reason'] = '요청 시간 초과'
    except requests.exceptions.ConnectionError:
        result['reason'] = '연결 실패'
    except Exception as e:
        result['reason'] = f'확인 실패: {str(e)}'

    return result


# [성능 개선] httpx 기반 비동기 URL 검증 함수
async def _verify_url_commentable_async(url: str, platform: str) -> Dict[str, Any]:
    """
    URL에 비동기로 접속하여 댓글 가능 여부를 확인 (httpx 사용)

    Args:
        url: 확인할 URL
        platform: 플랫폼 (youtube, naver, instagram 등)

    Returns:
        {
            'accessible': bool,        # URL 접근 가능 여부
            'commentable': bool,       # 댓글 가능 여부
            'reason': str,             # 상태 설명
            'verified_at': str         # 확인 시간
        }
    """
    result = {
        'accessible': False,
        'commentable': False,
        'reason': '확인 중...',
        'verified_at': datetime.now().isoformat()
    }

    # httpx를 사용할 수 없으면 동기 함수로 폴백
    if not HTTPX_AVAILABLE:
        return _verify_url_commentable(url, platform)

    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as client:
            response = await client.get(url, headers=headers)

            if response.status_code == 200:
                result['accessible'] = True
                html_content = response.text.lower()

                # 플랫폼별 댓글 가능 여부 확인
                if 'youtube' in platform.lower():
                    if 'comments are turned off' in html_content or '댓글이 사용 중지되었습니다' in html_content:
                        result['commentable'] = False
                        result['reason'] = '댓글이 비활성화됨'
                    elif 'comments' in html_content or 'comment' in html_content:
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                    else:
                        result['commentable'] = False
                        result['reason'] = '댓글 영역 없음'

                elif 'kin' in platform.lower():
                    if '질문마감' in html_content or '채택완료' in html_content:
                        result['commentable'] = False
                        result['reason'] = '질문 마감됨 (채택 완료)'
                    elif '삭제된 질문' in html_content:
                        result['commentable'] = False
                        result['reason'] = '삭제된 질문'
                    elif '답변' in html_content:
                        result['commentable'] = True
                        result['reason'] = '답변 작성 가능'
                    else:
                        result['commentable'] = True
                        result['reason'] = '답변 가능 추정'

                elif 'naver' in platform.lower() or 'blog' in platform.lower() or 'cafe' in platform.lower():
                    if '회원만 볼 수 있는' in html_content or '멤버에게만 공개' in html_content:
                        result['commentable'] = False
                        result['reason'] = '회원 전용 게시글'
                    elif '삭제된 게시글' in html_content:
                        result['commentable'] = False
                        result['reason'] = '삭제된 게시글'
                    elif '댓글' in html_content or 'comment' in html_content:
                        if '댓글을 작성하려면 로그인' in html_content:
                            result['commentable'] = True
                            result['reason'] = '댓글 가능 (로그인 필요)'
                        elif '댓글 작성 불가' in html_content or '댓글 기능을 사용할 수 없' in html_content:
                            result['commentable'] = False
                            result['reason'] = '댓글이 비활성화됨'
                        else:
                            result['commentable'] = True
                            result['reason'] = '댓글 작성 가능'
                    else:
                        result['commentable'] = False
                        result['reason'] = '댓글 영역 없음'

                elif 'instagram' in platform.lower():
                    result['commentable'] = True
                    result['reason'] = '확인 필요 (로그인 후)'

                elif 'tiktok' in platform.lower():
                    if '댓글' in html_content or 'comment' in html_content:
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                    else:
                        result['commentable'] = False
                        result['reason'] = '댓글 영역 확인 불가'
                else:
                    if '댓글' in html_content or 'comment' in html_content:
                        result['commentable'] = True
                        result['reason'] = '댓글 영역 발견'
                    else:
                        result['commentable'] = False
                        result['reason'] = '댓글 영역 없음'

            elif response.status_code == 404:
                result['reason'] = '페이지를 찾을 수 없음 (삭제됨)'
            elif response.status_code == 403:
                result['reason'] = '접근 권한 없음'
            else:
                result['reason'] = f'HTTP 오류 ({response.status_code})'

    except httpx.TimeoutException:
        result['reason'] = '요청 시간 초과'
    except httpx.ConnectError:
        result['reason'] = '연결 실패'
    except Exception as e:
        result['reason'] = f'확인 실패: {str(e)}'

    return result


# [P2-3] 비동기 URL 검증 함수
async def _verify_url_async(
    session: 'aiohttp.ClientSession',
    url: str,
    platform: str,
    semaphore: asyncio.Semaphore
) -> Dict[str, Any]:
    """
    비동기 URL 검증 (aiohttp 사용)
    Semaphore로 동시 요청 수 제한
    """
    # 캐시 확인
    cached = _get_cached_verification(url)
    if cached:
        cached_copy = cached.copy()
        cached_copy['from_cache'] = True
        return cached_copy

    result = {
        'accessible': False,
        'commentable': False,
        'reason': '확인 중...',
        'verified_at': datetime.now().isoformat(),
        'from_cache': False
    }

    async with semaphore:  # 동시 요청 수 제한
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=5)) as response:
                if response.status == 200:
                    result['accessible'] = True
                    html_content = (await response.text()).lower()

                    # 플랫폼별 댓글 가능 여부 확인
                    if 'youtube' in platform.lower():
                        if 'comments are turned off' in html_content:
                            result['commentable'] = False
                            result['reason'] = '댓글이 비활성화됨'
                        elif 'comments' in html_content:
                            result['commentable'] = True
                            result['reason'] = '댓글 작성 가능'
                        else:
                            result['commentable'] = False
                            result['reason'] = '댓글 영역 없음'

                    elif 'naver' in platform.lower() or 'blog' in platform.lower() or 'cafe' in platform.lower():
                        if '댓글' in html_content or 'comment' in html_content:
                            result['commentable'] = True
                            result['reason'] = '댓글 작성 가능'
                        else:
                            result['commentable'] = False
                            result['reason'] = '댓글 영역 없음'

                    elif 'instagram' in platform.lower():
                        result['commentable'] = True
                        result['reason'] = '확인 필요 (로그인 후)'

                    else:
                        if '댓글' in html_content or 'comment' in html_content:
                            result['commentable'] = True
                            result['reason'] = '댓글 영역 발견'
                        else:
                            result['commentable'] = False
                            result['reason'] = '댓글 영역 없음'

                elif response.status == 404:
                    result['reason'] = '페이지를 찾을 수 없음 (삭제됨)'
                elif response.status == 403:
                    result['reason'] = '접근 권한 없음'
                else:
                    result['reason'] = f'HTTP 오류 ({response.status})'

        except asyncio.TimeoutError:
            result['reason'] = '요청 시간 초과'
        except Exception as e:
            result['reason'] = f'확인 실패: {str(e)}'

    # 캐시에 저장
    _set_cache_verification(url, result)
    return result


@router.get("/scan-batches")
async def get_scan_batches() -> List[Dict[str, Any]]:
    """
    스캔 배치 목록 조회 (언제 스캔한 데이터인지)

    discovered_at을 기준으로 그룹화하여 배치 목록 반환
    - 최신 배치가 첫 번째
    - 각 배치에 타겟 수 포함

    Returns:
        스캔 배치 목록 [{batch_id, batch_label, count, scan_time}]
    """
    try:
        db = DatabaseManager()

        # discovered_at을 시간 단위로 그룹화 (같은 스캔 세션)
        query = """
            SELECT
                strftime('%Y-%m-%d %H', discovered_at) as batch_hour,
                strftime('%Y-%m-%d', discovered_at) as batch_date,
                strftime('%H', discovered_at) as hour,
                COUNT(*) as count,
                MIN(discovered_at) as first_discovered,
                MAX(discovered_at) as last_discovered
            FROM viral_targets
            WHERE comment_status = 'pending'
            GROUP BY strftime('%Y-%m-%d %H', discovered_at)
            ORDER BY batch_hour DESC
        """

        db.cursor.execute(query)
        rows = db.cursor.fetchall()

        batches = []
        for row in rows:
            batch_hour, batch_date, hour, count, first_discovered, last_discovered = row

            # 배치 라벨 생성 (예: "2026-02-06 21시 (1,300개)")
            batch_id = batch_hour  # YYYY-MM-DD HH 형식
            batch_label = f"{batch_date} {hour}시 ({count:,}개)"

            batches.append({
                'batch_id': batch_id,
                'batch_label': batch_label,
                'batch_date': batch_date,
                'batch_hour': int(hour),
                'count': count,
                'first_discovered': first_discovered,
                'last_discovered': last_discovered
            })

        return batches

    except Exception as e:
        print(f"[Scan Batches Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"스캔 배치 조회 실패: {str(e)}")


@router.get("/stats")
@handle_exceptions
async def get_viral_stats() -> Dict[str, Any]:
    """
    Viral Hunter 통계 조회

    Returns:
        - total_targets: 총 타겟 수
        - pending: 대기 중
        - approved: 승인됨
        - posted: 게시됨
        - skipped: 건너뜀
    """
    default_response = {
        'total_targets': 0,
        'pending': 0,
        'approved': 0,
        'posted': 0,
        'skipped': 0
    }

    try:
        hunter = get_viral_hunter()
        stats = hunter.get_stats()

        # 프론트엔드가 기대하는 형식으로 변환
        return {
            'total_targets': stats.get('total', 0),
            'pending': stats.get('by_status', {}).get('pending', 0),
            'approved': stats.get('by_status', {}).get('approved', 0),
            'posted': stats.get('by_status', {}).get('posted', 0) + stats.get('by_status', {}).get('generated', 0),
            'skipped': stats.get('by_status', {}).get('skipped', 0)
        }

    except Exception as e:
        print(f"[Viral Stats Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"바이럴 통계 조회 실패: {str(e)}")


@router.get("/home-stats")
async def get_viral_home_stats(
    scan_batch: Optional[str] = None,
    work_scope: Optional[str] = Query(default="latest_legion", description="latest_legion|core|all_backlog")
) -> Dict[str, Any]:
    """
    [Phase 9.0 성능 최적화] 홈 화면용 집계 통계 API

    DB에서 직접 집계하여 10,000개 데이터 로드 없이 통계 제공

    Returns:
        - total_count: 총 pending 타겟 수
        - platform_stats: 플랫폼별 통계
        - category_stats: 카테고리별 통계
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 스캔 배치 필터 조건
        scope_where: List[str] = []
        params: List[Any] = []
        _apply_work_scope_sql(cursor, work_scope, scope_where, params)
        if scan_batch:
            scope_where.append("strftime('%Y-%m-%d %H', discovered_at) = ?")
            params.append(scan_batch)
        batch_condition = f"AND {' AND '.join(scope_where)}" if scope_where else ""

        # 1. 플랫폼별 통계 (DB 집계)
        cursor.execute(f"""
            SELECT
                LOWER(COALESCE(platform, 'other')) as platform,
                COUNT(*) as count,
                AVG(COALESCE(priority_score, 0)) as avg_score,
                MAX(COALESCE(priority_score, 0)) as max_score
            FROM viral_targets
            WHERE comment_status = 'pending'
            {batch_condition}
            GROUP BY LOWER(COALESCE(platform, 'other'))
        """, params)

        platform_rows = cursor.fetchall()
        platform_stats = {}
        for row in platform_rows:
            # 플랫폼명 정규화
            p = row['platform'] or 'other'
            if 'cafe' in p or '카페' in p:
                normalized = 'cafe'
            elif 'blog' in p or '블로그' in p:
                normalized = 'blog'
            elif 'kin' in p or '지식' in p:
                normalized = 'kin'
            elif 'youtube' in p or '유튜브' in p:
                normalized = 'youtube'
            elif 'instagram' in p or '인스타' in p:
                normalized = 'instagram'
            elif 'tiktok' in p or '틱톡' in p:
                normalized = 'tiktok'
            else:
                normalized = 'other'

            if normalized not in platform_stats:
                platform_stats[normalized] = {'count': 0, 'avgScore': 0, 'maxScore': 0, 'totalScore': 0}

            platform_stats[normalized]['count'] += row['count']
            platform_stats[normalized]['totalScore'] += (row['avg_score'] or 0) * row['count']
            platform_stats[normalized]['maxScore'] = max(
                platform_stats[normalized]['maxScore'],
                row['max_score'] or 0
            )

        # 평균 재계산
        for p in platform_stats:
            if platform_stats[p]['count'] > 0:
                platform_stats[p]['avgScore'] = platform_stats[p]['totalScore'] / platform_stats[p]['count']
            del platform_stats[p]['totalScore']

        # 2. 카테고리별 통계 (DB 집계)
        cursor.execute(f"""
            SELECT
                COALESCE(category, '기타') as category,
                COUNT(*) as count,
                AVG(COALESCE(priority_score, 0)) as avg_score,
                MAX(COALESCE(priority_score, 0)) as max_score
            FROM viral_targets
            WHERE comment_status = 'pending'
            {batch_condition}
            GROUP BY COALESCE(category, '기타')
            ORDER BY MAX(COALESCE(priority_score, 0)) DESC
        """, params)

        category_rows = cursor.fetchall()
        category_stats = []
        for row in category_rows:
            avg_score = row['avg_score'] or 0
            max_score = row['max_score'] or 0
            priority = max_score * 0.5 + avg_score * 0.3 + row['count'] * 0.2

            category_stats.append({
                'category': row['category'],
                'count': row['count'],
                'avgScore': round(avg_score, 2),
                'maxScore': round(max_score, 2),
                'priority': round(priority, 2)
            })

        # 우선순위순 정렬
        category_stats.sort(key=lambda x: x['priority'], reverse=True)

        # 3. 총 개수
        cursor.execute(f"""
            SELECT COUNT(*) as total
            FROM viral_targets
            WHERE comment_status = 'pending'
            {batch_condition}
        """, params)
        total_count = cursor.fetchone()['total']

        # 4. 댓글 상태별 통계 (차트용)
        cursor.execute(f"""
            SELECT
                COALESCE(comment_status, 'pending') as status,
                COUNT(*) as count
            FROM viral_targets
            WHERE 1=1
            {batch_condition.replace('AND', 'AND') if batch_condition else ''}
            GROUP BY COALESCE(comment_status, 'pending')
        """, params)
        status_rows = cursor.fetchall()
        status_stats = {row['status']: row['count'] for row in status_rows}

        # 5. 점수 분포 (차트용)
        cursor.execute(f"""
            SELECT
                CASE
                    WHEN priority_score <= 20 THEN '0-20'
                    WHEN priority_score <= 40 THEN '21-40'
                    WHEN priority_score <= 60 THEN '41-60'
                    WHEN priority_score <= 80 THEN '61-80'
                    WHEN priority_score <= 100 THEN '81-100'
                    ELSE '100+'
                END as score_range,
                COUNT(*) as count
            FROM viral_targets
            WHERE comment_status = 'pending'
            {batch_condition}
            GROUP BY score_range
            ORDER BY MIN(COALESCE(priority_score, 0))
        """, params)
        score_rows = cursor.fetchall()
        score_distribution = {row['score_range']: row['count'] for row in score_rows}

        return {
            'total_count': total_count,
            'platform_stats': platform_stats,
            'category_stats': category_stats,
            'status_stats': status_stats,
            'score_distribution': score_distribution
        }

    except Exception as e:
        logger.error(f"[Home Stats Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"홈 통계 조회 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


@router.get("/targets")
async def get_viral_targets(
    status: str = "pending",
    category: Optional[str] = None,
    date_filter: Optional[str] = None,
    platforms: Optional[str] = None,  # 쉼표로 구분된 플랫폼 목록
    comment_status: Optional[str] = None,  # 댓글 상태 필터 (pending, generated, approved, posted, skipped)
    min_scan_count: Optional[int] = None,
    search: Optional[str] = None,
    sort: Optional[str] = None,
    scan_batch: Optional[str] = None,  # 스캔 배치 필터 (YYYY-MM-DD HH 형식)
    ai_ad_label: Optional[str] = None,  # AI 분류 라벨 (자연_질문, 광고, 광고성_후기톤, 기타_노이즈) 쉼표 가능
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0),  # AI 신뢰도 최소
    specialty_match: Optional[str] = None,  # high|medium|low (쉼표 가능). 미용 특화 매칭
    post_region: Optional[str] = None,  # 청주|타지역|불명 (쉼표 가능). 게시글 지역
    work_scope: Optional[str] = Query(default="latest_legion", description="latest_legion|core|all_backlog"),
    limit: int = Query(default=200, ge=1, le=1000, description="최대 조회 수"),
    offset: int = Query(default=0, ge=0, description="페이지 오프셋")
) -> List[Dict[str, Any]]:
    """
    바이럴 타겟 목록 조회 (필터링 및 정렬 지원)

    Args:
        status: 상태 필터 (pending, approved, posted, skipped)
        category: 카테고리 필터
        date_filter: 날짜 필터 (오늘, 최근 7일, 최근 30일)
        platforms: 플랫폼 필터 (쉼표 구분: cafe,blog,instagram)
        comment_status: 댓글 상태 필터 (pending, generated, approved, posted, skipped)
        min_scan_count: 최소 재발견 횟수 (2 이상이면 재발견)
        search: 검색 키워드 (제목/내용)
        sort: 정렬 기준 (priority, date, scan_count)
        scan_batch: 스캔 배치 필터 (YYYY-MM-DD HH 형식)
        limit: 최대 조회 수

    Returns:
        타겟 목록
    """
    try:
        # [S1] ViralTargetRepository로 위임 — hunter.list_targets 경유 제거
        from repositories import ViralTargetRepository
        repo = ViralTargetRepository(get_db_path())

        platforms_list = None
        if platforms:
            platforms_list = [p.strip() for p in platforms.split(',') if p.strip()]

        filters = {k: v for k, v in {
            "status": status,
            "category": category,
            "date_filter": date_filter,
            "platforms": platforms_list,
            "comment_status": comment_status,
            "min_scan_count": min_scan_count,
            "search": search,
            "scan_batch": scan_batch,
            "ai_ad_label": ai_ad_label,
            "min_confidence": min_confidence,
            "specialty_match": specialty_match,
            "post_region": post_region,
        }.items() if v is not None}

        db = DatabaseManager()
        _apply_work_scope_filters(db.cursor, filters, work_scope)

        targets = repo.list(
            filters=filters,
            sort=sort or "priority",
            limit=limit,
            offset=offset,
        )
        # matched_keywords는 Repository에서 이미 list로 디코드됨 — 추가 변환 불필요

        return targets

    except Exception as e:
        print(f"[Viral Targets Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"바이럴 타겟 조회 실패: {str(e)}")


def _record_skip_learning(db, target_id: str, reason_tag: str, note: Optional[str]) -> None:
    """[R4] viral_service로 위임 — 하위 호환용 thin wrapper."""
    from services.viral_service import record_skip_learning as _svc
    _svc(db, target_id, reason_tag, note)


@router.get("/adaptive-penalties")
async def get_adaptive_penalties(min_skip: int = Query(default=3, ge=1)) -> Dict[str, Any]:
    """[D2/R4] 반복 skip된 도메인·작성자 목록. viral_service로 위임."""
    try:
        from services.viral_service import fetch_adaptive_penalties
        return {"items": fetch_adaptive_penalties(get_db_path(), min_skip=min_skip)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/kpi-stats")
async def get_kpi_stats(days: int = Query(default=14, ge=1, le=90)) -> Dict[str, Any]:
    """[U6] KPI 위젯용 통계 — 일/주 처리량, 적체, 적합률.

    응답:
    {
      "daily": [{date, approved, posted, skipped, new_hot}, ...],
      "summary": {
        "backlog_pending": N,
        "backlog_hot": N,
        "today_processed": N,
        "week_processed": N,
        "ai_accept_rate": 0.52,
      },
      "range_days": 14
    }
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # 일별 시계열: last_scanned_at 또는 discovered_at 기준
        cur.execute(
            """
            SELECT DATE(COALESCE(last_scanned_at, discovered_at)) as day,
                   SUM(CASE WHEN comment_status = 'approved' THEN 1 ELSE 0 END) as approved,
                   SUM(CASE WHEN comment_status = 'posted'   THEN 1 ELSE 0 END) as posted,
                   SUM(CASE WHEN comment_status = 'skipped'  THEN 1 ELSE 0 END) as skipped,
                   SUM(CASE WHEN priority_score >= 100 THEN 1 ELSE 0 END) as new_hot
            FROM viral_targets
            WHERE COALESCE(last_scanned_at, discovered_at) >= datetime('now', ?)
            GROUP BY day
            ORDER BY day
            """,
            (f"-{days} days",)
        )
        daily = [dict(r) for r in cur.fetchall()]

        # 적체 (대기 중)
        cur.execute("SELECT COUNT(*) FROM viral_targets WHERE comment_status = 'pending'")
        backlog_pending = cur.fetchone()[0]
        cur.execute(
            "SELECT COUNT(*) FROM viral_targets "
            "WHERE comment_status = 'pending' AND priority_score >= 100"
        )
        backlog_hot = cur.fetchone()[0]

        # 오늘/1주 처리량 (승인+게시+스킵)
        cur.execute(
            """
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status IN ('approved', 'posted', 'skipped')
              AND DATE(last_scanned_at) = DATE('now', 'localtime')
            """
        )
        today_processed = cur.fetchone()[0]
        cur.execute(
            """
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status IN ('approved', 'posted', 'skipped')
              AND last_scanned_at >= datetime('now', '-7 days')
            """
        )
        week_processed = cur.fetchone()[0]

        # AI 적합률 (최근 Ndays 내 등록된 것 중 approved 비율)
        cur.execute(
            """
            SELECT
              SUM(CASE WHEN comment_status IN ('approved','posted') THEN 1 ELSE 0 END) as accepted,
              COUNT(*) as total
            FROM viral_targets
            WHERE discovered_at >= datetime('now', ?)
            """,
            (f"-{days} days",)
        )
        r = cur.fetchone()
        accepted = r[0] or 0
        total = r[1] or 0
        ai_accept_rate = (accepted / total) if total else 0.0

        return {
            "range_days": days,
            "daily": daily,
            "summary": {
                "backlog_pending": backlog_pending,
                "backlog_hot": backlog_hot,
                "today_processed": today_processed,
                "week_processed": week_processed,
                "ai_accept_rate": round(ai_accept_rate, 3),
            },
        }
    except Exception as e:
        logger.error(f"[kpi-stats] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/targets/{target_id}/context")
async def get_target_context(target_id: str) -> Dict[str, Any]:
    """단일 타겟에 대한 컨텍스트 카드 데이터 (과노출·경쟁사·이력).

    - 동일 도메인 내 최근 7일 내 내가 댓글 단 건수
    - 동일 작성자에 대한 최근 7일 댓글 건수
    - 경쟁사 여부 (category == '경쟁사_역공략')
    - 동일 URL 스캔 횟수 (scan_count)
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT id, url, author, category, scan_count, priority_score "
            "FROM viral_targets WHERE id = ?",
            (target_id,),
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="타겟 없음")
        target = dict(row)

        # 도메인 추출
        from urllib.parse import urlparse
        domain = urlparse(target["url"] or "").netloc.replace("www.", "")

        # 동일 도메인 내 7일간 내가 댓글 달았던(승인/posted) 건수
        cursor.execute(
            """
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status IN ('approved', 'posted')
              AND discovered_at >= datetime('now', '-7 days')
              AND url LIKE ?
              AND id != ?
            """,
            (f"%{domain}%", target_id),
        )
        domain_recent_approved = cursor.fetchone()[0] if domain else 0

        # 동일 작성자 최근 댓글 이력 (같은 author 또는 동일 카페명)
        author_recent_approved = 0
        if target.get("author"):
            cursor.execute(
                """
                SELECT COUNT(*) FROM viral_targets
                WHERE comment_status IN ('approved', 'posted')
                  AND discovered_at >= datetime('now', '-7 days')
                  AND author = ?
                  AND id != ?
                """,
                (target["author"], target_id),
            )
            author_recent_approved = cursor.fetchone()[0]

        warnings: List[str] = []
        if domain_recent_approved >= 3:
            warnings.append(
                f"⚠️ 최근 7일간 동일 도메인({domain})에 댓글 {domain_recent_approved}건 작성 — 과노출 주의"
            )
        if author_recent_approved >= 2:
            warnings.append(
                f"⚠️ 동일 작성자/카페 댓글 최근 {author_recent_approved}건 — 반복 노출 주의"
            )
        if (target.get("scan_count") or 0) >= 3:
            warnings.append(
                f"🔁 이 게시글은 {target['scan_count']}회 스캔됨 — 재발견 HOT LEAD 가능성"
            )

        badges: List[Dict[str, str]] = []
        if target.get("category") == "경쟁사_역공략":
            badges.append({"type": "competitor", "label": "⚔️ 경쟁사 역공략", "color": "orange"})
        if (target.get("priority_score") or 0) >= 120:
            badges.append({"type": "tier1", "label": "🔥 Tier 1", "color": "red"})
        elif (target.get("priority_score") or 0) >= 100:
            badges.append({"type": "tier2", "label": "🟠 Tier 2", "color": "amber"})

        return {
            "target_id": target_id,
            "domain": domain,
            "domain_recent_approved_7d": domain_recent_approved,
            "author_recent_approved_7d": author_recent_approved,
            "scan_count": target.get("scan_count") or 0,
            "badges": badges,
            "warnings": warnings,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[target context] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/todays-queue")
async def get_todays_queue(
    total_limit: int = Query(default=30, ge=5, le=100),
    per_category: int = Query(default=5, ge=1, le=20),
    today_only: bool = Query(default=True, description="오늘 발견된 것만 (기본 True)"),
    work_scope: Optional[str] = Query(default="latest_legion", description="latest_legion|core|all_backlog"),
) -> Dict[str, Any]:
    """오늘 작업할 Top N 카테고리별 묶음 큐.

    기본: comment_status='pending' + 우선순위 DESC 상위 30건을 카테고리별로 묶음.
    [V1] today_only=True(기본)이면 오늘(로컬 시간) 발견된 것만.

    응답:
    {
      "total": 30,
      "today_only": true,
      "generated_at": "...",
      "groups": [...]
    }
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        scope_where: List[str] = []
        params: List[Any] = []
        _apply_work_scope_sql(cursor, work_scope, scope_where, params)
        scope_condition = f" AND {' AND '.join(scope_where)}" if scope_where else ""

        query = f"""
            SELECT id, platform, url, title, content_preview, matched_keywords,
                   category, priority_score, discovered_at, author, matched_keyword
            FROM viral_targets
            WHERE comment_status = 'pending'
              AND priority_score >= 80
              {scope_condition}
        """
        if today_only:
            query += " AND DATE(discovered_at) = DATE('now', 'localtime')"
        query += " ORDER BY priority_score DESC, discovered_at DESC LIMIT ?"
        params.append(total_limit)
        cursor.execute(query, params)
        rows = [dict(r) for r in cursor.fetchall()]

        # matched_keywords JSON 파싱
        for r in rows:
            if isinstance(r.get("matched_keywords"), str):
                try:
                    r["matched_keywords"] = json.loads(r["matched_keywords"])
                except Exception:
                    r["matched_keywords"] = []

        # 카테고리별 그룹핑 (per_category 상한 적용)
        groups_map: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            cat = r.get("category") or "기타"
            groups_map.setdefault(cat, []).append(r)

        groups = []
        for cat, items in sorted(groups_map.items(), key=lambda kv: (-len(kv[1]), kv[0])):
            groups.append({
                "category": cat,
                "count": len(items),
                "items": items[:per_category],
            })

        return {
            "total": len(rows),
            "today_only": today_only,
            "generated_at": datetime.now().isoformat(),
            "groups": groups,
        }
    except Exception as e:
        logger.error(f"[todays-queue] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/targets/count")
async def count_viral_targets(
    status: str = "pending",
    category: Optional[str] = None,
    date_filter: Optional[str] = None,
    platforms: Optional[str] = None,
    comment_status: Optional[str] = None,
    min_scan_count: Optional[int] = None,
    search: Optional[str] = None,
    scan_batch: Optional[str] = None,
    ai_ad_label: Optional[str] = None,
    min_confidence: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    specialty_match: Optional[str] = None,
    post_region: Optional[str] = None,
    work_scope: Optional[str] = Query(default="latest_legion", description="latest_legion|core|all_backlog"),
) -> Dict[str, int]:
    """[R3 Repository PoC] 필터 조건에 일치하는 viral_targets 총 개수.

    ViralTargetRepository로 위임 — 쿼리 빌더·연결 관리를 Repository가 담당.
    """
    try:
        from repositories import ViralTargetRepository
        repo = ViralTargetRepository(get_db_path())
        filters = {
            "status": status,
            "category": category,
            "date_filter": date_filter,
            "platforms": platforms,
            "comment_status": comment_status,
            "min_scan_count": min_scan_count,
            "search": search,
            "scan_batch": scan_batch,
            "ai_ad_label": ai_ad_label,
            "min_confidence": min_confidence,
            "specialty_match": specialty_match,
            "post_region": post_region,
        }
        filters = {k: v for k, v in filters.items() if v is not None}
        db = DatabaseManager()
        _apply_work_scope_filters(db.cursor, filters, work_scope)
        total = repo.count(filters)
        return {"total": total}
    except Exception as e:
        logger.error(f"[Viral Targets Count Error] {e}")
        raise HTTPException(status_code=500, detail=f"카운트 조회 실패: {e}")


@router.get("/categories")
async def get_viral_categories() -> List[Dict[str, Any]]:
    """
    카테고리별 바이럴 타겟 통계 (DB 집계 최적화)

    Returns:
        카테고리별 통계 (개수, 평균 점수, 우선순위)
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # DB에서 직접 카테고리별 집계 (기존: 10,000개 로드 후 Python 처리)
        cursor.execute("""
            SELECT
                COALESCE(category, '기타') as category,
                COUNT(*) as count,
                AVG(COALESCE(priority_score, 0)) as avg_score,
                MAX(COALESCE(priority_score, 0)) as max_score
            FROM viral_targets
            WHERE comment_status = 'pending'
            GROUP BY COALESCE(category, '기타')
        """)

        rows = cursor.fetchall()

        # 우선순위 계산 및 결과 생성
        result = []
        for row in rows:
            category, count, avg_score, max_score = row
            avg_score = avg_score or 0
            max_score = max_score or 0
            priority = max_score * 0.5 + avg_score * 0.3 + count * 0.2

            result.append({
                'category': category,
                'count': count,
                'avg_score': round(avg_score, 2),
                'max_score': max_score,
                'priority': round(priority, 2)
            })

        # 우선순위 순 정렬
        result.sort(key=lambda x: x['priority'], reverse=True)

        return result

    except Exception as e:
        logger.error(f"[Viral Categories Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"카테고리 조회 실패: {str(e)}")
    finally:
        if conn:
            conn.close()

@router.get("/comment-styles")
async def get_comment_styles() -> Dict[str, Any]:
    """
    AI 댓글 생성 스타일 목록 조회

    Returns:
        사용 가능한 스타일 목록
    """
    try:
        from utils import ConfigManager
        cfg = ConfigManager()
        prompts = cfg.load_prompts()

        styles_config = prompts.get('viral_hunter', {}).get('comment_generation', {}).get('styles', {})

        styles = []
        for style_id, style_data in styles_config.items():
            styles.append({
                'id': style_id,
                'name': style_data.get('name', style_id),
                'icon': style_data.get('icon', '🤖'),
                'description': style_data.get('description', '')
            })

        # 기본 스타일이 없으면 추가
        if not styles:
            styles = [{
                'id': 'default',
                'name': '기본',
                'icon': '🤖',
                'description': '자연스럽고 도움이 되는 기본 스타일'
            }]

        return {
            'success': True,
            'styles': styles
        }

    except Exception as e:
        print(f"[Comment Styles Error] {str(e)}")
        # 에러 시 기본 스타일 반환
        return {
            'success': True,
            'styles': [{
                'id': 'default',
                'name': '기본',
                'icon': '🤖',
                'description': '자연스럽고 도움이 되는 기본 스타일'
            }]
        }


@router.post("/generate-comment")
async def generate_comment(request: CommentGenerateRequest) -> Dict[str, Any]:
    """
    AI 댓글 생성

    Args:
        request: 타겟 ID와 스타일

    Returns:
        생성된 댓글
    """
    try:
        hunter = get_viral_hunter()
        db = DatabaseManager()

        # 타겟 조회
        target_data = db.get_viral_target(request.target_id)

        if not target_data:
            raise HTTPException(status_code=404, detail="타겟을 찾을 수 없습니다")

        # ViralTarget 객체 생성
        target = ViralTarget(
            platform=target_data.get('platform', 'unknown'),
            url=target_data.get('url', ''),
            title=target_data.get('title', ''),
            content_preview=target_data.get('content_preview', ''),
            matched_keywords=target_data.get('matched_keywords', []),
            category=target_data.get('category', '기타'),
            priority_score=target_data.get('priority_score', 0)
        )

        # [D3] 댓글 생성을 threadpool로 offload하여 이벤트 루프 비블로킹
        loop = asyncio.get_event_loop()
        comment = await loop.run_in_executor(
            None, lambda: hunter.generator.generate(target, style=request.style)
        )

        if comment:
            # 생성된 댓글을 DB에 저장 (batch 엔드포인트와 동일하게)
            # 저장 실패해도 응답은 성공으로 — 사용자는 일단 받은 텍스트로 작업 가능
            import sqlite3
            conn = None
            try:
                conn = sqlite3.connect(db.db_path, timeout=30.0)
                cur = conn.cursor()
                cur.execute(
                    """
                    UPDATE viral_targets
                    SET generated_comment = ?,
                        comment_status = 'generated',
                        updated_at = datetime('now', 'localtime')
                    WHERE id = ?
                    """,
                    (comment, str(request.target_id)),
                )
                conn.commit()
            except Exception as persist_err:
                print(f"[generate_comment] DB persist 실패 (target_id={request.target_id}): {persist_err}")
            finally:
                if conn is not None:
                    conn.close()

            return {
                'success': True,
                'comment': comment,
                'target_id': request.target_id,
                'style': request.style
            }
        else:
            raise HTTPException(status_code=500, detail="댓글 생성 실패")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-comments-batch")
async def generate_comments_batch(request: BatchCommentRequest) -> Dict[str, Any]:
    """
    [Phase 5.1] AI 댓글 배치 생성

    여러 타겟에 대해 AI 댓글을 일괄 생성합니다.
    - 배치 크기 제한으로 API 부하 관리
    - 우선순위 기반 타겟 선택
    - 실패한 경우도 계속 처리

    Args:
        request: 배치 생성 설정

    Returns:
        생성 결과 및 통계
    """
    import sqlite3
    conn = None
    try:
        hunter = get_viral_hunter()
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        results = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'skipped': 0,
            'comments': [],
            'errors': []
        }

        # 타겟 목록 조회
        if request.target_ids:
            # 특정 ID 목록
            placeholders = ','.join(['?' for _ in request.target_ids])
            query = f"""
                SELECT id, platform, url, title, content_preview, category,
                       matched_keywords, priority_score
                FROM viral_targets
                WHERE id IN ({placeholders})
                  AND comment_status = 'pending'
            """
            cursor.execute(query, request.target_ids)
        else:
            # 자동 선택 (우선순위 기반)
            query = """
                SELECT id, platform, url, title, content_preview, category,
                       matched_keywords, priority_score
                FROM viral_targets
                WHERE comment_status = 'pending'
                  AND is_commentable = 1
            """
            params = []

            if request.category:
                query += " AND category = ?"
                params.append(request.category)

            # 정렬 기준
            if request.prioritize_by == 'freshness':
                query += " ORDER BY discovered_at DESC"
            elif request.prioritize_by == 'engagement':
                query += " ORDER BY like_count + comment_count DESC"
            else:
                query += " ORDER BY priority_score DESC"

            query += " LIMIT ?"
            params.append(request.batch_size)

            cursor.execute(query, params)

        targets = cursor.fetchall()
        results['total'] = len(targets)

        if not targets:
            return {
                'status': 'no_targets',
                'message': '생성할 타겟이 없습니다.',
                **results
            }

        # 각 타겟에 대해 댓글 생성
        for target_row in targets:
            target_data = dict(target_row)
            target_id = str(target_data['id'])

            try:
                # ViralTarget 객체 생성
                matched_keywords = target_data.get('matched_keywords', '')
                if isinstance(matched_keywords, str):
                    matched_keywords = matched_keywords.split(',') if matched_keywords else []

                target = ViralTarget(
                    platform=target_data.get('platform', 'unknown'),
                    url=target_data.get('url', ''),
                    title=target_data.get('title', ''),
                    content_preview=target_data.get('content_preview', ''),
                    matched_keywords=matched_keywords,
                    category=target_data.get('category', '기타'),
                    priority_score=target_data.get('priority_score', 0)
                )

                # 댓글 생성
                comment = hunter.generator.generate(target)

                if comment:
                    # DB 업데이트
                    cursor.execute("""
                        UPDATE viral_targets
                        SET generated_comment = ?,
                            comment_status = 'generated',
                            updated_at = datetime('now', 'localtime')
                        WHERE id = ?
                    """, (comment, target_id))

                    results['success'] += 1
                    results['comments'].append({
                        'target_id': target_id,
                        'title': target_data.get('title', '')[:50],
                        'comment': comment[:200] + '...' if len(comment) > 200 else comment,
                        'status': 'success'
                    })
                else:
                    results['skipped'] += 1
                    results['comments'].append({
                        'target_id': target_id,
                        'title': target_data.get('title', '')[:50],
                        'comment': None,
                        'status': 'skipped',
                        'reason': '댓글 생성 실패'
                    })

            except Exception as e:
                results['failed'] += 1
                results['errors'].append({
                    'target_id': target_id,
                    'error': str(e)
                })

        conn.commit()

        return {
            'status': 'success',
            'message': f'{results["success"]}개 댓글 생성 완료',
            **results
        }

    except Exception as e:
        print(f"[Batch Comment Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"배치 댓글 생성 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


@router.post("/verify-target")
async def verify_target(request: VerifyTargetRequest, use_selenium: bool = False) -> Dict[str, Any]:
    """
    [Phase 4.0] 타겟 URL 댓글 가능 여부 확인

    실제로 URL에 접속하여 페이지 존재 여부와 댓글 가능 여부를 확인합니다.

    Args:
        request: 타겟 ID
        use_selenium: Selenium 사용 여부 (정확도 높음, 느림)

    Returns:
        검증 결과 (accessible, commentable, reason, verified_at)
    """
    import sqlite3
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 타겟 조회
        cursor.execute("""
            SELECT id, platform, url, title
            FROM viral_targets
            WHERE id = ?
        """, (request.target_id,))
        target = cursor.fetchone()

        if not target:
            raise HTTPException(status_code=404, detail="타겟을 찾을 수 없습니다")

        # URL 검증 (Selenium 또는 비동기 방식)
        if use_selenium:
            try:
                from services.comment_verifier import verify_comment_availability
                result = verify_comment_availability(target['url'], target['platform'])
            except ImportError:
                logger.warning("Selenium 검증 모듈 로드 실패, 비동기 방식 사용")
                result = await _verify_url_commentable_async(target['url'], target['platform'])
        else:
            # [성능 개선] 비동기 HTTP 호출 사용 (이벤트 루프 블로킹 방지)
            result = await _verify_url_commentable_async(target['url'], target['platform'])

        # 결과를 DB에 저장
        cursor.execute("""
            UPDATE viral_targets
            SET is_commentable = ?,
                last_scanned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (1 if result['commentable'] else 0, request.target_id))
        conn.commit()

        return {
            'success': True,
            'target_id': request.target_id,
            'title': target['title'],
            'url': target['url'],
            'verification': result,
            'method': 'selenium' if use_selenium else 'basic'
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Verify Target Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"검증 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


@router.post("/verify-target-selenium")
async def verify_target_selenium(request: VerifyTargetRequest) -> Dict[str, Any]:
    """
    [Phase 4.1] Selenium 기반 정확한 댓글 가능 여부 확인

    [안정성 개선] 비동기 래퍼 사용으로 서버 블로킹 방지

    JavaScript 렌더링을 통해 실제 댓글 입력창/버튼을 확인합니다.
    - 네이버 카페: iframe 내 댓글 영역 확인
    - 네이버 블로그: mainFrame 내 댓글 영역 확인
    - 지식인: 답변 가능 여부 및 마감 여부 확인
    - YouTube: 댓글 비활성화 여부 확인

    Args:
        request: 타겟 ID

    Returns:
        상세 검증 결과
    """
    import sqlite3
    conn = None
    try:
        from services.comment_verifier import verify_url_async

        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 타겟 조회
        cursor.execute("""
            SELECT id, platform, url, title
            FROM viral_targets
            WHERE id = ?
        """, (request.target_id,))
        target = cursor.fetchone()

        if not target:
            raise HTTPException(status_code=404, detail="타겟을 찾을 수 없습니다")

        # [안정성 개선] 비동기 Selenium 검증
        result = await verify_url_async(target['url'], target['platform'])

        # 결과를 DB에 저장
        cursor.execute("""
            UPDATE viral_targets
            SET is_commentable = ?,
                last_scanned_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (1 if result['commentable'] else 0, request.target_id))
        conn.commit()

        return {
            'success': True,
            'target_id': request.target_id,
            'title': target['title'],
            'url': target['url'],
            'platform': target['platform'],
            'verification': result,
            'method': 'selenium_async'
        }

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Selenium 모듈 로드 실패: {str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Selenium Verify Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"Selenium 검증 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


@router.post("/verify-batch-selenium")
async def verify_batch_selenium(
    category: Optional[str] = None,
    platform: Optional[str] = None,
    limit: int = Query(10, ge=1, le=50)
) -> Dict[str, Any]:
    """
    [Phase 4.1] Selenium 기반 일괄 댓글 가능 여부 확인

    [안정성 개선] 비동기 래퍼 사용으로 서버 블로킹 방지
    동시 검증 수를 제한하여 리소스 문제 방지 (max_concurrent=3)

    Args:
        category: 카테고리 필터
        platform: 플랫폼 필터
        limit: 최대 검증 수 (기본 10, 최대 50)

    Returns:
        일괄 검증 결과
    """
    import sqlite3
    conn = None
    try:
        from services.comment_verifier import verify_batch_async

        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 검증 대상 조회
        query = """
            SELECT id, platform, url, title
            FROM viral_targets
            WHERE comment_status = 'pending'
        """
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)
        if platform:
            query += " AND platform = ?"
            params.append(platform)

        query += " ORDER BY priority_score DESC LIMIT ?"
        params.append(limit)

        cursor.execute(query, params)
        targets = [dict(row) for row in cursor.fetchall()]

        if not targets:
            return {
                'success': True,
                'message': '검증할 타겟이 없습니다',
                'verified': 0,
                'results': []
            }

        # [안정성 개선] 비동기 일괄 검증 (동시 3개)
        verification_results = await verify_batch_async(targets, max_concurrent=3)

        # 결과 처리 및 DB 업데이트
        results = []
        commentable_count = 0
        not_commentable_count = 0

        for vr in verification_results:
            result = vr['result']

            # DB 업데이트
            cursor.execute("""
                UPDATE viral_targets
                SET is_commentable = ?,
                    last_scanned_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (1 if result['commentable'] else 0, vr['target_id']))

            if result['commentable']:
                commentable_count += 1
            else:
                not_commentable_count += 1

            # 타겟 정보 찾기
            target_info = next((t for t in targets if t['id'] == vr['target_id']), {})

            results.append({
                'target_id': vr['target_id'],
                'title': target_info.get('title', '')[:50],
                'platform': vr['platform'],
                'commentable': result['commentable'],
                'reason': result.get('reason', '')
            })

        conn.commit()

        return {
            'success': True,
            'message': f'{len(results)}개 검증 완료',
            'verified': len(results),
            'commentable': commentable_count,
            'not_commentable': not_commentable_count,
            'results': results,
            'method': 'selenium_async'
        }

    except ImportError as e:
        raise HTTPException(status_code=500, detail=f"Selenium 모듈 로드 실패: {str(e)}")
    except Exception as e:
        print(f"[Batch Selenium Verify Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"일괄 검증 실패: {str(e)}")
    finally:
        if conn:
            conn.close()


_verify_jobs: Dict[str, Dict[str, Any]] = {}
_verify_jobs_lock = threading.Lock()


def _new_verify_job() -> str:
    import uuid
    job_id = uuid.uuid4().hex[:12]
    with _verify_jobs_lock:
        _verify_jobs[job_id] = {
            "status": "queued",
            "progress": 0,
            "total": 0,
            "commentable": 0,
            "not_commentable": 0,
            "failed": 0,
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
        }
    return job_id


async def _run_verify_job(job_id: str, category: Optional[str], limit: int) -> None:
    """[D5] 백그라운드에서 verify-batch 실행 + 진행률 업데이트."""
    try:
        with _verify_jobs_lock:
            _verify_jobs[job_id]["status"] = "running"
        # 기존 동기 로직 재사용 (inline 호출)
        result = await verify_batch(category=category, limit=limit, _internal=True)
        with _verify_jobs_lock:
            _verify_jobs[job_id].update({
                "status": "done",
                "total": result.get("total", 0),
                "commentable": result.get("commentable", 0),
                "not_commentable": result.get("not_commentable", 0),
                "failed": result.get("failed", 0),
                "progress": 100,
                "finished_at": datetime.now().isoformat(),
            })
    except Exception as e:
        with _verify_jobs_lock:
            _verify_jobs[job_id].update({
                "status": "error",
                "error": str(e),
                "finished_at": datetime.now().isoformat(),
            })


@router.post("/bulk-action-by-filter")
async def bulk_action_by_filter(req: BulkActionByFilterRequest) -> Dict[str, Any]:
    """[F3] 필터 조건에 매칭되는 모든 타겟에 일괄 액션 (skip/approve/delete/posted).

    WHERE 절을 재사용하여 단일 UPDATE로 처리. 안전을 위해 max_affected 상한 적용.
    - dry_run=true: 매칭 개수만 반환, 변경 없음
    """
    db_path = get_db_path()
    conn = None
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # WHERE 절 구성 (GET /targets/count와 동일 로직)
        where = "WHERE 1=1"
        params: List[Any] = []
        effective_status = req.comment_status if req.comment_status else req.status
        if effective_status:
            where += " AND comment_status = ?"
            params.append(effective_status)
        if req.platforms:
            placeholders = ','.join(['?'] * len(req.platforms))
            where += f" AND platform IN ({placeholders})"
            params.extend(req.platforms)
        if req.category:
            where += " AND category = ?"
            params.append(req.category)
        if req.scan_batch:
            where += " AND strftime('%Y-%m-%d %H', discovered_at) = ?"
            params.append(req.scan_batch)
        elif req.date_filter:
            if req.date_filter == "오늘":
                where += " AND DATE(discovered_at) = DATE('now', 'localtime')"
            elif req.date_filter == "최근 7일":
                where += " AND discovered_at >= datetime('now', '-7 days')"
            elif req.date_filter == "최근 30일":
                where += " AND discovered_at >= datetime('now', '-30 days')"
        if req.min_scan_count and req.min_scan_count > 0:
            where += " AND scan_count >= ?"
            params.append(req.min_scan_count)
        if req.search:
            where += " AND (title LIKE ? OR content_preview LIKE ?)"
            pattern = f"%{req.search}%"
            params.extend([pattern, pattern])
        # AI 분류 필터 — 골든 큐 일괄 작업 안전 (필터 좁힘으로 max_affected 게이트 통과 용이)
        if req.ai_ad_label:
            labels = [l.strip() for l in req.ai_ad_label.split(',') if l.strip()] if ',' in req.ai_ad_label else [req.ai_ad_label]
            placeholders = ','.join(['?'] * len(labels))
            where += f" AND ai_ad_label IN ({placeholders})"
            params.extend(labels)
        if req.specialty_match:
            tiers = [t.strip() for t in req.specialty_match.split(',') if t.strip()] if ',' in req.specialty_match else [req.specialty_match]
            placeholders = ','.join(['?'] * len(tiers))
            where += f" AND specialty_match IN ({placeholders})"
            params.extend(tiers)
        if req.post_region:
            regions = [r.strip() for r in req.post_region.split(',') if r.strip()] if ',' in req.post_region else [req.post_region]
            placeholders = ','.join(['?'] * len(regions))
            where += f" AND post_region IN ({placeholders})"
            params.extend(regions)
        if req.min_confidence is not None:
            where += " AND ai_ad_confidence >= ?"
            params.append(req.min_confidence)

        # 매칭 개수 확인
        cursor.execute(f"SELECT COUNT(*) FROM viral_targets {where}", params)
        matched = cursor.fetchone()[0]

        if matched > req.max_affected:
            raise HTTPException(
                status_code=400,
                detail=f"매칭 {matched}건이 max_affected({req.max_affected})를 초과합니다. 필터를 좁히거나 max_affected를 조정하세요."
            )

        if req.dry_run:
            return {"matched": matched, "updated": 0, "dry_run": True}

        # 액션에 따른 comment_status 매핑
        action_map = {
            'approve': 'posted',
            'skip': 'skipped',
            'delete': 'deleted',
            'pending': 'pending',
            'generated': 'generated',
            'posted': 'posted',
            'skipped': 'skipped',
        }
        new_status = action_map.get(req.action)
        if not new_status:
            raise HTTPException(status_code=400, detail=f"지원하지 않는 action: {req.action}")

        # skip 학습: 사유 일괄 기록 (샘플 최대 100건, 너무 많으면 학습 품질 낮음)
        if req.action == 'skip' and req.skip_reason:
            cursor.execute(
                f"SELECT id, url, author FROM viral_targets {where} LIMIT 100",
                params,
            )
            sample_rows = cursor.fetchall()
            from urllib.parse import urlparse
            now = datetime.now().isoformat()
            for (tid, url, author) in sample_rows:
                cursor.execute(
                    "INSERT INTO viral_skip_reasons(target_id, reason_tag, note) VALUES(?,?,?)",
                    (tid, req.skip_reason, "(bulk)"),
                )
                domain = urlparse(url or '').netloc.replace('www.', '')
                if domain:
                    cursor.execute(
                        """
                        INSERT INTO viral_adaptive_penalties(key_type, key_value, skip_count, last_updated)
                        VALUES('domain', ?, 1, ?)
                        ON CONFLICT(key_type, key_value) DO UPDATE
                        SET skip_count = skip_count + 1, last_updated = excluded.last_updated
                        """,
                        (domain, now),
                    )
                if author:
                    cursor.execute(
                        """
                        INSERT INTO viral_adaptive_penalties(key_type, key_value, skip_count, last_updated)
                        VALUES('author', ?, 1, ?)
                        ON CONFLICT(key_type, key_value) DO UPDATE
                        SET skip_count = skip_count + 1, last_updated = excluded.last_updated
                        """,
                        (author, now),
                    )

        # 단일 UPDATE로 일괄 처리
        cursor.execute(
            f"UPDATE viral_targets SET comment_status = ? {where}",
            [new_status] + params,
        )
        updated = cursor.rowcount
        conn.commit()
        return {"matched": matched, "updated": updated, "dry_run": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[bulk-action-by-filter] {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/verify-batch/start")
async def verify_batch_start(
    background: BackgroundTasks,
    category: Optional[str] = None,
    limit: int = 20,
) -> Dict[str, str]:
    """[D5] verify-batch를 백그라운드로 실행하고 job_id 즉시 반환."""
    job_id = _new_verify_job()
    background.add_task(_run_verify_job, job_id, category, limit)
    return {"job_id": job_id, "status": "queued"}


@router.get("/verify-batch/status/{job_id}")
async def verify_batch_status(job_id: str) -> Dict[str, Any]:
    with _verify_jobs_lock:
        job = _verify_jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return job


@router.post("/verify-batch")
async def verify_batch(category: Optional[str] = None, limit: int = 20, _internal: bool = False) -> Dict[str, Any]:
    """
    [Phase 4.0 + P2-3] 여러 타겟의 댓글 가능 여부 비동기 일괄 확인

    pending 상태의 타겟들을 대상으로 일괄 검증합니다.
    - 비동기 처리로 성능 개선
    - 동시 요청 수 제한 (5개)
    - 검증 결과 1시간 캐싱

    Args:
        category: 특정 카테고리만 검증 (선택)
        limit: 최대 검증 수 (기본 20개)

    Returns:
        검증 결과 요약
    """
    try:
        db = DatabaseManager()
        import sqlite3

        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 검증할 타겟 조회 (최근 스캔되지 않은 pending 타겟)
        query = """
            SELECT id, platform, url, title
            FROM viral_targets
            WHERE comment_status = 'pending'
        """
        params = []

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY last_scanned_at ASC NULLS FIRST, discovered_at DESC"

        # limit=0이면 전체 조회, 아니면 제한
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, params)
        targets = cursor.fetchall()

        results = {
            'total': len(targets),
            'accessible': 0,
            'commentable': 0,
            'not_commentable': 0,
            'failed': 0,
            'cached': 0,
            'details': []
        }

        # [P2-3] 비동기 처리 (aiohttp 사용 가능한 경우)
        if AIOHTTP_AVAILABLE and len(targets) > 1:
            # 동시 요청 수 제한 (5개)
            semaphore = asyncio.Semaphore(5)

            async with aiohttp.ClientSession() as session:
                # 모든 타겟을 병렬로 검증
                tasks = [
                    _verify_url_async(session, target['url'], target['platform'], semaphore)
                    for target in targets
                ]
                verifications = await asyncio.gather(*tasks, return_exceptions=True)

            # 결과 처리
            for target, verification in zip(targets, verifications):
                if isinstance(verification, Exception):
                    verification = {
                        'accessible': False,
                        'commentable': False,
                        'reason': f'오류: {str(verification)}',
                        'from_cache': False
                    }

                if verification.get('from_cache'):
                    results['cached'] += 1

                if verification['accessible']:
                    results['accessible'] += 1
                    if verification['commentable']:
                        results['commentable'] += 1
                    else:
                        results['not_commentable'] += 1
                else:
                    results['failed'] += 1

                # DB 업데이트
                cursor.execute("""
                    UPDATE viral_targets
                    SET is_commentable = ?,
                        last_scanned_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (1 if verification['commentable'] else 0, target['id']))

                results['details'].append({
                    'target_id': target['id'],
                    'title': target['title'][:30] + '...' if len(target['title']) > 30 else target['title'],
                    'accessible': verification['accessible'],
                    'commentable': verification['commentable'],
                    'reason': verification['reason'],
                    'cached': verification.get('from_cache', False)
                })

        else:
            # 폴백: httpx 비동기 방식 (aiohttp 없거나 단일 타겟)
            for target in targets:
                # 캐시 확인
                cached = _get_cached_verification(target['url'])
                if cached:
                    verification = cached.copy()
                    verification['from_cache'] = True
                    results['cached'] += 1
                else:
                    # [성능 개선] 비동기 HTTP 호출 사용
                    verification = await _verify_url_commentable_async(target['url'], target['platform'])
                    verification['from_cache'] = False
                    _set_cache_verification(target['url'], verification)

                if verification['accessible']:
                    results['accessible'] += 1
                    if verification['commentable']:
                        results['commentable'] += 1
                    else:
                        results['not_commentable'] += 1
                else:
                    results['failed'] += 1

                # DB 업데이트
                cursor.execute("""
                    UPDATE viral_targets
                    SET is_commentable = ?,
                        last_scanned_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                """, (1 if verification['commentable'] else 0, target['id']))

                results['details'].append({
                    'target_id': target['id'],
                    'title': target['title'][:30] + '...' if len(target['title']) > 30 else target['title'],
                    'accessible': verification['accessible'],
                    'commentable': verification['commentable'],
                    'reason': verification['reason'],
                    'cached': verification.get('from_cache', False)
                })

        conn.commit()
        conn.close()

        return {
            'success': True,
            'async_mode': AIOHTTP_AVAILABLE and len(targets) > 1,
            **results
        }

    except Exception as e:
        print(f"[Verify Batch Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"일괄 검증 실패: {str(e)}")


@router.post("/action")
async def target_action(request: TargetActionRequest) -> Dict[str, Any]:
    """
    타겟 액션 (승인/건너뛰기/삭제/reopen)

    [AA4] idempotency_key가 제공되고 최근 10분 내 처리된 키면 재적용 스킵.
    오프라인 큐 재전송 시 중복 방지.

    Args:
        request: 타겟 ID 및 액션

    Returns:
        상태 메시지
    """
    # [AA4] Idempotency 체크 — 프로세스 로컬 TTL 캐시
    if request.idempotency_key:
        now = time.time()
        # 오래된 항목 청소 (10분 TTL)
        expired = [k for k, ts in _idempotency_cache.items() if now - ts > 600]
        for k in expired:
            _idempotency_cache.pop(k, None)
        if request.idempotency_key in _idempotency_cache:
            return {
                'status': 'success',
                'message': '중복 요청 무시됨 (idempotency)',
                'lead_created': False,
                'deduplicated': True,
            }
        _idempotency_cache[request.idempotency_key] = now

    try:
        hunter = get_viral_hunter()

        lead_created = False
        audit_conn = sqlite3.connect(hunter.db.db_path)
        before_snapshot = _fetch_target_snapshot(audit_conn.cursor(), request.target_id)

        if request.action == "approve":
            hunter.db.update_viral_target(request.target_id, {
                'generated_comment': request.comment,
                'comment_status': 'posted'
            })

            # [Phase 4.0] 바이럴→리드 자동 파이프라인
            # 승인된 바이럴 타겟을 자동으로 리드(mentions)로 등록
            lead_created = _create_lead_from_viral(hunter.db, request.target_id)
            message = "타겟 승인 완료"

        elif request.action == "skip":
            hunter.db.update_viral_target(request.target_id, {
                'comment_status': 'skipped'
            })
            # [D2] skip 사유 학습 — 도메인/작성자 감점 누적
            if request.skip_reason:
                _record_skip_learning(
                    hunter.db,
                    request.target_id,
                    request.skip_reason,
                    request.skip_note,
                )
            message = "타겟 건너뛰기 완료"

        elif request.action == "delete":
            hunter.db.update_viral_target(request.target_id, {
                'comment_status': 'deleted'
            })
            message = "타겟 삭제 완료"

        elif request.action == "reopen":
            # [U1] Undo — 처리된 타겟을 대기로 복구 (생성된 댓글은 보존)
            # [EE1] Lead 정책: 이미 생성된 lead는 유지 (mentions.url unique 체크로 중복 방지).
            #   - reopen → 재승인 시 lead 재생성되지 않음 (의도된 동작).
            #   - 수정된 comment 내용은 viral_targets에만 보존되고 lead에는 반영되지 않음.
            #   - 사용자에게는 "복구" 의미만 있으며 lead 파이프라인에는 영향 없음.
            hunter.db.update_viral_target(request.target_id, {
                'comment_status': 'pending'
            })
            message = "타겟 복구 완료"

        else:
            raise HTTPException(status_code=400, detail="잘못된 액션입니다")

        try:
            after_snapshot = _fetch_target_snapshot(audit_conn.cursor(), request.target_id)
            _write_audit_event(
                audit_conn,
                action=f"viral_target.{request.action}",
                entity_type="viral_target",
                entity_id=request.target_id,
                before=before_snapshot,
                after=after_snapshot,
                metadata={
                    "lead_created": lead_created,
                    "skip_reason": request.skip_reason,
                    "skip_note": request.skip_note,
                    "has_comment": bool(request.comment),
                },
            )
        except Exception as audit_error:
            logger.warning(f"[viral audit] action log failed: {audit_error}")
        finally:
            audit_conn.close()

        return {
            'status': 'success',
            'message': message,
            'lead_created': lead_created
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/feedback")
async def record_target_feedback(request: TargetFeedbackRequest) -> Dict[str, Any]:
    """Record staff quality feedback for a generated viral comment."""
    conn = None
    try:
        hunter = get_viral_hunter()
        conn = sqlite3.connect(hunter.db.db_path)
        _ensure_quality_ops_tables(conn)
        cursor = conn.cursor()
        before_snapshot = _fetch_target_snapshot(cursor, request.target_id)
        if not before_snapshot:
            raise HTTPException(status_code=404, detail="target not found")

        cursor.execute(
            """
            INSERT INTO viral_target_feedback (
                target_id, rating, reason, corrected_comment, staff_user
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (
                request.target_id,
                request.rating,
                request.reason,
                request.corrected_comment,
                request.staff_user or "staff",
            ),
        )
        conn.commit()
        if request.corrected_comment:
            cursor.execute(
                """
                UPDATE viral_targets
                SET generated_comment = ?, comment_status = 'generated'
                WHERE id = ?
                """,
                (request.corrected_comment, request.target_id),
            )
            conn.commit()

        after_snapshot = _fetch_target_snapshot(cursor, request.target_id)
        _write_audit_event(
            conn,
            action="viral_target.feedback",
            entity_type="viral_target",
            entity_id=request.target_id,
            before=before_snapshot,
            after=after_snapshot,
            metadata={
                "rating": request.rating,
                "reason": request.reason,
                "has_corrected_comment": bool(request.corrected_comment),
            },
            actor=request.staff_user or "staff",
        )
        return {"status": "success", "message": "feedback recorded"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            conn.close()


@router.get("/quality-summary")
async def get_quality_summary(days: int = Query(default=14, ge=1, le=90)) -> Dict[str, Any]:
    """Summarize staff feedback and action quality for the recent viral workflow."""
    conn = None
    try:
        hunter = get_viral_hunter()
        conn = sqlite3.connect(hunter.db.db_path)
        conn.row_factory = sqlite3.Row
        _ensure_quality_ops_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT rating, COUNT(*) AS count
            FROM viral_target_feedback
            WHERE created_at >= datetime('now', ?)
            GROUP BY rating
            """,
            (f"-{days} days",),
        )
        feedback_by_rating = {row["rating"]: row["count"] for row in cursor.fetchall()}
        total_feedback = sum(feedback_by_rating.values())
        good = feedback_by_rating.get("good", 0)
        needs_edit = feedback_by_rating.get("needs_edit", 0)
        bad = feedback_by_rating.get("bad", 0)

        cursor.execute(
            """
            SELECT vt.category, f.rating, COUNT(*) AS count
            FROM viral_target_feedback f
            JOIN viral_targets vt ON vt.id = f.target_id
            WHERE f.created_at >= datetime('now', ?)
            GROUP BY vt.category, f.rating
            ORDER BY count DESC
            LIMIT 50
            """,
            (f"-{days} days",),
        )
        category_rows = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            """
            SELECT action, COUNT(*) AS count
            FROM audit_events
            WHERE entity_type = 'viral_target'
              AND created_at >= datetime('now', ?)
            GROUP BY action
            """,
            (f"-{days} days",),
        )
        actions = {row["action"]: row["count"] for row in cursor.fetchall()}

        cursor.execute(
            """
            SELECT id, actor, action, entity_id, metadata_json, created_at
            FROM audit_events
            WHERE entity_type = 'viral_target'
            ORDER BY created_at DESC
            LIMIT 20
            """
        )
        recent_audit = []
        for row in cursor.fetchall():
            item = dict(row)
            try:
                item["metadata"] = json.loads(item.pop("metadata_json") or "{}")
            except Exception:
                item["metadata"] = {}
            recent_audit.append(item)

        acceptance_rate = round((good / total_feedback) * 100, 1) if total_feedback else None
        edit_rate = round(((needs_edit + bad) / total_feedback) * 100, 1) if total_feedback else None
        return {
            "days": days,
            "feedback_total": total_feedback,
            "feedback_by_rating": feedback_by_rating,
            "acceptance_rate": acceptance_rate,
            "edit_rate": edit_rate,
            "category_feedback": category_rows,
            "actions": actions,
            "recent_audit": recent_audit,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            conn.close()


@router.get("/ops-status")
async def get_viral_ops_status() -> Dict[str, Any]:
    """Expose the minimum operating checks staff need without opening restore endpoints."""
    conn = None
    try:
        hunter = get_viral_hunter()
        conn = sqlite3.connect(hunter.db.db_path)
        _ensure_quality_ops_tables(conn)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_events")
        audit_events = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM viral_target_feedback")
        feedback_events = cursor.fetchone()[0]

        backup_status = {}
        try:
            from db_backup import DatabaseBackup
            backup = DatabaseBackup()
            backup_status = backup.get_backup_status()
            if os.path.exists(backup.db_path):
                backup_status["db_size_mb"] = round(os.path.getsize(backup.db_path) / (1024 * 1024), 2)
            latest = backup_status.get("latest_backup")
            if latest:
                last_backup_time = datetime.fromisoformat(latest["created"])
                backup_status["days_since_backup"] = (datetime.now() - last_backup_time).days
            else:
                backup_status["days_since_backup"] = None
        except Exception as backup_error:
            backup_status = {"error": str(backup_error)}

        return {
            "audit_events": audit_events,
            "feedback_events": feedback_events,
            "api_auth_enabled": os.getenv("DISABLE_API_AUTH", "false").lower() != "true",
            "backup": backup_status,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn is not None:
            conn.close()


ScanPlatform = Literal["cafe", "blog", "kin", "place", "karrot", "youtube", "instagram", "tiktok"]


class ScanConfig(BaseModel):
    """스캔 설정"""
    platforms: List[ScanPlatform] = ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok']
    max_results: int = Field(500, ge=0, le=5000)  # 0 = 무제한, 최대 5000
    use_latest_legion: bool = True
    fresh: bool = True


@router.post("/scan")
async def scan_viral_targets(
    background_tasks: BackgroundTasks,
    config: Optional[ScanConfig] = None
) -> Dict[str, Any]:
    """
    바이럴 타겟 스캔 실행 (백그라운드)

    8개 플랫폼 지원:
    - cafe: 네이버 카페
    - blog: 네이버 블로그
    - kin: 지식iN
    - place: 네이버 플레이스 리뷰
    - karrot: 당근마켓
    - youtube: 유튜브
    - instagram: 인스타그램
    - tiktok: 틱톡

    Args:
        config: 스캔 설정 (platforms, max_results)

    Returns:
        상태 메시지
    """
    try:
        if config is None:
            config = ScanConfig()

        # 네이버 플랫폼 (cafe, blog, kin)
        naver_platforms = [p for p in config.platforms if p in ['cafe', 'blog', 'kin']]
        # 멀티 플랫폼 (place, karrot, youtube, instagram, tiktok)
        multi_platforms = [p for p in config.platforms if p in ['place', 'karrot', 'youtube', 'instagram', 'tiktok']]

        commands = []

        # 1. 네이버 통합 검색 (viral_hunter.py)
        if naver_platforms:
            script_path = os.path.join(parent_dir, "viral_hunter.py")
            if os.path.exists(script_path):
                cmd = ["python", script_path, "--scan"]
                if config.fresh:
                    cmd.append("--fresh")
                if not config.use_latest_legion:
                    cmd.append("--legacy-keywords")
                if config.max_results > 0:
                    cmd.extend(["--limit-keywords", str(min(config.max_results, 5000))])
                commands.append(cmd)

        # 2. 멀티 플랫폼 (viral_hunter_multi_platform.py)
        if multi_platforms:
            multi_script = os.path.join(parent_dir, "viral_hunter_multi_platform.py")
            if os.path.exists(multi_script):
                cmd = ["python", multi_script, "--platforms", ",".join(multi_platforms)]
                if config.max_results > 0:
                    cmd.extend(["--max-results", str(config.max_results)])
                commands.append(cmd)

        if not commands:
            raise HTTPException(status_code=400, detail="실행할 스캔 스크립트가 없습니다")

        # 백그라운드에서 모든 스크립트 실행
        for cmd in commands:
            background_tasks.add_task(subprocess.run, cmd, cwd=parent_dir)

        return {
            'status': 'started',
            'message': f'Viral Hunter 스캔 시작 (플랫폼: {len(config.platforms)}개, 최대: {config.max_results if config.max_results > 0 else "무제한"})',
            'platforms': config.platforms,
            'max_results': config.max_results,
            'scripts': len(commands)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================
# 댓글 템플릿 API
# =====================================

EngagementSignal = Literal["any", "seeking_info", "ready_to_act", "passive"]
PrioritySegment = Literal["vip", "high", "medium", "low", "all"]


# [U1] TemplateCreate, TemplateRecommendRequest 및 /templates/* 엔드포인트는
# routers/viral_templates.py로 완전 분리됨.


# [U1] /templates/* 5개 엔드포인트는 routers/viral_templates.py로 완전 분리됨.


# =====================================
# [Phase 4.0] UTM 매개변수 API
# =====================================

# [T2] UTM 관련 엔드포인트는 routers/viral_utm.py로 완전 분리됨.


# ============================================
# [Phase 3.1] 크로스 플랫폼 중복 제거 API
# ============================================

@router.post("/deduplicate")
async def deduplicate_targets(
    similarity_threshold: float = Query(default=0.7, ge=0.0, le=1.0),
    limit: int = Query(default=200, ge=1, le=500, description="처리할 최대 타겟 수")
) -> Dict[str, Any]:
    """
    [Phase 3.1] 바이럴 타겟 중복 제거

    동일/유사 콘텐츠를 감지하고 대표 리드만 선택합니다.

    Args:
        similarity_threshold: 유사도 임계값 (0.0~1.0, 기본 0.7)
        limit: 처리할 최대 타겟 수 (기본 500)

    Returns:
        중복 제거 결과 및 통계
    """
    try:
        # 서비스 임포트
        services_path = os.path.join(parent_dir, 'services')
        if services_path not in sys.path:
            sys.path.insert(0, services_path)

        from deduplicator import get_deduplicator

        # DB에서 타겟 조회
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                id, platform, url, title, content_preview,
                matched_keywords, category, is_commentable,
                priority_score, author, scraped_at
            FROM viral_targets
            WHERE is_commentable = 1
            ORDER BY scraped_at DESC
            LIMIT ?
        """, (limit,))

        targets = []
        for row in cursor.fetchall():
            target = dict(row)
            if target.get('matched_keywords'):
                target['matched_keywords'] = target['matched_keywords'].split(',')
            targets.append(target)

        conn.close()

        if not targets:
            return {
                'status': 'no_data',
                'message': '처리할 타겟이 없습니다.',
                'original_count': 0,
                'deduplicated_count': 0,
                'removed_count': 0
            }

        # 중복 제거 실행
        deduplicator = get_deduplicator(similarity_threshold)
        deduped = deduplicator.deduplicate(targets)

        # 결과 변환
        results = []
        for item in deduped:
            lead = item.lead.copy()
            lead['related_platforms'] = item.related_platforms
            lead['duplicate_count'] = item.duplicate_count
            lead['total_reach'] = item.total_reach
            results.append(lead)

        return {
            'status': 'success',
            'original_count': len(targets),
            'deduplicated_count': len(results),
            'removed_count': len(targets) - len(results),
            'removal_rate': round((len(targets) - len(results)) / len(targets) * 100, 1) if targets else 0,
            'targets': results[:100],  # 상위 100개만 반환
            'stats': deduplicator.get_stats()
        }

    except ImportError as e:
        print(f"[deduplicate] Import error: {e}")
        return {
            'status': 'error',
            'message': 'Deduplicator service not available',
            'original_count': 0,
            'deduplicated_count': 0
        }
    except Exception as e:
        print(f"[deduplicate Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))



# [U2] /comments/* 4개 엔드포인트 + PostedComment·CommentEngagement 모델 +
# _ensure_posted_comments_table 함수는 routers/viral_comments.py로 완전 분리됨.

# [Decision Intelligence] 컨텍스트 리치 뷰
# ===========================================================================

@router.get("/target/{target_id}/context")
async def get_target_context(target_id: str) -> Dict[str, Any]:
    """
    타겟의 컨텍스트 정보 조회

    의사결정에 필요한 심층 정보를 제공합니다:
    - 유사 타겟 추천
    - 키워드 연관 분석
    - 경쟁사 언급 분석
    - 타겟 히스토리

    Args:
        target_id: 타겟 ID

    Returns:
        - similar_targets: 유사한 타겟 목록
        - keyword_analysis: 매칭 키워드의 등급 및 검색량
        - competitor_mentions: 경쟁사 언급 분석
        - target_history: 타겟 이력
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 타겟 기본 정보 조회
        cursor.execute("""
            SELECT id, title, url, platform, content_preview, matched_keywords,
                   category, priority_score, comment_status, scan_count,
                   discovered_at, last_scanned_at
            FROM viral_targets
            WHERE id = ?
        """, (target_id,))
        target_row = cursor.fetchone()

        if not target_row:
            raise HTTPException(status_code=404, detail="타겟을 찾을 수 없습니다")

        target = dict(target_row)

        # matched_keywords 파싱
        matched_keywords = []
        if target.get('matched_keywords'):
            try:
                matched_keywords = json.loads(target['matched_keywords'])
            except (json.JSONDecodeError, TypeError):
                matched_keywords = target['matched_keywords'].split(',') if target['matched_keywords'] else []

        result = {
            "target_id": target_id,
            "title": target.get('title'),
            "platform": target.get('platform'),
            "similar_targets": [],
            "keyword_analysis": [],
            "competitor_mentions": [],
            "target_history": [],
            "insights": []
        }

        # 1. 유사 타겟 조회 (같은 키워드 또는 플랫폼)
        # [Phase 2 최적화] LIKE '%keyword%' → 정규화 테이블 JOIN으로 변경 (인덱스 활용)
        if matched_keywords:
            search_kws = matched_keywords[:3]
            keyword_placeholders = ','.join(['?' for _ in search_kws])
            cursor.execute(f"""
                SELECT DISTINCT vt.id, vt.title, vt.platform, vt.priority_score, vt.comment_status, vt.discovered_at
                FROM viral_targets vt
                INNER JOIN viral_target_keywords vtk ON CAST(vt.id AS TEXT) = vtk.viral_target_id
                WHERE vt.id != ? AND vt.comment_status = 'pending'
                AND vtk.keyword IN ({keyword_placeholders})
                ORDER BY vt.priority_score DESC
                LIMIT 5
            """, (target_id, *search_kws))
            similar_targets = [dict(row) for row in cursor.fetchall()]
            result["similar_targets"] = similar_targets

            if len(similar_targets) > 0:
                result["insights"].append({
                    "type": "similar",
                    "message": f"유사한 타겟 {len(similar_targets)}개 발견됨",
                    "importance": "medium"
                })

        # 2. 키워드 연관 분석
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if cursor.fetchone() and matched_keywords:
            keyword_analysis = []
            # [N+1 최적화] LIKE 조건을 OR로 묶어 한 번에 조회
            search_keywords = matched_keywords[:5]
            if search_keywords:
                like_conditions = " OR ".join(["keyword LIKE ?" for _ in search_keywords])
                like_params = [f"%{kw}%" for kw in search_keywords]
                cursor.execute(f"""
                    SELECT keyword, grade, search_volume, kei
                    FROM keyword_insights
                    WHERE {like_conditions}
                """, like_params)

                # 각 검색 키워드에 대해 첫 번째 매칭만 사용
                all_matches = cursor.fetchall()
                matched_set = set()
                for row in all_matches:
                    # 중복 방지: 이미 추가된 원본 키워드는 스킵
                    matched_orig = None
                    for orig_kw in search_keywords:
                        if orig_kw.lower() in row[0].lower() and orig_kw not in matched_set:
                            matched_orig = orig_kw
                            break
                    if matched_orig:
                        matched_set.add(matched_orig)
                        keyword_analysis.append({
                            "keyword": row[0],
                            "grade": row[1],
                            "search_volume": row[2],
                            "kei": row[3]
                        })
            result["keyword_analysis"] = keyword_analysis

            # S급/A급 키워드 인사이트
            high_grade_keywords = [k for k in keyword_analysis if k['grade'] in ('S', 'A')]
            if high_grade_keywords:
                result["insights"].append({
                    "type": "keyword",
                    "message": f"고가치 키워드 {len(high_grade_keywords)}개 매칭됨",
                    "importance": "high"
                })

        # 3. 경쟁사 언급 분석
        content_preview = target.get('content_preview', '') or ''
        title = target.get('title', '') or ''
        full_text = f"{title} {content_preview}".lower()

        # 경쟁사 목록 조회
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='competitors'")
        if cursor.fetchone():
            cursor.execute("SELECT id, name FROM competitors")
            competitors = cursor.fetchall()

            for comp_id, comp_name in competitors:
                if comp_name.lower() in full_text:
                    result["competitor_mentions"].append({
                        "competitor_id": comp_id,
                        "competitor_name": comp_name,
                        "context": "타겟 콘텐츠에서 언급됨"
                    })

            if result["competitor_mentions"]:
                result["insights"].append({
                    "type": "competitor",
                    "message": f"경쟁사 {len(result['competitor_mentions'])}곳 언급됨 - 역공략 기회!",
                    "importance": "high"
                })

        # 4. 타겟 히스토리 (같은 URL의 이전 스캔 정보)
        cursor.execute("""
            SELECT scan_count, first_seen_at, last_scanned_at, priority_score
            FROM viral_targets
            WHERE url = ?
        """, (target.get('url'),))
        history_row = cursor.fetchone()
        if history_row:
            result["target_history"] = {
                "scan_count": history_row[0],
                "first_seen": history_row[1],
                "last_seen": history_row[2],
                "current_score": history_row[3]
            }

            if history_row[0] and history_row[0] >= 3:
                result["insights"].append({
                    "type": "recurring",
                    "message": f"이 타겟은 {history_row[0]}회 재발견됨 - 중요도 높음",
                    "importance": "high"
                })

        # 5. 플랫폼 관련 정보
        platform = target.get('platform', '')
        platform_insights = {
            'cafe': '네이버 카페는 커뮤니티 신뢰도가 높아 자연스러운 접근 필요',
            'blog': '블로그는 정보성 댓글이 효과적',
            'kin': '지식인은 전문성 있는 답변이 중요',
            'youtube': 'YouTube는 영상 관련 구체적 댓글 권장',
            'instagram': '인스타그램은 짧고 친근한 톤 권장'
        }

        if platform in platform_insights:
            result["insights"].append({
                "type": "platform",
                "message": platform_insights[platform],
                "importance": "low"
            })

        conn.close()
        return result

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Target Context Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# [Decision Intelligence] 스마트 필터/추천 시스템
# ===========================================================================

@router.get("/smart-recommendations")
async def get_smart_recommendations() -> Dict[str, Any]:
    """
    스마트 추천 및 필터 프리셋

    AI 기반으로 오늘 집중해야 할 타겟과 추천 필터를 제공합니다.

    Returns:
        - quick_filters: 빠른 필터 프리셋
        - today_focus: 오늘 집중해야 할 타겟
        - insights: 추천 근거 인사이트
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "quick_filters": [],
            "today_focus": [],
            "insights": [],
            "platform_priorities": []
        }

        # 1. 빠른 필터 프리셋 생성

        # 고우선순위 타겟 (80점 이상)
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status = 'pending' AND priority_score >= 80
        """)
        high_priority_count = cursor.fetchone()[0]

        if high_priority_count > 0:
            result["quick_filters"].append({
                "id": "high_priority",
                "name": "고우선순위",
                "icon": "🔥",
                "description": f"{high_priority_count}개의 80점 이상 타겟",
                "count": high_priority_count,
                "filter": {"min_score": 80, "sort": "priority"}
            })

        # 오늘 발견된 타겟
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status = 'pending'
            AND discovered_at >= datetime('now', 'start of day')
        """)
        today_count = cursor.fetchone()[0]

        if today_count > 0:
            result["quick_filters"].append({
                "id": "today",
                "name": "오늘 발견",
                "icon": "🆕",
                "description": f"오늘 발견된 {today_count}개 타겟",
                "count": today_count,
                "filter": {"date_filter": "오늘", "sort": "date"}
            })

        # 재발견된 타겟 (scan_count >= 2)
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status = 'pending' AND scan_count >= 2
        """)
        recurring_count = cursor.fetchone()[0]

        if recurring_count > 0:
            result["quick_filters"].append({
                "id": "recurring",
                "name": "재발견 타겟",
                "icon": "🔄",
                "description": f"여러 번 발견된 {recurring_count}개 타겟",
                "count": recurring_count,
                "filter": {"min_scan_count": 2, "sort": "scan_count"}
            })

        # 댓글 가능 타겟
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status = 'pending' AND is_commentable = 1
        """)
        commentable_count = cursor.fetchone()[0]

        if commentable_count > 0:
            result["quick_filters"].append({
                "id": "commentable",
                "name": "댓글 가능",
                "icon": "✅",
                "description": f"즉시 작업 가능한 {commentable_count}개 타겟",
                "count": commentable_count,
                "filter": {"commentable_only": True, "sort": "priority"}
            })

        # AI 생성된 댓글 대기 중
        cursor.execute("""
            SELECT COUNT(*) FROM viral_targets
            WHERE comment_status = 'generated'
        """)
        generated_count = cursor.fetchone()[0]

        if generated_count > 0:
            result["quick_filters"].append({
                "id": "generated",
                "name": "승인 대기",
                "icon": "✍️",
                "description": f"댓글 승인 대기 {generated_count}개",
                "count": generated_count,
                "filter": {"status": "generated", "sort": "priority"}
            })

        # 2. 오늘 집중해야 할 타겟 (Top 5)
        cursor.execute("""
            SELECT id, title, platform, priority_score, matched_keywords, scan_count
            FROM viral_targets
            WHERE comment_status = 'pending'
            ORDER BY
                CASE WHEN scan_count >= 2 THEN 1 ELSE 0 END DESC,
                priority_score DESC
            LIMIT 5
        """)

        focus_targets = []
        for row in cursor.fetchall():
            target = dict(row)
            # matched_keywords 파싱
            if target.get('matched_keywords'):
                try:
                    target['matched_keywords'] = json.loads(target['matched_keywords'])
                except (json.JSONDecodeError, TypeError):
                    target['matched_keywords'] = []
            focus_targets.append(target)

        result["today_focus"] = focus_targets

        # 3. 플랫폼별 우선순위
        cursor.execute("""
            SELECT platform, COUNT(*) as count, AVG(priority_score) as avg_score
            FROM viral_targets
            WHERE comment_status = 'pending'
            GROUP BY platform
            ORDER BY avg_score DESC
        """)

        platform_priorities = []
        for row in cursor.fetchall():
            platform_priorities.append({
                "platform": row[0],
                "count": row[1],
                "avg_score": round(row[2] or 0, 1)
            })

        result["platform_priorities"] = platform_priorities

        # 4. 인사이트 생성
        if high_priority_count > 10:
            result["insights"].append({
                "type": "priority",
                "message": f"고우선순위 타겟이 {high_priority_count}개 있습니다. 우선 처리를 권장합니다.",
                "importance": "high"
            })

        if recurring_count > 5:
            result["insights"].append({
                "type": "recurring",
                "message": f"재발견된 타겟 {recurring_count}개는 관심도가 높은 주제입니다.",
                "importance": "medium"
            })

        if generated_count > 0:
            result["insights"].append({
                "type": "pending_approval",
                "message": f"{generated_count}개의 AI 댓글이 승인을 기다리고 있습니다.",
                "importance": "high"
            })

        # 가장 활발한 플랫폼 추천
        if platform_priorities:
            top_platform = platform_priorities[0]
            result["insights"].append({
                "type": "platform",
                "message": f"{top_platform['platform']}에서 평균 {top_platform['avg_score']}점으로 가장 높은 기회가 있습니다.",
                "importance": "medium"
            })

        conn.close()
        return result

    except Exception as e:
        print(f"[Smart Recommendations Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# [Decision Intelligence] 트렌드 인사이트
# ===========================================================================

@router.get("/trend-insights")
async def get_trend_insights(days: int = 7) -> Dict[str, Any]:
    """
    트렌드 인사이트 조회

    기간별 키워드/플랫폼 트렌드를 분석하여 인사이트를 제공합니다.

    Args:
        days: 분석 기간 (기본 7일)

    Returns:
        - daily_trends: 일별 타겟 발견 추이
        - keyword_trends: 급상승/하락 키워드
        - platform_trends: 플랫폼별 트렌드
        - category_trends: 카테고리별 변화
        - insights: 트렌드 기반 인사이트
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "period_days": days,
            "daily_trends": [],
            "keyword_trends": {
                "rising": [],
                "falling": []
            },
            "platform_trends": [],
            "category_trends": [],
            "insights": []
        }

        # 1. 일별 타겟 발견 추이
        cursor.execute(f"""
            SELECT DATE(discovered_at) as date,
                   COUNT(*) as count,
                   AVG(priority_score) as avg_score
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            GROUP BY DATE(discovered_at)
            ORDER BY date ASC
        """)

        daily_trends = []
        for row in cursor.fetchall():
            daily_trends.append({
                "date": row[0],
                "count": row[1],
                "avg_score": round(row[2] or 0, 1)
            })

        result["daily_trends"] = daily_trends

        # 2. 키워드 트렌드 분석
        # 최근 절반 기간 vs 이전 절반 기간 비교
        half_days = days // 2

        # 최근 기간 키워드
        cursor.execute(f"""
            SELECT matched_keywords
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{half_days} days')
        """)

        recent_keywords: Dict[str, int] = {}
        for row in cursor.fetchall():
            if row[0]:
                try:
                    keywords = json.loads(row[0])
                    for kw in keywords:
                        recent_keywords[kw] = recent_keywords.get(kw, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass  # JSON 파싱 실패 무시

        # 이전 기간 키워드
        cursor.execute(f"""
            SELECT matched_keywords
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            AND discovered_at < datetime('now', '-{half_days} days')
        """)

        older_keywords: Dict[str, int] = {}
        for row in cursor.fetchall():
            if row[0]:
                try:
                    keywords = json.loads(row[0])
                    for kw in keywords:
                        older_keywords[kw] = older_keywords.get(kw, 0) + 1
                except (json.JSONDecodeError, TypeError):
                    pass  # JSON 파싱 실패 무시

        # 트렌드 계산
        rising_keywords = []
        falling_keywords = []

        for kw, recent_count in recent_keywords.items():
            older_count = older_keywords.get(kw, 0)
            if older_count == 0 and recent_count >= 3:
                rising_keywords.append({
                    "keyword": kw,
                    "recent_count": recent_count,
                    "older_count": older_count,
                    "change": "new"
                })
            elif older_count > 0:
                change_rate = (recent_count - older_count) / older_count * 100
                if change_rate >= 50:
                    rising_keywords.append({
                        "keyword": kw,
                        "recent_count": recent_count,
                        "older_count": older_count,
                        "change_rate": round(change_rate, 1)
                    })
                elif change_rate <= -50:
                    falling_keywords.append({
                        "keyword": kw,
                        "recent_count": recent_count,
                        "older_count": older_count,
                        "change_rate": round(change_rate, 1)
                    })

        result["keyword_trends"]["rising"] = sorted(
            rising_keywords, key=lambda x: x.get("recent_count", 0), reverse=True
        )[:10]
        result["keyword_trends"]["falling"] = sorted(
            falling_keywords, key=lambda x: x.get("change_rate", 0)
        )[:5]

        # 3. 플랫폼별 트렌드
        cursor.execute(f"""
            SELECT platform,
                   DATE(discovered_at) as date,
                   COUNT(*) as count
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            GROUP BY platform, DATE(discovered_at)
            ORDER BY platform, date
        """)

        platform_data: Dict[str, List[Dict]] = {}
        for row in cursor.fetchall():
            platform = row[0]
            if platform not in platform_data:
                platform_data[platform] = []
            platform_data[platform].append({
                "date": row[1],
                "count": row[2]
            })

        for platform, data in platform_data.items():
            result["platform_trends"].append({
                "platform": platform,
                "data": data,
                "total": sum(d["count"] for d in data)
            })

        # 4. 카테고리별 변화
        cursor.execute(f"""
            SELECT category, COUNT(*) as count
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            AND category IS NOT NULL
            GROUP BY category
            ORDER BY count DESC
            LIMIT 10
        """)

        result["category_trends"] = [
            {"category": row[0], "count": row[1]}
            for row in cursor.fetchall()
        ]

        # 5. 인사이트 생성
        if daily_trends:
            # 최근 추세 분석
            if len(daily_trends) >= 3:
                recent_avg = sum(d["count"] for d in daily_trends[-3:]) / 3
                older_avg = sum(d["count"] for d in daily_trends[:-3]) / max(len(daily_trends) - 3, 1)

                if older_avg > 0 and recent_avg > older_avg * 1.3:
                    result["insights"].append({
                        "type": "trend_up",
                        "message": f"최근 3일간 타겟 발견이 {int((recent_avg/older_avg - 1) * 100)}% 증가했습니다.",
                        "importance": "high"
                    })
                elif older_avg > 0 and recent_avg < older_avg * 0.7:
                    result["insights"].append({
                        "type": "trend_down",
                        "message": "최근 타겟 발견이 감소했습니다. 키워드 확장을 고려하세요.",
                        "importance": "medium"
                    })
                elif older_avg == 0 and recent_avg > 0:
                    result["insights"].append({
                        "type": "trend_up",
                        "message": f"최근 3일간 타겟이 새로 발견되기 시작했습니다 (일평균 {round(recent_avg, 1)}건).",
                        "importance": "high"
                    })

        if rising_keywords:
            top_rising = rising_keywords[0]
            result["insights"].append({
                "type": "rising_keyword",
                "message": f"'{top_rising['keyword']}' 키워드가 급상승 중입니다 ({top_rising['recent_count']}회 발견)",
                "importance": "high"
            })

        # 가장 활발한 플랫폼
        if result["platform_trends"]:
            top_platform = max(result["platform_trends"], key=lambda x: x["total"])
            result["insights"].append({
                "type": "top_platform",
                "message": f"{top_platform['platform']}이(가) 최근 {days}일간 가장 활발합니다 ({top_platform['total']}개 타겟)",
                "importance": "medium"
            })

        conn.close()
        return result

    except Exception as e:
        print(f"[Trend Insights Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
# [Performance Dashboard] 성과 대시보드
# ===========================================================================

@router.get("/performance-stats")
async def get_performance_stats(days: int = Query(30, ge=1, le=365)) -> Dict[str, Any]:
    """
    Viral Hunter 성과 통계

    전체 퍼널 분석, 플랫폼별/카테고리별 성과, 시간별 추이를 제공합니다.

    Args:
        days: 분석 기간 (기본 30일)

    Returns:
        - funnel: 전체 퍼널 (스캔 → 필터 → 생성 → 승인 → 게시)
        - rates: 각 단계별 전환율
        - by_platform: 플랫폼별 성과
        - by_category: 카테고리별 성과
        - daily_stats: 일별 추이
        - top_performers: 베스트 성과 타겟
        - insights: 성과 기반 인사이트
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "period_days": days,
            "funnel": {},
            "rates": {},
            "by_platform": [],
            "by_category": [],
            "daily_stats": [],
            "top_performers": [],
            "recent_posted": [],
            "insights": []
        }

        # 1. 전체 퍼널 분석
        cursor.execute(f"""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN is_commentable = 1 THEN 1 ELSE 0 END) as filtered,
                SUM(CASE WHEN comment_status = 'generated' OR comment_status = 'approved' OR comment_status = 'posted' THEN 1 ELSE 0 END) as generated,
                SUM(CASE WHEN comment_status = 'approved' OR comment_status = 'posted' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) as skipped,
                AVG(priority_score) as avg_priority_score
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
        """)
        row = cursor.fetchone()

        if row:
            total = row['total'] or 0
            filtered = row['filtered'] or 0
            generated = row['generated'] or 0
            approved = row['approved'] or 0
            posted = row['posted'] or 0
            skipped = row['skipped'] or 0

            result["funnel"] = {
                "scanned": total,
                "filtered": filtered,
                "generated": generated,
                "approved": approved,
                "posted": posted,
                "skipped": skipped,
                "avg_priority_score": round(row['avg_priority_score'] or 0, 1)
            }

            # 전환율 계산
            result["rates"] = {
                "filter_rate": round(filtered / total * 100, 1) if total > 0 else 0,
                "generation_rate": round(generated / filtered * 100, 1) if filtered > 0 else 0,
                "approval_rate": round(approved / generated * 100, 1) if generated > 0 else 0,
                "posting_rate": round(posted / approved * 100, 1) if approved > 0 else 0,
                "overall_conversion": round(posted / total * 100, 1) if total > 0 else 0,
                "skip_rate": round(skipped / generated * 100, 1) if generated > 0 else 0
            }

        # 2. 플랫폼별 성과
        cursor.execute(f"""
            SELECT
                platform,
                COUNT(*) as total,
                SUM(CASE WHEN comment_status = 'generated' OR comment_status = 'approved' OR comment_status = 'posted' THEN 1 ELSE 0 END) as generated,
                SUM(CASE WHEN comment_status = 'approved' OR comment_status = 'posted' THEN 1 ELSE 0 END) as approved,
                SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                AVG(priority_score) as avg_score
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            GROUP BY platform
            ORDER BY posted DESC
        """)

        for row in cursor.fetchall():
            total = row['total'] or 0
            generated = row['generated'] or 0
            approved = row['approved'] or 0
            posted = row['posted'] or 0

            result["by_platform"].append({
                "platform": row['platform'],
                "total": total,
                "generated": generated,
                "approved": approved,
                "posted": posted,
                "avg_score": round(row['avg_score'] or 0, 1),
                "approval_rate": round(approved / generated * 100, 1) if generated > 0 else 0,
                "posting_rate": round(posted / total * 100, 1) if total > 0 else 0
            })

        # 3. 카테고리별 성과
        cursor.execute(f"""
            SELECT
                COALESCE(category, '미분류') as category,
                COUNT(*) as total,
                SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                AVG(priority_score) as avg_score
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            GROUP BY category
            ORDER BY posted DESC
            LIMIT 10
        """)

        for row in cursor.fetchall():
            total = row['total'] or 0
            posted = row['posted'] or 0

            result["by_category"].append({
                "category": row['category'],
                "total": total,
                "posted": posted,
                "avg_score": round(row['avg_score'] or 0, 1),
                "posting_rate": round(posted / total * 100, 1) if total > 0 else 0
            })

        # 4. 일별 통계
        cursor.execute(f"""
            SELECT
                DATE(discovered_at) as date,
                COUNT(*) as scanned,
                SUM(CASE WHEN comment_status = 'generated' OR comment_status = 'approved' OR comment_status = 'posted' THEN 1 ELSE 0 END) as generated,
                SUM(CASE WHEN comment_status = 'posted' THEN 1 ELSE 0 END) as posted,
                AVG(priority_score) as avg_score
            FROM viral_targets
            WHERE discovered_at >= datetime('now', '-{days} days')
            GROUP BY DATE(discovered_at)
            ORDER BY date DESC
            LIMIT 30
        """)

        result["daily_stats"] = [
            {
                "date": row['date'],
                "scanned": row['scanned'],
                "generated": row['generated'],
                "posted": row['posted'],
                "avg_score": round(row['avg_score'] or 0, 1)
            }
            for row in cursor.fetchall()
        ]
        result["daily_stats"].reverse()  # 오래된 것부터

        # 5. 최근 게시된 댓글 (베스트 성과)
        cursor.execute(f"""
            SELECT
                id, title, platform, category, priority_score,
                generated_comment, discovered_at
            FROM viral_targets
            WHERE comment_status = 'posted'
            AND discovered_at >= datetime('now', '-{days} days')
            ORDER BY priority_score DESC
            LIMIT 10
        """)

        result["top_performers"] = [
            {
                "id": row['id'],
                "title": row['title'][:50] + "..." if len(row['title'] or '') > 50 else row['title'],
                "platform": row['platform'],
                "category": row['category'],
                "priority_score": round(row['priority_score'] or 0, 1),
                "comment_preview": (row['generated_comment'] or '')[:100] + "..." if len(row['generated_comment'] or '') > 100 else row['generated_comment'],
                "discovered_at": row['discovered_at']
            }
            for row in cursor.fetchall()
        ]

        # 6. 최근 게시 (시간순)
        cursor.execute("""
            SELECT
                id, title, platform, category, priority_score, discovered_at
            FROM viral_targets
            WHERE comment_status = 'posted'
            ORDER BY discovered_at DESC
            LIMIT 5
        """)

        result["recent_posted"] = [
            {
                "id": row['id'],
                "title": row['title'][:40] + "..." if len(row['title'] or '') > 40 else row['title'],
                "platform": row['platform'],
                "category": row['category'],
                "priority_score": round(row['priority_score'] or 0, 1),
                "discovered_at": row['discovered_at']
            }
            for row in cursor.fetchall()
        ]

        # 7. 인사이트 생성
        funnel = result["funnel"]
        rates = result["rates"]

        # 전체 전환율 인사이트
        if rates.get("overall_conversion", 0) > 5:
            result["insights"].append({
                "type": "success",
                "message": f"전체 전환율 {rates['overall_conversion']}%로 양호합니다.",
                "importance": "high"
            })
        elif rates.get("overall_conversion", 0) < 1:
            result["insights"].append({
                "type": "warning",
                "message": f"전체 전환율이 {rates['overall_conversion']}%로 낮습니다. 타겟 품질을 점검하세요.",
                "importance": "high"
            })

        # 승인율 인사이트
        if rates.get("approval_rate", 0) < 50:
            result["insights"].append({
                "type": "warning",
                "message": f"승인율이 {rates['approval_rate']}%입니다. 댓글 품질 개선이 필요합니다.",
                "importance": "medium"
            })

        # 가장 성과 좋은 플랫폼
        if result["by_platform"]:
            top_platform = result["by_platform"][0]
            if top_platform["posted"] > 0:
                result["insights"].append({
                    "type": "platform",
                    "message": f"{top_platform['platform']}에서 가장 많은 게시({top_platform['posted']}건)가 이루어졌습니다.",
                    "importance": "medium"
                })

        # 평균 점수 인사이트
        avg_score = funnel.get("avg_priority_score", 0)
        if avg_score >= 70:
            result["insights"].append({
                "type": "quality",
                "message": f"평균 우선순위 점수 {avg_score}점으로 고품질 타겟입니다.",
                "importance": "low"
            })

        conn.close()
        return result

    except Exception as e:
        print(f"[Performance Stats Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance-comparison")
async def get_performance_comparison() -> Dict[str, Any]:
    """
    기간별 성과 비교

    이번 주 vs 지난 주, 이번 달 vs 지난 달 비교

    Returns:
        - weekly: 이번 주 vs 지난 주
        - monthly: 이번 달 vs 지난 달
    """
    try:
        db_path = get_db_path()
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        result = {
            "weekly": {},
            "monthly": {}
        }

        # 이번 주 vs 지난 주
        cursor.execute("""
            SELECT
                SUM(CASE WHEN discovered_at >= datetime('now', '-7 days') THEN 1 ELSE 0 END) as this_week_scanned,
                SUM(CASE WHEN discovered_at >= datetime('now', '-7 days') AND comment_status = 'posted' THEN 1 ELSE 0 END) as this_week_posted,
                SUM(CASE WHEN discovered_at >= datetime('now', '-14 days') AND discovered_at < datetime('now', '-7 days') THEN 1 ELSE 0 END) as last_week_scanned,
                SUM(CASE WHEN discovered_at >= datetime('now', '-14 days') AND discovered_at < datetime('now', '-7 days') AND comment_status = 'posted' THEN 1 ELSE 0 END) as last_week_posted
            FROM viral_targets
        """)
        row = cursor.fetchone()

        this_week_scanned = row['this_week_scanned'] or 0
        this_week_posted = row['this_week_posted'] or 0
        last_week_scanned = row['last_week_scanned'] or 0
        last_week_posted = row['last_week_posted'] or 0

        result["weekly"] = {
            "this_week": {
                "scanned": this_week_scanned,
                "posted": this_week_posted,
                "rate": round(this_week_posted / this_week_scanned * 100, 1) if this_week_scanned > 0 else 0
            },
            "last_week": {
                "scanned": last_week_scanned,
                "posted": last_week_posted,
                "rate": round(last_week_posted / last_week_scanned * 100, 1) if last_week_scanned > 0 else 0
            },
            "change": {
                "scanned": this_week_scanned - last_week_scanned,
                "scanned_pct": round((this_week_scanned - last_week_scanned) / last_week_scanned * 100, 1) if last_week_scanned > 0 else 0,
                "posted": this_week_posted - last_week_posted,
                "posted_pct": round((this_week_posted - last_week_posted) / last_week_posted * 100, 1) if last_week_posted > 0 else 0
            }
        }

        # 이번 달 vs 지난 달
        cursor.execute("""
            SELECT
                SUM(CASE WHEN discovered_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as this_month_scanned,
                SUM(CASE WHEN discovered_at >= datetime('now', '-30 days') AND comment_status = 'posted' THEN 1 ELSE 0 END) as this_month_posted,
                SUM(CASE WHEN discovered_at >= datetime('now', '-60 days') AND discovered_at < datetime('now', '-30 days') THEN 1 ELSE 0 END) as last_month_scanned,
                SUM(CASE WHEN discovered_at >= datetime('now', '-60 days') AND discovered_at < datetime('now', '-30 days') AND comment_status = 'posted' THEN 1 ELSE 0 END) as last_month_posted
            FROM viral_targets
        """)
        row = cursor.fetchone()

        this_month_scanned = row['this_month_scanned'] or 0
        this_month_posted = row['this_month_posted'] or 0
        last_month_scanned = row['last_month_scanned'] or 0
        last_month_posted = row['last_month_posted'] or 0

        result["monthly"] = {
            "this_month": {
                "scanned": this_month_scanned,
                "posted": this_month_posted,
                "rate": round(this_month_posted / this_month_scanned * 100, 1) if this_month_scanned > 0 else 0
            },
            "last_month": {
                "scanned": last_month_scanned,
                "posted": last_month_posted,
                "rate": round(last_month_posted / last_month_scanned * 100, 1) if last_month_scanned > 0 else 0
            },
            "change": {
                "scanned": this_month_scanned - last_month_scanned,
                "scanned_pct": round((this_month_scanned - last_month_scanned) / last_month_scanned * 100, 1) if last_month_scanned > 0 else 0,
                "posted": this_month_posted - last_month_posted,
                "posted_pct": round((this_month_posted - last_month_posted) / last_month_posted * 100, 1) if last_month_posted > 0 else 0
            }
        }

        conn.close()
        return result

    except Exception as e:
        print(f"[Performance Comparison Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
