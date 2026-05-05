import sys
import os
import time
import sqlite3
import random
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# [고도화 A-1] Sentry 에러 모니터링
try:
    from scrapers.sentry_init import init_sentry
    init_sentry("scraper_naver_place")
except Exception:
    pass

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException
)
from webdriver_manager.chrome import ChromeDriverManager
from datetime import datetime
from typing import List, Tuple, Dict, Any, Optional

# DB Setup - Use Manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from db.status_manager import status_manager
from utils import logger, download_image_robust

# [Phase 2.1] Event Bus Integration
try:
    from core.event_bus import publish_event, EventType
    HAS_EVENT_BUS = True
except ImportError:
    HAS_EVENT_BUS = False
    logger.debug("Event bus not available, events will not be published")

# Windows Encoding Fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


# =============================================================================
# [Phase 3] Browser Pool & Parallel Scanning
# =============================================================================

class BrowserPool:
    """
    [Phase 3] 스레드 안전한 브라우저 인스턴스 풀
    - 브라우저 인스턴스를 재사용하여 생성 오버헤드 감소
    - 최대 pool_size개의 브라우저만 유지
    """

    def __init__(self, pool_size: int = 3, mobile: bool = False, headless: bool = True):
        self.pool_size = pool_size
        self.mobile = mobile
        self.headless = headless
        self.browsers: List[webdriver.Chrome] = []
        self.lock = threading.Lock()
        self._closed = False
        logger.info(f"🏊 BrowserPool initialized (size={pool_size}, mobile={mobile})")

    def _create_browser(self) -> webdriver.Chrome:
        """새 브라우저 인스턴스 생성"""
        from retry_helper import SafeSeleniumDriver, USER_AGENTS

        options = Options()
        if self.headless:
            options.add_argument("--headless")

        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")

        # Random User-Agent
        ua = random.choice(USER_AGENTS)
        options.add_argument(f"user-agent={ua}")

        # Exclude automation switches
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)

        # Mobile emulation
        if self.mobile:
            mobile_emulation = {"deviceName": "iPhone X"}
            options.add_experimental_option("mobileEmulation", mobile_emulation)

        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )

        # Remove navigator.webdriver flag
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })

        driver.set_page_load_timeout(30)
        driver.implicitly_wait(10)

        return driver

    def get_browser(self) -> webdriver.Chrome:
        """풀에서 브라우저 가져오기 (없으면 새로 생성)"""
        with self.lock:
            if self._closed:
                raise RuntimeError("BrowserPool is closed")

            if self.browsers:
                browser = self.browsers.pop()
                logger.debug(f"🏊 Browser retrieved from pool (remaining: {len(self.browsers)})")
                return browser

        # 풀이 비어있으면 새로 생성 (lock 밖에서)
        logger.debug("🏊 Creating new browser instance...")
        return self._create_browser()

    def return_browser(self, browser: webdriver.Chrome):
        """브라우저를 풀에 반환"""
        if browser is None:
            return

        with self.lock:
            if self._closed:
                try:
                    browser.quit()
                except Exception as e:
                    logger.debug(f"Browser quit failed (pool closed): {e}")
                return

            if len(self.browsers) < self.pool_size:
                # 브라우저 상태 초기화 (쿠키, 로컬스토리지 삭제)
                try:
                    browser.delete_all_cookies()
                    browser.execute_script("window.localStorage.clear(); window.sessionStorage.clear();")
                except Exception as e:
                    logger.debug(f"Browser state reset failed: {e}")

                self.browsers.append(browser)
                logger.debug(f"🏊 Browser returned to pool (size: {len(self.browsers)})")
            else:
                # 풀이 가득 찼으면 브라우저 종료
                try:
                    browser.quit()
                except Exception as e:
                    logger.debug(f"Browser quit failed (pool full): {e}")
                logger.debug("🏊 Pool full, browser closed")

    def close_all(self):
        """모든 브라우저 종료"""
        with self.lock:
            self._closed = True
            for driver in self.browsers:
                try:
                    driver.quit()
                except Exception as e:
                    logger.debug(f"Browser quit failed during pool close: {e}")
            self.browsers.clear()
            logger.info("🏊 BrowserPool closed, all browsers terminated")


