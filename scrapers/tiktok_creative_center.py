"""
TikTok Creative Center Scraper
트렌딩 해시태그, 음악, 크리에이터 수집 (로그인 불필요)
https://ads.tiktok.com/business/creativecenter/
"""
import sys
import os
import time
import random
import json
from datetime import datetime

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from retry_helper import SafeSeleniumDriver, CircuitBreaker, retry_with_backoff

import logging
logger = logging.getLogger("TikTokCreativeCenter")


class TikTokCreativeCenterScraper:
    """
    TikTok Creative Center에서 트렌드 데이터 수집
    - 트렌딩 해시태그 (한국)
    - 트렌딩 음악/사운드
    - 인기 크리에이터
    """

    BASE_URL = "https://ads.tiktok.com/business/creativecenter"
    HASHTAG_URL = f"{BASE_URL}/inspiration/popular/hashtag/pc/ko"
    MUSIC_URL = f"{BASE_URL}/inspiration/popular/music/pc/ko"
    CREATOR_URL = f"{BASE_URL}/inspiration/popular/creator/pc/ko"

    def __init__(self, headless=True):
        self.db = DatabaseManager()
        self.headless = headless
        self.circuit_breaker = CircuitBreaker(name="tiktok_cc", threshold=3, reset_after=300)

        # Load selectors from config
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> dict:
        """Load TikTok Creative Center selectors from config."""
        try:
            config_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'selectors.json'
            )
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get('tiktok_creative_center', {})
        except Exception as e:
            logger.warning(f"Failed to load selectors config: {e}. Using defaults.")
            return {}

    @retry_with_backoff(max_retries=3, initial_delay=2.0, exceptions=(Exception,))
    def scrape_hashtags(self, limit=50) -> list:
        """
        트렌딩 해시태그 수집

        Returns:
            list: 해시태그 정보 리스트 [{name, rank, posts, views, url}, ...]
        """
        if self.circuit_breaker.is_open():
            logger.warning("[CircuitBreaker] TikTok CC circuit is OPEN. Skipping hashtags.")
            return []

        print(f"[{datetime.now()}] Scraping TikTok Creative Center - Hashtags (limit: {limit})...")
        hashtags = []

        try:
            with SafeSeleniumDriver(headless=self.headless) as driver:
                driver.get(self.HASHTAG_URL)
                time.sleep(5)  # Wait for React hydration

                # Multi-strategy selector fallback
                items = self._find_trend_items(driver, 'hashtag')

                if not items:
                    logger.warning("No hashtag items found with any selector strategy.")
                    self.circuit_breaker.record_failure()
                    return []

                print(f"   Found {len(items)} hashtag items")

                for idx, item in enumerate(items[:limit], 1):
                    try:
                        data = self._parse_hashtag_item(driver, item, idx)
                        if data:
                            hashtags.append(data)

                            # Save to DB
                            self.db.insert_mention({
                                "target_name": "TikTok",
                                "keyword": data['name'],
                                "source": "tiktok_cc_hashtag",
                                "title": f"#{data['name']} (Rank #{data['rank']})",
                                "content": f"Posts: {data.get('posts', 'N/A')}, Views: {data.get('views', 'N/A')}",
                                "url": data['url'],
                                "image_url": "",
                                "date_posted": datetime.now().strftime("%Y-%m-%d")
                            })

                    except Exception as e:
                        logger.debug(f"Failed to parse hashtag item {idx}: {e}")
                        continue

                self.circuit_breaker.record_success()
                print(f"   Collected {len(hashtags)} hashtags successfully.")

        except Exception as e:
            logger.error(f"Hashtag scraping failed: {e}")
            self.circuit_breaker.record_failure()
            raise

        return hashtags

    @retry_with_backoff(max_retries=3, initial_delay=2.0, exceptions=(Exception,))
    def scrape_music(self, limit=30) -> list:
        """
        트렌딩 음악/사운드 수집

        Returns:
            list: 음악 정보 리스트 [{name, artist, rank, videos, url}, ...]
        """
        if self.circuit_breaker.is_open():
            logger.warning("[CircuitBreaker] TikTok CC circuit is OPEN. Skipping music.")
            return []

        print(f"[{datetime.now()}] Scraping TikTok Creative Center - Music (limit: {limit})...")
        music_list = []

        try:
            with SafeSeleniumDriver(headless=self.headless) as driver:
                driver.get(self.MUSIC_URL)
                time.sleep(5)

                items = self._find_trend_items(driver, 'music')

                if not items:
                    logger.warning("No music items found.")
                    self.circuit_breaker.record_failure()
                    return []

                print(f"   Found {len(items)} music items")

                for idx, item in enumerate(items[:limit], 1):
                    try:
                        data = self._parse_music_item(driver, item, idx)
                        if data:
                            music_list.append(data)

                            # Save to DB
                            self.db.insert_mention({
                                "target_name": "TikTok",
                                "keyword": data['name'],
                                "source": "tiktok_cc_music",
                                "title": f"{data['name']} - {data.get('artist', 'Unknown')} (Rank #{data['rank']})",
                                "content": f"Videos using: {data.get('videos', 'N/A')}",
                                "url": data['url'],
                                "image_url": data.get('cover_url', ''),
                                "date_posted": datetime.now().strftime("%Y-%m-%d")
                            })

                    except Exception as e:
                        logger.debug(f"Failed to parse music item {idx}: {e}")
                        continue

                self.circuit_breaker.record_success()
                print(f"   Collected {len(music_list)} music tracks successfully.")

        except Exception as e:
            logger.error(f"Music scraping failed: {e}")
            self.circuit_breaker.record_failure()
            raise

        return music_list

    @retry_with_backoff(max_retries=3, initial_delay=2.0, exceptions=(Exception,))
    def scrape_creators(self, limit=20) -> list:
        """
        인기 크리에이터 수집

        Returns:
            list: 크리에이터 정보 리스트 [{name, handle, rank, followers, url}, ...]
        """
        if self.circuit_breaker.is_open():
            logger.warning("[CircuitBreaker] TikTok CC circuit is OPEN. Skipping creators.")
            return []

        print(f"[{datetime.now()}] Scraping TikTok Creative Center - Creators (limit: {limit})...")
        creators = []

        try:
            with SafeSeleniumDriver(headless=self.headless) as driver:
                driver.get(self.CREATOR_URL)
                time.sleep(5)

                items = self._find_trend_items(driver, 'creator')

                if not items:
                    logger.warning("No creator items found.")
                    self.circuit_breaker.record_failure()
                    return []

                print(f"   Found {len(items)} creator items")

                for idx, item in enumerate(items[:limit], 1):
                    try:
                        data = self._parse_creator_item(driver, item, idx)
                        if data:
                            creators.append(data)

                            # Save to DB
                            self.db.insert_mention({
                                "target_name": "TikTok",
                                "keyword": data.get('handle', data['name']),
                                "source": "tiktok_cc_creator",
                                "title": f"@{data.get('handle', data['name'])} (Rank #{data['rank']})",
                                "content": f"Followers: {data.get('followers', 'N/A')}",
                                "url": data['url'],
                                "image_url": data.get('avatar_url', ''),
                                "date_posted": datetime.now().strftime("%Y-%m-%d")
                            })

                    except Exception as e:
                        logger.debug(f"Failed to parse creator item {idx}: {e}")
                        continue

                self.circuit_breaker.record_success()
                print(f"   Collected {len(creators)} creators successfully.")

        except Exception as e:
            logger.error(f"Creator scraping failed: {e}")
            self.circuit_breaker.record_failure()
            raise

        return creators

    def _find_trend_items(self, driver, content_type: str) -> list:
        """
        Multi-strategy selector fallback for finding trend items.

        Args:
            driver: Selenium WebDriver
            content_type: 'hashtag', 'music', or 'creator'

        Returns:
            list: WebElement list
        """
        from selenium.webdriver.common.by import By
        from selenium.webdriver.support.ui import WebDriverWait
        from selenium.webdriver.support import expected_conditions as EC

        items = []

        # Scroll to load more content
        try:
            driver.execute_script("window.scrollTo(0, 500);")
            time.sleep(2)
        except Exception:
            pass

        # Strategy 1: TikTok Creative Center specific - Card based layout
        cc_selectors = [
            # Card-based layout (2024+ design)
            "[class*='CardPc_container']",
            "[class*='RankingCardPc']",
            "[class*='CommonDataList'] > div",
            "[class*='DataCard']",
            # Table-based layout
            "[class*='TableChart'] tbody tr",
            "[class*='RankTable'] tbody tr",
            # Generic ranking items
            "[class*='rankingItem']",
            "[class*='trending-item']",
        ]

        for css in cc_selectors:
            try:
                items = driver.find_elements(By.CSS_SELECTOR, css)
                # Filter out header/nav elements
                items = [i for i in items if i.text and len(i.text) > 2 and not i.text.startswith('Hashtags') and not i.text.startswith('Songs') and not i.text.startswith('Creators')]
                if items and len(items) >= 3:
                    print(f"      [Strategy 1] CC CSS '{css}' found {len(items)} items")
                    return items
            except Exception:
                continue

        # Strategy 2: Config-based selectors
        selectors = self.selectors.get(content_type, {})
        css_selectors = selectors.get('item_list', [])

        for css in css_selectors:
            try:
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, css))
                )
                items = driver.find_elements(By.CSS_SELECTOR, css)
                items = [i for i in items if i.text and len(i.text) > 2]
                if items:
                    print(f"      [Strategy 2] Config CSS '{css}' found {len(items)} items")
                    return items
            except Exception:
                continue

        # Strategy 3: Table rows with rank numbers
        try:
            # Find rows that contain rank numbers (1, 2, 3, etc.)
            all_rows = driver.find_elements(By.CSS_SELECTOR, "tr, [role='row'], [class*='Row']")
            ranked_items = []
            for row in all_rows:
                text = row.text.strip()
                # Check if starts with a number (rank)
                if text and text[0].isdigit():
                    ranked_items.append(row)
            if ranked_items and len(ranked_items) >= 3:
                print(f"      [Strategy 3] Ranked rows found {len(ranked_items)} items")
                return ranked_items
        except Exception:
            pass

        # Strategy 4: Links containing hashtag/music/creator URLs
        url_patterns = {
            'hashtag': '/tag/',
            'music': '/music/',
            'creator': '/@'
        }
        pattern = url_patterns.get(content_type, '')
        if pattern:
            try:
                links = driver.find_elements(By.CSS_SELECTOR, f"a[href*='{pattern}']")
                # Get parent containers
                containers = []
                for link in links:
                    try:
                        parent = link.find_element(By.XPATH, "./ancestor::div[contains(@class, 'Card') or contains(@class, 'Item') or contains(@class, 'Row')][1]")
                        if parent not in containers:
                            containers.append(parent)
                    except Exception:
                        containers.append(link)
                if containers and len(containers) >= 3:
                    print(f"      [Strategy 4] URL pattern found {len(containers)} items")
                    return containers
            except Exception:
                pass

        # Strategy 5: Generic fallback - any div with substantial text content
        try:
            divs = driver.find_elements(By.CSS_SELECTOR, "main div, [class*='content'] div")
            content_divs = []
            for div in divs:
                text = div.text.strip()
                # Look for divs that have hashtag-like content
                if text and ('#' in text or len(text.split('\n')) >= 2) and len(text) < 500:
                    if not any(skip in text for skip in ['Hashtags', 'Songs', 'Creators', 'Login', 'Sign']):
                        content_divs.append(div)
            if content_divs and len(content_divs) >= 3:
                print(f"      [Strategy 5] Content divs found {len(content_divs)} items")
                return content_divs[:50]  # Limit
        except Exception:
            pass

        print(f"      [Warning] No items found with any strategy")
        return items

    def _parse_hashtag_item(self, driver, item, rank: int) -> dict:
        """Parse a hashtag item element."""
        from selenium.webdriver.common.by import By
        import re

        data = {'rank': rank}
        item_text = item.text.strip()

        # Skip navigation/header items
        skip_words = ['Hashtags', 'Songs', 'Creators', 'TikTok Videos', 'Login', 'For You']
        if any(item_text.startswith(sw) for sw in skip_words):
            return None

        # Method 1: Extract from link with /tag/ URL
        try:
            link = item.find_element(By.CSS_SELECTOR, "a[href*='/tag/']")
            href = link.get_attribute('href')
            # Extract hashtag from URL: /tag/hashtag_name
            match = re.search(r'/tag/([^/?]+)', href)
            if match:
                data['name'] = match.group(1)
                data['url'] = href
        except Exception:
            pass

        # Method 2: Find text that looks like a hashtag
        if 'name' not in data:
            lines = item_text.split('\n')
            for line in lines:
                line = line.strip()
                # Skip numbers only (ranks) and stats
                if line and not line.isdigit() and not re.match(r'^[\d.]+[KMB]?$', line):
                    # Skip common non-hashtag words
                    if line not in skip_words and len(line) > 1 and len(line) < 50:
                        data['name'] = line.replace('#', '').strip()
                        break

        # Method 3: Try specific selectors
        if 'name' not in data:
            name_selectors = [
                "[class*='hashtag']",
                "[class*='name']",
                "[class*='title']",
                "a",
                "span"
            ]
            for sel in name_selectors:
                try:
                    el = item.find_element(By.CSS_SELECTOR, sel)
                    text = el.text.strip().replace('#', '')
                    if text and len(text) > 1 and text not in skip_words:
                        data['name'] = text
                        break
                except Exception:
                    continue

        if 'name' not in data:
            # Fallback: full item text, first meaningful word
            text = item_text.split('\n')[0].replace('#', '').strip()
            if text:
                data['name'] = text[:50]

        # URL
        try:
            link = item.find_element(By.TAG_NAME, 'a')
            data['url'] = link.get_attribute('href') or f"https://www.tiktok.com/tag/{data.get('name', '')}"
        except Exception:
            data['url'] = f"https://www.tiktok.com/tag/{data.get('name', '')}"

        # Stats (posts/views) - varies by layout
        try:
            text = item.text
            lines = text.split('\n')
            for line in lines:
                if 'M' in line or 'K' in line or 'B' in line:
                    # Likely a stat value
                    if 'posts' not in data:
                        data['posts'] = line.strip()
                    else:
                        data['views'] = line.strip()
        except Exception:
            pass

        return data if 'name' in data else None

    def _parse_music_item(self, driver, item, rank: int) -> dict:
        """Parse a music item element."""
        from selenium.webdriver.common.by import By

        data = {'rank': rank}

        # Name and artist
        try:
            text_parts = item.text.split('\n')
            if text_parts:
                data['name'] = text_parts[0].strip()[:100]
            if len(text_parts) > 1:
                data['artist'] = text_parts[1].strip()[:50]
        except Exception:
            pass

        # Cover image
        try:
            img = item.find_element(By.TAG_NAME, 'img')
            data['cover_url'] = img.get_attribute('src')
        except Exception:
            pass

        # URL
        try:
            link = item.find_element(By.TAG_NAME, 'a')
            data['url'] = link.get_attribute('href') or "https://www.tiktok.com/"
        except Exception:
            data['url'] = "https://www.tiktok.com/"

        # Video count
        try:
            text = item.text
            import re
            match = re.search(r'(\d+[KMB]?\+?)\s*(videos?)?', text, re.IGNORECASE)
            if match:
                data['videos'] = match.group(1)
        except Exception:
            pass

        return data if 'name' in data else None

    def _parse_creator_item(self, driver, item, rank: int) -> dict:
        """Parse a creator item element."""
        from selenium.webdriver.common.by import By

        data = {'rank': rank}

        # Name and handle
        try:
            text_parts = item.text.split('\n')
            for part in text_parts:
                if part.startswith('@'):
                    data['handle'] = part.replace('@', '').strip()
                elif not data.get('name') and len(part) > 1:
                    data['name'] = part.strip()[:50]
        except Exception:
            pass

        if 'name' not in data:
            data['name'] = data.get('handle', f'Creator_{rank}')

        # Avatar
        try:
            img = item.find_element(By.TAG_NAME, 'img')
            data['avatar_url'] = img.get_attribute('src')
        except Exception:
            pass

        # URL
        try:
            link = item.find_element(By.TAG_NAME, 'a')
            href = link.get_attribute('href')
            data['url'] = href or f"https://www.tiktok.com/@{data.get('handle', '')}"
        except Exception:
            data['url'] = f"https://www.tiktok.com/@{data.get('handle', data['name'])}"

        # Followers
        try:
            text = item.text
            import re
            match = re.search(r'(\d+\.?\d*[KMB]?)\s*(followers?)?', text, re.IGNORECASE)
            if match:
                data['followers'] = match.group(1)
        except Exception:
            pass

        return data if 'name' in data or 'handle' in data else None

    def run_full_scan(self) -> dict:
        """
        전체 트렌드 데이터 수집 (해시태그 + 음악 + 크리에이터)

        Returns:
            dict: {'hashtags': [...], 'music': [...], 'creators': [...], 'total': int}
        """
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] TikTok Creative Center - Full Scan")
        print(f"{'='*60}\n")

        results = {
            'hashtags': [],
            'music': [],
            'creators': [],
            'total': 0,
            'errors': []
        }

        # Hashtags (main priority)
        try:
            results['hashtags'] = self.scrape_hashtags(limit=50)
        except Exception as e:
            results['errors'].append(f"Hashtags: {e}")
            print(f"   Hashtag scraping failed: {e}")

        time.sleep(random.uniform(3, 5))  # Rate limiting

        # Music
        try:
            results['music'] = self.scrape_music(limit=30)
        except Exception as e:
            results['errors'].append(f"Music: {e}")
            print(f"   Music scraping failed: {e}")

        time.sleep(random.uniform(3, 5))

        # Creators
        try:
            results['creators'] = self.scrape_creators(limit=20)
        except Exception as e:
            results['errors'].append(f"Creators: {e}")
            print(f"   Creator scraping failed: {e}")

        results['total'] = (
            len(results['hashtags']) +
            len(results['music']) +
            len(results['creators'])
        )

        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] Scan Complete!")
        print(f"   Hashtags: {len(results['hashtags'])}")
        print(f"   Music: {len(results['music'])}")
        print(f"   Creators: {len(results['creators'])}")
        print(f"   Total: {results['total']}")
        if results['errors']:
            print(f"   Errors: {len(results['errors'])}")
        print(f"{'='*60}\n")

        return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TikTok Creative Center Scraper")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--hashtags-only", action="store_true", help="Only scrape hashtags")
    parser.add_argument("--limit", type=int, default=50, help="Max items per category")
    args = parser.parse_args()

    scraper = TikTokCreativeCenterScraper(headless=not args.headed)

    if args.hashtags_only:
        hashtags = scraper.scrape_hashtags(limit=args.limit)
        print(f"\nCollected {len(hashtags)} hashtags")
        for h in hashtags[:10]:
            print(f"   #{h['name']} (Rank {h['rank']})")
    else:
        results = scraper.run_full_scan()

        # Summary
        if results['hashtags']:
            print("\nTop 10 Trending Hashtags:")
            for h in results['hashtags'][:10]:
                print(f"   #{h['name']} - Rank {h['rank']}")
