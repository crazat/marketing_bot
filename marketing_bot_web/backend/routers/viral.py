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

# [P2-3] 검증 결과 캐시 (1시간) - [안정성 개선] TTL 기반 자동 정리
_verification_cache: Dict[str, Dict[str, Any]] = {}
_verification_cache_lock = threading.Lock()  # 스레드 안전을 위한 lock
_cache_ttl = 3600  # 1시간
_cache_max_size = 1000  # 최대 캐시 항목 수
_cache_cleanup_threshold = 800  # 이 수에 도달하면 정리 시작

# [Phase 7] 템플릿 캐시 (5분 TTL) - DB 부하 감소
_templates_cache: Dict[str, tuple[List[Dict], float]] = {}
_templates_cache_lock = threading.Lock()
_templates_cache_ttl = 300  # 5분
_last_cleanup_time = 0.0


def _cleanup_expired_cache():
    """
    [안정성 개선] 만료된 캐시 항목 정리
    - TTL이 지난 항목 모두 제거
    - 메모리 누수 방지
    """
    global _last_cleanup_time
    current_time = time.time()

    # 마지막 정리 후 5분 이내면 스킵 (과도한 정리 방지)
    if current_time - _last_cleanup_time < 300:
        return

    expired_keys = [
        key for key, value in _verification_cache.items()
        if current_time - value.get('cached_at', 0) >= _cache_ttl
    ]

    for key in expired_keys:
        del _verification_cache[key]

    _last_cleanup_time = current_time

    if expired_keys:
        logger.debug(f"캐시 정리 완료: {len(expired_keys)}개 만료 항목 제거, 남은 항목: {len(_verification_cache)}")


def _get_cached_verification(url: str) -> Optional[Dict[str, Any]]:
    """캐시된 검증 결과 반환 (없거나 만료되면 None)"""
    if url in _verification_cache:
        cached = _verification_cache[url]
        if time.time() - cached.get('cached_at', 0) < _cache_ttl:
            return cached['result']
        else:
            # 만료된 항목 즉시 제거
            del _verification_cache[url]
    return None


def _set_cache_verification(url: str, result: Dict[str, Any]):
    """검증 결과를 캐시에 저장"""
    current_time = time.time()

    _verification_cache[url] = {
        'result': result,
        'cached_at': current_time
    }

    # [안정성 개선] 임계값 도달 시 만료 캐시 정리
    if len(_verification_cache) >= _cache_cleanup_threshold:
        _cleanup_expired_cache()

    # 정리 후에도 최대 크기 초과 시 가장 오래된 20% 제거
    if len(_verification_cache) > _cache_max_size:
        # 시간순 정렬 후 오래된 20% 제거
        sorted_items = sorted(
            _verification_cache.items(),
            key=lambda x: x[1].get('cached_at', 0)
        )
        items_to_remove = len(_verification_cache) - int(_cache_max_size * 0.8)
        for key, _ in sorted_items[:items_to_remove]:
            del _verification_cache[key]
        logger.debug(f"캐시 크기 제한으로 {items_to_remove}개 항목 제거")

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
# 개인정보는 수집하지 않습니다.
#
# UTM 추적을 비활성화하려면 아래 값을 False로 변경하세요.
UTM_TRACKING_ENABLED = True
# =======================================================================


