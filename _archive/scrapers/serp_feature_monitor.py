#!/usr/bin/env python3
"""
SERP Feature Monitor - Naver SERP Feature Detection
====================================================

Monitors what SERP features appear for each keyword on Naver search.
- Detects: Place Pack, VIEW/Blog, News, Kin, Shopping, Ads, AI Briefing
- Checks our clinic visibility across each section
- User-Agent rotation, rate limiting (1.5s between requests)
- Results stored in serp_features table

Usage:
    python scrapers/serp_feature_monitor.py
"""

import sys
import os
import time
import json
import logging
import random
import re
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import quote

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

import requests
from bs4 import BeautifulSoup

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# ============================================================================
# User-Agent Rotation Pool
# ============================================================================

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36 Edg/129.0.0.0",
]

# ============================================================================
# SERP Feature Detection Patterns
# ============================================================================

FEATURE_PATTERNS = {
    "place_pack": {
        "classes": ["place-main-pack-top", "sc_new sp_plc", "place_bluelink", "sp_place"],
        "ids": ["place-main-pack", "loc-main-pack"],
        "attrs": [("data-cr-area", "plc")],
    },
    "view_blog": {
        "classes": ["view-search", "sc_new sp_blog", "sp_blog"],
        "ids": ["_blog", "blog-main"],
        "attrs": [("data-cr-area", "blg"), ("data-cr-area", "view")],
    },
    "news": {
        "classes": ["sc_new sp_nws", "sp_nws"],
        "ids": ["_news", "news-main"],
        "attrs": [("data-cr-area", "nws")],
    },
    "kin": {
        "classes": ["sc_new sp_kin", "sp_kin"],
        "ids": ["_kin", "kin-main"],
        "attrs": [("data-cr-area", "kin")],
    },
    "shopping": {
        "classes": ["sc_new sp_shp", "sp_shp"],
        "ids": ["_shopping", "shopping-main"],
        "attrs": [("data-cr-area", "shp")],
    },
    "ad_top": {
        "classes": ["ad_area", "sp_ad", "sc_new sp_psa"],
        "ids": ["ad_area", "_ad"],
        "attrs": [("data-cr-area", "psa")],
    },
    "ai_briefing": {
        "classes": ["ai_brief", "sc_new sp_ai", "sp_ai_brief"],
        "ids": ["ai_brief", "_ai_briefing"],
        "attrs": [("data-cr-area", "aib")],
    },
}