def _scan_single_keyword(
    pool: BrowserPool,
    keyword: str,
    target_name: str,
    device_type: str,
    competitors: List[str]
) -> Dict[str, Any]:
    """
    [Phase 3] 단일 키워드 스캔 (병렬 실행용)
    - 각 스레드에서 독립적으로 DB 연결 생성
    - 브라우저 풀에서 인스턴스 가져와 사용 후 반환
    """
    result = {
        "keyword": keyword,
        "device_type": device_type,
        "status": "error",
        "rank": 0,
        "total_results": 0,
        "note": "",
        "competitor_ranks": {}
    }

    # 각 스레드에서 별도 DB 연결 (SQLite 스레드 안전성)
    db = DatabaseManager()
    driver = None

    try:
        driver = pool.get_browser()

        # 디바이스별 URL 설정
        if device_type == "mobile":
            url = f"https://m.place.naver.com/place/list?query={keyword}"
        else:
            url = f"https://map.naver.com/p/search/{keyword}"

        device_emoji = "📱" if device_type == "mobile" else "🖥️"
        logger.info(f"   🔍 [{device_type}] Scanning: {keyword}...")

        driver.get(url)
        time.sleep(3 + random.random() * 2)

        found_rank = 0
        total_results = 0
        rank_status = "error"
        rank_note = ""
        extracted_places = []

        try:
            # 스크롤 및 항목 수집
            if device_type == "mobile":
                # Mobile: 메인 윈도우 스크롤
                for _ in range(3):
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1)

                # 항목 수집
                all_li = driver.find_elements(By.TAG_NAME, "li")
                place_items = []
                for li in all_li:
                    try:
                        text = li.text or ""
                        if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                            place_items.append(li)
                        elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                            if len(text) > 20:
                                place_items.append(li)
                    except (StaleElementReferenceException, NoSuchElementException):
                        pass

                for idx, item in enumerate(place_items):
                    try:
                        place_name, is_ad = _extract_place_name(item, skip_img_search=True)
                        if not place_name:
                            try:
                                place_name = item.text or ""
                            except Exception:
                                pass
                        extracted_places.append((place_name, is_ad, idx))
                    except Exception:
                        extracted_places.append(("", False, idx))

            else:
                # Desktop: iframe 내부 검색
                try:
                    iframe = driver.find_element(By.ID, "searchIframe")
                    driver.switch_to.frame(iframe)

                    # 스크롤 컨테이너 찾기
                    try:
                        scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
                    except NoSuchElementException:
                        try:
                            scroll_container = driver.find_element(By.CSS_SELECTOR, ".Ryr1F")
                        except NoSuchElementException:
                            scroll_container = None

                    if scroll_container:
                        no_change_count = 0
                        for scroll_attempt in range(50):
                            current_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
                            driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + 800;", scroll_container)
                            time.sleep(0.5)

                            if scroll_attempt < 10:
                                continue

                            new_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                            new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)
                            viewport_height = driver.execute_script("return arguments[0].clientHeight", scroll_container)
                            at_bottom = (new_scroll + viewport_height >= new_height - 10)

                            if at_bottom and new_height == current_height:
                                no_change_count += 1
                                if no_change_count >= 3:
                                    break
                            else:
                                no_change_count = 0

                    # 항목 수집
                    place_items = []
                    all_li = driver.find_elements(By.TAG_NAME, "li")
                    for li in all_li:
                        try:
                            text = li.text or ""
                            if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                                place_items.append(li)
                            elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                                if len(text) > 20:
                                    place_items.append(li)
                        except (StaleElementReferenceException, NoSuchElementException):
                            pass

                    for idx, item in enumerate(place_items):
                        try:
                            place_name, is_ad = _extract_place_name(item, skip_img_search=False)
                            if not place_name:
                                try:
                                    place_name = item.text or ""
                                except Exception:
                                    pass
                            extracted_places.append((place_name, is_ad, idx))
                        except Exception:
                            extracted_places.append(("", False, idx))

                    driver.switch_to.default_content()

                except Exception as iframe_err:
                    logger.debug(f"      ⚠️ iframe 처리 오류: {iframe_err}")
                    driver.switch_to.default_content()

            total_results = len(extracted_places)

            if not extracted_places:
                if "검색결과가 없습니다" in driver.page_source:
                    rank_status = "no_results"
                    rank_note = f"[{device_type}] 검색 결과 없음"
                else:
                    rank_status = "no_results"
                    rank_note = f"[{device_type}] DOM 파싱 실패"
            else:
                # 타겟 순위 계산
                real_rank = 0
                is_target_ad = False
                target_normalized = target_name.replace(" ", "")

                for place_name, is_ad, idx in extracted_places:
                    if not is_ad:
                        real_rank += 1

                    place_normalized = place_name.replace(" ", "")
                    if target_normalized in place_normalized:
                        if is_ad:
                            is_target_ad = True
                            rank_note = f"[{device_type}] 광고 게재 중 (위치: {idx + 1})"
                        else:
                            found_rank = real_rank
                            rank_status = "found"
                        break

                if found_rank > 0:
                    result["status"] = "found"
                elif is_target_ad:
                    rank_status = "found"
                    found_rank = 0
                else:
                    rank_status = "not_in_results"
                    rank_note = f"[{device_type}] 상위 {total_results}개에 미포함"

        except Exception as parse_err:
            logger.error(f"      ⚠️ [{device_type}] Parse Error: {parse_err}")
            rank_status = "error"
            rank_note = f"[{device_type}] {str(parse_err)[:150]}"

        # 이전 순위 조회 (이벤트 발행용)
        previous_rank, _ = _get_previous_rank(db, keyword, target_name)

        # DB 저장
        db.insert_rank(keyword, found_rank, target_name,
                       status=rank_status, total_results=total_results,
                       note=rank_note, device_type=device_type)

        # 순위 이벤트 발행
        if rank_status == "found" and found_rank > 0:
            _publish_rank_event(keyword, target_name, found_rank, previous_rank, total_results)

        # 경쟁사 순위 체크
        if extracted_places and rank_status != "error":
            for comp_name in competitors:
                if comp_name == target_name:
                    continue

                comp_rank = 0
                comp_status = "not_in_results"
                comp_note = ""
                real_rank = 0
                comp_normalized = comp_name.replace(" ", "")

                for place_name, is_ad, idx in extracted_places:
                    if not is_ad:
                        real_rank += 1

                    place_normalized = place_name.replace(" ", "")
                    if comp_normalized in place_normalized:
                        if is_ad:
                            comp_note = f"광고 게재 중 (위치: {idx + 1})"
                        else:
                            comp_rank = real_rank
                            comp_status = "found"
                        break

                db.insert_rank(keyword, comp_rank, comp_name,
                               status=comp_status, total_results=total_results,
                               note=comp_note, device_type=device_type)
                result["competitor_ranks"][comp_name] = comp_rank

        result.update({
            "status": rank_status,
            "rank": found_rank,
            "total_results": total_results,
            "note": rank_note
        })

    except Exception as e:
        logger.error(f"      ⚠️ [{device_type}] Error scanning {keyword}: {e}")
        db.insert_rank(keyword, 0, target_name,
                       status="error", total_results=0,
                       note=f"[{device_type}] {str(e)[:150]}", device_type=device_type)
        result["note"] = str(e)[:150]

    finally:
        if driver:
            pool.return_browser(driver)
        # 싱글톤 DB 연결은 닫지 않음 (다른 스레드에서 사용 중)

    return result


