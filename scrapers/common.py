"""scrapers/common.py — 스크래퍼 공용 유틸리티.

15+ 스크래퍼에 복붙된 HTTP 헤더·rate limit·재시도 로직을 통합.

사용:
    from scrapers.common import BaseScraperMixin, default_headers, rate_limited_session

    class MyScraper(BaseScraperMixin):
        def __init__(self):
            super().__init__()
            self.session = rate_limited_session()
"""
from __future__ import annotations

import logging
import random
import time
from typing import Dict, Optional

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


# ── 공용 헤더 ──────────────────────────────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]


def default_headers(referer: str = "https://www.naver.com/") -> Dict[str, str]:
    """랜덤 UA 헤더 — 네이버 계열 기본값."""
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "Referer": referer,
    }


# ── 공용 Session (자동 재시도 + 커넥션 풀) ─────────────────────────────
def rate_limited_session(
    total_retries: int = 3,
    backoff_factor: float = 0.5,
    status_forcelist: tuple = (429, 500, 502, 503, 504),
    pool_maxsize: int = 20,
) -> requests.Session:
    """재시도 + 커넥션 풀 기본 설정된 requests.Session.

    429/5xx 상태 코드에 대해 exponential backoff 재시도.
    """
    session = requests.Session()
    retry = Retry(
        total=total_retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=frozenset(["GET", "POST", "HEAD"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_maxsize=pool_maxsize)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


# ── BaseScraperMixin ───────────────────────────────────────────────────
class BaseScraperMixin:
    """모든 스크래퍼가 공유할 수 있는 기본 레이트 리밋·로깅.

    사용:
        class MyScraper(BaseScraperMixin):
            def __init__(self):
                super().__init__(delay=1.0)
                ...
    """

    def __init__(self, delay: float = 1.0, max_retries: int = 3):
        self.delay = delay
        self.max_retries = max_retries
        self._last_call = 0.0
        self._request_count = 0
        self._error_count = 0

    def _rate_limit(self) -> None:
        """요청 간 최소 delay 초 보장."""
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def safe_get(
        self,
        session: requests.Session,
        url: str,
        *,
        params: Optional[dict] = None,
        headers: Optional[dict] = None,
        timeout: int = 10,
    ) -> Optional[requests.Response]:
        """레이트 리밋 적용된 GET. 실패 시 None."""
        self._rate_limit()
        self._request_count += 1
        try:
            resp = session.get(
                url,
                params=params,
                headers=headers or default_headers(),
                timeout=timeout,
            )
            return resp
        except requests.exceptions.RequestException as e:
            self._error_count += 1
            logger.warning(f"[{self.__class__.__name__}] GET {url} 실패: {e}")
            return None

    def get_stats(self) -> Dict[str, int]:
        """요청/에러 통계."""
        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "error_rate": (
                f"{self._error_count / self._request_count * 100:.1f}%"
                if self._request_count > 0 else "0%"
            ),
        }
