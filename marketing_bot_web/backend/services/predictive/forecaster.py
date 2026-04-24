"""
시계열 예측 엔진
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-2] 순위/트렌드/리드 시계열 예측

전략:
1. statsforecast 설치 시: AutoARIMA (자동 파라미터 튜닝)
2. 미설치 시: 가중 이동평균 + 선형회귀 (경량 폴백)
"""

import sqlite3
import math
import logging
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from collections import defaultdict

logger = logging.getLogger(__name__)

# statsforecast 가용 여부
try:
    from statsforecast import StatsForecast
    from statsforecast.models import AutoARIMA, SeasonalNaive
    HAS_STATSFORECAST = True
except ImportError:
    HAS_STATSFORECAST = False


class Forecaster:
    """시계열 예측 엔진"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _query(self, sql: str, params: tuple = ()) -> List[Dict]:
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(sql, params)
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Forecaster DB 조회 실패: {e}")
            return []
        finally:
            if conn:
                conn.close()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 순위 예측
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def forecast_rank(
        self,
        keyword: str,
        device_type: str = "mobile",
        horizon: int = 14,
        lookback_days: int = 60,
    ) -> Dict[str, Any]:
        """
        키워드 순위 예측

        Args:
            keyword: 타겟 키워드
            device_type: mobile/desktop
            horizon: 예측 기간 (일)
            lookback_days: 학습 데이터 기간 (일)

        Returns:
            {historical: [...], forecast: [...], trend, confidence}
        """
        rows = self._query("""
            SELECT date, rank
            FROM rank_history
            WHERE keyword = ? AND device_type = ?
              AND status = 'found' AND rank > 0
              AND date >= date('now', ? || ' days')
            ORDER BY date ASC
        """, (keyword, device_type, f"-{lookback_days}"))

        if len(rows) < 7:
            return {
                "keyword": keyword,
                "device_type": device_type,
                "error": f"데이터 부족 ({len(rows)}건, 최소 7건 필요)",
                "historical": rows,
                "forecast": [],
            }

        # 일별 평균 (같은 날 여러 스캔 시)
        daily = self._aggregate_daily(rows, "rank")
        values = [d["value"] for d in daily]
        dates = [d["date"] for d in daily]

        # 예측
        if HAS_STATSFORECAST and len(values) >= 14:
            forecast_values = self._forecast_statsforecast(values, horizon)
        else:
            forecast_values = self._forecast_fallback(values, horizon)

        # 트렌드 판정
        trend = self._detect_trend(values)

        # 예측 날짜 생성
        last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        forecast_dates = [
            (last_date + timedelta(days=i+1)).strftime("%Y-%m-%d")
            for i in range(horizon)
        ]

        forecast = [
            {"date": d, "rank": max(1, round(v))}
            for d, v in zip(forecast_dates, forecast_values)
        ]

        return {
            "keyword": keyword,
            "device_type": device_type,
            "historical": daily,
            "forecast": forecast,
            "trend": trend,
            "method": "AutoARIMA" if HAS_STATSFORECAST and len(values) >= 14 else "가중이동평균+선형회귀",
            "data_points": len(daily),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 리드 전환 예측
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def forecast_leads(
        self,
        horizon: int = 14,
        lookback_days: int = 60,
    ) -> Dict[str, Any]:
        """일별 리드 수 예측"""
        rows = self._query("""
            SELECT date(created_at) as date, COUNT(*) as count
            FROM viral_targets
            WHERE created_at >= datetime('now', ? || ' days')
              AND status IN ('new', 'contacted', 'converted')
            GROUP BY date(created_at)
            ORDER BY date ASC
        """, (f"-{lookback_days}",))

        if len(rows) < 7:
            return {
                "error": f"데이터 부족 ({len(rows)}건)",
                "historical": rows,
                "forecast": [],
            }

        values = [r["count"] for r in rows]
        dates = [r["date"] for r in rows]

        if HAS_STATSFORECAST and len(values) >= 14:
            forecast_values = self._forecast_statsforecast(values, horizon)
        else:
            forecast_values = self._forecast_fallback(values, horizon)

        last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        forecast = [
            {
                "date": (last_date + timedelta(days=i+1)).strftime("%Y-%m-%d"),
                "leads": max(0, round(v)),
            }
            for i, v in enumerate(forecast_values)
        ]

        trend = self._detect_trend(values)

        return {
            "historical": [{"date": r["date"], "leads": r["count"]} for r in rows],
            "forecast": forecast,
            "trend": trend,
            "method": "AutoARIMA" if HAS_STATSFORECAST and len(values) >= 14 else "가중이동평균+선형회귀",
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 키워드 검색량 트렌드 예측
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def forecast_keyword_trend(
        self,
        keyword: str,
        horizon: int = 30,
    ) -> Dict[str, Any]:
        """DataLab 트렌드 데이터 기반 검색량 예측"""
        rows = self._query("""
            SELECT date, ratio
            FROM keyword_trend_daily
            WHERE keyword = ?
            ORDER BY date ASC
        """, (keyword,))

        if len(rows) < 14:
            return {
                "keyword": keyword,
                "error": f"트렌드 데이터 부족 ({len(rows)}건)",
                "historical": rows,
                "forecast": [],
            }

        values = [r["ratio"] for r in rows]
        dates = [r["date"] for r in rows]

        if HAS_STATSFORECAST and len(values) >= 30:
            forecast_values = self._forecast_statsforecast(values, horizon, season_length=7)
        else:
            forecast_values = self._forecast_fallback(values, horizon)

        last_date = datetime.strptime(dates[-1], "%Y-%m-%d")
        forecast = [
            {
                "date": (last_date + timedelta(days=i+1)).strftime("%Y-%m-%d"),
                "ratio": round(max(0, v), 2),
            }
            for i, v in enumerate(forecast_values)
        ]

        return {
            "keyword": keyword,
            "historical": [{"date": r["date"], "ratio": r["ratio"]} for r in rows],
            "forecast": forecast,
            "trend": self._detect_trend(values),
        }

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 내부 예측 엔진
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def _forecast_statsforecast(
        self, values: List[float], horizon: int, season_length: int = 7
    ) -> List[float]:
        """statsforecast AutoARIMA 예측"""
        try:
            import pandas as pd
            import numpy as np

            df = pd.DataFrame({
                "unique_id": ["series"] * len(values),
                "ds": pd.date_range(end=pd.Timestamp.now().normalize(), periods=len(values), freq="D"),
                "y": values,
            })

            models = [AutoARIMA(season_length=season_length)]
            sf = StatsForecast(models=models, freq="D")
            forecast_df = sf.forecast(df=df, h=horizon)

            return forecast_df["AutoARIMA"].tolist()

        except Exception as e:
            logger.warning(f"statsforecast 실패, 폴백 사용: {e}")
            return self._forecast_fallback(values, horizon)

    def _forecast_fallback(self, values: List[float], horizon: int) -> List[float]:
        """
        경량 폴백 예측: 가중 이동평균 + 선형회귀 트렌드

        외부 패키지 없이 순수 Python으로 동작
        """
        n = len(values)
        if n == 0:
            return [0] * horizon

        # 가중 이동평균 (최근 값에 가중치)
        window = min(7, n)
        weights = list(range(1, window + 1))
        weight_sum = sum(weights)
        recent = values[-window:]
        wma = sum(v * w for v, w in zip(recent, weights)) / weight_sum

        # 선형회귀로 트렌드 추출
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        # 예측: WMA + 트렌드 반영
        forecast = []
        for i in range(horizon):
            predicted = wma + slope * (i + 1)
            # 노이즈 감쇠 (먼 미래일수록 평균 회귀)
            dampening = 1.0 / (1.0 + 0.05 * i)
            predicted = wma + (predicted - wma) * dampening
            forecast.append(predicted)

        return forecast

    def _aggregate_daily(self, rows: List[Dict], value_key: str) -> List[Dict]:
        """같은 날짜의 값을 평균으로 집계"""
        daily_map = defaultdict(list)
        for r in rows:
            daily_map[r["date"]].append(r[value_key])

        return [
            {"date": date, "value": round(sum(vals) / len(vals), 1)}
            for date, vals in sorted(daily_map.items())
        ]

    def _detect_trend(self, values: List[float], window: int = 7) -> Dict[str, Any]:
        """트렌드 판정 (상승/하락/안정)"""
        if len(values) < window * 2:
            return {"direction": "insufficient_data", "strength": 0}

        first_half = values[-window*2:-window]
        second_half = values[-window:]

        avg_first = sum(first_half) / len(first_half)
        avg_second = sum(second_half) / len(second_half)

        if avg_first == 0:
            change_pct = 0
        else:
            change_pct = ((avg_second - avg_first) / abs(avg_first)) * 100

        if abs(change_pct) < 5:
            direction = "stable"
        elif change_pct > 0:
            direction = "rising"
        else:
            direction = "falling"

        return {
            "direction": direction,
            "change_percent": round(change_pct, 1),
            "recent_avg": round(avg_second, 1),
            "previous_avg": round(avg_first, 1),
        }