def _scan_keywords_parallel(
    keywords: List[str],
    target_name: str,
    device_type: str,
    max_workers: int = 3,
    delay_between_starts: float = 2.0
) -> List[Dict[str, Any]]:
    """
    [Phase 3] 키워드 병렬 스캔
    - ThreadPoolExecutor로 max_workers개의 브라우저를 병렬 실행
    - 네이버 차단 방지를 위해 시작 간격 딜레이

    Args:
        keywords: 스캔할 키워드 목록
        target_name: 메인 타겟 이름
        device_type: "mobile" 또는 "desktop"
        max_workers: 동시 브라우저 수 (기본: 3)
        delay_between_starts: 작업 시작 간격 (초)

    Returns:
        각 키워드별 스캔 결과 리스트
    """
    if not keywords:
        return []

    device_emoji = "📱" if device_type == "mobile" else "🖥️"
    logger.info(f"{device_emoji} [Phase 3] Starting PARALLEL {device_type.upper()} scan...")
    logger.info(f"   🚀 Keywords: {len(keywords)}, Workers: {max_workers}")

    # 경쟁사 목록 로드 (한 번만)
    competitors = _load_competitors()

    # 브라우저 풀 생성
    pool = BrowserPool(
        pool_size=max_workers,
        mobile=(device_type == "mobile"),
        headless=True
    )

    results = []
    start_time = time.time()

    try:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 작업 제출 (시작 간격 두어 차단 방지)
            futures = {}
            for idx, keyword in enumerate(keywords):
                if idx > 0:
                    time.sleep(delay_between_starts)

                future = executor.submit(
                    _scan_single_keyword,
                    pool,
                    keyword,
                    target_name,
                    device_type,
                    competitors
                )
                futures[future] = keyword

            # 결과 수집
            for future in as_completed(futures):
                keyword = futures[future]
                try:
                    result = future.result()
                    results.append(result)

                    # 진행 상황 로그
                    if result["status"] == "found" and result["rank"] > 0:
                        logger.info(f"   ✅ [{device_type}] {keyword}: Rank {result['rank']}")
                    elif result["status"] == "found":
                        logger.info(f"   📢 [{device_type}] {keyword}: AD only")
                    else:
                        logger.info(f"   ❌ [{device_type}] {keyword}: {result['status']}")

                except Exception as e:
                    logger.error(f"   ⚠️ [{device_type}] {keyword} failed: {e}")
                    results.append({
                        "keyword": keyword,
                        "device_type": device_type,
                        "status": "error",
                        "rank": 0,
                        "total_results": 0,
                        "note": str(e)[:150]
                    })

    finally:
        pool.close_all()

    elapsed = time.time() - start_time
    logger.info(f"{device_emoji} [Phase 3] Parallel scan complete in {elapsed:.1f}s ({len(results)}/{len(keywords)} keywords)")

    return results


def _load_competitors() -> list:
    """경쟁사 목록 로드 (targets.json에서 High/Critical 우선순위)"""
    competitors = []
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'targets.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                for t in config_data.get('targets', []):
                    if t.get('priority') in ['High', 'Critical', 'Medium']:
                        competitors.append(t['name'])
        except Exception as e:
            logger.error(f"Failed to load competitors: {e}")
    return competitors


def _get_previous_rank(db: DatabaseManager, keyword: str, target_name: str) -> tuple:
    """
    [Phase 2.1] 이전 순위 조회
    Returns: (previous_rank, days_ago) - 순위와 며칠 전 데이터인지
    """
    try:
        db.cursor.execute('''
            SELECT rank, checked_at
            FROM rank_history
            WHERE keyword = ? AND target_name = ? AND status = 'found'
            ORDER BY checked_at DESC
            LIMIT 1 OFFSET 1
        ''', (keyword, target_name))
        row = db.cursor.fetchone()
        if row:
            prev_rank = row[0]
            checked_at = datetime.fromisoformat(row[1]) if row[1] else datetime.now()
            days_ago = (datetime.now() - checked_at).days
            return prev_rank, days_ago
    except Exception as e:
        logger.debug(f"Failed to get previous rank: {e}")
    return None, 0


def _publish_rank_event(keyword: str, target_name: str, current_rank: int,
                        previous_rank: int, total_results: int):
    """
    [Phase 2.1] 순위 변동 이벤트 발행
    - RANK_CHECKED: 모든 순위 체크
    - RANK_CHANGED: 순위 변동 발생
    - RANK_DROPPED: 순위 5위 이상 하락
    - RANK_IMPROVED: 순위 상승
    """
    if not HAS_EVENT_BUS:
        return

    try:
        # 기본 데이터
        event_data = {
            "keyword": keyword,
            "target_name": target_name,
            "current_rank": current_rank,
            "previous_rank": previous_rank,
            "total_results": total_results,
            "change": (previous_rank - current_rank) if previous_rank else 0
        }

        # 1. RANK_CHECKED 이벤트 (항상 발행)
        publish_event(EventType.RANK_CHECKED, event_data, source="place_sniper")

        # 이전 순위가 있는 경우에만 변동 이벤트 발행
        if previous_rank and previous_rank != current_rank:
            change = previous_rank - current_rank

            # 2. RANK_CHANGED 이벤트 (변동 시)
            publish_event(EventType.RANK_CHANGED, event_data, source="place_sniper")

            # 3. RANK_DROPPED 이벤트 (5위 이상 하락)
            if change <= -5:
                event_data["severity"] = "critical" if change <= -10 else "warning"
                publish_event(EventType.RANK_DROPPED, event_data, source="place_sniper")
                logger.warning(f"🚨 순위 급락 감지: {keyword} ({previous_rank}위 → {current_rank}위)")

            # 4. RANK_IMPROVED 이벤트 (순위 상승)
            elif change > 0:
                event_data["improvement"] = change
                publish_event(EventType.RANK_IMPROVED, event_data, source="place_sniper")
                logger.info(f"📈 순위 상승: {keyword} ({previous_rank}위 → {current_rank}위)")

    except Exception as e:
        logger.debug(f"Failed to publish rank event: {e}")


def _extract_place_name(item, skip_img_search: bool = False) -> tuple:
    """
    업체명과 광고 여부 추출 (테스트 스크립트와 동일한 로직)
    Returns: (name: str, is_ad: bool)
    """
    import re
    try:
        full_text = ""
        try:
            full_text = item.text or item.get_attribute("textContent") or ""
        except Exception as e:
            logger.debug(f"Failed to get item text: {e}")

        is_ad = "광고" in full_text

        # 방법 1: img[alt] 속성
        if not skip_img_search:
            try:
                img = item.find_element(By.CSS_SELECTOR, "img[alt]")
                alt = img.get_attribute("alt")
                if alt and len(alt) >= 2 and "이미지" not in alt.lower():
                    return alt.strip(), is_ad
            except NoSuchElementException:
                pass  # img 요소 없음 - 정상 케이스
            except Exception as e:
                logger.debug(f"Failed to extract img alt: {e}")

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
                for cat in ["한의원", "한방병원", "병원", "의원", "약국"]:
                    if cat in full_text[:100]:
                        name += " " + cat if not name.endswith(cat) else ""
                        break
                if len(name) >= 2:
                    return name.strip(), is_ad

        return full_text[:50] if full_text else "", is_ad
    except Exception:
        return "", False


