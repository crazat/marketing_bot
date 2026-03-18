#!/usr/bin/env python3
"""
SmartPlace Statistics Collector - 네이버 스마트플레이스 통계 수집기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

네이버 스마트플레이스 센터(smartplace.naver.com)에서 다운로드한
CSV 통계 데이터를 파싱하여 DB에 저장합니다.

3가지 데이터 수집 모드:
  1. Manual CSV Import (Primary) - CSV 파일 직접 임포트
  2. API Integration (Placeholder) - 향후 API 연동 대비
  3. Email Report Parsing - 주간 리포트 이메일 파싱

추가 기능:
  - 통계 요약 (get_stats_summary)
  - 지표 트렌드 (get_trend)
  - 기간 비교 (compare_periods)
  - 전화 추적 데이터 임포트 (import_call_data)

Usage:
    python scrapers/smartplace_stats_collector.py --import path/to/stats.csv
    python scrapers/smartplace_stats_collector.py --import-calls path/to/calls.csv
    python scrapers/smartplace_stats_collector.py --summary 30
    python scrapers/smartplace_stats_collector.py --trend clicks 90
    python scrapers/smartplace_stats_collector.py --compare 2026-01-01 2026-01-31 2026-02-01 2026-02-28
    python scrapers/smartplace_stats_collector.py --import-email path/to/report.json
"""

import os
import sys
import csv
import json
import logging
import traceback
import argparse
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple

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

# CSV 컬럼명 매핑 (한글 -> 영문 DB 컬럼)
COLUMN_MAP_KR = {
    '날짜': 'stat_date',
    '노출': 'impressions',
    '노출수': 'impressions',
    '클릭': 'clicks',
    '클릭수': 'clicks',
    '전화': 'calls',
    '전화수': 'calls',
    '길찾기': 'directions',
    '길찾기수': 'directions',
    '저장': 'saves',
    '저장수': 'saves',
    '공유': 'shares',
    '공유수': 'shares',
    '예약': 'bookings',
    '예약수': 'bookings',
    '블로그리뷰': 'blog_reviews',
    '영수증리뷰': 'receipt_reviews',
}

COLUMN_MAP_EN = {
    'date': 'stat_date',
    'impressions': 'impressions',
    'clicks': 'clicks',
    'calls': 'calls',
    'directions': 'directions',
    'saves': 'saves',
    'shares': 'shares',
    'bookings': 'bookings',
    'blog_reviews': 'blog_reviews',
    'receipt_reviews': 'receipt_reviews',
}

# 날짜 포맷 후보
DATE_FORMATS = [
    '%Y-%m-%d',
    '%Y.%m.%d',
    '%Y/%m/%d',
    '%Y%m%d',
    '%m/%d/%Y',
    '%d/%m/%Y',
]

# 통계 메트릭 컬럼 목록 (stat_date 제외)
METRIC_COLUMNS = [
    'impressions', 'clicks', 'calls', 'directions',
    'saves', 'shares', 'bookings', 'blog_reviews', 'receipt_reviews',
]

# 전화 추적 CSV 컬럼 매핑
CALL_TRACKING_COLUMN_MAP = {
    '날짜': 'stat_date',
    'date': 'stat_date',
    '총 전화수': 'total_calls',
    'total_calls': 'total_calls',
    '네이버 검색 전화': 'naver_search_calls',
    'naver_search_calls': 'naver_search_calls',
    '키워드': 'keyword',
    'keyword': 'keyword',
    '전화번호': 'phone_number',
    'phone_number': 'phone_number',
    '통화시간(초)': 'duration_seconds',
    'duration_seconds': 'duration_seconds',
}


# ============================================================================
# SmartPlace Stats Collector
# ============================================================================

