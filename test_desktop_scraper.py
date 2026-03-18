#!/usr/bin/env python3
"""
데스크탑 스크래퍼 테스트 스크립트
수정된 iframe 로직을 테스트합니다.
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

def test_desktop_parsing(keyword="청주 한의원", target_name="규림한의원"):
    """데스크탑 파싱 로직 테스트"""

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

        url = f"https://map.naver.com/p/search/{keyword}"
        print(f"🔍 URL 접속 중: {url}")
        driver.get(url)

        print(f"⏳ 페이지 로딩 대기 중...")
        time.sleep(10)

        # === 수정된 파싱 로직 테스트 ===
        place_items = []

        try:
            # searchIframe으로 전환
            iframe = driver.find_element(By.ID, "searchIframe")
            driver.switch_to.frame(iframe)
            print(f"✅ searchIframe으로 전환 완료")

            # 스크롤 컨테이너 찾기
            try:
                scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
                print(f"✅ 스크롤 컨테이너 발견: #_pcmap_list_scroll_container")
            except:
                try:
                    scroll_container = driver.find_element(By.CSS_SELECTOR, ".Ryr1F")
                    print(f"✅ 스크롤 컨테이너 발견: .Ryr1F")
                except:
                    scroll_container = None
                    print(f"⚠️ 스크롤 컨테이너 없음")

            if scroll_container:
                # 무한 스크롤로 100개까지 로드 (또는 더 이상 없을 때까지)
                print(f"📜 스크롤 컨테이너 스크롤 실행 중 (최대 100개)...")
                prev_count = 0
                max_scrolls = 30  # 증가: 30회 스크롤
                no_change_count = 0
                target_count = 100  # 목표: 100개

                for scroll_attempt in range(max_scrolls):
                    # 현재 항목 개수 확인
                    current_elements = driver.find_elements(By.CSS_SELECTOR, "li.DWs4Q, li[class*='DWs4Q']")
                    current_count = len(current_elements)

                    print(f"   스크롤 {scroll_attempt + 1}회: {current_count}개 항목")

                    # 100개 도달 시 종료
                    if current_count >= target_count:
                        print(f"   ✅ 목표 개수 도달 (총 {current_count}개)")
                        break

                    # 스크롤 컨테이너 스크롤
                    driver.execute_script("arguments[0].scrollTop = arguments[0].scrollHeight;", scroll_container)
                    time.sleep(2)  # 대기 시간 증가

                    # 새로운 항목이 로드되었는지 확인
                    if current_count == prev_count:
                        no_change_count += 1
                        if no_change_count >= 5:  # 5회 연속 변화 없으면 종료
                            print(f"   ✅ 모든 결과 로드 완료 (총 {current_count}개)")
                            break
                    else:
                        no_change_count = 0

                    prev_count = current_count

                print(f"✅ 스크롤 완료")
            else:
                print(f"⚠️ 기본 스크롤 사용")

            # Strategy 1: li.DWs4Q 셀렉터
            elements = driver.find_elements(By.CSS_SELECTOR, "li.DWs4Q, li[class*='DWs4Q']")
            if elements:
                place_items = elements
                print(f"✅ [Strategy 1] {len(elements)}개 항목 발견 (li.DWs4Q)")

            # Strategy 2: fallback
            if not place_items:
                all_li = driver.find_elements(By.TAG_NAME, "li")
                for li in all_li:
                    if li.find_elements(By.CSS_SELECTOR, "span.q2LdB, a.place_bluelink"):
                        place_items.append(li)
                if place_items:
                    print(f"✅ [Strategy 2] {len(place_items)}개 항목 발견 (fallback)")

            # 검색 결과 출력
            print(f"\n📍 검색 결과 ({len(place_items)}개):")
            target_rank = None
            gyulim_found = []

            for idx, item in enumerate(place_items, 1):
                try:
                    # 장소명 추출
                    name_elem = item.find_element(By.CSS_SELECTOR, "span.q2LdB")
                    name = name_elem.text.strip()

                    # "규림" 포함 여부 확인
                    if "규림" in name:
                        gyulim_found.append((idx, name))

                    # 타겟 발견 확인
                    if target_name and target_name in name:
                        target_rank = idx
                        print(f"   {idx}. {name} ⭐ [TARGET FOUND!]")
                    else:
                        print(f"   {idx}. {name}")

                except Exception as e:
                    print(f"   {idx}. [이름 추출 실패: {e}]")

            # "규림" 검색 결과
            if gyulim_found:
                print(f"\n🔍 '규림' 포함 업체:")
                for rank, name in gyulim_found:
                    print(f"   {rank}위: {name}")

            # 원래 프레임으로 복귀
            driver.switch_to.default_content()
            print(f"✅ 기본 프레임으로 복귀")

            # 결과 요약
            print(f"\n{'='*60}")
            if target_rank:
                print(f"🎯 결과: '{target_name}' 순위 {target_rank}위 발견!")
                print(f"   status: found")
                print(f"   rank: {target_rank}")
            else:
                print(f"❌ 결과: '{target_name}' 검색 결과 100위 내 없음")
                print(f"   status: not_in_results")
            print(f"{'='*60}")

        except Exception as iframe_err:
            print(f"❌ iframe 처리 오류: {iframe_err}")
            import traceback
            traceback.print_exc()
            driver.switch_to.default_content()

    except Exception as e:
        print(f"❌ 오류 발생: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            print(f"\n🔚 드라이버 종료")

if __name__ == "__main__":
    # 테스트 실행
    test_desktop_parsing(keyword="청주 한의원", target_name="규림한의원")
