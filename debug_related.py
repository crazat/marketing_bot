from retry_helper import SafeSeleniumDriver
from selenium.webdriver.common.by import By
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Target: A keyword that definitely has related keywords
target_url = "https://search.naver.com/search.naver?query=청주+다이어트"

print(f"🕵️ Debugging Related Keywords for: {target_url}")

with SafeSeleniumDriver(mobile=False, headless=True) as driver:
    driver.get(target_url)
    time.sleep(2)
    
    print("\n--- Searching for '연관검색어' section ---")
    try:
        # Check standard containers
        pass
    except: pass
    
    # Dump all elements that look like related keyword chips
    # Typically they are in a list or div with class 'related'
    
    print("\n--- Scanning candidate elements ---")
    # New Naver Design often uses logic like:
    # <div class="related_srch"> ... </div>
    # or just look for the text "연관검색어" and traverse down
    
    # Method 1: Find Header "연관검색어"
    try:
        headers = driver.find_elements(By.XPATH, "//*[contains(text(), '연관검색어')]")
        for h in headers:
            print(f"Found Header: Tag={h.tag_name}, Class={h.get_attribute('class')}")
            # Try to find parent's siblings
            try:
                parent = h.find_element(By.XPATH, "./..|./../..")
                print(f"  Parent Cluster: {parent.tag_name} class='{parent.get_attribute('class')}'")
                print(f"  Snippet: {parent.text[:100]}...")
            except: pass
    except: pass

    # Method 2: Scan common classes
    classes = ["related_srch", "lst_related_srch", "api_related_search", "keyword_challenge", "plus_b"]
    for c in classes:
        els = driver.find_elements(By.CLASS_NAME, c)
        if els:
            print(f"✅ Found Class '{c}': {len(els)} elements")
            for e in els:
                print(f"   Text: {e.text[:50]}...")
