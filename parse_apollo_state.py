#!/usr/bin/env python3
"""__APOLLO_STATE__ JSON 파싱으로 규림 찾기"""
import sys
import time
import json
import re
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

    # __APOLLO_STATE__ 추출
    script = driver.execute_script("""
        return window.__APOLLO_STATE__ || null;
    """)

    if script:
        print("✅ __APOLLO_STATE__ 발견!\n")

        # HospitalSummary 항목들 추출
        hospitals = []
        for key, value in script.items():
            if key.startswith("HospitalSummary:") and isinstance(value, dict):
                name = value.get("name", "")
                if name:
                    hospitals.append(name)

        print(f"총 {len(hospitals)}개 병원 발견\n")

        # 규림 검색
        gyulim_rank = None
        for idx, name in enumerate(hospitals, 1):
            if "규림" in name:
                gyulim_rank = idx
                print(f"🎯 발견! {idx}위: {name}")

        if gyulim_rank:
            print(f"\n✅ 성공! '규림한의원 청주점' {gyulim_rank}위에서 발견!\n")
            print(f"주변 항목:")
            for i in range(max(1, gyulim_rank-2), min(len(hospitals)+1, gyulim_rank+3)):
                marker = "👉" if i == gyulim_rank else "  "
                print(f"{marker} {i}. {hospitals[i-1]}")
        else:
            print(f"\n❌ '규림' 미발견. 상위 30개:")
            for i, name in enumerate(hospitals[:30], 1):
                print(f"  {i}. {name}")

    else:
        print("❌ __APOLLO_STATE__ 없음")

finally:
    driver.quit()
