#!/usr/bin/env python3
"""
KakaoMap 순위 추적기
- KakaoMap Local Search API를 사용하여 키워드별 순위 추적
- 우리 한의원의 카카오맵 검색 순위를 모니터링
"""
import sys
import os
import time
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any

# Robust Path Setup for Hybrid Execution (Standalone vs Module)
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)

try:
    from db.database import DatabaseManager
    from utils import ConfigManager, logger
except ImportError:
    print("Import Error: Check directory structure.")
    sys.exit(1)

# Force UTF-8 output
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger(__name__)


class KakaoMapTracker:
    """
    KakaoMap Local Search API를 이용한 순위 추적기.
    카카오맵에서 키워드 검색 시 우리 한의원의 순위를 기록합니다.
    """

    KAKAO_LOCAL_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/keyword.json"

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # API Key
        self.api_key = self.config.get_api_key("KAKAO_REST_API_KEY")

        # Load business profile
        self.business_name = None
        self.business_short_names = []
        self.default_lat = 36.6372   # 청주시 성안길 기본값
        self.default_lng = 127.4895
        self._load_business_profile()

        # Load keywords
        self.keywords = self._load_keywords()

        # Ensure DB table exists
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
                short_name = business.get('short_name', '')
                self.business_short_names = [
                    self.business_name,
                    short_name,
                ] if short_name else [self.business_name]

                # location from profile if available
                location = data.get('location', {})
                if location.get('latitude'):
                    self.default_lat = float(location['latitude'])
                if location.get('longitude'):
                    self.default_lng = float(location['longitude'])

                logger.info(f"Business profile loaded: {self.business_name}")
            else:
                logger.warning(f"Business profile not found: {profile_path}")
        except Exception as e:
            logger.error(f"Error loading business profile: {e}")

    def _load_keywords(self) -> List[str]:
        """config/keywords.json에서 naver_place 키워드 목록 로드"""
        kw_path = os.path.join(project_root, 'config', 'keywords.json')
        try:
            if os.path.exists(kw_path):
                with open(kw_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                keywords = data.get('naver_place', [])
                logger.info(f"Loaded {len(keywords)} keywords from keywords.json")
                return keywords
            else:
                logger.warning(f"Keywords file not found: {kw_path}")
                return []
        except Exception as e:
            logger.error(f"Error loading keywords: {e}")
            return []

    def _ensure_table(self):
        """kakao_rank_history 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS kakao_rank_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        rank INTEGER,
                        total_results INTEGER DEFAULT 0,
                        place_name TEXT,
                        place_id TEXT,
                        category TEXT,
                        address TEXT,
                        status TEXT DEFAULT 'found',
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_kakao_rank_keyword_date
                    ON kakao_rank_history(keyword, scanned_at)
                ''')
                conn.commit()
                logger.info("kakao_rank_history table ensured")
        except Exception as e:
            logger.error(f"Error creating kakao_rank_history table: {e}")

    def _is_our_clinic(self, place_name: str) -> bool:
        """검색 결과의 업체명이 우리 한의원인지 확인"""
        if not self.business_name:
            return False
        place_lower = place_name.strip()
        for name in self.business_short_names:
            if name and name in place_lower:
                return True
        return False

    def search_kakao_map(self, keyword: str, page: int = 1) -> Optional[Dict[str, Any]]:
        """
        KakaoMap Local Search API 호출

        Args:
            keyword: 검색 키워드
            page: 페이지 번호 (1~45)

        Returns:
            API 응답 dict 또는 None
        """
        import requests

        headers = {
            "Authorization": f"KakaoAK {self.api_key}"
        }
        params = {
            "query": keyword,
            "x": str(self.default_lng),  # longitude
            "y": str(self.default_lat),  # latitude
            "radius": 20000,             # 20km 반경
            "category_group_code": "HP8", # 한의원/한방병원
            "page": page,
            "size": 15,                  # 페이지당 최대 15개
            "sort": "accuracy"
        }

        try:
            response = requests.get(
                self.KAKAO_LOCAL_SEARCH_URL,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                logger.error("KakaoMap API 인증 실패: API 키를 확인하세요")
                return None
            elif response.status_code == 429:
                logger.warning("KakaoMap API 호출 제한 초과, 잠시 대기...")
                time.sleep(5)
                return None
            else:
                logger.error(f"KakaoMap API 오류: {response.status_code} - {response.text[:200]}")
                return None

        except requests.exceptions.Timeout:
            logger.warning(f"KakaoMap API 타임아웃: {keyword}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"KakaoMap API 요청 실패: {e}")
            return None

    def find_rank_for_keyword(self, keyword: str) -> Dict[str, Any]:
        """
        키워드에 대한 우리 한의원의 카카오맵 순위를 찾습니다.
        최대 3페이지(45개 결과)까지 검색합니다.

        Returns:
            {
                "keyword": str,
                "rank": int or None,
                "total_results": int,
                "place_name": str or None,
                "place_id": str or None,
                "category": str or None,
                "address": str or None,
                "status": "found" | "not_in_results" | "error"
            }
        """
        result = {
            "keyword": keyword,
            "rank": None,
            "total_results": 0,
            "place_name": None,
            "place_id": None,
            "category": None,
            "address": None,
            "status": "not_in_results"
        }

        overall_rank = 0

        for page in range(1, 4):  # 최대 3페이지
            data = self.search_kakao_map(keyword, page=page)
            if not data:
                if page == 1:
                    result["status"] = "error"
                break

            documents = data.get("documents", [])
            meta = data.get("meta", {})
            result["total_results"] = meta.get("total_count", 0)

            for doc in documents:
                overall_rank += 1
                place_name = doc.get("place_name", "")

                if self._is_our_clinic(place_name):
                    result["rank"] = overall_rank
                    result["place_name"] = place_name
                    result["place_id"] = doc.get("id", "")
                    result["category"] = doc.get("category_name", "")
                    result["address"] = doc.get("road_address_name", "") or doc.get("address_name", "")
                    result["status"] = "found"
                    return result

            # 더 이상 결과가 없으면 중단
            if meta.get("is_end", True):
                break

            time.sleep(0.5)  # Rate limit between pages

        return result

    def save_result(self, result: Dict[str, Any]):
        """검색 결과를 DB에 저장"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT INTO kakao_rank_history
                    (keyword, rank, total_results, place_name, place_id, category, address, status, scanned_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    result["keyword"],
                    result["rank"],
                    result["total_results"],
                    result["place_name"],
                    result["place_id"],
                    result["category"],
                    result["address"],
                    result["status"],
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
                logger.debug(f"Saved kakao rank: {result['keyword']} -> {result['rank']}")
        except Exception as e:
            logger.error(f"Error saving kakao rank result: {e}")
            logger.error(traceback.format_exc())

    def run(self):
        """전체 키워드에 대해 카카오맵 순위 추적 실행"""
        if not self.api_key:
            logger.warning("KAKAO_REST_API_KEY not configured. Skipping KakaoMap tracking.")
            print("[KakaoMap Tracker] API key not configured. Set KAKAO_REST_API_KEY in config/secrets.json or environment.")
            return

        if not self.business_name:
            logger.warning("Business name not configured. Cannot track rankings.")
            return

        if not self.keywords:
            logger.warning("No keywords to track. Check config/keywords.json")
            return

        print(f"[{datetime.now()}] KakaoMap Tracker 시작: {len(self.keywords)}개 키워드")
        print(f"  업체명: {self.business_name}")
        print(f"  중심좌표: ({self.default_lat}, {self.default_lng})")
        print()

        found_count = 0
        error_count = 0

        for i, keyword in enumerate(self.keywords, 1):
            try:
                print(f"[{i}/{len(self.keywords)}] '{keyword}' 검색 중...")
                result = self.find_rank_for_keyword(keyword)
                self.save_result(result)

                if result["status"] == "found":
                    print(f"  -> {result['rank']}위 (총 {result['total_results']}개)")
                    found_count += 1
                elif result["status"] == "not_in_results":
                    print(f"  -> 순위권 밖 (총 {result['total_results']}개)")
                else:
                    print(f"  -> 오류 발생")
                    error_count += 1

                # Rate limit between keywords
                if i < len(self.keywords):
                    time.sleep(0.5)

            except Exception as e:
                logger.error(f"Error tracking keyword '{keyword}': {e}")
                logger.error(traceback.format_exc())
                error_count += 1

        print()
        print(f"[{datetime.now()}] KakaoMap Tracker 완료")
        print(f"  순위 발견: {found_count}/{len(self.keywords)}")
        if error_count:
            print(f"  오류: {error_count}건")


if __name__ == "__main__":
    tracker = KakaoMapTracker()
    tracker.run()
