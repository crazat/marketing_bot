"""
댓글 가능 여부 검증 모듈 (Selenium 기반)

플랫폼별 댓글 작성 가능 여부를 정확하게 확인합니다.
- JavaScript 렌더링 지원
- 실제 댓글 입력창/버튼 확인
- 헤드리스 모드로 빠른 검증
"""

import os
import time
import logging
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class CommentVerifier:
    """Selenium 기반 댓글 가능 여부 검증기"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self._initialized = False

    def _init_driver(self):
        """Chrome WebDriver 초기화"""
        if self._initialized and self.driver:
            return

        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options

            options = Options()
            if self.headless:
                options.add_argument("--headless=new")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")
            options.add_argument("--disable-gpu")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-blink-features=AutomationControlled")
            options.add_experimental_option("excludeSwitches", ["enable-automation"])
            options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

            # ChromeDriver 경로 확인
            driver_path = os.environ.get('CHROMEDRIVER_PATH')

            if driver_path and os.path.exists(driver_path):
                self.driver = webdriver.Chrome(service=Service(driver_path), options=options)
            else:
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    self.driver = webdriver.Chrome(
                        service=Service(ChromeDriverManager().install()),
                        options=options
                    )
                except ImportError:
                    self.driver = webdriver.Chrome(options=options)

            self.driver.set_page_load_timeout(15)
            self._initialized = True
            logger.info("Chrome WebDriver 초기화 완료")

        except Exception as e:
            logger.error(f"WebDriver 초기화 실패: {e}")
            raise

    def close(self):
        """WebDriver 종료"""
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self._initialized = False

    def __enter__(self):
        self._init_driver()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def verify_url(self, url: str, platform: str) -> Dict[str, Any]:
        """
        URL의 댓글 가능 여부 확인

        Returns:
            {
                'accessible': bool,      # URL 접근 가능
                'commentable': bool,     # 댓글 작성 가능
                'reason': str,           # 상태 설명
                'details': dict,         # 추가 정보
                'verified_at': str       # 확인 시간
            }
        """
        if not self._initialized:
            self._init_driver()

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '확인 중...',
            'details': {},
            'verified_at': datetime.now().isoformat()
        }

        try:
            platform_lower = platform.lower()

            if 'cafe' in platform_lower:
                result = self._verify_naver_cafe(url)
            elif 'blog' in platform_lower:
                result = self._verify_naver_blog(url)
            elif 'kin' in platform_lower:
                result = self._verify_naver_kin(url)
            elif 'youtube' in platform_lower:
                result = self._verify_youtube(url)
            elif 'instagram' in platform_lower:
                result = self._verify_instagram(url)
            else:
                result = self._verify_generic(url)

        except Exception as e:
            result['reason'] = f'검증 실패: {str(e)}'
            logger.error(f"URL 검증 오류 [{platform}]: {e}")

        result['verified_at'] = datetime.now().isoformat()
        return result

    def _verify_naver_cafe(self, url: str) -> Dict[str, Any]:
        """네이버 카페 댓글 가능 여부 확인"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '',
            'details': {}
        }

        try:
            self.driver.get(url)
            time.sleep(2)

            # iframe 확인 (카페 본문은 iframe 내에 있음)
            try:
                iframe = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "cafe_main"))
                )
                self.driver.switch_to.frame(iframe)
                result['accessible'] = True
            except Exception:
                # iframe 없이 접근 가능한 경우
                result['accessible'] = True

            page_source = self.driver.page_source

            # 비회원 접근 불가 확인
            if '카페 회원만 볼 수 있는 게시글' in page_source or '멤버에게만 공개' in page_source:
                result['reason'] = '회원 전용 게시글'
                result['commentable'] = False
                result['details']['member_only'] = True
                return result

            # 삭제된 게시글 확인
            if '삭제된 게시글' in page_source or '존재하지 않는 게시글' in page_source:
                result['reason'] = '삭제된 게시글'
                result['accessible'] = False
                return result

            # 댓글 영역 확인
            comment_indicators = [
                (By.CSS_SELECTOR, ".comment_box"),
                (By.CSS_SELECTOR, ".CommentWriter"),
                (By.CSS_SELECTOR, "textarea.comment_inbox"),
                (By.CSS_SELECTOR, ".btn_comment"),
                (By.XPATH, "//*[contains(text(), '댓글 쓰기')]"),
            ]

            for by, selector in comment_indicators:
                try:
                    element = self.driver.find_element(by, selector)
                    if element.is_displayed():
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                        return result
                except Exception:
                    continue

            # 댓글 비활성화 확인
            if '댓글 기능이 꺼져 있습니다' in page_source or '댓글을 작성할 수 없습니다' in page_source:
                result['reason'] = '댓글 기능 비활성화'
                result['commentable'] = False
            else:
                result['reason'] = '댓글 영역 확인 불가'
                result['commentable'] = False

        except Exception as e:
            result['reason'] = f'카페 검증 실패: {str(e)}'
        finally:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

        return result

    def _verify_naver_blog(self, url: str) -> Dict[str, Any]:
        """네이버 블로그 댓글 가능 여부 확인"""
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '',
            'details': {}
        }

        try:
            self.driver.get(url)
            time.sleep(2)

            # iframe 확인 (블로그 본문은 mainFrame 내에 있음)
            try:
                iframe = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.ID, "mainFrame"))
                )
                self.driver.switch_to.frame(iframe)
            except Exception:
                pass

            result['accessible'] = True
            page_source = self.driver.page_source

            # 삭제된 포스트 확인
            if '삭제되었거나 존재하지 않는' in page_source:
                result['reason'] = '삭제된 게시글'
                result['accessible'] = False
                return result

            # 댓글 영역 확인
            comment_indicators = [
                (By.CSS_SELECTOR, ".comment_writer"),
                (By.CSS_SELECTOR, "#commentArea"),
                (By.CSS_SELECTOR, ".area_comment"),
                (By.CSS_SELECTOR, "textarea[placeholder*='댓글']"),
                (By.XPATH, "//*[contains(@class, 'comment')]//textarea"),
            ]

            for by, selector in comment_indicators:
                try:
                    element = self.driver.find_element(by, selector)
                    if element:
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                        return result
                except Exception:
                    continue

            # 댓글 비활성화 확인
            if '댓글 허용 안 함' in page_source or '댓글을 사용할 수 없' in page_source:
                result['reason'] = '댓글 기능 비활성화'
            else:
                # 댓글 수 확인으로 추정
                if '댓글' in page_source and ('0' in page_source or '개' in page_source):
                    result['commentable'] = True
                    result['reason'] = '댓글 가능 추정'
                else:
                    result['reason'] = '댓글 영역 확인 불가'

        except Exception as e:
            result['reason'] = f'블로그 검증 실패: {str(e)}'
        finally:
            try:
                self.driver.switch_to.default_content()
            except Exception:
                pass

        return result

    def _verify_naver_kin(self, url: str) -> Dict[str, Any]:
        """네이버 지식인 답변 가능 여부 확인"""
        from selenium.webdriver.common.by import By

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '',
            'details': {}
        }

        try:
            self.driver.get(url)
            time.sleep(2)

            result['accessible'] = True
            page_source = self.driver.page_source

            # 삭제된 질문 확인
            if '삭제된 질문' in page_source or '존재하지 않는 질문' in page_source:
                result['reason'] = '삭제된 질문'
                result['accessible'] = False
                return result

            # 질문 마감 확인
            if '질문마감' in page_source or '채택완료' in page_source:
                result['reason'] = '질문 마감됨 (채택 완료)'
                result['commentable'] = False
                result['details']['closed'] = True
                return result

            # 답변하기 버튼 확인
            answer_indicators = [
                (By.CSS_SELECTOR, ".answer_write"),
                (By.CSS_SELECTOR, ".btn_answer"),
                (By.XPATH, "//*[contains(text(), '답변하기')]"),
                (By.XPATH, "//*[contains(text(), '답변 작성')]"),
            ]

            for by, selector in answer_indicators:
                try:
                    element = self.driver.find_element(by, selector)
                    if element.is_displayed():
                        result['commentable'] = True
                        result['reason'] = '답변 작성 가능'
                        return result
                except Exception:
                    continue

            # 기본적으로 지식인은 답변 가능
            if '답변' in page_source and '질문' in page_source:
                result['commentable'] = True
                result['reason'] = '답변 가능 추정'
            else:
                result['reason'] = '답변 영역 확인 불가'

        except Exception as e:
            result['reason'] = f'지식인 검증 실패: {str(e)}'

        return result

    def _verify_youtube(self, url: str) -> Dict[str, Any]:
        """YouTube 댓글 가능 여부 확인"""
        from selenium.webdriver.common.by import By

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '',
            'details': {}
        }

        try:
            self.driver.get(url)
            time.sleep(3)  # YouTube는 로딩이 느림

            # 스크롤하여 댓글 영역 로드
            self.driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)

            result['accessible'] = True
            page_source = self.driver.page_source

            # 비공개/삭제된 영상 확인
            if '비공개 동영상' in page_source or '삭제된 동영상' in page_source:
                result['reason'] = '비공개/삭제된 영상'
                result['accessible'] = False
                return result

            # 댓글 비활성화 확인
            if '댓글이 사용 중지되었습니다' in page_source or 'Comments are turned off' in page_source:
                result['reason'] = '댓글 사용 중지됨'
                result['commentable'] = False
                return result

            # 댓글 영역 확인
            comment_indicators = [
                (By.CSS_SELECTOR, "#comments"),
                (By.CSS_SELECTOR, "ytd-comments"),
                (By.CSS_SELECTOR, "#comment-teaser"),
                (By.CSS_SELECTOR, "#placeholder-area"),
            ]

            for by, selector in comment_indicators:
                try:
                    element = self.driver.find_element(by, selector)
                    if element:
                        result['commentable'] = True
                        result['reason'] = '댓글 작성 가능'
                        return result
                except Exception:
                    continue

            result['reason'] = '댓글 영역 확인 불가'

        except Exception as e:
            result['reason'] = f'YouTube 검증 실패: {str(e)}'

        return result

    def _verify_instagram(self, url: str) -> Dict[str, Any]:
        """Instagram 댓글 가능 여부 확인 (제한적)"""
        result = {
            'accessible': False,
            'commentable': False,
            'reason': '로그인 필요 - 수동 확인 권장',
            'details': {'requires_login': True}
        }

        try:
            self.driver.get(url)
            time.sleep(2)

            page_source = self.driver.page_source

            # 로그인 페이지 리다이렉트 확인
            if 'login' in self.driver.current_url.lower():
                result['reason'] = '로그인 필요'
                return result

            # 페이지 존재 확인
            if '페이지를 찾을 수 없습니다' in page_source or 'Page Not Found' in page_source:
                result['reason'] = '게시물 없음/삭제됨'
                result['accessible'] = False
                return result

            result['accessible'] = True

            # 댓글 제한 확인
            if '댓글이 제한되었습니다' in page_source or 'Comments on this post have been limited' in page_source:
                result['reason'] = '댓글 제한됨'
                result['commentable'] = False
                return result

            # 기본적으로 Instagram은 댓글 가능으로 추정
            result['commentable'] = True
            result['reason'] = '댓글 가능 추정 (로그인 필요)'

        except Exception as e:
            result['reason'] = f'Instagram 검증 실패: {str(e)}'

        return result

    def _verify_generic(self, url: str) -> Dict[str, Any]:
        """일반 URL 댓글 가능 여부 확인"""
        from selenium.webdriver.common.by import By

        result = {
            'accessible': False,
            'commentable': False,
            'reason': '',
            'details': {}
        }

        try:
            self.driver.get(url)
            time.sleep(2)

            result['accessible'] = True
            page_source = self.driver.page_source.lower()

            # 일반적인 댓글 영역 확인
            comment_keywords = ['comment', '댓글', 'reply', '답글']

            for keyword in comment_keywords:
                if keyword in page_source:
                    result['commentable'] = True
                    result['reason'] = '댓글 영역 발견'
                    return result

            result['reason'] = '댓글 영역 없음'

        except Exception as e:
            result['reason'] = f'검증 실패: {str(e)}'

        return result

    def verify_batch(self, targets: List[Dict], max_workers: int = 3) -> List[Dict]:
        """
        여러 타겟 일괄 검증

        Args:
            targets: [{'id': int, 'url': str, 'platform': str}, ...]
            max_workers: 동시 처리 수 (기본 3)

        Returns:
            [{'target_id': int, 'result': {...}}, ...]
        """
        results = []

        for target in targets:
            try:
                result = self.verify_url(target['url'], target['platform'])
                results.append({
                    'target_id': target['id'],
                    'url': target['url'],
                    'platform': target['platform'],
                    'result': result
                })
            except Exception as e:
                results.append({
                    'target_id': target['id'],
                    'url': target['url'],
                    'platform': target['platform'],
                    'result': {
                        'accessible': False,
                        'commentable': False,
                        'reason': f'오류: {str(e)}',
                        'verified_at': datetime.now().isoformat()
                    }
                })

        return results