def _generate_utm_url(base_url: str, source: str = "viral_hunter",
                       medium: str = "comment", campaign: str = "",
                       content: str = "", term: str = "") -> str:
    """
    [Phase 4.0] UTM 매개변수가 포함된 URL 생성

    [투명성 안내]
    이 기능은 마케팅 활동의 효과 측정 목적으로 UTM 파라미터를 추가합니다.
    - 개인정보 수집 없음
    - 유입 경로 분석용
    - UTM_TRACKING_ENABLED = False로 비활성화 가능

    Args:
        base_url: 원본 URL
        source: 유입 소스 (예: viral_hunter)
        medium: 매체 유형 (예: comment, reply)
        campaign: 캠페인명 (예: 카테고리명)
        content: 콘텐츠 구분 (예: template_id)
        term: 검색어/키워드

    Returns:
        UTM 매개변수가 추가된 URL (비활성화 시 원본 URL 반환)
    """
    # UTM 추적이 비활성화되면 원본 URL 반환
    if not UTM_TRACKING_ENABLED:
        return base_url
    if not base_url:
        return ""

    try:
        parsed = urlparse(base_url)
        existing_params = parse_qs(parsed.query)

        utm_params = {
            'utm_source': source,
            'utm_medium': medium,
        }

        if campaign:
            utm_params['utm_campaign'] = campaign
        if content:
            utm_params['utm_content'] = content
        if term:
            utm_params['utm_term'] = term

        # 기존 파라미터와 병합
        existing_params.update({k: [v] for k, v in utm_params.items()})

        # 새 쿼리스트링 생성
        new_query = urlencode({k: v[0] for k, v in existing_params.items()})

        return urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
    except Exception as e:
        print(f"[UTM Error] {str(e)}")
        return base_url


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

        # 바이럴 타겟 정보 조회
        cursor.execute("""
            SELECT id, platform, title, url, author, category, content,
                   discovered_at, generated_comment
            FROM viral_targets
            WHERE id = ?
        """, (target_id,))
        target = cursor.fetchone()

        if not target:
            return False

        target_id_val, platform, title, url, author, category, content, discovered_at, comment = target

        # mentions 테이블에 source_module 컬럼이 있는지 확인하고 없으면 추가
        cursor.execute("PRAGMA table_info(mentions)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'source_module' not in columns:
            cursor.execute("ALTER TABLE mentions ADD COLUMN source_module TEXT DEFAULT NULL")

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

        # 현재 mentions 테이블의 실제 컬럼에 맞춰 INSERT
        cursor.execute("""
            INSERT INTO mentions (
                platform, title, url, summary, content,
                author, category, keyword, status,
                source_module, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', 'viral_hunter', datetime('now', 'localtime'))
        """, (
            platform_mapped,
            title or '',
            url or '',
            content[:500] if content else '',  # summary
            content or '',
            author or '',
            category or '',
            category or ''  # keyword
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


class VerifyTargetRequest(BaseModel):
    target_id: str = Field(..., min_length=1, max_length=100)


class BatchCommentRequest(BaseModel):
    """[Phase 5.1] 댓글 배치 생성 요청"""
    target_ids: Optional[List[str]] = None  # 특정 타겟 ID 목록 (없으면 자동 선택)
    category: Optional[str] = Field(None, max_length=50)  # 카테고리 필터
    batch_size: int = Field(20, ge=1, le=100)  # 배치 크기 (1-100개)
    prioritize_by: PrioritizeSortBy = "priority_score"  # 정렬 기준


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
    scan_batch: Optional[str] = None
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
        batch_condition = ""
        params: List[Any] = []
        if scan_batch:
            batch_condition = "AND strftime('%Y-%m-%d %H', discovered_at) = ?"
            params.append(scan_batch)

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
    limit: int = Query(default=200, ge=1, le=1000, description="최대 조회 수")
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
        hunter = get_viral_hunter()

        # platforms 파라미터를 리스트로 변환
        platforms_list = None
        if platforms:
            platforms_list = [p.strip() for p in platforms.split(',') if p.strip()]

        targets = hunter.list_targets(
            status=status,
            category=category,
            date_filter=date_filter,
            platforms=platforms_list,
            comment_status=comment_status,
            min_scan_count=min_scan_count,
            search=search,
            sort=sort,
            scan_batch=scan_batch,
            limit=limit
        )

        # matched_keywords를 JSON 문자열에서 배열로 변환
        for target in targets:
            if 'matched_keywords' in target and isinstance(target['matched_keywords'], str):
                try:
                    target['matched_keywords'] = json.loads(target['matched_keywords'])
                except (json.JSONDecodeError, TypeError):
                    target['matched_keywords'] = []

        return targets

    except Exception as e:
        print(f"[Viral Targets Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"바이럴 타겟 조회 실패: {str(e)}")

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

        # 댓글 생성 (스타일 적용)
        comment = hunter.generator.generate(target, style=request.style)

        if comment:
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


@router.post("/verify-batch")
async def verify_batch(category: Optional[str] = None, limit: int = 20) -> Dict[str, Any]:
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
    타겟 액션 (승인/건너뛰기/삭제)

    Args:
        request: 타겟 ID 및 액션

    Returns:
        상태 메시지
    """
    try:
        hunter = get_viral_hunter()

        lead_created = False

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
            message = "타겟 건너뛰기 완료"

        elif request.action == "delete":
            hunter.db.update_viral_target(request.target_id, {
                'comment_status': 'deleted'
            })
            message = "타겟 삭제 완료"

        else:
            raise HTTPException(status_code=400, detail="잘못된 액션입니다")

        return {
            'status': 'success',
            'message': message,
            'lead_created': lead_created
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

ScanPlatform = Literal["cafe", "blog", "kin", "place", "karrot", "youtube", "instagram", "tiktok"]


class ScanConfig(BaseModel):
    """스캔 설정"""
    platforms: List[ScanPlatform] = ['cafe', 'blog', 'kin', 'place', 'karrot', 'youtube', 'instagram', 'tiktok']
    max_results: int = Field(500, ge=0, le=5000)  # 0 = 무제한, 최대 5000


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


class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=5000)
    category: str = Field("general", max_length=50)
    situation_type: str = Field("general", max_length=50)  # [Phase 5.0]
    engagement_signal: EngagementSignal = "any"   # [Phase 5.0]
    priority_segment: PrioritySegment = "all"    # [Phase 5.1]


class TemplateRecommendRequest(BaseModel):
    """[Phase 5.1] 템플릿 자동 추천 요청"""
    priority_rank: int = Field(3, ge=1, le=5)  # 1-5
    engagement_signal: EngagementSignal = "passive"
    category: str = Field("general", max_length=50)
    content_preview: str = Field("", max_length=1000)  # 원본 콘텐츠 미리보기


@router.get("/templates")
async def get_comment_templates(
    situation_type: Optional[str] = None,
    engagement_signal: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    댓글 템플릿 목록 조회

    [Phase 5.0] 필터링 지원:
    - situation_type: 상황 유형 (general, question, review, recommendation 등)
    - engagement_signal: 참여 신호 (any, seeking_info, ready_to_act, passive)

    [Phase 7] TTLCache 적용 (5분) - DB 부하 감소

    Args:
        situation_type: 상황 유형 필터
        engagement_signal: 참여 신호 필터

    Returns:
        필터링된 템플릿 목록
    """
    # [Phase 7] 캐시 키 생성
    cache_key = f"templates:{situation_type or 'all'}:{engagement_signal or 'all'}"

    # 캐시 확인
    with _templates_cache_lock:
        if cache_key in _templates_cache:
            cached_data, cached_time = _templates_cache[cache_key]
            if time.time() - cached_time < _templates_cache_ttl:
                return cached_data

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # [Phase 6.1] 테이블 생성/마이그레이션은 services/db_init.py에서 앱 시작 시 처리
        # [Phase 7] SELECT * 제거 - 필요한 컬럼만 명시
        columns = "id, name, content, category, situation_type, engagement_signal, use_count, created_at"
        query = f"SELECT {columns} FROM comment_templates WHERE 1=1"
        params = []

        # [Phase 5.0] 필터링 조건 추가
        if situation_type:
            query += " AND (situation_type = ? OR situation_type = 'general')"
            params.append(situation_type)

        if engagement_signal:
            query += " AND (engagement_signal = ? OR engagement_signal = 'any')"
            params.append(engagement_signal)

        query += " ORDER BY use_count DESC, created_at DESC"

        cursor.execute(query, params)
        templates = [dict(row) for row in cursor.fetchall()]
        conn.close()

        # [Phase 7] 결과 캐싱
        with _templates_cache_lock:
            _templates_cache[cache_key] = (templates, time.time())
            # 캐시 크기 제한 (최대 50개 키)
            if len(_templates_cache) > 50:
                oldest_key = min(_templates_cache, key=lambda k: _templates_cache[k][1])
                del _templates_cache[oldest_key]

        return templates

    except Exception as e:
        logger.error(f"[Templates Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"템플릿 조회 실패: {str(e)}")


@router.post("/templates")
async def create_template(template: TemplateCreate) -> Dict[str, Any]:
    """
    새 댓글 템플릿 생성

    [Phase 5.0] situation_type, engagement_signal 필드 추가
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO comment_templates (name, content, category, situation_type, engagement_signal)
            VALUES (?, ?, ?, ?, ?)
        """, (template.name, template.content, template.category,
              template.situation_type, template.engagement_signal))

        conn.commit()
        template_id = cursor.lastrowid
        conn.close()

        # [Phase 7] 캐시 무효화 - 새 템플릿 추가 시 목록 캐시 클리어
        with _templates_cache_lock:
            _templates_cache.clear()

        return {
            'status': 'success',
            'message': '템플릿이 저장되었습니다',
            'template_id': template_id
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"템플릿 저장 실패: {str(e)}")


@router.patch("/templates/{template_id}/use")
async def increment_template_use(template_id: int) -> Dict[str, str]:
    """
    템플릿 사용 횟수 증가
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE comment_templates
            SET use_count = use_count + 1, updated_at = datetime('now')
            WHERE id = ?
        """, (template_id,))

        conn.commit()
        conn.close()

        return {'status': 'success'}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int) -> Dict[str, str]:
    """
    댓글 템플릿 삭제
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM comment_templates WHERE id = ?", (template_id,))
        conn.commit()
        conn.close()

        # [Phase 7] 캐시 무효화 - 템플릿 삭제 시 목록 캐시 클리어
        with _templates_cache_lock:
            _templates_cache.clear()

        return {'status': 'success', 'message': '템플릿이 삭제되었습니다'}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/recommend")
async def recommend_template(request: TemplateRecommendRequest) -> Dict[str, Any]:
    """
    [Phase 5.1] 리드 정보 기반 템플릿 자동 추천

    priority_rank와 engagement_signal을 기반으로 가장 적합한 템플릿을 추천합니다.

    세그먼트 매핑:
    - priority_rank 1 → VIP (최우선 고객)
    - priority_rank 2 → High (높은 가치)
    - priority_rank 3 → Medium (중간 가치)
    - priority_rank 4-5 → Low (낮은/보류)

    Args:
        request: 리드의 priority_rank, engagement_signal, category, content_preview

    Returns:
        추천 템플릿 목록 (최대 3개)
    """
    import sqlite3

    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # priority_segment 컬럼 확인 및 추가
        cursor.execute("PRAGMA table_info(comment_templates)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'priority_segment' not in columns:
            cursor.execute("""
                ALTER TABLE comment_templates
                ADD COLUMN priority_segment TEXT DEFAULT 'all'
            """)
            conn.commit()

        # priority_rank → segment 매핑
        segment_map = {1: 'vip', 2: 'high', 3: 'medium', 4: 'low', 5: 'low'}
        target_segment = segment_map.get(request.priority_rank, 'medium')

        # [Phase 7] SELECT * 제거 - 템플릿 검색 (우선순위 순)
        columns = "id, name, content, category, situation_type, engagement_signal, use_count, created_at, priority_segment"
        query = f"""
            SELECT {columns},
                   CASE
                       WHEN priority_segment = ? THEN 100
                       WHEN priority_segment = 'all' THEN 50
                       ELSE 10
                   END +
                   CASE
                       WHEN engagement_signal = ? THEN 30
                       WHEN engagement_signal = 'any' THEN 15
                       ELSE 0
                   END +
                   CASE
                       WHEN category = ? THEN 20
                       WHEN category = 'general' THEN 10
                       ELSE 0
                   END as match_score
            FROM comment_templates
            WHERE (priority_segment = ? OR priority_segment = 'all')
              AND (engagement_signal = ? OR engagement_signal = 'any')
            ORDER BY match_score DESC, use_count DESC
            LIMIT 3
        """

        cursor.execute(query, (
            target_segment, request.engagement_signal, request.category,
            target_segment, request.engagement_signal
        ))

        templates = [dict(row) for row in cursor.fetchall()]

        # 기본 템플릿이 없으면 일반 템플릿 반환
        if not templates:
            cursor.execute(f"""
                SELECT {columns}
                FROM comment_templates
                WHERE priority_segment = 'all' OR priority_segment IS NULL
                ORDER BY use_count DESC
                LIMIT 3
            """)
            templates = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # 세그먼트별 톤 가이드 추가
        tone_guides = {
            'vip': '🔥 VIP 세그먼트: 개인화된 프리미엄 응대, 빠른 반응 시간, 전문 상담 제안',
            'high': '⚡ High 세그먼트: 적극적 관심 표현, 상세한 정보 제공, 방문 유도',
            'medium': '📌 Medium 세그먼트: 친절한 안내, 관심사 파악, 후속 연락 제안',
            'low': '📋 Low 세그먼트: 기본 정보 제공, 간결한 응대'
        }

        return {
            'status': 'success',
            'priority_rank': request.priority_rank,
            'target_segment': target_segment,
            'tone_guide': tone_guides.get(target_segment, ''),
            'templates': templates,
            'template_count': len(templates)
        }

    except Exception as e:
        print(f"[Template Recommend Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"템플릿 추천 실패: {str(e)}")


# =====================================
# [Phase 4.0] UTM 매개변수 API
# =====================================

class UTMRequest(BaseModel):
    """UTM 매개변수 생성 요청"""
    url: str = Field(..., min_length=1, max_length=2000)
    campaign: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = Field(None, max_length=200)
    term: Optional[str] = Field(None, max_length=100)
    source: str = Field("viral_hunter", max_length=100)
    medium: str = Field("comment", max_length=100)


@router.post("/generate-utm")
async def generate_utm(request: UTMRequest) -> Dict[str, Any]:
    """
    [Phase 4.0] UTM 매개변수가 포함된 URL 생성

    댓글에 포함할 링크에 UTM 추적 매개변수를 자동으로 추가합니다.
    이를 통해 바이럴 마케팅의 클릭 및 전환을 추적할 수 있습니다.

    Args:
        request: URL 및 UTM 매개변수

    Returns:
        UTM이 추가된 URL
    """
    try:
        utm_url = _generate_utm_url(
            base_url=request.url,
            source=request.source,
            medium=request.medium,
            campaign=request.campaign or "",
            content=request.content or "",
            term=request.term or ""
        )

        return {
            "success": True,
            "original_url": request.url,
            "utm_url": utm_url,
            "utm_params": {
                "utm_source": request.source,
                "utm_medium": request.medium,
                "utm_campaign": request.campaign,
                "utm_content": request.content,
                "utm_term": request.term
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/utm-stats")
async def get_utm_stats() -> Dict[str, Any]:
    """
    [Phase 4.0] UTM 추적 통계 조회

    생성된 UTM 링크의 사용 현황을 조회합니다.

    Returns:
        - total_utm_links: 생성된 UTM 링크 수
        - by_campaign: 캠페인별 통계
        - recent_links: 최근 생성된 링크
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # utm_links 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS utm_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT NOT NULL,
                utm_url TEXT NOT NULL,
                campaign TEXT,
                content TEXT,
                term TEXT,
                click_count INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now', 'localtime'))
            )
        """)
        conn.commit()

        # 통계 조회
        cursor.execute("SELECT COUNT(*) FROM utm_links")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT campaign, COUNT(*) as count, SUM(click_count) as clicks
            FROM utm_links
            WHERE campaign IS NOT NULL AND campaign != ''
            GROUP BY campaign
            ORDER BY clicks DESC
            LIMIT 10
        """)
        by_campaign = [
            {"campaign": row[0], "links": row[1], "clicks": row[2] or 0}
            for row in cursor.fetchall()
        ]

        cursor.execute("""
            SELECT original_url, utm_url, campaign, click_count, created_at
            FROM utm_links
            ORDER BY created_at DESC
            LIMIT 10
        """)
        recent = [
            {
                "original_url": row[0],
                "utm_url": row[1],
                "campaign": row[2],
                "clicks": row[3],
                "created_at": row[4]
            }
            for row in cursor.fetchall()
        ]

        conn.close()

        return {
            "total_utm_links": total,
            "by_campaign": by_campaign,
            "recent_links": recent
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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


# ============================================
# [Phase 7.2] 댓글 성과 추적 API
# ============================================

class PostedComment(BaseModel):
    """게시된 댓글 기록"""
    target_id: int  # viral_targets.id
    template_id: Optional[int] = None  # comment_templates.id
    content: str
    platform: str
    url: str
    posted_at: Optional[str] = None


class CommentEngagement(BaseModel):
    """댓글 참여 지표 업데이트"""
    likes: Optional[int] = 0
    replies: Optional[int] = 0
    clicks: Optional[int] = 0
    led_to_contact: Optional[bool] = False
    led_to_conversion: Optional[bool] = False


def _ensure_posted_comments_table(cursor):
    """posted_comments 테이블 생성"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER,
            template_id INTEGER,
            content TEXT NOT NULL,
            platform TEXT,
            url TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            -- 참여 지표
            likes INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            -- 전환 추적
            led_to_contact INTEGER DEFAULT 0,
            led_to_conversion INTEGER DEFAULT 0,
            -- 메타데이터
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (target_id) REFERENCES viral_targets(id),
            FOREIGN KEY (template_id) REFERENCES comment_templates(id)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_posted_comments_platform
        ON posted_comments(platform)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_posted_comments_posted_at
        ON posted_comments(posted_at)
    """)


