#!/usr/bin/env python3
"""모든 검색 결과 항목 확인 (광고 포함)"""
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

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

try:
    url = "https://map.naver.com/p/search/청주 한의원"
    print(f"🔍 URL: {url}\n")
    driver.get(url)

    # 충분한 대기 시간
    print("⏳ 페이지 로딩 대기 중 (15초)...")
    time.sleep(15)

    # iframe으로 전환 (재시도 포함)
    for attempt in range(5):
        try:
            iframe = driver.find_element(By.ID, "searchIframe")
            driver.switch_to.frame(iframe)
            print("✅ iframe 전환\n")
            break
        except Exception:
            print(f"   iframe 찾기 시도 {attempt + 1}/5...")
            time.sleep(3)

    # 스크롤 컨테이너 스크롤
    scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
    for i in range(10):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
        time.sleep(2)

    # 다양한 셀렉터로 항목 찾기
    selectors = [
        ("li.DWs4Q", "일반 검색 결과"),
        ("li[class*='place']", "place 클래스"),
        ("li[class*='item']", "item 클래스"),
        ("div[class*='ad']", "광고 div"),
        ("li", "모든 li"),
        ("a[href*='place']", "place 링크"),
    ]

    all_names = []

    for selector, desc in selectors:
        elements = driver.find_elements(By.CSS_SELECTOR, selector)
        print(f"=== {desc} ({selector}): {len(elements)}개 ===")

        if selector == "모든 li":
            # 너무 많으면 스킵
            continue

        for idx, elem in enumerate(elements[:5], 1):
            try:
                # 텍스트 추출
                text = elem.text.strip()[:100]  # 처음 100자만

                # "규림" 검색
                if "규림" in text:
                    print(f"   ✅ {idx}. [규림 발견!] {text}")
                    all_names.append(text)
                elif text:
                    print(f"   {idx}. {text}")
            except Exception:
                pass
        print()

    # 모든 텍스트에서 "규림" 검색
    page_source = driver.page_source
    if "규림" in page_source:
        print("\n🔍 페이지 소스에 '규림' 있음!")
        # 규림 주변 텍스트 추출
        import re
        matches = re.findall(r'.{0,50}규림.{0,50}', page_source)
        for i, match in enumerate(matches[:3], 1):
            print(f"   {i}. {match}")
    else:
        print("\n❌ 페이지 소스에 '규림' 없음")

finally:
    driver.quit()
