import time
import json
import os
import sys
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Add parent directory to path to import db
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from utils import logger

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class NaverViewScraper:
    def __init__(self):
        # Path fixed to resolve correctly regardless of CWD
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.config_path = os.path.join(base_dir, 'config', 'targets.json')
        self._load_config()
        self.db = DatabaseManager()
        self.driver = None

    def _load_config(self):
        with open(self.config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

    # _init_driver is no longer needed as we use context manager in methods
    
    def search_view_tab(self, keyword):
        """Scrape Naver View tab for a specific keyword."""
        from retry_helper import SafeSeleniumDriver
        
        url = f"https://search.naver.com/search.naver?where=view&sm=tab_jum&query={keyword}"
        
        results = []
        
        # Use Stealth Driver in Context
        with SafeSeleniumDriver(headless=True) as driver:
            driver.get(url)
            
            # Wait for items to load
            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "li.bx, .view_wrap, .api_no_result"))
                )
            except Exception:
                print(f"     ⚠️ Timeout waiting for results for '{keyword}'")
                return []

            # Scroll down to trigger lazy load
            for _ in range(3):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)

            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Check for "No Results" message explicitly
            no_result = soup.select_one('.api_no_result')
            if no_result:
                print(f"     ℹ️ No results found for '{keyword}' (Verified).")
                return []

            # [Robustness] Try multiple selectors including modern Smart Block attributes
            items = []
            
            # Strategy 1: Smart Block / Generic View Items with data attributes
            items = soup.select('li[data-cr-rank]')
            
            # Strategy 2: Legacy Class based
            if not items:
                items = soup.select('li.bx, .view_wrap')
            
            # Strategy 3: Fallback for mixed content
            if not items:
                items = soup.select('.total_wrap')
            
            # [Robustness] If no items found but also no "No Result" message, it's a selector failure or block.
            if not items and not no_result:
                # Check for "Blocked" or "Captcha"
                if "captcha" in driver.page_source.lower() or "traffic" in driver.page_source.lower():
                    print(f"     🚨 DETECTED CAPTCHA/BLOCK during '{keyword}' scan.")
                    return [] # Or raise Alert
                
                print(f"     ⚠️ Suspicious: No items found for '{keyword}' but no 'No Result' msg. Check Selectors.")
                return []

            for item in items[:15]: # Top 15
                try:
                    title_el = item.select_one('.title_link') or item.select_one('.api_txt_lines.total_tit')
                    desc_el = item.select_one('.dsc_link') or item.select_one('.dsc_txt') or item.select_one('.api_txt_lines.dsc_txt')
                    date_el = item.select_one('.sub') or item.select_one('.sub_time') or item.select_one('.date')
                    name_el = item.select_one('.name') or item.select_one('.sub_txt')
                    
                    if not title_el: continue
                    
                    link = title_el['href'] if title_el.has_attr('href') else ""
                    title = title_el.get_text(strip=True)
                    content = desc_el.get_text(strip=True) if desc_el else ""
                    date = date_el.get_text(strip=True) if date_el else ""
                    source_name = name_el.get_text(strip=True) if name_el else "Unknown"

                    # Determine source type
                    source_type = 'naver_view'
                    if 'blog.naver' in link: source_type = 'naver_blog'
                    elif 'cafe.naver' in link: source_type = 'naver_cafe'

                    # Deep Crawl Enhancement (Slow but Quality)
                    try:
                        full_content = self._deep_crawl(driver, link, source_type)
                        if full_content:
                            content = full_content # Override snippet
                    except Exception as deep_err:
                         # Deep crawl failure shouldn't stop the flow
                         pass

                    results.append({
                        "title": title,
                        "content": content,
                        "url": link,
                        "date_posted": date,
                        "source": source_type,
                        "author": source_name
                    })
                except Exception as e:
                    continue
                    
        return results

    def _deep_crawl(self, driver, url, source_type):
        """
        Visits the URL and extracts full content.
        Handles Naver Blog/Cafe iframes.
        Uses the passed 'driver' from the context manager.
        """
        import random
        try:
            # Open new tab
            driver.execute_script(f"window.open('{url}', '_blank');")
            driver.switch_to.window(driver.window_handles[-1])
            time.sleep(random.uniform(2, 4)) # Random delay for human-like behavior
            
            # Helper to clean text
            def extract_clean_text(soup_obj, selector):
                el = soup_obj.select_one(selector)
                if el:
                    # Remove scripts/styles
                    for s in el(['script', 'style', 'iframe']): s.decompose()
                    return el.get_text(separator=' ').strip()[:3000] # Limit 3000 chars
                return None

            full_text = None
            
            if source_type == 'naver_blog':
                # Switch to iframe 'mainFrame'
                try:
                    driver.switch_to.frame("mainFrame")
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    # Common selectors for Naver Blog
                    full_text = extract_clean_text(soup, '.se-main-container') or \
                                extract_clean_text(soup, '#postViewArea') or \
                                extract_clean_text(soup, '.post_ct')
                except Exception:
                    pass
                    
            elif source_type == 'naver_cafe':
                # Switch to iframe 'cafe_main'
                try:
                    driver.switch_to.frame("cafe_main")
                    page_source = driver.page_source
                    soup = BeautifulSoup(page_source, 'html.parser')
                    full_text = extract_clean_text(soup, '.se-main-container') or \
                                extract_clean_text(soup, '.ContentRenderer') or \
                                extract_clean_text(soup, '#tbody')
                except Exception:
                    pass
            else:
                # General Web
                page_source = self.driver.page_source
                soup = BeautifulSoup(page_source, 'html.parser')
                full_text = extract_clean_text(soup, 'body')

            driver.close()
            driver.switch_to.window(driver.window_handles[0])
            
            return full_text
            
        except Exception:
            # Ensure we close tab and return even on error
            if len(driver.window_handles) > 1:
                driver.close()
                driver.switch_to.window(driver.window_handles[0])
            return None

    def run(self):
        # self._init_driver() <- Removed
        print(f"[{datetime.now()}] Starting Broad View Scraping...")
        
        search_suffixes = ["후기", "비용", "추천", "부작용"] # Keywords to append
        
        for target in self.config['targets']:
            name = target['name']
            print(f"\n🔎 Searching for '{name}'...")
            
            for suffix in search_suffixes:
                query = f"{name} {suffix}"
                print(f"   - Query: {query}")
                
                try:
                    # search_view_tab now manages its own driver context
                    results = self.search_view_tab(query)
                    new_count = 0
                    for r in results:
                        # Save to DB
                        saved = self.db.insert_mention({
                            "target_name": name,
                            "keyword": suffix,
                            "source": r['source'],
                            "title": r['title'],
                            "content": r['content'],
                            "url": r['url'],
                            "date_posted": r['date_posted']
                        })
                        if saved: new_count += 1
                        
                    print(f"     ✅ Found {len(results)} items, {new_count} new.")
                except Exception as e:
                    print(f"     ❌ Error: {e}")
                    
        print("\n✨ Broad Scraping Complete.")
        # Cleanup handled by context managers in sub-methods
        # if hasattr(self, '_safe_driver_ctx'): ...

    def check_view_rank(self, target_keywords=["청주 다이어트", "청주 한의원", "청주 교통사고"]):
        """
        The Sniper Logic:
        Checks the rank of 'Kyurim' or 'Specific Blog ID' in VIEW tab.
        """
        """
        The Sniper Logic:
        Checks the rank of 'Kyurim' or 'Specific Blog ID' in VIEW tab.
        """
        # self._init_driver() <- Removed
        print(f"\n🎯 [The Sniper] Starting Rank Check (Real Data)...")
        from retry_helper import SafeSeleniumDriver
        
        my_blog_identifiers = ["규림", "kyurim", "sline"] # Identifiers to recognize 'us'
        
        with SafeSeleniumDriver(headless=True) as driver:
            for keyword in target_keywords:
                print(f"   🔫 Sniping: '{keyword}'...")
                url = f"https://search.naver.com/search.naver?where=view&sm=tab_jum&query={keyword}"
                driver.get(url)
                time.sleep(2)
                
                # Get Top 10
                soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # [Robustness] Selector Sync
            items = soup.select('li[data-cr-rank]')
            if not items:
                items = soup.select('li.bx, .view_wrap')
            if not items:
                 items = soup.select('.total_wrap')
                
            rank = 0
            found = False
            
            for idx, item in enumerate(items[:10]):
                txt = item.get_text()
                link_area = item.select_one('.title_link')
                url_txt = link_area['href'] if link_area else ""
                
                # Check match
                for ident in my_blog_identifiers:
                    if ident in txt or ident in url_txt:
                        rank = idx + 1
                        found = True
                        break
                if found: break
                
            status = f"Rank {rank}" if found else "Out of Top 10"
            print(f"      👉 Result: {status}")
            
            # Save Rank to DB
            try:
                self.db.insert_rank(keyword, rank, "naver_view_real")
            except Exception as e:
                print(f"      ❌ DB Error: {e}")

            # [Vision AI Data Collection]
            # Download top 3 thumbnail images for Trend Analysis
            try:
                import requests
                img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'images_scraped')
                os.makedirs(img_dir, exist_ok=True)
                
                # Extract image URLs from top 3
                for i, item in enumerate(items[:3]):
                    img_tag = item.select_one('.thumb_area img') or item.select_one('.api_get_img')
                    if img_tag and img_tag.has_attr('src'):
                        img_url = img_tag['src']
                        # Download
                        try:
                            res = requests.get(img_url, timeout=5)
                            if res.status_code == 200:
                                fname = f"rank_{i+1}_{keyword.replace(' ', '_')}.jpg"
                                with open(os.path.join(img_dir, fname), 'wb') as f:
                                    f.write(res.content)
                                print(f"      📸 Downloaded: {fname}")
                        except Exception:
                            pass  # Image download optional
            except Exception as e:
                print(f"      ⚠️ Image Download Failed: {e}")

if __name__ == "__main__":
    scraper = NaverViewScraper()
    try:
        # 1. Broad Mentions
        scraper.run()
        # 2. Sniper Rank Check
        scraper.check_view_rank(["청주 다이어트", " 청주 여드름", "청주 교통사고 한의원"])
    finally:
        if scraper.driver:
            try:
                scraper.driver.quit()
            except Exception as e:
                logger.debug(f"Driver cleanup: {e}")
