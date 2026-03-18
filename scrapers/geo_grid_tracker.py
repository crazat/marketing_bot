#!/usr/bin/env python3
"""
Geo-Grid 순위 추적기
- 지리적 격자(Grid) 기반으로 네이버 플레이스 순위를 다양한 위치에서 측정
- Average Ranking Position (ARP) 산출
- 각 격자 지점에서의 순위를 시각화 데이터로 제공
"""
import sys
import os
import time
import json
import math
import uuid
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple

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


class GeoGridTracker:
    """
    Geo-Grid 기반 순위 추적기.
    다양한 지리적 지점에서 네이버 로컬 검색을 실행하여
    위치별 순위 차이를 분석합니다.
    """

    NAVER_LOCAL_SEARCH_URL = "https://openapi.naver.com/v1/search/local.json"

    # 기본 격자 설정
    DEFAULT_GRID_SIZE = 5          # 5x5 격자
    DEFAULT_RADIUS_KM = 3.0        # 반경 3km

    # 청주시 성안길 기본 중심 좌표
    DEFAULT_CENTER_LAT = 36.6372
    DEFAULT_CENTER_LNG = 127.4895

    def __init__(self, grid_size: int = None, radius_km: float = None):
        self.db = DatabaseManager()
        self.config = ConfigManager()

        # Naver API Keys (NAVER_SEARCH_KEYS 우선, 폴백: NAVER_CLIENT_ID)
        self.api_keys = []
        search_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS") if hasattr(self.config, 'get_api_key_list') else []
        if search_keys:
            self.api_keys = search_keys
        else:
            cid = self.config.get_api_key("NAVER_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
            if cid and sec:
                self.api_keys = [{"id": cid, "secret": sec}]
        self._current_key_idx = 0
        self.client_id = self.api_keys[0]["id"] if self.api_keys else None
        self.client_secret = self.api_keys[0]["secret"] if self.api_keys else None

        # Grid settings
        self.grid_size = grid_size or self.DEFAULT_GRID_SIZE
        self.radius_km = radius_km or self.DEFAULT_RADIUS_KM

        # Load business profile
        self.business_name = None
        self.business_short_names = []
        self.center_lat = self.DEFAULT_CENTER_LAT
        self.center_lng = self.DEFAULT_CENTER_LNG
        self._load_business_profile()

        # Load keywords
        self.keywords = self._load_keywords()

        # Ensure DB table
        self._ensure_table()

    def _load_business_profile(self):
        """config/business_profile.json에서 업체 정보 및 위치 로드"""
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

                # Location from profile if available
                location = data.get('location', {})
                if location.get('latitude'):
                    self.center_lat = float(location['latitude'])
                if location.get('longitude'):
                    self.center_lng = float(location['longitude'])

                logger.info(f"Business profile loaded: {self.business_name} at ({self.center_lat}, {self.center_lng})")
            else:
                logger.warning(f"Business profile not found, using defaults: ({self.center_lat}, {self.center_lng})")
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
                logger.info(f"Loaded {len(keywords)} keywords")
                return keywords
            else:
                logger.warning(f"Keywords file not found: {kw_path}")
                return []
        except Exception as e:
            logger.error(f"Error loading keywords: {e}")
            return []

    def _ensure_table(self):
        """geo_grid_rankings 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS geo_grid_rankings (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scan_session_id TEXT NOT NULL,
                        keyword TEXT NOT NULL,
                        grid_label TEXT NOT NULL,
                        grid_lat REAL NOT NULL,
                        grid_lng REAL NOT NULL,
                        rank INTEGER,
                        total_results INTEGER DEFAULT 0,
                        place_name TEXT,
                        status TEXT DEFAULT 'found',
                        arp REAL,
                        scanned_at TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_geo_grid_session
                    ON geo_grid_rankings(scan_session_id)
                ''')
                cursor.execute('''
                    CREATE INDEX IF NOT EXISTS idx_geo_grid_keyword_date
                    ON geo_grid_rankings(keyword, scanned_at)
                ''')
                conn.commit()
                logger.info("geo_grid_rankings table ensured")
        except Exception as e:
            logger.error(f"Error creating geo_grid_rankings table: {e}")

    def generate_grid_points(self) -> List[Dict[str, Any]]:
        """
        중심점을 기준으로 NxN 격자 포인트를 생성합니다.

        Returns:
            List of {label: "A1", lat: float, lng: float}
        """
        points = []
        half = self.grid_size // 2

        # 1도 위도 = 약 111km, 1도 경도 = 약 88.8km (위도 36도 기준)
        lat_step = self.radius_km / 111.0 * 2 / (self.grid_size - 1) if self.grid_size > 1 else 0
        lng_step = self.radius_km / (111.0 * math.cos(math.radians(self.center_lat))) * 2 / (self.grid_size - 1) if self.grid_size > 1 else 0

        for row in range(self.grid_size):
            for col in range(self.grid_size):
                lat_offset = (row - half) * lat_step
                lng_offset = (col - half) * lng_step

                label = f"{chr(65 + row)}{col + 1}"  # A1, A2, ... B1, B2, ...
                points.append({
                    "label": label,
                    "lat": round(self.center_lat + lat_offset, 6),
                    "lng": round(self.center_lng + lng_offset, 6),
                })

        logger.info(f"Generated {len(points)} grid points ({self.grid_size}x{self.grid_size}, radius={self.radius_km}km)")
        return points

    def search_naver_local(self, keyword: str) -> Optional[Dict[str, Any]]:
        """
        네이버 로컬 검색 API 호출

        Note: 네이버 로컬 검색 API는 좌표 기반 검색을 직접 지원하지 않으므로
        키워드에 지역명을 포함하여 검색합니다.

        Args:
            keyword: 검색 키워드

        Returns:
            API 응답 dict 또는 None
        """
        import requests

        params = {
            "query": keyword,
            "display": 20,
            "sort": "random",  # 정확도순
        }

        # 키 로테이션 시도 (모든 키를 순회)
        max_attempts = len(self.api_keys) if self.api_keys else 1
        try:
            for attempt in range(max_attempts):
                key_data = self.api_keys[self._current_key_idx] if self.api_keys else {}
                headers = {
                    "X-Naver-Client-Id": key_data.get("id", self.client_id or ""),
                    "X-Naver-Client-Secret": key_data.get("secret", self.client_secret or ""),
                }

                response = requests.get(
                    self.NAVER_LOCAL_SEARCH_URL,
                    headers=headers,
                    params=params,
                    timeout=10
                )

                if response.status_code == 200:
                    return response.json()
                elif response.status_code in (401, 429):
                    if attempt < max_attempts - 1:
                        self._current_key_idx = (self._current_key_idx + 1) % len(self.api_keys)
                        logger.info(f"키 로테이션: 키 #{self._current_key_idx + 1}로 전환")
                        time.sleep(0.5)
                        continue
                    logger.error(f"Naver Local API error: {response.status_code} - {response.text[:200]}")
                    return None
                else:
                    logger.error(f"Naver Local API error: {response.status_code} - {response.text[:200]}")
                    return None
        except requests.exceptions.Timeout:
            logger.warning(f"Naver Local API timeout: {keyword}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Naver Local API request failed: {e}")
            return None

    def _is_our_clinic(self, title: str) -> bool:
        """검색 결과의 업체명이 우리 한의원인지 확인"""
        if not self.business_name:
            return False
        # Naver Local API returns HTML tags in title
        import re
        clean_title = re.sub(r'<[^>]+>', '', title).strip()
        for name in self.business_short_names:
            if name and name in clean_title:
                return True
        return False

    def find_rank_at_point(self, keyword: str, grid_point: Dict[str, Any]) -> Dict[str, Any]:
        """
        특정 격자 지점에서의 순위를 검색합니다.

        네이버 로컬 검색 API는 좌표 기반 필터를 직접 지원하지 않으므로,
        키워드 그대로 검색 후 순위를 확인합니다.
        (실제 프로덕션에서는 모바일 네이버 Place 검색을 좌표와 함께 사용할 수 있습니다)

        Returns:
            {
                "grid_label": str,
                "grid_lat": float,
                "grid_lng": float,
                "rank": int or None,
                "total_results": int,
                "place_name": str or None,
                "status": "found" | "not_in_results" | "error"
            }
        """
        import re

        result = {
            "grid_label": grid_point["label"],
            "grid_lat": grid_point["lat"],
            "grid_lng": grid_point["lng"],
            "rank": None,
            "total_results": 0,
            "place_name": None,
            "status": "not_in_results"
        }

        data = self.search_naver_local(keyword)
        if not data:
            result["status"] = "error"
            return result

        items = data.get("items", [])
        result["total_results"] = data.get("total", 0)

        for idx, item in enumerate(items, 1):
            title = re.sub(r'<[^>]+>', '', item.get("title", "")).strip()
            if self._is_our_clinic(item.get("title", "")):
                result["rank"] = idx
                result["place_name"] = title
                result["status"] = "found"
                return result

        return result

    def calculate_arp(self, grid_results: List[Dict[str, Any]], max_rank: int = 21) -> Optional[float]:
        """
        Average Ranking Position (ARP) 산출

        순위를 찾지 못한 경우 max_rank를 할당하여 페널티를 부여합니다.

        Args:
            grid_results: 격자별 순위 결과 리스트
            max_rank: 순위권 밖일 때 부여할 값

        Returns:
            ARP 값 또는 None (결과가 없는 경우)
        """
        if not grid_results:
            return None

        ranks = []
        for r in grid_results:
            if r["status"] == "found" and r["rank"] is not None:
                ranks.append(r["rank"])
            elif r["status"] != "error":
                ranks.append(max_rank)
            # error 상태는 계산에서 제외

        if not ranks:
            return None

        return round(sum(ranks) / len(ranks), 2)

    def save_results(self, session_id: str, keyword: str, grid_results: List[Dict[str, Any]], arp: Optional[float]):
        """격자별 결과를 DB에 저장"""
        try:
            scanned_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                for result in grid_results:
                    cursor.execute('''
                        INSERT INTO geo_grid_rankings
                        (scan_session_id, keyword, grid_label, grid_lat, grid_lng,
                         rank, total_results, place_name, status, arp, scanned_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        session_id,
                        keyword,
                        result["grid_label"],
                        result["grid_lat"],
                        result["grid_lng"],
                        result["rank"],
                        result["total_results"],
                        result["place_name"],
                        result["status"],
                        arp,
                        scanned_at
                    ))
                conn.commit()
                logger.debug(f"Saved {len(grid_results)} grid results for '{keyword}' (ARP: {arp})")
        except Exception as e:
            logger.error(f"Error saving geo grid results: {e}")
            logger.error(traceback.format_exc())

    def run(self, keywords: List[str] = None):
        """
        Geo-Grid 순위 추적 실행

        Args:
            keywords: 추적할 키워드 목록 (None이면 config에서 로드)
        """
        if not self.client_id or not self.client_secret:
            logger.warning("NAVER_CLIENT_ID / NAVER_CLIENT_SECRET not configured. Skipping geo-grid tracking.")
            print("[Geo-Grid Tracker] Naver API keys not configured. "
                  "Set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET in config/secrets.json or environment.")
            return

        if not self.business_name:
            logger.warning("Business name not configured. Cannot track rankings.")
            return

        target_keywords = keywords or self.keywords
        if not target_keywords:
            logger.warning("No keywords to track. Check config/keywords.json")
            return

        # Generate grid
        grid_points = self.generate_grid_points()
        session_id = str(uuid.uuid4())

        print(f"[{datetime.now()}] Geo-Grid Tracker 시작")
        print(f"  업체명: {self.business_name}")
        print(f"  중심좌표: ({self.center_lat}, {self.center_lng})")
        print(f"  격자: {self.grid_size}x{self.grid_size} ({len(grid_points)}개 지점), 반경: {self.radius_km}km")
        print(f"  세션 ID: {session_id[:8]}...")
        print(f"  키워드: {len(target_keywords)}개")
        print()

        total_scans = len(target_keywords) * len(grid_points)
        completed = 0

        for kw_idx, keyword in enumerate(target_keywords, 1):
            print(f"[{kw_idx}/{len(target_keywords)}] '{keyword}' 격자 스캔 중...")

            grid_results = []
            for point in grid_points:
                try:
                    result = self.find_rank_at_point(keyword, point)
                    grid_results.append(result)
                    completed += 1

                    # Progress indicator
                    rank_str = f"{result['rank']}위" if result['rank'] else "-"
                    if completed % 5 == 0 or completed == total_scans:
                        print(f"  [{completed}/{total_scans}] {point['label']}: {rank_str}")

                    # Rate limit between API calls
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error scanning grid point {point['label']}: {e}")
                    grid_results.append({
                        "grid_label": point["label"],
                        "grid_lat": point["lat"],
                        "grid_lng": point["lng"],
                        "rank": None,
                        "total_results": 0,
                        "place_name": None,
                        "status": "error"
                    })

            # Calculate ARP
            arp = self.calculate_arp(grid_results)

            # Save to DB
            self.save_results(session_id, keyword, grid_results, arp)

            # Print summary for this keyword
            found = sum(1 for r in grid_results if r["status"] == "found")
            print(f"  -> ARP: {arp if arp else 'N/A'} | 순위 발견: {found}/{len(grid_results)}")
            print()

        print(f"[{datetime.now()}] Geo-Grid Tracker 완료")
        print(f"  총 스캔: {completed}건 ({len(target_keywords)}키워드 x {len(grid_points)}지점)")
        print(f"  세션 ID: {session_id}")

    def get_latest_session(self, keyword: str = None) -> Optional[str]:
        """최근 세션 ID 조회"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                if keyword:
                    cursor.execute('''
                        SELECT scan_session_id FROM geo_grid_rankings
                        WHERE keyword = ?
                        ORDER BY scanned_at DESC LIMIT 1
                    ''', (keyword,))
                else:
                    cursor.execute('''
                        SELECT scan_session_id FROM geo_grid_rankings
                        ORDER BY scanned_at DESC LIMIT 1
                    ''')
                row = cursor.fetchone()
                return row[0] if row else None
        except Exception as e:
            logger.error(f"Error fetching latest session: {e}")
            return None

    def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """세션 요약 정보 조회"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT keyword, grid_label, rank, status, arp, scanned_at
                    FROM geo_grid_rankings
                    WHERE scan_session_id = ?
                    ORDER BY keyword, grid_label
                ''', (session_id,))
                rows = cursor.fetchall()

                if not rows:
                    return {}

                summary = {}
                for row in rows:
                    kw = row[0]
                    if kw not in summary:
                        summary[kw] = {
                            "arp": row[4],
                            "scanned_at": row[5],
                            "grid_points": []
                        }
                    summary[kw]["grid_points"].append({
                        "label": row[1],
                        "rank": row[2],
                        "status": row[3]
                    })

                return summary
        except Exception as e:
            logger.error(f"Error fetching session summary: {e}")
            return {}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Geo-Grid Rank Tracker")
    parser.add_argument("--grid", type=int, default=5, help="Grid size (default: 5 for 5x5)")
    parser.add_argument("--radius", type=float, default=3.0, help="Radius in km (default: 3.0)")
    parser.add_argument("--keyword", type=str, help="Single keyword to track (optional)")
    args = parser.parse_args()

    tracker = GeoGridTracker(grid_size=args.grid, radius_km=args.radius)

    if args.keyword:
        tracker.run(keywords=[args.keyword])
    else:
        tracker.run()
