#!/usr/bin/env python3
"""
데스크탑 스크래핑 테스트 (모바일 제외)
Usage: python test_desktop_only.py
"""
import sys
import os
import time

# Windows 인코딩 설정
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

# 설정
KEYWORDS = ["청주 다이어트 한약"]  # 테스트할 키워드
TARGET_NAME = "규림한의원"


def extract_place_name(item, skip_img_search=False):
    """업체명과 광고 여부 추출"""
    import re
    try:
        full_text = ""
        try:
            full_text = item.text or item.get_attribute("textContent") or ""
        except:
            pass

        is_ad = "광고" in full_text

        # 방법 1: img[alt] 속성
        if not skip_img_search:
            try:
                img = item.find_element(By.CSS_SELECTOR, "img[alt]")
                alt = img.get_attribute("alt")
                if alt and len(alt) >= 2 and "이미지" not in alt.lower():
                    return alt.strip(), is_ad
            except:
                pass

        # 방법 2: 텍스트에서 추출
        if full_text:
            # 패턴 1: 광고 항목 (한XXXXX + 업체명)
            match = re.search(r'한\d{5}\s*(.+?)(?:\s*(?:주말|야간|진료|휴일|신경|한의사|광고|365일|24시간|톡톡))', full_text)
            if match:
                return match.group(1).strip(), is_ad

            # 패턴 2: 이미지 수 + 업체명
            match = re.search(r'이미지\s*수?\s*\d+\s*(.+?)(?:한의원|병원|의원|치과|약국|한방병원|클리닉)', full_text)
            if match:
                name = match.group(1).strip()
                # 뒤에 카테고리 붙이기
                for cat in ["한의원", "병원", "의원", "치과", "약국", "한방병원", "클리닉"]:
                    if cat in full_text:
                        name += cat
                        break
                return name, is_ad

            # 패턴 3: 첫 줄에서 업체명 추출 (톡톡 또는 한의원/병원 앞까지)
            first_line = full_text.split('\n')[0] if '\n' in full_text else full_text
            match = re.search(r'^(.+?)(?:\s*톡톡|\s*한의원|\s*병원|\s*의원|\s*약국)', first_line)
            if match:
                name = match.group(1).strip()
                # 카테고리 붙이기
                for cat in ["한의원", "한방병원", "병원", "의원", "약국"]:
                    if cat in full_text[:100]:
                        name += " " + cat if not name.endswith(cat) else ""
                        break
                if len(name) >= 2:
                    return name.strip(), is_ad

        return full_text[:50] if full_text else "", is_ad
    except:
        return "", False


