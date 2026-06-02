"""API usage tracker for marketing automation services.

LLM usage is now tracked as Codex CLI calls.  The tracker still supports
non-LLM services such as Naver and Telegram for operational reporting.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
from contextlib import closing
from datetime import datetime
from functools import wraps

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import ConfigManager

logger = logging.getLogger("APITracker")


class APIUsageTracker:
    COST_PER_CALL = {
        "codex_cli": 1.0,
        "codex_cli_premium": 8.0,
        "naver_search": 0,
        "naver_ad": 0,
        "telegram": 0,
    }

    DAILY_LIMITS = {
        "codex_cli": 10000,
        "codex_cli_premium": 2000,
        "naver_search": 25000,
        "naver_ad": 100000,
    }

    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path
        self._ensure_table()

    def _ensure_table(self) -> None:
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS api_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_name TEXT NOT NULL,
                    endpoint TEXT,
                    tokens_used INTEGER DEFAULT 0,
                    cost_estimate REAL DEFAULT 0,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_api_usage_date
                ON api_usage(api_name, created_at)
                """
            )
            conn.commit()

    def log_call(self, api_name, endpoint=None, tokens=0, success=True, error=None):
        cost = self.COST_PER_CALL.get(api_name, 0)
        if tokens > 0 and api_name.startswith("codex_cli"):
            cost = max(cost, tokens * 0.0002)

        try:
            with closing(sqlite3.connect(self.db_path, timeout=5)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO api_usage
                      (api_name, endpoint, tokens_used, cost_estimate, success, error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        api_name,
                        endpoint,
                        tokens,
                        cost,
                        1 if success else 0,
                        error,
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    ),
                )
                conn.commit()
            self._check_limits(api_name)
        except Exception as exc:
            logger.warning("Failed to log API call: %s", exc)

    def _check_limits(self, api_name) -> None:
        limit = self.DAILY_LIMITS.get(api_name)
        if not limit:
            return
        today_count = self.get_daily_count(api_name)
        if today_count >= limit * 0.9:
            logger.warning(
                "API limit warning: %s at %s/%s (%.0f%%)",
                api_name,
                today_count,
                limit,
                today_count / limit * 100,
            )

    def get_daily_count(self, api_name, date=None):
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*) FROM api_usage
                    WHERE api_name = ? AND created_at LIKE ?
                    """,
                    (api_name, f"{date}%"),
                )
                return cursor.fetchone()[0]
        except Exception:
            return 0

    def get_daily_stats(self, date=None):
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT
                        api_name,
                        COUNT(*) as calls,
                        SUM(tokens_used) as total_tokens,
                        SUM(cost_estimate) as total_cost,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                    FROM api_usage
                    WHERE created_at LIKE ?
                    GROUP BY api_name
                    """,
                    (f"{date}%",),
                )
                return {
                    row[0]: {
                        "calls": row[1],
                        "tokens": row[2] or 0,
                        "cost": round(row[3] or 0, 2),
                        "failures": row[4],
                    }
                    for row in cursor.fetchall()
                }
        except Exception as exc:
            logger.error("Failed to get daily stats: %s", exc)
            return {}

    def get_monthly_summary(self, year=None, month=None):
        year = year or datetime.now().year
        month = month or datetime.now().month
        date_prefix = f"{year}-{month:02d}"
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT api_name, COUNT(*) as calls, SUM(tokens_used), SUM(cost_estimate)
                    FROM api_usage
                    WHERE created_at LIKE ?
                    GROUP BY api_name
                    """,
                    (f"{date_prefix}%",),
                )
                apis = {}
                total_cost = 0
                for row in cursor.fetchall():
                    cost = round(row[3] or 0, 2)
                    apis[row[0]] = {"calls": row[1], "tokens": row[2] or 0, "cost": cost}
                    total_cost += cost
                return {"month": date_prefix, "apis": apis, "total_cost": round(total_cost, 2)}
        except Exception as exc:
            logger.error("Failed to get monthly summary: %s", exc)
            return {}

    def get_usage_report(self):
        today = self.get_daily_stats()
        monthly = self.get_monthly_summary()
        report = ["=" * 40, "API Usage Report", "=" * 40]
        report.append(f"\nToday ({datetime.now().strftime('%Y-%m-%d')}):")
        if today:
            for api, stats in today.items():
                limit = self.DAILY_LIMITS.get(api, "-")
                suffix = f" ({stats['calls']}/{limit})" if limit != "-" else ""
                error_suffix = f" [{stats['failures']} errors]" if stats["failures"] else ""
                report.append(f"  {api}: {stats['calls']} calls{suffix}{error_suffix}")
        else:
            report.append("  No API calls recorded today")
        report.append(f"\nThis Month ({monthly.get('month', 'N/A')}):")
        if monthly.get("apis"):
            for api, stats in monthly["apis"].items():
                report.append(f"  {api}: {stats['calls']} calls, ~{stats['cost']}")
            report.append(f"\nEstimated Total Cost: {monthly.get('total_cost', 0)}")
        else:
            report.append("  No data available")
        report.append("=" * 40)
        return "\n".join(report)


def track_api_call(api_name, endpoint=None):
    tracker = APIUsageTracker()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                tracker.log_call(api_name, endpoint, success=True)
                return result
            except Exception as exc:
                tracker.log_call(api_name, endpoint, success=False, error=str(exc)[:100])
                raise

        return wrapper

    return decorator


_tracker_instance = None


def get_tracker():
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = APIUsageTracker()
    return _tracker_instance


if __name__ == "__main__":
    tracker = APIUsageTracker()
    tracker.log_call("codex_cli", "test_endpoint", tokens=100)
    tracker.log_call("naver_search", "blog")
    tracker.log_call("codex_cli_premium", "batch_analysis", tokens=500)
    print(tracker.get_usage_report())
