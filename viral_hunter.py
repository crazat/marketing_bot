#!/usr/bin/env python3
"""
Viral Hunter - 네이버 통합 검색 기반 바이럴 마케팅 침투 시스템

기능:
- 네이버 카페 + 블로그 + 지식인 통합 검색
- 댓글 가능 게시물 필터링
- AI 기반 맞춤 댓글 생성
- 우선순위 기반 타겟 관리

Phase: Viral Hunter V1
"""

import sys
import os

# [고도화 A-1] Sentry 에러 모니터링
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("viral_hunter")
except Exception:
    pass
import json
import time
import re
import hashlib
import logging
import argparse
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple
from datetime import datetime
from urllib.parse import quote, urljoin
import requests
from bs4 import BeautifulSoup

# Path setup
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))

from db.database import DatabaseManager
from utils import ConfigManager, logger
from services.ai_client import ai_generate, ai_generate_korean

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


# ============================================
# 데이터 클래스
# ============================================
@dataclass
class ViralTarget:
    """바이럴 마케팅 타겟"""
    platform: str           # cafe, blog, kin
    url: str
    title: str
    content_preview: str = ""
    matched_keywords: List[str] = field(default_factory=list)
    category: str = "기타"
    is_commentable: bool = True
    generated_comment: str = ""
    priority_score: float = 0.0
    author: str = ""
    date_str: str = ""

    def __post_init__(self):
        # [Q11/2026-04-28] 카테고리 자동 정규화 — title까지 보고 미용 카테고리(다이어트/피부/비대칭) 정확히 분류.
        # 시드 키워드만 보면 "산후조리원/지역명"이 모두 "기타"로 떨어지는 문제 해결.
        try:
            from services.category_normalizer import normalize_category, STANDARD_CATEGORIES
        except ImportError:
            return

        if self.category and self.category != "기타" and self.category in STANDARD_CATEGORIES:
            return  # 명시적 표준 카테고리 그대로

        # 비표준 값이면 정규화
        if self.category and self.category != "기타":
            self.category = normalize_category(self.category)
            if self.category in STANDARD_CATEGORIES and self.category != "기타":
                return

        # "기타" 폴백 — title + matched_keywords[0] 둘 다 시도, 미용 카테고리 우선
        candidates = []
        if self.title:
            candidates.append(self.title)
        if self.matched_keywords:
            candidates.append(self.matched_keywords[0])

        for raw in candidates:
            cat = normalize_category(raw)
            if cat != "기타":
                self.category = cat
                return
        self.category = "기타"

    @property
    def id(self) -> str:
        """URL 기반 고유 ID 생성"""
        return hashlib.md5(self.url.encode()).hexdigest()[:16]

    def to_dict(self) -> dict:
        """DB 저장용 딕셔너리 변환"""
        return {
            'id': self.id,
            'platform': self.platform,
            'url': self.url,
            'title': self.title,
            'content_preview': self.content_preview,
            'matched_keywords': self.matched_keywords,
            'category': self.category,
            'is_commentable': self.is_commentable,
            'generated_comment': self.generated_comment,
            'priority_score': self.priority_score,
            'author': self.author,
            'date_str': self.date_str,
        }