def test_desktop_scraping(keyword, target_name):
    """데스크탑 스크래핑 테스트"""

    print(f"\n{'='*70}")
    print(f"🔍 키워드: {keyword}")
    print(f"🎯 타겟: {target_name}")
    print(f"{'='*70}\n")

    # Chrome 옵션
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
    wait = WebDriverWait(driver, 30)

    try:
        # 네이버 지도 접속
        url = f"https://map.naver.com/p/search/{keyword}"
        print(f"📡 접속 중: {url}")
        driver.get(url)
        time.sleep(5)

        # iframe 전환
        print(f"🔄 iframe 전환 중...")
        iframe = wait.until(EC.presence_of_element_located((By.ID, "searchIframe")))
        driver.switch_to.frame(iframe)
        print(f"   ✅ iframe 전환 완료")

        # 스크롤 컨테이너 찾기 (다양한 방법 시도)
        scroll_container = None

        # 방법 1: ID로 찾기
        try:
            scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
            print(f"   ✅ 스크롤 컨테이너 발견 (ID: _pcmap_list_scroll_container)")
        except NoSuchElementException:
            pass

        # 방법 2: 클래스로 찾기
        if not scroll_container:
            try:
                scroll_container = driver.find_element(By.CSS_SELECTOR, ".Ryr1F")
                print(f"   ✅ 스크롤 컨테이너 발견 (클래스: Ryr1F)")
            except NoSuchElementException:
                pass

        # 방법 3: 검색 결과 리스트 컨테이너 직접 찾기
        if not scroll_container:
            try:
                # 스크롤 가능한 div 찾기 (overflow: auto/scroll)
                scroll_container = driver.find_element(By.CSS_SELECTOR, "#_list_scroll_container")
                print(f"   ✅ 스크롤 컨테이너 발견 (ID: _list_scroll_container)")
            except NoSuchElementException:
                pass

        # 방법 4: 결과 리스트의 부모 요소
        if not scroll_container:
            try:
                # ul.place_list 또는 다른 리스트 컨테이너
                result_list = driver.find_element(By.CSS_SELECTOR, "ul[data-nclicks-area-code]")
                scroll_container = result_list.find_element(By.XPATH, "..")
                print(f"   ✅ 스크롤 컨테이너 발견 (결과 리스트 부모)")
            except NoSuchElementException:
                pass

        if not scroll_container:
            print(f"   ⚠️ 스크롤 컨테이너 없음 - window 스크롤 사용")
            # 디버그: 어떤 요소들이 있는지 출력
            all_divs = driver.find_elements(By.CSS_SELECTOR, "div[id]")
            print(f"   📋 div[id] 요소들: {[d.get_attribute('id')[:30] for d in all_divs[:10]]}")

        # 스크롤하여 모든 항목 로드 (개선된 로직)
        print(f"\n📜 스크롤 중...")
        if scroll_container:
            prev_height = 0
            no_change_count = 0
            min_scrolls = 10  # 최소 10회 스크롤 강제

            for i in range(50):  # 최대 50회
                current_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)

                # 점진적 스크롤 (끝까지 한 번에가 아니라 조금씩)
                current_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + 800;", scroll_container)
                time.sleep(0.5)

                # 끝까지 도달했는지 확인
                new_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)

                # 현재 로드된 항목 수 확인
                li_count = len(driver.find_elements(By.TAG_NAME, "li"))

                if i < min_scrolls:
                    # 최소 스크롤 횟수까지는 계속 진행
                    if (i + 1) % 5 == 0:
                        print(f"   📜 {i+1}회 스크롤, 현재 {li_count}개 항목, 높이: {new_height}")
                    continue

                # 끝에 도달했는지 확인 (스크롤 위치 + 뷰포트 >= 전체 높이)
                viewport_height = driver.execute_script("return arguments[0].clientHeight", scroll_container)
                at_bottom = (new_scroll + viewport_height >= new_height - 10)

                if at_bottom and new_height == current_height:
                    no_change_count += 1
                    if no_change_count >= 3:
                        print(f"   ✅ 스크롤 완료 ({i+1}회, {li_count}개 항목)")
                        break
                else:
                    no_change_count = 0
        else:
            for _ in range(5):
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(1)
            print(f"   ✅ window 스크롤 완료")

        # 항목 수집 - 텍스트 기반 (한의원/병원/약국 등 포함)
        print(f"\n📋 항목 수집 중 (텍스트 기반)...")
        place_items = []
        all_li = driver.find_elements(By.TAG_NAME, "li")

        for li in all_li:
            try:
                text = li.text or ""
                # 업체 항목인지 판단 (거리 정보나 진료/영업 정보 포함)
                if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                    place_items.append(li)
                # 또는 한의원/병원/약국 등 키워드 포함
                elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                    if len(text) > 20:  # 충분한 텍스트가 있어야 함
                        place_items.append(li)
            except (StaleElementReferenceException, NoSuchElementException):
                pass

        print(f"   ✅ {len(place_items)}개 항목 수집됨\n")

        # 항목이 적으면 Apollo State 시도
        if len(place_items) < 20:
            print(f"🔍 Apollo State 파싱 시도...")
            try:
                driver.switch_to.default_content()
                apollo_state = driver.execute_script("return window.__APOLLO_STATE__ || null;")
                driver.switch_to.frame(iframe)

                if apollo_state:
                    json_items = []
                    for key, value in apollo_state.items():
                        if key.startswith("HospitalSummary:") and isinstance(value, dict):
                            name = value.get("name", "")
                            if name:
                                json_items.append({"name": name})

                    if len(json_items) > len(place_items):
                        print(f"   ✅ Apollo State: {len(json_items)}개 항목 (더 많음 → 사용)")

                        class ApolloItem:
                            def __init__(self, name):
                                self._text = name
                            @property
                            def text(self):
                                return self._text
                            def get_attribute(self, attr):
                                return self._text if attr in ["textContent", "innerText"] else ""
                            def find_elements(self, by, selector):
                                return []

                        place_items = [ApolloItem(item["name"]) for item in json_items]
                    else:
                        print(f"   ℹ️ Apollo State: {len(json_items)}개 (DOM 사용)")
                else:
                    print(f"   ⚠️ Apollo State 없음")
            except Exception as e:
                print(f"   ⚠️ Apollo State 오류: {e}")

        print(f"\n📊 최종 항목 수: {len(place_items)}개\n")

        # 모든 항목 이름 미리 추출
        print(f"📋 업체명 추출 중...")
        extracted_places = []  # [(name, is_ad, idx), ...]
        for idx, item in enumerate(place_items):
            try:
                place_name, is_ad = extract_place_name(item, skip_img_search=False)
                if not place_name:
                    try:
                        place_name = item.text or ""
                    except:
                        pass
                extracted_places.append((place_name, is_ad, idx))
            except:
                extracted_places.append(("", False, idx))

        print(f"   ✅ {len(extracted_places)}개 추출 완료\n")

        # 상위 20개 출력
        print(f"📋 상위 20개 항목:")
        for i, (name, is_ad, idx) in enumerate(extracted_places[:20]):
            ad_marker = "📢 [광고]" if is_ad else ""
            display_name = name[:50] if name else "[추출 실패]"
            print(f"  {i+1}. {display_name} {ad_marker}")
        print()

        # 타겟 검색 (광고 제외 순위)
        print(f"🎯 '{target_name}' 검색 중 (광고 제외 순위)...")
        found_rank = 0
        real_rank = 0
        is_target_ad = False
        ad_position = 0

        # 공백 제거하여 비교
        target_normalized = target_name.replace(" ", "")

        for place_name, is_ad, idx in extracted_places:
            if not is_ad:
                real_rank += 1

            # 공백 제거 후 비교
            place_normalized = place_name.replace(" ", "")
            if target_normalized in place_normalized:
                if is_ad:
                    is_target_ad = True
                    ad_position = idx + 1
                    print(f"   📢 광고로 발견! (광고 위치: {ad_position}번째)")
                else:
                    found_rank = real_rank
                    print(f"\n{'='*70}")
                    print(f"✅ 성공! '{target_name}' 발견!")
                    print(f"{'='*70}")
                    print(f"실제 순위: {found_rank}위 (광고 제외)")
                    print(f"리스트 위치: {idx + 1}번째")
                    print(f"업체명: {place_name[:100]}")
                    print(f"총 항목: {len(place_items)}개")
                    print(f"{'='*70}\n")
                break

        if found_rank == 0:
            print(f"\n{'='*70}")
            if is_target_ad:
                print(f"📢 '{target_name}' 광고로만 노출 중!")
                print(f"광고 위치: {ad_position}번째")
            else:
                print(f"❌ '{target_name}' 미발견")
            print(f"{'='*70}")
            print(f"총 항목: {len(place_items)}개")
            print(f"{'='*70}\n")

        driver.switch_to.default_content()

    except Exception as e:
        print(f"\n❌ 에러 발생:")
        print(f"   {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()

    finally:
        driver.quit()
        print(f"🔚 브라우저 종료\n")


if __name__ == "__main__":
    print(f"\n{'#'*70}")
    print(f"# 데스크탑 스크래핑 테스트 (모바일 제외)")
    print(f"{'#'*70}")

    for keyword in KEYWORDS:
        test_desktop_scraping(keyword, TARGET_NAME)

    print(f"\n✅ 테스트 완료!")