# 간편 사용 함수
def verify_comment_availability(url: str, platform: str) -> Dict[str, Any]:
    """단일 URL 댓글 가능 여부 확인 (간편 함수)"""
    with CommentVerifier(headless=True) as verifier:
        return verifier.verify_url(url, platform)


def verify_batch_comments(targets: List[Dict]) -> List[Dict]:
    """여러 타겟 일괄 검증 (간편 함수)"""
    with CommentVerifier(headless=True) as verifier:
        return verifier.verify_batch(targets)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [안정성 개선] 비동기 래퍼 함수들
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 검증 작업용 스레드 풀 (WebDriver는 blocking이므로 별도 스레드 필요)
_verifier_pool: Optional[ThreadPoolExecutor] = None
_pool_lock = threading.Lock()


def _get_verifier_pool() -> ThreadPoolExecutor:
    """스레드 풀 인스턴스 반환 (지연 초기화)"""
    global _verifier_pool
    if _verifier_pool is None:
        with _pool_lock:
            if _verifier_pool is None:
                _verifier_pool = ThreadPoolExecutor(
                    max_workers=3,
                    thread_name_prefix="CommentVerifier"
                )
                logger.info("CommentVerifier 스레드 풀 초기화 (workers=3)")
    return _verifier_pool


async def verify_url_async(url: str, platform: str) -> Dict[str, Any]:
    """
    [비동기 래퍼] 단일 URL 댓글 가능 여부 확인

    FastAPI 라우터에서 사용:
        result = await verify_url_async(url, platform)

    내부적으로 ThreadPoolExecutor에서 동기 검증 실행
    """
    import asyncio

    loop = asyncio.get_event_loop()
    pool = _get_verifier_pool()

    def _run_verification():
        with CommentVerifier(headless=True) as verifier:
            return verifier.verify_url(url, platform)

    return await loop.run_in_executor(pool, _run_verification)


