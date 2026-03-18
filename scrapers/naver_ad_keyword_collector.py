"""
Naver Ads API 키워드 데이터 수집기 (Enhanced)

NaverAdManager를 활용하여 keywords.json의 모든 키워드에 대해
검색량, 클릭수, CTR, 경쟁도 등 상세 데이터를 수집하고 DB에 저장합니다.

기존 naver_ad_manager.py의 패턴을 확장하여 전체 키워드 데이터를 일괄 수집합니다.

Usage:
    python scrapers/naver_ad_keyword_collector.py
"""
import sys
import os
import time
import json
import logging
import traceback
from datetime import datetime
from typing import Optional, Dict, List, Any

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


class NaverAdKeywordCollector:
    """
    Naver Ads API 키워드 데이터 수집기

    NaverAdManager를 활용하여 keyword data를 수집하고,
    naver_ad_keyword_data 테이블에 상세 정보를 저장합니다.

    수집 항목:
    - monthly_search_pc / monthly_search_mobile
    - monthly_click_pc / monthly_click_mobile
    - monthly_ctr_pc / monthly_ctr_mobile
    - competition_level
    - avg_ad_count (월평균 광고 노출 수)
    - related_keywords
    """

    BASE_URL = "https://api.naver.com"

    def __init__(self):
        self.config = ConfigManager()
        self.db = DatabaseManager()
        self.ad_manager = None
        self.disabled = False

        # NaverAdManager 로드 시도
        try:
            from scrapers.naver_ad_manager import NaverAdManager
            self.ad_manager = NaverAdManager()
            if getattr(self.ad_manager, 'disabled', False):
                logger.warning("NaverAdManager가 비활성화 상태입니다 (API 키 없음).")
                self.disabled = True
            else:
                logger.info("NaverAdManager 로드 완료")
        except ImportError:
            logger.warning("NaverAdManager를 import할 수 없습니다. 직접 API 호출을 시도합니다.")
            self._init_direct_api()
        except Exception as e:
            logger.warning(f"NaverAdManager 초기화 실패: {e}. 직접 API 호출을 시도합니다.")
            self._init_direct_api()

        # DB 테이블 초기화
        self._init_table()

    def _init_direct_api(self):
        """NaverAdManager 없이 직접 API 호출을 위한 설정"""
        import hmac
        import hashlib
        import base64

        self.api_key = self.config.get_api_key("NAVER_AD_ACCESS_KEY")
        self.secret_key = self.config.get_api_key("NAVER_AD_SECRET_KEY")
        self.customer_id = self.config.get_api_key("NAVER_AD_CUSTOMER_ID")

        if not all([self.api_key, self.secret_key, self.customer_id]):
            logger.warning("Naver Ad API 자격 증명이 없습니다. 키워드 수집이 비활성화됩니다.")
            self.disabled = True
        else:
            self.disabled = False
            logger.info("Naver Ad API 직접 연결 모드")

    def _init_table(self):
        """naver_ad_keyword_data 테이블 생성"""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS naver_ad_keyword_data (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT,
                        monthly_search_pc INTEGER DEFAULT 0,
                        monthly_search_mobile INTEGER DEFAULT 0,
                        monthly_click_pc REAL DEFAULT 0.0,
                        monthly_click_mobile REAL DEFAULT 0.0,
                        monthly_ctr_pc REAL DEFAULT 0.0,
                        monthly_ctr_mobile REAL DEFAULT 0.0,
                        competition_level TEXT DEFAULT '',
                        avg_ad_count REAL DEFAULT 0.0,
                        total_search_volume INTEGER DEFAULT 0,
                        is_related INTEGER DEFAULT 0,
                        source_keyword TEXT DEFAULT '',
                        collected_date TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(keyword, collected_date)
                    )
                ''')

                # related_keywords 테이블 (연관 키워드 별도 저장)
                cursor.execute('''
                    CREATE TABLE IF NOT EXISTS naver_ad_related_keywords (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source_keyword TEXT,
                        related_keyword TEXT,
                        search_volume INTEGER DEFAULT 0,
                        collected_date TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(source_keyword, related_keyword, collected_date)
                    )
                ''')

                conn.commit()
                logger.info("naver_ad_keyword_data 테이블 준비 완료")
        except Exception as e:
            logger.error(f"테이블 초기화 실패: {e}")

    def _load_keywords(self) -> List[str]:
        """config/keywords.json에서 모든 키워드 로드"""
        keywords = []
        keywords_path = os.path.join(project_root, 'config', 'keywords.json')

        try:
            if not os.path.exists(keywords_path):
                logger.warning(f"keywords.json을 찾을 수 없습니다: {keywords_path}")
                return keywords

            with open(keywords_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # naver_place 키워드
            naver_place = data.get('naver_place', [])
            if naver_place:
                keywords.extend(naver_place)
                logger.info(f"  naver_place 키워드: {len(naver_place)}개")

            # blog_seo 키워드
            blog_seo = data.get('blog_seo', [])
            if blog_seo:
                keywords.extend(blog_seo)
                logger.info(f"  blog_seo 키워드: {len(blog_seo)}개")

            # 중복 제거
            keywords = list(dict.fromkeys(keywords))
            logger.info(f"  총 키워드 (중복 제거): {len(keywords)}개")

        except Exception as e:
            logger.error(f"키워드 로드 실패: {e}")

        return keywords

    def _generate_signature(self, timestamp: str, method: str, uri: str) -> str:
        """HMAC-SHA256 서명 생성 (직접 API 호출용)"""
        import hmac
        import hashlib
        import base64

        message = f"{timestamp}.{method}.{uri}"
        sign = hmac.new(
            self.secret_key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        )
        return base64.b64encode(sign.digest()).decode("utf-8")

    def _get_headers(self, method: str, uri: str) -> Dict[str, str]:
        """API 요청 헤더 생성 (직접 API 호출용)"""
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, uri)

        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": str(self.customer_id),
            "X-Signature": signature
        }

    def _fetch_keyword_data_direct(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        직접 Naver Ad API를 호출하여 키워드 상세 데이터를 가져옵니다.

        Args:
            keywords: 키워드 목록 (최대 5개씩 청크)

        Returns:
            API 응답의 keywordList 항목들
        """
        import requests

        all_items = []
        uri = "/keywordstool"
        method = "GET"

        chunk_size = 5
        chunks = [keywords[i:i + chunk_size] for i in range(0, len(keywords), chunk_size)]

        for idx, chunk in enumerate(chunks):
            if self.disabled:
                break

            try:
                query_params = {
                    "hintKeywords": ",".join([k.replace(" ", "") for k in chunk]),
                    "showDetail": 1
                }

                headers = self._get_headers(method, uri)

                resp = requests.get(
                    self.BASE_URL + uri,
                    params=query_params,
                    headers=headers,
                    timeout=15
                )

                if resp.status_code == 200:
                    data = resp.json()
                    keyword_list = data.get("keywordList", [])
                    all_items.extend(keyword_list)
                    logger.info(f"  청크 {idx+1}/{len(chunks)}: {len(keyword_list)}개 키워드 데이터 수신")

                elif resp.status_code == 429:
                    logger.warning("API 할당량 초과 (429). 60초 대기 후 재시도...")
                    time.sleep(60)
                    # 재시도
                    resp = requests.get(
                        self.BASE_URL + uri,
                        params=query_params,
                        headers=self._get_headers(method, uri),
                        timeout=15
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        all_items.extend(data.get("keywordList", []))

                elif resp.status_code in [401, 403]:
                    logger.error(f"API 인증 실패 ({resp.status_code}). 수집을 중단합니다.")
                    self.disabled = True
                    break

                else:
                    logger.error(f"API 오류 {resp.status_code}: {repr(resp.content[:200])}")

                # Rate limiting
                time.sleep(0.3)

            except Exception as e:
                logger.error(f"API 호출 오류 (청크 {idx+1}): {e}")
                time.sleep(1)

        return all_items

    def _parse_count_value(self, value) -> int:
        """'< 10' 같은 문자열 값을 정수로 변환"""
        if isinstance(value, str):
            if "<" in value:
                return 5  # '< 10' -> 5 (추정값)
            try:
                return int(value.replace(",", ""))
            except ValueError:
                return 0
        return int(value) if value else 0

    def _parse_float_value(self, value) -> float:
        """문자열/숫자를 float로 변환"""
        if value is None:
            return 0.0
        if isinstance(value, str):
            if "<" in value:
                return 0.0
            try:
                return float(value.replace(",", "").replace("%", ""))
            except ValueError:
                return 0.0
        return float(value)

    def collect_keyword_data(self) -> Dict[str, Any]:
        """
        모든 키워드에 대한 상세 데이터를 수집하여 DB에 저장합니다.

        Returns:
            {
                "total_keywords": int,
                "collected": int,
                "related_found": int,
                "collected_date": str,
            }
        """
        result = {
            "total_keywords": 0,
            "collected": 0,
            "related_found": 0,
            "collected_date": datetime.now().strftime("%Y-%m-%d"),
        }

        if self.disabled:
            logger.warning("Naver Ad API가 비활성화 상태입니다. 수집을 건너뜁니다.")
            return result

        # 키워드 로드
        keywords = self._load_keywords()
        if not keywords:
            logger.warning("수집할 키워드가 없습니다.")
            return result

        result["total_keywords"] = len(keywords)
        collected_date = result["collected_date"]

        logger.info(f"키워드 데이터 수집 시작: {len(keywords)}개 키워드")

        # API 호출
        if self.ad_manager and not getattr(self.ad_manager, 'disabled', False):
            # NaverAdManager 활용 (get_keyword_volumes는 캐싱 지원)
            logger.info("NaverAdManager를 통한 수집...")
            raw_items = self._fetch_via_ad_manager(keywords)
        else:
            # 직접 API 호출
            logger.info("직접 API 호출을 통한 수집...")
            raw_items = self._fetch_keyword_data_direct(keywords)

        if not raw_items:
            logger.warning("API에서 데이터를 받지 못했습니다.")
            return result

        logger.info(f"API로부터 {len(raw_items)}개 키워드 데이터 수신")

        # 원본 키워드 세트 (정규화)
        original_keywords_normalized = {k.replace(" ", "") for k in keywords}

        # DB 저장
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for item in raw_items:
                    try:
                        kw = item.get("relKeyword", "").strip()
                        if not kw:
                            continue

                        # 검색량 파싱
                        pc_search = self._parse_count_value(item.get("monthlyPcQcCnt", 0))
                        mo_search = self._parse_count_value(item.get("monthlyMobileQcCnt", 0))
                        total_vol = pc_search + mo_search

                        # 클릭수 파싱
                        pc_click = self._parse_float_value(item.get("monthlyPcClkCnt", 0))
                        mo_click = self._parse_float_value(item.get("monthlyMobileClkCnt", 0))

                        # CTR 파싱
                        pc_ctr = self._parse_float_value(item.get("monthlyPcCtr", 0))
                        mo_ctr = self._parse_float_value(item.get("monthlyMobileCtr", 0))

                        # 경쟁도 / 광고 수
                        competition = item.get("compIdx", "")
                        avg_ad = self._parse_float_value(item.get("plAvgDepth", 0))

                        # 원본 키워드인지 연관 키워드인지 판별
                        kw_normalized = kw.replace(" ", "")
                        is_related = 0 if kw_normalized in original_keywords_normalized else 1

                        # UPSERT
                        cursor.execute('''
                            INSERT INTO naver_ad_keyword_data
                                (keyword, monthly_search_pc, monthly_search_mobile,
                                 monthly_click_pc, monthly_click_mobile,
                                 monthly_ctr_pc, monthly_ctr_mobile,
                                 competition_level, avg_ad_count,
                                 total_search_volume, is_related, collected_date)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(keyword, collected_date) DO UPDATE SET
                                monthly_search_pc = excluded.monthly_search_pc,
                                monthly_search_mobile = excluded.monthly_search_mobile,
                                monthly_click_pc = excluded.monthly_click_pc,
                                monthly_click_mobile = excluded.monthly_click_mobile,
                                monthly_ctr_pc = excluded.monthly_ctr_pc,
                                monthly_ctr_mobile = excluded.monthly_ctr_mobile,
                                competition_level = excluded.competition_level,
                                avg_ad_count = excluded.avg_ad_count,
                                total_search_volume = excluded.total_search_volume,
                                is_related = excluded.is_related
                        ''', (
                            kw, pc_search, mo_search,
                            pc_click, mo_click,
                            pc_ctr, mo_ctr,
                            competition, avg_ad,
                            total_vol, is_related, collected_date
                        ))

                        result["collected"] += 1

                        # 연관 키워드 저장
                        if is_related:
                            result["related_found"] += 1
                            # 가장 가까운 원본 키워드를 source로 추정
                            source_kw = self._find_source_keyword(kw, keywords)
                            if source_kw:
                                cursor.execute('''
                                    INSERT OR IGNORE INTO naver_ad_related_keywords
                                        (source_keyword, related_keyword, search_volume, collected_date)
                                    VALUES (?, ?, ?, ?)
                                ''', (source_kw, kw, total_vol, collected_date))

                    except Exception as e:
                        logger.warning(f"  키워드 저장 실패 ({item.get('relKeyword', '?')}): {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"DB 저장 오류: {e}")
            logger.error(traceback.format_exc())

        logger.info(f"\n수집 완료:")
        logger.info(f"  원본 키워드: {result['total_keywords']}개")
        logger.info(f"  수집된 데이터: {result['collected']}개")
        logger.info(f"  연관 키워드: {result['related_found']}개")

        return result

    def _fetch_via_ad_manager(self, keywords: List[str]) -> List[Dict[str, Any]]:
        """
        NaverAdManager를 사용하여 원시 API 응답 데이터를 가져옵니다.
        get_keyword_volumes()는 합계만 반환하므로, 상세 데이터를 위해 직접 호출합니다.
        """
        # NaverAdManager의 API 키/시크릿을 빌려와서 직접 호출
        if hasattr(self.ad_manager, 'api_key') and hasattr(self.ad_manager, 'secret_key'):
            self.api_key = self.ad_manager.api_key
            self.secret_key = self.ad_manager.secret_key
            self.customer_id = self.ad_manager.customer_id
            return self._fetch_keyword_data_direct(keywords)
        else:
            logger.warning("NaverAdManager에서 API 키를 가져올 수 없습니다.")
            return []

    def _find_source_keyword(self, related_kw: str, original_keywords: List[str]) -> Optional[str]:
        """연관 키워드의 가능한 원본 키워드를 추정"""
        related_normalized = related_kw.replace(" ", "")

        # 원본 키워드 중 가장 많이 겹치는 것 찾기
        best_match = None
        best_score = 0

        for orig in original_keywords:
            orig_normalized = orig.replace(" ", "")
            # 공통 글자 수 계산 (간단한 유사도)
            common = sum(1 for c in orig_normalized if c in related_normalized)
            score = common / max(len(orig_normalized), 1)

            if score > best_score:
                best_score = score
                best_match = orig

        # 최소 30% 이상 겹쳐야 매칭
        return best_match if best_score >= 0.3 else None

    def get_keyword_report(self, keyword: str = None, days: int = 30) -> List[Dict[str, Any]]:
        """
        키워드 데이터 리포트를 조회합니다.

        Args:
            keyword: 특정 키워드 (None이면 전체)
            days: 조회 기간

        Returns:
            키워드 데이터 목록
        """
        report = []
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                if keyword:
                    cursor.execute('''
                        SELECT keyword, monthly_search_pc, monthly_search_mobile,
                               total_search_volume, competition_level, avg_ad_count,
                               monthly_ctr_pc, monthly_ctr_mobile,
                               collected_date, is_related
                        FROM naver_ad_keyword_data
                        WHERE keyword = ? AND collected_date >= date('now', ?)
                        ORDER BY collected_date DESC
                    ''', (keyword, f'-{days} days'))
                else:
                    cursor.execute('''
                        SELECT keyword, monthly_search_pc, monthly_search_mobile,
                               total_search_volume, competition_level, avg_ad_count,
                               monthly_ctr_pc, monthly_ctr_mobile,
                               collected_date, is_related
                        FROM naver_ad_keyword_data
                        WHERE is_related = 0 AND collected_date >= date('now', ?)
                        ORDER BY total_search_volume DESC
                    ''', (f'-{days} days',))

                for row in cursor.fetchall():
                    report.append({
                        "keyword": row[0],
                        "pc_search": row[1],
                        "mobile_search": row[2],
                        "total_volume": row[3],
                        "competition": row[4],
                        "avg_ad_count": row[5],
                        "pc_ctr": row[6],
                        "mobile_ctr": row[7],
                        "date": row[8],
                        "is_related": bool(row[9]),
                    })

        except Exception as e:
            logger.error(f"리포트 조회 오류: {e}")

        return report

    def get_related_keywords(self, source_keyword: str, min_volume: int = 10) -> List[Dict[str, Any]]:
        """
        특정 키워드의 연관 키워드 목록을 조회합니다.

        Args:
            source_keyword: 원본 키워드
            min_volume: 최소 검색량 필터

        Returns:
            연관 키워드 목록
        """
        related = []
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT r.related_keyword, r.search_volume, r.collected_date,
                           d.competition_level, d.avg_ad_count
                    FROM naver_ad_related_keywords r
                    LEFT JOIN naver_ad_keyword_data d
                        ON r.related_keyword = d.keyword AND r.collected_date = d.collected_date
                    WHERE r.source_keyword = ? AND r.search_volume >= ?
                    ORDER BY r.search_volume DESC
                ''', (source_keyword, min_volume))

                for row in cursor.fetchall():
                    related.append({
                        "keyword": row[0],
                        "volume": row[1],
                        "date": row[2],
                        "competition": row[3],
                        "avg_ad_count": row[4],
                    })

        except Exception as e:
            logger.error(f"연관 키워드 조회 오류: {e}")

        return related


