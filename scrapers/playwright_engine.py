"""
Playwright 기반 브라우저 엔진
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 B-1a] Selenium BrowserPool의 Playwright 대체 구현

기존 BrowserPool 인터페이스와 호환되는 async 버전:
- get_page() / return_page() / close_all() 패턴
- 한국 로케일/타임존 자동 설정
- 리소스 차단 (이미지/폰트/CSS) 으로 속도 향상
- navigator.webdriver 감지 우회

사용법:
    async with PlaywrightPool(pool_size=3) as pool:
        page = await pool.get_page()
        try:
            await page.goto("https://m.place.naver.com/...")
            # ... 스크래핑 로직
        finally:
            await pool.return_page(page)
"""

import asyncio
import random
import logging
from typing import List, Optional, Dict, Any, Set
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# 실제 브라우저 User-Agent (Chrome 120~131)
USER_AGENTS_DESKTOP = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
]

USER_AGENTS_MOBILE = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.69 Mobile Safari/537.36",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.69 Mobile Safari/537.36",
]

# 차단할 리소스 타입 (속도 향상용)
BLOCKED_RESOURCE_TYPES = {"image", "font", "media"}
BLOCKED_URL_PATTERNS = [
    "*.woff", "*.woff2", "*.ttf", "*.otf",
    "*.png", "*.jpg", "*.jpeg", "*.gif", "*.svg", "*.webp", "*.ico",
    "*.mp4", "*.webm",
    "*google-analytics*", "*googletagmanager*", "*facebook.net*",
]