@router.post("/comments/post")
async def record_posted_comment(comment: PostedComment) -> Dict[str, Any]:
    """
    [Phase 7.2] 게시된 댓글 기록

    바이럴 타겟에 댓글을 게시한 후 기록합니다.

    Args:
        comment: 댓글 정보

    Returns:
        기록된 댓글 ID
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_posted_comments_table(cursor)

        cursor.execute("""
            INSERT INTO posted_comments
            (target_id, template_id, content, platform, url, posted_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            comment.target_id,
            comment.template_id,
            comment.content,
            comment.platform,
            comment.url,
            comment.posted_at or datetime.now().isoformat()
        ))

        comment_id = cursor.lastrowid

        # 템플릿 사용 횟수 증가
        if comment.template_id:
            cursor.execute("""
                UPDATE comment_templates
                SET use_count = use_count + 1,
                    updated_at = datetime('now')
                WHERE id = ?
            """, (comment.template_id,))

        # 타겟 상태 업데이트
        cursor.execute("""
            UPDATE viral_targets
            SET status = 'commented'
            WHERE id = ?
        """, (comment.target_id,))

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "comment_id": comment_id,
            "message": "댓글이 기록되었습니다"
        }

    except Exception as e:
        print(f"[Post Comment Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/comments/{comment_id}/engagement")
