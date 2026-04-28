"""
HIRA (건강보험심사평가원) Public API Client

공공데이터포털 건강보험심사평가원 의료기관 기본정보 API를 통해
한의원/병원 데이터를 수집하여 DB에 저장합니다.

API: https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList

Usage:
    python scrapers/hira_api_client.py
"""
import sys
import os
import time
import json
import logging
import traceback
import xml.etree.ElementTree as ET
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
# 시도/시군구 코드 매핑
# ============================================================
SIDO_CODES = {
    "서울특별시": "110000",
    "부산광역시": "210000",
    "대구광역시": "220000",
    "인천광역시": "230000",
    "광주광역시": "240000",
    "대전광역시": "250000",
    "울산광역시": "260000",
    "세종특별자치시": "290000",
    "경기도": "310000",
    "강원도": "320000",
    "충청북도": "330000",
    "충청남도": "340000",
    "전라북도": "350000",
    "전라남도": "360000",
    "경상북도": "370000",
    "경상남도": "380000",
    "제주특별자치도": "390000",
}

# 충청북도 시군구 코드 (주요 지역)
CHUNGBUK_SIGUNGU_CODES = {
    "청주시": "331000",
    "충주시": "332000",
    "제천시": "333000",
    "보은군": "334000",
    "옥천군": "335000",
    "영동군": "336000",
    "증평군": "337000",
    "진천군": "338000",
    "괴산군": "339000",
    "음성군": "340000",
    "단양군": "341000",
}

# 종별코드 (clCd)
CLINIC_TYPE_CODES = {
    "한의원": "31",
    "의원": "21",
    "병원": "11",
    "한방병원": "28",
    "치과의원": "41",
    "약국": "81",
}


