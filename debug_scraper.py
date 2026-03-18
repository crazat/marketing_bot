#!/usr/bin/env python3
"""
디버그용 HTML 저장 스크립트
DB 접근 없이 네이버 플레이스 페이지의 HTML만 저장합니다.
"""
import os
import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

def save_naver_place_html(keyword="청주 한의원"):
    """네이버 플레이스 검색 결과 HTML 저장"""

    # Chrome 옵션 설정
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = None
    try:
        print(f"🌐 Chrome 드라이버 시작 중...")
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

        # 데스크탑 URL
        url = f"https://map.naver.com/p/search/{keyword}"
        print(f"🔍 URL 접속 중: {url}")
        driver.get(url)

        # 페이지 로딩 대기 (10초)
        print(f"⏳ 페이지 로딩 대기 중...")
        time.sleep(10)

        # 스크롤 (동적 로딩 유도)
        print(f"📜 스크롤 실행 중...")
        for i in range(3):
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)

        # 디렉토리 생성
        os.makedirs("debug_screenshots", exist_ok=True)

        # 스크린샷 저장
        screenshot_path = f"debug_screenshots/{keyword.replace(' ', '_')}_desktop.png"
        driver.save_screenshot(screenshot_path)
        print(f"📸 스크린샷 저장: {screenshot_path}")

        # HTML 저장
        html_path = f"debug_screenshots/{keyword.replace(' ', '_')}_desktop.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"📄 HTML 저장: {html_path}")

        # iframe 확인
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        print(f"\n🔍 iframe 개수: {len(iframes)}")

        for idx, iframe in enumerate(iframes):
            try:
                iframe_id = iframe.get_attribute("id")
                iframe_src = iframe.get_attribute("src")
                print(f"   iframe[{idx}]: id='{iframe_id}', src='{iframe_src[:50] if iframe_src else 'None'}...'")

                # searchIframe인 경우 내부 HTML도 저장
                if iframe_id == "searchIframe" or (iframe_src and "search" in str(iframe_src)):
                    print(f"   → searchIframe 발견! 내부 HTML 저장 중...")
                    driver.switch_to.frame(iframe)

                    iframe_html_path = f"debug_screenshots/{keyword.replace(' ', '_')}_iframe.html"
                    with open(iframe_html_path, 'w', encoding='utf-8') as f:
                        f.write(driver.page_source)
                    print(f"   📄 iframe HTML 저장: {iframe_html_path}")

                    driver.switch_to.default_content()
            except Exception as e:
                print(f"   ⚠️ iframe 처리 오류: {e}")
                driver.switch_to.default_content()

        print(f"\n✅ 완료!")

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            print(f"🔚 드라이버 종료")

if __name__ == "__main__":
    save_naver_place_html()
