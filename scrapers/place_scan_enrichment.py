#!/usr/bin/env python3
"""
Place Scan Enrichment - Post-scan data enrichment module
=========================================================

Place Sniper 스캔 완료 후 추가 데이터를 수집하는 모듈.
Selenium을 사용하여 API로 얻을 수 없는 데이터를 보강합니다.

Part 1: ReviewMetadataCollector - 경쟁사 리뷰 메타데이터 수집
Part 2: SerpFeatureDetector - 키워드별 SERP 기능 감지

Usage:
    # scraper_naver_place.py에서 자동 호출됨
    from place_scan_enrichment import run_enrichment
    run_enrichment()

    # 직접 실행
    python scrapers/place_scan_enrichment.py
    python scrapers/place_scan_enrichment.py --skip-reviews
    python scrapers/place_scan_enrichment.py --skip-serp
"""

import sys
import os
import time
import random
import json
import sqlite3
import logging
import re
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional
from urllib.parse import quote

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    StaleElementReferenceException,
    WebDriverException,
    TimeoutException,
)
from webdriver_manager.chrome import ChromeDriverManager

# Path setup
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from utils import logger

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Module logger
log = logging.getLogger(__name__)


# =============================================================================
# Constants
# =============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS_PATH = os.path.join(PROJECT_ROOT, 'config', 'targets.json')
KEYWORDS_PATH = os.path.join(PROJECT_ROOT, 'config', 'keywords.json')
BUSINESS_PROFILE_PATH = os.path.join(PROJECT_ROOT, 'config', 'business_profile.json')


# =============================================================================
# Browser Factory
# =============================================================================

def create_headless_browser() -> webdriver.Chrome:
    """Create a headless Chrome browser with anti-detection measures."""
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ko-KR")

    ua = random.choice(USER_AGENTS)
    options.add_argument(f"user-agent={ua}")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

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
    driver.implicitly_wait(5)

    return driver


# =============================================================================
# Part 1: Review Metadata Collector
# =============================================================================

