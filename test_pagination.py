#!/usr/bin/env python3
"""페이지네이션 테스트"""
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
chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

driver = None

try:
    print("🌐 Chrome 드라이버 시작 중...")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

    url = "https://map.naver.com/p/search/청주 한의원"
    print(f"🔍 URL 접속: {url}")
    driver.get(url)

    print("⏳ 페이지 로딩 대기 중 (15초)...")
    time.sleep(15)

    # iframe으로 전환 (재시도)
    iframe = None
    for attempt in range(5):
        try:
            iframe = driver.find_element(By.ID, "searchIframe")
            driver.switch_to.frame(iframe)
            print("✅ iframe 전환 완료\n")
            break
        except Exception as e:
            if attempt < 4:
                print(f"   iframe 찾기 시도 {attempt + 1}/5...")
                time.sleep(3)
            else:
                print(f"❌ iframe 찾기 실패: {e}")
                raise

    # 스크롤 컨테이너 찾기
    scroll_container = None
    try:
        scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
        print("✅ 스크롤 컨테이너 발견\n")
    except:
        print("⚠️ 스크롤 컨테이너 없음\n")

    # 페이지네이션으로 여러 페이지 수집
    all_items = []
    max_pages = 5
    gyulim_found = []

    for page_num in range(1, max_pages + 1):
        print(f"📄 === 페이지 {page_num} ===")

        # 스크롤하여 현재 페이지의 모든 항목 로드
        if scroll_container:
            for _ in range(3):
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
                time.sleep(1)

        # 현재 페이지 항목 수집
        current_items = driver.find_elements(By.CSS_SELECTOR, "li.DWs4Q, li[class*='DWs4Q']")
        print(f"   현재 페이지 항목: {len(current_items)}개")

        # 항목 파싱 및 규림 검색
        for idx, item in enumerate(current_items, 1):
            try:
                name_elem = item.find_element(By.CSS_SELECTOR, "span.q2LdB")
                name = name_elem.text.strip()

                # 전체 리스트에 추가 (중복 체크)
                item_key = f"{page_num}-{name}"
                if not any(item_key in str(x) for x in all_items):
                    all_items.append((len(all_items) + 1, name, page_num))

                # 규림 검색
                if "규림" in name:
                    rank = len(all_items)
                    gyulim_found.append((rank, name, page_num))
                    print(f"   ✅ {idx}번째: {name} [규림 발견!]")

            except:
                pass

        print(f"   누적 항목: {len(all_items)}개\n")

        # 규림을 찾았으면 조기 종료
        if gyulim_found:
            print(f"🎯 규림 발견! 탐색 종료\n")
            break

        # 다음 페이지 버튼 찾기
        next_button = None
        try:
            # 여러 셀렉터 시도
            selectors = [
                "a.eUTV2",  # 다음 버튼
                "button.eUTV2",
                "a[aria-label='다음 페이지']",
                "button[aria-label='다음 페이지']",
                ".Nqxtj a",  # 페이지네이션 컨테이너 내 링크
            ]

            for selector in selectors:
                try:
                    buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                    for btn in buttons:
                        if btn.is_displayed() and btn.is_enabled():
                            # "다음" 또는 숫자가 포함된 버튼
                            btn_text = btn.text
                            if "다음" in btn_text or str(page_num + 1) in btn_text:
                                next_button = btn
                                break
                    if next_button:
                        break
                except:
                    continue

            if next_button:
                print(f"   ➡️ 다음 페이지로 이동 중...")
                driver.execute_script("arguments[0].click();", next_button)
                time.sleep(3)  # 페이지 로드 대기
            else:
                print(f"   ℹ️ 다음 페이지 버튼 없음. 마지막 페이지입니다.")
                break

        except Exception as page_err:
            print(f"   ⚠️ 페이지네이션 오류: {page_err}")
            break

    # 결과 출력
    print(f"\n{'='*70}")
    print(f"📊 전체 수집 결과")
    print(f"{'='*70}")
    print(f"총 항목 수: {len(all_items)}개")
    print(f"탐색 페이지: {page_num}페이지")

    if gyulim_found:
        print(f"\n✅ '규림' 발견:")
        for rank, name, page in gyulim_found:
            print(f"   {rank}위: {name} (페이지 {page})")
    else:
        print(f"\n❌ '규림' 포함 업체 없음")
        print(f"\n전체 {len(all_items)}개 항목:")
        for rank, name, page in all_items:
            print(f"   {rank}. {name} (페이지 {page})")

    driver.switch_to.default_content()

except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
    import traceback
    traceback.print_exc()

finally:
    if driver:
        driver.quit()
        print(f"\n🔚 드라이버 종료")
