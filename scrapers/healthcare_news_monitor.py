#!/usr/bin/env python3
"""
Healthcare News Monitor - 의료/경쟁사 뉴스 모니터링
====================================================

네이버 뉴스 검색 API를 통해 의료 업계 및 경쟁사 관련 뉴스를 수집합니다.
- 경쟁사별 뉴스 모니터링
- 업계 규제/트렌드 뉴스 수집
- 자사 브랜드 언급 감지
- HTML 태그 자동 제거
- Telegram 알림 (자사 언급/경쟁사 중요 뉴스)

Usage:
    python scrapers/healthcare_news_monitor.py
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

NEWS_API_URL = "https://openapi.naver.com/v1/search/news.json"
RATE_LIMIT_DELAY = 0.3  # seconds between requests
DISPLAY_COUNT = 100  # max results per request

# Industry search queries
INDUSTRY_QUERIES = [
    "한의원 규제",
    "한의원 보험",
    "청주 의료",
    "한약 트렌드",
    "한의원 마케팅",
]


# ============================================================================
# Utility
# ============================================================================

def strip_html_tags(text: str) -> str:
    """HTML 태그를 제거하고 엔티티를 디코딩합니다."""
    if not text:
        return ""
    # Remove HTML tags
    clean = re.sub(r'<[^>]+>', '', text)
    # Decode common HTML entities
    clean = clean.replace('&amp;', '&')
    clean = clean.replace('&lt;', '<')
    clean = clean.replace('&gt;', '>')
    clean = clean.replace('&quot;', '"')
    clean = clean.replace('&#39;', "'")
    clean = clean.replace('&nbsp;', ' ')
    # Collapse whitespace
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def extract_source(original_link: str) -> str:
    """뉴스 원본 링크에서 언론사 도메인을 추출합니다."""
    if not original_link:
        return ""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(original_link)
        return parsed.netloc.replace("www.", "")
    except Exception:
        return ""


class HealthcareNewsMonitor:
    """의료 업계 및 경쟁사 관련 뉴스를 모니터링합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_api_keys()
        self._load_competitors()
        self._load_business_profile()
        self._init_telegram()
        self._last_request_time = 0

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """healthcare_news 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS healthcare_news (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        description TEXT,
                        link TEXT UNIQUE,
                        pub_date TEXT,
                        source TEXT,
                        query_keyword TEXT,
                        news_type TEXT DEFAULT 'industry',
                        is_competitor_mention INTEGER DEFAULT 0,
                        is_our_mention INTEGER DEFAULT 0,
                        competitor_name TEXT,
                        relevance_score INTEGER DEFAULT 50,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_healthcare_news_type
                    ON healthcare_news (news_type, created_at DESC)
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_healthcare_news_link
                    ON healthcare_news (link)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"healthcare_news 테이블 생성 실패: {e}")
            raise
        logger.info("healthcare_news 테이블 준비 완료")

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
            logger.warning("Naver Search API 키를 찾을 수 없습니다. 뉴스 모니터링이 불가합니다.")

    def _load_competitors(self):
        """config/targets.json에서 경쟁사 목록을 로드합니다."""
        self.competitors = []

        try:
            targets_data = self.config.load_targets()
            targets = targets_data.get('targets', [])

            for target in targets:
                name = target.get('name', '').strip()
                if name:
                    self.competitors.append(name)
        except Exception as e:
            logger.error(f"targets.json 로드 실패: {e}")

        logger.info(f"경쟁사 {len(self.competitors)}개 로드")

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보를 로드합니다."""
        self.business_name = "규림한의원"
        self.business_short_name = "규림"
        self.business_identifiers = []

        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                business = data.get('business', {})
                self.business_name = business.get('name', '규림한의원')
                self.business_short_name = business.get('short_name', '규림')

                # Collect all identifiers
                for key in ['name', 'short_name', 'english_name']:
                    val = business.get(key)
                    if val:
                        self.business_identifiers.append(val.lower())

                exclude_names = data.get('competitors', {}).get('exclude_names', [])
                for name in exclude_names:
                    if name.lower() not in self.business_identifiers:
                        self.business_identifiers.append(name.lower())

        except Exception as e:
            logger.warning(f"business_profile.json 로드 실패: {e}")

        if not self.business_identifiers:
            self.business_identifiers = ["규림한의원", "규림", "kyurim"]

        logger.info(f"업체명: {self.business_name}")

    def _init_telegram(self):
        """Telegram 알림 봇을 초기화합니다."""
        self.telegram_bot = None
        try:
            from alert_bot import TelegramBot

            token = self.config.get_api_key('TELEGRAM_BOT_TOKEN')
            chat_id = self.config.get_api_key('TELEGRAM_CHAT_ID')
            self.telegram_bot = TelegramBot(token=token, chat_id=chat_id)
            logger.info("Telegram 알림 봇 초기화 완료")
        except ImportError:
            logger.info("alert_bot 모듈 없음, Telegram 알림 비활성화")
        except Exception as e:
            logger.warning(f"Telegram 봇 초기화 실패: {e}")

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
    # News Search API
    # ========================================================================

    def _search_news(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        네이버 뉴스 검색 API로 쿼리를 검색합니다.

        Args:
            query: 검색어

        Returns:
            뉴스 항목 리스트 또는 None (실패 시)
        """
        if not self.api_keys:
            return None

        params = {
            "query": query,
            "display": DISPLAY_COUNT,
            "start": 1,
            "sort": "date"
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_headers()
                response = requests.get(
                    NEWS_API_URL,
                    params=params,
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('items', [])

                elif response.status_code in [401, 429]:
                    logger.warning(f"News API {response.status_code}, 키 로테이션...")
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"News API 오류 {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"News API 타임아웃 (시도 {attempt + 1}/{max_retries})")
                time.sleep(2.0)

            except requests.exceptions.RequestException as e:
                logger.error(f"News API 요청 실패: {e}")
                break

        return None

    # ========================================================================
    # Classification & Scoring
    # ========================================================================

    def _classify_news_type(self, query: str, title: str, description: str) -> str:
        """뉴스 유형을 분류합니다."""
        combined = f"{title} {description}".lower()

        # 자사 브랜드 언급
        for ident in self.business_identifiers:
            if ident.lower() in combined:
                return "our_brand"

        # 경쟁사 언급
        for comp in self.competitors:
            if comp.lower() in combined:
                return "competitor"

        # 규제 관련
        regulation_keywords = ["규제", "보험", "법안", "정책", "건보", "심사평가", "의료법"]
        for kw in regulation_keywords:
            if kw in combined:
                return "regulation"

        return "industry"

    def _check_our_mention(self, title: str, description: str) -> bool:
        """자사 브랜드 언급 여부를 확인합니다."""
        combined = f"{title} {description}".lower()
        for ident in self.business_identifiers:
            if ident.lower() in combined:
                return True
        return False

    def _check_competitor_mention(self, title: str, description: str) -> Optional[str]:
        """경쟁사 언급 여부를 확인하고 해당 경쟁사명을 반환합니다."""
        combined = f"{title} {description}".lower()
        for comp in self.competitors:
            if comp.lower() in combined:
                return comp
        return None

    def _calculate_relevance(self, news_type: str, title: str, description: str) -> int:
        """뉴스 관련성 점수를 계산합니다 (0-100)."""
        score = 50  # base

        combined = f"{title} {description}".lower()

        # 자사 언급 -> 높은 점수
        if news_type == "our_brand":
            score = 95

        # 경쟁사 -> 중간-높은 점수
        elif news_type == "competitor":
            score = 75

        # 규제 -> 중간-높은 점수
        elif news_type == "regulation":
            score = 70

        # 지역 관련 가산점
        if "청주" in combined:
            score = min(100, score + 10)

        # 한의원 관련 가산점
        if "한의원" in combined or "한방" in combined:
            score = min(100, score + 5)

        # 트렌드/마케팅 관련
        trend_keywords = ["마케팅", "트렌드", "성장", "시장"]
        for kw in trend_keywords:
            if kw in combined:
                score = min(100, score + 3)

        return score

    def _parse_pub_date(self, pub_date_str: str) -> str:
        """네이버 API의 pubDate를 YYYY-MM-DD HH:MM:SS 형식으로 변환합니다."""
        if not pub_date_str:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # Naver API format: "Tue, 18 Mar 2026 09:00:00 +0900"
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(pub_date_str)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ========================================================================
    # Collection
    # ========================================================================

    def collect_news(self) -> Dict[str, Any]:
        """
        모든 검색 쿼리에 대해 뉴스를 수집합니다.

        Returns:
            수집 결과 요약 dict
        """
        if not self.api_keys:
            print("[WARN] Naver Search API 키가 설정되지 않았습니다.")
            return {"total_found": 0, "new_saved": 0, "our_mentions": 0, "competitor_mentions": 0}

        # Build search query list
        search_queries = []

        # 1. Competitor names
        for comp in self.competitors:
            search_queries.append({"query": comp, "type": "competitor"})

        # 2. Industry queries
        for q in INDUSTRY_QUERIES:
            search_queries.append({"query": q, "type": "industry"})

        # 3. Our brand
        search_queries.append({"query": self.business_name, "type": "our_brand"})

        print(f"\n{'='*60}")
        print(f" Healthcare News Monitor")
        print(f" 검색 쿼리: {len(search_queries)}개 (경쟁사 {len(self.competitors)} + 업계 {len(INDUSTRY_QUERIES)} + 자사)")
        print(f" API 키: {len(self.api_keys)}개")
        print(f"{'='*60}\n")

        total_found = 0
        new_saved = 0
        our_mentions = 0
        competitor_mentions = 0
        all_news_items = []

        for q_idx, query_info in enumerate(search_queries):
            query = query_info["query"]
            q_type = query_info["type"]

            print(f"  [{q_idx + 1}/{len(search_queries)}] '{query}' ({q_type})...", end=" ", flush=True)

            items = self._search_news(query)

            if not items:
                print("-> 결과 없음")
                self._rotate_key()
                continue

            total_found += len(items)

            # Process items
            processed = []
            for item in items:
                title = strip_html_tags(item.get('title', ''))
                description = strip_html_tags(item.get('description', ''))
                link = item.get('link', '')
                original_link = item.get('originallink', link)
                pub_date = self._parse_pub_date(item.get('pubDate', ''))

                if not link:
                    continue

                # Classify
                news_type = self._classify_news_type(query, title, description)
                is_our = self._check_our_mention(title, description)
                comp_name = self._check_competitor_mention(title, description)
                relevance = self._calculate_relevance(news_type, title, description)
                source = extract_source(original_link)

                processed.append({
                    "title": title[:500],
                    "description": description[:1000],
                    "link": link,
                    "pub_date": pub_date,
                    "source": source,
                    "query_keyword": query,
                    "news_type": news_type,
                    "is_competitor_mention": 1 if comp_name else 0,
                    "is_our_mention": 1 if is_our else 0,
                    "competitor_name": comp_name or "",
                    "relevance_score": relevance,
                })

                if is_our:
                    our_mentions += 1
                if comp_name:
                    competitor_mentions += 1

            # Save to DB
            saved = self._save_news(processed)
            new_saved += saved
            all_news_items.extend(processed)

            print(f"-> {len(items)}건 수신, {saved}건 신규")

            self._rotate_key()

        print(f"\n>> 수집 완료: {total_found}건 검색, {new_saved}건 신규 저장")
        print(f"   자사 언급: {our_mentions}건, 경쟁사 언급: {competitor_mentions}건")

        # Send Telegram alerts
        self._send_alerts(all_news_items)

        return {
            "total_found": total_found,
            "new_saved": new_saved,
            "our_mentions": our_mentions,
            "competitor_mentions": competitor_mentions,
            "news_items": all_news_items,
        }

    def _save_news(self, news_items: List[Dict[str, Any]]) -> int:
        """뉴스를 DB에 저장합니다 (link 기반 중복 방지)."""
        saved_count = 0

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for item in news_items:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO healthcare_news
                                (title, description, link, pub_date, source,
                                 query_keyword, news_type, is_competitor_mention,
                                 is_our_mention, competitor_name, relevance_score)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            item['title'],
                            item['description'],
                            item['link'],
                            item['pub_date'],
                            item['source'],
                            item['query_keyword'],
                            item['news_type'],
                            item['is_competitor_mention'],
                            item['is_our_mention'],
                            item['competitor_name'],
                            item['relevance_score'],
                        ))
                        if cursor.rowcount > 0:
                            saved_count += 1
                    except Exception as e:
                        logger.warning(f"뉴스 저장 실패: {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"뉴스 DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

        return saved_count

    # ========================================================================
    # Telegram Alerts
    # ========================================================================

    def _send_alerts(self, news_items: List[Dict[str, Any]]):
        """자사 언급 또는 중요 경쟁사 뉴스에 대해 Telegram 알림을 발송합니다."""
        if not self.telegram_bot:
            return

        # Filter: our brand mentions
        our_news = [n for n in news_items if n['is_our_mention']]

        # Filter: high relevance competitor news
        comp_news = [n for n in news_items
                     if n['is_competitor_mention'] and n['relevance_score'] >= 70]

        if not our_news and not comp_news:
            return

        try:
            lines = ["[Healthcare News Alert]", ""]

            if our_news:
                lines.append(f"자사 언급 뉴스 ({len(our_news)}건):")
                for n in our_news[:5]:
                    lines.append(f"  - {n['title'][:60]}")
                    lines.append(f"    출처: {n['source']} | {n['pub_date'][:10]}")
                lines.append("")

            if comp_news:
                lines.append(f"경쟁사 관련 뉴스 ({len(comp_news)}건):")
                for n in comp_news[:5]:
                    comp = n['competitor_name']
                    lines.append(f"  - [{comp}] {n['title'][:50]}")
                    lines.append(f"    출처: {n['source']} | 관련성: {n['relevance_score']}")
                lines.append("")

            lines.append(f"모니터링 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

            message = "\n".join(lines)
            self.telegram_bot.send_message(message)
            logger.info(f"Telegram 뉴스 알림 발송: 자사 {len(our_news)}건, 경쟁사 {len(comp_news)}건")

        except Exception as e:
            logger.error(f"Telegram 알림 발송 실패: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Analysis & Output
    # ========================================================================

    def analyze_news(self, days: int = 7) -> Dict[str, Any]:
        """
        최근 뉴스를 분석하여 요약합니다.

        Args:
            days: 분석 기간 (일)

        Returns:
            분석 결과 dict
        """
        results = {
            "by_type": {},
            "top_sources": [],
            "competitor_coverage": [],
            "our_coverage": [],
        }

        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # By type
                cursor.execute("""
                    SELECT news_type, COUNT(*) as cnt
                    FROM healthcare_news
                    WHERE created_at >= ?
                    GROUP BY news_type
                    ORDER BY cnt DESC
                """, (cutoff,))
                for row in cursor.fetchall():
                    results["by_type"][row[0]] = row[1]

                # Top sources
                cursor.execute("""
                    SELECT source, COUNT(*) as cnt
                    FROM healthcare_news
                    WHERE created_at >= ? AND source != ''
                    GROUP BY source
                    ORDER BY cnt DESC
                    LIMIT 10
                """, (cutoff,))
                results["top_sources"] = [
                    {"source": row[0], "count": row[1]}
                    for row in cursor.fetchall()
                ]

                # Competitor coverage
                cursor.execute("""
                    SELECT competitor_name, COUNT(*) as cnt
                    FROM healthcare_news
                    WHERE is_competitor_mention = 1 AND created_at >= ?
                    GROUP BY competitor_name
                    ORDER BY cnt DESC
                """, (cutoff,))
                results["competitor_coverage"] = [
                    {"name": row[0], "count": row[1]}
                    for row in cursor.fetchall()
                ]

                # Our coverage
                cursor.execute("""
                    SELECT title, source, pub_date, relevance_score
                    FROM healthcare_news
                    WHERE is_our_mention = 1 AND created_at >= ?
                    ORDER BY pub_date DESC
                    LIMIT 10
                """, (cutoff,))
                results["our_coverage"] = [
                    {"title": row[0], "source": row[1], "date": row[2], "relevance": row[3]}
                    for row in cursor.fetchall()
                ]

        except Exception as e:
            logger.error(f"뉴스 분석 오류: {e}")
            logger.debug(traceback.format_exc())

        return results

    def _print_summary(self, collect_result: Dict[str, Any], analysis: Dict[str, Any]):
        """뉴스 모니터링 결과를 출력합니다."""
        print(f"\n{'='*80}")
        print(f" Healthcare News Monitor - Summary")
        print(f"{'─'*80}")

        # By type
        by_type = analysis.get('by_type', {})
        if by_type:
            print(f"\n  뉴스 유형별 분포:")
            type_labels = {
                "industry": "업계", "competitor": "경쟁사",
                "our_brand": "자사", "regulation": "규제"
            }
            for t, cnt in by_type.items():
                label = type_labels.get(t, t)
                print(f"    {label:<10} : {cnt}건")

        # Competitor coverage
        comp_cov = analysis.get('competitor_coverage', [])
        if comp_cov:
            print(f"\n  경쟁사 뉴스 노출:")
            for c in comp_cov[:5]:
                print(f"    {c['name']:<25} : {c['count']}건")

        # Our coverage
        our_cov = analysis.get('our_coverage', [])
        if our_cov:
            print(f"\n  자사 뉴스 ({len(our_cov)}건):")
            for o in our_cov[:5]:
                print(f"    [{o['date'][:10]}] {o['title'][:50]}... (출처: {o['source']})")
        else:
            print(f"\n  자사 뉴스: 없음")

        print(f"{'='*80}\n")

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """뉴스 수집 + 분석을 실행합니다."""
        start_time = time.time()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Healthcare News Monitor 시작")

        # 1. Collect
        collect_result = self.collect_news()

        # 2. Analyze (last 7 days)
        analysis = self.analyze_news(days=7)

        # 3. Print summary
        self._print_summary(collect_result, analysis)

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")

        return {
            "total_found": collect_result.get('total_found', 0),
            "new_saved": collect_result.get('new_saved', 0),
            "our_mentions": collect_result.get('our_mentions', 0),
            "competitor_mentions": collect_result.get('competitor_mentions', 0),
            "analysis": analysis,
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
        monitor = HealthcareNewsMonitor()
        result = monitor.run()
        print(f"\n[완료] 검색: {result['total_found']}건, 신규: {result['new_saved']}건, "
              f"자사: {result['our_mentions']}건, 경쟁사: {result['competitor_mentions']}건")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
