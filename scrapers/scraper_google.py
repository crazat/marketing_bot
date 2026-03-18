import sys
import os
import time
import random
import logging
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from retry_helper import SafeSeleniumDriver

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

logger = logging.getLogger(__name__)

class GoogleRanker:
    def __init__(self, headless=True):
        self.db = DatabaseManager()
        self.target_name = "규림"
        
        # [MODIFIED] Dynamic Keyword Loading
        # 1. Default fallback
        self.keywords = ["청주 한의원", "청주 다이어트"] 
        
        # 2. Check for CLI arguments (comma separated)
        cli_args = [arg for arg in sys.argv[1:] if not arg.startswith("--")]
        if cli_args:
             joined = " ".join(cli_args)
             if "," in joined:
                 self.keywords = [k.strip() for k in joined.split(',')]
             else:
                 self.keywords = cli_args
                 
        # 3. If no CLI args, try loading from config
        elif os.path.exists("marketing_bot/config/keywords.json"):
            try:
                with open("marketing_bot/config/keywords.json", 'r', encoding='utf-8') as f:
                     data = json.load(f)
                     if "keywords" in data:
                         self.keywords = data["keywords"]
            except Exception as e:
                logger.warning(f"Failed to load keywords config: {e}")
                pass
        
        # Ensure flattened list if loading failed
        if not isinstance(self.keywords, list):
             self.keywords = ["청주 한의원"]

        print(f"🔎 Tracking Keywords: {self.keywords}")
            
        self.headless = headless
        
    def run(self):
        print(f"[{datetime.now()}] 🌏 Starting Google Ranker (Stealth Mode)...")
        summary_report = []

        try:
            # Use SafeSeleniumDriver for robust cleanup
            with SafeSeleniumDriver(headless=self.headless, mobile=False, timeout=30) as driver:
                
                for kw in self.keywords:
                    print(f"   g Search: '{kw}'...")
                    try:
                        url = f"https://www.google.com/search?q={kw}&hl=ko&num=30" 
                        driver.get(url)
                        time.sleep(random.uniform(2, 4))
                        
                        try:
                            WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.ID, "search")))
                        except Exception: 
                            pass # Start check failed, but soup might still work
                        
                        soup = BeautifulSoup(driver.page_source, 'html.parser')
                        results = soup.select("div.g") 
                        
                        rank = -1
                        found = False
                        current_rank = 1
                        
                        for res in results:
                            text = res.get_text()
                            if "광고" in text[:10] or not text.strip(): continue
                            
                            if self.target_name in text:
                                rank = current_rank
                                found = True
                                print(f"      ✅ Found at Rank #{rank}")
                                break
                            
                            if len(text) > 30: current_rank += 1
                        
                        status_msg = "Not Found"
                        if found:
                            status_msg = f"#{rank}"
                        else:
                            print("      ⚠️ Not found in top 30.")
                            if "비정상적인 트래픽" in soup.text or "CAPTCHA" in soup.text:
                                 print("      ❌ Google CAPTCHA Detected!")
                                 status_msg = "Blocked (CAPTCHA)"
                                 rank = -999
                            else:
                                 rank = 0
                        
                        summary_report.append({"kw": kw, "status": status_msg})
                        
                        if rank != -999:
                             self.db.insert_rank(f"{kw} (Google)", rank, "규림한의원")
                             
                        time.sleep(random.uniform(3, 6))
                        
                    except Exception as e:
                        logger.error(f"Error processing keyword '{kw}': {e}", exc_info=True)
                        summary_report.append({"kw": kw, "status": "Error"})
                        
        except Exception as e:
            logger.error(f"   ❌ Driver Error: {e}")
        finally:
            # Driver closed by context manager
            
            # [NEW] Print Summary for Dashboard
            print("\n" + "="*30)
            print("📊 [Google Ranking Report]")
            print("| Keyword | Rank | Status |")
            print("| :--- | :--- | :--- |")
            for item in summary_report:
                 print(f"| {item['kw']} | {item['status']} | {item.get('status','-')} |") 
            print("="*30 + "\n") 

    # End of class
    pass


if __name__ == "__main__":
    # Check args for headed mode
    is_headless = True
    if "--headed" in sys.argv:
        is_headless = False
        
    scraper = GoogleRanker(headless=is_headless)
    scraper.run()
