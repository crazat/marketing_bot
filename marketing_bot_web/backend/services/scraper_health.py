"""
스크래퍼 헬스 모니터
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V3-2] 14개 스크래퍼 실행 상태 자동 감시

기능:
- 각 스크래퍼 실행 시 메트릭 자동 수집 (수집 건수, 에러율, 실행 시간)
- z-score 기반 이상 감지 (2σ=WARNING, 3σ=CRITICAL)
- 데이터 신선도 모니터링 (마지막 성공 스캔 시점 추적)
- 텔레그램 장애 알림 자동 발송
"""

import sqlite3
import math
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BROKEN = "broken"
    STALE = "stale"
    UNKNOWN = "unknown"


@dataclass
class ScraperRunMetric:
    """스크래퍼 1회 실행 메트릭"""
    scraper_name: str
    records_collected: int
    error_count: int = 0
    duration_seconds: float = 0
    new_records: int = 0
    duplicate_records: int = 0


class ScraperHealthMonitor:
    """스크래퍼 건강 상태 모니터"""

    # 스크래퍼 → 타겟 테이블 매핑 (각 스크래퍼가 어떤 테이블에 쓰는지)
    SCRAPER_TABLE_MAP = {
        "place_sniper": "rank_history",
        "pathfinder": "keyword_insights",
        "community_api": "community_mentions",
        "kin_leads": "community_mentions",
        "ad_keywords": "naver_ad_keyword_data",
        "keyword_trends": "keyword_trend_daily",
        "competitor_blogs": "competitor_blog_activity",
        "change_detector": "competitor_changes",
        "healthcare_news": "healthcare_news",
        "web_visibility": "web_visibility",
        "demographics": "search_demographics",
        "blog_rank": "blog_rank_history",
        "shop_trends": "shop_trend_monitoring",
        "intelligence": "intelligence_reports",
        "viral_hunter": "viral_targets",
        "instagram": "instagram_reels_analysis",
        "tiktok": "tiktok_videos",
    }

    # 신선도 기준 (시간): 이 시간 내에 데이터가 있어야 건강
    FRESHNESS_THRESHOLDS = {
        "place_sniper": 26,       # 매일 09:00 실행, 26시간 여유
        "pathfinder": 26,
        "community_api": 26,
        "kin_leads": 26,
        "ad_keywords": 26,
        "keyword_trends": 26,
        "competitor_blogs": 26,
        "healthcare_news": 26,
        "viral_hunter": 26,
        "intelligence": 26,
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._ensure_metrics_table()

    def _ensure_metrics_table(self):
        """메트릭 저장 테이블 생성"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scraper_run_metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    scraper_name TEXT NOT NULL,
                    records_collected INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    new_records INTEGER DEFAULT 0,
                    duplicate_records INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'completed',
                    run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scraper_metrics_name_date
                ON scraper_run_metrics(scraper_name, run_at)
            """)
            conn.commit()
        finally:
            conn.close()

    def record_run(self, metric: ScraperRunMetric, status: str = "completed"):
        """스크래퍼 실행 결과 기록"""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("""
                INSERT INTO scraper_run_metrics
                (scraper_name, records_collected, error_count, duration_seconds,
                 new_records, duplicate_records, status)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                metric.scraper_name, metric.records_collected, metric.error_count,
                metric.duration_seconds, metric.new_records, metric.duplicate_records,
                status,
            ))
            conn.commit()
        finally:
            conn.close()

    def check_health(self, scraper_name: str = None) -> Dict[str, Any]:
        """
        스크래퍼 건강 상태 종합 점검

        Args:
            scraper_name: 특정 스크래퍼만 (None이면 전체)

        Returns:
            {scrapers: [{name, status, last_run, avg_records, anomaly}], overall}
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        results = []

        scrapers = [scraper_name] if scraper_name else list(self.SCRAPER_TABLE_MAP.keys())

        for name in scrapers:
            result = self._check_single(cursor, name)
            results.append(result)

        conn.close()

        # 전체 상태 판정
        statuses = [r["status"] for r in results]
        if "broken" in statuses:
            overall = HealthStatus.BROKEN
        elif "stale" in statuses or "degraded" in statuses:
            overall = HealthStatus.DEGRADED
        elif all(s == "unknown" for s in statuses):
            overall = HealthStatus.UNKNOWN
        else:
            overall = HealthStatus.HEALTHY

        broken = [r["name"] for r in results if r["status"] == "broken"]
        stale = [r["name"] for r in results if r["status"] == "stale"]

        return {
            "overall": overall.value,
            "scrapers": results,
            "broken_count": len(broken),
            "stale_count": len(stale),
            "broken_scrapers": broken,
            "stale_scrapers": stale,
            "checked_at": datetime.now().isoformat(),
        }

    def _check_single(self, cursor, name: str) -> Dict[str, Any]:
        """단일 스크래퍼 건강 점검"""
        result = {
            "name": name,
            "status": HealthStatus.UNKNOWN.value,
            "last_run": None,
            "records_last": 0,
            "avg_records_14d": 0,
            "z_score": 0,
            "anomaly": None,
        }

        # 최근 실행 이력 (14일)
        cursor.execute("""
            SELECT records_collected, error_count, duration_seconds, run_at
            FROM scraper_run_metrics
            WHERE scraper_name = ?
              AND run_at >= datetime('now', '-14 days')
            ORDER BY run_at DESC
        """, (name,))

        runs = cursor.fetchall()

        if not runs:
            # 메트릭 테이블에 없으면 타겟 테이블에서 직접 확인
            table = self.SCRAPER_TABLE_MAP.get(name)
            if table:
                result.update(self._check_from_target_table(cursor, name, table))
            return result

        # 마지막 실행
        last = runs[0]
        result["last_run"] = last["run_at"]
        result["records_last"] = last["records_collected"]

        # 14일 평균 및 표준편차
        counts = [r["records_collected"] for r in runs]
        if len(counts) >= 3:
            mean = sum(counts) / len(counts)
            variance = sum((x - mean) ** 2 for x in counts) / len(counts)
            std = math.sqrt(variance) if variance > 0 else 0.001

            result["avg_records_14d"] = round(mean, 1)

            # 마지막 실행의 z-score
            z = (last["records_collected"] - mean) / std if std > 0 else 0
            result["z_score"] = round(z, 2)

            # 이상 감지
            if last["records_collected"] == 0 and mean > 5:
                result["status"] = HealthStatus.BROKEN.value
                result["anomaly"] = f"수집 0건 (평균 {mean:.0f}건)"
            elif z < -3:
                result["status"] = HealthStatus.BROKEN.value
                result["anomaly"] = f"z-score {z:.1f} (3σ 이하)"
            elif z < -2:
                result["status"] = HealthStatus.DEGRADED.value
                result["anomaly"] = f"z-score {z:.1f} (2σ 이하)"
            else:
                result["status"] = HealthStatus.HEALTHY.value
        else:
            result["status"] = HealthStatus.HEALTHY.value

        # 신선도 체크
        freshness_hours = self.FRESHNESS_THRESHOLDS.get(name, 48)
        if last["run_at"]:
            try:
                last_dt = datetime.fromisoformat(last["run_at"].replace("Z", "+00:00"))
                hours_ago = (datetime.now() - last_dt).total_seconds() / 3600
                if hours_ago > freshness_hours:
                    result["status"] = HealthStatus.STALE.value
                    result["anomaly"] = f"{hours_ago:.0f}시간 전 마지막 실행 (기준: {freshness_hours}시간)"
            except Exception:
                pass

        return result

    def _check_from_target_table(self, cursor, name: str, table: str) -> Dict[str, Any]:
        """타겟 테이블에서 직접 신선도 확인 (메트릭이 없을 때)"""
        try:
            # 테이블 존재 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not cursor.fetchone():
                return {"status": HealthStatus.UNKNOWN.value}

            # created_at 또는 scraped_at 컬럼으로 최근 데이터 확인
            for date_col in ["created_at", "scraped_at", "scanned_at", "run_at", "collected_at", "generated_at"]:
                try:
                    cursor.execute(f"""
                        SELECT MAX({date_col}) as last_date, COUNT(*) as total
                        FROM {table}
                        WHERE {date_col} >= datetime('now', '-48 hours')
                    """)
                    row = cursor.fetchone()
                    if row and row["last_date"]:
                        return {
                            "status": HealthStatus.HEALTHY.value if row["total"] > 0 else HealthStatus.STALE.value,
                            "last_run": row["last_date"],
                            "records_last": row["total"],
                        }
                except Exception:
                    continue

        except Exception:
            pass

        return {"status": HealthStatus.UNKNOWN.value}

    def get_dashboard_summary(self) -> Dict[str, Any]:
        """대시보드용 요약 (모든 스크래퍼 상태 한눈에)"""
        health = self.check_health()

        summary = {
            "overall": health["overall"],
            "total": len(health["scrapers"]),
            "healthy": sum(1 for s in health["scrapers"] if s["status"] == "healthy"),
            "degraded": sum(1 for s in health["scrapers"] if s["status"] == "degraded"),
            "broken": health["broken_count"],
            "stale": health["stale_count"],
            "unknown": sum(1 for s in health["scrapers"] if s["status"] == "unknown"),
            "issues": [
                {"name": s["name"], "status": s["status"], "detail": s.get("anomaly", "")}
                for s in health["scrapers"]
                if s["status"] in ("broken", "stale", "degraded")
            ],
        }

        return summary
