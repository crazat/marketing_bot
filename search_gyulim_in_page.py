#!/usr/bin/env python3
"""페이지 전체에서 규림 검색"""
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
    for _ in range(5):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
        time.sleep(2)

    # 전체 body 텍스트
    body = driver.find_element(By.TAG_NAME, "body")
    full_text = body.get_attribute("textContent") or body.text

    if "규림" in full_text:
        print("✅ 페이지에 '규림' 존재!")

        # 규림 주변 텍스트 추출
        idx = full_text.find("규림")
        context = full_text[max(0, idx-200):min(len(full_text), idx+200)]
        print(f"\n주변 텍스트:\n{context}\n")

        # 규림을 포함하는 요소 찾기
        all_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '규림')]")
        print(f"'규림' 포함 요소: {len(all_elements)}개\n")

        for i, elem in enumerate(all_elements[:5], 1):
            print(f"{i}. 태그: {elem.tag_name}")
            print(f"   클래스: {elem.get_attribute('class')}")
            print(f"   텍스트: {elem.text[:200]}\n")

    else:
        print("❌ 페이지에 '규림' 없음")

        # 디버깅: 전체 텍스트 일부 출력
        print(f"\n페이지 텍스트 샘플 (처음 500자):\n{full_text[:500]}\n")

finally:
    driver.quit()