class HiraAPIClient:
    """건강보험심사평가원 의료기관 정보 API 클라이언트"""

    BASE_URL = "https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList"

    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.api_key = self.config.get_api_key("DATA_GO_KR_API_KEY")

        if not self.api_key:
            logger.warning("DATA_GO_KR_API_KEY가 설정되지 않았습니다. HIRA API를 사용할 수 없습니다.")

        # DB 테이블 초기화
        self._init_table()

    def _init_table(self):
        """hira_clinics 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS hira_clinics (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ykiho TEXT UNIQUE,
                        name TEXT,
                        category TEXT,
                        address TEXT,
                        phone TEXT,
                        sido TEXT,
                        sigungu TEXT,
                        specialty TEXT,
                        doctor_count INTEGER DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                ''')
                conn.commit()
                logger.info("hira_clinics 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 초기화 실패: {e}")

    def _parse_xml_response(self, xml_text: str) -> List[Dict[str, Any]]:
        """XML 응답 파싱"""
        items = []
        try:
            root = ET.fromstring(xml_text)

            # 에러 응답 확인
            header = root.find('.//header')
            if header is not None:
                result_code = header.findtext('resultCode', '')
                result_msg = header.findtext('resultMsg', '')
                if result_code != '00':
                    logger.error(f"API 응답 오류: [{result_code}] {result_msg}")
                    return items

            # 아이템 파싱
            for item in root.findall('.//item'):
                clinic_data = {
                    'ykiho': item.findtext('ykiho', '').strip(),
                    'name': item.findtext('yadmNm', '').strip(),
                    'category': item.findtext('clCdNm', '').strip(),
                    'address': item.findtext('addr', '').strip(),
                    'phone': item.findtext('telno', '').strip(),
                    'sido': item.findtext('sidoCdNm', '').strip(),
                    'sigungu': item.findtext('sgguCdNm', '').strip(),
                    'specialty': item.findtext('dgsbjtCdNm', '').strip(),
                    'doctor_count': int(item.findtext('drTotCnt', '0') or '0'),
                }

                if clinic_data['ykiho']:
                    items.append(clinic_data)

        except ET.ParseError as e:
            logger.error(f"XML 파싱 오류: {e}")
        except Exception as e:
            logger.error(f"응답 처리 오류: {e}")

        return items

    def _fetch_page(self, sido_cd: str, sggu_cd: str, cl_cd: str,
                    page_no: int = 1, num_of_rows: int = 100) -> Optional[str]:
        """API 한 페이지 요청"""
        params = {
            'ServiceKey': self.api_key,
            'sidoCd': sido_cd,
            'sgguCd': sggu_cd,
            'clCd': cl_cd,
            'pageNo': str(page_no),
            'numOfRows': str(num_of_rows),
        }

        try:
            response = requests.get(self.BASE_URL, params=params, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.exceptions.Timeout:
            logger.error(f"API 요청 타임아웃 (페이지 {page_no})")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"API 요청 실패: {e}")
            return None

    def _get_total_count(self, xml_text: str) -> int:
        """응답에서 전체 건수 추출"""
        try:
            root = ET.fromstring(xml_text)
            total_count = root.findtext('.//totalCount', '0')
            return int(total_count)
        except Exception:
            return 0

    def _upsert_clinic(self, conn, clinic_data: Dict[str, Any]) -> bool:
        """기존 ykiho가 있으면 UPDATE, 없으면 INSERT"""
        cursor = conn.cursor()

        # 기존 레코드 확인
        cursor.execute("SELECT id FROM hira_clinics WHERE ykiho = ?", (clinic_data['ykiho'],))
        existing = cursor.fetchone()

        if existing:
            # UPDATE
            cursor.execute('''
                UPDATE hira_clinics
                SET name = ?, category = ?, address = ?, phone = ?,
                    sido = ?, sigungu = ?, specialty = ?, doctor_count = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ykiho = ?
            ''', (
                clinic_data['name'], clinic_data['category'], clinic_data['address'],
                clinic_data['phone'], clinic_data['sido'], clinic_data['sigungu'],
                clinic_data['specialty'], clinic_data['doctor_count'],
                clinic_data['ykiho']
            ))
            return False  # Updated, not inserted
        else:
            # INSERT
            cursor.execute('''
                INSERT INTO hira_clinics (ykiho, name, category, address, phone,
                                          sido, sigungu, specialty, doctor_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                clinic_data['ykiho'], clinic_data['name'], clinic_data['category'],
                clinic_data['address'], clinic_data['phone'], clinic_data['sido'],
                clinic_data['sigungu'], clinic_data['specialty'], clinic_data['doctor_count']
            ))
            return True  # Inserted

    def collect_hira_clinics(self, sido: str = '충청북도', sigungu: str = '청주시',
                             clinic_type: str = '한의원') -> Dict[str, int]:
        """
        HIRA API에서 의료기관 정보를 수집하여 DB에 저장합니다.

        Args:
            sido: 시도명 (기본: 충청북도)
            sigungu: 시군구명 (기본: 청주시)
            clinic_type: 종별 (기본: 한의원)

        Returns:
            {"total_fetched": int, "inserted": int, "updated": int}
        """
        result = {"total_fetched": 0, "inserted": 0, "updated": 0}

        # API 키 확인
        if not self.api_key:
            logger.warning("DATA_GO_KR_API_KEY 미설정. HIRA 수집을 건너뜁니다.")
            return result

        # 코드 변환
        sido_cd = SIDO_CODES.get(sido)
        if not sido_cd:
            logger.error(f"알 수 없는 시도명: {sido}")
            return result

        # 시군구 코드 조회 (충청북도 기준)
        sggu_cd = CHUNGBUK_SIGUNGU_CODES.get(sigungu, '')
        if not sggu_cd:
            logger.warning(f"시군구코드를 찾을 수 없습니다: {sigungu}. 전체 시도 범위로 조회합니다.")

        cl_cd = CLINIC_TYPE_CODES.get(clinic_type, '31')

        logger.info(f"HIRA 데이터 수집 시작: {sido} {sigungu} ({clinic_type})")
        logger.info(f"  시도코드={sido_cd}, 시군구코드={sggu_cd}, 종별코드={cl_cd}")

        # 첫 페이지 요청으로 전체 건수 파악
        xml_text = self._fetch_page(sido_cd, sggu_cd, cl_cd, page_no=1, num_of_rows=100)
        if not xml_text:
            logger.error("첫 페이지 요청 실패")
            return result

        total_count = self._get_total_count(xml_text)
        logger.info(f"  전체 건수: {total_count}")

        if total_count == 0:
            logger.info("수집할 데이터가 없습니다.")
            return result

        # 첫 페이지 데이터 처리
        all_clinics = self._parse_xml_response(xml_text)
        total_pages = (total_count + 99) // 100  # ceil division

        # 나머지 페이지 요청
        for page in range(2, total_pages + 1):
            time.sleep(0.5)  # Rate limiting

            xml_text = self._fetch_page(sido_cd, sggu_cd, cl_cd, page_no=page, num_of_rows=100)
            if xml_text:
                page_items = self._parse_xml_response(xml_text)
                all_clinics.extend(page_items)
                logger.info(f"  페이지 {page}/{total_pages} 완료 ({len(page_items)}건)")
            else:
                logger.warning(f"  페이지 {page} 요청 실패. 건너뜁니다.")

        result["total_fetched"] = len(all_clinics)
        logger.info(f"  총 {len(all_clinics)}건 수집 완료. DB 저장 시작...")

        # DB 저장
        try:
            with self.db.get_new_connection() as conn:
                for clinic in all_clinics:
                    try:
                        is_new = self._upsert_clinic(conn, clinic)
                        if is_new:
                            result["inserted"] += 1
                        else:
                            result["updated"] += 1
                    except Exception as e:
                        logger.warning(f"  레코드 저장 실패 ({clinic.get('name', '?')}): {e}")

                conn.commit()
        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            logger.error(traceback.format_exc())

        logger.info(f"HIRA 수집 완료: 총 {result['total_fetched']}건 "
                     f"(신규 {result['inserted']}, 업데이트 {result['updated']})")

        return result

    def collect_multiple_types(self, sido: str = '충청북도', sigungu: str = '청주시',
                               clinic_types: List[str] = None) -> Dict[str, Dict[str, int]]:
        """
        여러 종별의 의료기관 정보를 수집합니다.

        Args:
            sido: 시도명
            sigungu: 시군구명
            clinic_types: 종별 목록 (기본: 한의원, 의원)

        Returns:
            {종별: {"total_fetched": int, "inserted": int, "updated": int}}
        """
        if clinic_types is None:
            clinic_types = ["한의원", "의원"]

        results = {}
        for clinic_type in clinic_types:
            logger.info(f"\n{'='*50}")
            logger.info(f"수집 대상: {clinic_type}")
            logger.info(f"{'='*50}")

            results[clinic_type] = self.collect_hira_clinics(sido, sigungu, clinic_type)

            # 종별 간 대기
            time.sleep(1.0)

        return results

    def get_clinic_stats(self, sido: str = None, sigungu: str = None) -> Dict[str, Any]:
        """
        저장된 의료기관 통계를 조회합니다.

        Returns:
            카테고리별 개수, 전체 개수 등
        """
        stats = {"total": 0, "by_category": {}, "by_sigungu": {}}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 필터 조건
                where_clauses = []
                params = []
                if sido:
                    where_clauses.append("sido = ?")
                    params.append(sido)
                if sigungu:
                    where_clauses.append("sigungu LIKE ?")
                    params.append(f"%{sigungu}%")

                where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

                # 전체 건수
                cursor.execute(f"SELECT COUNT(*) FROM hira_clinics {where_sql}", params)
                stats["total"] = cursor.fetchone()[0]

                # 카테고리별
                cursor.execute(f"""
                    SELECT category, COUNT(*) as cnt
                    FROM hira_clinics {where_sql}
                    GROUP BY category ORDER BY cnt DESC
                """, params)
                stats["by_category"] = {row[0]: row[1] for row in cursor.fetchall()}

                # 시군구별
                cursor.execute(f"""
                    SELECT sigungu, COUNT(*) as cnt
                    FROM hira_clinics {where_sql}
                    GROUP BY sigungu ORDER BY cnt DESC
                """, params)
                stats["by_sigungu"] = {row[0]: row[1] for row in cursor.fetchall()}

        except Exception as e:
            logger.error(f"통계 조회 오류: {e}")

        return stats


def main():
    """메인 실행 함수.

    CLI 사용 (External Signals R3-7로 활성화):
      python scrapers/hira_api_client.py --status
      python scrapers/hira_api_client.py --region "충북" --year 2025
      python scrapers/hira_api_client.py --region "충북" --sigungu "청주시" --type 한의원
      python scrapers/hira_api_client.py --dry-run

    DATA_GO_KR_API_KEY는 config/secrets.json에 등록됨.
    """
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='충북', help='시도명 (기본 충북 → 충청북도)')
    parser.add_argument('--sigungu', default='청주시')
    parser.add_argument('--type', default='한의원',
                        choices=['한의원', '의원', '한방병원', '병원'])
    parser.add_argument('--year', type=int, help='연도 (현재는 metadata 출력용, 본 API는 항상 현재 시점)')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 시도명 별칭 처리
    sido_full = args.region
    if args.region in ('충북', '충청북도'):
        sido_full = '충청북도'
    elif args.region in ('충남', '충청남도'):
        sido_full = '충청남도'

    if args.status:
        try:
            client = HiraAPIClient()
            stats = client.get_clinic_stats(sigungu=args.sigungu)
            print(f'=== HIRA 한의원 데이터 현황 ({args.sigungu}) ===')
            print(f'  전체: {stats.get("total", 0)}건')
            for cat, cnt in stats.get('by_category', {}).items():
                print(f'    {cat:<10} {cnt}건')
            for sgg, cnt in stats.get('by_sigungu', {}).items():
                print(f'    [지역] {sgg:<15} {cnt}건')
            return 0
        except Exception as e:
            print(f'status 조회 실패: {e}')
            return 1

    logger.info("=" * 60)
    logger.info(f"HIRA 의료기관 정보 수집 시작 — {sido_full} {args.sigungu} ({args.type})"
                + (f' year={args.year}' if args.year else ''))
    logger.info("=" * 60)

    if args.dry_run:
        print(f'  [dry-run] 대상: {sido_full} {args.sigungu} {args.type}')
        print('  실제 수집은 --dry-run 제거 후 재실행')
        return 0

    try:
        client = HiraAPIClient()
        if not client.api_key:
            print('DATA_GO_KR_API_KEY 미설정. config/secrets.json 등록 필요.')
            return 1

        result = client.collect_hira_clinics(
            sido=sido_full,
            sigungu=args.sigungu,
            clinic_type=args.type,
        )

        logger.info(f"\n수집 결과: {json.dumps(result, ensure_ascii=False, indent=2)}")

        # 통계 출력
        stats = client.get_clinic_stats(sigungu=args.sigungu)
        logger.info(f"\n저장된 데이터 통계:")
        logger.info(f"  전체: {stats['total']}건")
        for cat, cnt in stats.get('by_category', {}).items():
            logger.info(f"  - {cat}: {cnt}건")
        return 0

    except Exception as e:
        logger.error(f"실행 오류: {e}")
        logger.error(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main() or 0)