class PlaywrightPool:
    """
    Playwright 기반 비동기 브라우저 컨텍스트 풀

    BrowserPool(Selenium)과 동일한 역할:
    - 브라우저 컨텍스트를 재사용하여 생성 오버헤드 감소
    - 최대 pool_size개의 컨텍스트만 유지
    - 한국 로케일/타임존 자동 설정
    """

    def __init__(
        self,
        pool_size: int = 3,
        mobile: bool = False,
        headless: bool = True,
        block_resources: bool = True,
        page_load_timeout: int = 30000,
    ):
        """
        Args:
            pool_size: 최대 동시 페이지 수
            mobile: 모바일 에뮬레이션 여부
            headless: 헤드리스 모드
            block_resources: 이미지/폰트/CSS 차단 여부
            page_load_timeout: 페이지 로드 타임아웃 (ms)
        """
        self.pool_size = pool_size
        self.mobile = mobile
        self.headless = headless
        self.block_resources = block_resources
        self.page_load_timeout = page_load_timeout

        self._playwright = None
        self._browser = None
        self._available_pages: asyncio.Queue = asyncio.Queue()
        self._all_contexts: List = []
        self._closed = False
        self._lock = asyncio.Lock()
        self._created_count = 0

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_all()

    async def start(self):
        """Playwright 및 브라우저 시작"""
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise ImportError(
                "playwright가 설치되지 않았습니다. "
                "pip install playwright && playwright install chromium"
            )

        self._playwright = await async_playwright().start()

        launch_args = [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-blink-features=AutomationControlled",
        ]

        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=launch_args,
        )

        logger.info(
            f"🎭 PlaywrightPool started "
            f"(size={self.pool_size}, mobile={self.mobile}, headless={self.headless})"
        )

    async def _create_page(self):
        """새 브라우저 컨텍스트 + 페이지 생성"""
        if self._browser is None:
            raise RuntimeError("PlaywrightPool이 시작되지 않았습니다. start()를 먼저 호출하세요.")

        ua = random.choice(
            USER_AGENTS_MOBILE if self.mobile else USER_AGENTS_DESKTOP
        )

        context_options = {
            "locale": "ko-KR",
            "timezone_id": "Asia/Seoul",
            "user_agent": ua,
            "bypass_csp": True,
            "java_script_enabled": True,
        }

        # 모바일 에뮬레이션
        if self.mobile:
            context_options.update({
                "viewport": {"width": 375, "height": 812},
                "device_scale_factor": 3,
                "is_mobile": True,
                "has_touch": True,
            })
        else:
            context_options.update({
                "viewport": {"width": 1920, "height": 1080},
            })

        context = await self._browser.new_context(**context_options)

        # navigator.webdriver 감지 우회
        await context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            // Chrome plugins 위장
            Object.defineProperty(navigator, 'plugins', {
                get: () => [1, 2, 3, 4, 5],
            });
            // languages 설정
            Object.defineProperty(navigator, 'languages', {
                get: () => ['ko-KR', 'ko', 'en-US', 'en'],
            });
        """)

        page = await context.new_page()

        # 리소스 차단 (이미지, 폰트, 미디어 등)
        if self.block_resources:
            await page.route(
                "**/*.{png,jpg,jpeg,gif,svg,webp,ico,woff,woff2,ttf,otf,mp4,webm}",
                lambda route: route.abort()
            )

        # 타임아웃 설정
        page.set_default_timeout(self.page_load_timeout)
        page.set_default_navigation_timeout(self.page_load_timeout)

        self._all_contexts.append(context)
        self._created_count += 1

        logger.debug(f"🎭 New page created (total: {self._created_count})")
        return page

    async def get_page(self):
        """풀에서 페이지 가져오기 (없으면 새로 생성)"""
        if self._closed:
            raise RuntimeError("PlaywrightPool is closed")

        # 풀에 가용 페이지가 있으면 사용
        try:
            page = self._available_pages.get_nowait()
            # 페이지가 여전히 유효한지 확인
            if not page.is_closed():
                logger.debug(f"🎭 Page retrieved from pool (available: ~{self._available_pages.qsize()})")
                return page
            # 닫힌 페이지면 새로 생성
        except asyncio.QueueEmpty:
            pass

        # 풀이 비어있으면 새로 생성
        async with self._lock:
            return await self._create_page()

    async def return_page(self, page):
        """페이지를 풀에 반환 (상태 초기화)"""
        if page is None or page.is_closed():
            return

        if self._closed:
            try:
                await page.context.close()
            except Exception:
                pass
            return

        try:
            # 상태 초기화: 쿠키 및 스토리지 삭제
            await page.context.clear_cookies()
            await page.evaluate("() => { try { localStorage.clear(); sessionStorage.clear(); } catch(e) {} }")

            if self._available_pages.qsize() < self.pool_size:
                await self._available_pages.put(page)
                logger.debug(f"🎭 Page returned to pool (available: ~{self._available_pages.qsize()})")
            else:
                # 풀이 가득 차면 컨텍스트 종료
                await page.context.close()
                logger.debug("🎭 Pool full, page context closed")
        except Exception as e:
            logger.debug(f"🎭 Page return failed: {e}")
            try:
                await page.context.close()
            except Exception:
                pass

    async def close_all(self):
        """모든 리소스 정리"""
        self._closed = True

        # 풀의 모든 페이지 정리
        while not self._available_pages.empty():
            try:
                page = self._available_pages.get_nowait()
                if not page.is_closed():
                    await page.context.close()
            except Exception:
                pass

        # 모든 컨텍스트 정리
        for context in self._all_contexts:
            try:
                await context.close()
            except Exception:
                pass
        self._all_contexts.clear()

        # 브라우저 종료
        if self._browser:
            try:
                await self._browser.close()
            except Exception:
                pass

        # Playwright 종료
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass

        logger.info(f"🎭 PlaywrightPool closed (total pages created: {self._created_count})")


@asynccontextmanager
async def managed_page(pool: PlaywrightPool):
    """
    편의 컨텍스트 매니저: 자동으로 get/return 처리

    Usage:
        async with managed_page(pool) as page:
            await page.goto(url)
            # ... 스크래핑
        # 자동으로 pool에 반환됨
    """
    page = await pool.get_page()
    try:
        yield page
    finally:
        await pool.return_page(page)


async def scroll_and_collect(
    page,
    scroll_container_selector: str = None,
    min_scrolls: int = 10,
    max_scrolls: int = 50,
    scroll_amount: int = 800,
    scroll_delay: float = 0.5,
) -> int:
    """
    점진적 스크롤로 동적 콘텐츠 로드 (기존 Selenium 스크롤 로직과 동일)

    Args:
        page: Playwright 페이지
        scroll_container_selector: 스크롤 대상 CSS 선택자 (None이면 body)
        min_scrolls: 최소 스크롤 횟수 (조기 종료 방지)
        max_scrolls: 최대 스크롤 횟수
        scroll_amount: 1회 스크롤 양 (px)
        scroll_delay: 스크롤 간 대기 시간 (초)

    Returns:
        실제 스크롤 수행 횟수
    """
    for attempt in range(max_scrolls):
        if scroll_container_selector:
            await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{scroll_container_selector}');
                    if (el) el.scrollTop += {scroll_amount};
                }}
            """)
        else:
            await page.evaluate(f"window.scrollBy(0, {scroll_amount})")

        await asyncio.sleep(scroll_delay)

        # 최소 스크롤 횟수까지는 계속 진행
        if attempt < min_scrolls:
            continue

        # 끝 도달 판정
        if scroll_container_selector:
            at_bottom = await page.evaluate(f"""
                () => {{
                    const el = document.querySelector('{scroll_container_selector}');
                    if (!el) return true;
                    return (el.scrollTop + el.clientHeight >= el.scrollHeight - 10);
                }}
            """)
        else:
            at_bottom = await page.evaluate("""
                () => (window.innerHeight + window.scrollY >= document.body.scrollHeight - 10)
            """)

        if at_bottom:
            logger.debug(f"🎭 Scroll reached bottom at attempt {attempt + 1}")
            return attempt + 1

    logger.debug(f"🎭 Max scrolls reached ({max_scrolls})")
    return max_scrolls


async def random_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """네이버 차단 방지를 위한 랜덤 딜레이"""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)
    return delay
