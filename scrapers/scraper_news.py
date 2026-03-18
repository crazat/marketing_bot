import sys
import os
import time
import requests
import xml.etree.ElementTree as ET
from datetime import datetime

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

class NewsScraper:
    def __init__(self):
        self.db = DatabaseManager()
        if len(sys.argv) > 1:
            input_str = " ".join(sys.argv[1:])
            self.keywords = [k.strip() for k in input_str.split(',')]
        else:
            # v4.0 All-in-One Radar Keywords
            self.keywords = [
                # 1. Start & Event (Discovery)
                "청주 오픈", "청주 개최", "청주 축제", "청주 박람회", "청주 팝업", 
                "청주 입주", "청주 분양", "청주 사전점검",
                
                # 2. Key Clinical (Diet/Beauty)
                "위고비", "삭센다 품귀", "제로 슈거", "혈당 스파이크", "웨딩 다이어트",
                
                # 3. Life Cycle & Target
                "청주 수험생", "청주 난임", "청주 산후조리", "청주 직장인 검진",
                
                # 4. Risk & Policy
                "실손보험 지급 거절", "한의원 행정처분", "교통사고 합의금", "자동차보험 개정",
                
                # 5. Season & Disease (Dynamic)
                "청주 독감", "청주 수족구", "청주 식중독", "청주 미세먼지"
            ]

        # Negative Keywords (Filter out noise)
        self.negative_keywords = ["부고", "모집", "채용", "주식", "코스피", "동정"]
        
    def run(self):
        print(f"[{datetime.now()}] ⚡ Starting News Scraper (RSS Mode)...")
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            for kw in self.keywords:
                print(f"   📰 Searching RSS: '{kw}'...")
                # Google News RSS (Korean)
                url = f"https://news.google.com/rss/search?q={kw}&hl=ko&gl=KR&ceid=KR:ko"
                
                response = requests.get(url, headers=headers, timeout=10)
                
                if response.status_code == 200:
                    root = ET.fromstring(response.content)
                    
                    # Parse Items
                    channel = root.find("channel")
                    items = channel.findall("item") if channel else []
                    
                    count = 0
                    for item in items[:5]: # Top 5
                        try:
                            title = item.find("title").text
                            link = item.find("link").text
                            pubDate = item.find("pubDate").text
                            description = item.find("description").text # Often contains HTML
                            
                            # Clean description (remove html tags if needed, or keep simple)
                            # We'll just use title mostly.
                            
                            # v4.0 Negative Filtering
                            full_text = (title + " " + description).lower()
                            if any(neg in full_text for neg in self.negative_keywords):
                                print(f"      🗑️ Skipped (Negative Filter): {title[:20]}...")
                                continue
                            
                            # Save
                            self.db.insert_mention({
                                "target_name": "News",
                                "keyword": kw,
                                "source": "google_news_rss",
                                "title": title,
                                "content": title, # Use title as content for now
                                "url": link,
                                "date_posted": datetime.now().strftime("%Y-%m-%d"), # Or parse pubDate
                                "image_url": "" 
                            })
                            count += 1
                            print(f"      ⚡ Found: {title[:30]}...")
                        except Exception: continue
                        
                    if count == 0:
                        print("      ⚠️ No news found in RSS.")
                else:
                    print(f"      ❌ HTTP Error: {response.status_code}")
                    
                time.sleep(1)
                
        except Exception as e:
            print(f"   ❌ Error: {e}")

if __name__ == "__main__":
    scraper = NewsScraper()
    scraper.run()
