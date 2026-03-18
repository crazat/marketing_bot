#!/usr/bin/env python3
"""규림 찾기 - 모든 요소 검색"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    url = "https://map.naver.com/p/search/청주 한의원"
    print(f"🔍 URL: {url}\n")
    driver.get(url)
    time.sleep(15)

    iframe = driver.find_element(By.ID, "searchIframe")
    driver.switch_to.frame(iframe)
    print("✅ iframe 전환\n")

    # 스크롤
    scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
    for _ in range(5):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
        time.sleep(1.5)

    # 페이지 전체 텍스트에서 "규림" 검색
    page_text = driver.find_element(By.TAG_NAME, "body").text

    if "규림" in page_text:
        print("✅ 페이지에 '규림' 텍스트 발견!\n")

        # 규림 주변 텍스트 추출
        lines = page_text.split('\n')
        for i, line in enumerate(lines):
            if "규림" in line:
                print(f"라인 {i}: {line}")
                # 앞뒤 5줄도 출력
                print("  [컨텍스트]")
                for j in range(max(0, i-5), min(len(lines), i+6)):
                    print(f"    {j}: {lines[j]}")
                print()
    else:
        print("❌ 페이지에 '규림' 텍스트 없음\n")

    # 모든 li 요소의 텍스트 추출
    print("=== 모든 리스트 항목 텍스트 ===")
    all_li = driver.find_elements(By.TAG_NAME, "li")

    for idx, li in enumerate(all_li[:100], 1):  # 처음 100개만
        text = li.text.strip()
        if text and len(text) > 5:
            if "규림" in text:
                print(f"✅ {idx}. [규림 발견!] {text[:200]}")
            elif "삼성" in text or "바른" in text:
                print(f"   {idx}. {text[:200]}")

finally:
    driver.quit()