class SerpFeatureMonitor:
    """Monitors SERP features for each keyword on Naver search."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_keywords()
        self._load_business_identifiers()
        self._last_request_time = 0.0
        self.session = requests.Session()

    def _ensure_table(self):
        """Create serp_features table if it doesn't exist."""
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
            logger.error(f"serp_features table creation failed: {e}")
            raise
        logger.info("serp_features table ready")

    def _load_keywords(self):
        """Load keywords from config/keywords.json (all categories)."""
        self.keywords = []
        keywords_path = os.path.join(project_root, 'config', 'keywords.json')

        try:
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                # Merge all keyword categories
                for category in ['naver_place', 'blog_seo']:
                    self.keywords.extend(kw_data.get(category, []))
                # Deduplicate while preserving order
                self.keywords = list(dict.fromkeys(self.keywords))
        except Exception as e:
            logger.error(f"Failed to load keywords.json: {e}")

        if not self.keywords:
            logger.warning("No keywords loaded. Check config/keywords.json.")

        logger.info(f"Loaded {len(self.keywords)} keywords for SERP monitoring")

    def _load_business_identifiers(self):
        """Load our clinic identifiers from config/business_profile.json."""
        self.our_identifiers = []
        profile_path = os.path.join(project_root, 'config', 'business_profile.json')

        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)

                business = profile.get('business', {})
                for key in ['name', 'short_name', 'english_name']:
                    val = business.get(key)
                    if val:
                        self.our_identifiers.append(val)

                exclude_names = profile.get('competitors', {}).get('exclude_names', [])
                self.our_identifiers.extend(exclude_names)

                # Deduplicate
                seen = set()
                unique = []
                for ident in self.our_identifiers:
                    low = ident.lower()
                    if low and low not in seen:
                        seen.add(low)
                        unique.append(ident)
                self.our_identifiers = unique
        except Exception as e:
            logger.warning(f"Failed to load business_profile.json: {e}")

        if not self.our_identifiers:
            self.our_identifiers = ["규림한의원", "규림", "kyurim"]
            logger.warning(f"Using default identifiers: {self.our_identifiers}")
        else:
            logger.info(f"Business identifiers: {self.our_identifiers}")

    def _rate_limit(self):
        """Enforce 1.5s minimum between requests."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(1.5, 2.5)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> Dict[str, str]:
        """Return headers with a random User-Agent."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
        }

    def _fetch_search_page(self, keyword: str) -> Optional[BeautifulSoup]:
        """Fetch Naver main search results page for a keyword."""
        self._rate_limit()

        encoded_kw = quote(keyword)
        url = f"https://search.naver.com/search.naver?query={encoded_kw}"

        try:
            response = self.session.get(
                url,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()

            # Captcha/block detection
            page_lower = response.text.lower()
            if 'captcha' in page_lower or 'unusual traffic' in page_lower:
                logger.warning(f"[{keyword}] Captcha/block detected!")
                return None

            return BeautifulSoup(response.text, 'html.parser')

        except requests.exceptions.Timeout:
            logger.error(f"[{keyword}] Request timeout")
        except requests.exceptions.HTTPError as e:
            logger.error(f"[{keyword}] HTTP error: {e}")
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[{keyword}] Connection error: {e}")
        except requests.exceptions.RequestException as e:
            logger.error(f"[{keyword}] Request error: {e}")

        return None

    def _detect_feature(self, soup: BeautifulSoup, feature_key: str) -> bool:
        """Detect whether a specific SERP feature is present."""
        patterns = FEATURE_PATTERNS.get(feature_key, {})

        # Check by CSS class
        for cls_str in patterns.get("classes", []):
            # Handle compound classes like "sc_new sp_plc"
            class_parts = cls_str.split()
            if len(class_parts) > 1:
                found = soup.find(class_=lambda c: c and all(part in c for part in class_parts))
            else:
                found = soup.find(class_=re.compile(re.escape(cls_str)))
            if found:
                return True

        # Check by ID
        for id_str in patterns.get("ids", []):
            if soup.find(id=id_str):
                return True

        # Check by data attributes
        for attr_name, attr_val in patterns.get("attrs", []):
            if soup.find(attrs={attr_name: attr_val}):
                return True

        return False

    def _count_place_pack_items(self, soup: BeautifulSoup) -> int:
        """Count the number of items in the Place Pack section."""
        count = 0

        # Try multiple selectors for place items
        place_selectors = [
            'li.place_bluelink',
            'a.place_bluelink',
            'div[class*="place"] li',
            '.sc_new.sp_plc li',
        ]

        for selector in place_selectors:
            items = soup.select(selector)
            if items:
                count = len(items)
                break

        # Fallback: look for place-related data attributes
        if count == 0:
            place_section = soup.find(attrs={"data-cr-area": "plc"})
            if place_section:
                items = place_section.find_all('li')
                count = len(items) if items else 0

        return count

    def _count_ads(self, soup: BeautifulSoup) -> int:
        """Count visible ad items on the page."""
        ad_count = 0

        # Try multiple ad selectors
        ad_selectors = [
            '.ad_area li',
            '.sp_ad li',
            '[data-cr-area="psa"] li',
            '.sc_new.sp_psa li',
        ]

        for selector in ad_selectors:
            items = soup.select(selector)
            if items:
                ad_count = len(items)
                break

        # Fallback: count elements with "ad" related attributes
        if ad_count == 0:
            ad_links = soup.find_all('a', class_=re.compile(r'ad_|_ad|sp_ad'))
            ad_count = len(ad_links) if ad_links else 0

        return ad_count

    def _check_our_visibility(self, soup: BeautifulSoup) -> Dict[str, bool]:
        """Check if our clinic appears in each SERP section."""
        visibility = {
            "place": False,
            "blog": False,
            "news": False,
            "kin": False,
            "shopping": False,
            "ad": False,
            "ai_briefing": False,
        }

        # Map section names to their detection areas
        section_map = {
            "place": ["plc"],
            "blog": ["blg", "view"],
            "news": ["nws"],
            "kin": ["kin"],
            "shopping": ["shp"],
            "ad": ["psa"],
            "ai_briefing": ["aib"],
        }

        for section_name, area_codes in section_map.items():
            for area_code in area_codes:
                section_el = soup.find(attrs={"data-cr-area": area_code})
                if section_el:
                    section_text = section_el.get_text(separator=' ').lower()
                    for identifier in self.our_identifiers:
                        if identifier.lower() in section_text:
                            visibility[section_name] = True
                            break

            # If not found by data-cr-area, try broader text search within class-based sections
            if not visibility[section_name]:
                class_patterns_map = {
                    "place": ["sp_plc", "place_bluelink"],
                    "blog": ["sp_blog", "view-search"],
                    "news": ["sp_nws"],
                    "kin": ["sp_kin"],
                    "shopping": ["sp_shp"],
                    "ad": ["sp_ad", "ad_area"],
                    "ai_briefing": ["sp_ai", "ai_brief"],
                }
                for cls in class_patterns_map.get(section_name, []):
                    el = soup.find(class_=re.compile(re.escape(cls)))
                    if el:
                        el_text = el.get_text(separator=' ').lower()
                        for identifier in self.our_identifiers:
                            if identifier.lower() in el_text:
                                visibility[section_name] = True
                                break
                    if visibility[section_name]:
                        break

        return visibility

    def analyze_keyword(self, keyword: str) -> Optional[Dict[str, Any]]:
        """Analyze SERP features for a single keyword."""
        soup = self._fetch_search_page(keyword)
        if not soup:
            return None

        # Detect features
        has_place_pack = self._detect_feature(soup, "place_pack")
        has_view_blog = self._detect_feature(soup, "view_blog")
        has_news = self._detect_feature(soup, "news")
        has_kin = self._detect_feature(soup, "kin")
        has_shopping = self._detect_feature(soup, "shopping")
        has_ad_top = self._detect_feature(soup, "ad_top")
        has_ai_briefing = self._detect_feature(soup, "ai_briefing")

        # Counts
        place_pack_count = self._count_place_pack_items(soup) if has_place_pack else 0
        ad_count = self._count_ads(soup) if has_ad_top else 0

        # Our visibility
        our_visibility = self._check_our_visibility(soup)

        result = {
            "keyword": keyword,
            "has_place_pack": 1 if has_place_pack else 0,
            "place_pack_count": place_pack_count,
            "has_view_tab": 1 if has_view_blog else 0,
            "has_blog_section": 1 if has_view_blog else 0,
            "has_news_section": 1 if has_news else 0,
            "has_kin_section": 1 if has_kin else 0,
            "has_shopping_section": 1 if has_shopping else 0,
            "has_ad_top": 1 if has_ad_top else 0,
            "ad_count": ad_count,
            "has_ai_briefing": 1 if has_ai_briefing else 0,
            "our_visibility": our_visibility,
            "scanned_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        return result

    def _save_result(self, result: Dict[str, Any]):
        """Save analysis result to DB."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO serp_features
                    (keyword, has_place_pack, place_pack_count, has_view_tab,
                     has_blog_section, has_news_section, has_kin_section,
                     has_shopping_section, has_ad_top, ad_count, has_ai_briefing,
                     our_visibility, scanned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    json.dumps(result['our_visibility'], ensure_ascii=False),
                    result['scanned_at'],
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB save error [{result.get('keyword')}]: {e}")
            logger.debug(traceback.format_exc())

    def _print_feature_matrix(self, results: List[Dict[str, Any]]):
        """Print a feature matrix: keyword x features grid."""
        if not results:
            print("  No results to display.")
            return

        # Header
        features = ["Place", "Blog/View", "News", "Kin", "Shop", "Ads", "AI Brief"]
        kw_max_len = max(len(r['keyword']) for r in results)
        kw_col_width = max(kw_max_len, 10)

        header = f"  {'Keyword':<{kw_col_width}} | " + " | ".join(f"{f:^9}" for f in features) + " | Our Visible"
        separator = "  " + "-" * len(header)

        print(f"\n{separator}")
        print(header)
        print(separator)

        for r in results:
            flags = [
                "O" if r['has_place_pack'] else "-",
                "O" if r['has_blog_section'] else "-",
                "O" if r['has_news_section'] else "-",
                "O" if r['has_kin_section'] else "-",
                "O" if r['has_shopping_section'] else "-",
                f"{r['ad_count']}" if r['has_ad_top'] else "-",
                "O" if r['has_ai_briefing'] else "-",
            ]

            # Our visibility summary
            vis = r.get('our_visibility', {})
            visible_sections = [k for k, v in vis.items() if v]
            vis_str = ", ".join(visible_sections) if visible_sections else "none"

            row = f"  {r['keyword']:<{kw_col_width}} | " + " | ".join(f"{f:^9}" for f in flags) + f" | {vis_str}"
            print(row)

        print(separator)

        # Summary statistics
        total = len(results)
        place_count = sum(1 for r in results if r['has_place_pack'])
        blog_count = sum(1 for r in results if r['has_blog_section'])
        news_count = sum(1 for r in results if r['has_news_section'])
        ad_count = sum(1 for r in results if r['has_ad_top'])
        ai_count = sum(1 for r in results if r['has_ai_briefing'])

        print(f"\n  Feature Presence ({total} keywords):")
        print(f"    Place Pack: {place_count}/{total} ({place_count/total*100:.0f}%)")
        print(f"    Blog/VIEW:  {blog_count}/{total} ({blog_count/total*100:.0f}%)")
        print(f"    News:       {news_count}/{total} ({news_count/total*100:.0f}%)")
        print(f"    Ads:        {ad_count}/{total} ({ad_count/total*100:.0f}%)")
        print(f"    AI Brief:   {ai_count}/{total} ({ai_count/total*100:.0f}%)")

        # Our visibility summary
        any_visible = sum(1 for r in results if any(r.get('our_visibility', {}).values()))
        print(f"\n  Our Visibility: {any_visible}/{total} keywords ({any_visible/total*100:.0f}%)")

    def run(self):
        """Run SERP feature monitoring for all keywords."""
        if not self.keywords:
            print("No keywords to monitor.")
            return

        print(f"\n{'='*70}")
        print(f"  SERP Feature Monitor")
        print(f"  Keywords: {len(self.keywords)} | Identifiers: {self.our_identifiers}")
        print(f"  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*70}\n")

        results = []
        success_count = 0
        error_count = 0

        for idx, keyword in enumerate(self.keywords, 1):
            print(f"  [{idx}/{len(self.keywords)}] '{keyword}'...", end=" ", flush=True)

            try:
                result = self.analyze_keyword(keyword)
                if result:
                    self._save_result(result)
                    results.append(result)
                    success_count += 1

                    # Brief status
                    features_found = sum([
                        result['has_place_pack'],
                        result['has_blog_section'],
                        result['has_news_section'],
                        result['has_kin_section'],
                        result['has_shopping_section'],
                        result['has_ad_top'],
                        result['has_ai_briefing'],
                    ])
                    vis = result.get('our_visibility', {})
                    visible_count = sum(1 for v in vis.values() if v)
                    print(f"-> {features_found} features, visibility: {visible_count}")
                else:
                    error_count += 1
                    print("-> FAILED (fetch error)")

            except Exception as e:
                error_count += 1
                print(f"-> ERROR: {e}")
                logger.error(f"[{keyword}] Analysis error: {e}")
                logger.debug(traceback.format_exc())

        # Feature matrix output
        print(f"\n{'='*70}")
        print(f"  Scan Complete! Success: {success_count}/{len(self.keywords)}")
        if error_count:
            print(f"  Errors: {error_count}")
        print(f"{'='*70}")

        self._print_feature_matrix(results)

        return results

    def get_latest_features(self, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve latest SERP features from DB. For API endpoint use."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                if keyword:
                    cursor.execute("""
                        SELECT * FROM serp_features
                        WHERE keyword = ?
                        ORDER BY scanned_at DESC
                        LIMIT 1
                    """, (keyword,))
                else:
                    # Get latest scan for each keyword
                    cursor.execute("""
                        SELECT sf.* FROM serp_features sf
                        INNER JOIN (
                            SELECT keyword, MAX(scanned_at) as max_date
                            FROM serp_features
                            GROUP BY keyword
                        ) latest ON sf.keyword = latest.keyword AND sf.scanned_at = latest.max_date
                        ORDER BY sf.keyword
                    """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"DB query error: {e}")
            return []


if __name__ == "__main__":
    try:
        monitor = SerpFeatureMonitor()
        monitor.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