def _scan_keywords_for_device(driver, db, keywords, target_name, device_type: str):
    """
    특정 디바이스 타입(mobile/desktop)으로 키워드 순위 스캔
    """
    # 디바이스별 올바른 URL 사용
    if device_type == "mobile":
        base_url = "https://m.place.naver.com"
        url_format = "{base}/place/list?query={keyword}"
    else:  # desktop
        base_url = "https://map.naver.com"
        url_format = "{base}/p/search/{keyword}"

    device_emoji = "📱" if device_type == "mobile" else "🖥️"

    logger.info(f"{device_emoji} Starting {device_type.upper()} scan...")

    for keyword in keywords:
        logger.info(f"   🔍 [{device_type}] Searching: {keyword}...")
        status_manager.update_status("Place Sniper", "RUNNING", f"[{device_type}] {keyword}")
        try:
            url = url_format.format(base=base_url, keyword=keyword)
            driver.get(url)
            time.sleep(3 + random.random() * 2)

            found_rank = 0
            total_results = 0
            rank_status = "error"
            rank_note = ""

            try:
                # Scroll to load more results
                if device_type == "mobile":
                    # Mobile: 메인 윈도우 스크롤
                    for _ in range(3):
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(1)
                else:
                    # Desktop: iframe 내부 스크롤 (나중에 수행)
                    pass

                place_items = []

                # [디버그] 스크린샷 저장
                if device_type == "desktop":
                    try:
                        os.makedirs("debug_screenshots", exist_ok=True)
                        screenshot_path = f"debug_screenshots/{keyword.replace(' ', '_')}_desktop.png"
                        driver.save_screenshot(screenshot_path)
                        logger.info(f"      📸 Screenshot saved: {screenshot_path}")

                        # [추가] HTML 소스 저장
                        html_path = f"debug_screenshots/{keyword.replace(' ', '_')}_desktop.html"
                        with open(html_path, 'w', encoding='utf-8') as f:
                            f.write(driver.page_source)
                        logger.info(f"      📄 HTML saved: {html_path}")
                    except Exception as e:
                        logger.debug(f"Failed to save debug files: {e}")

                # Device-specific parsing strategies
                extracted_places = []  # [(name, is_ad, idx), ...] - 모든 디바이스에서 사용

                if device_type == "mobile":
                    # Mobile: 텍스트 기반 li 수집 (데스크톱과 동일한 접근 방식)
                    all_li = driver.find_elements(By.TAG_NAME, "li")
                    for li in all_li:
                        try:
                            text = li.text or ""
                            # 업체 항목인지 판단 (거리 정보나 진료/영업 정보 포함)
                            if ("km" in text or "m " in text) and ("진료" in text or "영업" in text or "휴무" in text):
                                place_items.append(li)
                            # 또는 한의원/병원/약국 등 키워드 포함
                            elif any(kw in text for kw in ["한의원", "병원", "약국", "의원", "클리닉"]):
                                if len(text) > 20:
                                    place_items.append(li)
                        except (StaleElementReferenceException, NoSuchElementException):
                            pass

                    # 모바일에서도 extracted_places 생성
                    for idx, item in enumerate(place_items):
                        try:
                            place_name, is_ad = _extract_place_name(item, skip_img_search=True)
                            if not place_name:
                                try:
                                    place_name = item.text or ""
                                except Exception:
                                    pass
                            extracted_places.append((place_name, is_ad, idx))
                        except Exception:
                            extracted_places.append(("", False, idx))

                    logger.info(f"      🔍 [mobile] Found {len(extracted_places)} items")

                else:
                    # Desktop: map.naver.com - iframe 내부 검색 결과
                    try:
                        # searchIframe으로 전환
                        iframe = driver.find_element(By.ID, "searchIframe")
                        driver.switch_to.frame(iframe)
                        logger.debug(f"      🔄 Switched to searchIframe")

                        # iframe 내부 검색 결과 컨테이너 스크롤로 모든 결과 로드
                        try:
                            scroll_container = driver.find_element(By.ID, "_pcmap_list_scroll_container")
                        except NoSuchElementException:
                            # fallback: 클래스명으로 찾기
                            try:
                                scroll_container = driver.find_element(By.CSS_SELECTOR, ".Ryr1F")
                            except NoSuchElementException:
                                scroll_container = None

                        if scroll_container:
                            prev_height = 0
                            max_scrolls = 50  # 최대 50회 스크롤
                            min_scrolls = 10  # 최소 10회 스크롤 강제
                            no_change_count = 0

                            for scroll_attempt in range(max_scrolls):
                                # 스크롤 전 높이 확인
                                current_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)

                                # 점진적 스크롤 (한 번에 800px씩)
                                driver.execute_script("arguments[0].scrollTop = arguments[0].scrollTop + 800;", scroll_container)
                                time.sleep(0.5)

                                # 스크롤 후 상태 확인
                                new_scroll = driver.execute_script("return arguments[0].scrollTop", scroll_container)
                                new_height = driver.execute_script("return arguments[0].scrollHeight", scroll_container)

                                # 최소 스크롤 횟수까지는 계속 진행
                                if scroll_attempt < min_scrolls:
                                    continue

                                # 끝에 도달했는지 확인
                                viewport_height = driver.execute_script("return arguments[0].clientHeight", scroll_container)
                                at_bottom = (new_scroll + viewport_height >= new_height - 10)

                                if at_bottom and new_height == current_height:
                                    no_change_count += 1
                                    if no_change_count >= 3:
                                        all_li = driver.find_elements(By.TAG_NAME, "li")
                                        logger.debug(f"      📜 Scroll complete after {scroll_attempt} scrolls (total li: {len(all_li)})")
                                        break
                                else:
                                    no_change_count = 0

                                prev_height = new_height
                        else:
                            logger.debug(f"      ⚠️ Scroll container not found, using window scroll")
                            # fallback: window 스크롤
                            for _ in range(3):
                                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                                time.sleep(1)

                        # 항목 수집 - 텍스트 기반 (테스트 스크립트와 동일)
                        # 페이지네이션 없이 스크롤로 로드된 항목만 수집 (stale 요소 문제 방지)
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
                                    if len(text) > 20:
                                        place_items.append(li)
                            except (StaleElementReferenceException, NoSuchElementException):
                                pass

                        logger.info(f"      🔍 [iframe Strategy 1] Found {len(place_items)} items (텍스트 기반)")

                        # ===== DOM에서 업체명 추출 (iframe 전환 전에 완료해야 함!) =====
                        extracted_places = []  # [(name, is_ad, original_idx), ...]
                        skip_img = (device_type == "mobile")

                        for idx, item in enumerate(place_items):
                            try:
                                place_name, is_ad = _extract_place_name(item, skip_img_search=skip_img)
                                if not place_name:
                                    try:
                                        place_name = item.text or ""
                                    except Exception:
                                        pass
                                extracted_places.append((place_name, is_ad, idx))
                            except Exception:
                                extracted_places.append(("", False, idx))

                        logger.debug(f"      ✅ Extracted {len(extracted_places)} place names from DOM")

                        # Strategy 3: __APOLLO_STATE__ JSON 파싱 (항목이 적으면 시도)
                        # [FIX] Apollo State는 메인 프레임에 있으므로 iframe에서 나와서 접근
                        if len(place_items) < 20:
                            try:
                                driver.switch_to.default_content()  # 메인 프레임으로 전환
                                apollo_state = driver.execute_script("return window.__APOLLO_STATE__ || null;")
                                if apollo_state:
                                    json_items = []
                                    for key, value in apollo_state.items():
                                        if key.startswith("HospitalSummary:") and isinstance(value, dict):
                                            name = value.get("name", "")
                                            if name:
                                                json_items.append({"name": name})

                                    if len(json_items) > len(place_items):
                                        logger.info(f"      🔍 [Apollo State] Found {len(json_items)} items (더 많음 → 사용)")
                                        # Apollo State에서 extracted_places 재생성
                                        extracted_places = [(item["name"], False, idx) for idx, item in enumerate(json_items)]
                            except Exception as apollo_err:
                                logger.debug(f"      ⚠️ Apollo State 파싱 오류: {apollo_err}")

                        # 원래 프레임으로 복귀
                        driver.switch_to.default_content()

                    except Exception as iframe_err:
                        logger.debug(f"      ⚠️ iframe 처리 오류: {iframe_err}")
                        driver.switch_to.default_content()

                total_results = len(extracted_places) if extracted_places else 0

                if not extracted_places:
                    if "검색결과가 없습니다" in driver.page_source:
                        logger.info(f"      ℹ️ [{device_type}] No places found for '{keyword}'.")
                        rank_status = "no_results"
                        rank_note = f"[{device_type}] 네이버 플레이스 검색 결과 없음"
                    else:
                        logger.warning(f"      ⚠️ [{device_type}] No place items found for '{keyword}'.")
                        rank_status = "no_results"
                        rank_note = f"[{device_type}] DOM 파싱 실패"
                else:

                    # [DEBUG] 상위 20개 업체명 출력
                    logger.info(f"      📋 [DEBUG] 상위 20개 업체명:")
                    for i, (name, is_ad, idx) in enumerate(extracted_places[:20]):
                        ad_mark = "[광고]" if is_ad else ""
                        logger.info(f"         {i+1}. {name[:40]} {ad_mark}")

                    # ===== 타겟 순위 계산 (추출된 리스트 사용) =====
                    real_rank = 0  # 광고 제외 실제 순위
                    is_target_ad = False  # 타겟이 광고인지 여부
                    target_normalized = target_name.replace(" ", "")  # 공백 제거

                    for place_name, is_ad, idx in extracted_places:
                        # 광고가 아닌 경우에만 실제 순위 증가
                        if not is_ad:
                            real_rank += 1

                        # 타겟명 매칭 (공백 제거 후 비교)
                        place_normalized = place_name.replace(" ", "")
                        if target_normalized in place_normalized:
                            if is_ad:
                                # 광고인 경우: 순위는 0으로 처리하고 메모에 기록
                                is_target_ad = True
                                rank_note = f"[{device_type}] 광고 게재 중 (광고 위치: {idx + 1}번째)"
                                logger.info(f"      📢 [{device_type}] '{target_name}' is running ad (position {idx + 1})")
                            else:
                                # 일반 순위: 광고 제외 실제 순위
                                found_rank = real_rank
                                rank_status = "found"
                                logger.debug(f"      🎯 [{device_type}] '{target_name}' found at real rank {real_rank} (list position {idx + 1})")
                            break

                    if found_rank > 0:
                        logger.info(f"      ✅ [{device_type}] Found at Rank {found_rank}! (total: {total_results}, 광고 제외)")
                    elif is_target_ad:
                        # 광고로만 노출되는 경우
                        rank_status = "found"
                        found_rank = 0  # 광고는 순위 0으로 표시
                        logger.info(f"      📢 [{device_type}] Found as AD only (total: {total_results})")
                    else:
                        logger.info(f"      ❌ [{device_type}] Not in top {total_results} results.")
                        rank_status = "not_in_results"
                        rank_note = f"[{device_type}] 상위 {total_results}개 결과에 미포함"

            except Exception as parse_err:
                logger.error(f"      ⚠️ [{device_type}] Parse Error: {parse_err}", exc_info=True)
                rank_status = "error"
                rank_note = f"[{device_type}] {str(parse_err)[:150]}"

            # 이전 순위 조회 (이벤트 발행용)
            previous_rank, _ = _get_previous_rank(db, keyword, target_name)

            # device_type 포함하여 저장
            db.insert_rank(keyword, found_rank, target_name,
                           status=rank_status, total_results=total_results,
                           note=rank_note, device_type=device_type)

            # 순위 이벤트 발행
            if rank_status == "found" and found_rank > 0:
                _publish_rank_event(keyword, target_name, found_rank,
                                    previous_rank, total_results)

            # 경쟁사 순위도 함께 체크 (광고 제외 순위) - extracted_places 재사용
            if extracted_places and rank_status != "error":
                competitors = _load_competitors()
                logger.debug(f"      👥 Checking {len(competitors)} competitors...")

                for comp_name in competitors:
                    if comp_name == target_name:
                        continue
                    comp_rank = 0
                    comp_status = "not_in_results"
                    comp_note = ""
                    real_rank = 0  # 광고 제외 실제 순위
                    comp_normalized = comp_name.replace(" ", "")  # 공백 제거

                    # extracted_places 재사용 (DOM 접근 없음!)
                    for place_name, is_ad, idx in extracted_places:
                        # 광고가 아닌 경우에만 실제 순위 증가
                        if not is_ad:
                            real_rank += 1

                        # 공백 제거 후 비교
                        place_normalized = place_name.replace(" ", "")
                        if comp_normalized in place_normalized:
                            if is_ad:
                                comp_note = f"광고 게재 중 (위치: {idx + 1})"
                            else:
                                comp_rank = real_rank
                                comp_status = "found"
                            break

                    db.insert_rank(keyword, comp_rank, comp_name,
                                   status=comp_status, total_results=total_results,
                                   note=comp_note, device_type=device_type)

        except Exception as e:
            logger.error(f"      ⚠️ [{device_type}] Error scraping {keyword}: {e}", exc_info=True)
            db.insert_rank(keyword, 0, target_name,
                           status="error", total_results=0,
                           note=f"[{device_type}] {str(e)[:150]}", device_type=device_type)


