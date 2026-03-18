#!/usr/bin/env python3
"""
Competitor Blog Tracker - 경쟁사 블로그 활동 추적기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

경쟁사 블로그 포스팅 빈도 및 키워드 타겟팅을 추적합니다.
- 네이버 블로그 검색 API로 경쟁사별 최신 포스트 수집
- HTML 태그 제거 후 우리 키워드와 매칭
- url_hash 기반 중복 방지
- 활동 스파이크 감지 (평소 대비 3x)
- API 키 로테이션 + Rate limiting
"""

import sys
import os
import time
import json
import hashlib
import logging
import re
import traceback
import requests
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

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# ============================================================================
# Constants
# ============================================================================

BLOG_SEARCH_API_URL = "https://openapi.naver.com/v1/search/blog.json"
DISPLAY_COUNT = 30  # max results per request
RATE_LIMIT_DELAY = 0.5  # seconds between requests


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


def make_url_hash(url: str) -> str:
    """URL의 MD5 해시를 생성합니다."""
    return hashlib.md5(url.encode('utf-8')).hexdigest()


class CompetitorBlogTracker:
    """경쟁사 블로그 포스팅 활동을 추적합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_api_keys()
        self._load_competitors()
        self._load_keywords()
        self._init_telegram()
        self._last_request_time = 0

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """competitor_blog_activity 테이블이 없으면 생성합니다."""
        with self.db.get_new_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS competitor_blog_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    competitor_name TEXT NOT NULL,
                    blog_title TEXT,
                    blog_link TEXT,
                    blog_description TEXT,
                    blogger_name TEXT,
                    post_date TEXT,
                    matched_keywords TEXT DEFAULT '[]',
                    url_hash TEXT UNIQUE,
                    detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_competitor_blog_name_date
                ON competitor_blog_activity (competitor_name, detected_at DESC)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_competitor_blog_hash
                ON competitor_blog_activity (url_hash)
            """)
            conn.commit()
        logger.info("competitor_blog_activity 테이블 준비 완료")

    def _load_api_keys(self):
        """NAVER_SEARCH_KEYS 로드 (키 로테이션)."""
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
            logger.warning("Naver Search API 키를 찾을 수 없습니다. 블로그 추적이 불가합니다.")

    def _load_competitors(self):
        """config/targets.json에서 경쟁사 목록을 로드합니다."""
        self.competitors = []

        try:
            targets_data = self.config.load_targets()
            targets = targets_data.get('targets', [])

            for target in targets:
                name = target.get('name', '').strip()
                if not name:
                    continue

                self.competitors.append({
                    "name": name,
                    "category": target.get('category', ''),
                    "priority": target.get('priority', 'Medium'),
                    "keywords": target.get('keywords', [])
                })

        except Exception as e:
            logger.error(f"targets.json 로드 실패: {e}")

        if not self.competitors:
            logger.warning("추적할 경쟁사가 없습니다. config/targets.json을 확인하세요.")

        logger.info(f"경쟁사 {len(self.competitors)}개 로드")

    def _load_keywords(self):
        """config/keywords.json에서 우리 키워드를 로드합니다 (매칭 용도)."""
        self.our_keywords = []
        keywords_path = os.path.join(project_root, 'config', 'keywords.json')

        try:
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                self.our_keywords.extend(kw_data.get('naver_place', []))
                self.our_keywords.extend(kw_data.get('blog_seo', []))
                # 중복 제거
                self.our_keywords = list(dict.fromkeys(self.our_keywords))
        except Exception as e:
            logger.error(f"keywords.json 로드 실패: {e}")

        logger.info(f"매칭용 키워드 {len(self.our_keywords)}개 로드")

    def _init_telegram(self):
        """Telegram 알림 봇을 초기화합니다."""
        self.telegram_bot = None
        try:
            from alert_bot import TelegramBot, AlertPriority
            self.AlertPriority = AlertPriority

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
            logger.info(f"API 키 로테이션 -> 인덱스 {self.current_key_index}")

    def _rate_limit(self):
        """요청 간 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    # ========================================================================
    # Blog Search API
    # ========================================================================

    def _search_blog(self, query: str) -> Optional[List[Dict[str, Any]]]:
        """
        네이버 블로그 검색 API로 쿼리를 검색합니다.

        Args:
            query: 검색어

        Returns:
            블로그 항목 리스트 또는 None (실패 시)
        """
        if not self.api_keys:
            return None

        params = {
            "query": query,
            "display": DISPLAY_COUNT,
            "sort": "date"
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_headers()
                response = requests.get(
                    BLOG_SEARCH_API_URL,
                    params=params,
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('items', [])

                elif response.status_code in [401, 429]:
                    logger.warning(f"Blog Search API {response.status_code}, 키 로테이션...")
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"Blog Search API 오류 {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"Blog Search API 타임아웃 (시도 {attempt + 1}/{max_retries})")
                time.sleep(2.0)

            except requests.exceptions.RequestException as e:
                logger.error(f"Blog Search API 요청 실패: {e}")
                break

        return None

    # ========================================================================
    # Keyword Matching
    # ========================================================================

    def _match_keywords(self, title: str, description: str) -> List[str]:
        """
        포스트의 제목+설명에서 우리 키워드와 매칭되는 항목을 찾습니다.

        Args:
            title: 포스트 제목
            description: 포스트 설명

        Returns:
            매칭된 키워드 리스트
        """
        matched = []
        text = f"{title} {description}".lower()

        for kw in self.our_keywords:
            # 키워드에서 공백 제거 후에도 매칭 시도
            kw_lower = kw.lower()
            kw_no_space = kw_lower.replace(' ', '')

            if kw_lower in text or kw_no_space in text.replace(' ', ''):
                matched.append(kw)

        return matched

    # ========================================================================
    # Collection
    # ========================================================================

    def collect_blog_activity(self) -> Dict[str, Any]:
        """
        모든 경쟁사의 블로그 활동을 수집합니다.

        Returns:
            수집 결과 요약 dict
        """
        if not self.competitors:
            print("[WARN] 추적할 경쟁사가 없습니다.")
            return {"total_posts": 0, "new_posts": 0, "competitors_scanned": 0}

        if not self.api_keys:
            print("[WARN] Naver Search API 키가 설정되지 않았습니다.")
            return {"total_posts": 0, "new_posts": 0, "competitors_scanned": 0}

        print(f"\n{'='*60}")
        print(f" Competitor Blog Tracker")
        print(f" 경쟁사: {len(self.competitors)}개")
        print(f" 매칭 키워드: {len(self.our_keywords)}개")
        print(f" API 키: {len(self.api_keys)}개")
        print(f"{'='*60}\n")

        total_posts = 0
        new_posts = 0
        competitors_scanned = 0
        all_posts_by_competitor = {}  # competitor_name -> [posts]

        for comp_idx, competitor in enumerate(self.competitors):
            comp_name = competitor['name']
            print(f"[{comp_idx + 1}/{len(self.competitors)}] {comp_name} ({competitor.get('priority', '')})")

            posts = []

            # Search 1: competitor name directly
            items = self._search_blog(comp_name)
            if items:
                posts.extend(items)

            # Search 2: competitor name + 한의원
            if '한의원' not in comp_name and '병원' not in comp_name:
                items2 = self._search_blog(f"{comp_name} 한의원")
                if items2:
                    posts.extend(items2)

            if not posts:
                logger.info(f"  {comp_name}: 검색 결과 없음")
                competitors_scanned += 1
                # Rotate key per competitor
                self._rotate_key()
                continue

            # Deduplicate by URL within this batch
            seen_links = set()
            unique_posts = []
            for post in posts:
                link = post.get('link', '')
                if link and link not in seen_links:
                    seen_links.add(link)
                    unique_posts.append(post)

            # Process posts
            processed = []
            for post in unique_posts:
                title = strip_html_tags(post.get('title', ''))
                description = strip_html_tags(post.get('description', ''))
                link = post.get('link', '')
                blogger_name = post.get('bloggername', '')
                post_date = post.get('postdate', '')  # YYYYMMDD format

                # Format post_date to YYYY-MM-DD
                if post_date and len(post_date) == 8:
                    post_date = f"{post_date[:4]}-{post_date[4:6]}-{post_date[6:8]}"

                # Match against our keywords
                matched_keywords = self._match_keywords(title, description)

                url_hash = make_url_hash(link)

                processed.append({
                    "competitor_name": comp_name,
                    "blog_title": title,
                    "blog_link": link,
                    "blog_description": description[:500],  # truncate long descriptions
                    "blogger_name": blogger_name,
                    "post_date": post_date,
                    "matched_keywords": json.dumps(matched_keywords, ensure_ascii=False),
                    "url_hash": url_hash
                })

            total_posts += len(processed)
            all_posts_by_competitor[comp_name] = processed

            # Save to DB
            saved = self._save_posts(processed)
            new_posts += saved

            matched_count = sum(1 for p in processed if json.loads(p['matched_keywords']))
            print(f"  -> {len(processed)}개 포스트 ({saved}개 신규), 키워드 매칭: {matched_count}개")

            competitors_scanned += 1

            # Rotate key per competitor
            self._rotate_key()

        print(f"\n>> 수집 완료: {competitors_scanned}개 경쟁사, "
              f"{total_posts}개 포스트 ({new_posts}개 신규)")

        return {
            "total_posts": total_posts,
            "new_posts": new_posts,
            "competitors_scanned": competitors_scanned,
            "posts_by_competitor": all_posts_by_competitor
        }

    def _save_posts(self, posts: List[Dict[str, Any]]) -> int:
        """포스트를 DB에 저장합니다 (url_hash 기반 중복 방지)."""
        saved_count = 0

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for post in posts:
                    try:
                        cursor.execute("""
                            INSERT OR IGNORE INTO competitor_blog_activity
                                (competitor_name, blog_title, blog_link, blog_description,
                                 blogger_name, post_date, matched_keywords, url_hash, detected_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            post['competitor_name'],
                            post['blog_title'],
                            post['blog_link'],
                            post['blog_description'],
                            post['blogger_name'],
                            post['post_date'],
                            post['matched_keywords'],
                            post['url_hash'],
                            datetime.now().isoformat()
                        ))
                        if cursor.rowcount > 0:
                            saved_count += 1
                    except Exception as e:
                        logger.warning(f"포스트 저장 실패: {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"포스트 DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

        return saved_count

    # ========================================================================
    # Analysis
    # ========================================================================

    def analyze_activity(self) -> List[Dict[str, Any]]:
        """
        경쟁사 블로그 활동을 분석합니다.
        - 최근 7일/30일 포스팅 수
        - 활동 스파이크 감지 (3x normal)
        - 경쟁사 타겟 키워드 중 우리가 타겟하지 않는 것 식별

        Returns:
            경쟁사별 분석 결과 리스트
        """
        results = []
        spike_alerts = []

        try:
            now = datetime.now()
            date_7d = (now - timedelta(days=7)).strftime("%Y-%m-%d")
            date_30d = (now - timedelta(days=30)).strftime("%Y-%m-%d")
            date_60d = (now - timedelta(days=60)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for competitor in self.competitors:
                    comp_name = competitor['name']

                    # Posts in last 7 days
                    cursor.execute("""
                        SELECT COUNT(*) as cnt
                        FROM competitor_blog_activity
                        WHERE competitor_name = ? AND detected_at >= ?
                    """, (comp_name, date_7d))
                    row_7d = cursor.fetchone()
                    posts_7d = row_7d['cnt'] if row_7d else 0

                    # Posts in last 30 days
                    cursor.execute("""
                        SELECT COUNT(*) as cnt
                        FROM competitor_blog_activity
                        WHERE competitor_name = ? AND detected_at >= ?
                    """, (comp_name, date_30d))
                    row_30d = cursor.fetchone()
                    posts_30d = row_30d['cnt'] if row_30d else 0

                    # Posts in 30-60 days ago (for baseline comparison)
                    cursor.execute("""
                        SELECT COUNT(*) as cnt
                        FROM competitor_blog_activity
                        WHERE competitor_name = ?
                          AND detected_at >= ? AND detected_at < ?
                    """, (comp_name, date_60d, date_30d))
                    row_prev = cursor.fetchone()
                    posts_prev_30d = row_prev['cnt'] if row_prev else 0

                    # Trend direction
                    if posts_prev_30d > 0:
                        activity_ratio = posts_30d / posts_prev_30d
                    else:
                        activity_ratio = float(posts_30d) if posts_30d > 0 else 0.0

                    if activity_ratio >= 3.0 and posts_30d >= 3:
                        trend = "SPIKE"
                    elif activity_ratio >= 1.5:
                        trend = "UP"
                    elif activity_ratio >= 0.7:
                        trend = "STABLE"
                    elif posts_prev_30d > 0:
                        trend = "DOWN"
                    else:
                        trend = "NEW"

                    # Top matched keywords
                    cursor.execute("""
                        SELECT matched_keywords
                        FROM competitor_blog_activity
                        WHERE competitor_name = ? AND detected_at >= ?
                          AND matched_keywords != '[]'
                    """, (comp_name, date_30d))
                    kw_rows = cursor.fetchall()

                    keyword_counts = {}
                    for kw_row in kw_rows:
                        try:
                            kws = json.loads(kw_row['matched_keywords'])
                            for kw in kws:
                                keyword_counts[kw] = keyword_counts.get(kw, 0) + 1
                        except (json.JSONDecodeError, TypeError):
                            pass

                    top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]

                    result = {
                        "name": comp_name,
                        "category": competitor.get('category', ''),
                        "priority": competitor.get('priority', ''),
                        "posts_7d": posts_7d,
                        "posts_30d": posts_30d,
                        "posts_prev_30d": posts_prev_30d,
                        "activity_ratio": round(activity_ratio, 2),
                        "trend": trend,
                        "top_keywords": top_keywords
                    }
                    results.append(result)

                    if trend == "SPIKE":
                        spike_alerts.append(result)

        except Exception as e:
            logger.error(f"활동 분석 실패: {e}")
            logger.debug(traceback.format_exc())

        # Identify keywords competitors target that we don't
        uncovered_keywords = self._find_uncovered_keywords()

        # Print summary
        self._print_summary(results, uncovered_keywords)

        # Telegram alerts for spikes
        if spike_alerts:
            self._send_spike_alerts(spike_alerts)

        return results

    def _find_uncovered_keywords(self) -> List[Dict[str, Any]]:
        """경쟁사가 타겟하지만 우리가 타겟하지 않는 키워드를 찾습니다."""
        uncovered = []

        try:
            date_30d = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            our_kw_set = set(kw.lower() for kw in self.our_keywords)

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # Get all competitor blog titles/descriptions from last 30 days
                cursor.execute("""
                    SELECT competitor_name, blog_title, blog_description
                    FROM competitor_blog_activity
                    WHERE detected_at >= ?
                """, (date_30d,))
                rows = cursor.fetchall()

            # Extract common terms from competitor posts
            term_counts = {}
            # Common medical/marketing terms to look for
            search_terms = [
                "다이어트", "한약", "추나", "교통사고", "입원", "야간진료",
                "일요일", "비만", "체중", "감량", "디톡스", "해독",
                "피부", "여드름", "흉터", "재생", "안면", "비대칭",
                "턱관절", "두통", "불면", "스트레스", "면역", "보약",
                "산후조리", "갱년기", "성장", "비염", "아토피"
            ]

            for row in rows:
                text = f"{row['blog_title']} {row['blog_description']}".lower()
                comp_name = row['competitor_name']

                for term in search_terms:
                    if term in text:
                        key = term
                        if key not in term_counts:
                            term_counts[key] = {"count": 0, "competitors": set()}
                        term_counts[key]["count"] += 1
                        term_counts[key]["competitors"].add(comp_name)

            # Find terms that appear frequently but are not in our keywords
            for term, data in term_counts.items():
                # Check if this term appears in any of our keywords
                is_covered = any(term in kw for kw in our_kw_set)
                if not is_covered and data["count"] >= 2:
                    uncovered.append({
                        "term": term,
                        "count": data["count"],
                        "competitors": list(data["competitors"])[:3]
                    })

            uncovered.sort(key=lambda x: x['count'], reverse=True)

        except Exception as e:
            logger.debug(f"미커버 키워드 분석 실패: {e}")

        return uncovered[:10]  # Top 10

    # ========================================================================
    # Output
    # ========================================================================

    def _print_summary(self, results: List[Dict[str, Any]],
                       uncovered: List[Dict[str, Any]]):
        """경쟁사 블로그 활동 요약을 출력합니다."""
        print(f"\n{'='*90}")
        print(f" {'경쟁사':<20} {'7일':>6} {'30일':>6} {'이전30일':>8} {'추세':>8} {'상위 키워드'}")
        print(f"{'─'*90}")

        for r in results:
            name_display = r['name'][:19]
            kw_str = ", ".join([f"{kw}({c})" for kw, c in r['top_keywords'][:3]]) if r['top_keywords'] else "-"

            trend_display = {
                "SPIKE": "SPIKE!",
                "UP": "UP",
                "STABLE": "~",
                "DOWN": "DOWN",
                "NEW": "NEW"
            }.get(r['trend'], r['trend'])

            print(
                f" {name_display:<20} "
                f"{r['posts_7d']:>5} "
                f"{r['posts_30d']:>5} "
                f"{r['posts_prev_30d']:>7} "
                f"{trend_display:>7} "
                f" {kw_str}"
            )

        print(f"{'─'*90}")
        print(f" 총 {len(results)}개 경쟁사 분석")

        # Uncovered keywords
        if uncovered:
            print(f"\n >> 우리가 미커버하는 키워드 ({len(uncovered)}개):")
            for u in uncovered:
                comp_str = ", ".join(u['competitors'][:2])
                print(f"    * {u['term']} (등장 {u['count']}회, 사용: {comp_str})")

        print(f"{'='*90}\n")

    def _send_spike_alerts(self, spikes: List[Dict[str, Any]]):
        """활동 스파이크 감지 시 Telegram 알림을 발송합니다."""
        if not self.telegram_bot:
            return

        try:
            lines = ["*[Competitor Blog Spike Alert]*", ""]
            lines.append("*비정상 활동 감지:*")

            for s in spikes[:5]:
                lines.append(
                    f"  * {s['name']}: {s['posts_30d']}건 "
                    f"(이전 {s['posts_prev_30d']}건, {s['activity_ratio']:.1f}x)"
                )

            lines.append("")
            lines.append(f"감지 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

            message = "\n".join(lines)
            self.telegram_bot.send_message(message, priority=self.AlertPriority.WARNING)
            logger.info(f"Telegram 스파이크 알림 발송: {len(spikes)}개 경쟁사")

        except Exception as e:
            logger.error(f"Telegram 알림 발송 실패: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """블로그 활동 수집 + 분석을 실행합니다."""
        start_time = time.time()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Competitor Blog Tracker 시작")

        # 1. Collect
        result = self.collect_blog_activity()

        # 2. Analyze
        analysis = self.analyze_activity()

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")

        return {
            "total_posts": result.get('total_posts', 0),
            "new_posts": result.get('new_posts', 0),
            "competitors_scanned": result.get('competitors_scanned', 0),
            "analysis": analysis,
            "elapsed_seconds": round(elapsed, 1)
        }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    tracker = CompetitorBlogTracker()
    result = tracker.run()

    print(f"\n[완료] 경쟁사: {result['competitors_scanned']}개, "
          f"포스트: {result['total_posts']}개 ({result['new_posts']}개 신규)")
