#!/usr/bin/env python3
"""
Ad Bid Monitor - 광고 경쟁 강도 추적기
========================================

기존 naver_ad_keyword_data 테이블의 데이터를 분석하여
광고 경쟁 강도 변화를 시계열로 추적합니다.
- 외부 API 호출 없음 (기존 DB 데이터 분석)
- 광고 수, 경쟁도, 검색량 변화 감지
- 경쟁 심화 키워드 자동 감지
- Telegram 알림 (경쟁 급등 시)

Usage:
    python scrapers/ad_bid_monitor.py
"""

import sys
import os
import time
import json
import logging
import traceback
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from collections import defaultdict

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

# Competition level numeric mapping
COMPETITION_LEVEL_MAP = {
    "높음": 3,
    "HIGH": 3,
    "중간": 2,
    "MEDIUM": 2,
    "낮음": 1,
    "LOW": 1,
    "": 0,
}

# Intensity thresholds
AD_COUNT_CHANGE_THRESHOLD = 1.0    # ad count change > 1 = significant
INTENSITY_HIGH_THRESHOLD = 70.0     # score > 70 = alert worthy
COMPETITION_UPGRADE_ALERT = True    # alert on competition level upgrade


class AdBidMonitor:
    """기존 naver_ad_keyword_data를 분석하여 광고 경쟁 강도 변화를 추적합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._init_telegram()

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """ad_competition_tracking 테이블이 없으면 생성합니다."""
        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS ad_competition_tracking (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        keyword TEXT NOT NULL,
                        tracking_date TEXT NOT NULL,
                        avg_ad_count REAL DEFAULT 0,
                        competition_level TEXT,
                        total_search_volume INTEGER DEFAULT 0,
                        ad_count_change REAL DEFAULT 0,
                        competition_change TEXT DEFAULT 'stable',
                        intensity_score REAL DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(keyword, tracking_date)
                    )
                """)
                cursor.execute("""
                    CREATE INDEX IF NOT EXISTS idx_ad_competition_keyword_date
                    ON ad_competition_tracking (keyword, tracking_date DESC)
                """)
                conn.commit()
        except Exception as e:
            logger.error(f"ad_competition_tracking 테이블 생성 실패: {e}")
            raise
        logger.info("ad_competition_tracking 테이블 준비 완료")

    def _init_telegram(self):
        """Telegram 알림 봇을 초기화합니다."""
        self.telegram_bot = None
        try:
            from alert_bot import TelegramBot

            token = self.config.get_api_key('TELEGRAM_BOT_TOKEN')
            chat_id = self.config.get_api_key('TELEGRAM_CHAT_ID')
            self.telegram_bot = TelegramBot(token=token, chat_id=chat_id)
            logger.info("Telegram 알림 봇 초기화 완료")
        except ImportError:
            logger.info("alert_bot 모듈 없음, Telegram 알림 비활성화")
        except Exception as e:
            logger.warning(f"Telegram 봇 초기화 실패: {e}")

    # ========================================================================
    # Data Retrieval
    # ========================================================================

    def _get_latest_ad_data(self) -> Dict[str, Dict[str, Any]]:
        """
        naver_ad_keyword_data 테이블에서 최신 데이터를 가져옵니다.

        Returns:
            {keyword: {avg_ad_count, competition_level, total_search_volume, collected_date}}
        """
        result = {}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 가장 최근 collected_date 확인
                cursor.execute("""
                    SELECT MAX(collected_date) as latest_date
                    FROM naver_ad_keyword_data
                    WHERE is_related = 0
                """)
                row = cursor.fetchone()
                latest_date = row[0] if row and row[0] else None

                if not latest_date:
                    logger.warning("naver_ad_keyword_data에 데이터가 없습니다.")
                    return result

                logger.info(f"최신 수집일: {latest_date}")

                # 해당 날짜의 원본 키워드 데이터 로드
                cursor.execute("""
                    SELECT keyword, avg_ad_count, competition_level,
                           total_search_volume, collected_date
                    FROM naver_ad_keyword_data
                    WHERE collected_date = ? AND is_related = 0
                    ORDER BY keyword
                """, (latest_date,))

                for row in cursor.fetchall():
                    result[row[0]] = {
                        "avg_ad_count": float(row[1]) if row[1] else 0.0,
                        "competition_level": row[2] or "",
                        "total_search_volume": int(row[3]) if row[3] else 0,
                        "collected_date": row[4],
                    }

        except Exception as e:
            logger.error(f"최신 광고 데이터 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        return result

    def _get_previous_ad_data(self, exclude_date: str) -> Dict[str, Dict[str, Any]]:
        """
        이전 수집 데이터를 가져옵니다 (비교용).

        Args:
            exclude_date: 제외할 날짜 (최신 날짜)

        Returns:
            {keyword: {avg_ad_count, competition_level, total_search_volume, collected_date}}
        """
        result = {}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 최신 날짜 제외 가장 최근 날짜
                cursor.execute("""
                    SELECT MAX(collected_date) as prev_date
                    FROM naver_ad_keyword_data
                    WHERE is_related = 0 AND collected_date < ?
                """, (exclude_date,))
                row = cursor.fetchone()
                prev_date = row[0] if row and row[0] else None

                if not prev_date:
                    logger.info("이전 수집 데이터가 없습니다 (첫 수집)")
                    return result

                logger.info(f"이전 수집일: {prev_date}")

                cursor.execute("""
                    SELECT keyword, avg_ad_count, competition_level,
                           total_search_volume, collected_date
                    FROM naver_ad_keyword_data
                    WHERE collected_date = ? AND is_related = 0
                    ORDER BY keyword
                """, (prev_date,))

                for row in cursor.fetchall():
                    result[row[0]] = {
                        "avg_ad_count": float(row[1]) if row[1] else 0.0,
                        "competition_level": row[2] or "",
                        "total_search_volume": int(row[3]) if row[3] else 0,
                        "collected_date": row[4],
                    }

        except Exception as e:
            logger.error(f"이전 광고 데이터 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        return result

    def _get_previous_tracking(self) -> Dict[str, Dict[str, Any]]:
        """
        이전 ad_competition_tracking 데이터를 가져옵니다 (추세 비교용).

        Returns:
            {keyword: {intensity_score, competition_change, tracking_date}}
        """
        result = {}

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # 각 키워드의 가장 최근 tracking 데이터
                cursor.execute("""
                    SELECT act.keyword, act.intensity_score, act.competition_change,
                           act.tracking_date, act.avg_ad_count
                    FROM ad_competition_tracking act
                    INNER JOIN (
                        SELECT keyword, MAX(tracking_date) as max_date
                        FROM ad_competition_tracking
                        GROUP BY keyword
                    ) latest ON act.keyword = latest.keyword
                        AND act.tracking_date = latest.max_date
                """)

                for row in cursor.fetchall():
                    result[row[0]] = {
                        "intensity_score": float(row[1]) if row[1] else 0.0,
                        "competition_change": row[2] or "stable",
                        "tracking_date": row[3],
                        "avg_ad_count": float(row[4]) if row[4] else 0.0,
                    }

        except Exception as e:
            logger.error(f"이전 tracking 데이터 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        return result

    # ========================================================================
    # Analysis
    # ========================================================================

    def _competition_level_to_numeric(self, level: str) -> int:
        """경쟁도 문자열을 숫자로 변환합니다."""
        return COMPETITION_LEVEL_MAP.get(level.strip(), 0)

    def _calculate_intensity_score(self, avg_ad_count: float, competition_level: str,
                                    total_volume: int) -> float:
        """
        경쟁 강도 점수를 계산합니다 (0-100).

        Components:
        - Ad count contribution (0-40): more ads = more competition
        - Competition level (0-30): higher level = more competition
        - Volume factor (0-30): higher volume + ads = more valuable competition
        """
        # Ad count score (0-40)
        # avg_ad_count typically ranges 0-15+
        ad_score = min(40.0, (avg_ad_count / 15.0) * 40.0)

        # Competition level score (0-30)
        level_numeric = self._competition_level_to_numeric(competition_level)
        level_score = (level_numeric / 3.0) * 30.0

        # Volume factor (0-30)
        # Higher volume makes competition more significant
        if total_volume > 0:
            import math
            vol_factor = min(1.0, math.log10(max(1, total_volume)) / 5.0)  # log scale, cap at 100k
            vol_score = vol_factor * 30.0
        else:
            vol_score = 0.0

        total = ad_score + level_score + vol_score
        return round(min(100.0, total), 1)

    def _determine_competition_change(self, current_ad: float, prev_ad: float,
                                       current_level: str, prev_level: str) -> str:
        """
        경쟁 변화 방향을 결정합니다.

        Returns:
            'intensifying', 'stable', or 'declining'
        """
        ad_change = current_ad - prev_ad
        level_current = self._competition_level_to_numeric(current_level)
        level_prev = self._competition_level_to_numeric(prev_level)
        level_change = level_current - level_prev

        # Intensifying conditions
        if ad_change > AD_COUNT_CHANGE_THRESHOLD or level_change > 0:
            return "intensifying"

        # Declining conditions
        if ad_change < -AD_COUNT_CHANGE_THRESHOLD or level_change < 0:
            return "declining"

        return "stable"

    def analyze_competition(self) -> Dict[str, Any]:
        """
        광고 경쟁 강도를 분석하고 DB에 저장합니다.

        Returns:
            분석 결과 요약 dict
        """
        tracking_date = datetime.now().strftime("%Y-%m-%d")

        # 1. Load latest ad data
        latest_data = self._get_latest_ad_data()
        if not latest_data:
            print("[WARN] naver_ad_keyword_data에 데이터가 없습니다.")
            print("       먼저 naver_ad_keyword_collector.py를 실행하세요.")
            return {"analyzed": 0, "intensifying": 0, "declining": 0}

        # Get the collected_date from latest data
        sample_data = next(iter(latest_data.values()))
        latest_date = sample_data['collected_date']

        # 2. Load previous ad data
        prev_data = self._get_previous_ad_data(latest_date)

        # 3. Load previous tracking (for trend continuity)
        prev_tracking = self._get_previous_tracking()

        print(f"\n{'='*60}")
        print(f" Ad Bid Monitor")
        print(f" 최신 데이터: {latest_date} ({len(latest_data)}개 키워드)")
        print(f" 이전 데이터: {len(prev_data)}개 키워드")
        print(f" 이전 추적: {len(prev_tracking)}개 키워드")
        print(f"{'='*60}\n")

        # 4. Analyze each keyword
        results = []
        intensifying_keywords = []
        declining_keywords = []

        for keyword, current in latest_data.items():
            avg_ad_count = current['avg_ad_count']
            competition_level = current['competition_level']
            total_volume = current['total_search_volume']

            # Compare with previous
            prev = prev_data.get(keyword, {})
            prev_ad = prev.get('avg_ad_count', avg_ad_count)
            prev_level = prev.get('competition_level', competition_level)

            ad_count_change = round(avg_ad_count - prev_ad, 2)

            # Determine change direction
            if prev:
                competition_change = self._determine_competition_change(
                    avg_ad_count, prev_ad, competition_level, prev_level
                )
            else:
                competition_change = "stable"

            # Calculate intensity score
            intensity_score = self._calculate_intensity_score(
                avg_ad_count, competition_level, total_volume
            )

            result = {
                "keyword": keyword,
                "tracking_date": tracking_date,
                "avg_ad_count": avg_ad_count,
                "competition_level": competition_level,
                "total_search_volume": total_volume,
                "ad_count_change": ad_count_change,
                "competition_change": competition_change,
                "intensity_score": intensity_score,
            }
            results.append(result)

            if competition_change == "intensifying":
                intensifying_keywords.append(result)
            elif competition_change == "declining":
                declining_keywords.append(result)

        # 5. Save to DB
        self._save_tracking(results)

        # 6. Print summary
        self._print_summary(results, intensifying_keywords, declining_keywords)

        # 7. Send alerts
        self._send_alerts(intensifying_keywords)

        return {
            "analyzed": len(results),
            "intensifying": len(intensifying_keywords),
            "stable": len(results) - len(intensifying_keywords) - len(declining_keywords),
            "declining": len(declining_keywords),
            "results": results,
        }

    def _save_tracking(self, results: List[Dict[str, Any]]):
        """추적 결과를 DB에 저장합니다."""
        saved = 0

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for r in results:
                    try:
                        cursor.execute("""
                            INSERT INTO ad_competition_tracking
                                (keyword, tracking_date, avg_ad_count, competition_level,
                                 total_search_volume, ad_count_change,
                                 competition_change, intensity_score)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(keyword, tracking_date) DO UPDATE SET
                                avg_ad_count = excluded.avg_ad_count,
                                competition_level = excluded.competition_level,
                                total_search_volume = excluded.total_search_volume,
                                ad_count_change = excluded.ad_count_change,
                                competition_change = excluded.competition_change,
                                intensity_score = excluded.intensity_score
                        """, (
                            r['keyword'],
                            r['tracking_date'],
                            r['avg_ad_count'],
                            r['competition_level'],
                            r['total_search_volume'],
                            r['ad_count_change'],
                            r['competition_change'],
                            r['intensity_score'],
                        ))
                        saved += 1
                    except Exception as e:
                        logger.warning(f"tracking 저장 실패 ({r['keyword']}): {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"tracking DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

        logger.info(f"ad_competition_tracking {saved}건 저장 완료")

    # ========================================================================
    # Output
    # ========================================================================

    def _print_summary(self, results: List[Dict[str, Any]],
                       intensifying: List[Dict[str, Any]],
                       declining: List[Dict[str, Any]]):
        """경쟁 강도 요약을 출력합니다."""
        if not results:
            print("  분석 결과가 없습니다.")
            return

        # Sort by intensity score descending
        sorted_results = sorted(results, key=lambda x: x['intensity_score'], reverse=True)

        print(f"\n{'='*95}")
        print(f" {'키워드':<25} {'광고수':>7} {'변화':>7} {'경쟁도':>8} {'검색량':>8} {'강도':>6} {'추세':>12}")
        print(f"{'─'*95}")

        for r in sorted_results:
            kw_display = r['keyword'][:24]
            change_str = f"{r['ad_count_change']:+.1f}" if r['ad_count_change'] != 0 else "0.0"

            change_label = {
                "intensifying": "INTENSIFY",
                "stable": "stable",
                "declining": "declining",
            }.get(r['competition_change'], r['competition_change'])

            print(
                f" {kw_display:<25} "
                f"{r['avg_ad_count']:>6.1f} "
                f"{change_str:>7} "
                f"{r['competition_level']:>8} "
                f"{r['total_search_volume']:>8,} "
                f"{r['intensity_score']:>5.1f} "
                f"{change_label:>12}"
            )

        print(f"{'─'*95}")
        print(f" 총 {len(results)}개 키워드 분석")

        # Summary stats
        avg_intensity = sum(r['intensity_score'] for r in results) / len(results) if results else 0
        max_intensity = max(r['intensity_score'] for r in results) if results else 0
        print(f"\n  평균 경쟁 강도: {avg_intensity:.1f}/100")
        print(f"  최고 경쟁 강도: {max_intensity:.1f}/100")

        if intensifying:
            print(f"\n >> 경쟁 심화 키워드 ({len(intensifying)}개):")
            for i in sorted(intensifying, key=lambda x: x['intensity_score'], reverse=True)[:10]:
                print(
                    f"    * {i['keyword']}: "
                    f"광고수 {i['ad_count_change']:+.1f}, "
                    f"강도 {i['intensity_score']:.1f}"
                )

        if declining:
            print(f"\n >> 경쟁 완화 키워드 ({len(declining)}개):")
            for d in sorted(declining, key=lambda x: x['ad_count_change'])[:5]:
                print(
                    f"    * {d['keyword']}: "
                    f"광고수 {d['ad_count_change']:+.1f}, "
                    f"강도 {d['intensity_score']:.1f}"
                )

        print(f"{'='*95}\n")

    # ========================================================================
    # Telegram Alerts
    # ========================================================================

    def _send_alerts(self, intensifying: List[Dict[str, Any]]):
        """경쟁 심화 키워드에 대해 Telegram 알림을 발송합니다."""
        if not self.telegram_bot:
            return

        # Filter by high intensity
        alert_worthy = [i for i in intensifying if i['intensity_score'] >= INTENSITY_HIGH_THRESHOLD]

        if not alert_worthy:
            return

        try:
            lines = ["[Ad Competition Alert]", ""]
            lines.append(f"경쟁 심화 감지 ({len(alert_worthy)}개 키워드):")

            for item in sorted(alert_worthy, key=lambda x: x['intensity_score'], reverse=True)[:8]:
                lines.append(
                    f"  - {item['keyword']}: "
                    f"강도 {item['intensity_score']:.0f}/100, "
                    f"광고수 {item['ad_count_change']:+.1f}"
                )

            lines.append("")
            lines.append(f"분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

            message = "\n".join(lines)
            self.telegram_bot.send_message(message)
            logger.info(f"Telegram 경쟁 알림 발송: {len(alert_worthy)}개 키워드")

        except Exception as e:
            logger.error(f"Telegram 알림 발송 실패: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Historical Query
    # ========================================================================

    def get_competition_history(self, keyword: Optional[str] = None,
                                 days: int = 30) -> List[Dict[str, Any]]:
        """DB에서 경쟁 추적 이력을 조회합니다. API 엔드포인트용."""
        try:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                if keyword:
                    cursor.execute("""
                        SELECT * FROM ad_competition_tracking
                        WHERE keyword = ? AND tracking_date >= ?
                        ORDER BY tracking_date DESC
                    """, (keyword, cutoff))
                else:
                    # Latest tracking for each keyword
                    cursor.execute("""
                        SELECT act.* FROM ad_competition_tracking act
                        INNER JOIN (
                            SELECT keyword, MAX(tracking_date) as max_date
                            FROM ad_competition_tracking
                            GROUP BY keyword
                        ) latest ON act.keyword = latest.keyword
                            AND act.tracking_date = latest.max_date
                        ORDER BY act.intensity_score DESC
                    """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"경쟁 이력 조회 오류: {e}")
            return []

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """광고 경쟁 분석을 실행합니다."""
        start_time = time.time()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Ad Bid Monitor 시작")

        result = self.analyze_competition()

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")

        return {
            "analyzed": result.get('analyzed', 0),
            "intensifying": result.get('intensifying', 0),
            "stable": result.get('stable', 0),
            "declining": result.get('declining', 0),
            "elapsed_seconds": round(elapsed, 1)
        }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        monitor = AdBidMonitor()
        result = monitor.run()
        print(
            f"\n[완료] 분석: {result['analyzed']}개, "
            f"심화: {result['intensifying']}개, "
            f"안정: {result['stable']}개, "
            f"완화: {result['declining']}개"
        )
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