def check_naver_place_rank(parallel: bool = True, max_workers: int = 3):
    """
    네이버 플레이스 순위 체크

    Args:
        parallel: True면 병렬 모드 사용 (Phase 3), False면 순차 모드
        max_workers: 병렬 모드에서 동시 브라우저 수 (기본: 3)
    """
    # Load Dynamic Keywords
    import json
    from retry_helper import SafeSeleniumDriver
    kw_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config', 'keywords.json')
    keywords = []
    if os.path.exists(kw_path):
        try:
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                keywords = data.get("naver_place", [])
        except Exception as e:
            logger.error(f"❌ Failed to load keywords.json: {e}", exc_info=True)
            return # Fail fast

    if not keywords:
        logger.error("❌ No keywords found in config. Aborting Rank Check.")
        return

    logger.info(f"📋 Loaded {len(keywords)} Target Keywords")

    # Load Main Target
    target_name = "규림한의원" # Default
    try:
        from utils import ConfigManager
        cfg = ConfigManager()
        targets_data = cfg.load_targets()
        for t in targets_data.get('targets', []):
            if "규림" in t['name']:
                target_name = t['name']
                break
    except Exception as e:
        logger.error(f"❌ Failed to load target name from config: {e}", exc_info=True)
        pass # Keep default "규림한의원" but log error.

    logger.info(f"🎯 Target Name: {target_name}")

    mode_str = f"PARALLEL (workers={max_workers})" if parallel else "SEQUENTIAL"
    print(f"🚀 Naver Place Rank Tracker Started... [{mode_str}]")
    status_manager.update_status("Place Sniper", "RUNNING", f"Checking Ranks... [{mode_str}]")

    start_time = time.time()

    if parallel:
        # [Phase 3] 병렬 모드 - BrowserPool + ThreadPoolExecutor
        logger.info(f"⚡ [Phase 3] PARALLEL MODE: {max_workers} concurrent browsers")

        # 1. 모바일 병렬 스캔
        logger.info("📱 Phase 1: Mobile PARALLEL Scan...")
        mobile_results = _scan_keywords_parallel(
            keywords, target_name, "mobile",
            max_workers=max_workers,
            delay_between_starts=2.0  # 네이버 차단 방지
        )

        # 2. 데스크톱 병렬 스캔
        logger.info("🖥️ Phase 2: Desktop PARALLEL Scan...")
        desktop_results = _scan_keywords_parallel(
            keywords, target_name, "desktop",
            max_workers=max_workers,
            delay_between_starts=2.0
        )

        # 결과 요약
        mobile_found = sum(1 for r in mobile_results if r["status"] == "found" and r["rank"] > 0)
        desktop_found = sum(1 for r in desktop_results if r["status"] == "found" and r["rank"] > 0)
        logger.info(f"📊 Results: Mobile {mobile_found}/{len(keywords)}, Desktop {desktop_found}/{len(keywords)}")

    else:
        # 기존 순차 모드
        db = DatabaseManager()

        # 1. 모바일 스캔 (m.place.naver.com)
        logger.info("📱 Phase 1: Mobile Scan Starting...")
        with SafeSeleniumDriver(mobile=True, headless=True) as driver:
            _scan_keywords_for_device(driver, db, keywords, target_name, "mobile")

        # 2. 데스크톱 스캔 (place.naver.com)
        logger.info("🖥️ Phase 2: Desktop Scan Starting...")
        with SafeSeleniumDriver(mobile=False, headless=True) as driver:
            _scan_keywords_for_device(driver, db, keywords, target_name, "desktop")

    elapsed = time.time() - start_time
    print(f"🏁 Rank Check Complete (Mobile + Desktop) in {elapsed:.1f}s")
    status_manager.update_status("Place Sniper", "COMPLETED", f"Rank Check Done ({elapsed:.1f}s)")