def main():
    """메인 실행 함수"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logger.info("=" * 60)
    logger.info("Naver Ads 키워드 데이터 수집 시작")
    logger.info("=" * 60)

    try:
        collector = NaverAdKeywordCollector()

        # 키워드 데이터 수집
        result = collector.collect_keyword_data()

        logger.info(f"\n최종 결과:")
        logger.info(json.dumps(result, ensure_ascii=False, indent=2))

        # 원본 키워드 리포트 출력
        report = collector.get_keyword_report(days=1)
        if report:
            logger.info(f"\n오늘 수집된 키워드 데이터 ({len(report)}개):")
            logger.info(f"{'키워드':<25} {'PC검색':>8} {'모바일':>8} {'합계':>8} {'경쟁도':>6} {'광고수':>6}")
            logger.info("-" * 75)
            for r in report[:20]:
                logger.info(
                    f"{r['keyword']:<25} {r['pc_search']:>8,} {r['mobile_search']:>8,} "
                    f"{r['total_volume']:>8,} {r['competition']:>6} {r['avg_ad_count']:>6.1f}"
                )

        # 광고 경쟁 강도 분석 (ad_bid_monitor 통합)
        try:
            from scrapers.ad_bid_monitor import AdBidMonitor
            monitor = AdBidMonitor()
            monitor.run()
            logger.info("광고 경쟁 강도 분석 완료")
        except ImportError:
            try:
                from ad_bid_monitor import AdBidMonitor
                monitor = AdBidMonitor()
                monitor.run()
                logger.info("광고 경쟁 강도 분석 완료")
            except Exception as e2:
                logger.warning(f"광고 경쟁 분석 스킵: {e2}")
        except Exception as e:
            logger.warning(f"광고 경쟁 분석 스킵: {e}")

    except Exception as e:
        logger.error(f"실행 오류: {e}")
        logger.error(traceback.format_exc())


if __name__ == "__main__":
    main()
