import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Add parent directory for DB access
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

class KarrotScraper:
    def __init__(self):
        self.db = DatabaseManager()
        # Location: Cheongju
        # Accept keywords from CLI args, else default
        if len(sys.argv) > 1:
            input_str = " ".join(sys.argv[1:])
            self.keywords = [k.strip() for k in input_str.split(',')]
        else:
            self.keywords = ["청주 다이어트", "청주 한의원", "청주 교통사고", "청주 보약"]
        
    def run(self):
        print(f"[{datetime.now()}] Starting Karrot (Danggeun) Scraper...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        
        for kw in self.keywords:
            print(f"🥕 Searching for '{kw}'...")
            url = f"https://www.daangn.com/search/{kw}"
            
            try:
                res = requests.get(url, headers=headers, timeout=10)
                soup = BeautifulSoup(res.text, 'html.parser')
                
                # Karrot search results structure
                articles = soup.select("article.flea-market-article")
                
                count = 0
                for art in articles:
                    try:
                        title_el = art.select_one(".article-title")
                        desc_el = art.select_one(".article-content")
                        link_el = art.select_one("a.flea-market-article-link")
                        
                        if not title_el: continue
                        
                        title = title_el.get_text(strip=True)
                        content = desc_el.get_text(strip=True) if desc_el else ""
                        link = "https://www.daangn.com" + link_el['href'] if link_el else ""
                        
                        # Filter used items vs questions? 
                        # Karrot web search mixes them. We accept all for now as 'mentions'.
                        
                        self.db.insert_mention({
                            "target_name": "Karrot",
                            "keyword": kw,
                            "source": "karrot",
                            "title": title,
                            "content": content,
                            "url": link,
                            "date_posted": datetime.now().strftime("%Y-%m-%d") # Karrot doesn't show exact date on list easily
                        })
                        count += 1
                    except Exception: continue
                    
                print(f"   ✅ Found {count} items.")
                time.sleep(2)
                
            except Exception as e:
                print(f"   ❌ Error searching Karrot: {e}")

if __name__ == "__main__":
    scraper = KarrotScraper()
    scraper.run()
