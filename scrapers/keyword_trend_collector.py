#!/usr/bin/env python3
"""
Keyword Trend Collector - 네이버 DataLab 키워드 트렌드 수집기
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모든 키워드의 일별 검색 트렌드를 DataLab API로 수집합니다.
- 최근 30일 일별 트렌드 수집
- 키워드당 선형 회귀 기울기 계산 (상승/하락 판단)
- 급등/급락 키워드 자동 감지
- 4개 API 키 라운드로빈 로테이션
- Telegram 알림 연동
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
MAX_KEYWORD_GROUPS = 5  # DataLab API limit per request
RATE_LIMIT_DELAY = 0.5  # seconds between requests
TREND_DAYS = 30  # collect last 30 days

# Trend direction thresholds
SLOPE_SURGE_THRESHOLD = 0.5    # slope > 0.5 = surging
SLOPE_DECLINE_THRESHOLD = -0.5  # slope < -0.5 = declining
ALERT_CHANGE_THRESHOLD = 30.0   # Telegram alert if > 30% change


class KeywordTrendCollector:
    """네이버 DataLab API를 사용하여 키워드 일별 트렌드를 수집합니다."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self._ensure_table()
        self._load_api_keys()
        self._load_keywords()
        self._init_telegram()
        self._last_request_time = 0

    # ========================================================================
    # Initialization
    # ========================================================================

    def _ensure_table(self):
        """keyword_trend_daily 테이블이 없으면 생성합니다."""
        with self.db.get_new_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS keyword_trend_daily (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    trend_date TEXT NOT NULL,
                    ratio REAL DEFAULT 0.0,
                    collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(keyword, trend_date)
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_keyword_trend_date
                ON keyword_trend_daily (keyword, trend_date DESC)
            """)
            conn.commit()
        logger.info("keyword_trend_daily 테이블 준비 완료")

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
            logger.warning("DataLab API 키를 찾을 수 없습니다. 트렌드 수집이 불가합니다.")

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

        logger.info(f"트렌드 수집 대상 키워드 {len(self.keywords)}개 로드")

    def _init_telegram(self):
        """Telegram 알림 봇을 초기화합니다."""
        self.telegram_bot = None
        try:
            from alert_bot import TelegramBot, AlertPriority
            self.AlertPriority = AlertPriority

            token = self.config.get_api_key('TELEGRAM_BOT_TOKEN')
            chat_id = self.config.get_api_key('TELEGRAM_CHAT_ID')
            self.telegram_bot = TelegramBot(token=token, chat_id=chat_id)
            logger.info("Telegram 알림 봇 초기화 완료")
        except ImportError:
            logger.info("alert_bot 모듈 없음, Telegram 알림 비활성화")
        except Exception as e:
            logger.warning(f"Telegram 봇 초기화 실패: {e}")

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
            logger.info(f"API 키 로테이션 -> 인덱스 {self.current_key_index}")

    def _rate_limit(self):
        """요청 간 딜레이를 적용합니다."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMIT_DELAY:
            time.sleep(RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = time.time()

    # ========================================================================
    # DataLab API
    # ========================================================================

    def _fetch_trends(self, keywords: List[str], start_date: str, end_date: str) -> Optional[Dict[str, Any]]:
        """
        DataLab API로 키워드 그룹의 트렌드 데이터를 조회합니다.

        Args:
            keywords: 키워드 리스트 (최대 5개)
            start_date: 시작일 (YYYY-MM-DD)
            end_date: 종료일 (YYYY-MM-DD)

        Returns:
            API 응답 JSON 또는 None (실패 시)
        """
        if not self.api_keys:
            return None

        keyword_groups = []
        for kw in keywords:
            keyword_groups.append({
                "groupName": kw,
                "keywords": [kw]
            })

        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": keyword_groups
        }

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
                    return response.json()

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
    # Collection
    # ========================================================================

    def collect_trends(self) -> Dict[str, Any]:
        """
        모든 키워드의 최근 30일 트렌드 데이터를 수집합니다.

        Returns:
            수집 결과 요약 dict
        """
        if not self.keywords:
            print("[WARN] 수집할 키워드가 없습니다.")
            return {"collected": 0, "failed": 0}

        if not self.api_keys:
            print("[WARN] DataLab API 키가 설정되지 않았습니다.")
            return {"collected": 0, "failed": 0}

        today = datetime.now()
        end_date = today.strftime("%Y-%m-%d")
        start_date = (today - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f" Keyword Trend Collector")
        print(f" 기간: {start_date} ~ {end_date}")
        print(f" 키워드: {len(self.keywords)}개")
        print(f" API 키: {len(self.api_keys)}개")
        print(f"{'='*60}\n")

        # Batch keywords into groups of MAX_KEYWORD_GROUPS
        batches = []
        for i in range(0, len(self.keywords), MAX_KEYWORD_GROUPS):
            batches.append(self.keywords[i:i + MAX_KEYWORD_GROUPS])

        total_collected = 0
        total_failed = 0
        all_trend_data = {}  # keyword -> [{"date": ..., "ratio": ...}, ...]

        for batch_idx, batch in enumerate(batches):
            batch_str = ", ".join(batch)
            print(f"[{batch_idx + 1}/{len(batches)}] 배치 수집: {batch_str}")

            data = self._fetch_trends(batch, start_date, end_date)

            if not data or 'results' not in data:
                logger.warning(f"배치 {batch_idx + 1} 데이터 없음")
                total_failed += len(batch)
                continue

            # Parse and store results
            results = data.get('results', [])
            for result in results:
                keyword = result.get('title', '')
                data_points = result.get('data', [])

                if not keyword or not data_points:
                    total_failed += 1
                    continue

                trend_records = []
                for dp in data_points:
                    trend_records.append({
                        "date": dp.get('period', ''),
                        "ratio": float(dp.get('ratio', 0.0))
                    })

                all_trend_data[keyword] = trend_records
                total_collected += 1

            # Rotate key after each batch
            self._rotate_key()

        # Save to DB
        if all_trend_data:
            self._save_trends(all_trend_data)

        print(f"\n>> 수집 완료: {total_collected}개 키워드, 실패: {total_failed}개")

        return {
            "collected": total_collected,
            "failed": total_failed,
            "trend_data": all_trend_data
        }

    def _save_trends(self, trend_data: Dict[str, List[Dict[str, Any]]]):
        """트렌드 데이터를 DB에 UPSERT합니다."""
        saved_count = 0

        try:
            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                for keyword, records in trend_data.items():
                    for record in records:
                        try:
                            cursor.execute("""
                                INSERT OR REPLACE INTO keyword_trend_daily
                                    (keyword, trend_date, ratio, collected_at)
                                VALUES (?, ?, ?, ?)
                            """, (
                                keyword,
                                record['date'],
                                record['ratio'],
                                datetime.now().isoformat()
                            ))
                            saved_count += 1
                        except Exception as e:
                            logger.warning(f"레코드 저장 실패 ({keyword}, {record['date']}): {e}")

                conn.commit()

        except Exception as e:
            logger.error(f"트렌드 데이터 DB 저장 오류: {e}")
            logger.debug(traceback.format_exc())

        logger.info(f"트렌드 레코드 {saved_count}건 저장 완료")

    # ========================================================================
    # Analysis
    # ========================================================================

    @staticmethod
    def _calculate_slope(ratios: List[float]) -> float:
        """
        선형 회귀 기울기를 계산합니다.

        Args:
            ratios: 일별 ratio 값 리스트

        Returns:
            기울기 (양수=상승, 음수=하락)
        """
        n = len(ratios)
        if n < 5:
            return 0.0

        xs = list(range(n))
        ys = ratios

        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x * y for x, y in zip(xs, ys))
        sum_xx = sum(x * x for x in xs)

        denominator = n * sum_xx - sum_x * sum_x
        if denominator == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return round(slope, 4)

    @staticmethod
    def _get_direction_arrow(slope: float) -> str:
        """기울기에 따른 방향 화살표를 반환합니다."""
        if slope > 1.0:
            return "↑"    # 급상승
        elif slope > 0.3:
            return "↗"   # 상승
        elif slope > -0.3:
            return "→"   # 보합
        elif slope > -1.0:
            return "↘"   # 하락
        else:
            return "↓"    # 급하락

    def analyze_trends(self, trend_data: Optional[Dict[str, List[Dict[str, Any]]]] = None) -> List[Dict[str, Any]]:
        """
        트렌드 분석: 기울기 계산, 급등/급락 감지

        Args:
            trend_data: collect_trends()에서 반환된 데이터 (없으면 DB에서 로드)

        Returns:
            키워드별 분석 결과 리스트
        """
        # DB에서 로드 (trend_data가 없는 경우)
        if trend_data is None:
            trend_data = self._load_trends_from_db()

        if not trend_data:
            print("[WARN] 분석할 트렌드 데이터가 없습니다.")
            return []

        analysis_results = []
        surging = []
        declining = []

        for keyword, records in trend_data.items():
            ratios = [r['ratio'] for r in records]

            if not ratios:
                continue

            slope = self._calculate_slope(ratios)
            current_ratio = ratios[-1] if ratios else 0.0
            avg_ratio = sum(ratios) / len(ratios) if ratios else 0.0
            max_ratio = max(ratios) if ratios else 0.0
            min_ratio = min(ratios) if ratios else 0.0
            direction = self._get_direction_arrow(slope)

            # Percent change (first half vs second half)
            half = len(ratios) // 2
            if half > 0:
                first_half_avg = sum(ratios[:half]) / half
                second_half_avg = sum(ratios[half:]) / (len(ratios) - half)
                if first_half_avg > 0:
                    pct_change = ((second_half_avg - first_half_avg) / first_half_avg) * 100
                else:
                    pct_change = 0.0
            else:
                pct_change = 0.0

            result = {
                "keyword": keyword,
                "current_ratio": current_ratio,
                "avg_ratio": round(avg_ratio, 2),
                "max_ratio": max_ratio,
                "min_ratio": min_ratio,
                "slope": slope,
                "direction": direction,
                "pct_change": round(pct_change, 1),
                "data_points": len(ratios)
            }
            analysis_results.append(result)

            # Detect surging / declining
            if slope > SLOPE_SURGE_THRESHOLD:
                surging.append(result)
            elif slope < SLOPE_DECLINE_THRESHOLD:
                declining.append(result)

        # Sort by slope (descending)
        analysis_results.sort(key=lambda x: x['slope'], reverse=True)

        # Print summary table
        self._print_summary(analysis_results, surging, declining)

        # Telegram alerts for significant changes
        self._send_trend_alerts(surging, declining)

        return analysis_results

    def _load_trends_from_db(self) -> Dict[str, List[Dict[str, Any]]]:
        """DB에서 최근 30일 트렌드 데이터를 로드합니다."""
        trend_data = {}

        try:
            cutoff = (datetime.now() - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT keyword, trend_date, ratio
                    FROM keyword_trend_daily
                    WHERE trend_date >= ?
                    ORDER BY keyword, trend_date ASC
                """, (cutoff,))
                rows = cursor.fetchall()

            for row in rows:
                keyword = row['keyword']
                if keyword not in trend_data:
                    trend_data[keyword] = []
                trend_data[keyword].append({
                    "date": row['trend_date'],
                    "ratio": float(row['ratio'])
                })

        except Exception as e:
            logger.error(f"DB에서 트렌드 로드 실패: {e}")
            logger.debug(traceback.format_exc())

        return trend_data

    def _detect_seasonal_patterns(self, keyword: str) -> Optional[Dict[str, Any]]:
        """전월 동기 데이터와 비교하여 계절성 패턴을 감지합니다."""
        try:
            today = datetime.now()
            current_start = (today - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")
            current_end = today.strftime("%Y-%m-%d")

            prev_end = (today - timedelta(days=TREND_DAYS)).strftime("%Y-%m-%d")
            prev_start = (today - timedelta(days=TREND_DAYS * 2)).strftime("%Y-%m-%d")

            with self.db.get_new_connection() as conn:
                cursor = conn.cursor()

                # Current period
                cursor.execute("""
                    SELECT AVG(ratio) as avg_ratio
                    FROM keyword_trend_daily
                    WHERE keyword = ? AND trend_date BETWEEN ? AND ?
                """, (keyword, current_start, current_end))
                current_row = cursor.fetchone()
                current_avg = float(current_row['avg_ratio']) if current_row and current_row['avg_ratio'] else None

                # Previous period
                cursor.execute("""
                    SELECT AVG(ratio) as avg_ratio
                    FROM keyword_trend_daily
                    WHERE keyword = ? AND trend_date BETWEEN ? AND ?
                """, (keyword, prev_start, prev_end))
                prev_row = cursor.fetchone()
                prev_avg = float(prev_row['avg_ratio']) if prev_row and prev_row['avg_ratio'] else None

            if current_avg is not None and prev_avg is not None and prev_avg > 0:
                seasonal_change = ((current_avg - prev_avg) / prev_avg) * 100
                return {
                    "keyword": keyword,
                    "current_avg": round(current_avg, 2),
                    "previous_avg": round(prev_avg, 2),
                    "seasonal_change_pct": round(seasonal_change, 1)
                }

        except Exception as e:
            logger.debug(f"계절성 분석 실패 ({keyword}): {e}")

        return None

    # ========================================================================
    # Output
    # ========================================================================

    def _print_summary(self, results: List[Dict[str, Any]],
                       surging: List[Dict[str, Any]],
                       declining: List[Dict[str, Any]]):
        """트렌드 요약 테이블을 출력합니다."""
        print(f"\n{'='*80}")
        print(f" {'키워드':<25} {'현재':>8} {'평균':>8} {'기울기':>8} {'변화율':>8} {'방향':>4}")
        print(f"{'─'*80}")

        for r in results:
            kw_display = r['keyword'][:24]
            print(
                f" {kw_display:<25} "
                f"{r['current_ratio']:>7.1f} "
                f"{r['avg_ratio']:>7.1f} "
                f"{r['slope']:>+7.4f} "
                f"{r['pct_change']:>+7.1f}% "
                f"  {r['direction']}"
            )

        print(f"{'─'*80}")
        print(f" 총 {len(results)}개 키워드 분석")

        if surging:
            print(f"\n >> 급등 키워드 ({len(surging)}개):")
            for s in surging:
                print(f"    ↑ {s['keyword']} (기울기: {s['slope']:+.4f}, 변화: {s['pct_change']:+.1f}%)")

        if declining:
            print(f"\n >> 급락 키워드 ({len(declining)}개):")
            for d in declining:
                print(f"    ↓ {d['keyword']} (기울기: {d['slope']:+.4f}, 변화: {d['pct_change']:+.1f}%)")

        print(f"{'='*80}\n")

    def _send_trend_alerts(self, surging: List[Dict[str, Any]], declining: List[Dict[str, Any]]):
        """급등/급락 키워드에 대해 Telegram 알림을 발송합니다."""
        if not self.telegram_bot:
            return

        # Filter by alert threshold
        alert_surging = [s for s in surging if abs(s['pct_change']) > ALERT_CHANGE_THRESHOLD]
        alert_declining = [d for d in declining if abs(d['pct_change']) > ALERT_CHANGE_THRESHOLD]

        if not alert_surging and not alert_declining:
            return

        try:
            lines = ["*[Keyword Trend Alert]*", ""]

            if alert_surging:
                lines.append("*급등 키워드:*")
                for s in alert_surging[:5]:  # 최대 5개
                    lines.append(f"  ↑ {s['keyword']} ({s['pct_change']:+.1f}%)")
                lines.append("")

            if alert_declining:
                lines.append("*급락 키워드:*")
                for d in alert_declining[:5]:  # 최대 5개
                    lines.append(f"  ↓ {d['keyword']} ({d['pct_change']:+.1f}%)")
                lines.append("")

            lines.append(f"분석 시각: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

            message = "\n".join(lines)
            priority = self.AlertPriority.WARNING
            if any(abs(s['pct_change']) > 50 for s in alert_surging + alert_declining):
                priority = self.AlertPriority.CRITICAL

            self.telegram_bot.send_message(message, priority=priority)
            logger.info(f"Telegram 트렌드 알림 발송: 급등 {len(alert_surging)}개, 급락 {len(alert_declining)}개")

        except Exception as e:
            logger.error(f"Telegram 알림 발송 실패: {e}")
            logger.debug(traceback.format_exc())

    # ========================================================================
    # Main
    # ========================================================================

    def run(self) -> Dict[str, Any]:
        """트렌드 수집 + 분석을 실행합니다."""
        start_time = time.time()

        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Keyword Trend Collector 시작")

        # 1. Collect
        result = self.collect_trends()
        trend_data = result.get('trend_data', {})

        # 2. Analyze
        analysis = self.analyze_trends(trend_data)

        # 3. Seasonal pattern detection
        seasonal_alerts = []
        for keyword in self.keywords[:10]:  # Top 10 keywords only
            pattern = self._detect_seasonal_patterns(keyword)
            if pattern and abs(pattern['seasonal_change_pct']) > 20:
                seasonal_alerts.append(pattern)

        if seasonal_alerts:
            print(f"\n >> 계절성 변동 감지 ({len(seasonal_alerts)}개):")
            for sa in seasonal_alerts:
                print(
                    f"    {sa['keyword']}: "
                    f"이전 {sa['previous_avg']:.1f} -> 현재 {sa['current_avg']:.1f} "
                    f"({sa['seasonal_change_pct']:+.1f}%)"
                )

        elapsed = time.time() - start_time
        print(f"\n>> 전체 소요 시간: {elapsed:.1f}초")

        return {
            "collected": result.get('collected', 0),
            "failed": result.get('failed', 0),
            "analysis": analysis,
            "seasonal_alerts": seasonal_alerts,
            "elapsed_seconds": round(elapsed, 1)
        }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    collector = KeywordTrendCollector()
    result = collector.run()

    print(f"\n[완료] 수집: {result['collected']}개, 실패: {result['failed']}개")
