"""
Debug Cafe Internal Search - Check actual HTML structure
"""
import time
import os
import sys
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def debug_cafe_internal_search():
    driver_path = r"C:\Users\craza\.wdm\drivers\chromedriver\win64\144.0.7559.60\chromedriver-win32\chromedriver.exe"
    
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(service=Service(driver_path), options=options)
    driver.set_page_load_timeout(60)
    
    # Test: Cafe Internal Search URL
    cafe_id = "cjcjmom"
    keyword = "다이어트"
    url = f"https://cafe.naver.com/{cafe_id}/ArticleSearchList.nhn?search.searchBy=0&search.query={keyword}"
    
    print(f"🔎 Loading: {url}")
    
    try:
        driver.get(url)
        time.sleep(4)
        
        print(f"📄 Page title: {driver.title}")
        print(f"📐 Page source length: {len(driver.page_source)}")
        
        # Check if we're on a login page or redirect
        if "로그인" in driver.page_source or "login" in driver.current_url.lower():
            print("⚠️ Redirected to login page!")
        
        # Try switching to iframe
        print("\n--- Trying iframes ---")
        iframes = driver.find_elements("tag name", "iframe")
        print(f"Found {len(iframes)} iframes")
        for i, iframe in enumerate(iframes):
            name = iframe.get_attribute("name") or iframe.get_attribute("id") or f"iframe_{i}"
            print(f"  [{i}] {name}")
        
        # Try cafe_main iframe
        try:
            driver.switch_to.frame("cafe_main")
            print("✅ Switched to 'cafe_main' iframe")
        except Exception as e:
            print(f"❌ Failed to switch to 'cafe_main': {e}")
        
        time.sleep(2)
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Try various selectors
        print("\n--- Testing Selectors ---")
        test_selectors = [
            'div.article-board tbody tr',
            'ul.article-movie-sub li',
            '.article_lst li',
            '.article-album-sub li',
            'tr[class*="article"]',
            'div.inner_list a',
            'a.article',
            '.content-list li',
            '.article-board',
            'table.article-board',
            '.article_wrap',
            'li.article-item',
            '.search_list li',
            '.group_list li'
        ]
        
        for sel in test_selectors:
            items = soup.select(sel)
            print(f"  '{sel}': {len(items)} items")
        
        # Also try finding any links that look like articles
        print("\n--- Checking all links ---")
        all_links = soup.find_all('a', href=True)
        article_links = [a for a in all_links if 'ArticleRead' in a.get('href', '') or '/articles/' in a.get('href', '')]
        print(f"Found {len(article_links)} article-like links")
        
        if article_links[:5]:
            print("\nSample article links:")
            for a in article_links[:5]:
                print(f"  - {a.get_text(strip=True)[:50]} -> {a['href'][:60]}")
        
        # Dump some HTML structure for analysis
        print("\n--- HTML Structure Sample ---")
        body = soup.find('body')
        if body:
            # Get first 2000 chars of body HTML for analysis
            body_html = str(body)[:3000]
            print(body_html)
        
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    debug_cafe_internal_search()
