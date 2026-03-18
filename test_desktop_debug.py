#!/usr/bin/env python3
"""
데스크탑 스크래핑 디버그 버전
"""
import sys
import os
import time

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import StaleElementReferenceException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

KEYWORD = "청주 다이어트 한약"
TARGET_NAME = "규림한의원"

print(f"\n{'='*70}")
print(f"🔍 키워드: {KEYWORD}")
print(f"🎯 타겟: {TARGET_NAME}")
print(f"{'='*70}\n")

# Chrome 옵션 (headless 끄기 - 직접 확인)
chrome_options = Options()
# chrome_options.add_argument("--headless")  # 주석 처리 - 브라우저 보이게
chrome_options.add_argument("--no-sandbox")
chrome_options.add_argument("--disable-dev-shm-usage")
chrome_options.add_argument("--window-size=1920,1080")

driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
wait = WebDriverWait(driver, 30)

try:
    url = f"https://map.naver.com/p/search/{KEYWORD}"
    print(f"📡 접속 중: {url}")
    driver.get(url)
    time.sleep(5)

    # iframe 전환
    print(f"🔄 iframe 전환...")
    iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
    driver.switch_to.frame(iframe)
    print(f"   ✅ iframe 전환 완료")

    # 스크롤 컨테이너 찾기
    scroll_container = None
    try:
        scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
        print(f"   ✅ 스크롤 컨테이너 발견")
    except:
        try:
            scroll_container = driver.find_element(By.CSS_SELECTOR, ".Ryr1F")
            print(f"   ✅ 스크롤 컨테이너 발견 (클래스)")
        except:
            # 다른 방법 시도
            try:
                scroll_container = driver.find_element(By.CSS_SELECTOR, "div[class*='scroll']")
                print(f"   ✅ 스크롤 컨테이너 발견 (scroll 클래스)")
            except:
                print(f"   ⚠️ 스크롤 컨테이너 없음")

    # 스크롤 전 항목 수 확인
    all_li_before = driver.find_elements(By.TAG_NAME, "li")
    print(f"\n📋 스크롤 전 li 개수: {len(all_li_before)}")

    # 스크롤
    print(f"\n📜 스크롤 시작...")
    if scroll_container:
        for i in range(10):
            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
            time.sleep(0.5)
            current_li = len(driver.find_elements(By.TAG_NAME, "li"))
            print(f"   스크롤 {i+1}: li 개수 = {current_li}")
    else:
        # window 스크롤 시도
        for i in range(10):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.5)
            current_li = len(driver.find_elements(By.TAG_NAME, "li"))
            print(f"   window 스크롤 {i+1}: li 개수 = {current_li}")

    # 스크롤 후 항목 수 확인
    all_li_after = driver.find_elements(By.TAG_NAME, "li")
    print(f"\n📋 스크롤 후 li 개수: {len(all_li_after)}")

    # 모든 li 항목에서 텍스트 추출
    print(f"\n📋 모든 li 항목 텍스트:")
    for i, li in enumerate(all_li_after[:30]):  # 최대 30개
        try:
            text = li.text[:100].replace('\n', ' ') if li.text else "[텍스트 없음]"

            # img[alt] 확인
            imgs = li.find_elements(By.CSS_SELECTOR, "img[alt]")
            alt_text = ""
            if imgs:
                alt_text = imgs[0].get_attribute("alt") or ""

            print(f"  {i+1}. alt=\"{alt_text}\" | text: {text[:60]}...")

            # 규림 포함 여부
            if "규림" in text or "규림" in alt_text:
                print(f"      ⭐ 규림 발견!")
        except Exception as e:
            print(f"  {i+1}. [에러: {e}]")

    # 규림 검색
    print(f"\n🔍 '규림' 텍스트 검색...")
    page_source = driver.page_source
    if "규림" in page_source:
        print(f"   ✅ 페이지 소스에 '규림' 있음!")
        # 위치 찾기
        idx = page_source.find("규림")
        context = page_source[max(0, idx-50):idx+100]
        print(f"   컨텍스트: ...{context}...")
    else:
        print(f"   ❌ 페이지 소스에 '규림' 없음")

    input("\n⏸️ 브라우저 확인 후 Enter 키를 누르세요...")

except Exception as e:
    print(f"\n❌ 에러: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()

finally:
    driver.quit()
    print(f"\n🔚 종료")
