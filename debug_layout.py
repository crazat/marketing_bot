from retry_helper import SafeSeleniumDriver
from selenium.webdriver.common.by import By
import time
import sys

sys.stdout.reconfigure(encoding='utf-8')

# Debug Target: Mobile Blog Search for a popular keyword
target_url = "https://m.search.naver.com/search.naver?query=청주+다이어트&where=m_blog"

print(f"🕵️ Debugging Layout for (Mobile): {target_url}")

with SafeSeleniumDriver(mobile=True, headless=True) as driver:
    driver.get(target_url)
    time.sleep(2)
    
    print("\n--- Page Title ---")
    print(driver.title)
    
    print("\n--- Searching for '건' (Count) ---")
    # Find any element with "건" text
    try:
        els = driver.find_elements(By.XPATH, "//*[contains(text(), '건')]")
        print(f"Found {len(els)} elements with '건':")
        for i, el in enumerate(els[:10]):
            try:
                print(f"[{i}] Tag: {el.tag_name} | Class: {el.get_attribute('class')} | Text: {el.text.strip()}")
                # Print parent too
                parent = el.find_element(By.XPATH, "..")
                print(f"    Parent: {parent.tag_name} | Class: {parent.get_attribute('class')}")
            except: pass
    except ActionChains: pass

    print("\n--- Searching for '블로그' or 'VIEW' (Tabs) ---")
    vals = ["블로그", "VIEW"]
    for v in vals:
        try:
            els = driver.find_elements(By.XPATH, f"//*[contains(text(), '{v}')]")
            print(f"Elements with '{v}':")
            for el in els:
                txt = el.text.strip()
                if len(txt) < 30: # Only short labels
                    print(f"  Tag: {el.tag_name} | Class: {el.get_attribute('class')} | Text: '{txt}'")
        except: pass
        
    print("\n--- Checking '.option_area' (Tab Bar) ---")
    try:
        tabs = driver.find_elements(By.CSS_SELECTOR, ".option_area a, .api_tab_option a")
        for t in tabs:
            print(f"  Tab: {t.text}")
    except: pass

    print("\n--- Fallback Check 'li.bx' ---")
    items = driver.find_elements(By.CSS_SELECTOR, "li.bx")
    print(f"Found {len(items)} items using 'li.bx'")
