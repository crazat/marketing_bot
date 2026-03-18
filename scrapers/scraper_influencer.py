import sys
import os
import time
import random
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

class InfluencerScraper:
    def __init__(self):
        self.db = DatabaseManager()
        # Accept keywords from CLI args, else default
        if len(sys.argv) > 1:
            input_str = " ".join(sys.argv[1:])
            self.keywords = [k.strip() for k in input_str.split(',')]
        else:
            self.keywords = ["청주 맛집", "청주 핫플", "청주 미용실", "청주 네일", "청주 카페"] 
        # Keywords that local influencers post about
        
    def run(self):
        print(f"[{datetime.now()}] 🕵️ Starting Influencer Scout...")
        
        from retry_helper import SafeSeleniumDriver

        try:
            with SafeSeleniumDriver(headless=True) as driver:
                for kw in self.keywords:
                    print(f"   🔍 Scouting for '{kw}'...")
                    try:
                        url = f"https://search.naver.com/search.naver?where=view&sm=tab_jum&query={kw}"
                        driver.get(url)
                        
                        # Wait for content
                        WebDriverWait(driver, 10).until(
                            EC.presence_of_element_located((By.CSS_SELECTOR, ".view_wrap"))
                        )
                        
                        # Scroll a bit
                        for _ in range(2):
                            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                            time.sleep(1)
                        
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        items = soup.select(".view_wrap")
                        
                        count = 0
                        for item in items[:5]: # Check top 5 for each keyword (High authority)
                            try:
                                title_el = item.select_one(".title_link._cross_trigger")
                                name_el = item.select_one(".name") # Blogger name
                                link_el = item.select_one(".title_link._cross_trigger")
                                
                                if not title_el or not name_el: continue
                                
                                blog_name = name_el.get_text(strip=True)
                                post_title = title_el.get_text(strip=True)
                                post_url = link_el['href']
                                
                                # Save as Influencer Lead
                                # We use 'Influencer' as target_name
                                self.db.insert_mention({
                                    "target_name": "Influencer",
                                    "keyword": kw,
                                    "source": "naver_blog",
                                    "title": blog_name, # Storing Blog Name as Title for list view
                                    "content": f"Recent Post: {post_title}",
                                    "url": post_url,
                                    "date_posted": datetime.now().strftime("%Y-%m-%d")
                                })
                                count += 1
                                print(f"      ✨ Found Candidate: {blog_name}")
                            except Exception as e: 
                                print(f"      ⚠️ Item Error: {e}")
                                continue
                    except Exception as e:
                        print(f"   ⚠️ Keyword '{kw}' Error: {e}")

        except Exception as e:
            print(f"   ❌ Critical Error: {e}")

if __name__ == "__main__":
    scraper = InfluencerScraper()
    scraper.run()
