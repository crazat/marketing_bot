#!/usr/bin/env python3
"""
Blog Rank Tracker - 네이버 VIEW 탭 블로그 순위 추적기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

blog_seo 키워드별 네이버 VIEW 탭에서 우리 블로그 순위를 추적합니다.
- requests + BeautifulSoup 기반 (Selenium 미사용, 고속)
- User-Agent 로테이션
- Rate limiting (1-2초)
- blog_rank_history 테이블에 결과 저장
"""

import os
import sys
import json
import time
import random
import hashlib
import traceback
import logging
import re
from datetime import datetime
from urllib.parse import quote, urlencode
from typing import Optional, Dict, List, Tuple

import requests
from bs4 import BeautifulSoup

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')


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


class BlogRankTracker:
    """네이버 VIEW 탭에서 우리 블로그의 순위를 추적합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_blog_identifier()
        self._load_keywords()
        self._last_request_time = 0

    def _ensure_table(self):
        """blog_rank_history 테이블이 없으면 생성합니다."""
        with self.db.get_new_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS blog_rank_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    rank_position INTEGER DEFAULT 0,
                    found INTEGER DEFAULT 0,
                    result_title TEXT,
                    result_url TEXT,
                    result_source TEXT,
                    total_checked INTEGER DEFAULT 0,
                    search_url TEXT,
                    tracked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # 인덱스 생성
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_blog_rank_keyword_date
                ON blog_rank_history (keyword, tracked_at)
            """)
            conn.commit()
        logger.info("blog_rank_history 테이블 준비 완료")

    def _load_blog_identifier(self):
        """config/business_profile.json에서 블로그 식별자를 로드합니다."""
        self.blog_identifiers = []

        profile_path = os.path.join(project_root, 'config', 'business_profile.json')
        try:
            if os.path.exists(profile_path):
                with open(profile_path, 'r', encoding='utf-8') as f:
                    profile = json.load(f)

                business = profile.get('business', {})
                # 다양한 식별자 수집
                if business.get('name'):
                    self.blog_identifiers.append(business['name'])
                if business.get('short_name'):
                    self.blog_identifiers.append(business['short_name'])
                if business.get('english_name'):
                    self.blog_identifiers.append(business['english_name'])

                # blog_url or blog_id 필드가 있으면 추가
                if business.get('blog_url'):
                    # URL에서 blog_id 추출
                    match = re.search(r'blog\.naver\.com/(\w+)', business['blog_url'])
                    if match:
                        self.blog_identifiers.append(match.group(1))
                if business.get('blog_id'):
                    self.blog_identifiers.append(business['blog_id'])

                # competitors.exclude_names 도 식별자로 활용
                exclude_names = profile.get('competitors', {}).get('exclude_names', [])
                self.blog_identifiers.extend(exclude_names)
        except Exception as e:
            logger.warning(f"business_profile.json 로드 실패: {e}")

        # 중복 제거, 소문자 변환
        seen = set()
        unique = []
        for ident in self.blog_identifiers:
            low = ident.lower()
            if low and low not in seen:
                seen.add(low)
                unique.append(ident)
        self.blog_identifiers = unique

        if not self.blog_identifiers:
            # Fallback
            self.blog_identifiers = ["규림", "kyurim"]
            logger.warning("블로그 식별자를 찾지 못해 기본값 사용: %s", self.blog_identifiers)
        else:
            logger.info("블로그 식별자 로드: %s", self.blog_identifiers)

    def _load_keywords(self):
        """config/keywords.json에서 blog_seo 카테고리 키워드를 로드합니다."""
        self.keywords = []
        keywords_path = os.path.join(project_root, 'config', 'keywords.json')

        try:
            if os.path.exists(keywords_path):
                with open(keywords_path, 'r', encoding='utf-8') as f:
                    kw_data = json.load(f)
                self.keywords = kw_data.get('blog_seo', [])
                # naver_place 키워드도 VIEW 탭 추적 대상에 포함
                self.keywords.extend(kw_data.get('naver_place', []))
                # 중복 제거
                self.keywords = list(dict.fromkeys(self.keywords))
        except Exception as e:
            logger.error(f"keywords.json 로드 실패: {e}")

        if not self.keywords:
            logger.warning("추적할 키워드가 없습니다. config/keywords.json을 확인하세요.")

        logger.info(f"추적 키워드 {len(self.keywords)}개 로드")

    def _rate_limit(self):
        """요청 간 1-2초 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(1.0, 2.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _get_headers(self) -> Dict[str, str]:
        """랜덤 User-Agent가 포함된 헤더를 반환합니다."""
        return {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
        }

    def search_view_tab(self, keyword: str) -> Tuple[int, bool, Optional[str], Optional[str], Optional[str], int]:
        """
        네이버 VIEW 탭에서 키워드를 검색하고 우리 블로그 순위를 확인합니다.

        Returns:
            (rank_position, found, result_title, result_url, result_source, total_checked)
        """
        self._rate_limit()

        encoded_keyword = quote(keyword)
        search_url = f"https://search.naver.com/search.naver?where=view&query={encoded_keyword}"

        try:
            response = requests.get(
                search_url,
                headers=self._get_headers(),
                timeout=15
            )
            response.raise_for_status()
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP 오류 [{keyword}]: {e}")
            return (0, False, None, None, None, 0)
        except requests.exceptions.ConnectionError as e:
            logger.error(f"연결 오류 [{keyword}]: {e}")
            return (0, False, None, None, None, 0)
        except requests.exceptions.Timeout:
            logger.error(f"타임아웃 [{keyword}]")
            return (0, False, None, None, None, 0)
        except requests.exceptions.RequestException as e:
            logger.error(f"요청 오류 [{keyword}]: {e}")
            return (0, False, None, None, None, 0)

        soup = BeautifulSoup(response.text, 'html.parser')

        # 검색결과 없음 확인
        no_result = soup.select_one('.api_no_result')
        if no_result:
            logger.info(f"[{keyword}] 검색결과 없음")
            return (0, False, None, None, None, 0)

        # VIEW 탭 결과 파싱 (여러 셀렉터 시도)
        items = soup.select('li[data-cr-rank]')
        if not items:
            items = soup.select('li.bx')
        if not items:
            items = soup.select('.view_wrap')
        if not items:
            items = soup.select('.total_wrap')

        total_checked = len(items)

        if not items:
            # 캡차/차단 감지
            page_text = response.text.lower()
            if 'captcha' in page_text or 'unusual traffic' in page_text:
                logger.warning(f"[{keyword}] 캡차/차단 감지됨!")
            else:
                logger.warning(f"[{keyword}] 결과 항목을 파싱할 수 없음 (셀렉터 변경 가능성)")
            return (0, False, None, None, None, 0)

        # 상위 30개 내에서 우리 블로그 검색
        for rank, item in enumerate(items[:30], 1):
            try:
                item_text = item.get_text(separator=' ').lower()
                title_el = item.select_one('.title_link') or item.select_one('.api_txt_lines.total_tit')
                link = ""
                title = ""

                if title_el:
                    link = title_el.get('href', '')
                    title = title_el.get_text(strip=True)

                # 소스(블로그 이름) 추출
                name_el = item.select_one('.name') or item.select_one('.sub_txt') or item.select_one('.source_txt')
                source_name = name_el.get_text(strip=True) if name_el else ""

                # 우리 블로그인지 확인
                for identifier in self.blog_identifiers:
                    ident_lower = identifier.lower()
                    if (ident_lower in item_text or
                        ident_lower in link.lower() or
                        ident_lower in source_name.lower()):
                        logger.info(f"[{keyword}] {rank}위 발견! (매칭: '{identifier}')")
                        return (rank, True, title, link, source_name, total_checked)

            except Exception as e:
                logger.debug(f"항목 파싱 오류 (rank {rank}): {e}")
                continue

        logger.info(f"[{keyword}] 상위 {min(30, total_checked)}위 내 미발견")
        return (0, False, None, None, None, total_checked)

    def _save_result(self, keyword: str, rank: int, found: bool,
                     title: Optional[str], url: Optional[str],
                     source: Optional[str], total_checked: int,
                     search_url: str):
        """결과를 DB에 저장합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO blog_rank_history
                    (keyword, rank_position, found, result_title, result_url,
                     result_source, total_checked, search_url, tracked_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    keyword,
                    rank,
                    1 if found else 0,
                    title,
                    url,
                    source,
                    total_checked,
                    search_url,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB 저장 오류 [{keyword}]: {e}")
            logger.debug(traceback.format_exc())

    def run(self):
        """전체 키워드에 대해 VIEW 탭 순위 추적을 실행합니다."""
        if not self.keywords:
            print("추적할 키워드가 없습니다.")
            return

        print(f"\n{'='*60}")
        print(f" Blog Rank Tracker - VIEW 탭 순위 추적")
        print(f" 키워드: {len(self.keywords)}개 | 블로그 식별자: {self.blog_identifiers}")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        results_summary = []
        found_count = 0
        error_count = 0

        for idx, keyword in enumerate(self.keywords, 1):
            print(f"  [{idx}/{len(self.keywords)}] '{keyword}' 검색 중...", end=" ")

            try:
                rank, found, title, url, source, total = self.search_view_tab(keyword)

                encoded_kw = quote(keyword)
                search_url = f"https://search.naver.com/search.naver?where=view&query={encoded_kw}"

                self._save_result(keyword, rank, found, title, url, source, total, search_url)

                if found:
                    print(f"-> {rank}위 (출처: {source or 'N/A'})")
                    found_count += 1
                    results_summary.append((keyword, rank, source))
                else:
                    print(f"-> 미발견 (검색결과 {total}건 확인)")
                    results_summary.append((keyword, 0, None))

            except Exception as e:
                error_count += 1
                print(f"-> 오류: {e}")
                logger.error(f"[{keyword}] 추적 오류: {e}")
                logger.debug(traceback.format_exc())

        # 결과 요약
        print(f"\n{'='*60}")
        print(f" 추적 완료!")
        print(f" 발견: {found_count}/{len(self.keywords)}개")
        if error_count:
            print(f" 오류: {error_count}건")
        print(f"{'='*60}")

        if found_count > 0:
            print(f"\n 순위 발견 키워드:")
            for kw, rank, source in sorted(results_summary, key=lambda x: (x[1] == 0, x[1])):
                if rank > 0:
                    print(f"   {rank:3d}위  |  {kw}  ({source or ''})")

        return results_summary


if __name__ == "__main__":
    try:
        tracker = BlogRankTracker()
        tracker.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
