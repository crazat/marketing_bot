
import sys
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

import json
import logging
import threading
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from utils import ConfigManager, logger
from agent_crew import AgentCrew
from db.database import DatabaseManager
from selenium.common.exceptions import NoSuchElementException, TimeoutException, WebDriverException

# [Phase 5-1] 설정값 외부화
try:
    from config.app_settings import get_settings
    _app_settings = get_settings()
except ImportError:
    _app_settings = None

# [안정성 개선] 스레드 안전한 싱글톤 패턴
_shared_config = None
_shared_crew = None
_shared_db = None
_singleton_lock = threading.Lock()


def _get_shared_config():
    """ConfigManager 싱글톤 접근자 (스레드 안전)"""
    global _shared_config
    if _shared_config is None:
        with _singleton_lock:
            if _shared_config is None:  # Double-checked locking
                _shared_config = ConfigManager()
    return _shared_config


def _get_shared_crew():
    """AgentCrew 싱글톤 접근자 (스레드 안전)"""
    global _shared_crew
    if _shared_crew is None:
        with _singleton_lock:
            if _shared_crew is None:
                _shared_crew = AgentCrew()
    return _shared_crew


def _get_shared_db():
    """DatabaseManager 싱글톤 접근자 (스레드 안전)"""
    global _shared_db
    if _shared_db is None:
        with _singleton_lock:
            if _shared_db is None:
                _shared_db = DatabaseManager()
    return _shared_db


