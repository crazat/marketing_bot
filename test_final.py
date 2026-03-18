#!/usr/bin/env python3
"""최종 테스트 - 규림한의원 청주점 찾기"""
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

chrome_options = Options()
chrome_options.add_argument("--headless")
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")
chrome_options.add_argument("--disable-blink-features=AutomationControlled")
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = None

try:
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)

    url = "https://map.naver.com/p/search/청주 한의원"
    driver.get(url)

    # iframe 명시적 대기
    iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
    driver.switch_to.frame(iframe)

    # 스크롤 컨테이너 대기
    scroll_container = wait.until(EC.presence_of_element_located((By.ID, "_pcmap_list_scroll_container")))

    # 스크롤하여 모든 항목 로드
    for _ in range(5):
        driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
        time.sleep(2)

    # 먼저 페이지 전체 텍스트에서 규림 검색
    body = driver.find_element(By.TAG_NAME, "body")
    full_text = body.get_attribute("textContent") or body.text

    print(f"페이지 전체 텍스트에 '규림' 포함: {'✅ 예' if '규림' in full_text else '❌ 아니오'}\n")

    if "규림" in full_text:
        idx = full_text.find("규림")
        context = full_text[max(0, idx-100):min(len(full_text), idx+150)]
        print(f"규림 주변 텍스트:\n{context}\n")

    # XPath로 "규림"을 포함하는 모든 요소 찾기
    gyulim_elements = driver.find_elements(By.XPATH, "//*[contains(text(), '규림')]")
    print(f"'규림' 포함 요소 개수: {len(gyulim_elements)}\n")

    for i, elem in enumerate(gyulim_elements[:5], 1):
        print(f"{i}. 태그: <{elem.tag_name}>, 클래스: {elem.get_attribute('class')}")
        print(f"   텍스트: {elem.text[:200]}\n")

    # 모든 li 항목 수집
    all_li = driver.find_elements(By.TAG_NAME, "li")

    place_items = []
    gyulim_rank = None

    for idx, li in enumerate(all_li, 1):
        # 여러 방법으로 텍스트 추출
        text = ""

        try:
            text = li.text or ""
        except:
            pass

        if not text:
            try:
                text = li.get_attribute("textContent") or ""
            except:
                pass

        if not text:
            try:
                text = li.get_attribute("innerText") or ""
            except:
                pass

        # 장소명이 있는 항목만
        if len(text) > 10:
            place_items.append((idx, text.strip()[:100]))

            # 규림 검색
            if "규림" in text:
                gyulim_rank = len(place_items)
                print(f"✅ 발견! 순위 {gyulim_rank}: {text.strip()[:150]}")

    print(f"\n총 수집: {len(place_items)}개")

    if gyulim_rank:
        print(f"\n🎯 성공! '규림한의원 청주점' {gyulim_rank}위에서 발견!")
        print(f"\n주변 항목:")
        for rank, text in place_items[max(0, gyulim_rank-3):min(len(place_items), gyulim_rank+3)]:
            marker = "👉" if rank == gyulim_rank else "  "
            print(f"{marker} {rank}. {text}")
    else:
        print(f"\n❌ '규림' 미발견. 상위 30개:")
        for rank, text in place_items[:30]:
            print(f"  {rank}. {text}")

finally:
    if driver:
        driver.quit()
