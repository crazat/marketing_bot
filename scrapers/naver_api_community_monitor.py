#!/usr/bin/env python3
"""
Naver API Community Monitor
- Naver Search API (blog, cafe, kin) 기반 커뮤니티 멘션 수집
- HTML 스크래핑 대신 공식 API 사용으로 안정적 데이터 수집
- 키워드별 블로그/카페/지식인 검색 및 리드 후보 감지
"""
import sys
import os
import re
import time
import json
import logging
import hashlib
import requests
from datetime import datetime
from typing import List, Dict, Any, Optional

# Robust Path Setup for Hybrid Execution (Standalone vs Module)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Force UTF-8 output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

try:
    from db.database import DatabaseManager
    from utils import ConfigManager
except ImportError:
    print("Import Error: Check directory structure.")
    sys.exit(1)

logger = logging.getLogger(__name__)


class NaverAPICommunityMonitor:
    """
    Naver Search API 기반 커뮤니티 모니터링 엔진.
    블로그, 카페, 지식인 검색 API를 사용하여 안정적으로 데이터를 수집합니다.
    """

    # Naver Search API endpoints
    API_ENDPOINTS = {
        'naver_blog': 'https://openapi.naver.com/v1/search/blog.json',
        'naver_cafe': 'https://openapi.naver.com/v1/search/cafearticle.json',
        'naver_kin': 'https://openapi.naver.com/v1/search/kin.json',
    }

    # Additional hardcoded search terms
    EXTRA_SEARCH_TERMS = [
        "한의원 추천",
        "다이어트 한약 후기",
        "교통사고 치료 후기",
        "한의원 후기",
    ]

    # Mention type classification patterns
    MENTION_TYPE_PATTERNS = {
        'question': ['추천', '어디', '좋은곳', '알려주세요', '궁금', '질문'],
        'review': ['후기', '리뷰', '다녀왔', '방문'],
        'recommendation': ['추천합니다', '좋았어', '만족', '강추'],
        'complaint': ['별로', '실망', '불만', '나빠'],
    }

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # Load API keys for rotation
        self.api_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")

        # Fallback to single key
        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        self.current_key_index = 0

        if self.api_keys:
            logger.info(f"Loaded {len(self.api_keys)} Naver Search API Key(s) for rotation.")
        else:
            logger.warning("Naver Search API credentials not found. Monitor will be disabled.")

        # Load business profile
        self.business_name = ""
        self.business_short_name = ""
        self.region = "청주"
        self._load_business_profile()

        # Ensure DB table
        self._ensure_table()

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보 로드"""
        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                business = data.get('business', {})
                self.business_name = business.get('name', '')
                self.business_short_name = business.get('short_name', '')
                self.region = business.get('region', '청주')
                logger.info(f"Business profile loaded: {self.business_name} ({self.region})")
        except Exception as e:
            logger.error(f"Error loading business profile: {e}")

    def _ensure_table(self):
        """community_mentions 테이블 생성/확인"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS community_mentions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        platform TEXT NOT NULL,
                        keyword TEXT NOT NULL,
                        title TEXT,
                        content_preview TEXT,
                        author TEXT,
                        url TEXT,
                        url_hash TEXT UNIQUE,
                        comment_count INTEGER DEFAULT 0,
                        engagement_count INTEGER DEFAULT 0,
                        mention_type TEXT DEFAULT 'mention',
                        is_lead_candidate INTEGER DEFAULT 0,
                        is_our_mention INTEGER DEFAULT 0,
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_community_platform_keyword
                    ON community_mentions(platform, keyword)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_community_url_hash
                    ON community_mentions(url_hash)
                ''')
                conn.commit()
                logger.info("community_mentions table ensured")
        except Exception as e:
            logger.error(f"Error creating community_mentions table: {e}")

    def _get_headers(self) -> Dict[str, str]:
        """현재 API 키로 헤더 생성"""
        if not self.api_keys:
            return {}

        key_data = self.api_keys[self.current_key_index]
        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"],
        }

    def _rotate_key(self):
        """다음 API 키로 로테이션"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"API Key rotated to index {self.current_key_index}")

    def _advance_key_round_robin(self):
        """각 요청 배치마다 키 로테이션 (균등 분배)"""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

    @staticmethod
    def _strip_html(text: str) -> str:
        """HTML 태그 제거"""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()

    @staticmethod
    def _url_hash(url: str) -> str:
        """URL MD5 해시 생성"""
        return hashlib.md5(url.encode('utf-8')).hexdigest()

    def _classify_mention_type(self, text: str) -> str:
        """텍스트를 분석하여 언급 유형을 분류"""
        if not text:
            return 'mention'

        for mention_type, patterns in self.MENTION_TYPE_PATTERNS.items():
            for pattern in patterns:
                if pattern in text:
                    return mention_type

        return 'mention'

    def _is_lead_candidate(self, mention_type: str, platform: str) -> int:
        """리드 후보 여부 판단"""
        # question type on kin = high lead potential
        if mention_type == 'question' and platform == 'naver_kin':
            return 1
        # question type on cafe = recommendation-seeking
        if mention_type == 'question' and platform == 'naver_cafe':
            return 1
        return 0

    def _is_our_mention(self, title: str, description: str) -> int:
        """우리 한의원 언급 여부 확인"""
        if not self.business_name:
            return 0

        combined = f"{title} {description}"
        if self.business_name in combined:
            return 1
        if self.business_short_name and self.business_short_name in combined:
            return 1
        return 0

    def _load_keywords(self) -> List[str]:
        """config/keywords.json에서 키워드 로드 + 추가 검색어"""
        keywords = []
        kw_path = os.path.join(project_root, 'config', 'keywords.json')
        try:
            if os.path.exists(kw_path):
                with open(kw_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                naver_place_kws = data.get('naver_place', [])
                blog_seo_kws = data.get('blog_seo', [])
                keywords.extend(naver_place_kws)
                keywords.extend(blog_seo_kws)
        except Exception as e:
            logger.error(f"Error loading keywords.json: {e}")

        # Add extra search terms (dedup)
        for term in self.EXTRA_SEARCH_TERMS:
            if term not in keywords:
                keywords.append(term)

        return keywords

    def search_api(self, platform: str, query: str, display: int = 10) -> List[Dict[str, Any]]:
        """
        Naver Search API 호출

        Args:
            platform: 'naver_blog', 'naver_cafe', 'naver_kin'
            query: 검색 키워드
            display: 결과 수 (최대 100)

        Returns:
            API 응답 items 리스트
        """
        if not self.api_keys:
            logger.warning("No API keys available, skipping search.")
            return []

        endpoint = self.API_ENDPOINTS.get(platform)
        if not endpoint:
            logger.error(f"Unknown platform: {platform}")
            return []

        params = {
            'query': query,
            'display': display,
            'sort': 'date',
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            headers = self._get_headers()
            try:
                response = requests.get(
                    endpoint,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    return data.get('items', [])

                elif response.status_code in [401, 429]:
                    logger.warning(
                        f"API Error {response.status_code} for {platform}/{query}. "
                        f"Rotating key... (attempt {attempt + 1}/{max_retries})"
                    )
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"API Error {response.status_code} for {platform}/{query}: "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"Timeout for {platform}/{query} (attempt {attempt + 1})")
                time.sleep(2.0)
            except requests.exceptions.RequestException as e:
                logger.error(f"Request failed for {platform}/{query}: {e}")
                break

        return []

    def process_items(
        self, items: List[Dict[str, Any]], platform: str, keyword: str
    ) -> List[Dict[str, Any]]:
        """
        API 응답 아이템을 community_mentions 레코드로 변환

        Args:
            items: Naver Search API response items
            platform: 'naver_blog', 'naver_cafe', 'naver_kin'
            keyword: 검색 키워드

        Returns:
            DB 저장용 레코드 리스트
        """
        records = []
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        for item in items:
            title = self._strip_html(item.get('title', ''))
            description = self._strip_html(item.get('description', ''))
            link = item.get('link', '')
            bloggername = self._strip_html(item.get('bloggername', ''))
            cafename = self._strip_html(item.get('cafename', ''))

            if not link:
                continue

            # Author: blog uses bloggername, cafe uses cafename
            author = bloggername or cafename or ''

            # Classify
            combined_text = f"{title} {description}"
            mention_type = self._classify_mention_type(combined_text)
            lead_candidate = self._is_lead_candidate(mention_type, platform)
            our_mention = self._is_our_mention(title, description)

            records.append({
                'platform': platform,
                'keyword': keyword,
                'title': title[:500] if title else '',
                'content_preview': description[:1000] if description else '',
                'author': author[:200] if author else '',
                'url': link,
                'url_hash': self._url_hash(link),
                'comment_count': 0,
                'engagement_count': 0,
                'mention_type': mention_type,
                'is_lead_candidate': lead_candidate,
                'is_our_mention': our_mention,
                'scanned_at': now,
            })

        return records

    def save_records(self, records: List[Dict[str, Any]]) -> Dict[str, int]:
        """
        레코드를 DB에 저장 (INSERT OR IGNORE로 dedup)

        Returns:
            {'inserted': int, 'skipped': int}
        """
        inserted = 0
        skipped = 0

        if not records:
            return {'inserted': 0, 'skipped': 0}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                for record in records:
                    try:
                        cursor.execute('''
                            INSERT OR IGNORE INTO community_mentions
                            (platform, keyword, title, content_preview, author,
                             url, url_hash, comment_count, engagement_count,
                             mention_type, is_lead_candidate, is_our_mention, scanned_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (
                            record['platform'],
                            record['keyword'],
                            record['title'],
                            record['content_preview'],
                            record['author'],
                            record['url'],
                            record['url_hash'],
                            record['comment_count'],
                            record['engagement_count'],
                            record['mention_type'],
                            record['is_lead_candidate'],
                            record['is_our_mention'],
                            record['scanned_at'],
                        ))
                        if cursor.rowcount > 0:
                            inserted += 1
                        else:
                            skipped += 1
                    except Exception as e:
                        logger.debug(f"Insert error (likely duplicate): {e}")
                        skipped += 1

                conn.commit()
        except Exception as e:
            logger.error(f"Error saving records to DB: {e}")

        return {'inserted': inserted, 'skipped': skipped}

    def run(self) -> Dict[str, Any]:
        """
        메인 실행: 모든 키워드에 대해 3개 API 검색 수행

        Returns:
            실행 결과 요약
        """
        if not self.api_keys:
            logger.error("No API keys configured. Aborting.")
            return {'error': 'No API keys configured'}

        keywords = self._load_keywords()
        if not keywords:
            logger.warning("No keywords loaded. Aborting.")
            return {'error': 'No keywords'}

        logger.info(f"Starting Naver API Community Monitor with {len(keywords)} keywords")

        # naver_kin은 naver_kin_lead_finder.py가 전담 (중복 방지)
        platforms = ['naver_blog', 'naver_cafe']
        total_stats = {
            'naver_blog': {'new': 0, 'skipped': 0},
            'naver_cafe': {'new': 0, 'skipped': 0},
        }
        total_leads = 0
        total_our_mentions = 0
        total_requests = 0

        for kw_idx, keyword in enumerate(keywords):
            logger.info(f"[{kw_idx + 1}/{len(keywords)}] Searching: '{keyword}'")

            for platform in platforms:
                # Rotate key per request batch
                self._advance_key_round_robin()

                # Search API
                items = self.search_api(platform, keyword, display=10)
                total_requests += 1

                if items:
                    # Process and save
                    records = self.process_items(items, platform, keyword)
                    result = self.save_records(records)

                    total_stats[platform]['new'] += result['inserted']
                    total_stats[platform]['skipped'] += result['skipped']

                    # Count leads and our mentions
                    for r in records:
                        if r['is_lead_candidate']:
                            total_leads += 1
                        if r['is_our_mention']:
                            total_our_mentions += 1

                    logger.debug(
                        f"  {platform}: {len(items)} items, "
                        f"{result['inserted']} new, {result['skipped']} skipped"
                    )

                # Rate limit: 0.3s between requests
                time.sleep(0.3)

        summary = {
            'keywords_searched': len(keywords),
            'total_requests': total_requests,
            'platforms': total_stats,
            'total_new': sum(s['new'] for s in total_stats.values()),
            'total_skipped': sum(s['skipped'] for s in total_stats.values()),
            'leads_found': total_leads,
            'our_mentions': total_our_mentions,
        }

        return summary

    def print_summary(self, summary: Dict[str, Any]):
        """결과 요약 출력"""
        print("\n" + "=" * 60)
        print("  Naver API Community Monitor - Results")
        print("=" * 60)

        if 'error' in summary:
            print(f"  ERROR: {summary['error']}")
            return

        print(f"  Keywords searched: {summary['keywords_searched']}")
        print(f"  Total API requests: {summary['total_requests']}")
        print()

        print("  Platform Breakdown:")
        print("  " + "-" * 40)
        for platform, stats in summary.get('platforms', {}).items():
            label = platform.replace('naver_', 'Naver ').title()
            print(f"    {label:20s} | New: {stats['new']:4d} | Skipped: {stats['skipped']:4d}")

        print()
        print(f"  Total new records:  {summary.get('total_new', 0)}")
        print(f"  Total skipped:      {summary.get('total_skipped', 0)}")
        print(f"  Lead candidates:    {summary.get('leads_found', 0)}")
        print(f"  Our mentions:       {summary.get('our_mentions', 0)}")
        print("=" * 60)


def main():
    """Standalone execution entry point"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    print("=" * 60)
    print("  Naver API Community Monitor")
    print("  Reliable API-based community monitoring")
    print("=" * 60)

    monitor = NaverAPICommunityMonitor()
    summary = monitor.run()
    monitor.print_summary(summary)

    return summary


if __name__ == '__main__':
    main()
