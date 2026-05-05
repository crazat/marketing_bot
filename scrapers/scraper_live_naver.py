import sys
import json
import time
import random
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Force UTF-8 output for Windows consoles
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory to path to import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

class NaverLiveScraper:
    """
    Phase 1: Real Scraper for Naver Place/Blog.
    Uses Selenium for dynamic content and BS4 for parsing.
    """
    def __init__(self, config_path='marketing_bot/targets.json'):
        self.config_path = config_path
        self._load_config()
        self.driver = None
        self.data_dir = os.path.join(os.path.dirname(config_path), 'scraped_data')
        os.makedirs(self.data_dir, exist_ok=True)
        self.db = DatabaseManager() # Initialize DB

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    def _init_driver(self):
        if self.driver:
            return

        # [Phase 2 Fix] Use Unified SafeSeleniumDriver
        from retry_helper import SafeSeleniumDriver
        print(">> Initializing Safe Selenium Driver...")
        try:
            # We store ctx to exit later if needed (manual mode)
            self._driver_ctx = SafeSeleniumDriver(headless=True)
            self.driver = self._driver_ctx.__enter__()
            self.driver.set_page_load_timeout(30)
        except Exception as e:
            print(f"❌ Driver Init Failed: {e}")
            raise

    def _cleanup_driver(self):
        """Cleanup driver resources if initialized manually."""
        if hasattr(self, '_driver_ctx') and self._driver_ctx:
            try:
                self._driver_ctx.__exit__(None, None, None)
            except Exception as e:
                print(f"⚠️ Driver cleanup warning: {e}")
            self._driver_ctx = None
        self.driver = None

    def scrape_place_reviews(self, url, selectors, limit=10):
        """
        Scrapes visitor reviews from Naver Place Mobile URL.
        """
        print(f"   Getting Reviews from: {url}")
        self._init_driver()
        
        # Ensure we are on the review page
        if "/review/visitor" not in url:
            # Try to construct the review URL if it's a home URL
            # Typical format: https://m.place.naver.com/hospital/ID/home -> .../ID/review/visitor
            if "/home" in url:
                url = url.replace("/home", "/review/visitor")
            else:
                 # Just append if it looks like a base ID url
                 url = url.rstrip('/') + "/review/visitor"
        
        try:
            self.driver.get(url)

            # [성능 최적화] 고정 대기 → 명시적 대기로 전환
            try:
                # 리뷰 컨테이너가 로드될 때까지 대기 (최대 10초)
                review_selector = selectors.get('review_container', '.pui__X35jYm')
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, review_selector))
                )
            except Exception:
                # 셀렉터 대기 실패 시 최소 대기
                time.sleep(2)

            # Scroll logic if needed (naive scroll)
            # For now, just scrape what's visible or scroll once
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")

            # [성능 최적화] 스크롤 후 새 콘텐츠 로드 대기
            try:
                WebDriverWait(self.driver, 5).until(
                    lambda d: d.execute_script("return document.readyState") == "complete"
                )
            except Exception:
                time.sleep(1)

            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            
            reviews = []
            # Use selector from config
            items = soup.select(selectors['review_container'])
            
            print(f"   Found {len(items)} raw review items.")
            
            for item in items[:limit]:
                try:
                    text_el = item.select_one(selectors['review_text'])
                    date_el = item.select_one(selectors['date'])
                    nick_el = item.select_one(selectors['nickname'])
                    
                    text = text_el.get_text(strip=True) if text_el else ""
                    date = date_el.get_text(strip=True) if date_el else ""
                    nickname = nick_el.get_text(strip=True) if nick_el else "Unknown"
                    
                    # Filter out empty or system messages
                    if not text: continue

                    reviews.append({
                        "date": date,
                        "nickname": nickname,
                        "content": text,
                        "source": "naver_place"
                    })
                except Exception as e:
                    # print(f"    Error parsing item: {e}")
                    continue
                    
            return reviews
        except Exception as e:
            print(f"   ⚠️ Scrape Error {url}: {e}")
            return []

    def run(self):
        print(f"[{datetime.now()}] Starting Live Scraping Phase 1...")
        # self._init_driver() # Defer to context manager
        self._load_config() # Reload in case of changes
        
        all_data = []
        selectors = self.config.get('scraper_settings', {}).get('naver_place', {})
        
        if not selectors:
            print("❌ Error: No CSS selectors found in config!")
            return

        from retry_helper import SafeSeleniumDriver

        try:
            with SafeSeleniumDriver(headless=True) as driver:
                self.driver = driver # Set for helper methods
                
                for target in self.config['targets']:
                    name = target['name']
                    place_url = target['monitor_urls'].get('naver_place')
                    
                    if not place_url:
                        continue
                        
                    print(f"🔎 Scraping {name}...")
                    
                    try:
                        reviews = self.scrape_place_reviews(place_url, selectors)
                        if reviews:
                            # Save to JSON (Legacy)
                            entry = {
                                "target_name": name,
                                "scraped_at": datetime.now().isoformat(),
                                "reviews": reviews
                            }
                            all_data.append(entry)
                            
                            # Save to DB (New)
                            new_count = 0
                            for r in reviews:
                                saved = self.db.insert_mention({
                                    "target_name": name,
                                    "keyword": "Place Review",
                                    "source": "naver_place",
                                    "title": f"Review by {r['nickname']} ({r['date']})",
                                    "content": r['content'],
                                    "url": place_url, # Reviews don't have individual URLs easily
                                    "date_posted": r['date']
                                })
                                if saved: new_count += 1
                            
                            print(f"   ✅ Collected {len(reviews)} reviews ({new_count} new to DB).")
                        else:
                            print("   ⚠️ No reviews found.")
                    except Exception as e:
                        print(f"   ❌ Failed to scrape {name}: {e}")
                    
                    # Etiquette delay between targets
                    time.sleep(random.uniform(1, 3))
        
        except Exception as e:
             print(f"❌ Run Error: {e}")

        # Save aggregated JSON if any
        if all_data:
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"{timestamp}_raw.json"
            filepath = os.path.join(self.data_dir, filename)
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(all_data, f, ensure_ascii=False, indent=4)
                print(f"💾 Saved raw data to {filepath}")
            except Exception as e:
                print(f"⚠️ Save Error: {e}")

        self._cleanup_driver()

if __name__ == "__main__":
    bot = NaverLiveScraper()
    bot.run()