async def verify_batch_async(targets: List[Dict], max_concurrent: int = 3) -> List[Dict]:
    """
    [비동기 래퍼] 여러 타겟 일괄 검증

    FastAPI 라우터에서 사용:
        results = await verify_batch_async(targets)

    Args:
        targets: [{'id': int, 'url': str, 'platform': str}, ...]
        max_concurrent: 동시 검증 수 (기본 3)

    Returns:
        [{'target_id': int, 'result': {...}}, ...]
    """
    import asyncio

    loop = asyncio.get_event_loop()
    pool = _get_verifier_pool()

    # Semaphore로 동시 실행 제한
    semaphore = asyncio.Semaphore(max_concurrent)

    async def verify_single(target: Dict) -> Dict:
        async with semaphore:
            def _run():
                with CommentVerifier(headless=True) as verifier:
                    return verifier.verify_url(target['url'], target['platform'])

            try:
                result = await loop.run_in_executor(pool, _run)
                return {
                    'target_id': target.get('id'),
                    'url': target['url'],
                    'platform': target['platform'],
                    'result': result
                }
            except Exception as e:
                return {
                    'target_id': target.get('id'),
                    'url': target['url'],
                    'platform': target['platform'],
                    'result': {
                        'accessible': False,
                        'commentable': False,
                        'reason': f'오류: {str(e)}',
                        'verified_at': datetime.now().isoformat()
                    }
                }

    # 모든 타겟 비동기 검증
    tasks = [verify_single(target) for target in targets]
    results = await asyncio.gather(*tasks)
    return list(results)


def shutdown_verifier_pool():
    """서버 종료 시 스레드 풀 정리"""
    global _verifier_pool
    if _verifier_pool:
        _verifier_pool.shutdown(wait=True, cancel_futures=True)
        _verifier_pool = None
        logger.info("CommentVerifier 스레드 풀 종료")
