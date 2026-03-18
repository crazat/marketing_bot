#!/usr/bin/env python3
"""Production 로직 테스트"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 30)

try:
    driver.get("https://map.naver.com/p/search/청주 한의원")

    iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
    driver.switch_to.frame(iframe)

    scroll_container = wait.until(EC.presence_of_element_located((By.ID, "_pcmap_list_scroll_container")))

    # 스크롤
    for _ in range(3):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
        time.sleep(1.5)

    # Strategy 1: DOM 파싱
    dom_items = driver.find_elements(By.CSS_SELECTOR, "li.DWs4Q, li[class*='DWs4Q']")
    print(f"DOM 파싱: {len(dom_items)}개")

    place_items = dom_items

    # Strategy 3: __APOLLO_STATE__ (fallback)
    if len(place_items) < 20:
        print("DOM 파싱 결과 부족 → __APOLLO_STATE__ 시도")

        apollo_state = driver.execute_script("return window.__APOLLO_STATE__ || null;")
        if apollo_state:
            json_items = []
            for key, value in apollo_state.items():
                if key.startswith("HospitalSummary:") and isinstance(value, dict):
                    name = value.get("name", "")
                    if name:
                        json_items.append(name)

            print(f"__APOLLO_STATE__: {len(json_items)}개")

            # 가상 요소 생성
            class ApolloItem:
                def __init__(self, name):
                    self._text = name
                @property
                def text(self):
                    return self._text
                def get_attribute(self, attr):
                    return self._text if attr in ["textContent", "innerText"] else ""

            place_items = [ApolloItem(name) for name in json_items]

    # 타겟 검색: 규림한의원
    target_name = "규림한의원"
    found_rank = None

    for idx, item in enumerate(place_items, 1):
        item_text = ""
        try:
            item_text = item.text or ""
        except:
            pass
        if not item_text:
            try:
                item_text = item.get_attribute("textContent") or ""
            except:
                pass

        if target_name in item_text:
            found_rank = idx
            print(f"\n🎯 성공! '{target_name}' {found_rank}위에서 발견!")
            print(f"   업체명: {item_text}")
            break

    if not found_rank:
        print(f"\n❌ '{target_name}' 미발견")
        print(f"\n상위 10개:")
        for idx, item in enumerate(place_items[:10], 1):
            text = item.text if hasattr(item, 'text') else str(item)
            print(f"  {idx}. {text[:100]}")

finally:
    driver.quit()