def collect_competitor_reviews():
    """
    Real Review Scraper:
    1. Reads targeted competitors from DB/Config.
    2. Searches them on Naver Place.
    3. Scrapes recent 'Receipt Reviews'.
    4. Saves to 'competitor_reviews' table.
    """
    logger.info("🗣️ collecting Competitor Reviews (The Real Blood)...")
    from retry_helper import SafeSeleniumDriver
    
    # 1. Get Targets from config
    db = DatabaseManager()
    
    # Load targets from config file (Low 제외, 나머지 모두 스캔)
    targets = []
    config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config', 'targets.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                # Low(벤치마크)만 제외, Critical/High/Medium 모두 스캔
                targets = [t['name'] for t in config_data.get('targets', []) if t.get('priority') != 'Low']
        except Exception as e:
            logger.error(f"❌ Failed to load targets config: {e}", exc_info=True)
    
    if not targets:
        targets = ["하늘체한의원 청주점", "자연과한의원 청주점"]
    
    with SafeSeleniumDriver(mobile=True, headless=True) as driver:
        for target in targets:
            logger.info(f"   🔍 Targeting: {target}")
            try:
                encoded_query = target.replace(" ", "%20")
                url = f"https://m.place.naver.com/place/list?query={encoded_query}"
                driver.get(url)
                time.sleep(3)
                
                # Check for zero results
                if "검색결과가 없습니다" in driver.page_source:
                    logger.warning(f"   ⚠️ No place found for '{target}'. Skipping.")
                    continue

                # Click first result (assuming it's the target)
                try:
                    # [Robustness] Use same strategy as rank checker
                    place_items = driver.find_elements(By.CSS_SELECTOR, "[data-entry-id], [data-naver-card]")
                    
                    if not place_items:
                        # Fallback to li with place-like indicators
                        list_items = driver.find_elements(By.CSS_SELECTOR, "li")
                        for item in list_items:
                            t = item.text
                            if len(t) > 5 and ("리뷰" in t or "m" in t or "건" in t or "점" in t or target[:3] in t):
                                place_items.append(item)
                    
                    clicked = False
                    if place_items:
                        # Try to click the first one that seems relevant
                        # Priority: one that contains target name or just the first result
                        for item in place_items:
                            try:
                                # [BATTLEFRONT] More aggressive name matching
                                # Clean name for comparison
                                clean_target = target.replace(" ", "")
                                clean_item_text = item.text.replace(" ", "")
                                if clean_target[:5] in clean_item_text:
                                    item.click()
                                    clicked = True
                                    logger.info(f"      🎯 Clicked item matching: {target}")
                                    break
                            except Exception: continue
                        
                        if not clicked:
                            # Try searching for a/span/div with target name inside
                            try:
                                anchor = driver.find_element(By.XPATH, f"//a[contains(., '{target[:3]}')] | //span[contains(., '{target[:3]}')]")
                                anchor.click()
                                clicked = True
                                logger.info(f"      🎯 Clicked anchor/span with name: {target[:3]}")
                            except Exception as e:
                                logger.debug(f"Failed to click anchor/span: {e}")
                        
                        if not clicked:
                            place_items[0].click()
                            clicked = True
                            logger.info("      🎯 Clicked first place item as fallback.")
                    
                    if not clicked: raise Exception("No clickable place item found")
                    
                    time.sleep(3)
                    
                    # Go to Review Tab
                    try:
                        # [BATTLEFRONT] Strategy: Try different review tab patterns
                        review_selectors = [
                            (By.XPATH, "//*[contains(text(), '리뷰')]"),
                            (By.CSS_SELECTOR, "[data-tab-id='review']"),
                            (By.CSS_SELECTOR, "a[href*='review']"),
                            (By.XPATH, "//span[contains(text(), '리뷰')]")
                        ]
                        
                        tab_clicked = False
                        for by, sel in review_selectors:
                            try:
                                btn = driver.find_element(by, sel)
                                btn.click()
                                tab_clicked = True
                                break
                            except Exception: continue
                            
                        if not tab_clicked:
                            # Last resort: navigate directly to review URL part if possible
                            # Naver Place mobile detail URL is https://m.place.naver.com/place/ID/home
                            # Review is https://m.place.naver.com/place/ID/review
                            current_url = driver.current_url
                            if "/home" in current_url:
                                review_url = current_url.replace("/home", "/review")
                                driver.get(review_url)
                                tab_clicked = True
                                logger.info("      🎯 Navigated directly to review URL.")
                        
                        if not tab_clicked:
                            logger.warning("      ⚠️ Could not find Review tab. Staying on current page.")
                    except Exception as e:
                        logger.warning(f"      ⚠️ Review Tab navigation failed: {e}")
                        
                    time.sleep(2)

                    # [IMPROVED] 스크롤하여 더 많은 리뷰 로드 (최근 30일치 수집 목표)
                    for scroll_attempt in range(10):  # 충분히 스크롤
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(0.8)

                    review_elements = driver.find_elements(By.CSS_SELECTOR, "li")
                    count = 0
                    skipped_old = 0
                    img_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'images_scraped')
                    os.makedirs(img_dir, exist_ok=True)
                    import requests
                    import re

                    # 기존 리뷰 해시 목록 (중복 방지)
                    existing_hashes = set()
                    db.cursor.execute("SELECT content FROM competitor_reviews WHERE competitor_name = ?", (target,))
                    for row in db.cursor.fetchall():
                        existing_hashes.add(hash(row[0][:50]) if row[0] else 0)

                    def parse_relative_date(text):
                        """
                        네이버 플레이스 상대 날짜 파싱
                        예: "1일 전", "3일 전", "1주 전", "2주 전", "1개월 전", "3개월 전"
                        Returns: (days_ago, actual_date)
                        """
                        from datetime import datetime, timedelta
                        today = datetime.now()

                        # 오늘/어제
                        if "오늘" in text or "방금" in text:
                            return 0, today.strftime("%Y-%m-%d")
                        if "어제" in text:
                            return 1, (today - timedelta(days=1)).strftime("%Y-%m-%d")

                        # N일 전
                        match = re.search(r'(\d+)\s*일\s*전', text)
                        if match:
                            days = int(match.group(1))
                            return days, (today - timedelta(days=days)).strftime("%Y-%m-%d")

                        # N주 전
                        match = re.search(r'(\d+)\s*주\s*전', text)
                        if match:
                            weeks = int(match.group(1))
                            days = weeks * 7
                            return days, (today - timedelta(days=days)).strftime("%Y-%m-%d")

                        # N개월 전
                        match = re.search(r'(\d+)\s*개월\s*전', text)
                        if match:
                            months = int(match.group(1))
                            days = months * 30
                            return days, (today - timedelta(days=days)).strftime("%Y-%m-%d")

                        # N년 전
                        match = re.search(r'(\d+)\s*년\s*전', text)
                        if match:
                            years = int(match.group(1))
                            days = years * 365
                            return days, (today - timedelta(days=days)).strftime("%Y-%m-%d")

                        # 파싱 실패 시 30일 전으로 가정 (수집은 하되 오래된 것으로 처리)
                        return 30, (today - timedelta(days=30)).strftime("%Y-%m-%d")

                    for rv in review_elements:
                        text = rv.text
                        if len(text) > 10 and ("접기" in text or "더보기" in text or "방문" in text):
                            clean_text = text.replace("더보기", "").replace("\n", " ").strip()

                            # [IMPROVED] 날짜 파싱 - 최근 30일 이내만 수집
                            days_ago, review_date = parse_relative_date(text)
                            if days_ago > 30:
                                skipped_old += 1
                                continue  # 30일 이전 리뷰는 스킵

                            # 중복 체크
                            text_hash = hash(clean_text[:50])
                            if text_hash in existing_hashes:
                                continue
                            existing_hashes.add(text_hash)

                            try:
                                img_tag = rv.find_element(By.TAG_NAME, "img")
                                if img_tag:
                                    src = img_tag.get_attribute("src")
                                    if src:
                                        fname = f"review_{target.replace(' ', '')}_{count}.jpg"
                                        save_path = os.path.join(img_dir, fname)
                                        success = download_image_robust(src, save_path)
                                        if not success:
                                            logger.warning(f"      Failed to download image: {src[:50]}...")
                            except NoSuchElementException:
                                pass  # 이미지 없음 - 정상 케이스
                            except Exception as img_err:
                                logger.debug(f"Review image extraction failed: {img_err}")

                            # Sentiment Analysis (Simple)
                            sentiment = "neutral"
                            if "친절" in clean_text or "좋아" in clean_text or "추천" in clean_text or "최고" in clean_text:
                                sentiment = "positive"
                            if "별로" in clean_text or "대기" in clean_text or "비싸" in clean_text or "불친절" in clean_text:
                                sentiment = "negative"

                            img_count = 0
                            try:
                                imgs = rv.find_elements(By.TAG_NAME, "img")
                                img_count = len(imgs)
                            except Exception as e:
                                logger.debug(f"Failed to count review images: {e}")

                            # [Phase 1.2] 중복 방지 insert 사용
                            if db.insert_competitor_review(
                                competitor_name=target,
                                source="naver_place_real",
                                content=clean_text,
                                sentiment=sentiment,
                                keywords="[]",
                                review_date=review_date,
                                image_count=img_count
                            ):
                                count += 1
                            # else: 중복이면 카운트하지 않음

                    db.conn.commit()
                    logger.info(f"      ✅ {count} new reviews (30일 이내), skipped {skipped_old} older reviews")

                    # [Phase 2.1] 경쟁사 리뷰 수집 이벤트 발행
                    if HAS_EVENT_BUS and count > 0:
                        try:
                            publish_event(
                                EventType.COMPETITOR_REVIEW_COLLECTED,
                                {
                                    "competitor_name": target,
                                    "source": "naver_place_real",
                                    "new_reviews_count": count,
                                    "skipped_old_count": skipped_old
                                },
                                source="place_sniper"
                            )
                        except Exception as evt_err:
                            logger.debug(f"Failed to publish review event: {evt_err}")

                except Exception as e:
                    logger.error(f"      ❌ Failed to parse place page: {e}")
                    
            except Exception as e:
               logger.error(f"   ⚠️ Error processing target {target}: {e}")

    # 싱글톤 DB 연결은 닫지 않음