async def update_comment_engagement(
    comment_id: int,
    engagement: CommentEngagement
) -> Dict[str, Any]:
    """
    [Phase 7.2] 댓글 참여 지표 업데이트

    게시된 댓글의 참여 지표(좋아요, 답글, 클릭 등)를 업데이트합니다.

    Args:
        comment_id: 댓글 ID
        engagement: 참여 지표

    Returns:
        업데이트 결과
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        _ensure_posted_comments_table(cursor)

        # 기존 댓글 확인
        cursor.execute("SELECT id FROM posted_comments WHERE id = ?", (comment_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")

        cursor.execute("""
            UPDATE posted_comments
            SET likes = ?,
                replies = ?,
                clicks = ?,
                led_to_contact = ?,
                led_to_conversion = ?,
                updated_at = datetime('now')
            WHERE id = ?
        """, (
            engagement.likes or 0,
            engagement.replies or 0,
            engagement.clicks or 0,
            1 if engagement.led_to_contact else 0,
            1 if engagement.led_to_conversion else 0,
            comment_id
        ))

        conn.commit()
        conn.close()

        return {
            "status": "success",
            "message": "참여 지표가 업데이트되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Update Engagement Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments/performance")
async def get_comment_performance(days: int = 30) -> Dict[str, Any]:
    """
    [Phase 7.2] 댓글 성과 통계

    게시된 댓글의 전반적인 성과를 분석합니다.

    Args:
        days: 조회 기간 (일)

    Returns:
        - total_comments: 총 댓글 수
        - by_platform: 플랫폼별 통계
        - by_template: 템플릿별 성과
        - engagement_summary: 참여 요약
        - conversion_funnel: 전환 퍼널
        - recent_comments: 최근 댓글
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        _ensure_posted_comments_table(cursor)

        date_offset = f'-{min(days, 365)} days'

        # 총 댓글 수
        cursor.execute("""
            SELECT COUNT(*) FROM posted_comments
            WHERE posted_at >= datetime('now', ?)
        """, (date_offset,))
        total = cursor.fetchone()[0]

        # 플랫폼별 통계
        cursor.execute("""
            SELECT
                platform,
                COUNT(*) as count,
                SUM(likes) as total_likes,
                SUM(replies) as total_replies,
                SUM(clicks) as total_clicks,
                SUM(led_to_contact) as contacts,
                SUM(led_to_conversion) as conversions
            FROM posted_comments
            WHERE posted_at >= datetime('now', ?)
            GROUP BY platform
            ORDER BY count DESC
        """, (date_offset,))
        by_platform = [dict(row) for row in cursor.fetchall()]

        # 템플릿별 성과
        cursor.execute("""
            SELECT
                ct.name as template_name,
                ct.category,
                COUNT(pc.id) as use_count,
                AVG(pc.likes) as avg_likes,
                AVG(pc.replies) as avg_replies,
                SUM(pc.led_to_conversion) as conversions
            FROM posted_comments pc
            LEFT JOIN comment_templates ct ON pc.template_id = ct.id
            WHERE pc.posted_at >= datetime('now', ?)
              AND pc.template_id IS NOT NULL
            GROUP BY pc.template_id
            ORDER BY use_count DESC
            LIMIT 10
        """, (date_offset,))
        by_template = [
            {
                "template_name": row['template_name'] or '(삭제된 템플릿)',
                "category": row['category'],
                "use_count": row['use_count'],
                "avg_likes": round(row['avg_likes'] or 0, 1),
                "avg_replies": round(row['avg_replies'] or 0, 1),
                "conversions": row['conversions'] or 0
            }
            for row in cursor.fetchall()
        ]

        # 참여 요약
        cursor.execute("""
            SELECT
                SUM(likes) as total_likes,
                SUM(replies) as total_replies,
                SUM(clicks) as total_clicks,
                AVG(likes) as avg_likes,
                AVG(replies) as avg_replies
            FROM posted_comments
            WHERE posted_at >= datetime('now', ?)
        """, (date_offset,))
        eng_row = cursor.fetchone()
        engagement_summary = {
            "total_likes": eng_row['total_likes'] or 0,
            "total_replies": eng_row['total_replies'] or 0,
            "total_clicks": eng_row['total_clicks'] or 0,
            "avg_likes_per_comment": round(eng_row['avg_likes'] or 0, 2),
            "avg_replies_per_comment": round(eng_row['avg_replies'] or 0, 2)
        }

        # 전환 퍼널
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN likes > 0 OR replies > 0 THEN 1 ELSE 0 END) as engaged,
                SUM(led_to_contact) as contacts,
                SUM(led_to_conversion) as conversions
            FROM posted_comments
            WHERE posted_at >= datetime('now', ?)
        """, (date_offset,))
        funnel_row = cursor.fetchone()
        conversion_funnel = {
            "posted": funnel_row['total'] or 0,
            "engaged": funnel_row['engaged'] or 0,
            "contacted": funnel_row['contacts'] or 0,
            "converted": funnel_row['conversions'] or 0,
            "engagement_rate": round((funnel_row['engaged'] or 0) / (funnel_row['total'] or 1) * 100, 1),
            "contact_rate": round((funnel_row['contacts'] or 0) / (funnel_row['total'] or 1) * 100, 1),
            "conversion_rate": round((funnel_row['conversions'] or 0) / (funnel_row['total'] or 1) * 100, 1)
        }

        # 최근 댓글
        cursor.execute("""
            SELECT
                pc.id, pc.content, pc.platform, pc.url,
                pc.likes, pc.replies, pc.clicks,
                pc.led_to_contact, pc.led_to_conversion,
                pc.posted_at,
                ct.name as template_name
            FROM posted_comments pc
            LEFT JOIN comment_templates ct ON pc.template_id = ct.id
            WHERE pc.posted_at >= datetime('now', ?)
            ORDER BY pc.posted_at DESC
            LIMIT 20
        """, (date_offset,))
        recent = [dict(row) for row in cursor.fetchall()]

        conn.close()

        return {
            "total_comments": total,
            "period_days": days,
            "by_platform": by_platform,
            "by_template": by_template,
            "engagement_summary": engagement_summary,
            "conversion_funnel": conversion_funnel,
            "recent_comments": recent
        }

    except Exception as e:
        print(f"[Comment Performance Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments/list")
async def get_posted_comments(
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
) -> Dict[str, Any]:
    """
    [Phase 7.2] 게시된 댓글 목록 조회

    Args:
        platform: 플랫폼 필터 (선택)
        limit: 조회 수 (기본 50)
        offset: 시작 위치

    Returns:
        댓글 목록
    """
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        _ensure_posted_comments_table(cursor)

        query = """
            SELECT
                pc.id, pc.content, pc.platform, pc.url,
                pc.likes, pc.replies, pc.clicks,
                pc.led_to_contact, pc.led_to_conversion,
                pc.posted_at, pc.status,
                ct.name as template_name,
                vt.title as target_title
            FROM posted_comments pc
            LEFT JOIN comment_templates ct ON pc.template_id = ct.id
            LEFT JOIN viral_targets vt ON pc.target_id = vt.id
            WHERE 1=1
        """
        params = []

        if platform:
            query += " AND pc.platform = ?"
            params.append(platform)

        query += " ORDER BY pc.posted_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        comments = [dict(row) for row in cursor.fetchall()]

        # 총 개수
        count_query = "SELECT COUNT(*) FROM posted_comments WHERE 1=1"
        count_params = []
        if platform:
            count_query += " AND platform = ?"
            count_params.append(platform)

        cursor.execute(count_query, count_params)
        total = cursor.fetchone()[0]

        conn.close()

        return {
            "comments": comments,
            "total": total,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        print(f"[List Comments Error] {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ===========================================================================
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

                if recent_avg > older_avg * 1.3:
                    result["insights"].append({
                        "type": "trend_up",
                        "message": f"최근 3일간 타겟 발견이 {int((recent_avg/older_avg - 1) * 100)}% 증가했습니다.",
                        "importance": "high"
                    })
                elif recent_avg < older_avg * 0.7:
                    result["insights"].append({
                        "type": "trend_down",
                        "message": "최근 타겟 발견이 감소했습니다. 키워드 확장을 고려하세요.",
                        "importance": "medium"
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
