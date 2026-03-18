"""
YouTube Sentinel - Marketing Bot YouTube Scraper.

하이브리드 모드 지원:
- YouTube Data API v3 (우선): API 키가 있고 할당량이 남은 경우
- Selenium 폴백: API 미사용 또는 할당량 초과 시
"""
import sys
import os
import time
import json
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from retry_helper import SafeSeleniumDriver

# Lead Classifier (optional)
try:
    from lead_classifier import LeadClassifier, LeadPriority
    CLASSIFIER_AVAILABLE = True
except ImportError:
    CLASSIFIER_AVAILABLE = False
    LeadClassifier = None
    LeadPriority = None

# YouTube API Client (optional)
try:
    from scrapers.youtube_api_client import YouTubeAPIClient, QuotaExceededError
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    YouTubeAPIClient = None
    QuotaExceededError = Exception


class YouTubeSentinel:
    """YouTube 댓글에서 잠재 고객(리드)을 감지하는 스크래퍼."""

    def __init__(self):
        self.db = DatabaseManager()
        self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        # 선택자 로드 (외부 설정 파일)
        self.selectors = self._load_selectors()

        # API 클라이언트 초기화 (하이브리드 모드)
        self.api_client = None
        if API_AVAILABLE:
            self.api_client = YouTubeAPIClient()
            if self.api_client.is_available():
                print(f"[{datetime.now()}] YouTube API mode enabled")
            else:
                print(f"[{datetime.now()}] YouTube Selenium mode (API not configured)")

        # 리드 분류기 초기화
        self.lead_classifier = None
        if CLASSIFIER_AVAILABLE:
            self.lead_classifier = LeadClassifier(use_nlp=False)  # NLP는 high priority만 사용
            print(f"[{datetime.now()}] Lead Classifier enabled")

        # CLI 키워드 파싱
        self.keywords = self._parse_keywords()

    def _load_selectors(self) -> dict:
        """외부 설정 파일에서 YouTube 선택자 로드."""
        default_selectors = {
            "search_results": {
                "video_title": "#video-title, a#video-title",
                "video_link": "a#video-title"
            },
            "video_page": {
                "comment_section": "#comments, ytd-comments",
                "comment_thread": "ytd-comment-thread-renderer",
                "comment_text": "#content-text, yt-formatted-string#content-text"
            }
        }

        try:
            selector_path = os.path.join(self.root_dir, 'config', 'selectors.json')
            with open(selector_path, 'r', encoding='utf-8') as f:
                all_selectors = json.load(f)
            return all_selectors.get('youtube', default_selectors)
        except Exception as e:
            print(f"[Warning] Failed to load selectors.json: {e}, using defaults")
            return default_selectors

    def _parse_keywords(self) -> list:
        """CLI 인자 또는 마스터 키워드 리스트에서 키워드 파싱."""
        if len(sys.argv) > 1:
            input_str = " ".join(sys.argv[1:])
            return [k.strip() for k in input_str.split(',')]

        # Total War Mode: Load Master List
        try:
            kw_path = os.path.join(self.root_dir, 'config', 'keywords_master.json')
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            keywords = []
            for cat, kw_list in data.items():
                keywords.extend(kw_list)
            print(f"[{datetime.now()}] Total War Mode: Loaded {len(keywords)} keywords.")
            return keywords
        except Exception as e:
            print(f"Failed to load master keywords: {e}")
            return ["청주 다이어트", "청주 한의원"]

    def _find_element_with_fallback(self, driver, selector_str: str, by=By.CSS_SELECTOR):
        """다중 선택자 폴백 로직으로 요소 찾기."""
        selectors = [s.strip() for s in selector_str.split(',')]
        for selector in selectors:
            try:
                elements = driver.find_elements(by, selector)
                if elements:
                    return elements
            except Exception:
                continue
        return []

    def run(self):
        """메인 실행 - 하이브리드 모드."""
        print(f"[{datetime.now()}] Starting YouTube Sentinel...")

        # 하이브리드 모드: API 먼저 시도
        if self.api_client and self.api_client.is_available():
            print(f"[{datetime.now()}] Using YouTube API mode")
            self._run_api_mode()
        else:
            print(f"[{datetime.now()}] Using Selenium mode")
            self._run_selenium_mode()

    def _run_api_mode(self):
        """YouTube Data API v3를 사용한 스캔."""
        for kw in self.keywords:
            print(f"   Searching YouTube for '{kw}'...")
            try:
                videos = self.api_client.search_videos(kw, max_results=3)

                for video in videos:
                    print(f"      Analyzing Video: {video['title'][:40]}...")
                    try:
                        comments = self.api_client.get_video_comments(
                            video['video_id'],
                            max_results=10
                        )
                        self._process_comments(comments, kw, video['url'])
                    except QuotaExceededError:
                        print(f"      Quota exceeded, falling back to Selenium")
                        self._run_selenium_mode()
                        return
                    except Exception as e:
                        print(f"      Error getting comments: {e}")

            except QuotaExceededError:
                print(f"   Quota exceeded, falling back to Selenium mode")
                self._run_selenium_mode()
                return
            except Exception as e:
                print(f"   API Error: {e}")
                self._run_selenium_mode()
                return

    def _run_selenium_mode(self):
        """Selenium을 사용한 스캔 (폴백)."""
        with SafeSeleniumDriver(headless=True) as driver:
            try:
                for kw in self.keywords:
                    print(f"   Searching YouTube for '{kw}'...")
                    url = f"https://www.youtube.com/results?search_query={kw}"
                    driver.get(url)
                    time.sleep(5)  # 대기 시간 증가 (3초 → 5초)

                    # 다중 선택자로 동영상 링크 찾기
                    video_links = []
                    selector = self.selectors.get('search_results', {}).get(
                        'video_title', '#video-title'
                    )
                    elements = self._find_element_with_fallback(driver, selector)

                    for el in elements[:3]:
                        href = el.get_attribute('href')
                        if href:
                            video_links.append(href)

                    for v_url in video_links:
                        print(f"      Analyzing Video: {v_url}")
                        driver.get(v_url)
                        time.sleep(5)  # 대기 시간 증가

                        # Scroll to load comments
                        driver.execute_script("window.scrollTo(0, 600);")
                        time.sleep(3)

                        # Wait for comments
                        try:
                            comment_selector = self.selectors.get('video_page', {}).get(
                                'comment_thread', 'ytd-comment-thread-renderer'
                            )
                            WebDriverWait(driver, 10).until(
                                EC.presence_of_element_located((By.TAG_NAME, comment_selector.split(',')[0].strip()))
                            )
                        except TimeoutException:
                            print(f"         Timeout: Comments not loaded")
                            self.db.log_system_event(
                                module="YouTubeSentinel",
                                level="WARNING",
                                message=f"Comment loading timeout for video: {v_url[:50]}..."
                            )
                            continue
                        except NoSuchElementException:
                            print(f"         Comments disabled on this video")
                            continue

                        # Extract comments with fallback selectors
                        comment_text_selector = self.selectors.get('video_page', {}).get(
                            'comment_text', '#content-text'
                        )
                        comments = self._find_element_with_fallback(driver, comment_text_selector)

                        extracted_comments = []
                        for c_el in comments[:10]:
                            text = c_el.text
                            if text:
                                extracted_comments.append({'text': text})

                        self._process_comments(extracted_comments, kw, v_url)

            except Exception as e:
                print(f"   Error: {e}")
                self.db.log_system_event(
                    module="YouTubeSentinel",
                    level="ERROR",
                    message=f"Critical error in YouTube scan: {str(e)[:100]}"
                )

    def _process_comments(self, comments: list, keyword: str, video_url: str):
        """
        댓글 처리 및 리드 감지 (LeadClassifier 연동).

        Args:
            comments: 댓글 목록 (API: {'text': str, ...} / Selenium: {'text': str})
            keyword: 검색 키워드
            video_url: 동영상 URL
        """
        lead_count = 0

        for idx, comment in enumerate(comments):
            text = comment.get('text', '')
            if not text:
                continue

            # 댓글별 고유 URL 생성 (video_url + 댓글 해시)
            import hashlib
            comment_hash = hashlib.md5(text.encode('utf-8')).hexdigest()[:8]
            unique_url = f"{video_url}#comment-{comment_hash}"

            # LeadClassifier 사용 가능 시 고급 분류
            if self.lead_classifier:
                result = self.lead_classifier.classify(text)

                # NONE이 아닌 경우만 저장
                if result.priority != LeadPriority.NONE:
                    score = self.lead_classifier.get_lead_score(result)

                    # 메모에 분류 정보 포함
                    memo = f"[Score:{score}] [Priority:{result.priority.value}] [Intent:{result.intent.value}]"
                    if result.matched_keywords:
                        memo += f" [Keywords:{','.join(result.matched_keywords[:3])}]"

                    self.db.insert_mention({
                        "target_name": "YouTube",
                        "keyword": keyword,
                        "source": "youtube_comment",
                        "title": f"YouTube Lead (Score: {score})",
                        "content": text,
                        "url": unique_url,
                        "date_posted": datetime.now().strftime("%Y-%m-%d"),
                        "memo": memo
                    })
                    lead_count += 1
                    print(f"         Found Lead (Score:{score}): {text[:30]}...")
            else:
                # 폴백: 기존 키워드 매칭
                lead_keywords = ["얼마", "가격", "정보", "어디", "추천", "비용", "문의"]
                if any(x in text for x in lead_keywords):
                    self.db.insert_mention({
                        "target_name": "YouTube",
                        "keyword": keyword,
                        "source": "youtube_comment",
                        "title": "YouTube Lead Comment",
                        "content": text,
                        "url": unique_url,
                        "date_posted": datetime.now().strftime("%Y-%m-%d")
                    })
                    lead_count += 1
                    print(f"         Found Lead: {text[:30]}...")

        if lead_count > 0:
            print(f"      Saved {lead_count} leads from this video")


if __name__ == "__main__":
    scraper = YouTubeSentinel()
    scraper.run()
