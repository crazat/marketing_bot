#!/usr/bin/env python3
"""
Search Demographics Analyzer - 검색 인구통계 분석기
====================================================

네이버 DataLab API를 사용하여 각 키워드의 검색자 연령/성별 분포를 분석합니다.
- 연령대별 상대적 검색 비율 비교 (19세 이상)
- 성별 검색 비율 비교
- 주요 타겟 인구통계 자동 식별
- 4개 API 키 라운드로빈 로테이션

Usage:
    python scrapers/search_demographics_analyzer.py
"""

import sys
import os
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

DATALAB_API_URL = "https://openapi.naver.com/v1/datalab/search"
RATE_LIMIT_DELAY = 0.5  # seconds between requests

# Age group codes and labels
AGE_GROUPS = {
    "3": "19-24",
    "4": "25-29",
    "5": "30-34",
    "6": "35-39",
    "7": "40-44",
    "8": "45-49",
    "9": "50-54",
    "10": "55-59",
    "11": "60+",
}

# Mapping age code to DB column
AGE_CODE_TO_COLUMN = {
    "3": "age_19_24",
    "4": "age_25_29",
    "5": "age_30_34",
    "6": "age_35_39",
    "7": "age_40_44",
    "8": "age_45_49",
    "9": "age_50_plus",
    "10": "age_50_plus",
    "11": "age_50_plus",
}

# We aggregate 50-54, 55-59, 60+ into "50+"
AGE_50_PLUS_CODES = ["9", "10", "11"]