class SmartPlaceStatsCollector:
    """
    네이버 스마트플레이스 통계 데이터 수집 및 분석 클래스.

    3가지 모드 지원:
    1. CSV Import (Manual) - 스마트플레이스에서 다운로드한 CSV 파일 임포트
    2. API (Placeholder) - 향후 API 연동 대비
    3. Email Parsing - 주간 리포트 이메일 파싱
    """

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_tables()

    # ----------------------------------------------------------------
    # Table Setup
    # ----------------------------------------------------------------

    def _ensure_tables(self):
        """smartplace_stats 및 call_tracking 테이블이 없으면 생성합니다."""
        with self.db.get_new_connection() as conn:
            cursor = conn.cursor()

            # 스마트플레이스 통계 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS smartplace_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_date TEXT NOT NULL UNIQUE,
                    impressions INTEGER DEFAULT 0,
                    clicks INTEGER DEFAULT 0,
                    calls INTEGER DEFAULT 0,
                    directions INTEGER DEFAULT 0,
                    saves INTEGER DEFAULT 0,
                    shares INTEGER DEFAULT 0,
                    bookings INTEGER DEFAULT 0,
                    blog_reviews INTEGER DEFAULT 0,
                    receipt_reviews INTEGER DEFAULT 0,
                    conversion_rate REAL DEFAULT 0.0,
                    engagement_rate REAL DEFAULT 0.0,
                    source TEXT DEFAULT 'csv',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # 인덱스
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_smartplace_stats_date
                ON smartplace_stats(stat_date)
            """)

            # 전화 추적 테이블
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS call_tracking (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stat_date TEXT NOT NULL,
                    total_calls INTEGER DEFAULT 0,
                    naver_search_calls INTEGER DEFAULT 0,
                    keyword TEXT,
                    phone_number TEXT,
                    duration_seconds INTEGER DEFAULT 0,
                    source TEXT DEFAULT 'csv',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_call_tracking_date
                ON call_tracking(stat_date)
            """)

            conn.commit()
            logger.info("smartplace_stats / call_tracking 테이블 확인 완료")

    # ----------------------------------------------------------------
    # Mode 1: CSV Import
    # ----------------------------------------------------------------

    def import_csv(self, csv_path: str, update_existing: bool = False) -> Dict[str, Any]:
        """
        스마트플레이스에서 다운로드한 CSV 파일을 파싱하여 DB에 저장합니다.

        Args:
            csv_path: CSV 파일 경로
            update_existing: True이면 기존 데이터 업데이트, False이면 스킵

        Returns:
            dict: {inserted: int, updated: int, skipped: int, errors: int, total: int}
        """
        if not os.path.exists(csv_path):
            logger.error(f"CSV 파일을 찾을 수 없습니다: {csv_path}")
            return {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'total': 0}

        result = {'inserted': 0, 'updated': 0, 'skipped': 0, 'errors': 0, 'total': 0}

        try:
            # CSV 인코딩 감지 (BOM 포함 UTF-8 또는 CP949)
            encoding = self._detect_encoding(csv_path)
            rows = self._parse_csv(csv_path, encoding)

            if not rows:
                logger.warning("CSV에서 파싱된 행이 없습니다.")
                return result

            result['total'] = len(rows)
            logger.info(f"CSV에서 {len(rows)}개 행 파싱 완료 (encoding={encoding})")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for row in rows:
                    try:
                        stat_date = row.get('stat_date')
                        if not stat_date:
                            logger.warning(f"날짜 없는 행 스킵: {row}")
                            result['errors'] += 1
                            continue

                        # 날짜 정규화
                        normalized_date = self._normalize_date(stat_date)
                        if not normalized_date:
                            logger.warning(f"날짜 파싱 실패: {stat_date}")
                            result['errors'] += 1
                            continue

                        # 숫자 값 파싱
                        values = {}
                        for col in METRIC_COLUMNS:
                            raw = row.get(col, 0)
                            values[col] = self._parse_int(raw)

                        # 파생 지표 계산
                        values['conversion_rate'] = self._calc_conversion_rate(
                            values['calls'], values['clicks']
                        )
                        values['engagement_rate'] = self._calc_engagement_rate(
                            values['calls'], values['directions'],
                            values['saves'], values['impressions']
                        )

                        # UPSERT
                        existing = cursor.execute(
                            "SELECT id FROM smartplace_stats WHERE stat_date = ?",
                            (normalized_date,)
                        ).fetchone()

                        if existing:
                            if update_existing:
                                cursor.execute("""
                                    UPDATE smartplace_stats SET
                                        impressions = ?, clicks = ?, calls = ?,
                                        directions = ?, saves = ?, shares = ?,
                                        bookings = ?, blog_reviews = ?, receipt_reviews = ?,
                                        conversion_rate = ?, engagement_rate = ?,
                                        source = 'csv',
                                        updated_at = CURRENT_TIMESTAMP
                                    WHERE stat_date = ?
                                """, (
                                    values['impressions'], values['clicks'], values['calls'],
                                    values['directions'], values['saves'], values['shares'],
                                    values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                                    values['conversion_rate'], values['engagement_rate'],
                                    normalized_date,
                                ))
                                result['updated'] += 1
                            else:
                                result['skipped'] += 1
                        else:
                            cursor.execute("""
                                INSERT INTO smartplace_stats
                                    (stat_date, impressions, clicks, calls, directions,
                                     saves, shares, bookings, blog_reviews, receipt_reviews,
                                     conversion_rate, engagement_rate, source)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'csv')
                            """, (
                                normalized_date,
                                values['impressions'], values['clicks'], values['calls'],
                                values['directions'], values['saves'], values['shares'],
                                values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                                values['conversion_rate'], values['engagement_rate'],
                            ))
                            result['inserted'] += 1

                    except Exception as e:
                        logger.warning(f"행 처리 오류: {e} - row={row}")
                        result['errors'] += 1

                conn.commit()

        except Exception as e:
            logger.error(f"CSV 임포트 실패: {e}\n{traceback.format_exc()}")
            result['errors'] += 1

        logger.info(
            f"CSV 임포트 완료 - "
            f"삽입: {result['inserted']}, 업데이트: {result['updated']}, "
            f"스킵: {result['skipped']}, 오류: {result['errors']}, "
            f"총: {result['total']}"
        )
        return result

    # ----------------------------------------------------------------
    # Mode 2: API Integration (Placeholder)
    # ----------------------------------------------------------------

    def fetch_from_api(self, start_date: str = None, end_date: str = None) -> Dict[str, Any]:
        """
        SmartPlace API를 통한 통계 수집 (Placeholder).

        현재 네이버 스마트플레이스는 공개 API를 제공하지 않습니다.
        향후 API가 제공될 경우 이 메서드를 구현합니다.

        대안:
        - smartplace.naver.com에서 CSV 다운로드 후 import_csv() 사용
        - 주간 리포트 이메일 파싱 (import_email_report())

        Returns:
            dict: {success: False, message: str}
        """
        logger.warning(
            "SmartPlace 직접 API는 현재 제공되지 않습니다. "
            "대신 CSV 임포트를 사용하세요: "
            "python scrapers/smartplace_stats_collector.py --import <csv_path>"
        )
        return {
            'success': False,
            'message': (
                'SmartPlace API 직접 연동은 아직 지원되지 않습니다. '
                'smartplace.naver.com에서 CSV를 다운로드하여 --import 옵션으로 임포트하세요.'
            ),
        }

    # ----------------------------------------------------------------
    # Mode 3: Email Report Parsing
    # ----------------------------------------------------------------

    def import_email_report(self, report_path: str) -> Dict[str, Any]:
        """
        스마트플레이스 주간 리포트 이메일을 파싱합니다.

        지원 포맷:
        - JSON (이메일 -> JSON 변환 후)
        - 텍스트 (이메일 본문 복사)

        Expected JSON format:
        {
            "report_date": "2026-03-15",
            "period_start": "2026-03-08",
            "period_end": "2026-03-14",
            "metrics": {
                "impressions": 1500,
                "clicks": 200,
                "calls": 30,
                "directions": 45,
                "saves": 20,
                "shares": 5
            }
        }

        Args:
            report_path: 리포트 파일 경로 (JSON 또는 TXT)

        Returns:
            dict: {inserted: int, updated: int, errors: int}
        """
        result = {'inserted': 0, 'updated': 0, 'errors': 0}

        if not os.path.exists(report_path):
            logger.error(f"리포트 파일을 찾을 수 없습니다: {report_path}")
            result['errors'] += 1
            return result

        try:
            ext = os.path.splitext(report_path)[1].lower()

            if ext == '.json':
                with open(report_path, 'r', encoding='utf-8') as f:
                    report = json.load(f)
                return self._process_email_json(report)
            elif ext in ('.txt', '.text'):
                with open(report_path, 'r', encoding='utf-8') as f:
                    text = f.read()
                return self._process_email_text(text)
            else:
                logger.error(f"지원하지 않는 파일 형식: {ext} (json 또는 txt만 지원)")
                result['errors'] += 1
                return result

        except json.JSONDecodeError as e:
            logger.error(f"JSON 파싱 오류: {e}")
            result['errors'] += 1
            return result
        except Exception as e:
            logger.error(f"이메일 리포트 파싱 실패: {e}\n{traceback.format_exc()}")
            result['errors'] += 1
            return result

    def _process_email_json(self, report: dict) -> Dict[str, Any]:
        """JSON 형식의 이메일 리포트를 처리합니다."""
        result = {'inserted': 0, 'updated': 0, 'errors': 0}

        try:
            period_start = report.get('period_start')
            period_end = report.get('period_end')
            metrics = report.get('metrics', {})

            if not period_start or not period_end:
                logger.error("리포트에 period_start 또는 period_end가 없습니다.")
                result['errors'] += 1
                return result

            # 주간 리포트를 일별로 균등 분배하거나 합산으로 저장
            # 여기서는 기간의 마지막 날에 합산 데이터로 저장
            normalized_date = self._normalize_date(period_end)
            if not normalized_date:
                logger.error(f"날짜 파싱 실패: {period_end}")
                result['errors'] += 1
                return result

            values = {col: self._parse_int(metrics.get(col, 0)) for col in METRIC_COLUMNS}
            values['conversion_rate'] = self._calc_conversion_rate(
                values['calls'], values['clicks']
            )
            values['engagement_rate'] = self._calc_engagement_rate(
                values['calls'], values['directions'],
                values['saves'], values['impressions']
            )

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                existing = cursor.execute(
                    "SELECT id FROM smartplace_stats WHERE stat_date = ?",
                    (normalized_date,)
                ).fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE smartplace_stats SET
                            impressions = ?, clicks = ?, calls = ?,
                            directions = ?, saves = ?, shares = ?,
                            bookings = ?, blog_reviews = ?, receipt_reviews = ?,
                            conversion_rate = ?, engagement_rate = ?,
                            source = 'email',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE stat_date = ?
                    """, (
                        values['impressions'], values['clicks'], values['calls'],
                        values['directions'], values['saves'], values['shares'],
                        values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                        values['conversion_rate'], values['engagement_rate'],
                        normalized_date,
                    ))
                    result['updated'] += 1
                else:
                    cursor.execute("""
                        INSERT INTO smartplace_stats
                            (stat_date, impressions, clicks, calls, directions,
                             saves, shares, bookings, blog_reviews, receipt_reviews,
                             conversion_rate, engagement_rate, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'email')
                    """, (
                        normalized_date,
                        values['impressions'], values['clicks'], values['calls'],
                        values['directions'], values['saves'], values['shares'],
                        values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                        values['conversion_rate'], values['engagement_rate'],
                    ))
                    result['inserted'] += 1

                conn.commit()

            logger.info(f"이메일 리포트 처리 완료: {period_start} ~ {period_end}")

        except Exception as e:
            logger.error(f"이메일 JSON 처리 오류: {e}")
            result['errors'] += 1

        return result

    def _process_email_text(self, text: str) -> Dict[str, Any]:
        """텍스트 형식의 이메일 리포트를 파싱합니다."""
        result = {'inserted': 0, 'updated': 0, 'errors': 0}

        import re

        # 기간 추출 시도
        period_match = re.search(
            r'(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})\s*[~\-]\s*(\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2})',
            text
        )
        if not period_match:
            logger.error("이메일 텍스트에서 기간을 찾을 수 없습니다.")
            result['errors'] += 1
            return result

        period_end = period_match.group(2)
        normalized_date = self._normalize_date(period_end)
        if not normalized_date:
            result['errors'] += 1
            return result

        # 지표 추출 패턴
        metric_patterns = {
            'impressions': r'노출[수]?\s*[:\s]*([0-9,]+)',
            'clicks': r'클릭[수]?\s*[:\s]*([0-9,]+)',
            'calls': r'전화[수]?\s*[:\s]*([0-9,]+)',
            'directions': r'길찾기[수]?\s*[:\s]*([0-9,]+)',
            'saves': r'저장[수]?\s*[:\s]*([0-9,]+)',
            'shares': r'공유[수]?\s*[:\s]*([0-9,]+)',
        }

        values = {col: 0 for col in METRIC_COLUMNS}
        for metric, pattern in metric_patterns.items():
            match = re.search(pattern, text)
            if match:
                values[metric] = self._parse_int(match.group(1))

        values['conversion_rate'] = self._calc_conversion_rate(
            values['calls'], values['clicks']
        )
        values['engagement_rate'] = self._calc_engagement_rate(
            values['calls'], values['directions'],
            values['saves'], values['impressions']
        )

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                existing = cursor.execute(
                    "SELECT id FROM smartplace_stats WHERE stat_date = ?",
                    (normalized_date,)
                ).fetchone()

                if existing:
                    cursor.execute("""
                        UPDATE smartplace_stats SET
                            impressions = ?, clicks = ?, calls = ?,
                            directions = ?, saves = ?, shares = ?,
                            bookings = ?, blog_reviews = ?, receipt_reviews = ?,
                            conversion_rate = ?, engagement_rate = ?,
                            source = 'email',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE stat_date = ?
                    """, (
                        values['impressions'], values['clicks'], values['calls'],
                        values['directions'], values['saves'], values['shares'],
                        values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                        values['conversion_rate'], values['engagement_rate'],
                        normalized_date,
                    ))
                    result['updated'] += 1
                else:
                    cursor.execute("""
                        INSERT INTO smartplace_stats
                            (stat_date, impressions, clicks, calls, directions,
                             saves, shares, bookings, blog_reviews, receipt_reviews,
                             conversion_rate, engagement_rate, source)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'email')
                    """, (
                        normalized_date,
                        values['impressions'], values['clicks'], values['calls'],
                        values['directions'], values['saves'], values['shares'],
                        values['bookings'], values['blog_reviews'], values['receipt_reviews'],
                        values['conversion_rate'], values['engagement_rate'],
                    ))
                    result['inserted'] += 1

                conn.commit()

            logger.info(f"이메일 텍스트 리포트 처리 완료: {normalized_date}")

        except Exception as e:
            logger.error(f"이메일 텍스트 DB 저장 오류: {e}")
            result['errors'] += 1

        return result

    # ----------------------------------------------------------------
    # Call Tracking Import
    # ----------------------------------------------------------------

    def import_call_data(self, csv_path: str) -> Dict[str, Any]:
        """
        전화 추적 데이터 CSV를 임포트합니다.

        Expected CSV columns: 날짜, 총 전화수, 네이버 검색 전화, 키워드, 전화번호, 통화시간(초)

        Args:
            csv_path: CSV 파일 경로

        Returns:
            dict: {inserted: int, errors: int, total: int}
        """
        result = {'inserted': 0, 'errors': 0, 'total': 0}

        if not os.path.exists(csv_path):
            logger.error(f"전화 추적 CSV 파일을 찾을 수 없습니다: {csv_path}")
            return result

        try:
            encoding = self._detect_encoding(csv_path)
            rows = self._parse_csv(csv_path, encoding, column_map={
                **CALL_TRACKING_COLUMN_MAP
            })

            if not rows:
                logger.warning("전화 추적 CSV에서 파싱된 행이 없습니다.")
                return result

            result['total'] = len(rows)
            logger.info(f"전화 추적 CSV에서 {len(rows)}개 행 파싱 완료")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for row in rows:
                    try:
                        stat_date = row.get('stat_date')
                        if not stat_date:
                            result['errors'] += 1
                            continue

                        normalized_date = self._normalize_date(stat_date)
                        if not normalized_date:
                            result['errors'] += 1
                            continue

                        cursor.execute("""
                            INSERT INTO call_tracking
                                (stat_date, total_calls, naver_search_calls,
                                 keyword, phone_number, duration_seconds, source)
                            VALUES (?, ?, ?, ?, ?, ?, 'csv')
                        """, (
                            normalized_date,
                            self._parse_int(row.get('total_calls', 0)),
                            self._parse_int(row.get('naver_search_calls', 0)),
                            row.get('keyword', ''),
                            row.get('phone_number', ''),
                            self._parse_int(row.get('duration_seconds', 0)),
                        ))
                        result['inserted'] += 1

                    except Exception as e:
                        logger.warning(f"전화 추적 행 처리 오류: {e}")
                        result['errors'] += 1

                conn.commit()

        except Exception as e:
            logger.error(f"전화 추적 CSV 임포트 실패: {e}\n{traceback.format_exc()}")
            result['errors'] += 1

        logger.info(
            f"전화 추적 임포트 완료 - "
            f"삽입: {result['inserted']}, 오류: {result['errors']}, 총: {result['total']}"
        )
        return result

    # ----------------------------------------------------------------
    # Analysis / Query Methods
    # ----------------------------------------------------------------

    def get_stats_summary(self, days: int = 30) -> Dict[str, Any]:
        """
        최근 N일간 통계 요약을 반환합니다.

        Args:
            days: 조회 기간 (일수)

        Returns:
            dict: {
                period: str,
                total: {impressions, clicks, calls, directions, saves, shares},
                daily_avg: {impressions, clicks, calls, ...},
                conversion_rate: float,
                engagement_rate: float,
                best_day: {date, clicks},
                data_points: int
            }
        """
        summary = {
            'period': f'최근 {days}일',
            'total': {},
            'daily_avg': {},
            'conversion_rate': 0.0,
            'engagement_rate': 0.0,
            'best_day': None,
            'data_points': 0,
        }

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

                # 합계 및 평균
                cursor.execute("""
                    SELECT
                        COUNT(*) as cnt,
                        COALESCE(SUM(impressions), 0) as total_impressions,
                        COALESCE(SUM(clicks), 0) as total_clicks,
                        COALESCE(SUM(calls), 0) as total_calls,
                        COALESCE(SUM(directions), 0) as total_directions,
                        COALESCE(SUM(saves), 0) as total_saves,
                        COALESCE(SUM(shares), 0) as total_shares,
                        COALESCE(SUM(bookings), 0) as total_bookings,
                        COALESCE(AVG(impressions), 0) as avg_impressions,
                        COALESCE(AVG(clicks), 0) as avg_clicks,
                        COALESCE(AVG(calls), 0) as avg_calls,
                        COALESCE(AVG(directions), 0) as avg_directions,
                        COALESCE(AVG(saves), 0) as avg_saves,
                        COALESCE(AVG(shares), 0) as avg_shares
                    FROM smartplace_stats
                    WHERE stat_date >= ?
                """, (cutoff,))

                row = cursor.fetchone()
                if row and row['cnt'] > 0:
                    summary['data_points'] = row['cnt']
                    summary['total'] = {
                        'impressions': row['total_impressions'],
                        'clicks': row['total_clicks'],
                        'calls': row['total_calls'],
                        'directions': row['total_directions'],
                        'saves': row['total_saves'],
                        'shares': row['total_shares'],
                        'bookings': row['total_bookings'],
                    }
                    summary['daily_avg'] = {
                        'impressions': round(row['avg_impressions'], 1),
                        'clicks': round(row['avg_clicks'], 1),
                        'calls': round(row['avg_calls'], 1),
                        'directions': round(row['avg_directions'], 1),
                        'saves': round(row['avg_saves'], 1),
                        'shares': round(row['avg_shares'], 1),
                    }
                    summary['conversion_rate'] = self._calc_conversion_rate(
                        row['total_calls'], row['total_clicks']
                    )
                    summary['engagement_rate'] = self._calc_engagement_rate(
                        row['total_calls'], row['total_directions'],
                        row['total_saves'], row['total_impressions']
                    )

                # 최고 클릭일
                cursor.execute("""
                    SELECT stat_date, clicks
                    FROM smartplace_stats
                    WHERE stat_date >= ?
                    ORDER BY clicks DESC
                    LIMIT 1
                """, (cutoff,))

                best = cursor.fetchone()
                if best:
                    summary['best_day'] = {
                        'date': best['stat_date'],
                        'clicks': best['clicks'],
                    }

        except Exception as e:
            logger.error(f"통계 요약 조회 오류: {e}")

        return summary

    def get_trend(self, metric: str = 'clicks', days: int = 90) -> Dict[str, Any]:
        """
        특정 지표의 트렌드를 분석합니다.

        Args:
            metric: 분석할 지표 (clicks, impressions, calls 등)
            days: 조회 기간 (일수)

        Returns:
            dict: {
                metric: str,
                period: str,
                data: [{date, value}],
                slope: float,
                direction: str (상승/하락/보합),
                weekly_avg: [{week, avg}],
                total: int,
                avg: float
            }
        """
        if metric not in METRIC_COLUMNS:
            logger.error(f"유효하지 않은 지표: {metric} (가능: {METRIC_COLUMNS})")
            return {'metric': metric, 'error': f'유효하지 않은 지표: {metric}'}

        trend = {
            'metric': metric,
            'period': f'최근 {days}일',
            'data': [],
            'slope': 0.0,
            'direction': '데이터 없음',
            'weekly_avg': [],
            'total': 0,
            'avg': 0.0,
        }

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

                cursor.execute(f"""
                    SELECT stat_date, {metric} as value
                    FROM smartplace_stats
                    WHERE stat_date >= ?
                    ORDER BY stat_date ASC
                """, (cutoff,))

                rows = cursor.fetchall()
                if not rows:
                    return trend

                data = [{'date': r['stat_date'], 'value': r['value']} for r in rows]
                trend['data'] = data

                values = [d['value'] for d in data]
                trend['total'] = sum(values)
                trend['avg'] = round(sum(values) / len(values), 1) if values else 0.0

                # 선형 회귀 기울기 계산
                trend['slope'] = self._calculate_slope(values)

                if trend['slope'] > 0.1:
                    trend['direction'] = '상승'
                elif trend['slope'] < -0.1:
                    trend['direction'] = '하락'
                else:
                    trend['direction'] = '보합'

                # 주간 평균 계산
                trend['weekly_avg'] = self._calc_weekly_avg(data)

        except Exception as e:
            logger.error(f"트렌드 분석 오류: {e}")

        return trend

    def compare_periods(
        self,
        period1_start: str, period1_end: str,
        period2_start: str, period2_end: str,
    ) -> Dict[str, Any]:
        """
        두 기간의 통계를 비교합니다.

        Args:
            period1_start: 기간1 시작일 (YYYY-MM-DD)
            period1_end: 기간1 종료일 (YYYY-MM-DD)
            period2_start: 기간2 시작일 (YYYY-MM-DD)
            period2_end: 기간2 종료일 (YYYY-MM-DD)

        Returns:
            dict: {
                period1: {range, total, daily_avg},
                period2: {range, total, daily_avg},
                change: {metric: {absolute, percentage}},
                winner: str
            }
        """
        comparison = {
            'period1': {'range': f'{period1_start} ~ {period1_end}'},
            'period2': {'range': f'{period2_start} ~ {period2_end}'},
            'change': {},
            'winner': '',
        }

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 기간1 합계
                p1 = self._get_period_stats(cursor, period1_start, period1_end)
                # 기간2 합계
                p2 = self._get_period_stats(cursor, period2_start, period2_end)

                comparison['period1']['total'] = p1
                comparison['period2']['total'] = p2

                # 변화량 계산
                compare_metrics = ['impressions', 'clicks', 'calls', 'directions', 'saves', 'shares']
                p2_wins = 0
                p1_wins = 0

                for m in compare_metrics:
                    v1 = p1.get(m, 0)
                    v2 = p2.get(m, 0)
                    absolute = v2 - v1
                    percentage = round((absolute / v1) * 100, 1) if v1 > 0 else 0.0

                    comparison['change'][m] = {
                        'absolute': absolute,
                        'percentage': percentage,
                    }

                    if v2 > v1:
                        p2_wins += 1
                    elif v1 > v2:
                        p1_wins += 1

                if p2_wins > p1_wins:
                    comparison['winner'] = 'period2'
                elif p1_wins > p2_wins:
                    comparison['winner'] = 'period1'
                else:
                    comparison['winner'] = 'tie'

        except Exception as e:
            logger.error(f"기간 비교 오류: {e}")

        return comparison

    # ----------------------------------------------------------------
    # Internal Helpers
    # ----------------------------------------------------------------

    def _detect_encoding(self, file_path: str) -> str:
        """CSV 파일 인코딩을 감지합니다."""
        # BOM 확인
        with open(file_path, 'rb') as f:
            bom = f.read(3)

        if bom == b'\xef\xbb\xbf':
            return 'utf-8-sig'

        # UTF-8 시도
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(1024)
            return 'utf-8'
        except UnicodeDecodeError:
            pass

        # CP949 (한국어 Windows 기본)
        try:
            with open(file_path, 'r', encoding='cp949') as f:
                f.read(1024)
            return 'cp949'
        except UnicodeDecodeError:
            pass

        # EUC-KR 폴백
        return 'euc-kr'

    def _parse_csv(
        self, csv_path: str, encoding: str,
        column_map: Dict[str, str] = None,
    ) -> List[Dict[str, Any]]:
        """
        CSV 파일을 파싱하여 정규화된 딕셔너리 리스트를 반환합니다.

        Args:
            csv_path: CSV 파일 경로
            encoding: 파일 인코딩
            column_map: 컬럼명 매핑 (None이면 기본 스마트플레이스 매핑 사용)

        Returns:
            list: [{stat_date, impressions, clicks, ...}]
        """
        if column_map is None:
            column_map = {**COLUMN_MAP_KR, **COLUMN_MAP_EN}

        rows = []

        try:
            with open(csv_path, 'r', encoding=encoding, newline='') as f:
                # 첫 줄 읽어서 구분자 감지
                sample = f.read(4096)
                f.seek(0)

                # 탭 구분자 vs 쉼표 구분자 감지
                if '\t' in sample and sample.count('\t') > sample.count(','):
                    delimiter = '\t'
                else:
                    delimiter = ','

                reader = csv.DictReader(f, delimiter=delimiter)

                if not reader.fieldnames:
                    logger.error("CSV 헤더를 읽을 수 없습니다.")
                    return rows

                # 헤더 매핑 (공백 제거)
                header_map = {}
                for field in reader.fieldnames:
                    clean = field.strip().replace('\ufeff', '')
                    mapped = column_map.get(clean)
                    if mapped:
                        header_map[field] = mapped
                    else:
                        # 소문자로도 시도
                        mapped = column_map.get(clean.lower())
                        if mapped:
                            header_map[field] = mapped

                if 'stat_date' not in header_map.values():
                    logger.error(
                        f"CSV에서 날짜 컬럼을 찾을 수 없습니다. "
                        f"헤더: {reader.fieldnames}"
                    )
                    return rows

                for csv_row in reader:
                    row = {}
                    for original_col, mapped_col in header_map.items():
                        value = csv_row.get(original_col, '').strip()
                        row[mapped_col] = value
                    rows.append(row)

        except Exception as e:
            logger.error(f"CSV 파싱 오류: {e}\n{traceback.format_exc()}")

        return rows

    def _normalize_date(self, date_str: str) -> Optional[str]:
        """다양한 날짜 포맷을 YYYY-MM-DD로 정규화합니다."""
        if not date_str:
            return None

        date_str = date_str.strip()

        for fmt in DATE_FORMATS:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue

        logger.warning(f"날짜 포맷을 인식할 수 없습니다: {date_str}")
        return None

    @staticmethod
    def _parse_int(value) -> int:
        """문자열을 정수로 변환합니다 (쉼표, 공백 처리)."""
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if not value:
            return 0

        try:
            cleaned = str(value).strip().replace(',', '').replace(' ', '')
            if not cleaned or cleaned == '-':
                return 0
            return int(float(cleaned))
        except (ValueError, TypeError):
            return 0

    @staticmethod
    def _calc_conversion_rate(calls: int, clicks: int) -> float:
        """전환율 계산: 전화수 / 클릭수 * 100."""
        if clicks <= 0:
            return 0.0
        return round((calls / clicks) * 100, 2)

    @staticmethod
    def _calc_engagement_rate(
        calls: int, directions: int, saves: int, impressions: int
    ) -> float:
        """참여율 계산: (전화 + 길찾기 + 저장) / 노출수 * 100."""
        if impressions <= 0:
            return 0.0
        return round(((calls + directions + saves) / impressions) * 100, 2)

    @staticmethod
    def _calculate_slope(values: List[int]) -> float:
        """간단한 선형 회귀로 기울기를 계산합니다."""
        n = len(values)
        if n < 3:
            return 0.0

        xs = range(n)
        ys = [float(v) for v in values]

        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_xx = sum(x * x for x in xs)

        denominator = (n * sum_xx - sum_x * sum_x)
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return round(slope, 4)

    @staticmethod
    def _calc_weekly_avg(data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """일별 데이터를 주간 평균으로 집계합니다."""
        if not data:
            return []

        weekly = []
        week_data = []
        current_week = None

        for d in data:
            try:
                dt = datetime.strptime(d['date'], '%Y-%m-%d')
                week_num = dt.isocalendar()[1]
                week_key = f"{dt.year}-W{week_num:02d}"

                if current_week is None:
                    current_week = week_key

                if week_key != current_week:
                    if week_data:
                        avg_val = round(sum(week_data) / len(week_data), 1)
                        weekly.append({'week': current_week, 'avg': avg_val})
                    week_data = []
                    current_week = week_key

                week_data.append(d['value'])

            except (ValueError, KeyError):
                continue

        # 마지막 주 처리
        if week_data:
            avg_val = round(sum(week_data) / len(week_data), 1)
            weekly.append({'week': current_week, 'avg': avg_val})

        return weekly

    def _get_period_stats(
        self, cursor, start_date: str, end_date: str,
    ) -> Dict[str, int]:
        """특정 기간의 합계를 조회합니다."""
        cursor.execute("""
            SELECT
                COALESCE(SUM(impressions), 0) as impressions,
                COALESCE(SUM(clicks), 0) as clicks,
                COALESCE(SUM(calls), 0) as calls,
                COALESCE(SUM(directions), 0) as directions,
                COALESCE(SUM(saves), 0) as saves,
                COALESCE(SUM(shares), 0) as shares,
                COALESCE(SUM(bookings), 0) as bookings,
                COUNT(*) as data_points
            FROM smartplace_stats
            WHERE stat_date >= ? AND stat_date <= ?
        """, (start_date, end_date))

        row = cursor.fetchone()
        if row:
            return {
                'impressions': row['impressions'],
                'clicks': row['clicks'],
                'calls': row['calls'],
                'directions': row['directions'],
                'saves': row['saves'],
                'shares': row['shares'],
                'bookings': row['bookings'],
                'data_points': row['data_points'],
            }
        return {col: 0 for col in ['impressions', 'clicks', 'calls', 'directions', 'saves', 'shares', 'bookings', 'data_points']}


# ============================================================================
# CLI Interface
# ============================================================================

def _print_summary(summary: Dict[str, Any]):
    """통계 요약을 콘솔에 출력합니다."""
    print(f"\n{'='*60}")
    print(f"  SmartPlace 통계 요약 ({summary['period']})")
    print(f"{'='*60}")

    if summary['data_points'] == 0:
        print("  데이터가 없습니다. --import 로 CSV를 먼저 임포트하세요.")
        return

    print(f"  데이터 포인트: {summary['data_points']}일")
    print()

    total = summary.get('total', {})
    daily = summary.get('daily_avg', {})

    print(f"  {'지표':<12} {'합계':>10} {'일평균':>10}")
    print(f"  {'-'*34}")
    for m in ['impressions', 'clicks', 'calls', 'directions', 'saves', 'shares']:
        label = {
            'impressions': '노출',
            'clicks': '클릭',
            'calls': '전화',
            'directions': '길찾기',
            'saves': '저장',
            'shares': '공유',
        }.get(m, m)
        t = total.get(m, 0)
        a = daily.get(m, 0)
        print(f"  {label:<12} {t:>10,} {a:>10.1f}")

    print()
    print(f"  전환율 (전화/클릭):  {summary.get('conversion_rate', 0):.2f}%")
    print(f"  참여율 (행동/노출):  {summary.get('engagement_rate', 0):.2f}%")

    best = summary.get('best_day')
    if best:
        print(f"  최고 클릭일:         {best['date']} ({best['clicks']}클릭)")
    print()


def _print_trend(trend: Dict[str, Any]):
    """트렌드 분석 결과를 콘솔에 출력합니다."""
    print(f"\n{'='*60}")
    metric_kr = {
        'impressions': '노출', 'clicks': '클릭', 'calls': '전화',
        'directions': '길찾기', 'saves': '저장', 'shares': '공유',
        'bookings': '예약', 'blog_reviews': '블로그리뷰', 'receipt_reviews': '영수증리뷰',
    }.get(trend['metric'], trend['metric'])

    print(f"  {metric_kr} 트렌드 ({trend['period']})")
    print(f"{'='*60}")

    if not trend.get('data'):
        print("  데이터가 없습니다.")
        return

    print(f"  방향:   {trend['direction']}")
    print(f"  기울기: {trend['slope']}")
    print(f"  합계:   {trend['total']:,}")
    print(f"  평균:   {trend['avg']:.1f}")
    print()

    # 주간 평균 표시
    weekly = trend.get('weekly_avg', [])
    if weekly:
        print(f"  {'주차':<12} {'평균':>10}")
        print(f"  {'-'*24}")
        for w in weekly[-8:]:  # 최근 8주
            print(f"  {w['week']:<12} {w['avg']:>10.1f}")

    # 최근 7일 데이터
    recent = trend['data'][-7:]
    if recent:
        print()
        print(f"  최근 7일:")
        print(f"  {'날짜':<14} {'값':>8}")
        print(f"  {'-'*24}")
        for d in recent:
            print(f"  {d['date']:<14} {d['value']:>8,}")

    print()


def _print_comparison(comparison: Dict[str, Any]):
    """기간 비교 결과를 콘솔에 출력합니다."""
    print(f"\n{'='*60}")
    print(f"  기간 비교 분석")
    print(f"{'='*60}")

    p1 = comparison.get('period1', {})
    p2 = comparison.get('period2', {})

    print(f"  기간1: {p1.get('range', 'N/A')}")
    print(f"  기간2: {p2.get('range', 'N/A')}")
    print()

    change = comparison.get('change', {})
    if change:
        print(f"  {'지표':<12} {'기간1':>10} {'기간2':>10} {'변화':>10} {'변화율':>8}")
        print(f"  {'-'*54}")

        p1_total = p1.get('total', {})
        p2_total = p2.get('total', {})

        for m in ['impressions', 'clicks', 'calls', 'directions', 'saves', 'shares']:
            label = {
                'impressions': '노출', 'clicks': '클릭', 'calls': '전화',
                'directions': '길찾기', 'saves': '저장', 'shares': '공유',
            }.get(m, m)

            v1 = p1_total.get(m, 0)
            v2 = p2_total.get(m, 0)
            c = change.get(m, {})
            abs_change = c.get('absolute', 0)
            pct = c.get('percentage', 0)

            sign = '+' if abs_change > 0 else ''
            print(f"  {label:<12} {v1:>10,} {v2:>10,} {sign}{abs_change:>9,} {sign}{pct:>6.1f}%")

    winner = comparison.get('winner', '')
    if winner == 'period2':
        print(f"\n  결과: 기간2가 더 우수합니다.")
    elif winner == 'period1':
        print(f"\n  결과: 기간1이 더 우수합니다.")
    else:
        print(f"\n  결과: 두 기간이 비슷합니다.")

    print()


def main():
    """CLI 메인 엔트리포인트."""
    parser = argparse.ArgumentParser(
        description='네이버 스마트플레이스 통계 수집기',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
사용 예시:
  %(prog)s --import stats.csv              CSV 통계 임포트
  %(prog)s --import stats.csv --update     기존 데이터 업데이트 포함
  %(prog)s --import-calls calls.csv        전화 추적 데이터 임포트
  %(prog)s --import-email report.json      이메일 리포트 임포트
  %(prog)s --summary 30                    최근 30일 요약
  %(prog)s --trend clicks 90              클릭 트렌드 (90일)
  %(prog)s --compare 2026-01-01 2026-01-31 2026-02-01 2026-02-28
  %(prog)s --api                           API 연동 (placeholder)
        """,
    )

    parser.add_argument(
        '--import', dest='import_csv', metavar='CSV_PATH',
        help='스마트플레이스 통계 CSV 파일 임포트',
    )
    parser.add_argument(
        '--update', action='store_true',
        help='--import 사용 시 기존 데이터 업데이트 (기본: 스킵)',
    )
    parser.add_argument(
        '--import-calls', dest='import_calls', metavar='CSV_PATH',
        help='전화 추적 데이터 CSV 파일 임포트',
    )
    parser.add_argument(
        '--import-email', dest='import_email', metavar='REPORT_PATH',
        help='이메일 리포트 파일 임포트 (JSON 또는 TXT)',
    )
    parser.add_argument(
        '--summary', nargs='?', type=int, const=30, metavar='DAYS',
        help='최근 N일간 통계 요약 (기본: 30일)',
    )
    parser.add_argument(
        '--trend', nargs=2, metavar=('METRIC', 'DAYS'),
        help='지표 트렌드 분석 (예: clicks 90)',
    )
    parser.add_argument(
        '--compare', nargs=4,
        metavar=('P1_START', 'P1_END', 'P2_START', 'P2_END'),
        help='두 기간 비교 (예: 2026-01-01 2026-01-31 2026-02-01 2026-02-28)',
    )
    parser.add_argument(
        '--api', action='store_true',
        help='SmartPlace API 연동 시도 (현재 placeholder)',
    )

    args = parser.parse_args()

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(name)s] %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
    )

    collector = SmartPlaceStatsCollector()

    # 아무 인자도 없으면 도움말 출력
    if not any([
        args.import_csv, args.import_calls, args.import_email,
        args.summary is not None, args.trend, args.compare, args.api,
    ]):
        parser.print_help()
        return

    # CSV 임포트
    if args.import_csv:
        print(f"\nCSV 임포트: {args.import_csv}")
        result = collector.import_csv(args.import_csv, update_existing=args.update)
        print(f"결과: 삽입 {result['inserted']}, 업데이트 {result['updated']}, "
              f"스킵 {result['skipped']}, 오류 {result['errors']}")

    # 전화 추적 임포트
    if args.import_calls:
        print(f"\n전화 추적 임포트: {args.import_calls}")
        result = collector.import_call_data(args.import_calls)
        print(f"결과: 삽입 {result['inserted']}, 오류 {result['errors']}")

    # 이메일 리포트 임포트
    if args.import_email:
        print(f"\n이메일 리포트 임포트: {args.import_email}")
        result = collector.import_email_report(args.import_email)
        print(f"결과: 삽입 {result['inserted']}, 업데이트 {result['updated']}, "
              f"오류 {result['errors']}")

    # API 연동
    if args.api:
        result = collector.fetch_from_api()
        print(f"\n{result['message']}")

    # 통계 요약
    if args.summary is not None:
        summary = collector.get_stats_summary(days=args.summary)
        _print_summary(summary)

    # 트렌드 분석
    if args.trend:
        metric = args.trend[0]
        try:
            days = int(args.trend[1])
        except ValueError:
            print(f"오류: DAYS는 정수여야 합니다: {args.trend[1]}")
            return
        trend = collector.get_trend(metric=metric, days=days)
        _print_trend(trend)

    # 기간 비교
    if args.compare:
        comparison = collector.compare_periods(
            args.compare[0], args.compare[1],
            args.compare[2], args.compare[3],
        )
        _print_comparison(comparison)


if __name__ == '__main__':
    main()