def scan_single_keyword(
    keyword: str,
    device_type: str = "mobile",
    target_name: str = None,
    headless: bool = True
) -> Dict[str, Any]:
    """
    [Phase 4] 단일 키워드 스캔 - AutoRescanHandler에서 사용

    Args:
        keyword: 스캔할 키워드
        device_type: "mobile" 또는 "desktop"
        target_name: 타겟 업체명 (기본: config에서 로드)
        headless: 헤드리스 모드 여부

    Returns:
        스캔 결과 딕셔너리
    """
    # 타겟 이름 로드
    if target_name is None:
        target_name = "규림한의원"
        try:
            from utils import ConfigManager
            cfg = ConfigManager()
            targets_data = cfg.load_targets()
            for t in targets_data.get('targets', []):
                if "규림" in t['name']:
                    target_name = t['name']
                    break
        except Exception as e:
            logger.warning(f"Failed to load target name: {e}")

    logger.info(f"🎯 [Phase 4] Single keyword scan: {keyword} ({device_type})")

    # 브라우저 풀 생성 (단일 인스턴스)
    pool = BrowserPool(
        pool_size=1,
        mobile=(device_type == "mobile"),
        headless=headless
    )

    # 경쟁사 목록 로드
    competitors = _load_competitors()

    try:
        result = _scan_single_keyword(
            pool,
            keyword,
            target_name,
            device_type,
            competitors
        )

        if result["status"] == "found" and result["rank"] > 0:
            logger.info(f"✅ [{device_type}] {keyword}: Rank {result['rank']}")
        else:
            logger.info(f"❌ [{device_type}] {keyword}: {result['status']}")

        return result

    finally:
        pool.close_all()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Naver Place Rank Tracker")
    parser.add_argument(
        "--sequential", "-s",
        action="store_true",
        help="Use sequential mode instead of parallel (default: parallel)"
    )
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=3,
        help="Number of concurrent browsers in parallel mode (default: 3)"
    )
    parser.add_argument(
        "--skip-reviews",
        action="store_true",
        help="Skip competitor review collection"
    )
    # [Phase 4] 단일 키워드 스캔 옵션
    parser.add_argument(
        "--keyword", "-k",
        type=str,
        default=None,
        help="[Phase 4] Scan a single keyword only"
    )
    parser.add_argument(
        "--device", "-d",
        type=str,
        choices=["mobile", "desktop", "both"],
        default="both",
        help="[Phase 4] Device type for single keyword scan (default: both)"
    )

    args = parser.parse_args()

    # [Phase 4] 단일 키워드 스캔 모드
    if args.keyword:
        logger.info(f"🎯 [Phase 4] Single keyword scan mode: {args.keyword}")

        if args.device in ("mobile", "both"):
            result = scan_single_keyword(args.keyword, "mobile")
            print(f"📱 Mobile: {result['status']} (rank: {result['rank']})")

        if args.device in ("desktop", "both"):
            result = scan_single_keyword(args.keyword, "desktop")
            print(f"🖥️ Desktop: {result['status']} (rank: {result['rank']})")

        sys.exit(0)

    # [Phase 3] 기본값: 병렬 모드 (3개 브라우저)
    parallel_mode = not args.sequential

    check_naver_place_rank(parallel=parallel_mode, max_workers=args.workers)

    if not args.skip_reviews:
        collect_competitor_reviews()

    # [Phase 9] Place Scan Enrichment - 리뷰 메타 + SERP 기능 수집
    try:
        from place_scan_enrichment import run_enrichment
        logger.info("📊 [Phase 9] Running post-scan enrichment...")
        run_enrichment()
    except ImportError:
        logger.debug("place_scan_enrichment module not available, skipping")
    except Exception as e:
        logger.warning(f"⚠️ Post-scan enrichment failed (non-critical): {e}")
