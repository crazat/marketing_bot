"""
소상공인시장진흥공단 상가정보 API Client

소상공인시장진흥공단 상권정보 API를 통해
특정 지역의 상가(업종) 데이터를 수집하고 경쟁 지수를 산출합니다.

API: https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong

Usage:
    python scrapers/commercial_data_collector.py
"""
import sys
import os
import time
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any

import requests

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# ============================================================
# 지역 코드 매핑 (시도 코드 - divId: ctprvnCd)
# ============================================================
REGION_CODES = {
    "서울": "11",
    "부산": "26",
    "대구": "27",
    "인천": "28",
    "광주": "29",
    "대전": "30",
    "울산": "31",
    "세종": "36",
    "경기": "41",
    "강원": "42",
    "충북": "43",
    "충남": "44",
    "전북": "45",
    "전남": "46",
    "경북": "47",
    "경남": "48",
    "제주": "50",
    # 별칭
    "청주": "43",
    "충청북도": "43",
    "충청남도": "44",
}

# 업종 중분류 코드 (indsMclsCd) - 의료 관련
INDUSTRY_CODES = {
    "한의원": "Q12",
    "의원": "Q11",
    "치과": "Q13",
    "약국": "Q14",
    "병원": "Q10",
    "종합병원": "Q01",
    "요양병원": "Q09",
    "안과": "Q15",
    "피부과": "Q16",
    # 비의료 참고용
    "일반음식점": "I201",
    "커피전문점": "I212",
    "미용실": "F12",
}


