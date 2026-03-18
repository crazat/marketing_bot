import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from webdriver_manager.chrome import ChromeDriverManager
import sys

# Force UTF-8
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def debug_selectors():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    # Test URL: Naver Cafe Search for "청주 한의원"
    url = "https://search.naver.com/search.naver?ssc=tab.cafe.all&query=%EC%B2%AD%EC%A3%BC+%ED%95%9C%EC%9D%98%EC%9B%90"
    print(f"Loading {url}...")
    
    try:
        driver.get(url)
        time.sleep(3)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Test 1: List Items
        items_bx = soup.select("li.bx")
        items_view = soup.select(".view_wrap")
        
        print(f"Found {len(items_bx)} items with 'li.bx'")
        print(f"Found {len(items_view)} items with '.view_wrap'")
        
        items = items_bx if items_bx else items_view
        
        if items:
            # Deep Inspection of First Valid Link
            target_link = None
            for i, item in enumerate(items[10:15]):
                print(f"\n--- Item {i+11} Summary ---")
                
                # Check Title & Link
                title_el = item.select_one(".title_link")
                if title_el:
                    print(f"  [Title]: {title_el.get_text().strip()}")
                    target_link = title_el['href']
                    print(f"  [Link]: {target_link}")
                    break # Stop at first valid item
            
            if target_link:
                print(f"\n>>> Navigating to Target Link: {target_link}")
                driver.get(target_link)
                time.sleep(3)
                
                # Check Frame
                try:
                    driver.switch_to.frame("cafe_main")
                    print("  [Frame]: Switched to 'cafe_main'")
                except:
                    print("  [Frame]: 'cafe_main' not found (might be full page)")
                
                # Inspect Body Selectors
                page_soup = BeautifulSoup(driver.page_source, 'html.parser')
                selectors = ['.se-main-container', '.ContentRenderer', '.article_viewer', '#tbody']
                
                print("\n>>> Testing Body Selectors:")
                matched = False
                for sel in selectors:
                    content = page_soup.select_one(sel)
                    if content:
                        print(f"  [MATCH] '{sel}': Found content ({len(content.get_text())} chars)")
                        # print(f"  [Preview]: {content.get_text(strip=True)[:100]}...")
                        matched = True
                    else:
                        print(f"  [FAIL] '{sel}': Not found")
                
                # Check Author/Date
                print("\n>>> Testing Meta Selectors:")
                nick = page_soup.select_one('.nickname') or page_soup.select_one('.nick_box')
                if nick:
                    print(f"  [Author]: {nick.get_text(strip=True)}")
                else:
                    print("  [Author]: Not Found")

                date_el = page_soup.select_one('.date') or page_soup.select_one('.article_info .date')
                if date_el:
                    print(f"  [Date]: {date_el.get_text(strip=True)}")
                else:
                    print("  [Date]: Not Found")

                if not matched:
                    print("\n>>> DUMPING BODY START (No selector matched) <<<")
                    print(page_soup.find('body').prettify()[:1000])
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    debug_selectors()
