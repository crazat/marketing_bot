#!/usr/bin/env python3
"""
Naver Shop Trend Monitor - 네이버 쇼핑 트렌드 모니터링
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
네이버 쇼핑 검색 API를 활용하여 한의원/건강 관련
상품 트렌드를 모니터링합니다.

- 검색어별 상품 수, 가격대, 주요 브랜드 추적
- 가격 트렌드 감지 (상승/하락/안정)
- TOP 상품 및 브랜드 파악
- NAVER_SEARCH_KEYS 5개 키 로테이션

Usage:
    python scrapers/naver_shop_trend_monitor.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import Counter, defaultdict

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


# 검색 키워드 목록
SEARCH_QUERIES = [
    "다이어트 한약",
    "보약",
    "한방 다이어트",
    "여드름 한약",
    "교통사고 한약",
    "한방 화장품",
    "한의원 추천",
]

SHOP_API_URL = "https://openapi.naver.com/v1/search/shop.json"
RATE_LIMIT_DELAY = 0.5  # API 호출 간격 (초)


class NaverShopTrendMonitor:
    """네이버 쇼핑 트렌드 모니터링"""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self.api_keys = []
        self.current_key_index = 0
        self._init_api_keys()
        self._ensure_table()

    def _init_api_keys(self):
        """네이버 검색 API 키를 로드합니다."""
        self.api_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")

        # Fallback: 개별 키 시도
        if not self.api_keys:
            for i in range(1, 10):
                cid = self.config.get_api_key(f"NAVER_SEARCH_CLIENT_ID_{i}")
                sec = self.config.get_api_key(f"NAVER_SEARCH_SECRET_{i}")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})

        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_SEARCH_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_SEARCH_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        if self.api_keys:
            logger.info(f"네이버 검색 API 키 {len(self.api_keys)}개 로드")
        else:
            logger.warning("네이버 검색 API 키를 찾을 수 없습니다.")

    def _get_next_headers(self) -> Dict[str, str]:
        """라운드 로빈으로 API 키를 로테이션합니다."""
        if not self.api_keys:
            return {}

        key_data = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)

        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"]
        }

    def _ensure_table(self):
        """shop_trend_monitoring 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS shop_trend_monitoring (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        query_keyword TEXT NOT NULL,
                        total_results INTEGER DEFAULT 0,
                        avg_price REAL DEFAULT 0,
                        min_price REAL DEFAULT 0,
                        max_price REAL DEFAULT 0,
                        top_products TEXT DEFAULT '[]',
                        top_brands TEXT DEFAULT '[]',
                        price_trend TEXT DEFAULT 'stable',
                        scanned_date TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(query_keyword, scanned_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_shop_trend_keyword_date
                    ON shop_trend_monitoring (query_keyword, scanned_date)
                """)
                conn.commit()
            logger.info("shop_trend_monitoring 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 생성 실패: {e}")
            logger.debug(traceback.format_exc())

    def _clean_html(self, text: str) -> str:
        """HTML 태그를 제거합니다."""
        if not text:
            return ""
        return re.sub(r'<[^>]+>', '', text).strip()

    def _search_shop(self, query: str, display: int = 100, sort: str = "sim") -> Optional[Dict]:
        """네이버 쇼핑 검색 API를 호출합니다."""
        if not self.api_keys:
            logger.warning("API 키가 없어 쇼핑 검색을 건너뜁니다.")
            return None

        headers = self._get_next_headers()
        params = {
            "query": query,
            "display": display,
            "start": 1,
            "sort": sort
        }

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            try:
                response = requests.get(
                    SHOP_API_URL,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    return response.json()

                elif response.status_code == 429:
                    logger.warning(f"API 할당량 초과 (429). 키 로테이션 후 재시도... ({attempt + 1}/{max_retries})")
                    headers = self._get_next_headers()
                    time.sleep(1.0)
                    continue

                elif response.status_code in (401, 403):
                    logger.warning(f"API 인증 오류 ({response.status_code}). 키 로테이션...")
                    headers = self._get_next_headers()
                    time.sleep(0.5)
                    continue

                else:
                    logger.error(f"API 오류 {response.status_code}: {response.text[:200]}")
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"타임아웃 (시도 {attempt + 1}/{max_retries})")
                time.sleep(1.0)

            except requests.exceptions.RequestException as e:
                logger.error(f"요청 오류: {e}")
                time.sleep(1.0)

        return None

    def _analyze_query(self, query: str) -> Optional[Dict]:
        """단일 검색어에 대한 쇼핑 트렌드를 분석합니다."""
        print(f"  [{query}] 검색 중...", end=" ")

        data = self._search_shop(query)
        if not data:
            print("-> 검색 실패")
            return None

        total_results = data.get('total', 0)
        items = data.get('items', [])

        if not items:
            print(f"-> 결과 없음 (total: {total_results})")
            return {
                'query_keyword': query,
                'total_results': total_results,
                'avg_price': 0,
                'min_price': 0,
                'max_price': 0,
                'top_products': [],
                'top_brands': [],
                'price_trend': 'stable'
            }

        # 가격 분석
        prices = []
        for item in items:
            try:
                lprice = int(item.get('lprice', 0))
                if lprice > 0:
                    prices.append(lprice)
            except (ValueError, TypeError):
                pass

        avg_price = round(sum(prices) / max(len(prices), 1)) if prices else 0
        min_price = min(prices) if prices else 0
        max_price = max(prices) if prices else 0

        # TOP 5 상품
        top_products = []
        for item in items[:5]:
            top_products.append({
                'title': self._clean_html(item.get('title', '')),
                'price': int(item.get('lprice', 0)),
                'link': item.get('link', ''),
                'mall_name': item.get('mallName', '')
            })

        # 브랜드/쇼핑몰 빈도
        mall_counter = Counter()
        for item in items:
            mall_name = item.get('mallName', '').strip()
            if mall_name:
                mall_counter[mall_name] += 1

        top_brands = [
            {"name": name, "count": count}
            for name, count in mall_counter.most_common(10)
        ]

        # 가격 트렌드 감지 (이전 데이터와 비교)
        price_trend = self._detect_price_trend(query, avg_price)

        print(f"-> {total_results:,}건 / 평균가 {avg_price:,}원 / {price_trend}")

        return {
            'query_keyword': query,
            'total_results': total_results,
            'avg_price': avg_price,
            'min_price': min_price,
            'max_price': max_price,
            'top_products': top_products,
            'top_brands': top_brands,
            'price_trend': price_trend
        }

    def _detect_price_trend(self, query: str, current_avg_price: float) -> str:
        """이전 데이터와 비교하여 가격 트렌드를 감지합니다."""
        if current_avg_price <= 0:
            return 'stable'

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT avg_price
                    FROM shop_trend_monitoring
                    WHERE query_keyword = ?
                      AND avg_price > 0
                    ORDER BY scanned_date DESC
                    LIMIT 1
                """, (query,))
                row = cursor.fetchone()

                if not row or not row[0]:
                    return 'stable'

                prev_price = row[0]
                if prev_price <= 0:
                    return 'stable'

                change_pct = ((current_avg_price - prev_price) / prev_price) * 100

                if change_pct > 10:
                    return 'rising'
                elif change_pct < -10:
                    return 'falling'
                else:
                    return 'stable'

        except Exception as e:
            logger.debug(f"가격 트렌드 감지 실패: {e}")
            return 'stable'

    def _save_result(self, result: Dict):
        """분석 결과를 DB에 저장합니다."""
        scanned_date = datetime.now().strftime("%Y-%m-%d")

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO shop_trend_monitoring
                    (query_keyword, total_results, avg_price, min_price, max_price,
                     top_products, top_brands, price_trend, scanned_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(query_keyword, scanned_date) DO UPDATE SET
                        total_results = excluded.total_results,
                        avg_price = excluded.avg_price,
                        min_price = excluded.min_price,
                        max_price = excluded.max_price,
                        top_products = excluded.top_products,
                        top_brands = excluded.top_brands,
                        price_trend = excluded.price_trend
                """, (
                    result['query_keyword'],
                    result['total_results'],
                    result['avg_price'],
                    result['min_price'],
                    result['max_price'],
                    json.dumps(result['top_products'], ensure_ascii=False),
                    json.dumps(result['top_brands'], ensure_ascii=False),
                    result['price_trend'],
                    scanned_date
                ))
                conn.commit()

        except Exception as e:
            logger.error(f"DB 저장 오류 [{result['query_keyword']}]: {e}")
            logger.debug(traceback.format_exc())

    def run(self):
        """전체 검색 키워드에 대해 쇼핑 트렌드를 모니터링합니다."""
        if not self.api_keys:
            print("네이버 검색 API 키가 설정되지 않았습니다.")
            print("config/secrets.json에 NAVER_SEARCH_KEYS를 추가하세요.")
            return

        print(f"\n{'='*60}")
        print(f" Naver Shop Trend Monitor")
        print(f" 검색어: {len(SEARCH_QUERIES)}개 / API 키: {len(self.api_keys)}개")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        results = []
        success_count = 0
        error_count = 0

        for idx, query in enumerate(SEARCH_QUERIES, 1):
            print(f"  [{idx}/{len(SEARCH_QUERIES)}] ", end="")

            try:
                result = self._analyze_query(query)
                if result:
                    self._save_result(result)
                    results.append(result)
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                print(f"  [{query}] 오류: {e}")
                logger.error(f"[{query}] 분석 오류: {e}")
                logger.debug(traceback.format_exc())

            # Rate limit
            if idx < len(SEARCH_QUERIES):
                time.sleep(RATE_LIMIT_DELAY)

        # 결과 요약
        print(f"\n{'='*60}")
        print(f" 수집 완료! 성공: {success_count}/{len(SEARCH_QUERIES)}")
        if error_count:
            print(f" 실패: {error_count}건")
        print(f"{'='*60}")

        # 트렌드 테이블 출력
        if results:
            print(f"\n{'='*80}")
            print(f" 쇼핑 트렌드 요약")
            print(f"{'='*80}")
            print(f"  {'키워드':20s} {'상품수':>10s} {'평균가격':>12s} {'가격범위':>20s} {'트렌드':>8s} {'TOP 브랜드':20s}")
            print(f"  {'-'*92}")

            for r in results:
                top_brand = r['top_brands'][0]['name'] if r['top_brands'] else '-'
                price_range = f"{r['min_price']:,}~{r['max_price']:,}" if r['min_price'] > 0 else '-'

                trend_icon = {'rising': 'UP', 'falling': 'DOWN', 'stable': '-'}.get(r['price_trend'], '-')

                print(
                    f"  {r['query_keyword']:20s} "
                    f"{r['total_results']:>10,} "
                    f"{r['avg_price']:>11,}원 "
                    f"{price_range:>20s} "
                    f"{trend_icon:>8s} "
                    f"{top_brand:20s}"
                )

            # TOP 상품 상세
            print(f"\n  [TOP 상품 상세]")
            for r in results:
                if r['top_products']:
                    print(f"\n  [{r['query_keyword']}]")
                    for i, product in enumerate(r['top_products'][:3], 1):
                        print(f"    {i}. {product['title'][:40]}... - {product['price']:,}원 ({product['mall_name']})")

        print(f"\n{'='*60}")

        return results


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        monitor = NaverShopTrendMonitor()
        monitor.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
