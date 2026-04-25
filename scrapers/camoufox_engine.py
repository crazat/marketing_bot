"""
Camoufox Engine - SERP 캡차 우회 전용 페이지 fetcher
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Camoufox = Firefox C++-level fingerprint spoofing browser.
2026 안티디텍트 SOTA. Naver SERP가 fingerprint scoring으로 사전 차단하므로
puppeteer/selenium 위에 stealth plugin 얹는 방식보다 우월.

용도:
- place_scan_enrichment.py의 SERP 분석 (현재 19/19 캡차 차단)
- AI 브리핑 + MY플레이스 클립 모니터 (신규)

사용법:
    from scrapers.camoufox_engine import CamoufoxFetcher

    with CamoufoxFetcher(headless=True) as f:
        html = f.fetch("https://search.naver.com/search.naver?query=청주+한의원")
        if html and not f.is_blocked(html):
            # parse...
            pass
"""

import logging
import random
import time
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Camoufox / Firefox 한국어 로케일
_DEFAULT_LOCALE = ['ko-KR', 'ko']
_DEFAULT_TIMEZONE = 'Asia/Seoul'

# 차단 신호
_BLOCK_MARKERS = (
    'captcha', 'unusual traffic', '비정상적인 접근',
    '자동화된 요청', '잠시 후 다시', 'recaptcha',
    'are you a robot', 'security check',
)


class CamoufoxFetcher:
    """sync 컨텍스트 매니저. 단순 페이지 fetch + 차단 감지 전용."""

    def __init__(
        self,
        headless: bool = True,
        humanize: bool = True,
        block_images: bool = True,
        proxy: Optional[dict] = None,
    ):
        """
        Args:
            headless: 헤드리스 모드 (서버 환경 True)
            humanize: 마우스 이동·스크롤 인간화
            block_images: 이미지 차단 (속도/대역폭)
            proxy: {'server': 'http://host:port', 'username': '...', 'password': '...'}
        """
        self.headless = headless
        self.humanize = humanize
        self.block_images = block_images
        self.proxy = proxy
        self._browser = None
        self._page = None
        self._cm = None

    def __enter__(self):
        try:
            from camoufox.sync_api import Camoufox
        except ImportError as e:
            raise RuntimeError(
                "camoufox not installed. Run: pip install camoufox && python -m camoufox fetch"
            ) from e

        kwargs = {
            'headless': self.headless,
            'humanize': self.humanize,
            'locale': _DEFAULT_LOCALE,
            'i_know_what_im_doing': True,  # geoip 없이도 시작
        }
        if self.proxy:
            kwargs['proxy'] = self.proxy
        if self.block_images:
            kwargs['block_images'] = True

        self._cm = Camoufox(**kwargs)
        self._browser = self._cm.__enter__()
        self._page = self._browser.new_page()
        # default timezone
        try:
            self._browser.contexts[0].set_extra_http_headers({})
        except Exception:
            pass
        logger.info(f"[Camoufox] Browser launched (headless={self.headless})")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if self._page:
                self._page.close()
        except Exception:
            pass
        try:
            if self._cm:
                self._cm.__exit__(exc_type, exc_val, exc_tb)
        except Exception as e:
            logger.warning(f"[Camoufox] Close error (non-fatal): {e}")
        self._browser = None
        self._page = None
        self._cm = None

    def fetch(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        wait_ms: int = 0,
        timeout_ms: int = 20000,
    ) -> Optional[str]:
        """
        URL 접근 후 HTML 반환.

        Args:
            url: 요청 URL
            wait_selector: 특정 selector 대기 (선택)
            wait_ms: 추가 wait (ms)
            timeout_ms: navigation timeout

        Returns:
            HTML 문자열 or None (차단/오류 시)
        """
        if not self._page:
            raise RuntimeError("CamoufoxFetcher must be used as context manager")
        try:
            self._page.goto(url, timeout=timeout_ms, wait_until='domcontentloaded')
            if wait_selector:
                try:
                    self._page.wait_for_selector(wait_selector, timeout=5000)
                except Exception:
                    pass
            if wait_ms > 0:
                time.sleep(wait_ms / 1000)
            else:
                # 자연스러운 짧은 휴지
                time.sleep(random.uniform(0.6, 1.4))
            html = self._page.content()
            return html
        except Exception as e:
            logger.warning(f"[Camoufox] fetch failed for {url[:80]}...: {e}")
            return None

    @staticmethod
    def is_blocked(html: str) -> bool:
        """차단/캡차 감지.

        실제 차단 페이지는 매우 짧고(<30KB) 검색 결과 마커가 없다.
        정상 결과 페이지에도 captcha/잠시 후 같은 단어가 JS에 포함될 수 있어
        길이 + 정상 마커로 false positive를 거른다.
        """
        if not html:
            return True
        # 정상 검색 결과는 보통 100KB+ (HTML+inline JS+CSS 포함)
        if len(html) > 100_000:
            # 정상 결과 마커 — 하나라도 있으면 차단 아님
            normal_markers = (
                '네이버 검색', 'place', '플레이스', 'view', 'sds-comps',
                'main_pack', 'sp_local', 'sp_view',
            )
            low_quick = html[:50_000].lower()
            if any(m.lower() in low_quick for m in normal_markers):
                return False
        # 짧거나 정상 마커 없음 → block 마커 정밀 검사
        low = html.lower()
        return any(m in low for m in _BLOCK_MARKERS)

    def fetch_with_retry(
        self,
        url: str,
        max_attempts: int = 2,
        backoff_seconds: float = 3.0,
        **fetch_kwargs,
    ) -> Tuple[Optional[str], bool]:
        """
        재시도 + 차단 감지.

        Returns:
            (html, blocked): blocked True면 마지막 시도까지 차단
        """
        for attempt in range(1, max_attempts + 1):
            html = self.fetch(url, **fetch_kwargs)
            if html and not self.is_blocked(html):
                return html, False
            if attempt < max_attempts:
                wait = backoff_seconds * attempt + random.uniform(0, 1.5)
                logger.info(f"[Camoufox] Retry {attempt}/{max_attempts - 1} after {wait:.1f}s")
                time.sleep(wait)
        return None, True


def smoke_test() -> bool:
    """간단한 스모크 테스트 — 네이버 SERP 1회 fetch."""
    test_url = "https://search.naver.com/search.naver?query=%EC%B2%AD%EC%A3%BC+%ED%95%9C%EC%9D%98%EC%9B%90"
    with CamoufoxFetcher(headless=True) as fetcher:
        html, blocked = fetcher.fetch_with_retry(test_url)
        if blocked:
            print("[smoke_test] BLOCKED")
            return False
        if html and len(html) > 5000:
            print(f"[smoke_test] OK - HTML length={len(html)}")
            print(f"  Has '플레이스': {'플레이스' in html or 'place' in html.lower()}")
            return True
        print("[smoke_test] FAIL - empty/short HTML")
        return False


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(name)s | %(message)s')
    success = smoke_test()
    sys.exit(0 if success else 1)