class CarrotFarmer:
    """
    Component for monitoring Karrot Market (Danggeun) and drafting replies.
    "The Friendly Neighbor Strategy"
    """

    def __init__(self, use_shared_resources=True):
        """
        Args:
            use_shared_resources: True면 싱글톤 리소스 사용 (scheduler 등에서 반복 호출 시 효율적)
        """
        if use_shared_resources:
            self.config = _get_shared_config()
            self.crew = _get_shared_crew()
            self.db = _get_shared_db()
        else:
            self.config = ConfigManager()
            self.crew = AgentCrew()
            self.db = DatabaseManager()
        self.driver = None

    def _google_search_karrot(self, keyword="청주 다이어트"):
        """
        Since scraping Karrot directly is hard, we use Google site search.
        site:daangn.com "청주" "keyword"
        """
        from retry_helper import SafeSeleniumDriver
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        results = []
        try:
            # Query: site:daangn.com "청주" {keyword}
            query = f"site:daangn.com \"청주\" \"{keyword}\""
            url = f"https://www.google.com/search?q={query}"

            # Load Selectors - 2026년 2월 업데이트된 Google 검색 결과 선택자
            selectors = self.config.get_selector("google_search", "result_container")
            if not selectors:
                # 여러 가능한 선택자를 시도 (Google은 자주 변경됨)
                selectors = "div.MjjYud, div.g, .tF2Cxc, div[data-sokoban-container], div.Gx5Zad"

            with SafeSeleniumDriver(mobile=False, headless=True) as driver:
                driver.get(url)

                # 페이지 로딩 대기 (5초로 증가)
                import time
                time.sleep(5)

                # 디버깅: 페이지 제목과 URL 확인
                logger.info(f"[CarrotFarmer] Page title: {driver.title}")
                logger.info(f"[CarrotFarmer] Current URL: {driver.current_url}")

                # WebDriverWait: 동적 대기 (최대 10초, 요소 로드 시 즉시 진행)
                elements = []
                for sel in selectors.split(","):
                    try:
                        sel = sel.strip()
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                        )
                        found = driver.find_elements(By.CSS_SELECTOR, sel)
                        if found:
                            elements = found
                            logger.info(f"[CarrotFarmer] Found {len(elements)} Google results (selector: {sel})")
                            break
                    except TimeoutException:
                        logger.debug(f"[CarrotFarmer] Selector '{sel}' timeout, trying next...")
                        continue

                if not elements:
                    logger.warning("[CarrotFarmer] No elements found with known selectors")
                    # 디버깅을 위해 페이지 소스 저장
                    try:
                        import os
                        debug_file = os.path.join(os.path.dirname(__file__), "debug_carrot_google.html")
                        with open(debug_file, "w", encoding="utf-8") as f:
                            f.write(driver.page_source)
                        logger.info(f"[CarrotFarmer] Debug HTML saved to: {debug_file}")

                        # 스크린샷도 저장
                        screenshot_file = debug_file.replace(".html", ".png")
                        driver.save_screenshot(screenshot_file)
                        logger.info(f"[CarrotFarmer] Screenshot saved to: {screenshot_file}")
                    except Exception as debug_err:
                        logger.error(f"[CarrotFarmer] Debug save failed: {debug_err}")
                
                for i, g in enumerate(elements[:10]):  # 상위 10개 확인
                    try:
                        # h3 태그 찾기 (제목)
                        title_el = g.find_element(By.TAG_NAME, "h3")
                        title = title_el.text.strip()

                        if not title:
                            continue

                        # 링크 찾기 (여러 방법 시도)
                        link = ""
                        try:
                            link_el = g.find_element(By.TAG_NAME, "a")
                            link = link_el.get_attribute("href")
                        except NoSuchElementException:
                            # h3의 부모 a 태그 찾기
                            try:
                                link_el = title_el.find_element(By.XPATH, "..")
                                if link_el.tag_name == "a":
                                    link = link_el.get_attribute("href")
                            except Exception:
                                pass

                        if not link:
                            logger.debug(f"[CarrotFarmer] No link found for: {title[:30]}...")
                            continue

                        # Snippet 추출 (여러 선택자 시도)
                        snippet = ""
                        snip_sels = self.config.get_selector("google_search", "snippet") or ".VwiC3b, .lEBKkf, div[data-sncf], div.s, .st"
                        for s_sel in snip_sels.split(","):
                            try:
                                s_sel = s_sel.strip()
                                snippet_el = g.find_element(By.CSS_SELECTOR, s_sel)
                                snippet = snippet_el.text.strip()
                                if snippet:
                                    break
                            except NoSuchElementException:
                                continue
                            except Exception as snippet_e:
                                logger.debug(f"[CarrotFarmer] Snippet extraction failed (selector: {s_sel}): {snippet_e}")
                                continue

                        # snippet이 없으면 모든 텍스트 추출
                        if not snippet:
                            snippet = g.text.replace(title, "").strip()[:200]

                        # URL 유효성 검증 (정확한 도메인 매칭)
                        try:
                            parsed_url = urlparse(link)
                            netloc = parsed_url.netloc.lower()
                            # 정확히 daangn.com이거나 서브도메인(*.daangn.com)만 허용
                            is_valid_domain = (netloc == "daangn.com" or netloc.endswith(".daangn.com"))
                            if parsed_url.netloc and is_valid_domain:
                                results.append({
                                    "title": title,
                                    "content": snippet,
                                    "url": link,
                                    "user": "Daangn User"
                                })
                        except Exception as url_e:
                            logger.debug(f"[CarrotFarmer] Invalid URL skipped: {url_e}")
                    except Exception as parse_e:
                        logger.warning(f"[CarrotFarmer] Result #{i} parse error: {parse_e}")
                        continue
        except TimeoutException as e:
            logger.warning(f"[CarrotFarmer] Search timeout (retryable): {e}")
            return []
        except WebDriverException as e:
            logger.error(f"[CarrotFarmer] WebDriver error (retryable): {e}")
            return []
        except Exception as e:
            logger.error(f"[CarrotFarmer] Search failed: {type(e).__name__}: {e}")
            return []

        return results

    def _generate_reply(self, post):
        """
        단일 포스트에 대한 AI 답글 생성 (병렬 처리용 헬퍼 메서드)

        Args:
            post: dict with 'title', 'content' keys

        Returns:
            dict with 'post_title', 'post_content', 'draft_reply' or None on failure
        """
        # 프롬프트 인젝션 방지: JSON 이스케이프 적용
        safe_title = json.dumps(post['title'], ensure_ascii=False)
        safe_content = json.dumps(post['content'], ensure_ascii=False)

        prompt = f"""
        You are a friendly neighbor living in Yulryang-dong, Cheongju.
        Write a comment on a Karrot Market post.

        [Post]
        Title: {safe_title}
        Content: {safe_content}

        [Your Role]
        You are actually the director of Kyurim Clinic, but you want to sound like a helpful local expert first, not just an ad robot.
        Be warm, empathetic, and briefly mention 'Kyurim Clinic' as a good option without being pushy.
        Use emojis. Keep it under 200 chars.
        """

        try:
            reply = self.crew.writer.generate(prompt)
            return {
                "post_title": post['title'],
                "post_content": post['content'],
                "draft_reply": reply
            }
        except Exception as e:
            logger.error(f"[CarrotFarmer] Reply generation failed for '{post['title'][:30]}...': {type(e).__name__}")
            return None

    def harvest_and_reply(self, keyword="청주 다이어트", max_workers=None, save_to_db=True):
        """
        1. Search REAL Karrot posts via Google.
        2. Draft reply (병렬 처리).
        3. Save to database (선택적).

        Args:
            keyword: 검색 키워드
            max_workers: 병렬 처리 워커 수 (기본값: 설정에서 로드, API 제한 준수)
            save_to_db: DB에 저장 여부 (기본값 True)

        Returns:
            dict: {
                "success": bool,
                "total_posts": int,
                "successful_replies": int,
                "failed_count": int,
                "saved_count": int,
                "results": list[dict]
            }
        """
        logger.info(f"[CarrotFarmer] Searching posts for keyword: '{keyword}'")

        real_posts = self._google_search_karrot(keyword)

        if not real_posts:
            logger.info("[CarrotFarmer] No posts found for this keyword")
            return {
                "success": False,
                "total_posts": 0,
                "successful_replies": 0,
                "failed_count": 0,
                "saved_count": 0,
                "results": []
            }

        responses = []
        failed_count = 0
        saved_count = 0

        # [Phase 5-1] 설정에서 워커 수와 타임아웃 로드
        _workers = max_workers
        _timeout = 60
        if _app_settings:
            _workers = max_workers or _app_settings.carrot_max_workers
            _timeout = _app_settings.ai_reply_timeout
        else:
            _workers = max_workers or 3

        # 병렬 처리로 AI 답글 생성 (API 제한 준수)
        with ThreadPoolExecutor(max_workers=_workers) as executor:
            future_to_post = {
                executor.submit(self._generate_reply, post): post
                for post in real_posts
            }

            for future in as_completed(future_to_post):
                post = future_to_post[future]
                try:
                    result = future.result(timeout=_timeout)
                    if result:
                        responses.append(result)

                        # DB에 저장
                        if save_to_db:
                            try:
                                self.db.insert_mention({
                                    "source": "carrot",  # 백엔드 API가 'carrot%' 패턴으로 검색
                                    "title": post['title'],
                                    "content": post['content'],
                                    "url": post['url'],
                                    "target_name": post.get('user', '익명'),
                                    "status": "New",
                                    "scraped_at": datetime.now().isoformat(),
                                    "memo": result.get('draft_reply', '')  # ✅ AI 답글 저장
                                })
                                saved_count += 1
                                logger.info(f"[CarrotFarmer] Saved to DB with AI reply: {post['title'][:30]}...")
                            except Exception as db_err:
                                logger.error(f"[CarrotFarmer] DB save failed: {db_err}")
                    else:
                        failed_count += 1
                except Exception as e:
                    logger.error(f"[CarrotFarmer] Parallel reply failed for '{post['title'][:30]}...': {type(e).__name__}")
                    failed_count += 1

        logger.info(f"[CarrotFarmer] Completed: {len(responses)} replies generated, {saved_count} saved to DB")

        return {
            "success": len(responses) > 0,
            "total_posts": len(real_posts),
            "successful_replies": len(responses),
            "failed_count": failed_count,
            "saved_count": saved_count,
            "results": responses
        }

if __name__ == "__main__":
    farmer = CarrotFarmer()

    # 여러 키워드로 스캔 (청주 한의원 핵심 카테고리)
    keywords = [
        "청주 다이어트",
        "청주 한의원",
        "청주 교통사고",
        "청주 비염",
        "청주 탈모"
    ]

    total_saved = 0
    for keyword in keywords:
        logger.info(f"[CarrotFarmer] 🔍 Scanning keyword: {keyword}")
        result = farmer.harvest_and_reply(keyword, save_to_db=True)

        print(f"\n{'='*60}")
        print(f"키워드: {keyword}")
        print(f"Success: {result['success']}")
        print(f"Total Posts: {result['total_posts']}, Successful: {result['successful_replies']}, Saved: {result.get('saved_count', 0)}, Failed: {result['failed_count']}")
        print(f"{'='*60}")

        total_saved += result.get('saved_count', 0)

        if result['results']:
            for r in result['results'][:3]:  # 처음 3개만 출력
                print(f"\nPost: {r['post_title']}")
                print(f"Reply: {r['draft_reply']}")

    print(f"\n✅ 전체 스캔 완료: {total_saved}개 리드를 DB에 저장했습니다.")