class SearchDemographicsAnalyzer:
    """네이버 DataLab API를 사용하여 키워드별 검색자 인구통계를 분석합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_api_keys()
        self._load_keywords()
        self._last_request_time = 0

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """search_demographics 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS search_demographics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        analysis_date TEXT NOT NULL,
                        age_19_24 REAL DEFAULT 0,
                        age_25_29 REAL DEFAULT 0,
                        age_30_34 REAL DEFAULT 0,
                        age_35_39 REAL DEFAULT 0,
                        age_40_44 REAL DEFAULT 0,
                        age_45_49 REAL DEFAULT 0,
                        age_50_plus REAL DEFAULT 0,
                        gender_male REAL DEFAULT 0,
                        gender_female REAL DEFAULT 0,
                        dominant_age TEXT,
                        dominant_gender TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(keyword, analysis_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_search_demographics_keyword_date
                    ON search_demographics (keyword, analysis_date DESC)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"search_demographics 테이블 생성 실패: {e}")
            raise
        logger.info("search_demographics 테이블 준비 완료")

    def _load_api_keys(self):
        """NAVER_DATALAB_KEYS 로드 (4개 키 로테이션)."""
        self.api_keys = self.config.get_api_key_list("NAVER_DATALAB_KEYS")

        # Fallback: single key
        if not self.api_keys:
            cid = self.config.get_api_key("NAVER_DATALAB_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_DATALAB_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})

        self.current_key_index = 0
        if self.api_keys:
            logger.info(f"DataLab API 키 {len(self.api_keys)}개 로드 완료")
        else:
            logger.warning("DataLab API 키를 찾을 수 없습니다. 인구통계 분석이 불가합니다.")

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

        logger.info(f"인구통계 분석 대상 키워드 {len(self.keywords)}개 로드")

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
            "X-Naver-Client-Secret": key_data["secret"],
            "Content-Type": "application/json"
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
    # DataLab API
    # ========================================================================

    def _call_datalab(self, keyword: str, start_date: str, end_date: str,
                      ages: Optional[List[str]] = None,
                      gender: Optional[str] = None) -> Optional[float]:
        """
        DataLab API를 호출하여 특정 필터의 평균 ratio를 반환합니다.

        Args:
            keyword: 검색 키워드
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)
            ages: 연령 코드 리스트 (예: ["3"])
            gender: 성별 ("m" 또는 "f")

        Returns:
            평균 ratio 값 또는 None (실패 시)
        """
        if not self.api_keys:
            return None

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "month",
            "keywordGroups": [
                {
                    "groupName": keyword,
                    "keywords": [keyword]
                }
            ]
        }

        if ages:
            body["ages"] = ages
        if gender:
            body["gender"] = gender

        max_retries = min(len(self.api_keys) + 1, 5)

        for attempt in range(max_retries):
            try:
                self._rate_limit()
                headers = self._get_headers()
                response = requests.post(
                    DATALAB_API_URL,
                    headers=headers,
                    json=body,
                    timeout=10
                )

                if response.status_code == 200:
                    data = response.json()
                    results = data.get('results', [])
                    if results:
                        data_points = results[0].get('data', [])
                        if data_points:
                            ratios = [float(dp.get('ratio', 0.0)) for dp in data_points]
                            return sum(ratios) / len(ratios) if ratios else 0.0
                    return 0.0

                elif response.status_code in [401, 429]:
                    logger.warning(f"DataLab API {response.status_code}, 키 로테이션...")
                    self._rotate_key()
                    time.sleep(1.0)
                    continue

                else:
                    logger.warning(
                        f"DataLab API 오류 {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    break

            except requests.exceptions.Timeout:
                logger.warning(f"DataLab API 타임아웃 (시도 {attempt + 1}/{max_retries})")
                time.sleep(2.0)

            except requests.exceptions.RequestException as e:
                logger.error(f"DataLab API 요청 실패: {e}")
                break

        return None

    # ========================================================================
    # Analysis
    # ========================================================================

    def analyze_keyword(self, keyword: str, start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """
        단일 키워드의 연령/성별 인구통계를 분석합니다.

        Args:
            keyword: 분석할 키워드
            start_date: 시작일
            end_date: 종료일

        Returns:
            인구통계 분석 결과 dict 또는 None
        """
        age_ratios = {}

        # 1. 연령대별 ratio 수집 (19세 이상, 코드 3-11)
        for age_code, age_label in AGE_GROUPS.items():
            ratio = self._call_datalab(keyword, start_date, end_date, ages=[age_code])
            if ratio is not None:
                age_ratios[age_code] = ratio
            else:
                age_ratios[age_code] = 0.0

            # Rotate key after each call
            self._rotate_key()

        # 2. 성별 ratio 수집
        male_ratio = self._call_datalab(keyword, start_date, end_date, gender="m")
        self._rotate_key()

        female_ratio = self._call_datalab(keyword, start_date, end_date, gender="f")
        self._rotate_key()

        if male_ratio is None:
            male_ratio = 0.0
        if female_ratio is None:
            female_ratio = 0.0

        # 3. DB 컬럼에 맞게 연령 데이터 정리
        # 50+ = 50-54 + 55-59 + 60+ 의 합산 평균
        age_50_values = [age_ratios.get(c, 0.0) for c in AGE_50_PLUS_CODES]
        age_50_plus = sum(age_50_values) / len(age_50_values) if age_50_values else 0.0

        result = {
            "keyword": keyword,
            "age_19_24": round(age_ratios.get("3", 0.0), 2),
            "age_25_29": round(age_ratios.get("4", 0.0), 2),
            "age_30_34": round(age_ratios.get("5", 0.0), 2),
            "age_35_39": round(age_ratios.get("6", 0.0), 2),
            "age_40_44": round(age_ratios.get("7", 0.0), 2),
            "age_45_49": round(age_ratios.get("8", 0.0), 2),
            "age_50_plus": round(age_50_plus, 2),
            "gender_male": round(male_ratio, 2),
            "gender_female": round(female_ratio, 2),
        }

        # 4. 지배적 연령대/성별 결정
        age_map = {
            "19-24": result["age_19_24"],
            "25-29": result["age_25_29"],
            "30-34": result["age_30_34"],
            "35-39": result["age_35_39"],
            "40-44": result["age_40_44"],
            "45-49": result["age_45_49"],
            "50+": result["age_50_plus"],
        }

        # 가장 높은 ratio의 연령대
        if any(v > 0 for v in age_map.values()):
            result["dominant_age"] = max(age_map, key=age_map.get)
        else:
            result["dominant_age"] = "unknown"

        # 성별
        if male_ratio > female_ratio:
            result["dominant_gender"] = "m"
        elif female_ratio > male_ratio:
            result["dominant_gender"] = "f"
        else:
            result["dominant_gender"] = "equal"

        return result

    def _save_result(self, result: Dict[str, Any], analysis_date: str):
        """분석 결과를 DB에 저장합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO search_demographics
                        (keyword, analysis_date, age_19_24, age_25_29, age_30_34,
                         age_35_39, age_40_44, age_45_49, age_50_plus,
                         gender_male, gender_female, dominant_age, dominant_gender)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(keyword, analysis_date) DO UPDATE SET
                        age_19_24 = excluded.age_19_24,
                        age_25_29 = excluded.age_25_29,
                        age_30_34 = excluded.age_30_34,
                        age_35_39 = excluded.age_35_39,
                        age_40_44 = excluded.age_40_44,
                        age_45_49 = excluded.age_45_49,
                        age_50_plus = excluded.age_50_plus,
                        gender_male = excluded.gender_male,
                        gender_female = excluded.gender_female,
                        dominant_age = excluded.dominant_age,
                        dominant_gender = excluded.dominant_gender
                """, (
                    result['keyword'],
                    analysis_date,
                    result['age_19_24'],
                    result['age_25_29'],
                    result['age_30_34'],
                    result['age_35_39'],
                    result['age_40_44'],
                    result['age_45_49'],
                    result['age_50_plus'],
                    result['gender_male'],
                    result['gender_female'],
                    result['dominant_age'],
                    result['dominant_gender'],
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"DB 저장 오류 [{result.get('keyword')}]: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Output
    # ========================================================================

    def _generate_insight(self, result: Dict[str, Any]) -> str:
        """인구통계 결과에서 마케팅 인사이트를 생성합니다."""
        dominant_age = result.get('dominant_age', 'unknown')
        dominant_gender = result.get('dominant_gender', 'equal')

        gender_label = {"m": "남성", "f": "여성", "equal": "동등"}.get(dominant_gender, "불명")

        insight_parts = []

        if dominant_age != "unknown":
            insight_parts.append(f"주요 검색층: {dominant_age}세")

        insight_parts.append(f"성별: {gender_label} 우세")

        # 특이 패턴 감지
        if result.get('age_19_24', 0) > 30:
            insight_parts.append("MZ세대 관심 높음")
        if result.get('age_50_plus', 0) > 25:
            insight_parts.append("50+ 시니어 수요")
        if result.get('gender_female', 0) > 70:
            insight_parts.append("여성 타겟 유리")
        if result.get('gender_male', 0) > 70:
            insight_parts.append("남성 타겟 유리")

        return " / ".join(insight_parts) if insight_parts else "-"

    def _print_summary(self, results: List[Dict[str, Any]]):
        """인구통계 요약 테이블을 출력합니다."""
        if not results:
            print("  분석 결과가 없습니다.")
            return

        print(f"\n{'='*100}")
        print(f" {'키워드':<25} {'주요연령':>8} {'성별':>6} {'인사이트'}")
        print(f"{'─'*100}")

        for r in results:
            kw_display = r['keyword'][:24]
            dominant_age = r.get('dominant_age', '?')
            gender_label = {"m": "남성", "f": "여성", "equal": "동등"}.get(
                r.get('dominant_gender', '?'), '?'
            )
            insight = self._generate_insight(r)

            print(
                f" {kw_display:<25} "
                f"{dominant_age:>8} "
                f"{gender_label:>6} "
                f" {insight}"
            )

        print(f"{'─'*100}")
        print(f" 총 {len(results)}개 키워드 분석 완료")

        # 전체 통계
        age_dist = {}
        for r in results:
            da = r.get('dominant_age', 'unknown')
            age_dist[da] = age_dist.get(da, 0) + 1

        gender_dist = {"m": 0, "f": 0, "equal": 0}
        for r in results:
            dg = r.get('dominant_gender', 'equal')
            gender_dist[dg] = gender_dist.get(dg, 0) + 1

        print(f"\n >> 연령대 분포:")
        for age, count in sorted(age_dist.items()):
            print(f"    {age}: {count}개 키워드")

        print(f"\n >> 성별 분포:")
        print(f"    남성 우세: {gender_dist['m']}개, 여성 우세: {gender_dist['f']}개, 동등: {gender_dist['equal']}개")

        print(f"{'='*100}\n")

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """인구통계 분석을 실행합니다."""
        start_time = time.time()

        if not self.keywords:
            print("[WARN] 분석할 키워드가 없습니다.")
            return {"analyzed": 0, "failed": 0}

        if not self.api_keys:
            print("[WARN] DataLab API 키가 설정되지 않았습니다.")
            return {"analyzed": 0, "failed": 0}

        today = datetime.now()
        analysis_date = today.strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=90)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f" Search Demographics Analyzer")
        print(f" 기간: {start_date} ~ {end_date} (최근 3개월)")
        print(f" 키워드: {len(self.keywords)}개")
        print(f" API 키: {len(self.api_keys)}개")
        print(f"{'='*60}\n")

        results = []
        analyzed = 0
        failed = 0

        for idx, keyword in enumerate(self.keywords, 1):
            print(f"  [{idx}/{len(self.keywords)}] '{keyword}'...", end=" ", flush=True)

            try:
                result = self.analyze_keyword(keyword, start_date, end_date)
                if result:
                    self._save_result(result, analysis_date)
                    results.append(result)
                    analyzed += 1
                    print(
                        f"-> 주요연령: {result['dominant_age']}, "
                        f"성별: {'남' if result['dominant_gender'] == 'm' else '여' if result['dominant_gender'] == 'f' else '동등'}"
                    )
                else:
                    failed += 1
                    print("-> FAILED")

            except Exception as e:
                failed += 1
                print(f"-> ERROR: {e}")
                logger.error(f"[{keyword}] 분석 오류: {e}")
                logger.debug(traceback.format_exc())

        # Print summary table
        self._print_summary(results)

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")
        print(f">> 분석: {analyzed}개, 실패: {failed}개")

        return {
            "analyzed": analyzed,
            "failed": failed,
            "results": results,
            "elapsed_seconds": round(elapsed, 1)
        }

    def get_demographics(self, keyword: Optional[str] = None) -> List[Dict[str, Any]]:
        """DB에서 인구통계 데이터를 조회합니다. API 엔드포인트용."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                if keyword:
                    cursor.execute("""
                        SELECT * FROM search_demographics
                        WHERE keyword = ?
                        ORDER BY analysis_date DESC
                        LIMIT 1
                    """, (keyword,))
                else:
                    # 각 키워드의 최신 분석 결과
                    cursor.execute("""
                        SELECT sd.* FROM search_demographics sd
                        INNER JOIN (
                            SELECT keyword, MAX(analysis_date) as max_date
                            FROM search_demographics
                            GROUP BY keyword
                        ) latest ON sd.keyword = latest.keyword
                            AND sd.analysis_date = latest.max_date
                        ORDER BY sd.keyword
                    """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"인구통계 조회 오류: {e}")
            return []


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        analyzer = SearchDemographicsAnalyzer()
        result = analyzer.run()
        print(f"\n[완료] 분석: {result['analyzed']}개, 실패: {result['failed']}개")
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