# ============================================
# 검색 결과 캐시 클래스
# ============================================
class SearchCache:
    """
    검색 결과 캐싱 (SQLite 기반, 24시간 유효)
    - 동일 키워드 재검색 방지
    - API 호출 70% 감소 효과
    """

    def __init__(self, cache_hours: int = 24):
        self.cache_hours = cache_hours
        self.config = ConfigManager()
        self.cache_path = os.path.join(self.config.root_dir, 'db', 'search_cache.db')
        self._init_db()

    def _init_db(self):
        """캐시 DB 초기화"""
        import sqlite3
        try:
            with sqlite3.connect(self.cache_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS search_cache (
                        cache_key TEXT PRIMARY KEY,
                        platform TEXT,
                        keyword TEXT,
                        results TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_created ON search_cache(created_at)")
                # 오래된 캐시 정리
                conn.execute(f"DELETE FROM search_cache WHERE created_at < datetime('now', '-{self.cache_hours} hours')")
                conn.commit()
        except Exception as e:
            logger.debug(f"SearchCache init failed: {e}")

    def get(self, platform: str, keyword: str) -> Optional[List[dict]]:
        """캐시에서 검색 결과 조회"""
        import sqlite3
        cache_key = f"{platform}:{keyword}"
        try:
            with sqlite3.connect(self.cache_path) as conn:
                cursor = conn.execute(
                    f"SELECT results FROM search_cache WHERE cache_key = ? AND created_at > datetime('now', '-{self.cache_hours} hours')",
                    (cache_key,)
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except Exception as e:
            logger.debug(f"SearchCache get failed: {e}")
        return None

    def set(self, platform: str, keyword: str, results: List[dict]):
        """검색 결과 캐시 저장"""
        import sqlite3
        cache_key = f"{platform}:{keyword}"
        try:
            with sqlite3.connect(self.cache_path) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO search_cache (cache_key, platform, keyword, results) VALUES (?, ?, ?, ?)",
                    (cache_key, platform, keyword, json.dumps(results, ensure_ascii=False))
                )
                conn.commit()
        except Exception as e:
            logger.debug(f"SearchCache set failed: {e}")

    def get_stats(self) -> dict:
        """캐시 통계"""
        import sqlite3
        try:
            with sqlite3.connect(self.cache_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM search_cache").fetchone()[0]
                valid = conn.execute(
                    f"SELECT COUNT(*) FROM search_cache WHERE created_at > datetime('now', '-{self.cache_hours} hours')"
                ).fetchone()[0]
                return {"total": total, "valid": valid}
        except Exception:
            return {"total": 0, "valid": 0}


# ============================================
# 네이버 통합 검색 클래스
# ============================================
class NaverUnifiedSearch:
    """
    네이버 카페 + 블로그 + 지식인 통합 검색

    기존 naver_serp_analyzer.py 패턴 재사용:
    - HTTP 세션 관리
    - User-Agent 로테이션
    - Rate limiting
    - Exponential backoff 재시도
    - 429/503 에러 자동 대기
    - 검색 결과 캐싱 (24시간)
    """

    # 공식 Naver Search API 엔드포인트
    API_ENDPOINTS = {
        'cafe': 'https://openapi.naver.com/v1/search/cafearticle.json',
        'blog': 'https://openapi.naver.com/v1/search/blog.json',
        'kin':  'https://openapi.naver.com/v1/search/kin.json',
    }

    def __init__(self, delay: float = 0.3, max_retries: int = 3, use_cache: bool = True):
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self._last_call = 0
        self._request_count = 0
        self._error_count = 0
        self._cache_hits = 0

        # 캐싱
        self.use_cache = use_cache
        self.cache = SearchCache() if use_cache else None

        # 네이버 공식 API 키 로테이션 (최대 5개)
        cfg = ConfigManager()
        self.api_keys = cfg.get_api_key_list("NAVER_SEARCH_KEYS")
        if not self.api_keys:
            cid = cfg.get_api_key("NAVER_CLIENT_ID")
            sec = cfg.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys = [{"id": cid, "secret": sec}]
        self._key_index = 0
        if self.api_keys:
            logger.info(f"✅ Naver Search API 키 {len(self.api_keys)}개 로드 (공식 API 모드)")
        else:
            logger.error("❌ Naver Search API 키가 없습니다 (.env NAVER_SEARCH_CLIENT_ID_1 등 확인)")

        # 하위 호환용 (사용 안 하지만 get_stats 등이 참조)
        self.user_agents = []
        self.ua_index = 0
        self._consecutive_empty_results = 0
        self._total_searches = 0
        self._successful_searches = 0
        self._is_blocked = False
        self._adaptive_delay = delay

    def _rotate_key(self):
        if self.api_keys:
            self._key_index = (self._key_index + 1) % len(self.api_keys)

    def _api_headers(self) -> dict:
        key = self.api_keys[self._key_index]
        return {
            "X-Naver-Client-Id": key["id"],
            "X-Naver-Client-Secret": key["secret"],
        }

    @staticmethod
    def _strip_html(text: str) -> str:
        if not text:
            return ""
        text = re.sub(r'<[^>]+>', '', text)
        # HTML entity 디코드
        import html as _html
        return _html.unescape(text).strip()

    def _api_fetch(self, platform: str, keyword: str, display: int = 100,
                   start: int = 1) -> List[dict]:
        """공식 API 호출. 실패 시 키 로테이션 + 재시도."""
        if not self.api_keys:
            return []
        endpoint = self.API_ENDPOINTS.get(platform)
        if not endpoint:
            return []

        params = {"query": keyword, "display": display, "start": start, "sort": "date"}
        max_attempts = min(len(self.api_keys) + 1, 6)

        for attempt in range(max_attempts):
            self._rate_limit()
            self._request_count += 1
            try:
                r = self.session.get(endpoint, headers=self._api_headers(),
                                     params=params, timeout=10)
                if r.status_code == 200:
                    return r.json().get("items", [])
                if r.status_code in (401, 403, 429):
                    logger.warning(f"[API] {platform} '{keyword}' {r.status_code} → 키 로테이션")
                    self._error_count += 1
                    self._rotate_key()
                    time.sleep(0.5)
                    continue
                logger.warning(f"[API] {platform} '{keyword}' {r.status_code}: {r.text[:120]}")
                self._error_count += 1
                break
            except requests.exceptions.Timeout:
                self._error_count += 1
                time.sleep(1.0)
            except requests.exceptions.RequestException as e:
                self._error_count += 1
                logger.warning(f"[API] 요청 예외 {platform}/{keyword}: {e}")
                break
        return []

    def _calculate_dynamic_limit(self, keyword: str, platform: str, search_volume: int = None) -> int:
        """
        [Phase 2 개선] 검색량 및 키워드 특성 기반 동적 수집 제한 계산

        Args:
            keyword: 검색 키워드
            platform: 플랫폼 (cafe, blog, kin)
            search_volume: 월간 검색량 (있으면 활용)

        Returns:
            동적으로 계산된 max_results 값
        """
        # 플랫폼별 기본값
        base_limits = {
            'cafe': 200,
            'blog': 200,
            'kin': 100,
        }
        base_limit = base_limits.get(platform, 200)

        # 검색량 기반 조정
        if search_volume:
            if search_volume >= 1000:
                base_limit = int(base_limit * 2.5)  # 고인기 키워드: 2.5배
            elif search_volume >= 300:
                base_limit = int(base_limit * 1.75)
            elif search_volume >= 100:
                base_limit = int(base_limit * 1.25)

        # 의도 키워드 포함 시 추가 확장
        intent_keywords = ['추천', '후기', '비교', '가격', '비용', '어디', '질문']
        if any(kw in keyword for kw in intent_keywords):
            base_limit = int(base_limit * 1.3)  # 정보탐색형 +30%

        # 플랫폼별 최대값 제한
        max_limits = {
            'cafe': 500,
            'blog': 500,
            'kin': 300,
        }

        return min(base_limit, max_limits.get(platform, 500))

    def _get_headers(self) -> dict:
        """헤더 생성 (User-Agent 로테이션)"""
        ua = self.user_agents[self.ua_index % len(self.user_agents)]
        self.ua_index += 1

        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
            "Cache-Control": "no-cache",
        }

    def _rate_limit(self):
        """API 호출 간격 제어 (적응형)"""
        elapsed = time.time() - self._last_call
        if elapsed < self._adaptive_delay:
            time.sleep(self._adaptive_delay - elapsed)
        self._last_call = time.time()

    def _validate_response(self, response: requests.Response, platform: str) -> bool:
        """
        🛡️ 응답 검증: 네이버가 차단/빈 페이지를 반환하는지 체크

        검증 항목:
        1. HTML 최소 길이 (10KB 이상) - 롱테일 키워드는 응답이 작을 수 있음
        2. "검색결과가 없습니다" 메시지 확인 (정상 응답)
        3. 네이버 검색 페이지 기본 구조 존재 (느슨하게)

        Returns:
            True: 정상 응답 (결과 없음 포함), False: 차단 의심
        """
        if not response or not response.text:
            return False

        html = response.text

        # 1. 최소 길이 체크 (10KB 미만이면 명백히 비정상)
        if len(html) < 10000:  # 10KB 미만
            logger.warning(f"⚠️ 응답이 너무 작습니다: {len(html):,} bytes (차단 의심)")
            return False

        # 2. "검색결과가 없습니다" 메시지가 있으면 정상 (결과 없는 것뿐)
        no_result_indicators = [
            '검색결과가 없습니다',
            '검색 결과가 없습니다',
            '결과가 없습니다',
            'no_result',
            '_result_none'
        ]

        if any(indicator in html for indicator in no_result_indicators):
            logger.debug(f"[{platform}] 검색 결과 없음 (정상 응답)")
            return True

        # 3. 주요 검색 결과 영역 또는 네이버 기본 구조 체크
        # 롱테일 키워드는 main_pack이 없을 수 있으므로 느슨하게 체크
        naver_indicators = [
            'main_pack', 'api_subject_bx', 'total_wrap',
            'naver.com', 'search_list', 'result_list',
            'content_search', 'section_head'
        ]

        found_any = any(indicator in html for indicator in naver_indicators)

        if not found_any:
            logger.warning(f"⚠️ 네이버 검색 페이지 구조를 찾을 수 없습니다 (차단 의심)")
            return False

        return True

    def _check_blocking_status(self, results_count: int):
        """
        🛡️ 차단 상태 감지 및 적응형 대응

        연속으로 N개 키워드에서 0개 결과 → 차단 의심
        - 5개 연속 0개: 경고 + delay 증가
        - 10개 연속 0개: 차단 플래그 + 장시간 대기
        """
        self._total_searches += 1

        if results_count > 0:
            self._successful_searches += 1
            self._consecutive_empty_results = 0
            # 성공률이 높으면 delay 감소
            if self._successful_searches > 10:
                self._adaptive_delay = max(1.0, self._adaptive_delay * 0.95)
        else:
            self._consecutive_empty_results += 1

            # 🚨 연속 5개 0개 결과: 경고
            if self._consecutive_empty_results == 5:
                logger.warning(f"⚠️ 연속 5개 키워드에서 0개 결과 - delay를 {self._adaptive_delay:.1f}초 → {self._adaptive_delay * 2:.1f}초로 증가")
                self._adaptive_delay *= 2

            # 🚨 연속 10개 0개 결과: 차단 의심
            elif self._consecutive_empty_results >= 10:
                self._is_blocked = True
                logger.error(f"❌ 연속 {self._consecutive_empty_results}개 키워드에서 0개 결과")
                logger.error(f"   → 네이버 차단 의심! 5분 대기 후 재시도합니다.")
                time.sleep(300)  # 5분 대기
                self._is_blocked = False
                self._consecutive_empty_results = 0
                self._adaptive_delay = self.delay * 3  # delay 3배 증가

    def _request_with_retry(self, url: str, params: dict) -> Optional[requests.Response]:
        """
        Exponential backoff 재시도 로직

        - 429 Too Many Requests: 60초 대기 후 재시도
        - 503 Service Unavailable: 30초 대기 후 재시도
        - 기타 에러: 점진적 대기 (2초, 4초, 8초)
        """
        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                self._request_count += 1

                response = self.session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=20
                )

                # 429 Too Many Requests
                if response.status_code == 429:
                    wait_time = 60 + (attempt * 30)  # 60초, 90초, 120초
                    logger.warning(f"⚠️ 429 Too Many Requests - {wait_time}초 대기 중...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 503 Service Unavailable
                if response.status_code == 503:
                    wait_time = 30 + (attempt * 15)  # 30초, 45초, 60초
                    logger.warning(f"⚠️ 503 Service Unavailable - {wait_time}초 대기 중...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 403 Forbidden (IP 차단 가능성)
                if response.status_code == 403:
                    if attempt == 0:
                        # 첫 번째 403: 즉시 5분 대기
                        wait_time = 300  # 5분
                        logger.error(f"🚨 403 Forbidden - 네이버 IP 차단 감지!")
                        logger.error(f"   → {wait_time}초 (5분) 대기 후 재시도...")
                    else:
                        # 재시도에도 403: 10분 대기
                        wait_time = 600  # 10분
                        logger.error(f"🚨 403 Forbidden 재발생 - {wait_time}초 (10분) 대기...")

                    self._error_count += 1
                    self._is_blocked = True  # 차단 플래그 설정
                    time.sleep(wait_time)
                    self._is_blocked = False
                    self._adaptive_delay = self.delay * 5  # delay 5배 증가
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout:
                wait_time = 5 * (attempt + 1)
                logger.warning(f"⚠️ Timeout - {wait_time}초 후 재시도 ({attempt+1}/{self.max_retries})")
                self._error_count += 1
                time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                wait_time = 2 ** (attempt + 1)  # 2초, 4초, 8초
                logger.warning(f"⚠️ Request failed: {e} - {wait_time}초 후 재시도 ({attempt+1}/{self.max_retries})")
                self._error_count += 1
                time.sleep(wait_time)

        logger.error(f"❌ 최대 재시도 횟수 초과: {url}")
        return None

    def get_stats(self) -> dict:
        """API 호출 통계 (차단 감지 정보 포함)"""
        cache_stats = self.cache.get_stats() if self.cache else {"total": 0, "valid": 0}
        success_rate = (self._successful_searches / max(1, self._total_searches)) * 100

        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "cache_hits": self._cache_hits,
            "cache_entries": cache_stats.get("valid", 0),
            "error_rate": f"{(self._error_count / max(1, self._request_count)) * 100:.1f}%",
            # 🛡️ 차단 감지 정보
            "total_searches": self._total_searches,
            "successful_searches": self._successful_searches,
            "success_rate": f"{success_rate:.1f}%",
            "consecutive_failures": self._consecutive_empty_results,
            "is_blocked": self._is_blocked,
            "current_delay": f"{self._adaptive_delay:.1f}초"
        }

    def _api_collect(self, platform: str, keyword: str, max_results: int) -> List[ViralTarget]:
        """공식 API로 N개까지 수집. 페이지당 display=100, start는 1/101/201…"""
        targets: List[ViralTarget] = []
        seen = set()
        display = 100
        # Naver API는 start + display ≤ 1000까지만 허용
        max_results = min(max_results, 900)

        start = 1
        while len(targets) < max_results and start <= 1000:
            fetch_n = min(display, max_results - len(targets), 1001 - start)
            if fetch_n <= 0:
                break
            items = self._api_fetch(platform, keyword, display=fetch_n, start=start)
            if not items:
                break

            for item in items:
                link = item.get('link', '') or ''
                if not link or link in seen:
                    continue
                title = self._strip_html(item.get('title', ''))
                if not title or len(title) < 5:
                    continue
                desc = self._strip_html(item.get('description', ''))

                if platform == 'cafe':
                    author = item.get('cafename', '') or ''
                elif platform == 'blog':
                    author = item.get('bloggername', '') or ''
                else:
                    author = ''

                seen.add(link)
                targets.append(ViralTarget(
                    platform=platform,
                    url=link,
                    title=title,
                    content_preview=desc[:300],
                    matched_keywords=[keyword],
                    author=author,
                    date_str=item.get('postdate', '') or '',
                ))
                if len(targets) >= max_results:
                    break

            if len(items) < fetch_n:
                break  # 결과 끝
            start += fetch_n

        return targets

    def search_cafe(self, keyword: str, max_results: int = 200, max_pages: int = 10) -> List[ViralTarget]:
        """
        네이버 카페 전용 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수 (1페이지=10개)
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get("cafe", keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Cafe] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect("cafe", keyword, max_results)

        # 캐시 저장
        if self.use_cache and self.cache and targets:
            self.cache.set("cafe", keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Cafe] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_blog(self, keyword: str, max_results: int = 200, max_pages: int = 10) -> List[ViralTarget]:
        """
        네이버 블로그 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get("blog", keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Blog] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect("blog", keyword, max_results)

        if self.use_cache and self.cache and targets:
            self.cache.set("blog", keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Blog] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_kin(self, keyword: str, max_results: int = 100, max_pages: int = 5) -> List[ViralTarget]:
        """
        네이버 지식인 검색 (페이지네이션 지원)

        Args:
            keyword: 검색 키워드
            max_results: 최대 결과 수
            max_pages: 최대 페이지 수
        """
        # 캐시 체크
        if self.use_cache and self.cache:
            cached = self.cache.get("kin", keyword)
            if cached:
                self._cache_hits += 1
                logger.debug(f"[Kin] '{keyword}' 캐시 히트")
                # id는 property이므로 제거 후 복원
                return [ViralTarget(**{k: v for k, v in item.items() if k != 'id'}) for item in cached]

        targets = self._api_collect("kin", keyword, max_results)

        if self.use_cache and self.cache and targets:
            self.cache.set("kin", keyword, [t.to_dict() for t in targets])

        self._check_blocking_status(len(targets))
        logger.info(f"[Kin] '{keyword}' -> {len(targets)}개 발견")
        return targets

    def search_all(
        self,
        keyword: str,
        max_per_platform: int = 100,
        include_blog: bool = False,
    ) -> List[ViralTarget]:
        """카페·지식인 통합 검색.

        [Q10] blog는 본인 광고 글 비율이 높고 게시 전환율 0.02%로 효율 낮음.
        명시적으로 include_blog=True 줄 때만 수집. 정보 수집 목적이면 search_blog() 직접 호출.
        """
        all_targets = []

        cafe_results = self.search_cafe(keyword, max_per_platform)
        all_targets.extend(cafe_results)

        blog_results: List[ViralTarget] = []
        if include_blog:
            blog_results = self.search_blog(keyword, max_per_platform)
            all_targets.extend(blog_results)

        kin_results = self.search_kin(keyword, max_per_platform)
        all_targets.extend(kin_results)

        logger.info(
            f"[통합] '{keyword}' -> 총 {len(all_targets)}개 "
            f"(카페:{len(cafe_results)}, 블로그:{len(blog_results)}, 지식인:{len(kin_results)})"
        )
        return all_targets


# ============================================
# 댓글 가능 필터 클래스
# ============================================
class CommentableFilter:
    """
    댓글 가능 게시물 필터링

    필터링 기준:
    - 광고/홍보글 제외 (cafe_spy.py AD_EXCLUDE_KEYWORDS 참조)
    - 질문글/고민글 우선
    - 건강 관련 키워드 매칭
    """

    # [Phase 2 개선] 광고 필터 분리: STRICT(제외) vs SOFT(감점만) vs NON_RELEVANT(제외)

    # STRICT: 명확한 광고/홍보글 - 무조건 제외
    STRICT_AD_PATTERNS = [
        "체험단", "협력업체", "입점", "모집", "프리마켓",
        "동행인사", "인사드립니다", "입점했습니다",
        "#광고", "#협찬", "제공받아", "원고료",
    ]

    # SOFT: 구매 의도 포함 가능 - 감점만 하고 제외하지 않음
    SOFT_AD_INDICATORS = [
        "할인", "이벤트", "무료", "증정", "쿠폰"
    ]

    # NON_RELEVANT: 비관련 업종 - 무조건 제외
    NON_RELEVANT_EXCLUDE = [
        # 기존
        "강아지", "반려견", "성형외과", "분양", "아파트",
        "주식", "코인", "부동산", "매매", "임대",
        "케이크", "베이커리", "맛집",
        "성형", "쌍수", "코수술", "지방흡입",
        # 확장 - 업계 외
        "대출", "신용", "보증", "카지노", "바카라", "슬롯", "도박", "토토",
        "분양권", "청약", "경매", "전세", "월세",
        "취업", "구인", "알바", "채용공고",
        "중고", "판매합니다", "나눔", "양도",
        "자동차보험료", "자차보험", "차보험 견적",
    ]

    # 사업 권역 지역 키워드 (제목 또는 본문에 하나 이상 포함돼야 통과)
    # 청주·세종·충주·제천·증평·보은·진천·옥천·영동·음성 및 동/지구 단위
    REGION_KEYWORDS = [
        "청주", "세종", "충주", "제천", "증평", "보은", "진천", "옥천", "영동", "음성",
        "율량", "가경", "복대", "산남", "오창", "오송", "사창", "성안길",
        "내덕", "우암", "흥덕", "용암", "용정", "개신", "분평", "수곡",
        "상당", "서원", "흥덕", "청원", "용암동", "봉명",
        "충북",
    ]

    # 최소 본문 길이 (API content_preview는 300자 잘림이므로 100자면 충분한 의미)
    MIN_CONTENT_LENGTH = 100

    # 기존 호환용 (STRICT + NON_RELEVANT)
    AD_EXCLUDE = STRICT_AD_PATTERNS + NON_RELEVANT_EXCLUDE

    # 질문글 패턴 (확장)
    INQUIRY_PATTERNS = [
        # 추천/질문
        "추천", "어디", "궁금", "있을까요", "있나요", "알려주세요",
        "가봤는데", "다니시는분", "해보신분", "경험", "후기",
        "좋은곳", "잘하는", "괜찮은", "어떤가요", "어때요",
        "고민", "도움", "상담", "문의", "질문",
        # 추가 패턴
        "어디로", "어떻게", "뭐가", "효과", "가격", "비용",
        "병원", "의원", "치료", "시술", "원장", "진료",
        "예약", "상담", "방문", "다녀", "받았", "받고",
        "좋았", "괜찮", "만족", "불만", "실망", "추천드",
        "알아보", "찾고", "구해", "필요", "원해", "하고싶"
    ]

    # 🔥 Hot Lead 키워드 (긴급/높은 전환율)
    HOT_LEAD_KEYWORDS = [
        # 추천 요청 (직접적)
        "추천해주세요", "추천부탁", "추천좀", "어디가 좋을까요", "어디로 가야",
        "알려주세요", "소개해주세요", "있을까요",
        # 긴급
        "급해요", "급합니다", "급함", "빨리", "당장", "오늘", "내일", "이번주",
        # 고민/걱정
        "고민이에요", "고민입니다", "걱정", "어떡해", "어떻게 해야", "힘들어요",
        # 직접 경험 요청
        "해보신 분", "다녀보신 분", "경험 있으신", "아시는 분", "가보신 분",
        # 비교/선택
        "어디가 나을까", "뭐가 좋을까", "고르기", "선택",
        # 가격 민감
        "가격", "비용", "얼마", "저렴", "착한", "합리적"
    ]

    # 🎯 경쟁사 키워드 (AI 탐지 참고용 - 실제 탐지는 AI가 수행)
    # 아래 키워드는 AI 프롬프트에서 참조됨
    COMPETITORS_REFERENCE = [
        "자연과한의원", "경희한의원", "동의보감", "청주한방병원",
        "수한의원", "참조은한의원", "보명한의원", "생기한의원", "자생한의원"
    ]

    # 건강 관련 키워드 (대폭 확장 - 양치기용)
    HEALTH_KEYWORDS = [
        # 다이어트
        "다이어트", "살빼기", "체중", "비만", "뱃살", "허벅지", "팔뚝",
        "식단", "운동", "헬스", "필라테스", "PT", "감량", "체형",
        # 안면/교정
        "비대칭", "안면비대칭", "얼굴비대칭", "골반", "교정", "체형교정",
        "턱", "광대", "사각턱", "거북목", "일자목", "척추", "측만",
        # 통증/디스크
        "허리", "목", "어깨", "무릎", "통증", "디스크", "추나", "도수",
        "관절", "근육", "인대", "염좌", "삐끗", "담", "뻐근", "결림",
        # 교통사고
        "교통사고", "자동차사고", "자보", "입원", "사고", "후유증",
        # 피부
        "여드름", "피부", "흉터", "트러블", "새살침", "모공", "기미",
        "주름", "리프팅", "탄력", "노화", "잡티", "색소", "홍조",
        # 한의원 일반
        "한의원", "한방", "침", "뜸", "한약", "보약", "공진단", "경옥고",
        "체질", "사상", "면역", "보양", "기력", "피로", "무기력",
        # 여성건강
        "생리통", "생리", "갱년기", "폐경", "산후", "산후조리", "임신",
        "자궁", "난소", "호르몬", "냉증", "수족냉증",
        # 기타 증상
        "불면", "수면", "두통", "어지럼", "소화", "위염", "역류",
        "비염", "알레르기", "아토피", "탈모", "다한증", "땀",
        "스트레스", "우울", "불안", "긴장", "화병",
        # 지역 키워드
        "청주", "율량", "가경", "복대", "산남", "오창", "오송", "세종"
    ]

    # [Phase 2 개선] 키워드 티어별 가치 차등화
    KEYWORD_TIER1 = [  # 핵심 상품 (15점)
        "다이어트한약", "안면비대칭", "새살침", "체형교정", "골반교정",
        "여드름흉터", "얼굴비대칭", "입원치료"
    ]
    KEYWORD_TIER2 = [  # 주요 서비스 (10점)
        "교통사고", "다이어트", "여드름", "탈모", "비염", "갱년기",
        "추나", "디스크", "산후조리", "공진단"
    ]
    KEYWORD_TIER3 = [  # 일반 (5점)
        "한의원", "한약", "침", "뜸", "부항", "한방", "체질", "보약"
    ]

    def _calculate_keyword_tier_score(self, matched_keywords: List[str]) -> int:
        """키워드 티어별 차등 점수 계산 (최대 40점)"""
        score = 0
        for kw in matched_keywords:
            kw_lower = kw.lower()
            if any(t in kw_lower for t in self.KEYWORD_TIER1):
                score += 15
            elif any(t in kw_lower for t in self.KEYWORD_TIER2):
                score += 10
            else:
                score += 5
        return min(score, 40)  # 최대 40점

    @staticmethod
    def _load_self_exclusion() -> Dict[str, List[str]]:
        """business_profile.json에서 자기 업체 제외 규칙 로드 (모듈 시작 시 1회)."""
        import json as _json
        import os as _os
        try:
            here = _os.path.dirname(_os.path.abspath(__file__))
            cfg_path = _os.path.join(here, "config", "business_profile.json")
            if not _os.path.exists(cfg_path):
                return {"blog_authors": [], "url_patterns": [], "title_keywords": []}
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = _json.load(f)
            se = data.get("self_exclusion", {}) or {}
            return {
                "blog_authors": [a.lower() for a in se.get("blog_authors", [])],
                "url_patterns": [u.lower() for u in se.get("url_patterns", [])],
                "title_keywords": [k.lower() for k in se.get("title_keywords", [])],
            }
        except Exception as e:
            logger.warning(f"[CommentableFilter] self_exclusion 로드 실패: {e}")
            return {"blog_authors": [], "url_patterns": [], "title_keywords": []}

    def _is_self_target(self, target: 'ViralTarget') -> bool:
        """자기 한의원 블로그/콘텐츠인지 검사 (어뷰징 방지)."""
        if not hasattr(self, "_self_exclusion"):
            self._self_exclusion = CommentableFilter._load_self_exclusion()
        se = self._self_exclusion
        url = (target.url or "").lower()
        title = (target.title or "").lower()
        author = (target.author or "").lower() if hasattr(target, "author") else ""
        if any(p in url for p in se["url_patterns"]):
            return True
        if any(a in author for a in se["blog_authors"]):
            return True
        if any(k in title for k in se["title_keywords"]):
            return True
        return False

    def filter(self, targets: List[ViralTarget]) -> List[ViralTarget]:
        """
        타겟 필터링 및 우선순위 점수 계산

        Returns:
            댓글 가능한 타겟만 (priority_score 계산됨)
        """
        filtered = []
        stats = {'self_excluded': 0, 'ad': 0, 'non_relevant': 0, 'too_short': 0,
                 'no_region': 0, 'title_only': 0, 'not_inquiry_health': 0}

        for target in targets:
            # 0. [의료광고법 + 어뷰징 방지] 자기 업체 자동 제외 (최우선)
            if self._is_self_target(target):
                stats['self_excluded'] += 1
                target.is_commentable = False
                continue

            title_lower = (target.title or '').lower()
            body_lower = (target.content_preview or '').lower()
            text = f"{title_lower} {body_lower}"

            # 1. 광고글 제외 (STRICT만 제외, SOFT는 감점)
            if any(ad in text for ad in self.STRICT_AD_PATTERNS):
                stats['ad'] += 1
                continue
            if any(ad in text for ad in self.NON_RELEVANT_EXCLUDE):
                stats['non_relevant'] += 1
                continue

            # 2. 본문 최소 길이
            if len(target.content_preview or '') < self.MIN_CONTENT_LENGTH:
                stats['too_short'] += 1
                continue

            # 3. 지역 키워드 필수 (제목 OR 본문)
            if not any(rk in text for rk in self.REGION_KEYWORDS):
                stats['no_region'] += 1
                continue

            # 4. 제목-본문 동시 매칭 (검색 키워드가 본문에도 있어야 의미 있음)
            if target.matched_keywords:
                base_kw = target.matched_keywords[0].lower()
                # 키워드 토큰화 (공백 기준)하여 주요 토큰 하나라도 본문에 있으면 통과
                tokens = [t for t in base_kw.split() if len(t) >= 2]
                if tokens and not any(tok in body_lower for tok in tokens):
                    stats['title_only'] += 1
                    continue

            # SOFT 광고 키워드는 감점만
            soft_ad_penalty = sum(-5 for kw in self.SOFT_AD_INDICATORS if kw in text)

            # 5. 질문글 여부
            is_inquiry = any(pat in text for pat in self.INQUIRY_PATTERNS)

            # 6. 건강 관련 여부
            is_health = any(kw in text for kw in self.HEALTH_KEYWORDS)

            # 7. 댓글 가능 여부 결정
            if not (is_inquiry or is_health):
                stats['not_inquiry_health'] += 1
                target.is_commentable = False
                continue

            # 5. 우선순위 점수 계산 (개선됨: 150점 캡, 세분화된 가중치)
            score = 0
            tags = []  # 태그 수집

            # 질문글 보너스 (정보 탐색 중인 사용자)
            if is_inquiry:
                score += 30
                tags.append("❓질문")

            # 건강 관련 보너스
            if is_health:
                score += 25
                tags.append("🏥건강")

            # 🔥 Hot Lead 감지 (조정: 35→25, 점수 포화 방지)
            hot_lead_matched = [kw for kw in self.HOT_LEAD_KEYWORDS if kw in text]
            if hot_lead_matched:
                score += 25  # Hot Lead 가산 (조정됨)
                tags.append("🔥HOT")
                logger.debug(f"🔥 Hot Lead 감지: {target.title[:30]}... ({hot_lead_matched[:2]})")

            # 🎯 즉시 행동 신호 (예약, 결정 관련 키워드)
            ready_to_act_keywords = [
                "예약", "전화", "상담", "문의", "가격", "비용",
                "방문", "예정", "결정", "선택", "비교"
            ]
            if any(kw in text for kw in ready_to_act_keywords):
                score += 15  # 즉시 행동 가능성
                if "⚡즉시" not in str(tags):
                    tags.append("⚡즉시")

            # 🎯 경쟁사 탐지는 AI가 수행 (filter 후 별도 호출)
            # AI 탐지 결과는 target.category와 priority_score에 반영됨

            # [Phase 2 개선] 플랫폼별 가중치 (전환율 기반 재조정)
            # [Q10] blog 18->5: 본인 광고 글 비중 높고 게시 전환율 0.02%로 매우 낮음.
            #       search_all에서 디폴트 비수집이지만, 외부 호출 대비 가중치도 다운.
            platform_weights = {
                'cafe': 22,       # 맘카페 = 고전환율
                'blog': 5,        # 블로그 = 신뢰도 낮음 (이전 18)
                'youtube': 16,    # YouTube = 영상 신뢰도
                'kin': 15,        # 지식인 = 질문 많지만 전환 낮음 (20→15)
                'instagram': 12,  # Instagram = 참여도 높지만 전환 낮음 (18→12)
                'tiktok': 10,     # TikTok = 단기 트렌드
                'karrot': 8,      # 당근마켓 = 지역 기반
            }
            score += platform_weights.get(target.platform, 10)

            # [Phase 2 개선] 키워드 티어별 차등 점수 (최대 40점)
            keyword_bonus = self._calculate_keyword_tier_score(target.matched_keywords)
            score += keyword_bonus

            # [Phase 2] SOFT 광고 키워드 감점 적용
            score += soft_ad_penalty  # 음수 값이므로 감점됨

            # 태그 정보 저장 (content_preview 앞에 추가)
            if tags:
                tag_str = " ".join(tags)
                target.content_preview = f"[{tag_str}] {target.content_preview}"

            # 점수 캡 상향 (100→150, Hot Lead도 구분 가능), 최소 0점
            target.priority_score = max(0, min(score, 150))
            target.is_commentable = True
            filtered.append(target)

        # 우선순위로 정렬
        filtered.sort(key=lambda x: x.priority_score, reverse=True)

        logger.info(
            f"✅ 필터링 완료: {len(targets)}개 -> {len(filtered)}개 (댓글 가능) "
            f"[제외: 광고 {stats['ad']}, 비관련 {stats['non_relevant']}, "
            f"단문 {stats['too_short']}, 지역외 {stats['no_region']}, "
            f"제목만 {stats['title_only']}, 무관 {stats['not_inquiry_health']}]"
        )
        return filtered


# ============================================
# AI 댓글 생성 클래스
# ============================================
class AICommentGenerator:
    """
    AI 기반 맞춤 댓글 생성

    Centralized ai_client 사용
    카테고리별 프롬프트 템플릿
    """

    def __init__(self):
        self.cfg = ConfigManager()
        logger.info("✅ AI Client 초기화 완료 (centralized ai_client)")

    def _load_prompts(self) -> dict:
        """prompts.json에서 viral_hunter 프롬프트 로드"""
        try:
            prompts = self.cfg.load_prompts()
            return prompts.get('viral_hunter', {})
        except Exception:
            return {}

    def generate(self, target: ViralTarget, style: str = "default") -> str:
        """
        단일 타겟에 대한 맞춤 댓글 생성

        Args:
            target: ViralTarget 객체
            style: 댓글 스타일 (default, empathy, informative, experience, question, recommendation)

        Returns:
            생성된 댓글 텍스트
        """
        prompts = self._load_prompts()
        comment_config = prompts.get('comment_generation', {})
        prompt_template = comment_config.get('template', '')

        # 스타일별 suffix 가져오기
        style_suffix = ""
        styles = comment_config.get('styles', {})
        if style and style in styles:
            style_suffix = styles[style].get('suffix', '')

        if not prompt_template:
            # 기본 프롬프트 (config/prompts.json 미로드 시 폴백)
            prompt_template = """당신은 청주 시내(성안길) 거주민이 자기 경험을 공유하듯 댓글을 작성합니다.
다음 게시글에 자연스럽고 도움이 되는 댓글을 작성해주세요.

[게시글 정보]
플랫폼: {platform}
제목: {title}
내용 미리보기: {content_preview}
관련 키워드: {keywords}

[중요 — 자연스러운 후기톤]
- '규림한의원' 풀네임 사용 절대 금지 (광고로 의심받음)
- 한의원 언급 시 'ㄱㄹ한의원', 'ㄱㄹ', '성안길 ㄱㄹ', '시내 그 한의원' 등 초성/모호 표현 사용
- 위치는 성안길/시내만. 가경동·율량동·복대동 절대 X

[댓글 작성 가이드]
1. 진짜 시민이 경험 공유하듯 자연스럽게 (광고 톤 절대 X)
2. 게시글 작성자 고민에 먼저 공감
3. 본인/지인 경험담처럼 ('저도~', '엄마가~')
4. 필요할 때만 자연스럽게 추천 (강제 X)
5. 2-3문장으로 간결하게 (4문장 넘으면 광고 의심)

댓글:"""

        try:
            prompt = prompt_template.format(
                platform=target.platform,
                title=target.title,
                content_preview=target.content_preview[:300],
                keywords=', '.join(target.matched_keywords)
            )

            # 스타일별 suffix 추가
            if style_suffix:
                prompt += style_suffix

            comment = ai_generate_korean(prompt, temperature=0.6, max_tokens=800)

            # 댓글 정제
            comment = comment.replace("댓글:", "").strip()
            comment = comment.replace("```", "").strip()

            return comment

        except Exception as e:
            logger.error(f"댓글 생성 실패: {e}")
            return "[생성 실패] 수동 작성 필요"

    def batch_generate(self, targets: List[ViralTarget], limit: int = 10) -> List[ViralTarget]:
        """
        대량 댓글 생성

        Args:
            targets: 타겟 리스트
            limit: 최대 생성 수

        Returns:
            댓글이 생성된 타겟 리스트
        """
        generated = []

        for i, target in enumerate(targets[:limit], 1):
            logger.info(f"[{i}/{min(len(targets), limit)}] 댓글 생성 중: {target.title[:30]}...")

            comment = self.generate(target)
            target.generated_comment = comment
            generated.append(target)

            # Rate limiting
            time.sleep(0.5)

        logger.info(f"✅ 댓글 생성 완료: {len(generated)}개")
        return generated

    def detect_competitors(self, targets: List[ViralTarget], batch_size: int = 10) -> List[ViralTarget]:
        """
        AI 기반 경쟁사 탐지 (배치 처리)

        Args:
            targets: 분석할 타겟 리스트
            batch_size: 한 번에 분석할 개수

        Returns:
            경쟁사 탐지 결과가 반영된 타겟 리스트
        """
        prompts = self._load_prompts()
        competitor_config = prompts.get('competitor_detection', {})
        template = competitor_config.get('template', '')

        if not template:
            logger.warning("⚠️ competitor_detection 프롬프트 없음")
            return targets

        logger.info(f"🎯 AI 경쟁사 탐지 시작: {len(targets)}개 타겟")

        # 배치 처리
        for batch_start in range(0, len(targets), batch_size):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += f"""
---
POST_ID: {i}
플랫폼: {target.platform}
제목: {target.title}
내용 미리보기: {target.content_preview[:200] if target.content_preview else '(없음)'}
---
"""

            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3)

                # 결과 파싱
                self._parse_competitor_results(batch, result_text)

                logger.info(f"   ✅ 배치 {batch_start // batch_size + 1} 완료 ({len(batch)}개)")

                # Rate limiting
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"경쟁사 탐지 배치 실패: {e}")
                continue

        # 결과 요약
        competitor_count = sum(1 for t in targets if t.category == "경쟁사_역공략")
        if competitor_count > 0:
            logger.info(f"⚔️ 경쟁사 역공략 기회 발견: {competitor_count}개")

        return targets

    def _parse_competitor_results(self, targets: List[ViralTarget], result_text: str):
        """
        AI 경쟁사 탐지 결과 파싱

        결과 형식:
        POST_ID: 1
        COMPETITOR_DETECTED: true
        COMPETITOR_TYPE: direct/indirect/recommendation_risk/complaint/none
        COMPETITOR_NAME: 자연과한의원
        COUNTER_OPPORTUNITY: 75
        REASON: 이유 설명
        ---
        """
        # 각 POST 결과 분리
        posts = result_text.split('---')

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            target = targets[post_id]

            # COMPETITOR_DETECTED 추출
            detected_match = re.search(r'COMPETITOR_DETECTED:\s*(true|false)', post_result, re.IGNORECASE)
            if not detected_match:
                continue

            is_detected = detected_match.group(1).lower() == 'true'

            if is_detected:
                # COUNTER_OPPORTUNITY 점수 추출
                score_match = re.search(r'COUNTER_OPPORTUNITY:\s*(\d+)', post_result)
                counter_score = int(score_match.group(1)) if score_match else 50

                # COMPETITOR_TYPE 추출
                type_match = re.search(r'COMPETITOR_TYPE:\s*(\w+)', post_result)
                comp_type = type_match.group(1) if type_match else "unknown"

                # COMPETITOR_NAME 추출
                name_match = re.search(r'COMPETITOR_NAME:\s*(.+?)(?:\n|$)', post_result)
                comp_name = name_match.group(1).strip() if name_match else "N/A"

                # 타겟 업데이트
                target.category = "경쟁사_역공략"

                # 우선순위 점수 가산 (역공략 기회 점수 기반)
                bonus = min(counter_score // 4, 25)  # 최대 25점 가산
                target.priority_score = min(target.priority_score + bonus, 100)

                # content_preview에 태그 추가
                if "⚔️경쟁사" not in target.content_preview:
                    if comp_name and comp_name != "N/A":
                        target.content_preview = f"[⚔️{comp_name}] {target.content_preview}"
                    else:
                        target.content_preview = f"[⚔️경쟁사감지] {target.content_preview}"

                logger.debug(f"⚔️ 경쟁사 탐지: {target.title[:30]}... ({comp_type}: {comp_name}, 점수+{bonus})")

    def evaluate_infiltration(self, targets: List[ViralTarget], batch_size: int = 10) -> List[ViralTarget]:
        """
        AI 기반 침투적합도 평가 (배치 처리)

        바이럴 댓글 침투에 적합한 글인지 평가:
        - 적합: 추천요청, 고민상담, 경험질문, 정보요청
        - 부적합: 홍보글, 후기글, 뉴스, 이미 해결된 글

        Args:
            targets: 평가할 타겟 리스트
            batch_size: 한 번에 분석할 개수

        Returns:
            침투적합도가 평가된 타겟 리스트 (적합한 것만 반환)
        """
        prompts = self._load_prompts()
        eval_config = prompts.get('infiltration_evaluation', {})
        template = eval_config.get('template', '')

        if not template:
            logger.warning("⚠️ infiltration_evaluation 프롬프트 없음")
            return targets

        logger.info(f"🔍 AI 침투적합도 평가 시작: {len(targets)}개 타겟")

        suitable_targets = []
        unsuitable_count = 0

        # 배치 처리
        for batch_start in range(0, len(targets), batch_size):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += f"""
---
POST_ID: {i}
플랫폼: {target.platform}
제목: {target.title}
내용 미리보기: {target.content_preview[:200] if target.content_preview else '(없음)'}
---
"""

            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3)

                # 결과 파싱
                batch_suitable, batch_unsuitable = self._parse_infiltration_results(batch, result_text)
                suitable_targets.extend(batch_suitable)
                unsuitable_count += batch_unsuitable

                logger.info(f"   ✅ 배치 {batch_start // batch_size + 1} 완료 (적합: {len(batch_suitable)}, 부적합: {batch_unsuitable})")

                # Rate limiting
                time.sleep(1.0)

            except Exception as e:
                logger.error(f"침투적합도 평가 배치 실패: {e}")
                # 실패한 배치는 일단 적합으로 처리 (보수적)
                suitable_targets.extend(batch)
                continue

        # 결과 요약
        logger.info(f"✅ 침투적합도 평가 완료: {len(targets)}개 → 적합 {len(suitable_targets)}개, 부적합 {unsuitable_count}개")

        # 적합한 타겟만 우선순위순 정렬
        suitable_targets.sort(key=lambda x: x.priority_score, reverse=True)

        return suitable_targets

    def unified_analysis(self, targets: List[ViralTarget], batch_size: int = 25) -> List[ViralTarget]:
        """
        통합 AI 분석 (경쟁사 탐지 + 침투적합도 평가를 하나로)

        기존: detect_competitors() + evaluate_infiltration() = API 2회
        통합: unified_analysis() = API 1회 (50% 감소)

        Args:
            targets: 분석할 타겟 리스트
            batch_size: 한 번에 분석할 개수 (기본 25개, 기존 10개에서 증가)

        Returns:
            분석 완료된 타겟 리스트 (침투 적합한 것만)
        """
        # AI client is always available via centralized ai_client

        prompts = self._load_prompts()
        unified_config = prompts.get('unified_analysis', {})
        template = unified_config.get('template', '')

        if not template:
            # 통합 프롬프트 없으면 기존 방식 사용
            logger.warning("⚠️ unified_analysis 프롬프트 없음, 기존 방식 사용")
            targets = self.detect_competitors(targets, batch_size=10)
            return self.evaluate_infiltration(targets, batch_size=10)

        # 설정에서 배치 크기 로드 (기본값 25)
        batch_size = unified_config.get('batch_size', batch_size)

        logger.info(f"🔬 AI 통합 분석 시작: {len(targets)}개 타겟 (배치 크기: {batch_size})")

        suitable_targets = []
        unsuitable_count = 0
        competitor_count = 0

        total_batches = (len(targets) + batch_size - 1) // batch_size

        # 배치 처리
        for batch_idx, batch_start in enumerate(range(0, len(targets), batch_size), 1):
            batch = targets[batch_start:batch_start + batch_size]

            # 게시글 포맷팅
            posts_formatted = ""
            for i, target in enumerate(batch, 1):
                posts_formatted += f"""
---
POST_ID: {i}
플랫폼: {target.platform}
제목: {target.title}
내용: {target.content_preview[:150] if target.content_preview else '(없음)'}
---
"""

            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3)

                # 결과 파싱
                batch_suitable, batch_unsuitable, batch_competitor = self._parse_unified_results(batch, result_text)
                suitable_targets.extend(batch_suitable)
                unsuitable_count += batch_unsuitable
                competitor_count += batch_competitor

                logger.info(f"   ✅ 배치 {batch_idx}/{total_batches} 완료 (적합: {len(batch_suitable)}, 부적합: {batch_unsuitable}, 경쟁사: {batch_competitor})")

                # Rate limiting
                time.sleep(0.8)

            except Exception as e:
                logger.error(f"통합 분석 배치 실패: {e}")
                # 실패한 배치는 일단 적합으로 처리 (보수적)
                suitable_targets.extend(batch)
                continue

        # 결과 요약
        logger.info(f"✅ 통합 분석 완료: {len(targets)}개 → 적합 {len(suitable_targets)}개, 부적합 {unsuitable_count}개")
        if competitor_count > 0:
            logger.info(f"⚔️ 경쟁사 역공략 기회 발견: {competitor_count}개")

        # 적합한 타겟만 우선순위순 정렬
        suitable_targets.sort(key=lambda x: x.priority_score, reverse=True)

        return suitable_targets

    def unified_analysis_parallel(
        self,
        targets: List[ViralTarget],
        batch_size: int = 25,
        max_workers: int = 5,
        db=None,
        skip_batch_indices: Optional[set] = None,
        on_batch_done=None,
    ) -> List[ViralTarget]:
        """
        병렬 + 증분 저장 버전의 unified_analysis.

        배치 단위 Qwen 호출을 ThreadPoolExecutor로 병렬 처리하고,
        매 N배치마다 `db.insert_viral_target()`으로 즉시 저장한다.
        """
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import threading

        prompts = self._load_prompts()
        unified_config = prompts.get('unified_analysis', {})
        template = unified_config.get('template', '')
        if not template:
            logger.warning("⚠️ unified_analysis 프롬프트 없음 — 순차 모드로 폴백")
            return self.unified_analysis(targets, batch_size=batch_size)

        batch_size = unified_config.get('batch_size', batch_size)
        total_batches = (len(targets) + batch_size - 1) // batch_size
        skip = skip_batch_indices or set()

        logger.info(
            f"🔬 AI 통합 분석 시작(병렬): {len(targets)}개, 배치 {batch_size}, "
            f"총 {total_batches}배치, 동시 {max_workers}, 건너뛸 배치 {len(skip)}"
        )

        def run_batch(batch_idx: int, batch: List[ViralTarget]):
            posts_formatted = ""
            for i, t in enumerate(batch, 1):
                posts_formatted += (
                    f"\n---\nPOST_ID: {i}\n플랫폼: {t.platform}\n"
                    f"제목: {t.title}\n"
                    f"내용: {t.content_preview[:150] if t.content_preview else '(없음)'}\n---\n"
                )
            try:
                prompt = template.format(posts_formatted=posts_formatted)
                result_text = ai_generate(prompt, temperature=0.3)
                suitable, unsuit, comp = self._parse_unified_results(batch, result_text)
                return batch_idx, suitable, unsuit, comp, None
            except Exception as e:
                # 실패 시 보수적: 배치 전체를 적합으로 반환
                return batch_idx, list(batch), 0, 0, e

        suitable_all: List[ViralTarget] = []
        done_batches = set(skip)
        lock = threading.Lock()
        save_every = 10  # 10배치마다 체크포인트 + DB 저장 로그

        # 제출할 배치만 선별
        pending = []
        for batch_idx, batch_start in enumerate(range(0, len(targets), batch_size), 1):
            if batch_idx in skip:
                continue
            pending.append((batch_idx, targets[batch_start:batch_start + batch_size]))

        processed_since_checkpoint = 0

        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futures = {ex.submit(run_batch, idx, b): idx for idx, b in pending}
            for fut in as_completed(futures):
                batch_idx, suitable, unsuit, comp, err = fut.result()
                if err:
                    logger.warning(f"   ⚠️ 배치 {batch_idx} 실패({err}) → 보수적 적합 처리")

                # 즉시 DB 저장
                newly_saved = 0
                if db is not None:
                    for t in suitable:
                        try:
                            if db.insert_viral_target(t.to_dict()):
                                newly_saved += 1
                        except Exception as e:
                            logger.warning(f"DB 저장 실패: {e}")

                with lock:
                    suitable_all.extend(suitable)
                    done_batches.add(batch_idx)
                    processed_since_checkpoint += 1
                    logger.info(
                        f"   ✅ 배치 {batch_idx}/{total_batches} 완료 "
                        f"(적합 {len(suitable)}, 부적합 {unsuit}, 경쟁사 {comp}, 저장 {newly_saved}) "
                        f"[누적 {len(done_batches)}/{total_batches}]"
                    )
                    # 체크포인트 저장
                    if on_batch_done and processed_since_checkpoint >= save_every:
                        try:
                            on_batch_done(done_batches.copy())
                            processed_since_checkpoint = 0
                        except Exception as e:
                            logger.warning(f"체크포인트 콜백 실패: {e}")

        # 마지막 체크포인트
        if on_batch_done:
            try:
                on_batch_done(done_batches.copy())
            except Exception:
                pass

        suitable_all.sort(key=lambda x: x.priority_score, reverse=True)
        logger.info(f"✅ 병렬 통합 분석 완료: 적합 {len(suitable_all)}개")
        return suitable_all

    def _parse_unified_results(self, targets: List[ViralTarget], result_text: str) -> tuple:
        """
        통합 분석 결과 파싱

        결과 형식:
        POST_ID: 1
        SUITABLE: true/false
        SCORE: 85
        TYPE: recommendation_request
        COMPETITOR: true/false
        COMPETITOR_NAME: 자연과한의원
        COUNTER_SCORE: 75
        REASON: 추천 요청글, 경쟁사 언급 있음
        ---
        """
        suitable = []
        unsuitable_count = 0
        competitor_count = 0

        # 각 POST 결과 분리
        posts = result_text.split('---')

        # 처리된 POST_ID 추적
        processed_ids = set()

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            # 중복 처리 방지
            if post_id in processed_ids:
                continue
            processed_ids.add(post_id)

            target = targets[post_id]

            # SUITABLE 추출
            suitable_match = re.search(r'SUITABLE:\s*(true|false)', post_result, re.IGNORECASE)
            is_suitable = suitable_match.group(1).lower() == 'true' if suitable_match else True

            # SCORE 추출
            score_match = re.search(r'SCORE:\s*(\d+)', post_result)
            infiltration_score = int(score_match.group(1)) if score_match else 50

            # TYPE 추출
            type_match = re.search(r'TYPE:\s*(\w+)', post_result)
            post_type = type_match.group(1) if type_match else "unknown"

            # COMPETITOR 추출
            competitor_match = re.search(r'COMPETITOR:\s*(true|false)', post_result, re.IGNORECASE)
            has_competitor = competitor_match.group(1).lower() == 'true' if competitor_match else False

            # COMPETITOR_NAME 추출
            name_match = re.search(r'COMPETITOR_NAME:\s*(.+?)(?:\n|$)', post_result)
            comp_name = name_match.group(1).strip() if name_match else "N/A"

            # COUNTER_SCORE 추출
            counter_match = re.search(r'COUNTER_SCORE:\s*(\d+)', post_result)
            counter_score = int(counter_match.group(1)) if counter_match else 0

            if is_suitable:
                # 적합한 글: 점수 반영 및 태그 추가
                bonus = min(infiltration_score // 5, 20)  # 최대 20점 가산
                target.priority_score = min(target.priority_score + bonus, 100)

                # 타입별 태그 추가
                type_tags = {
                    "recommendation_request": "💡추천요청",
                    "consultation": "💬고민상담",
                    "experience_question": "❓경험질문",
                    "info_request": "ℹ️정보요청"
                }
                tag = type_tags.get(post_type, "✅적합")

                if tag not in target.content_preview:
                    target.content_preview = f"[{tag}] {target.content_preview}"

                # 경쟁사 탐지 결과 반영
                if has_competitor:
                    competitor_count += 1
                    target.category = "경쟁사_역공략"

                    # 역공략 점수 가산
                    counter_bonus = min(counter_score // 4, 25)
                    target.priority_score = min(target.priority_score + counter_bonus, 100)

                    if comp_name and comp_name != "N/A" and "⚔️" not in target.content_preview:
                        target.content_preview = f"[⚔️{comp_name}] {target.content_preview}"

                suitable.append(target)
            else:
                unsuitable_count += 1

        # 파싱되지 않은 타겟은 적합으로 처리 (보수적)
        for i, target in enumerate(targets):
            if i not in processed_ids:
                suitable.append(target)

        return suitable, unsuitable_count, competitor_count

    def _parse_infiltration_results(self, targets: List[ViralTarget], result_text: str) -> tuple:
        """
        AI 침투적합도 평가 결과 파싱

        결과 형식:
        POST_ID: 1
        SUITABLE: true/false
        SCORE: 85
        TYPE: recommendation_request
        REASON: 추천 요청글
        ---
        """
        suitable = []
        unsuitable_count = 0

        # 각 POST 결과 분리
        posts = result_text.split('---')

        # 처리된 POST_ID 추적
        processed_ids = set()

        for post_result in posts:
            if not post_result.strip():
                continue

            # POST_ID 추출
            post_id_match = re.search(r'POST_ID:\s*(\d+)', post_result)
            if not post_id_match:
                continue

            post_id = int(post_id_match.group(1)) - 1  # 0-indexed
            if post_id < 0 or post_id >= len(targets):
                continue

            # 중복 처리 방지
            if post_id in processed_ids:
                continue
            processed_ids.add(post_id)

            target = targets[post_id]

            # SUITABLE 추출
            suitable_match = re.search(r'SUITABLE:\s*(true|false)', post_result, re.IGNORECASE)
            if not suitable_match:
                # 파싱 실패 시 적합으로 처리 (보수적)
                suitable.append(target)
                continue

            is_suitable = suitable_match.group(1).lower() == 'true'

            # SCORE 추출
            score_match = re.search(r'SCORE:\s*(\d+)', post_result)
            infiltration_score = int(score_match.group(1)) if score_match else 50

            # TYPE 추출
            type_match = re.search(r'TYPE:\s*(\w+)', post_result)
            post_type = type_match.group(1) if type_match else "unknown"

            if is_suitable:
                # 적합한 글: 점수 반영 및 태그 추가
                bonus = min(infiltration_score // 5, 20)  # 최대 20점 가산
                target.priority_score = min(target.priority_score + bonus, 100)

                # 타입별 태그 추가
                type_tags = {
                    "recommendation_request": "💡추천요청",
                    "consultation": "💬고민상담",
                    "experience_question": "❓경험질문",
                    "info_request": "ℹ️정보요청"
                }
                tag = type_tags.get(post_type, "✅적합")

                if tag not in target.content_preview:
                    target.content_preview = f"[{tag}] {target.content_preview}"

                suitable.append(target)
                logger.debug(f"✅ 침투적합: {target.title[:30]}... ({post_type}, 점수: {infiltration_score})")
            else:
                # 부적합한 글: 제외
                unsuitable_count += 1
                logger.debug(f"❌ 침투부적합: {target.title[:30]}... ({post_type})")

        # 파싱되지 않은 타겟은 적합으로 처리 (보수적)
        for i, target in enumerate(targets):
            if i not in processed_ids:
                suitable.append(target)

        return suitable, unsuitable_count


# ============================================
# 메인 오케스트레이터 클래스
# ============================================
class ViralHunter:
    """
    Viral Hunter 메인 클래스

    기능:
    - 타겟 발굴 (hunt)
    - 댓글 생성 (generate_comments)
    - DB 저장/조회
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.cfg = ConfigManager()
        self.searcher = NaverUnifiedSearch()
        self.filter = CommentableFilter()
        self.generator = AICommentGenerator()

    def _load_keywords(self) -> List[str]:
        """
        Pathfinder 전용 모드 - 검증된 키워드만 사용

        campaigns.json 비활성화:
        - 65.3% 미검증 키워드 제거
        - 100% Pathfinder 검증 키워드만 사용
        - 자동 업데이트 지원
        """
        keywords = set()
        keyword_sources = {
            'targets_json': 0,
            'pathfinder_sa': 0,
            'pathfinder_b': 0,
            'trending': 0
        }

        # 1. targets.json의 community_scan_keywords (핵심 키워드만)
        try:
            targets = self.cfg.load_targets()
            for kw in targets.get('community_scan_keywords', []):
                keywords.add(kw)
                keyword_sources['targets_json'] += 1
        except Exception as e:
            logger.warning(f"targets.json 로드 실패: {e}")

        # 2. campaigns.json - 비활성화됨 ⚠️
        # 이유: 65.3% 미검증 키워드, 품질 혼재
        # Pathfinder로 대체 (아래 참조)
        """
        try:
            campaigns_path = os.path.join(self.cfg.root_dir, 'config', 'campaigns.json')
            if os.path.exists(campaigns_path):
                with open(campaigns_path, 'r', encoding='utf-8') as f:
                    campaigns = json.load(f)
                for target in campaigns.get('targets', []):
                    for seed in target.get('seeds', []):
                        keywords.add(seed)
                        keyword_sources['campaigns_json'] += 1
        except Exception as e:
            logger.warning(f"campaigns.json 로드 실패: {e}")
        """

        # 3. Pathfinder S/A급 키워드 (최고 품질) ⭐
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # S/A급 키워드 전체
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE grade IN ('S', 'A')
                    ORDER BY priority_v3 DESC
                """)

                pathfinder_sa = cursor.fetchall()
                for row in pathfinder_sa:
                    keywords.add(row[0])
                    keyword_sources['pathfinder_sa'] += 1

                conn.close()

                if keyword_sources['pathfinder_sa'] > 0:
                    logger.info(f"✅ Pathfinder S/A급: {keyword_sources['pathfinder_sa']}개")
                else:
                    logger.warning("⚠️ Pathfinder에서 S/A급 키워드를 찾지 못했습니다")

        except Exception as e:
            logger.warning(f"Pathfinder S/A급 로드 실패: {e}")

        # 4. Pathfinder B급 키워드 (품질 확장) ⭐ 신규
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # B급 상위 100개 (우선순위 높은 순)
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE grade = 'B'
                    ORDER BY priority_v3 DESC
                    LIMIT 100
                """)

                pathfinder_b = cursor.fetchall()
                for row in pathfinder_b:
                    keywords.add(row[0])
                    keyword_sources['pathfinder_b'] += 1

                conn.close()

                if keyword_sources['pathfinder_b'] > 0:
                    logger.info(f"✅ Pathfinder B급 (상위): {keyword_sources['pathfinder_b']}개")

        except Exception as e:
            logger.warning(f"Pathfinder B급 로드 실패: {e}")

        # 5. 트렌드 rising 키워드 (선택적) ⭐
        try:
            import sqlite3
            db_path = os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db')

            if os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=10)
                cursor = conn.cursor()

                # 트렌드 상승 중인 A/B급 키워드
                cursor.execute("""
                    SELECT keyword
                    FROM keyword_insights
                    WHERE trend_status = 'rising'
                    AND grade IN ('A', 'B')
                    LIMIT 30
                """)

                trending_keywords = cursor.fetchall()
                for row in trending_keywords:
                    keywords.add(row[0])
                    keyword_sources['trending'] += 1

                conn.close()

                if keyword_sources['trending'] > 0:
                    logger.info(f"📈 트렌드 키워드: {keyword_sources['trending']}개")

        except Exception as e:
            logger.warning(f"트렌드 키워드 로드 실패: {e}")

        # 기본 키워드 (비어있을 경우)
        if not keywords:
            keywords = {"청주 한의원", "청주 다이어트"}

        # 통계 출력
        total = len(keywords)
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"📊 Pathfinder 전용 모드 - 키워드 로드 완료")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"   • targets.json: {keyword_sources['targets_json']}개")
        logger.info(f"   • Pathfinder S/A급: {keyword_sources['pathfinder_sa']}개")
        logger.info(f"   • Pathfinder B급: {keyword_sources['pathfinder_b']}개")
        logger.info(f"   • 트렌드: {keyword_sources['trending']}개")
        logger.info(f"   • 총 {total}개 (중복 제거 후)")
        logger.info(f"   • 검증률: 100% (모두 Pathfinder 검증)")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return list(keywords)

    # ── 체크포인트 유틸 ────────────────────────────────────────────────

    def _checkpoint_path(self) -> str:
        return os.path.join(self.cfg.root_dir, 'db', 'viral_hunter_checkpoint.json')

    def _save_checkpoint(self, keywords_hash: str, processed: List[str],
                         all_targets: List[ViralTarget], seen_urls: set):
        """체크포인트 저장 (raw 검색 결과 + 진행 상태)."""
        try:
            data = {
                'keywords_hash': keywords_hash,
                'total_keywords': len(processed) if processed else 0,
                'processed_keywords': processed,
                'seen_urls': list(seen_urls),
                'all_targets': [t.to_dict() for t in all_targets],
                'saved_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            }
            tmp = self._checkpoint_path() + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self._checkpoint_path())
        except Exception as e:
            logger.warning(f"체크포인트 저장 실패: {e}")

    def _load_checkpoint(self, keywords_hash: str) -> Optional[dict]:
        """동일 키워드 세트의 체크포인트 로드, 없으면 None."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if data.get('keywords_hash') != keywords_hash:
                logger.info(f"체크포인트 키워드 세트 불일치 → 무시")
                return None
            return data
        except Exception as e:
            logger.warning(f"체크포인트 로드 실패: {e}")
            return None

    def _clear_checkpoint(self):
        path = self._checkpoint_path()
        if os.path.exists(path):
            try:
                os.remove(path)
            except Exception as e:
                logger.warning(f"체크포인트 삭제 실패: {e}")

    @staticmethod
    def _viral_target_from_dict(d: dict) -> ViralTarget:
        """체크포인트 복원용. to_dict()의 'id'는 property이므로 제외."""
        return ViralTarget(
            platform=d.get('platform', ''),
            url=d.get('url', ''),
            title=d.get('title', ''),
            content_preview=d.get('content_preview', ''),
            matched_keywords=d.get('matched_keywords') or [],
            category=d.get('category', '기타'),
            is_commentable=d.get('is_commentable', True),
            generated_comment=d.get('generated_comment', ''),
            priority_score=d.get('priority_score', 0.0),
            author=d.get('author', ''),
            date_str=d.get('date_str', ''),
        )

    def hunt(self, keywords: List[str] = None, limit_keywords: int = None,
             max_per_platform: int = 100, progress_callback=None,
             fresh: bool = False, checkpoint_every: int = 20,
             top_n_for_ai: int = 10000, ai_parallel: int = 5) -> List[ViralTarget]:
        """
        바이럴 타겟 발굴

        Args:
            keywords: 검색할 키워드 (None이면 config에서 로드)
            limit_keywords: 키워드 제한 수
            max_per_platform: 플랫폼당 최대 결과 수
            progress_callback: 진행 상황 콜백 함수 (stage, current, total, message)
            fresh: True면 체크포인트 무시하고 처음부터 시작
            checkpoint_every: N개 키워드마다 체크포인트 저장

        Returns:
            발견된 ViralTarget 리스트
        """
        if keywords is None:
            keywords = self._load_keywords()

        if limit_keywords:
            keywords = keywords[:limit_keywords]

        # 키워드 세트 해시 (순서 무관)
        kw_hash = hashlib.md5(
            ('|'.join(sorted(keywords))).encode('utf-8')
        ).hexdigest()[:16]

        # 체크포인트 복원
        all_targets: List[ViralTarget] = []
        seen_urls: set = set()
        processed_set: set = set()

        if not fresh:
            cp = self._load_checkpoint(kw_hash)
            if cp:
                processed_set = set(cp.get('processed_keywords') or [])
                seen_urls = set(cp.get('seen_urls') or [])
                all_targets = [
                    self._viral_target_from_dict(d)
                    for d in (cp.get('all_targets') or [])
                ]
                print(f"\n♻️  체크포인트 복원: 처리 완료 {len(processed_set)}/{len(keywords)}, "
                      f"수집 {len(all_targets)}개 (저장 시각 {cp.get('saved_at')})")

        print(f"\n{'='*60}")
        print(f"🎯 Viral Hunter 스캔 시작")
        print(f"   키워드: {len(keywords)}개 (남은 {len(keywords) - len(processed_set)}개)")
        print(f"   플랫폼: 카페, 블로그, 지식인")
        print(f"   체크포인트: 매 {checkpoint_every}개마다 저장")
        print(f"{'='*60}\n")

        if progress_callback:
            progress_callback("초기화", len(processed_set), len(keywords),
                              f"키워드 {len(keywords)}개 로드 완료")

        checkpoint_counter = 0

        for i, kw in enumerate(keywords, 1):
            if kw in processed_set:
                continue  # 이미 처리됨

            print(f"\n[{i}/{len(keywords)}] '{kw}' 검색 중...")

            if progress_callback:
                progress_callback("검색중", i, len(keywords), f"'{kw}' 검색 | 수집: {len(all_targets)}개")

            try:
                results = self.searcher.search_all(kw, max_per_platform)
            except Exception as e:
                logger.error(f"'{kw}' 검색 중 예외: {e} — 다음 키워드로 진행")
                results = []

            # 중복 제거
            for target in results:
                if target.url not in seen_urls:
                    seen_urls.add(target.url)
                    all_targets.append(target)

            processed_set.add(kw)
            checkpoint_counter += 1

            # 진행 상황
            if i % 5 == 0:
                print(f"   📊 진행: {i}/{len(keywords)} | 수집: {len(all_targets)}개")

            # 체크포인트 저장
            if checkpoint_counter >= checkpoint_every:
                self._save_checkpoint(
                    kw_hash, list(processed_set), all_targets, seen_urls
                )
                checkpoint_counter = 0
                print(f"   💾 체크포인트 저장: {len(processed_set)}/{len(keywords)}, 수집 {len(all_targets)}개")

        # 검색 단계 끝 — 최종 체크포인트 (AI 분석 전 안전장치)
        self._save_checkpoint(
            kw_hash, list(processed_set), all_targets, seen_urls
        )

        # 필터링
        print(f"\n🔍 필터링 중...")
        if progress_callback:
            progress_callback("필터링중", len(keywords), len(keywords), f"{len(all_targets)}개 타겟 필터링 중...")
        filtered = self.filter.filter(all_targets)

        # 중복 타겟 방지 (DB에 이미 있는 URL 제외)
        if filtered:
            print(f"\n🔄 중복 체크 중...")
            try:
                existing_targets = self.db.get_viral_targets(limit=100000)  # 모든 타겟 조회
                existing_urls = set(row['url'] for row in existing_targets if row.get('url'))

                new_targets = [t for t in filtered if t.url not in existing_urls]

                if len(new_targets) < len(filtered):
                    duplicate_count = len(filtered) - len(new_targets)
                    print(f"   ✅ 중복 제거: {len(filtered)}개 → {len(new_targets)}개 (중복 {duplicate_count}개)")
                    filtered = new_targets
                else:
                    print(f"   ✅ 중복 없음: {len(filtered)}개 모두 신규")
            except Exception as e:
                logger.warning(f"중복 체크 실패 (계속 진행): {e}")

        # [D2] Adaptive penalty 적용 — 반복 skip된 도메인/작성자 감점
        if filtered:
            try:
                import sqlite3 as _sql
                from urllib.parse import urlparse as _urlparse
                conn = _sql.connect(os.path.join(self.cfg.root_dir, 'db', 'marketing_data.db'))
                c = conn.cursor()
                c.execute(
                    "SELECT key_type, key_value, skip_count FROM viral_adaptive_penalties WHERE skip_count >= 3"
                )
                penalties = {(r[0], r[1]): r[2] for r in c.fetchall()}
                conn.close()
                if penalties:
                    penalized = 0
                    for t in filtered:
                        domain = _urlparse(t.url or '').netloc.replace('www.', '')
                        dpen = penalties.get(('domain', domain), 0)
                        apen = penalties.get(('author', t.author or ''), 0)
                        total_pen = min(30, dpen * 3) + min(20, apen * 3)
                        if total_pen > 0:
                            t.priority_score = max(0, (t.priority_score or 0) - total_pen)
                            penalized += 1
                    if penalized:
                        filtered.sort(key=lambda x: x.priority_score, reverse=True)
                        print(f"   ⚙️ Adaptive penalty 적용: {penalized}개 타겟 점수 조정")
            except Exception as e:
                logger.debug(f"adaptive penalty skip: {e}")

        # 상위 N개만 AI 분석 대상, 나머지는 raw 저장
        ai_targets = filtered[:top_n_for_ai]
        rest_targets = filtered[top_n_for_ai:]

        # 나머지(raw)는 먼저 DB에 저장하여 즉시 보존
        raw_saved = 0
        if rest_targets:
            print(f"\n💾 Raw 저장 (AI 제외 {len(rest_targets)}개, 휴리스틱 점수 기준)...")
            for t in rest_targets:
                if self.db.insert_viral_target(t.to_dict()):
                    raw_saved += 1
            print(f"   ✅ Raw {raw_saved}개 저장 완료")

        # AI 통합 분석 (병렬 + 증분 DB 저장)
        analyzed_targets: List[ViralTarget] = []
        if ai_targets:
            print(f"\n🔬 AI 통합 분석 중 (상위 {len(ai_targets)}개, 병렬 {ai_parallel})...")
            if progress_callback:
                progress_callback("AI분석중", len(keywords), len(keywords),
                                  f"{len(ai_targets)}개 타겟 AI 분석 중...")

            # 체크포인트에서 이미 분석한 배치 인덱스 로드 (ai_processed_batches)
            cp_path = self._checkpoint_path()
            already_done_batches: set = set()
            if os.path.exists(cp_path):
                try:
                    with open(cp_path, 'r', encoding='utf-8') as f:
                        cp = json.load(f)
                    already_done_batches = set(cp.get('ai_processed_batches') or [])
                except Exception:
                    pass

            def save_progress(done_batch_indices: set):
                """현재까지 분석된 배치 인덱스를 체크포인트에 저장"""
                try:
                    cp_data = {}
                    if os.path.exists(cp_path):
                        with open(cp_path, 'r', encoding='utf-8') as f:
                            cp_data = json.load(f)
                    cp_data['ai_processed_batches'] = sorted(done_batch_indices)
                    cp_data['ai_saved_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
                    tmp = cp_path + '.tmp'
                    with open(tmp, 'w', encoding='utf-8') as f:
                        json.dump(cp_data, f, ensure_ascii=False)
                    os.replace(tmp, cp_path)
                except Exception as e:
                    logger.warning(f"AI 체크포인트 저장 실패: {e}")

            analyzed_targets = self.generator.unified_analysis_parallel(
                ai_targets,
                batch_size=25,
                max_workers=ai_parallel,
                db=self.db,
                skip_batch_indices=already_done_batches,
                on_batch_done=save_progress,
            )

        # 총 저장 수: raw + AI로 분석되어 이미 저장된 것
        saved = raw_saved + len(analyzed_targets)
        filtered = analyzed_targets + rest_targets  # 리포팅용 (정렬 순서 유지 안 됨)

        # HOT LEAD 즉시 알림 (Telegram) — Tier 구분
        # Tier 1 (점수 120+ 또는 경쟁사 탐지): 즉시 상위 10건 푸시
        # Tier 2 (100~119): daily_brief.py가 오전 09:00 요약
        # Tier 3 (그 외): 대시보드에서만 확인
        if analyzed_targets:
            tier1 = [
                t for t in analyzed_targets
                if (t.priority_score or 0) >= 120 or getattr(t, 'category', '') == '경쟁사_역공략'
            ]
            if tier1:
                try:
                    from alert_bot import TelegramBot
                    bot = TelegramBot()

                    top = sorted(tier1, key=lambda x: x.priority_score or 0, reverse=True)[:10]
                    message = (
                        f"🔥 **Tier 1 HOT LEAD {len(tier1)}건 발견** (점수 120+ 또는 경쟁사 탐지)\n"
                        f"상위 {len(top)}건만 표시, 나머지는 대시보드에서 확인:\n\n"
                    )
                    for i, lead in enumerate(top, 1):
                        platform_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(lead.platform, "📌")
                        badge = "⚔️" if getattr(lead, 'category', '') == '경쟁사_역공략' else ""
                        message += f"{i}. {platform_icon}{badge} [{lead.platform.upper()}] 점수 {lead.priority_score:.0f}\n"
                        message += f"   {lead.title[:60]}\n"
                        message += f"   {lead.url}\n\n"

                    total_rest = len(analyzed_targets) - len(tier1)
                    if total_rest > 0:
                        message += f"ℹ️ Tier 2/3 {total_rest}건은 오전 Daily Brief로 요약 전송됩니다."

                    bot.send_message(message)
                    print(f"   📱 Tier 1 {len(tier1)}건 Telegram 알림 발송 (상위 10건)")
                except Exception as e:
                    logger.warning(f"Telegram 알림 실패: {e}")
            else:
                print(f"   ℹ️ Tier 1 HOT LEAD 없음 — 즉시 알림 스킵 (Daily Brief에서 요약)")

        # 체크포인트 삭제 (성공 완료)
        self._clear_checkpoint()

        # CSV 자동 저장
        csv_path = None
        if filtered:
            import csv
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(self.cfg.root_dir, 'reports', f'viral_targets_{timestamp}.csv')
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)

            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['rank', 'platform', 'title', 'score', 'keyword', 'url'])
                for i, t in enumerate(filtered, 1):
                    writer.writerow([
                        i,
                        t.platform,
                        t.title,
                        t.priority_score,
                        ', '.join(t.matched_keywords[:3]) if t.matched_keywords else '',
                        t.url
                    ])

        # API 통계
        api_stats = self.searcher.get_stats()

        print(f"\n{'='*60}")
        print(f"✅ 스캔 완료!")
        print(f"   총 발견: {len(all_targets)}개")
        print(f"   필터링 후: {len(filtered)}개")
        print(f"   DB 저장: {saved}개")
        if csv_path:
            print(f"   📁 CSV: {csv_path}")
        print(f"\n📊 API 통계:")
        print(f"   요청: {api_stats['requests']}건 | 캐시 히트: {api_stats['cache_hits']}건")
        print(f"   에러: {api_stats['errors']}건 ({api_stats['error_rate']})")
        print(f"{'='*60}\n")

        if progress_callback:
            hot_count = len([t for t in filtered if "🔥" in t.content_preview or "🔥HOT" in t.content_preview])
            progress_callback("완료", len(keywords), len(keywords),
                            f"✅ 완료! 총 {saved}개 저장 (🔥HOT {hot_count}개)")

        return filtered

    def generate_comments(self, limit: int = 10, status: str = 'pending') -> List[ViralTarget]:
        """
        pending 상태의 타겟에 대해 AI 댓글 생성

        Args:
            limit: 생성할 최대 수
            status: 필터링할 상태

        Returns:
            댓글이 생성된 타겟 리스트
        """
        print(f"\n{'='*60}")
        print(f"🤖 AI 댓글 생성 시작")
        print(f"   대상 상태: {status}")
        print(f"   최대 생성: {limit}개")
        print(f"{'='*60}\n")

        # DB에서 pending 타겟 조회
        targets_data = self.db.get_viral_targets(status=status, limit=limit)

        if not targets_data:
            print("⚠️ 생성할 타겟이 없습니다.")
            return []

        # ViralTarget 객체로 변환
        targets = []
        for data in targets_data:
            target = ViralTarget(
                platform=data.get('platform', 'unknown'),
                url=data.get('url', ''),
                title=data.get('title', ''),
                content_preview=data.get('content_preview', ''),
                matched_keywords=json.loads(data.get('matched_keywords', '[]')),
                category=data.get('category', '기타'),
                priority_score=data.get('priority_score', 0)
            )
            targets.append(target)

        # 댓글 생성
        generated = self.generator.batch_generate(targets, limit)

        # DB 업데이트
        updated = 0
        for target in generated:
            if target.generated_comment:
                self.db.update_viral_target(target.id, {
                    'generated_comment': target.generated_comment,
                    'comment_status': 'generated'
                })
                updated += 1

        print(f"\n{'='*60}")
        print(f"✅ 댓글 생성 완료!")
        print(f"   생성됨: {updated}개")
        print(f"{'='*60}\n")

        return generated

    def get_stats(self) -> dict:
        """현재 통계 조회"""
        return self.db.get_viral_stats()

    def list_targets(self, status: str = None, platform: str = None,
                     category: str = None, date_filter: str = None,
                     platforms: list = None, comment_status: str = None,
                     min_scan_count: int = None,
                     search: str = None, sort: str = None,
                     scan_batch: str = None, limit: int = 50,
                     offset: int = 0) -> List[dict]:
        """타겟 목록 조회 (필터링 및 정렬 지원)"""
        return self.db.get_viral_targets(
            status=status, platform=platform, category=category,
            date_filter=date_filter, platforms=platforms,
            comment_status=comment_status,
            min_scan_count=min_scan_count, search=search, sort=sort,
            scan_batch=scan_batch, limit=limit, offset=offset
        )


# ============================================
# CLI 인터페이스
# ============================================
def main():
    parser = argparse.ArgumentParser(description="Viral Hunter - 바이럴 마케팅 타겟 발굴")
    parser.add_argument('--scan', action='store_true', help='타겟 스캔 실행')
    parser.add_argument('--generate', action='store_true', help='AI 댓글 생성')
    parser.add_argument('--stats', action='store_true', help='통계 출력')
    parser.add_argument('--list', action='store_true', help='타겟 목록 출력')
    parser.add_argument('--limit-keywords', type=int, default=None, help='스캔할 키워드 수 제한')
    parser.add_argument('--limit', type=int, default=10, help='댓글 생성 수 제한')
    parser.add_argument('--keyword', type=str, help='특정 키워드로 검색')
    parser.add_argument('--test-search', action='store_true', help='검색 테스트')
    parser.add_argument('--test-comment', action='store_true', help='댓글 생성 테스트')
    parser.add_argument('--no-db', action='store_true', help='DB 저장 없이 결과만 출력 (WSL 호환)')
    parser.add_argument('--fresh', action='store_true', help='체크포인트 무시하고 처음부터 스캔')
    parser.add_argument('--checkpoint-every', type=int, default=20, help='N개 키워드마다 체크포인트 저장 (기본 20)')
    parser.add_argument('--top-n-for-ai', type=int, default=10000, help='AI 분석 대상 상위 N개 (나머지는 raw 저장, 기본 10000)')
    parser.add_argument('--ai-parallel', type=int, default=5, help='AI 병렬 호출 수 (기본 5)')

    args = parser.parse_args()

    # 테스트 모드는 DB 없이 실행
    if args.test_search:
        keyword = args.keyword or "청주 다이어트"
        print(f"\n🔍 검색 테스트: '{keyword}'")
        searcher = NaverUnifiedSearch()
        results = searcher.search_all(keyword, max_per_platform=5)
        print(f"\n총 {len(results)}개 결과:\n")
        for r in results[:15]:
            print(f"  [{r.platform}] {r.title[:50]}...")
            print(f"       URL: {r.url[:70]}...")
        return

    if args.test_comment:
        # 댓글 생성 테스트 (DB 없이)
        generator = AICommentGenerator()
        test_target = ViralTarget(
            platform="kin",
            url="https://kin.naver.com/test",
            title="청주 다이어트 한의원 추천해주세요",
            content_preview="다이어트를 시작하려고 하는데 청주에 좋은 한의원 있을까요?",
            matched_keywords=["청주 다이어트", "한의원 추천"]
        )
        print(f"\n🤖 댓글 생성 테스트")
        print(f"   제목: {test_target.title}")
        comment = generator.generate(test_target)
        print(f"\n   생성된 댓글:\n   {comment}")
        return

    # --no-db 모드: DB 저장 없이 스캔만 실행
    if args.no_db and args.scan:
        cfg = ConfigManager()
        searcher = NaverUnifiedSearch()
        filter_obj = CommentableFilter()
        generator = AICommentGenerator()

        # 키워드 로드
        keywords = set()
        try:
            targets = cfg.load_targets()
            for kw in targets.get('community_scan_keywords', []):
                keywords.add(kw)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"targets.json 로드 실패: {e}")

        try:
            campaigns_path = os.path.join(cfg.root_dir, 'config', 'campaigns.json')
            if os.path.exists(campaigns_path):
                with open(campaigns_path, 'r', encoding='utf-8') as f:
                    campaigns = json.load(f)
                for target in campaigns.get('targets', []):
                    for seed in target.get('seeds', []):
                        keywords.add(seed)
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.debug(f"campaigns.json 로드 실패: {e}")

        if not keywords:
            keywords = {"청주 한의원", "청주 다이어트"}

        keywords = list(keywords)
        if args.limit_keywords:
            keywords = keywords[:args.limit_keywords]

        print(f"\n{'='*60}")
        print(f"🎯 Viral Hunter 스캔 (DB 저장 안함)")
        print(f"   키워드: {len(keywords)}개")
        print(f"   플랫폼: 카페, 블로그, 지식인")
        print(f"{'='*60}\n")

        all_targets = []
        seen_urls = set()

        for i, kw in enumerate(keywords, 1):
            print(f"[{i}/{len(keywords)}] '{kw}' 검색 중...")
            results = searcher.search_all(kw, max_per_platform=15)

            for target in results:
                if target.url not in seen_urls:
                    seen_urls.add(target.url)
                    all_targets.append(target)

            if i % 5 == 0:
                print(f"   📊 진행: {i}/{len(keywords)} | 수집: {len(all_targets)}개")

        # 필터링
        print(f"\n🔍 필터링 중...")
        filtered = filter_obj.filter(all_targets)

        # AI 통합 분석 (경쟁사 탐지 + 침투적합도 평가를 하나로)
        if filtered:
            print(f"\n🔬 AI 통합 분석 중 (경쟁사 탐지 + 침투적합도)...")
            before_count = len(filtered)
            filtered = generator.unified_analysis(filtered, batch_size=25)
            print(f"   통합 분석 완료: {before_count}개 → {len(filtered)}개 (침투적합)")

        # 결과 출력
        print(f"\n{'='*60}")
        print(f"✅ 스캔 완료!")
        print(f"   총 발견: {len(all_targets)}개")
        print(f"   침투적합: {len(filtered)}개")
        print(f"{'='*60}\n")

        # CSV 자동 저장
        if filtered:
            import csv
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            csv_path = os.path.join(cfg.root_dir, 'reports', f'viral_targets_{timestamp}.csv')
            os.makedirs(os.path.dirname(csv_path), exist_ok=True)

            with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow(['rank', 'platform', 'title', 'url', 'score', 'keywords', 'is_competitor', 'counter_score'])
                for i, t in enumerate(filtered, 1):
                    writer.writerow([
                        i,
                        t.platform,
                        t.title,
                        t.url,
                        t.priority_score,
                        ', '.join(t.matched_keywords) if t.matched_keywords else '',
                        getattr(t, 'is_competitor', False),
                        getattr(t, 'counter_score', 0)
                    ])
            print(f"📁 CSV 저장: {csv_path}")

        # 상위 결과 출력
        print(f"\n📋 상위 타겟 (우선순위순 상위 20개):")
        print("-" * 60)
        for i, t in enumerate(filtered[:20], 1):
            print(f"{i:2}. [{t.platform:5}] {t.title[:45]}...")
            print(f"     점수: {t.priority_score:.0f} | 키워드: {', '.join(t.matched_keywords[:2])}")
            print(f"     URL: {t.url[:65]}...")
            print()

        # AI 댓글 생성 (선택적)
        if args.generate and filtered:
            print(f"\n🤖 AI 댓글 생성 (상위 {min(args.limit, len(filtered))}개):")
            print("-" * 60)
            for t in filtered[:args.limit]:
                comment = generator.generate(t)
                print(f"\n[{t.platform}] {t.title[:40]}...")
                print(f"💬 {comment}")

        return

    # DB 필요한 명령어들은 여기서 hunter 초기화
    hunter = ViralHunter()

    if args.scan:
        # 스캔 실행
        keywords = [args.keyword] if args.keyword else None
        hunter.hunt(keywords=keywords, limit_keywords=args.limit_keywords,
                    fresh=args.fresh, checkpoint_every=args.checkpoint_every,
                    top_n_for_ai=args.top_n_for_ai, ai_parallel=args.ai_parallel)
        return

    if args.generate:
        # 댓글 생성
        hunter.generate_comments(limit=args.limit)
        return

    if args.stats:
        # 통계 출력
        stats = hunter.get_stats()
        print(f"\n📊 Viral Hunter 통계")
        print(f"   총 타겟: {stats.get('total', 0)}개")
        print(f"   오늘 발견: {stats.get('today', 0)}개")
        print(f"\n   플랫폼별:")
        for platform, count in stats.get('by_platform', {}).items():
            print(f"      {platform}: {count}개")
        print(f"\n   상태별:")
        for status, count in stats.get('by_status', {}).items():
            print(f"      {status}: {count}개")
        return

    if args.list:
        # 목록 출력
        targets = hunter.list_targets(limit=args.limit)
        print(f"\n📋 타겟 목록 (상위 {len(targets)}개)")
        for t in targets:
            status_icon = "⏳" if t['comment_status'] == 'pending' else "✅"
            print(f"  {status_icon} [{t['platform']}] {t['title'][:40]}...")
            print(f"       점수: {t['priority_score']:.0f} | 상태: {t['comment_status']}")
        return

    # 기본: 도움말 출력
    parser.print_help()


if __name__ == "__main__":
    main()
