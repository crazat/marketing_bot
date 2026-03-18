#!/usr/bin/env python3
"""
Web Visibility Tracker - 네이버 웹 검색 노출 추적기
====================================================

네이버 웹 검색 API를 통해 자사/경쟁사 웹사이트의 검색 노출 순위를 추적합니다.
- 키워드별 자사 웹사이트 순위 확인
- 경쟁사 웹사이트 순위 비교
- 검색 노출 변화 추이 분석
- API 키 로테이션 + Rate limiting

Usage:
    python scrapers/web_visibility_tracker.py
"""

import sys
import os
import re
import time
import json
import logging
import traceback
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

WEBKR_API_URL = "https://openapi.naver.com/v1/search/webkr.json"
RATE_LIMIT_DELAY = 0.3  # seconds between requests
DISPLAY_COUNT = 100  # max results per request
DEFAULT_OUR_DOMAIN = "kyurim.com"


def strip_html_tags(text: str) -> str:
    """HTML 태그를 제거합니다."""
    if not text:
        return ""
    clean = re.sub(r'<[^>]+>', '', text)
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&nbsp;', ' ')
    return re.sub(r'\s+', ' ', clean).strip()


def extract_domain(url: str) -> str:
    """URL에서 도메인을 추출합니다."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.replace("www.", "")
        return domain.lower()
    except Exception:
        return ""


class WebVisibilityTracker:
    """네이버 웹 검색에서 자사/경쟁사 웹사이트 노출 순위를 추적합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_api_keys()
        self._load_keywords()
        self._load_business_profile()
        self._load_competitors()
        self._last_request_time = 0

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """web_visibility 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS web_visibility (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        our_rank INTEGER DEFAULT 0,
                        our_url TEXT,
                        our_title TEXT,
                        competitor_results TEXT DEFAULT '[]',
                        total_results INTEGER DEFAULT 0,
                        scanned_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(keyword, scanned_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_web_visibility_keyword_date
                    ON web_visibility (keyword, scanned_date DESC)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"web_visibility 테이블 생성 실패: {e}")
            raise
        logger.info("web_visibility 테이블 준비 완료")

    def _load_api_keys(self):
        """NAVER_SEARCH_KEYS 로드 (5개 키 로테이션)."""
        self.api_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")

        # Fallback: single key
        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        self.current_key_index = 0
        if self.api_keys:
            logger.info(f"Naver Search API 키 {len(self.api_keys)}개 로드 완료")
        else:
            logger.warning("Naver Search API 키를 찾을 수 없습니다. 웹 노출 추적이 불가합니다.")

    def _load_keywords(self):
        """config/keywords.json에서 naver_place + blog_seo 키워드를 로드합니다."""
        self.keywords = []
        keywords_path = os.path.join(project_root, 'config', 'keywords.json')

        try:
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                self.keywords.extend(kw_data.get('naver_place', []))
                self.keywords.extend(kw_data.get('blog_seo', []))
                # 중복 제거 (순서 유지)
                self.keywords = list(dict.fromkeys(self.keywords))
        except Exception as e:
            logger.error(f"keywords.json 로드 실패: {e}")

        if not self.keywords:
            logger.warning("수집할 키워드가 없습니다. config/keywords.json을 확인하세요.")

        logger.info(f"웹 노출 추적 대상 키워드 {len(self.keywords)}개 로드")

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보를 로드합니다."""
        self.our_domain = DEFAULT_OUR_DOMAIN
        self.our_identifiers = []
        self.business_name = "규림한의원"

        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                business = data.get('business', {})
                self.business_name = business.get('name', '규림한의원')

                # Website domain
                website = business.get('website', '')
                if website:
                    self.our_domain = extract_domain(website) or DEFAULT_OUR_DOMAIN

                # Identifiers for matching
                for key in ['name', 'short_name', 'english_name']:
                    val = business.get(key)
                    if val:
                        self.our_identifiers.append(val.lower())

                exclude_names = data.get('competitors', {}).get('exclude_names', [])
                for name in exclude_names:
                    if name.lower() not in self.our_identifiers:
                        self.our_identifiers.append(name.lower())

        except Exception as e:
            logger.warning(f"business_profile.json 로드 실패: {e}")

        if not self.our_identifiers:
            self.our_identifiers = ["규림한의원", "규림", "kyurim"]

        logger.info(f"자사 도메인: {self.our_domain}, 식별자: {self.our_identifiers}")

    def _load_competitors(self):
        """config/targets.json에서 경쟁사 정보를 로드합니다."""
        self.competitors = []
        self.competitor_domains = {}  # name -> [domains]

        try:
            targets_data = self.config.load_targets()
            targets = targets_data.get('targets', [])

            for target in targets:
                name = target.get('name', '').strip()
                if not name:
                    continue

                comp = {
                    "name": name,
                    "domains": [],
                    "keywords": target.get('keywords', []),
                }

                # Extract domains from monitor_urls
                monitor_urls = target.get('monitor_urls', {})
                for url_key, url_val in monitor_urls.items():
                    if url_val and isinstance(url_val, str):
                        domain = extract_domain(url_val)
                        if domain and domain not in comp['domains']:
                            comp['domains'].append(domain)

                self.competitors.append(comp)
                self.competitor_domains[name.lower()] = comp['domains']

        except Exception as e:
            logger.error(f"targets.json 로드 실패: {e}")

        logger.info(f"경쟁사 {len(self.competitors)}개 로드")

    # ========================================================================
    # API Key Rotation & Rate Limiting
    # ========================================================================

    def _get_headers(self) -> Dict[str, str]:
        """현재 키 인덱스의 API 헤더를 반환합니다."""
        if not self.api_keys:
            return {}

        key_data = self.api_keys[self.current_key_index]
        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"]
        }

    def _rotate_key(self):
        """다음 API 키로 로테이션합니다."""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

    def _rate_limit(self):
        """요청 간 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    # ========================================================================
    # Web Search API
    # ========================================================================

    def _search_web(self, query: str) -> Optional[Dict[str, Any]]:
        """
        네이버 웹 검색 API로 쿼리를 검색합니다.

        Args:
            query: 검색어

        Returns:
            API 응답 dict (items + total) 또는 None (실패 시)
        """
        if not self.api_keys:
            return None

        params = {
            "query": query,
            "display": DISPLAY_COUNT,
            "start": 1
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_headers()
                response = requests.get(
                    WEBKR_API_URL,
                    params=params,
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    return {
                        "items": data.get('items', []),
                        "total": data.get('total', 0),
                    }

                elif response.status_code in [401, 429]:
                    logger.warning(f"Web Search API {response.status_code}, 키 로테이션...")
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"Web Search API 오류 {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"Web Search API 타임아웃 (시도 {attempt + 1}/{max_retries})")
                time.sleep(2.0)

            except requests.exceptions.RequestException as e:
                logger.error(f"Web Search API 요청 실패: {e}")
                break

        return None

    # ========================================================================
    # Matching
    # ========================================================================

    def _is_our_result(self, url: str, title: str) -> bool:
        """검색 결과가 자사인지 확인합니다."""
        domain = extract_domain(url)
        title_lower = title.lower()

        # Domain match
        if self.our_domain and self.our_domain in domain:
            return True

        # Name match in title
        for ident in self.our_identifiers:
            if ident in title_lower:
                return True

        return False

    def _find_competitor(self, url: str, title: str) -> Optional[str]:
        """검색 결과에서 경쟁사를 식별합니다."""
        domain = extract_domain(url)
        title_lower = title.lower()

        for comp in self.competitors:
            comp_name = comp['name']
            comp_name_lower = comp_name.lower()

            # Domain match
            for comp_domain in comp.get('domains', []):
                if comp_domain and comp_domain in domain:
                    return comp_name

            # Name match in title
            if comp_name_lower in title_lower:
                return comp_name

            # Partial name match (without suffixes like "청주점", "(벤치마크)")
            clean_name = re.sub(r'\s*(청주점|본점|점|병원|\(.*?\))', '', comp_name_lower).strip()
            if len(clean_name) >= 2 and clean_name in title_lower:
                return comp_name

        return None

    # ========================================================================
    # Collection
    # ========================================================================

    def track_visibility(self) -> Dict[str, Any]:
        """
        모든 키워드에 대해 웹 검색 노출을 추적합니다.

        Returns:
            추적 결과 요약 dict
        """
        if not self.keywords:
            print("[WARN] 추적할 키워드가 없습니다.")
            return {"scanned": 0, "our_found": 0}

        if not self.api_keys:
            print("[WARN] Naver Search API 키가 설정되지 않았습니다.")
            return {"scanned": 0, "our_found": 0}

        scanned_date = datetime.now().strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f" Web Visibility Tracker")
        print(f" 키워드: {len(self.keywords)}개")
        print(f" 자사 도메인: {self.our_domain}")
        print(f" 경쟁사: {len(self.competitors)}개")
        print(f" API 키: {len(self.api_keys)}개")
        print(f"{'='*60}\n")

        results = []
        scanned = 0
        our_found = 0

        for idx, keyword in enumerate(self.keywords, 1):
            print(f"  [{idx}/{len(self.keywords)}] '{keyword}'...", end=" ", flush=True)

            search_data = self._search_web(keyword)

            if not search_data:
                print("-> FAILED")
                self._rotate_key()
                continue

            items = search_data.get('items', [])
            total = search_data.get('total', 0)
            scanned += 1

            our_rank = 0
            our_url = ""
            our_title = ""
            competitor_results = []

            for rank, item in enumerate(items, 1):
                title = strip_html_tags(item.get('title', ''))
                link = item.get('link', '')
                description = strip_html_tags(item.get('description', ''))

                # Check if this is our result
                if our_rank == 0 and self._is_our_result(link, title):
                    our_rank = rank
                    our_url = link
                    our_title = title
                    our_found += 1

                # Check if this is a competitor result
                comp_name = self._find_competitor(link, title)
                if comp_name:
                    competitor_results.append({
                        "name": comp_name,
                        "rank": rank,
                        "url": link,
                        "title": title[:100],
                    })

            result = {
                "keyword": keyword,
                "our_rank": our_rank,
                "our_url": our_url,
                "our_title": our_title,
                "competitor_results": competitor_results,
                "total_results": total,
                "scanned_date": scanned_date,
            }
            results.append(result)

            # Save to DB
            self._save_result(result)

            # Print brief status
            if our_rank > 0:
                print(f"-> 우리: {our_rank}위, 경쟁사: {len(competitor_results)}개")
            else:
                print(f"-> 순위권 밖, 경쟁사: {len(competitor_results)}개")

            self._rotate_key()

        print(f"\n>> 추적 완료: {scanned}개 키워드, 자사 노출: {our_found}개")

        # Print matrix
        self._print_rank_matrix(results)

        return {
            "scanned": scanned,
            "our_found": our_found,
            "results": results,
        }

    def _save_result(self, result: Dict[str, Any]):
        """추적 결과를 DB에 저장합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO web_visibility
                        (keyword, our_rank, our_url, our_title,
                         competitor_results, total_results, scanned_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(keyword, scanned_date) DO UPDATE SET
                        our_rank = excluded.our_rank,
                        our_url = excluded.our_url,
                        our_title = excluded.our_title,
                        competitor_results = excluded.competitor_results,
                        total_results = excluded.total_results
                """, (
                    result['keyword'],
                    result['our_rank'],
                    result['our_url'],
                    result['our_title'],
                    json.dumps(result['competitor_results'], ensure_ascii=False),
                    result['total_results'],
                    result['scanned_date'],
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB 저장 오류 [{result.get('keyword')}]: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Output
    # ========================================================================

    def _print_rank_matrix(self, results: List[Dict[str, Any]]):
        """키워드 x 순위 매트릭스를 출력합니다."""
        if not results:
            print("  추적 결과가 없습니다.")
            return

        # Collect all competitor names that appeared
        all_comp_names = set()
        for r in results:
            for cr in r['competitor_results']:
                all_comp_names.add(cr['name'])

        comp_names = sorted(all_comp_names)
        if len(comp_names) > 8:
            comp_names = comp_names[:8]  # Limit to top 8 for display

        # Header
        kw_col = 25
        rank_col = 6
        header_parts = [f"{'키워드':<{kw_col}}", f"{'자사':>{rank_col}}"]
        for cn in comp_names:
            short_name = cn[:8]
            header_parts.append(f"{short_name:>{rank_col}}")

        print(f"\n{'='*120}")
        print("  " + " | ".join(header_parts))
        print(f"{'─'*120}")

        for r in results:
            kw_display = r['keyword'][:kw_col - 1]
            our_rank_str = str(r['our_rank']) if r['our_rank'] > 0 else "-"

            parts = [f"{kw_display:<{kw_col}}", f"{our_rank_str:>{rank_col}}"]

            # Competitor ranks
            comp_rank_map = {cr['name']: cr['rank'] for cr in r['competitor_results']}
            for cn in comp_names:
                rank = comp_rank_map.get(cn, 0)
                rank_str = str(rank) if rank > 0 else "-"
                parts.append(f"{rank_str:>{rank_col}}")

            print("  " + " | ".join(parts))

        print(f"{'─'*120}")

        # Summary statistics
        total = len(results)
        ranked = sum(1 for r in results if r['our_rank'] > 0)
        avg_rank = 0
        if ranked > 0:
            avg_rank = sum(r['our_rank'] for r in results if r['our_rank'] > 0) / ranked

        print(f"\n  자사 웹 노출: {ranked}/{total} 키워드 ({ranked/total*100:.0f}%)")
        if ranked > 0:
            print(f"  평균 순위: {avg_rank:.1f}위")

        top10 = sum(1 for r in results if 0 < r['our_rank'] <= 10)
        top30 = sum(1 for r in results if 0 < r['our_rank'] <= 30)
        print(f"  Top 10: {top10}개, Top 30: {top30}개")

        # Competitor summary
        if comp_names:
            print(f"\n  경쟁사 노출 빈도:")
            for cn in comp_names:
                count = sum(1 for r in results
                            if any(cr['name'] == cn for cr in r['competitor_results']))
                avg_comp = 0
                ranks = [cr['rank'] for r in results
                         for cr in r['competitor_results'] if cr['name'] == cn]
                if ranks:
                    avg_comp = sum(ranks) / len(ranks)
                print(f"    {cn:<25} : {count}개 키워드, 평균 {avg_comp:.1f}위")

        print(f"{'='*120}\n")

    # ========================================================================
    # Historical Query
    # ========================================================================

    def get_visibility_history(self, keyword: Optional[str] = None,
                               days: int = 30) -> List[Dict[str, Any]]:
        """DB에서 웹 노출 이력을 조회합니다. API 엔드포인트용."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                if keyword:
                    cursor.execute("""
                        SELECT * FROM web_visibility
                        WHERE keyword = ? AND scanned_date >= ?
                        ORDER BY scanned_date DESC
                    """, (keyword, cutoff))
                else:
                    # Latest scan for each keyword
                    cursor.execute("""
                        SELECT wv.* FROM web_visibility wv
                        INNER JOIN (
                            SELECT keyword, MAX(scanned_date) as max_date
                            FROM web_visibility
                            GROUP BY keyword
                        ) latest ON wv.keyword = latest.keyword
                            AND wv.scanned_date = latest.max_date
                        ORDER BY wv.our_rank ASC
                    """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"웹 노출 이력 조회 오류: {e}")
            return []

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """웹 노출 추적을 실행합니다."""
        start_time = time.time()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Web Visibility Tracker 시작")

        result = self.track_visibility()

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")

        return {
            "scanned": result.get('scanned', 0),
            "our_found": result.get('our_found', 0),
            "results": result.get('results', []),
            "elapsed_seconds": round(elapsed, 1)
        }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        tracker = WebVisibilityTracker()
        result = tracker.run()
        print(f"\n[완료] 스캔: {result['scanned']}개, 자사 노출: {result['our_found']}개")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
