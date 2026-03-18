#!/usr/bin/env python3
"""
Review Intelligence Collector - 경쟁사 리뷰 인텔리전스 수집기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

경쟁사 네이버 플레이스의 리뷰 메타데이터를 수집/분석합니다.
- 총 리뷰 수, 평균 평점, 별점 분포, 사진 리뷰 비율
- 경쟁사 리뷰 응답률
- 의심스러운 패턴 감지 (같은 날 대량 리뷰, 유사 텍스트 등)
- Naver Place GraphQL API 활용
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
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import Optional, Dict, List, Any, Tuple

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
# Constants
# ============================================================================

GRAPHQL_ENDPOINT = "https://pcmap-api.place.naver.com/graphql"

GRAPHQL_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "*/*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://pcmap.place.naver.com",
    "Referer": "https://pcmap.place.naver.com/",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# 리뷰 데이터 GraphQL 쿼리
REVIEW_LIST_QUERY = [
    {
        "operationName": "getVisitorReviews",
        "variables": {
            "input": {
                "businessId": None,  # 런타임에 채움
                "businessType": "restaurant",
                "item": "0",
                "bookingBusinessId": None,
                "page": 1,
                "size": 50,
                "isPhotoUsed": False,
                "includeContent": True,
                "getUserStats": True,
                "includeReceiptPhotos": True,
                "cidList": [],
            }
        },
        "query": """query getVisitorReviews($input: VisitorReviewsInput) {
            visitorReviews(input: $input) {
                items {
                    id
                    rating
                    author { nickname }
                    body
                    thumbnail
                    media { type }
                    created
                    reply { body created }
                }
                starDistribution { score count }
                total
                avgRating
            }
        }"""
    }
]


class ReviewIntelligenceCollector:
    """경쟁사 네이버 플레이스 리뷰 인텔리전스를 수집합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_targets()
        self._last_request_time = 0

    def _ensure_table(self):
        """review_intelligence 테이블이 없으면 생성합니다."""
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
                CREATE INDEX IF NOT EXISTS idx_review_intel_competitor_date
                ON review_intelligence (competitor_name, collected_at)
            """)
            conn.commit()
        logger.info("review_intelligence 테이블 준비 완료")

    def _load_targets(self):
        """config/targets.json에서 경쟁사 목록을 로드합니다."""
        self.targets = []
        targets_path = os.path.join(project_root, 'config', 'targets.json')

        try:
            if os.path.exists(targets_path):
                with open(targets_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.targets = data.get('targets', [])
        except Exception as e:
            logger.error(f"targets.json 로드 실패: {e}")

        logger.info(f"경쟁사 {len(self.targets)}개 로드")

    def _extract_place_id(self, naver_place_url: str) -> Optional[str]:
        """네이버 플레이스 URL에서 place_id를 추출합니다."""
        if not naver_place_url:
            return None
        # https://m.place.naver.com/restaurant/12345/home
        # https://m.place.naver.com/hospital/12345/home
        match = re.search(r'place\.naver\.com/\w+/(\d+)', naver_place_url)
        if match:
            return match.group(1)
        return None

    def _rate_limit(self, min_delay: float = 2.0):
        """요청 간 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        delay = random.uniform(min_delay, min_delay + 1.0)
        if elapsed < delay:
            time.sleep(delay - elapsed)
        self._last_request_time = time.time()

    def _fetch_reviews_graphql(self, place_id: str, page: int = 1, size: int = 50) -> Optional[Dict]:
        """GraphQL API를 통해 리뷰 데이터를 가져옵니다."""
        query_body = json.loads(json.dumps(REVIEW_LIST_QUERY))
        query_body[0]["variables"]["input"]["businessId"] = place_id
        query_body[0]["variables"]["input"]["page"] = page
        query_body[0]["variables"]["input"]["size"] = size

        try:
            response = requests.post(
                GRAPHQL_ENDPOINT,
                headers=GRAPHQL_HEADERS,
                json=query_body,
                timeout=15
            )
            response.raise_for_status()

            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get('data', {}).get('visitorReviews', {})
            elif isinstance(data, dict):
                return data.get('data', {}).get('visitorReviews', {})
            return None

        except requests.exceptions.RequestException as e:
            logger.warning(f"GraphQL 요청 실패 (place_id={place_id}): {e}")
            return None

    def _fetch_reviews_fallback(self, place_id: str) -> Optional[Dict]:
        """GraphQL 실패 시 모바일 웹페이지에서 리뷰 데이터를 파싱합니다."""
        url = f"https://m.place.naver.com/restaurant/{place_id}/review/visitor"
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept-Language": "ko-KR,ko;q=0.9",
        }

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')

            # 총 리뷰 수 추출 시도
            total_el = soup.select_one('.place_section_count')
            total_reviews = 0
            if total_el:
                num_match = re.search(r'[\d,]+', total_el.get_text())
                if num_match:
                    total_reviews = int(num_match.group().replace(',', ''))

            return {
                "total": total_reviews,
                "items": [],
                "avgRating": 0,
                "starDistribution": [],
            }

        except Exception as e:
            logger.warning(f"폴백 리뷰 파싱 실패 (place_id={place_id}): {e}")
            return None

    def _get_last_total_reviews(self, competitor_name: str) -> int:
        """마지막 수집 시 총 리뷰 수를 가져옵니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT total_reviews FROM review_intelligence
                    WHERE competitor_name = ?
                    ORDER BY collected_at DESC
                    LIMIT 1
                """, (competitor_name,))
                row = cursor.fetchone()
                if row:
                    return row[0] or 0
        except Exception as e:
            logger.debug(f"이전 리뷰 수 조회 실패: {e}")
        return 0

    def _detect_suspicious_patterns(self, reviews: List[Dict]) -> Tuple[List[str], int]:
        """
        의심스러운 리뷰 패턴을 감지합니다.

        Returns:
            (patterns_list, suspicious_score)
        """
        if not reviews:
            return [], 0

        patterns = []
        score = 0

        # 1. 같은 날 대량 리뷰 감지
        date_counter = Counter()
        for review in reviews:
            created = review.get('created', '')
            if created:
                # "2024-01-15" 형식 또는 timestamp
                date_str = created[:10] if len(created) >= 10 else created
                date_counter[date_str] += 1

        for date, count in date_counter.items():
            if count >= 5:
                patterns.append(f"같은 날 {count}건 리뷰 ({date})")
                score += count * 2

        # 2. 매우 짧은 리뷰 비율
        short_reviews = 0
        for review in reviews:
            body = review.get('body', '') or ''
            if len(body.strip()) < 10:
                short_reviews += 1

        if len(reviews) > 0:
            short_ratio = short_reviews / len(reviews)
            if short_ratio > 0.5:
                patterns.append(f"짧은 리뷰 비율 높음: {short_ratio:.0%} ({short_reviews}/{len(reviews)})")
                score += 10

        # 3. 유사 텍스트 패턴 감지 (간단한 해시 기반)
        text_hashes = defaultdict(int)
        for review in reviews:
            body = review.get('body', '') or ''
            # 공백 제거 후 앞 20자로 해시
            normalized = re.sub(r'\s+', '', body)[:20]
            if normalized:
                text_hashes[normalized] += 1

        for text_prefix, count in text_hashes.items():
            if count >= 3:
                patterns.append(f"유사 텍스트 패턴 {count}건 감지")
                score += count * 3
                break  # 하나만 보고

        # 4. 모든 리뷰가 5점인 경우
        all_five = all(review.get('rating', 0) == 5 for review in reviews if review.get('rating'))
        if all_five and len(reviews) >= 10:
            patterns.append("모든 리뷰가 5점 (의심)")
            score += 15

        return patterns, score

    def collect_competitor_reviews(self, target: Dict) -> Optional[Dict[str, Any]]:
        """단일 경쟁사의 리뷰 인텔리전스를 수집합니다."""
        name = target.get('name', 'Unknown')
        monitor_urls = target.get('monitor_urls', {})
        naver_place_url = monitor_urls.get('naver_place', '')
        place_id = self._extract_place_id(naver_place_url)

        if not place_id:
            logger.info(f"[{name}] 네이버 플레이스 URL 없음, 건너뜀")
            return None

        print(f"  [{name}] place_id={place_id} 리뷰 수집 중...", end=" ")

        self._rate_limit()

        # GraphQL로 리뷰 가져오기
        review_data = self._fetch_reviews_graphql(place_id)

        if not review_data:
            logger.info(f"[{name}] GraphQL 실패, 폴백 시도...")
            self._rate_limit(min_delay=1.0)
            review_data = self._fetch_reviews_fallback(place_id)

        if not review_data:
            print("-> 수집 실패")
            return None

        # 데이터 추출
        total_reviews = review_data.get('total', 0) or 0
        avg_rating = review_data.get('avgRating', 0) or 0
        items = review_data.get('items', []) or []
        star_dist_raw = review_data.get('starDistribution', []) or []

        # 별점 분포 정리
        rating_distribution = {}
        for entry in star_dist_raw:
            star = entry.get('score', 0)
            count = entry.get('count', 0)
            rating_distribution[str(star)] = count

        # 사진 리뷰 계산
        photo_review_count = 0
        for review in items:
            has_photo = False
            if review.get('thumbnail'):
                has_photo = True
            media = review.get('media', []) or []
            if media:
                has_photo = True
            if has_photo:
                photo_review_count += 1

        photo_review_ratio = (photo_review_count / len(items)) if items else 0

        # 응답률 계산
        response_count = sum(1 for r in items if r.get('reply'))
        response_rate = (response_count / len(items)) if items else 0

        # 신규 리뷰 계산
        last_total = self._get_last_total_reviews(name)
        new_reviews = max(0, total_reviews - last_total) if last_total > 0 else 0

        # 의심 패턴 감지
        suspicious_patterns, suspicious_score = self._detect_suspicious_patterns(items)

        result = {
            "competitor_name": name,
            "place_id": place_id,
            "total_reviews": total_reviews,
            "avg_rating": round(avg_rating, 2),
            "rating_distribution": rating_distribution,
            "photo_review_count": photo_review_count,
            "photo_review_ratio": round(photo_review_ratio, 3),
            "response_count": response_count,
            "response_rate": round(response_rate, 3),
            "new_reviews_since_last": new_reviews,
            "suspicious_patterns": suspicious_patterns,
            "suspicious_score": suspicious_score,
            "review_count_fetched": len(items),
        }

        status_parts = [f"총 {total_reviews}건"]
        if avg_rating:
            status_parts.append(f"평점 {avg_rating:.1f}")
        if new_reviews > 0:
            status_parts.append(f"신규 +{new_reviews}")
        if suspicious_score > 0:
            status_parts.append(f"의심점수 {suspicious_score}")

        print(f"-> {' | '.join(status_parts)}")

        return result

    def _save_result(self, result: Dict[str, Any]):
        """결과를 DB에 저장합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO review_intelligence
                    (competitor_name, place_id, total_reviews, avg_rating,
                     rating_distribution, photo_review_count, photo_review_ratio,
                     response_count, response_rate, new_reviews_since_last,
                     suspicious_patterns, suspicious_score, raw_data, collected_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    result['competitor_name'],
                    result['place_id'],
                    result['total_reviews'],
                    result['avg_rating'],
                    json.dumps(result['rating_distribution'], ensure_ascii=False),
                    result['photo_review_count'],
                    result['photo_review_ratio'],
                    result['response_count'],
                    result['response_rate'],
                    result['new_reviews_since_last'],
                    json.dumps(result['suspicious_patterns'], ensure_ascii=False),
                    result['suspicious_score'],
                    json.dumps(result, ensure_ascii=False, default=str),
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB 저장 오류 [{result.get('competitor_name')}]: {e}")
            logger.debug(traceback.format_exc())

    def run(self):
        """전체 경쟁사에 대해 리뷰 인텔리전스를 수집합니다."""
        # 네이버 플레이스 URL이 있는 경쟁사만 필터
        valid_targets = [
            t for t in self.targets
            if t.get('monitor_urls', {}).get('naver_place')
        ]

        if not valid_targets:
            print("네이버 플레이스 URL이 있는 경쟁사가 없습니다.")
            return

        print(f"\n{'='*60}")
        print(f" Review Intelligence Collector")
        print(f" 대상 경쟁사: {len(valid_targets)}개")
        print(f" 시작 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*60}\n")

        results = []
        success_count = 0
        error_count = 0

        for idx, target in enumerate(valid_targets, 1):
            name = target.get('name', 'Unknown')
            print(f"\n  [{idx}/{len(valid_targets)}] ", end="")

            try:
                result = self.collect_competitor_reviews(target)
                if result:
                    self._save_result(result)
                    results.append(result)
                    success_count += 1
                else:
                    error_count += 1
            except Exception as e:
                error_count += 1
                print(f"  [{name}] 오류: {e}")
                logger.error(f"[{name}] 수집 오류: {e}")
                logger.debug(traceback.format_exc())

        # 결과 요약
        print(f"\n{'='*60}")
        print(f" 수집 완료! 성공: {success_count}/{len(valid_targets)}")
        if error_count:
            print(f" 실패: {error_count}건")
        print(f"{'='*60}")

        # 의심 패턴 요약
        suspicious_results = [r for r in results if r.get('suspicious_score', 0) > 0]
        if suspicious_results:
            print(f"\n 의심 패턴 감지된 경쟁사:")
            for r in sorted(suspicious_results, key=lambda x: x['suspicious_score'], reverse=True):
                print(f"   [{r['competitor_name']}] 점수: {r['suspicious_score']}")
                for pattern in r['suspicious_patterns']:
                    print(f"     - {pattern}")

        # 응답률 비교
        if results:
            print(f"\n 경쟁사 리뷰 응답률:")
            for r in sorted(results, key=lambda x: x['response_rate'], reverse=True):
                bar = '#' * int(r['response_rate'] * 20)
                print(f"   {r['competitor_name']:20s} | {r['response_rate']:.0%} {bar}")

        return results


if __name__ == "__main__":
    try:
        collector = ReviewIntelligenceCollector()
        collector.run()
    except KeyboardInterrupt:
        print("\n사용자에 의해 중단되었습니다.")
    except Exception as e:
        logger.error(f"치명적 오류: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
