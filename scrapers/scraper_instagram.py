"""
Instagram Monitor

Instagram Graph API를 사용하여 해시태그 검색 및 미디어 수집.
API 설정이 없는 경우 Google 우회 방식으로 폴백.

Requirements:
- Instagram Graph API 설정 (권장)
- 또는 Selenium + Chrome (폴백)
"""

import sys
import os
import time
import random
from datetime import datetime
from typing import List, Dict, Optional

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager


class InstagramMonitor:
    """Instagram 해시태그 모니터"""

    def __init__(self):
        self.db = DatabaseManager()
        self.api_client = None
        self.use_api = False

        # API 클라이언트 초기화 시도
        self._init_api_client()

        # Total War Mode: Load Master List
        import json
        try:
            kw_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'keywords_master.json'
            )
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.hashtags = []
            for cat, kw_list in data.items():
                for k in kw_list:
                    self.hashtags.append(k.replace(" ", ""))
            print(f"[{datetime.now()}] Loaded {len(self.hashtags)} hashtags.")
        except Exception as e:
            print(f"Failed to load master keywords: {e}")
            self.hashtags = ["청주다이어트", "청주한의원"]

        # 모드 표시
        if self.use_api:
            print(f"[{datetime.now()}] Instagram Graph API MODE (Real-time data)")
        else:
            print(f"[{datetime.now()}] LIMITED MODE: Instagram data is 3-7 days delayed (Google indexing)")
            print(f"[{datetime.now()}] LIMITED MODE: Follower/engagement data NOT available")

    def _init_api_client(self):
        """Instagram Graph API 클라이언트 초기화"""
        try:
            from scrapers.instagram_api_client import InstagramGraphAPI
            self.api_client = InstagramGraphAPI()

            if self.api_client.is_configured():
                # 연결 테스트
                result = self.api_client.test_connection()
                if result["success"]:
                    self.use_api = True
                    print(f"[{datetime.now()}] {result['message']}")

                    # 토큰 만료 경고 및 자동 갱신 시도
                    if self.api_client.is_token_expiring_soon():
                        print(f"[{datetime.now()}] Token expiring soon, attempting refresh...")
                        self.api_client.refresh_token()
                else:
                    print(f"[{datetime.now()}] API connection failed: {result['message']}")
                    self.use_api = False
            else:
                print(f"[{datetime.now()}] Instagram API not configured, using Google fallback")
                self.use_api = False

        except ImportError as e:
            print(f"[{datetime.now()}] Instagram API client not available: {e}")
            self.use_api = False
        except Exception as e:
            print(f"[{datetime.now()}] Error initializing API client: {e}")
            self.use_api = False

    def run(self):
        """메인 실행"""
        print(f"[{datetime.now()}] Starting Instagram Monitor...")

        if self.use_api:
            self._run_api_mode()
        else:
            self._run_google_fallback()

    def _run_api_mode(self):
        """Instagram Graph API 모드로 실행"""
        print(f"[{datetime.now()}] Running in API mode...")

        total_collected = 0

        for tag in self.hashtags:
            print(f"   Checking #{tag} via Graph API...")

            try:
                # 최근 미디어 검색
                media_list = self.api_client.search_hashtag(tag, limit=25)

                for media in media_list:
                    try:
                        # 미디어 데이터 파싱
                        media_id = media.get('id', '')
                        caption = media.get('caption', '') or ''
                        permalink = media.get('permalink', '')
                        timestamp = media.get('timestamp', '')
                        media_url = media.get('media_url', '')
                        like_count = media.get('like_count', 0)
                        comments_count = media.get('comments_count', 0)

                        # 날짜 파싱
                        date_posted = datetime.now().strftime("%Y-%m-%d")
                        if timestamp:
                            try:
                                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                                date_posted = dt.strftime("%Y-%m-%d")
                            except Exception:
                                pass

                        # 제목 생성 (캡션 첫 줄)
                        title = caption.split('\n')[0][:100] if caption else f"Instagram #{tag}"

                        # 콘텐츠 (캡션 + 통계)
                        content = caption[:500] if caption else ""
                        if like_count or comments_count:
                            content += f"\n\n[Likes: {like_count}, Comments: {comments_count}]"

                        # DB 저장
                        self.db.insert_mention({
                            "target_name": "Instagram",
                            "keyword": f"#{tag}",
                            "source": "instagram_api",
                            "title": title,
                            "content": content,
                            "url": permalink,
                            "image_url": media_url or "",
                            "date_posted": date_posted,
                            "extra_data": {
                                "media_id": media_id,
                                "like_count": like_count,
                                "comments_count": comments_count,
                                "media_type": media.get('media_type', '')
                            }
                        })
                        total_collected += 1
                        print(f"      Found: {title[:30]}...")

                    except Exception as e:
                        print(f"      Error parsing media: {e}")
                        continue

                # API 레이트 리밋 준수
                time.sleep(1 + random.random())

            except Exception as e:
                print(f"   Error processing #{tag}: {e}")
                # API 실패 시 해당 태그만 Google 폴백 시도
                self._search_tag_google_fallback(tag)

        print(f"[{datetime.now()}] API mode complete. Collected: {total_collected}")

    def _run_google_fallback(self):
        """Google 우회 모드로 실행 (폴백)"""
        print(f"[{datetime.now()}] Running in Google fallback mode...")

        from selenium import webdriver
        from selenium.webdriver.chrome.service import Service
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.common.by import By
        from webdriver_manager.chrome import ChromeDriverManager

        try:
            from retry_helper import SafeSeleniumDriver

            with SafeSeleniumDriver(headless=True, mobile=True) as driver:
                for tag in self.hashtags:
                    self._search_tag_google(driver, tag)

        except Exception as e:
            print(f"   Critical Error: {e}")

    def _search_tag_google(self, driver, tag: str):
        """Google에서 Instagram 게시물 검색"""
        from selenium.webdriver.common.by import By

        print(f"   Checking #{tag} via Google Bypass...")

        try:
            query = f'site:instagram.com/p/ "{tag}"'
            search_url = f"https://www.google.com/search?q={query}&tbs=qdr:w"

            driver.get(search_url)
            time.sleep(3 + random.random() * 2)

            results = driver.find_elements(By.CSS_SELECTOR, ".g")

            count = 0
            for res in results[:5]:
                try:
                    title_el = res.find_element(By.TAG_NAME, "h3")
                    link_el = res.find_element(By.TAG_NAME, "a")

                    # Snippet 추출
                    snippet = ""
                    try:
                        snippet_el = res.find_element(By.CSS_SELECTOR, ".VwiC3b")
                        snippet = snippet_el.text
                    except Exception:
                        try:
                            snippet_el = res.find_element(By.CSS_SELECTOR, "[data-sncf]")
                            snippet = snippet_el.text
                        except Exception:
                            snippet = res.text[:100] if res.text else ""

                    title = title_el.text
                    link = link_el.get_attribute("href")

                    if "/p/" not in link and "/reel/" not in link:
                        continue

                    self.db.insert_mention({
                        "target_name": "Instagram",
                        "keyword": f"#{tag}",
                        "source": "instagram_limited_google",
                        "title": title,
                        "content": snippet,
                        "url": link,
                        "image_url": "[NOT_AVAILABLE_GOOGLE_BYPASS]",
                        "date_posted": datetime.now().strftime("%Y-%m-%d")
                    })
                    count += 1
                    print(f"      Found One: {title[:30]}...")

                except Exception:
                    continue

            if count == 0:
                print("      No recent posts found on Google.")

            time.sleep(random.uniform(2, 5))

        except Exception as tag_err:
            print(f"   Error processing tag #{tag}: {tag_err}")

    def _search_tag_google_fallback(self, tag: str):
        """단일 태그에 대한 Google 폴백 (API 실패 시)"""
        try:
            from retry_helper import SafeSeleniumDriver

            with SafeSeleniumDriver(headless=True, mobile=True) as driver:
                self._search_tag_google(driver, tag)

        except Exception as e:
            print(f"   Google fallback failed for #{tag}: {e}")

    def search_hashtag(self, hashtag: str, limit: int = 25) -> List[Dict]:
        """
        단일 해시태그 검색 (외부 호출용)

        Args:
            hashtag: 검색할 해시태그
            limit: 최대 결과 수

        Returns:
            미디어 목록
        """
        if self.use_api and self.api_client:
            return self.api_client.search_hashtag(hashtag, limit)

        # 폴백: 빈 목록 (Google 검색은 실시간 반환이 어려움)
        print(f"API not available. Use run() method for Google fallback.")
        return []

    def get_top_posts(self, hashtag: str, limit: int = 9) -> List[Dict]:
        """
        해시태그 인기 게시물 조회 (API 전용)

        Args:
            hashtag: 검색할 해시태그
            limit: 최대 결과 수

        Returns:
            인기 미디어 목록
        """
        if self.use_api and self.api_client:
            return self.api_client.search_hashtag_top(hashtag, limit)

        print(f"API not available for top posts.")
        return []


if __name__ == "__main__":
    monitor = InstagramMonitor()
    monitor.run()