class ReviewMetadataCollector:
    """
    네이버 플레이스에서 경쟁사 리뷰 메타데이터를 수집합니다.
    - 방문자리뷰 수, 블로그리뷰 수
    - 평균 별점
    - 사진 수
    - 사장님 댓글(응답) 여부
    """

    def __init__(self, driver: webdriver.Chrome):
        self.driver = driver
        self.db = DatabaseManager()
        self._ensure_table()

    def _ensure_table(self):
        """review_intelligence 테이블이 없으면 생성."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS review_intelligence (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        competitor_name TEXT NOT NULL,
                        place_id TEXT,
                        total_reviews INTEGER DEFAULT 0,
                        avg_rating REAL DEFAULT 0.0,
                        rating_distribution TEXT,
                        photo_review_count INTEGER DEFAULT 0,
                        photo_review_ratio REAL DEFAULT 0.0,
                        response_count INTEGER DEFAULT 0,
                        response_rate REAL DEFAULT 0.0,
                        new_reviews_since_last INTEGER DEFAULT 0,
                        suspicious_patterns TEXT,
                        suspicious_score INTEGER DEFAULT 0,
                        raw_data TEXT,
                        collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_review_intel_competitor
                    ON review_intelligence (competitor_name, collected_at)
                """)
                conn.commit()
        except Exception as e:
            log.error(f"review_intelligence table creation failed: {e}")

    def _load_targets(self) -> List[Dict[str, Any]]:
        """config/targets.json에서 naver_place URL이 있는 타겟 목록 로드."""
        targets = []
        try:
            if os.path.exists(TARGETS_PATH):
                with open(TARGETS_PATH, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for target in data.get('targets', []):
                    monitor_urls = target.get('monitor_urls', {})
                    naver_place_url = monitor_urls.get('naver_place', '')
                    if naver_place_url:
                        # Extract place_id from URL
                        place_id = self._extract_place_id(naver_place_url)
                        if place_id:
                            targets.append({
                                'name': target.get('name', 'Unknown'),
                                'place_id': place_id,
                                'url': naver_place_url,
                                'category': target.get('category', ''),
                                'priority': target.get('priority', 'Medium'),
                            })
        except Exception as e:
            log.error(f"Failed to load targets.json: {e}")
        return targets

    @staticmethod
    def _extract_place_id(url: str) -> Optional[str]:
        """네이버 플레이스 URL에서 place_id 추출."""
        # https://m.place.naver.com/hospital/13322046/home
        m = re.search(r'/(?:hospital|restaurant|place|cafe|beauty|school|accommodation)/(\d+)', url)
        if m:
            return m.group(1)
        # Fallback: just grab last numeric segment
        m = re.search(r'/(\d+)(?:/|$)', url)
        return m.group(1) if m else None

    def collect_single(self, target: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """단일 경쟁사의 리뷰 메타데이터 수집."""
        name = target['name']
        place_id = target['place_id']
        url = f"https://m.place.naver.com/hospital/{place_id}/home"

        log.info(f"  Collecting review metadata: {name} (place_id={place_id})")

        try:
            self.driver.get(url)
            time.sleep(random.uniform(3.0, 5.0))

            page_source = self.driver.page_source

            # --- Extract visitor review count ---
            visitor_reviews = 0
            m = re.search(r'방문자리뷰\s*(\d[\d,]*)', page_source)
            if m:
                visitor_reviews = int(m.group(1).replace(',', ''))
            else:
                # Alternative pattern: "리뷰 N개"
                m = re.search(r'리뷰\s*(\d[\d,]*)\s*개', page_source)
                if m:
                    visitor_reviews = int(m.group(1).replace(',', ''))

            # --- Extract blog review count ---
            blog_reviews = 0
            m = re.search(r'블로그리뷰\s*(\d[\d,]*)', page_source)
            if m:
                blog_reviews = int(m.group(1).replace(',', ''))

            total_reviews = visitor_reviews + blog_reviews

            # --- Extract rating ---
            rating = 0.0
            m = re.search(r'별점\s*([\d.]+)', page_source)
            if m:
                rating = float(m.group(1))
            else:
                # Try JSON-LD structured data
                try:
                    scripts = self.driver.find_elements(By.CSS_SELECTOR, 'script[type="application/ld+json"]')
                    for script in scripts:
                        try:
                            ld_data = json.loads(script.get_attribute('textContent') or '{}')
                            if 'aggregateRating' in ld_data:
                                rating = float(ld_data['aggregateRating'].get('ratingValue', 0))
                                if total_reviews == 0:
                                    total_reviews = int(ld_data['aggregateRating'].get('reviewCount', 0))
                                break
                        except (json.JSONDecodeError, ValueError):
                            continue
                except Exception:
                    pass

            # --- Extract photo count ---
            photo_count = 0
            m = re.search(r'사진\s*(\d[\d,]*)', page_source)
            if m:
                photo_count = int(m.group(1).replace(',', ''))
            else:
                # Try: "사진/동영상 N"
                m = re.search(r'(?:사진|포토)\s*(?:/\s*동영상)?\s*(\d[\d,]*)', page_source)
                if m:
                    photo_count = int(m.group(1).replace(',', ''))

            photo_ratio = (photo_count / total_reviews * 100) if total_reviews > 0 else 0.0

            # --- Check owner response (사장님 댓글) ---
            response_detected = False
            owner_response_count = 0

            if '사장님' in page_source and ('댓글' in page_source or '답글' in page_source):
                response_detected = True
                # Try to count response patterns
                owner_patterns = re.findall(r'사장님\s*(?:댓글|답글)', page_source)
                owner_response_count = len(owner_patterns) if owner_patterns else 1

            response_rate = 0.0
            if response_detected and visitor_reviews > 0:
                # Rough estimate: we can't get exact count from page overview
                # Just mark as having responses
                response_rate = min(owner_response_count / max(visitor_reviews, 1) * 100, 100.0)

            # --- Try JavaScript extraction as fallback ---
            if total_reviews == 0:
                try:
                    js_data = self.driver.execute_script("""
                        try {
                            var data = {};
                            // Try extracting from __NEXT_DATA__
                            if (window.__NEXT_DATA__) {
                                var pageProps = window.__NEXT_DATA__.props.pageProps || {};
                                var initialState = pageProps.initialState || {};
                                if (initialState.place) {
                                    var place = initialState.place;
                                    data.visitorReviewCount = place.visitorReviewCount || 0;
                                    data.blogReviewCount = place.blogReviewCount || 0;
                                    data.rating = place.rating || 0;
                                    data.imageCount = place.imageCount || 0;
                                }
                            }
                            return data;
                        } catch(e) {
                            return {};
                        }
                    """)
                    if js_data:
                        if js_data.get('visitorReviewCount', 0) > 0:
                            visitor_reviews = js_data['visitorReviewCount']
                        if js_data.get('blogReviewCount', 0) > 0:
                            blog_reviews = js_data['blogReviewCount']
                        total_reviews = visitor_reviews + blog_reviews
                        if js_data.get('rating', 0) > 0:
                            rating = float(js_data['rating'])
                        if js_data.get('imageCount', 0) > 0:
                            photo_count = js_data['imageCount']
                            photo_ratio = (photo_count / total_reviews * 100) if total_reviews > 0 else 0.0
                except Exception as e:
                    log.debug(f"  JS extraction failed for {name}: {e}")

            result = {
                'competitor_name': name,
                'place_id': place_id,
                'total_reviews': total_reviews,
                'visitor_reviews': visitor_reviews,
                'blog_reviews': blog_reviews,
                'avg_rating': round(rating, 2),
                'photo_review_count': photo_count,
                'photo_review_ratio': round(photo_ratio, 2),
                'response_count': owner_response_count,
                'response_rate': round(response_rate, 2),
            }

            log.info(
                f"    {name}: reviews={total_reviews} (visitor={visitor_reviews}, blog={blog_reviews}), "
                f"rating={rating:.1f}, photos={photo_count}, owner_response={'YES' if response_detected else 'NO'}"
            )

            return result

        except TimeoutException:
            log.warning(f"  Timeout loading page for {name}")
        except WebDriverException as e:
            log.warning(f"  WebDriver error for {name}: {e}")
        except Exception as e:
            log.error(f"  Unexpected error collecting {name}: {e}")
            log.debug(traceback.format_exc())

        return None

    def _save_result(self, result: Dict[str, Any]):
        """수집 결과를 review_intelligence 테이블에 UPSERT."""
        conn = None
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()

            raw_data = json.dumps(result, ensure_ascii=False)
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

            cursor.execute("""
                INSERT OR REPLACE INTO review_intelligence
                (competitor_name, place_id, total_reviews, avg_rating,
                 photo_review_count, photo_review_ratio,
                 response_count, response_rate, raw_data, collected_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result['competitor_name'],
                result['place_id'],
                result['total_reviews'],
                result['avg_rating'],
                result['photo_review_count'],
                result['photo_review_ratio'],
                result['response_count'],
                result['response_rate'],
                raw_data,
                now,
            ))
            conn.commit()
            log.debug(f"    Saved review metadata for {result['competitor_name']}")
        except Exception as e:
            log.error(f"  DB save failed for {result['competitor_name']}: {e}")
        finally:
            if conn:
                conn.close()

    def collect_all(self) -> Dict[str, Any]:
        """모든 타겟의 리뷰 메타데이터를 수집."""
        targets = self._load_targets()
        if not targets:
            log.warning("No targets with naver_place URLs found in targets.json")
            return {'collected': 0, 'failed': 0, 'targets': []}

        log.info(f"[Review Metadata] Collecting from {len(targets)} competitors...")

        collected = 0
        failed = 0
        results = []

        for i, target in enumerate(targets):
            log.info(f"  [{i+1}/{len(targets)}] {target['name']}")
            result = self.collect_single(target)

            if result:
                self._save_result(result)
                results.append(result)
                collected += 1
            else:
                failed += 1

            # Rate limit between targets
            if i < len(targets) - 1:
                delay = random.uniform(2.0, 4.0)
                time.sleep(delay)

        summary = {
            'collected': collected,
            'failed': failed,
            'targets': results,
        }

        log.info(f"[Review Metadata] Done: {collected} collected, {failed} failed")
        return summary


# =============================================================================
# Part 2: SERP Feature Detector
# =============================================================================

class SerpFeatureDetector:
    """
    네이버 검색 결과 페이지(SERP)의 기능 섹션을 감지합니다.
    - Place Pack, Blog/VIEW, News, Kin, Shopping, Ad, AI Briefing
    - 각 섹션에서 우리 업체의 노출 여부 확인
    """

    # SERP feature detection patterns (DOM-based)
    FEATURE_SELECTORS = {
        'place_pack': {
            'ids': ['loc-main-section', 'place-main-pack'],
            'attrs': [('data-cr-area', 'plc')],
            'class_patterns': ['sp_plc', 'place_bluelink', 'place-main-pack'],
            'text_markers': ['플레이스'],
        },
        'view_blog': {
            'ids': ['_blog', 'blog-main'],
            'attrs': [('data-cr-area', 'blg'), ('data-cr-area', 'view')],
            'class_patterns': ['sp_blog', 'view-search'],
            'text_markers': ['VIEW'],
        },
        'news': {
            'ids': ['_news', 'news-main'],
            'attrs': [('data-cr-area', 'nws')],
            'class_patterns': ['sp_nws'],
            'text_markers': [],
        },
        'kin': {
            'ids': ['_kin', 'kin-main'],
            'attrs': [('data-cr-area', 'kin')],
            'class_patterns': ['sp_kin'],
            'text_markers': ['지식인'],
        },
        'shopping': {
            'ids': ['_shopping', 'shopping-main'],
            'attrs': [('data-cr-area', 'shp')],
            'class_patterns': ['sp_shp'],
            'text_markers': [],
        },
        'ad_top': {
            'ids': ['sp_ad', 'ad_area'],
            'attrs': [('data-cr-area', 'sad'), ('data-cr-area', 'psa')],
            'class_patterns': ['ad_area', 'sp_ad', 'sp_psa'],
            'text_markers': [],
        },
        'ai_briefing': {
            'ids': ['ai_brief', '_ai_briefing'],
            'attrs': [('data-cr-area', 'aib')],
            'class_patterns': ['ai_brief', 'sp_ai_brief', 'sp_ai'],
            'text_markers': ['AI 추천', 'AI 브리핑'],
        },
    }

    def __init__(self, driver: webdriver.Chrome = None, *, use_camoufox: bool = True):
        """
        SerpFeatureDetector.

        Args:
            driver: Selenium driver (use_camoufox=False일 때 필수)
            use_camoufox: True면 Camoufox sync engine 사용 (캡차 우회).
                          기본값 True. False로 두면 기존 Selenium 사용.
        """
        self.driver = driver
        self.use_camoufox = use_camoufox
        self._camoufox_fetcher = None  # lazy
        self.db = DatabaseManager()
        self._ensure_table()
        self._load_keywords()
        self._load_business_identifiers()

    def _get_page_html(self, url: str) -> Optional[str]:
        """엔진별 페이지 fetch — Camoufox 우선."""
        if self.use_camoufox:
            if self._camoufox_fetcher is None:
                from scrapers.camoufox_engine import CamoufoxFetcher
                self._camoufox_fetcher = CamoufoxFetcher(headless=True).__enter__()
            html, blocked = self._camoufox_fetcher.fetch_with_retry(url, max_attempts=2)
            if blocked:
                return None
            return html
        # Fallback: Selenium driver
        if not self.driver:
            log.error("Neither camoufox nor selenium driver available")
            return None
        self.driver.get(url)
        time.sleep(random.uniform(2.0, 3.0))
        return self.driver.page_source

    def close_camoufox(self):
        """Camoufox 정리."""
        if self._camoufox_fetcher is not None:
            try:
                self._camoufox_fetcher.__exit__(None, None, None)
            except Exception:
                pass
            self._camoufox_fetcher = None

    def _ensure_table(self):
        """serp_features 테이블이 없으면 생성."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS serp_features (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        has_place_pack INTEGER DEFAULT 0,
                        place_pack_count INTEGER DEFAULT 0,
                        has_view_tab INTEGER DEFAULT 0,
                        has_blog_section INTEGER DEFAULT 0,
                        has_news_section INTEGER DEFAULT 0,
                        has_kin_section INTEGER DEFAULT 0,
                        has_shopping_section INTEGER DEFAULT 0,
                        has_ad_top INTEGER DEFAULT 0,
                        ad_count INTEGER DEFAULT 0,
                        has_ai_briefing INTEGER DEFAULT 0,
                        our_visibility TEXT DEFAULT '{}',
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_serp_features_keyword_date
                    ON serp_features (keyword, scanned_at)
                """)
                conn.commit()
        except Exception as e:
            log.error(f"serp_features table creation failed: {e}")

    def _load_keywords(self):
        """config/keywords.json에서 모든 키워드 로드."""
        self.keywords = []
        try:
            if os.path.exists(KEYWORDS_PATH):
                with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                for category in ['naver_place', 'blog_seo']:
                    self.keywords.extend(kw_data.get(category, []))
                # Deduplicate while preserving order
                self.keywords = list(dict.fromkeys(self.keywords))
        except Exception as e:
            log.error(f"Failed to load keywords.json: {e}")

        if not self.keywords:
            log.warning("No keywords loaded for SERP detection")
        else:
            log.info(f"Loaded {len(self.keywords)} keywords for SERP detection")

    def _load_business_identifiers(self):
        """config/business_profile.json에서 우리 업체 식별자 로드."""
        self.our_identifiers = []
        try:
            if os.path.exists(BUSINESS_PROFILE_PATH):
                with open(BUSINESS_PROFILE_PATH, 'r', encoding='utf-8') as f:
                    profile = json.load(f)
                business = profile.get('business', {})
                for key in ['name', 'short_name', 'english_name']:
                    val = business.get(key)
                    if val:
                        self.our_identifiers.append(val)
        except Exception as e:
            log.warning(f"Failed to load business_profile.json: {e}")

        if not self.our_identifiers:
            self.our_identifiers = ["규림한의원", "규림", "kyurim"]
            log.warning(f"Using default business identifiers: {self.our_identifiers}")

    def _detect_feature(self, page_source: str, feature_key: str) -> bool:
        """페이지 소스에서 특정 SERP 기능 존재 여부 감지."""
        patterns = self.FEATURE_SELECTORS.get(feature_key, {})

        # Check by ID
        for id_val in patterns.get('ids', []):
            if f'id="{id_val}"' in page_source or f"id='{id_val}'" in page_source:
                return True

        # Check by data attributes
        for attr_name, attr_val in patterns.get('attrs', []):
            if f'{attr_name}="{attr_val}"' in page_source:
                return True

        # Check by class patterns
        for cls in patterns.get('class_patterns', []):
            if f'class="{cls}"' in page_source or f'class="{cls} ' in page_source or f' {cls}"' in page_source:
                return True
            # Also check partial class matching
            if f'"{cls}"' in page_source or f"'{cls}'" in page_source:
                return True

        # Check by text markers (more expensive, do last)
        for marker in patterns.get('text_markers', []):
            if marker in page_source:
                return True

        return False

    def _count_place_items(self, page_source: str) -> int:
        """Place Pack 내 항목 수를 추정."""
        count = 0
        try:
            # Find the place section and count list items via Selenium
            place_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-cr-area="plc"] li')
            if place_elements:
                count = len(place_elements)
            else:
                # Fallback: try other selectors
                for selector in ['li.place_bluelink', 'a.place_bluelink', '.sp_plc li']:
                    items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                    if items:
                        count = len(items)
                        break
        except Exception:
            pass

        # Fallback: regex count
        if count == 0:
            # Count place-like list items via pattern
            place_matches = re.findall(r'place_bluelink', page_source)
            count = len(place_matches) if place_matches else 0

        return count

    def _count_ads(self, page_source: str) -> int:
        """광고 항목 수를 추정."""
        count = 0
        try:
            for selector in ['[data-cr-area="psa"] li', '[data-cr-area="sad"] li', '.ad_area li']:
                items = self.driver.find_elements(By.CSS_SELECTOR, selector)
                if items:
                    count = len(items)
                    break
        except Exception:
            pass
        return count

    def _check_our_visibility(self, page_source: str) -> Dict[str, bool]:
        """각 SERP 섹션에서 우리 업체 노출 여부 확인.

        Camoufox 모드에선 driver가 없으므로 page_source의 data-cr-area 블록을
        정규식으로 추출. Selenium 모드에선 기존 방식 유지.
        """
        visibility = {
            'place': False,
            'blog': False,
            'news': False,
            'kin': False,
            'shopping': False,
            'ad': False,
            'ai_briefing': False,
        }

        section_area_map = {
            'place': ['plc'],
            'blog': ['blg', 'view'],
            'news': ['nws'],
            'kin': ['kin'],
            'shopping': ['shp'],
            'ad': ['psa', 'sad'],
            'ai_briefing': ['aib'],
        }

        # Camoufox 모드: page_source에서 정규식 추출
        if self.use_camoufox or self.driver is None:
            import re as _re
            html_low = page_source.lower()
            ids_low = [i.lower() for i in self.our_identifiers]
            for section_name, area_codes in section_area_map.items():
                for area_code in area_codes:
                    # data-cr-area="<code>" ... </*> 블록 단순 캡처 (greedy 회피)
                    pattern = _re.compile(
                        rf'data-cr-area=["\']{area_code}["\']([^>]*>)(.*?)(?=data-cr-area=|</body>)',
                        _re.IGNORECASE | _re.DOTALL,
                    )
                    m = pattern.search(html_low)
                    if not m:
                        continue
                    block_text = m.group(2)
                    for identifier in ids_low:
                        if identifier and identifier in block_text:
                            visibility[section_name] = True
                            break
                    if visibility[section_name]:
                        break
            return visibility

        # Selenium 모드 (기존)
        for section_name, area_codes in section_area_map.items():
            for area_code in area_codes:
                try:
                    section_el = self.driver.find_element(
                        By.CSS_SELECTOR, f'[data-cr-area="{area_code}"]'
                    )
                    section_text = section_el.text.lower()
                    for identifier in self.our_identifiers:
                        if identifier.lower() in section_text:
                            visibility[section_name] = True
                            break
                except (NoSuchElementException, StaleElementReferenceException):
                    pass

                if visibility[section_name]:
                    break

        return visibility

    def _extract_ai_briefing(self, page_source: str) -> Dict[str, Any]:
        """AI 브리핑 박스 텍스트 + 인용 출처 추출 (2026 신규).

        네이버 Cue: 종료 후 AI 브리핑이 통합검색 상단 점유. 우리 업체가
        인용되는지 여부가 가장 강한 노출 신호.
        """
        import re as _re
        info = {"text": "", "sources": [], "includes_us": False}
        # data-cr-area="aib" 블록 또는 'AI 브리핑' 마커 인근
        # 1) data-cr-area 블록
        m = _re.search(
            r'data-cr-area=["\']aib["\'][^>]*>(.*?)(?=data-cr-area=|</body>)',
            page_source, _re.IGNORECASE | _re.DOTALL,
        )
        block = m.group(1) if m else ""
        # 2) 폴백: 'AI 브리핑' 또는 'AI 추천' 인근 1500자
        if not block:
            m2 = _re.search(r'(AI\s*브리핑|AI\s*추천)(.{0,1500})', page_source, _re.DOTALL)
            block = m2.group(2) if m2 else ""
        if not block:
            return info
        # 텍스트만 추출 (HTML 태그 제거)
        text = _re.sub(r'<[^>]+>', ' ', block)
        text = _re.sub(r'\s+', ' ', text).strip()[:1500]
        info["text"] = text
        # 출처 URL 추출 (인용 링크 → naver redirect or direct)
        urls = _re.findall(r'href=["\'](https?://[^"\']+)["\']', block)
        info["sources"] = list(dict.fromkeys(urls))[:10]
        # 우리 업체 인용 여부
        text_low = text.lower()
        for ident in self.our_identifiers:
            if ident and ident.lower() in text_low:
                info["includes_us"] = True
                break
        return info

    def _extract_place_clips(self, page_source: str) -> Dict[str, Any]:
        """MY플레이스 클립 (2026.4 출시) 카운트 + URL + source_type 추출.

        2026-04-14 네이버 클립 × MY플레이스 통합으로 탭 4→3.
        클립이 (a) 자동 리뷰 변환 (auto_from_review) 또는 (b) 직접 업로드 (manual_upload)
        인지 구분 — 가중치 다를 가능성.

        [R3-4] MY플레이스 ↔ 일반 클립 출처 분리 (2026-04-14 시행 후속)
        - my_place_count: '마이플레이스' / 'MY플레이스 후기' 마크 검출 클립
        - general_count: 일반 크리에이터 업로드 클립
        - my_place_link_rate: my_place / total
        """
        import re as _re
        info = {
            "count": 0, "urls": [], "source_type": "unknown",
            "my_place_count": 0, "general_count": 0, "my_place_link_rate": 0.0,
        }
        clip_urls = _re.findall(
            r'(https?://[^"\'\s]*(?:place\.naver\.com|m\.place\.naver\.com)[^"\'\s]*?(?:clips?|video)[^"\'\s]*)',
            page_source, _re.IGNORECASE,
        )
        clip_blocks = _re.findall(r'data-cr-area=["\'](?:clip|cliP|clp)', page_source)
        info["count"] = max(len(set(clip_urls)), len(clip_blocks))
        info["urls"] = list(dict.fromkeys(clip_urls))[:20]

        # source_type 휴리스틱
        # auto_from_review: 'review_clip', 'auto_clip', '리뷰 클립', 'autoplay_review'
        # manual_upload: 'upload_clip', 'creator_clip', '직접 업로드'
        page_low = page_source.lower()
        auto_markers = ('review_clip', 'auto_clip', '리뷰 클립', 'autoplay_review',
                        'reviewtoclip', 'auto-from-review')
        manual_markers = ('upload_clip', 'creator_clip', '직접 업로드',
                          'user_uploaded', 'manual_clip')
        auto_hits = sum(1 for m in auto_markers if m.lower() in page_low)
        manual_hits = sum(1 for m in manual_markers if m.lower() in page_low)
        if auto_hits > manual_hits and auto_hits > 0:
            info["source_type"] = "auto_from_review"
        elif manual_hits > 0:
            info["source_type"] = "manual_upload"
        elif info["count"] > 0:
            info["source_type"] = "mixed"

        # [R3-4] MY플레이스 ↔ 일반 클립 분리 (2026-04-14 시행)
        my_place_markers = (
            'my플레이스 후기', 'myplace', '마이플레이스', 'my_place_clip',
            'myplace_clip', 'myplaceclip', 'mypl_clip', 'fromMyplace',
        )
        my_place_hits = sum(
            page_low.count(m.lower()) for m in my_place_markers
        )
        info["my_place_count"] = min(my_place_hits, info["count"])
        info["general_count"] = max(0, info["count"] - info["my_place_count"])
        if info["count"] > 0:
            info["my_place_link_rate"] = round(
                info["my_place_count"] / info["count"], 3
            )
        return info

    def analyze_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """단일 키워드의 SERP 기능 분석."""
        encoded_kw = quote(keyword)
        url = f"https://search.naver.com/search.naver?query={encoded_kw}"

        log.info(f"  Analyzing SERP: {keyword} (engine={'camoufox' if self.use_camoufox else 'selenium'})")

        try:
            page_source = self._get_page_html(url)
            if not page_source:
                log.warning(f"  [{keyword}] Captcha/block detected or fetch failed, skipping")
                return None

            # Detect features
            has_place = self._detect_feature(page_source, 'place_pack')
            has_view = self._detect_feature(page_source, 'view_blog')
            has_news = self._detect_feature(page_source, 'news')
            has_kin = self._detect_feature(page_source, 'kin')
            has_shopping = self._detect_feature(page_source, 'shopping')
            has_ad = self._detect_feature(page_source, 'ad_top')
            has_ai = self._detect_feature(page_source, 'ai_briefing')

            place_count = self._count_place_items(page_source) if has_place else 0
            ad_count = self._count_ads(page_source) if has_ad else 0

            # [2026 신규] AI 브리핑 + MY플레이스 클립
            ai_brief = self._extract_ai_briefing(page_source) if has_ai else {"text": "", "sources": [], "includes_us": False}
            clips = self._extract_place_clips(page_source)

            # Check our visibility in each section
            visibility = self._check_our_visibility(page_source)

            features_found = []
            if has_place:
                features_found.append(f"Place({place_count})")
            if has_view:
                features_found.append("VIEW/Blog")
            if has_news:
                features_found.append("News")
            if has_kin:
                features_found.append("Kin")
            if has_shopping:
                features_found.append("Shopping")
            if has_ad:
                features_found.append(f"Ad({ad_count})")
            if has_ai:
                features_found.append("AI Briefing")

            visible_in = [k for k, v in visibility.items() if v]

            log.info(
                f"    Features: [{', '.join(features_found) if features_found else 'none'}] "
                f"| Our visibility: [{', '.join(visible_in) if visible_in else 'none'}]"
            )

            result = {
                'keyword': keyword,
                'has_place_pack': 1 if has_place else 0,
                'place_pack_count': place_count,
                'has_view_tab': 1 if has_view else 0,
                'has_blog_section': 1 if has_view else 0,
                'has_news_section': 1 if has_news else 0,
                'has_kin_section': 1 if has_kin else 0,
                'has_shopping_section': 1 if has_shopping else 0,
                'has_ad_top': 1 if has_ad else 0,
                'ad_count': ad_count,
                'has_ai_briefing': 1 if has_ai else 0,
                'our_visibility': json.dumps(visibility, ensure_ascii=False),
                'scanned_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                # [2026 신규]
                'ai_briefing_text': ai_brief["text"],
                'ai_briefing_sources': json.dumps(ai_brief["sources"], ensure_ascii=False),
                'ai_briefing_includes_us': 1 if ai_brief["includes_us"] else 0,
                'place_clip_count': clips["count"],
                'place_clip_urls': json.dumps(clips["urls"], ensure_ascii=False),
                'place_clip_source_type': clips.get("source_type", "unknown"),
                # [R3-4] MY플레이스 ↔ 일반 클립 분리
                'clip_source_my_place': clips.get("my_place_count", 0),
                'clip_source_general': clips.get("general_count", 0),
                'clip_my_place_link_rate': clips.get("my_place_link_rate", 0.0),
            }
            log.info(
                f"    AI Briefing: {'있음' if has_ai else '없음'}"
                f"{' (우리 인용!)' if ai_brief['includes_us'] else ''}"
                f" | 클립: {clips['count']}개"
            )

            return result

        except TimeoutException:
            log.warning(f"  [{keyword}] Page load timeout")
        except WebDriverException as e:
            log.warning(f"  [{keyword}] WebDriver error: {e}")
        except Exception as e:
            log.error(f"  [{keyword}] Unexpected error: {e}")
            log.debug(traceback.format_exc())

        return None

    def _save_result(self, result: Dict[str, Any]):
        """SERP 분석 결과를 serp_features 테이블에 저장 (2026 신규 컬럼 포함)."""
        conn = None
        try:
            conn = sqlite3.connect(self.db.db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO serp_features
                (keyword, has_place_pack, place_pack_count, has_view_tab,
                 has_blog_section, has_news_section, has_kin_section,
                 has_shopping_section, has_ad_top, ad_count,
                 has_ai_briefing, our_visibility, scanned_at,
                 ai_briefing_text, ai_briefing_sources, ai_briefing_includes_us,
                 place_clip_count, place_clip_urls, place_clip_source_type,
                 clip_source_my_place, clip_source_general, clip_my_place_link_rate)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result['keyword'],
                result['has_place_pack'],
                result['place_pack_count'],
                result['has_view_tab'],
                result['has_blog_section'],
                result['has_news_section'],
                result['has_kin_section'],
                result['has_shopping_section'],
                result['has_ad_top'],
                result['ad_count'],
                result['has_ai_briefing'],
                result['our_visibility'],
                result['scanned_at'],
                result.get('ai_briefing_text', ''),
                result.get('ai_briefing_sources', '[]'),
                result.get('ai_briefing_includes_us', 0),
                result.get('place_clip_count', 0),
                result.get('place_clip_urls', '[]'),
                result.get('place_clip_source_type', 'unknown'),
                result.get('clip_source_my_place', 0),
                result.get('clip_source_general', 0),
                result.get('clip_my_place_link_rate', 0.0),
            ))
            conn.commit()
            log.debug(f"    Saved SERP features for '{result['keyword']}'")
        except Exception as e:
            log.error(f"  DB save failed for '{result['keyword']}': {e}")
        finally:
            if conn:
                conn.close()

    def analyze_all(self) -> Dict[str, Any]:
        """모든 키워드의 SERP 기능을 분석."""
        if not self.keywords:
            log.warning("No keywords to analyze")
            return {'analyzed': 0, 'failed': 0, 'results': []}

        log.info(f"[SERP Features] Analyzing {len(self.keywords)} keywords...")

        analyzed = 0
        failed = 0
        results = []

        for i, keyword in enumerate(self.keywords):
            log.info(f"  [{i+1}/{len(self.keywords)}] {keyword}")
            result = self.analyze_keyword(keyword)

            if result:
                self._save_result(result)
                results.append(result)
                analyzed += 1
            else:
                failed += 1

            # Rate limit: 2s between keywords
            if i < len(self.keywords) - 1:
                delay = random.uniform(2.0, 3.0)
                time.sleep(delay)

        summary = {
            'analyzed': analyzed,
            'failed': failed,
            'results': results,
        }

        log.info(f"[SERP Features] Done: {analyzed} analyzed, {failed} failed")
        return summary


# =============================================================================
# Part 3: Entry Point
# =============================================================================

def run_enrichment(skip_reviews: bool = False, skip_serp: bool = False) -> Dict[str, Any]:
    """
    Place Sniper 스캔 후 실행되는 데이터 보강 모듈.

    Args:
        skip_reviews: True이면 리뷰 메타데이터 수집을 건너뜀
        skip_serp: True이면 SERP 기능 감지를 건너뜀

    Returns:
        dict with 'reviews' and 'serp' summary results
    """
    if skip_reviews and skip_serp:
        log.info("[Enrichment] Both parts skipped, nothing to do")
        return {'reviews': None, 'serp': None}

    log.info("=" * 60)
    log.info("[Enrichment] Starting post-scan data enrichment...")
    log.info("=" * 60)

    start_time = time.time()
    driver = None
    review_summary = None
    serp_summary = None

    try:
        # Create ONE shared headless browser
        log.info("[Enrichment] Creating headless Chrome browser...")
        driver = create_headless_browser()
        log.info("[Enrichment] Browser ready")

        # Part 1: Review Metadata Collection
        if not skip_reviews:
            log.info("")
            log.info("-" * 50)
            log.info("[Part 1/2] Review Metadata Collection")
            log.info("-" * 50)
            try:
                collector = ReviewMetadataCollector(driver)
                review_summary = collector.collect_all()
            except Exception as e:
                log.error(f"[Part 1] Review metadata collection failed: {e}")
                log.debug(traceback.format_exc())
                review_summary = {'collected': 0, 'failed': 0, 'error': str(e)}
        else:
            log.info("[Part 1/2] Review metadata collection SKIPPED")

        # Part 2: SERP Feature Detection (Camoufox 우선, Selenium 폴백)
        if not skip_serp:
            log.info("")
            log.info("-" * 50)
            log.info("[Part 2/2] SERP Feature Detection (Camoufox)")
            log.info("-" * 50)
            detector = None
            try:
                # Camoufox 모드: driver 불필요, 자체 Firefox launch
                detector = SerpFeatureDetector(driver=driver, use_camoufox=True)
                serp_summary = detector.analyze_all()
            except Exception as e:
                log.error(f"[Part 2] SERP feature detection failed: {e}")
                log.debug(traceback.format_exc())
                serp_summary = {'analyzed': 0, 'failed': 0, 'error': str(e)}
            finally:
                if detector is not None:
                    try:
                        detector.close_camoufox()
                    except Exception:
                        pass
        else:
            log.info("[Part 2/2] SERP feature detection SKIPPED")

    except WebDriverException as e:
        log.error(f"[Enrichment] Browser creation failed: {e}")
        return {'reviews': None, 'serp': None, 'error': str(e)}
    except Exception as e:
        log.error(f"[Enrichment] Unexpected error: {e}")
        log.debug(traceback.format_exc())
        return {'reviews': review_summary, 'serp': serp_summary, 'error': str(e)}
    finally:
        # Clean up browser
        if driver:
            try:
                driver.quit()
                log.info("[Enrichment] Browser closed")
            except Exception as e:
                log.debug(f"Browser quit error (non-critical): {e}")

    elapsed = time.time() - start_time

    log.info("")
    log.info("=" * 60)
    log.info(f"[Enrichment] Complete in {elapsed:.1f}s")
    if review_summary:
        log.info(f"  Reviews: {review_summary.get('collected', 0)} collected, {review_summary.get('failed', 0)} failed")
    if serp_summary:
        log.info(f"  SERP: {serp_summary.get('analyzed', 0)} analyzed, {serp_summary.get('failed', 0)} failed")
    log.info("=" * 60)

    return {
        'reviews': review_summary,
        'serp': serp_summary,
        'elapsed_seconds': round(elapsed, 1),
    }


# =============================================================================
# CLI Entry Point
# =============================================================================

if __name__ == '__main__':
    import argparse

    # Configure logging for standalone execution
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )

    parser = argparse.ArgumentParser(description='Place Scan Enrichment - Post-scan data collection')
    parser.add_argument('--skip-reviews', action='store_true', help='Skip review metadata collection')
    parser.add_argument('--skip-serp', action='store_true', help='Skip SERP feature detection')
    args = parser.parse_args()

    result = run_enrichment(
        skip_reviews=args.skip_reviews,
        skip_serp=args.skip_serp,
    )

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}")