class CommercialDataCollector:
    """소상공인시장진흥공단 상가정보 API 클라이언트"""

    BASE_URL = "https://apis.data.go.kr/B553077/api/open/sdsc2/storeListInDong"

    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.api_key = self.config.get_api_key("DATA_GO_KR_API_KEY")

        if not self.api_key:
            logger.warning("DATA_GO_KR_API_KEY가 설정되지 않았습니다. 상가정보 API를 사용할 수 없습니다.")

        # DB 테이블 초기화
        self._init_table()

    def _init_table(self):
        """commercial_district_data 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS commercial_district_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        region TEXT,
                        region_code TEXT,
                        industry_code TEXT,
                        industry_name TEXT,
                        store_count INTEGER DEFAULT 0,
                        total_medical_count INTEGER DEFAULT 0,
                        competition_index REAL DEFAULT 0.0,
                        collected_date TEXT,
                        raw_data TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(region, industry_code, collected_date)
                    )
                ''')
                conn.commit()
                logger.info("commercial_district_data 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 초기화 실패: {e}")

    def _fetch_store_count(self, div_id: str, key: str, inds_mcls_cd: str,
                           page_no: int = 1, num_of_rows: int = 1) -> Optional[Dict[str, Any]]:
        """
        상가 목록 API 호출하여 전체 건수 및 데이터를 가져옵니다.

        Args:
            div_id: 구분 ID (ctprvnCd: 시도, signguCd: 시군구)
            key: 지역코드 값
            inds_mcls_cd: 업종 중분류 코드
            page_no: 페이지 번호
            num_of_rows: 한 페이지 건수

        Returns:
            {"total_count": int, "items": list} or None
        """
        params = {
            'ServiceKey': self.api_key,
            'divId': 'ctprvnCd',
            'key': key,
            'indsMclsCd': inds_mcls_cd,
            'pageNo': str(page_no),
            'numOfRows': str(num_of_rows),
            'type': 'json',
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()

            # 응답 구조 확인
            header = data.get('header', {})
            result_code = header.get('resultCode', '')
            result_msg = header.get('resultMsg', '')

            if result_code != '00' and result_code != '':
                # 일부 API는 header가 다른 구조일 수 있음
                logger.warning(f"API 응답: [{result_code}] {result_msg}")

            body = data.get('body', {})
            total_count = body.get('totalCount', 0)
            items = body.get('items', [])

            # items가 None인 경우 빈 리스트 처리
            if items is None:
                items = []

            return {
                "total_count": total_count,
                "items": items,
            }

        except requests.exceptions.Timeout:
            logger.error("API 요청 타임아웃")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            return None

    def collect_commercial_data(self, region: str = '청주') -> Dict[str, Any]:
        """
        특정 지역의 의료 관련 상가 데이터를 수집하고 경쟁 지수를 산출합니다.

        Args:
            region: 지역명 (기본: 청주)

        Returns:
            {
                "region": str,
                "collected_date": str,
                "categories": {업종명: 건수, ...},
                "total_medical": int,
                "haniwon_count": int,
                "competition_index": float,
            }
        """
        result = {
            "region": region,
            "collected_date": datetime.now().strftime("%Y-%m-%d"),
            "categories": {},
            "total_medical": 0,
            "haniwon_count": 0,
            "competition_index": 0.0,
        }

        # API 키 확인
        if not self.api_key:
            logger.warning("DATA_GO_KR_API_KEY 미설정. 상가정보 수집을 건너뜁니다.")
            return result

        # 지역코드 조회
        region_code = REGION_CODES.get(region)
        if not region_code:
            logger.error(f"알 수 없는 지역명: {region}")
            return result

        logger.info(f"상가정보 수집 시작: {region} (코드: {region_code})")

        # 의료 관련 업종별 수집
        medical_categories = ["한의원", "의원", "치과", "약국", "병원", "종합병원", "요양병원"]
        total_medical = 0

        for category in medical_categories:
            inds_code = INDUSTRY_CODES.get(category)
            if not inds_code:
                continue

            logger.info(f"  {category} ({inds_code}) 조회 중...")

            api_result = self._fetch_store_count('ctprvnCd', region_code, inds_code)

            if api_result:
                count = api_result["total_count"]
                result["categories"][category] = count
                total_medical += count

                logger.info(f"    -> {category}: {count}건")

                if category == "한의원":
                    result["haniwon_count"] = count
            else:
                result["categories"][category] = 0
                logger.warning(f"    -> {category}: 조회 실패")

            # Rate limiting
            time.sleep(0.5)

        result["total_medical"] = total_medical

        # 경쟁 지수 산출: 한의원 수 / 전체 의료기관 수
        if total_medical > 0:
            result["competition_index"] = round(
                result["haniwon_count"] / total_medical, 4
            )
        else:
            result["competition_index"] = 0.0

        logger.info(f"\n수집 결과 요약:")
        logger.info(f"  전체 의료기관: {total_medical}건")
        logger.info(f"  한의원: {result['haniwon_count']}건")
        logger.info(f"  경쟁 지수 (한의원/전체): {result['competition_index']:.4f}")

        # DB 저장
        self._save_to_db(result, region_code)

        return result

    def _save_to_db(self, data: Dict[str, Any], region_code: str):
        """수집 결과를 DB에 저장"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                collected_date = data["collected_date"]

                for industry_name, count in data["categories"].items():
                    inds_code = INDUSTRY_CODES.get(industry_name, "")

                    # UPSERT: 같은 날짜/지역/업종이면 업데이트
                    cursor.execute('''
                        INSERT INTO commercial_district_data
                            (region, region_code, industry_code, industry_name,
                             store_count, total_medical_count, competition_index,
                             collected_date, raw_data)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(region, industry_code, collected_date) DO UPDATE SET
                            store_count = excluded.store_count,
                            total_medical_count = excluded.total_medical_count,
                            competition_index = excluded.competition_index,
                            raw_data = excluded.raw_data
                    ''', (
                        data["region"], region_code, inds_code, industry_name,
                        count, data["total_medical"], data["competition_index"],
                        collected_date, json.dumps(data, ensure_ascii=False)
                    ))

                conn.commit()
                logger.info(f"DB 저장 완료: {len(data['categories'])}건")

        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            logger.error(traceback.format_exc())

    def get_competition_trend(self, region: str = '청주', days: int = 30) -> List[Dict[str, Any]]:
        """
        경쟁 지수 추이를 조회합니다.

        Args:
            region: 지역명
            days: 조회 기간 (일)

        Returns:
            [{"date": str, "haniwon": int, "total": int, "index": float}, ...]
        """
        trend = []
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT collected_date, store_count, total_medical_count, competition_index
                    FROM commercial_district_data
                    WHERE region = ? AND industry_name = '한의원'
                      AND collected_date >= date('now', ?)
                    ORDER BY collected_date DESC
                ''', (region, f'-{days} days'))

                for row in cursor.fetchall():
                    trend.append({
                        "date": row[0],
                        "haniwon": row[1],
                        "total": row[2],
                        "index": row[3],
                    })

        except Exception as e:
            logger.error(f"추이 조회 오류: {e}")

        return trend

    def get_district_summary(self, region: str = '청주') -> Dict[str, Any]:
        """
        최신 상권 데이터 요약을 반환합니다.

        Args:
            region: 지역명

        Returns:
            최신 날짜 기준 업종별 요약
        """
        summary = {"region": region, "date": None, "categories": {}, "competition_index": 0.0}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 가장 최근 날짜 조회
                cursor.execute('''
                    SELECT MAX(collected_date) FROM commercial_district_data
                    WHERE region = ?
                ''', (region,))
                row = cursor.fetchone()
                if not row or not row[0]:
                    return summary

                latest_date = row[0]
                summary["date"] = latest_date

                # 해당 날짜의 모든 업종 데이터
                cursor.execute('''
                    SELECT industry_name, store_count, competition_index
                    FROM commercial_district_data
                    WHERE region = ? AND collected_date = ?
                    ORDER BY store_count DESC
                ''', (region, latest_date))

                for row in cursor.fetchall():
                    summary["categories"][row[0]] = row[1]
                    if row[0] == '한의원':
                        summary["competition_index"] = row[2]

        except Exception as e:
            logger.error(f"요약 조회 오류: {e}")

        return summary


def main():
    """메인 실행 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("=" * 60)
    logger.info("소상공인 상가정보 수집 시작")
    logger.info("=" * 60)

    try:
        collector = CommercialDataCollector()

        # 청주 지역 의료기관 데이터 수집
        result = collector.collect_commercial_data(region='청주')

        logger.info(f"\n최종 결과:")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))

        # 기존 데이터 요약 출력
        summary = collector.get_district_summary(region='청주')
        if summary["date"]:
            logger.info(f"\n최신 저장 데이터 ({summary['date']}):")
            for cat, cnt in summary["categories"].items():
                logger.info(f"  - {cat}: {cnt}건")
            logger.info(f"  경쟁지수: {summary['competition_index']:.4f}")

    except Exception as e:
        logger.error(f"실행 오류: {e}")
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
