"""
Analytics Module - Time-Series Analysis & Insights
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2.4] 시계열 분석 시스템
- 순위 트렌드 분석
- 키워드 성장 분석
- 경쟁사 활동 패턴 분석
- 이상치 감지
"""

import os
import sys
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from collections import defaultdict
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


@dataclass
class TrendPoint:
    """트렌드 데이터 포인트"""
    date: str
    value: float
    change: Optional[float] = None  # 전일 대비 변화


@dataclass
class TrendAnalysis:
    """트렌드 분석 결과"""
    trend: str  # up, down, stable, volatile
    slope: float  # 기울기 (양수=상승, 음수=하락)
    volatility: float  # 변동성 (표준편차)
    avg_value: float
    min_value: float
    max_value: float
    data_points: int
    period_days: int


@dataclass
class AnomalyDetection:
    """이상치 감지 결과"""
    detected: bool
    date: str
    value: float
    expected_range: Tuple[float, float]
    severity: str  # minor, moderate, severe
    description: str


class TimeSeriesAnalyzer:
    """
    시계열 분석기

    DB 데이터를 기반으로 트렌드 분석, 이상치 감지 수행
    """

    def __init__(self):
        self.db = None
        self._init_db()
        logger.info("TimeSeriesAnalyzer initialized")

    def _init_db(self):
        """DB 연결"""
        try:
            from db.database import DatabaseManager
            self.db = DatabaseManager()
        except Exception as e:
            logger.error(f"Failed to initialize DB: {e}")

    # ============================================================
    # 순위 트렌드 분석
    # ============================================================

    def analyze_rank_trend(
        self,
        keyword: str,
        target_name: str = "규림한의원",
        days: int = 30
    ) -> Dict[str, Any]:
        """
        키워드 순위 트렌드 분석

        Args:
            keyword: 분석할 키워드
            target_name: 타겟 이름
            days: 분석 기간 (일)

        Returns:
            트렌드 분석 결과
        """
        if not self.db:
            return {"error": "DB not available"}

        try:
            self.db.cursor.execute('''
                SELECT date(checked_at) as date, rank, status
                FROM rank_history
                WHERE keyword = ? AND target_name = ?
                  AND checked_at >= date('now', ?)
                  AND status = 'found'
                GROUP BY date(checked_at)
                ORDER BY date ASC
            ''', (keyword, target_name, f'-{days} days'))

            rows = self.db.cursor.fetchall()

            if not rows:
                return {"error": "No data found", "keyword": keyword}

            data_points = []
            prev_rank = None

            for date, rank, status in rows:
                change = None
                if prev_rank is not None and rank:
                    change = prev_rank - rank  # 양수 = 순위 상승

                data_points.append(TrendPoint(
                    date=date,
                    value=rank if rank else 0,
                    change=change
                ))
                prev_rank = rank

            # 트렌드 분석
            ranks = [p.value for p in data_points if p.value > 0]

            if len(ranks) < 2:
                return {"error": "Insufficient data", "data_points": len(ranks)}

            trend_analysis = self._calculate_trend(ranks, days)

            # 이상치 감지
            anomalies = self._detect_anomalies(data_points)

            return {
                "keyword": keyword,
                "target_name": target_name,
                "trend": trend_analysis.trend,
                "slope": round(trend_analysis.slope, 3),
                "volatility": round(trend_analysis.volatility, 2),
                "avg_rank": round(trend_analysis.avg_value, 1),
                "best_rank": int(trend_analysis.min_value),
                "worst_rank": int(trend_analysis.max_value),
                "data_points": trend_analysis.data_points,
                "period_days": days,
                "recent_data": [
                    {"date": p.date, "rank": int(p.value), "change": p.change}
                    for p in data_points[-7:]
                ],
                "anomalies": [
                    {
                        "date": a.date,
                        "value": a.value,
                        "severity": a.severity,
                        "description": a.description
                    }
                    for a in anomalies
                ],
                "summary": self._generate_rank_summary(trend_analysis, anomalies)
            }

        except Exception as e:
            logger.error(f"Rank trend analysis failed: {e}")
            return {"error": str(e)}

    def _calculate_trend(self, values: List[float], days: int) -> TrendAnalysis:
        """트렌드 계산"""
        n = len(values)

        # 기본 통계
        avg_value = statistics.mean(values)
        volatility = statistics.stdev(values) if n > 1 else 0
        min_value = min(values)
        max_value = max(values)

        # 선형 회귀로 기울기 계산
        x_mean = (n - 1) / 2
        y_mean = avg_value

        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))

        slope = numerator / denominator if denominator != 0 else 0

        # 트렌드 판정
        if abs(slope) < 0.5:
            trend = "stable"
        elif slope > 0:
            trend = "down"  # 순위 숫자가 커짐 = 하락
        else:
            trend = "up"  # 순위 숫자가 작아짐 = 상승

        # 변동성이 높으면 volatile로 표시
        if volatility > avg_value * 0.3:
            trend = "volatile"

        return TrendAnalysis(
            trend=trend,
            slope=slope,
            volatility=volatility,
            avg_value=avg_value,
            min_value=min_value,
            max_value=max_value,
            data_points=n,
            period_days=days
        )

    def _detect_anomalies(self, data_points: List[TrendPoint]) -> List[AnomalyDetection]:
        """이상치 감지"""
        anomalies = []
        values = [p.value for p in data_points if p.value > 0]

        if len(values) < 3:
            return anomalies

        avg = statistics.mean(values)
        std = statistics.stdev(values)

        for p in data_points:
            if p.value <= 0:
                continue

            # Z-score 계산
            z_score = abs(p.value - avg) / std if std > 0 else 0

            if z_score > 3:
                severity = "severe"
            elif z_score > 2:
                severity = "moderate"
            elif z_score > 1.5:
                severity = "minor"
            else:
                continue

            anomalies.append(AnomalyDetection(
                detected=True,
                date=p.date,
                value=p.value,
                expected_range=(avg - 2 * std, avg + 2 * std),
                severity=severity,
                description=f"순위 {int(p.value)}위 (평균 {avg:.1f}위에서 크게 벗어남)"
            ))

        return anomalies

    def _generate_rank_summary(
        self,
        trend: TrendAnalysis,
        anomalies: List[AnomalyDetection]
    ) -> str:
        """순위 트렌드 요약 생성"""
        parts = []

        # 트렌드 설명
        trend_desc = {
            "up": "순위가 상승 추세입니다",
            "down": "순위가 하락 추세입니다",
            "stable": "순위가 안정적입니다",
            "volatile": "순위 변동이 큽니다"
        }
        parts.append(trend_desc.get(trend.trend, ""))

        # 현재 위치
        parts.append(f"평균 {trend.avg_value:.1f}위")

        # 이상치
        severe_anomalies = [a for a in anomalies if a.severity == "severe"]
        if severe_anomalies:
            parts.append(f"주의: {len(severe_anomalies)}회 급격한 변동 발생")

        return ". ".join(parts) + "."

    # ============================================================
    # 키워드 성장 분석
    # ============================================================

    def analyze_keyword_growth(self, days: int = 30) -> Dict[str, Any]:
        """
        키워드 발굴 성장 분석

        신규 발굴된 키워드 수의 시계열 분석
        """
        if not self.db:
            return {"error": "DB not available"}

        try:
            self.db.cursor.execute('''
                SELECT date(discovered_at) as date,
                       COUNT(*) as new_keywords,
                       SUM(CASE WHEN grade IN ('S', 'A') THEN 1 ELSE 0 END) as high_grade
                FROM keyword_insights
                WHERE discovered_at >= date('now', ?)
                GROUP BY date(discovered_at)
                ORDER BY date ASC
            ''', (f'-{days} days',))

            rows = self.db.cursor.fetchall()

            daily_data = []
            total_new = 0
            total_high_grade = 0

            for date, new_count, high_grade in rows:
                daily_data.append({
                    "date": date,
                    "new_keywords": new_count,
                    "high_grade": high_grade or 0
                })
                total_new += new_count
                total_high_grade += high_grade or 0

            # 등급별 분포
            self.db.cursor.execute('''
                SELECT grade, COUNT(*) as count
                FROM keyword_insights
                WHERE discovered_at >= date('now', ?)
                GROUP BY grade
            ''', (f'-{days} days',))

            grade_dist = {row[0]: row[1] for row in self.db.cursor.fetchall()}

            return {
                "period_days": days,
                "total_discovered": total_new,
                "high_grade_count": total_high_grade,
                "high_grade_ratio": round(total_high_grade / total_new * 100, 1) if total_new > 0 else 0,
                "daily_avg": round(total_new / days, 1),
                "grade_distribution": grade_dist,
                "daily_data": daily_data[-14:],  # 최근 14일
                "growth_trend": "up" if len(daily_data) > 1 and daily_data[-1]["new_keywords"] > daily_data[0]["new_keywords"] else "stable"
            }

        except Exception as e:
            logger.error(f"Keyword growth analysis failed: {e}")
            return {"error": str(e)}

    # ============================================================
    # 경쟁사 활동 패턴 분석
    # ============================================================

    def analyze_competitor_activity(
        self,
        competitor_name: str = None,
        days: int = 30
    ) -> Dict[str, Any]:
        """
        경쟁사 활동 패턴 분석

        리뷰 수집량, 감성 분석 트렌드
        """
        if not self.db:
            return {"error": "DB not available"}

        try:
            if competitor_name:
                self.db.cursor.execute('''
                    SELECT date(scraped_at) as date,
                           COUNT(*) as review_count,
                           SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
                           SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative
                    FROM competitor_reviews
                    WHERE competitor_name = ?
                      AND scraped_at >= date('now', ?)
                    GROUP BY date(scraped_at)
                    ORDER BY date ASC
                ''', (competitor_name, f'-{days} days'))
            else:
                self.db.cursor.execute('''
                    SELECT date(scraped_at) as date,
                           COUNT(*) as review_count,
                           SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) as positive,
                           SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) as negative
                    FROM competitor_reviews
                    WHERE scraped_at >= date('now', ?)
                    GROUP BY date(scraped_at)
                    ORDER BY date ASC
                ''', (f'-{days} days',))

            rows = self.db.cursor.fetchall()

            daily_data = []
            total_reviews = 0
            total_positive = 0
            total_negative = 0

            for date, count, positive, negative in rows:
                daily_data.append({
                    "date": date,
                    "reviews": count,
                    "positive": positive or 0,
                    "negative": negative or 0,
                    "sentiment_score": round((positive or 0) / count * 100, 1) if count > 0 else 0
                })
                total_reviews += count
                total_positive += positive or 0
                total_negative += negative or 0

            # 요일별 분석
            weekday_counts = defaultdict(int)
            for d in daily_data:
                try:
                    dt = datetime.strptime(d["date"], "%Y-%m-%d")
                    weekday_counts[dt.strftime("%A")] += d["reviews"]
                except Exception:
                    pass

            return {
                "competitor": competitor_name or "all",
                "period_days": days,
                "total_reviews": total_reviews,
                "positive_ratio": round(total_positive / total_reviews * 100, 1) if total_reviews > 0 else 0,
                "negative_ratio": round(total_negative / total_reviews * 100, 1) if total_reviews > 0 else 0,
                "daily_avg": round(total_reviews / days, 1),
                "daily_data": daily_data[-14:],
                "weekday_pattern": dict(weekday_counts),
                "activity_level": "high" if total_reviews / days > 5 else ("medium" if total_reviews / days > 2 else "low")
            }

        except Exception as e:
            logger.error(f"Competitor activity analysis failed: {e}")
            return {"error": str(e)}

    # ============================================================
    # 종합 대시보드 데이터
    # ============================================================

    def get_analytics_dashboard(self, days: int = 30) -> Dict[str, Any]:
        """종합 분석 대시보드 데이터 반환"""
        return {
            "keyword_growth": self.analyze_keyword_growth(days),
            "competitor_activity": self.analyze_competitor_activity(days=days),
            "top_keywords_trend": self._get_top_keywords_trend(days),
            "generated_at": datetime.now().isoformat()
        }

    def _get_top_keywords_trend(self, days: int = 30) -> List[Dict[str, Any]]:
        """상위 키워드들의 트렌드 분석"""
        if not self.db:
            return []

        try:
            # 최근 체크된 상위 키워드 5개
            self.db.cursor.execute('''
                SELECT DISTINCT keyword
                FROM rank_history
                WHERE status = 'found'
                  AND checked_at >= date('now', '-7 days')
                ORDER BY rank ASC
                LIMIT 5
            ''')

            keywords = [row[0] for row in self.db.cursor.fetchall()]

            results = []
            for kw in keywords:
                analysis = self.analyze_rank_trend(kw, days=days)
                if "error" not in analysis:
                    results.append({
                        "keyword": kw,
                        "trend": analysis.get("trend"),
                        "avg_rank": analysis.get("avg_rank"),
                        "best_rank": analysis.get("best_rank"),
                        "summary": analysis.get("summary")
                    })

            return results

        except Exception as e:
            logger.error(f"Top keywords trend failed: {e}")
            return []


# 싱글톤 인스턴스
_analyzer = None


def get_time_series_analyzer() -> TimeSeriesAnalyzer:
    """TimeSeriesAnalyzer 싱글톤 인스턴스 반환"""
    global _analyzer
    if _analyzer is None:
        _analyzer = TimeSeriesAnalyzer()
    return _analyzer
