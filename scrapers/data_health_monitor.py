#!/usr/bin/env python3
"""
Data Health Monitor - Pipeline Health & Data Quality Dashboard
===============================================================

Monitors the health of all data collection pipelines:
- Data freshness: last record timestamps, records per time window
- Data quality: null ratios, duplicate detection
- API key validity: lightweight test calls
- Status per collector: HEALTHY / WARNING / CRITICAL / SETUP_NEEDED

Usage:
    python scrapers/data_health_monitor.py

API Endpoint Suggestion:
    GET /api/data-intelligence/health
    Returns the full health report as JSON.
    Add to: marketing_bot_web/backend/routers/data_intelligence.py
"""

import sys
import os
import time
import json
import logging
import traceback
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple

# Path setup
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

import requests

from db.database import DatabaseManager
from utils import ConfigManager

logger = logging.getLogger(__name__)


# ============================================================================
# Table Definitions - tables to monitor with their metadata
# ============================================================================

# Format: (table_name, date_column, key_columns_for_quality, collector_name, freshness_hours)
# freshness_hours: how many hours before WARNING (CRITICAL = 3x this)
TABLE_REGISTRY = [
    # Original tables
    ("rank_history", "checked_at", ["keyword", "rank"], "Place Rank Scanner", 24),
    ("keyword_insights", "created_at", ["keyword", "grade"], "Pathfinder", 168),
    ("competitor_reviews", "created_at", ["competitor_name"], "Competitor Analyzer", 168),
    ("viral_targets", "created_at", ["title", "url"], "Viral Hunter", 168),
    ("mentions", "created_at", ["platform", "url"], "Social Monitor", 168),

    # Phase 9 tables
    ("smartplace_stats", "stat_date", ["stat_date", "impressions"], "SmartPlace Collector", 168),
    ("review_intelligence", "collected_at", ["competitor_name", "total_reviews"], "Review Intelligence", 168),
    ("blog_rank_history", "tracked_at", ["keyword", "rank_position"], "Blog Rank Tracker", 72),
    ("hira_clinics", "created_at", ["name"], "HIRA API Client", 720),
    ("medical_platform_reviews", "created_at", ["platform", "clinic_name"], "Medical Review Monitor", 168),
    ("competitor_changes", "detected_at", ["competitor_name", "change_type"], "Competitor Change Detector", 168),
    ("kakao_rank_history", "tracked_at", ["keyword", "rank"], "KakaoMap Tracker", 72),
    ("call_tracking", "call_date", ["call_date"], "SmartPlace (Call Data)", 168),
    ("commercial_district_data", "created_at", ["district_code"], "Commercial Data Collector", 720),
    ("geo_grid_rankings", "created_at", ["keyword", "latitude"], "Geo Grid Tracker", 168),
    ("naver_ad_keyword_data", "created_at", ["keyword", "total_search_volume"], "Naver Ad Keywords", 168),
    ("community_mentions", "created_at", ["platform", "url"], "Community Monitor", 168),

    # New tables (may not exist yet)
    ("keyword_trend_daily", "created_at", ["keyword"], "Keyword Trend Daily", 48),
    ("competitor_blog_activity", "created_at", ["competitor_name"], "Competitor Blog Activity", 168),
    ("serp_features", "scanned_at", ["keyword", "has_place_pack"], "SERP Feature Monitor", 168),
    ("intelligence_reports", "created_at", ["report_type", "report_date"], "Intelligence Synthesizer", 168),
]


# Status constants
STATUS_HEALTHY = "HEALTHY"
STATUS_WARNING = "WARNING"
STATUS_CRITICAL = "CRITICAL"
STATUS_SETUP_NEEDED = "SETUP_NEEDED"
STATUS_NOT_FOUND = "NOT_FOUND"

# Status display icons
STATUS_ICONS = {
    STATUS_HEALTHY: "[OK]",
    STATUS_WARNING: "[!!]",
    STATUS_CRITICAL: "[XX]",
    STATUS_SETUP_NEEDED: "[??]",
    STATUS_NOT_FOUND: "[--]",
}


class DataHealthMonitor:
    """Monitors the health of all data collection pipelines."""

    def __init__(self):
        self.db = DatabaseManager()
        self.config = ConfigManager()
        self.report_time = datetime.now()
        self.health_results: List[Dict[str, Any]] = []
        self.api_health: List[Dict[str, Any]] = []
        self.quality_issues: List[Dict[str, Any]] = []

    def _table_exists(self, conn: sqlite3.Connection, table_name: str) -> bool:
        """Check if a table exists in the database."""
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,)
        )
        return cursor.fetchone() is not None

    def _get_table_stats(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        date_column: str,
    ) -> Dict[str, Any]:
        """Get record counts and timestamps for a table."""
        stats = {
            "total_records": 0,
            "last_record": None,
            "records_24h": 0,
            "records_7d": 0,
            "hours_since_last": None,
        }

        cursor = conn.cursor()

        try:
            # Total count
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            stats["total_records"] = cursor.fetchone()[0]

            if stats["total_records"] == 0:
                return stats

            # Last record timestamp
            cursor.execute(f"SELECT MAX([{date_column}]) FROM [{table_name}]")
            last_date_str = cursor.fetchone()[0]
            if last_date_str:
                stats["last_record"] = last_date_str
                # Parse date
                for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]:
                    try:
                        last_date = datetime.strptime(str(last_date_str), fmt)
                        stats["hours_since_last"] = round(
                            (self.report_time - last_date).total_seconds() / 3600, 1
                        )
                        break
                    except ValueError:
                        continue

            # Records in last 24h
            cursor.execute(
                f"SELECT COUNT(*) FROM [{table_name}] "
                f"WHERE [{date_column}] >= datetime('now', '-1 day')"
            )
            stats["records_24h"] = cursor.fetchone()[0]

            # Records in last 7d
            cursor.execute(
                f"SELECT COUNT(*) FROM [{table_name}] "
                f"WHERE [{date_column}] >= datetime('now', '-7 days')"
            )
            stats["records_7d"] = cursor.fetchone()[0]

        except Exception as e:
            logger.debug(f"Error getting stats for {table_name}: {e}")

        return stats

    def _check_data_quality(
        self,
        conn: sqlite3.Connection,
        table_name: str,
        key_columns: List[str],
    ) -> Dict[str, Any]:
        """Check data quality: null ratios and duplicates."""
        quality = {
            "null_ratios": {},
            "duplicate_count": 0,
            "issues": [],
        }

        cursor = conn.cursor()

        try:
            # Get total count
            cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
            total = cursor.fetchone()[0]
            if total == 0:
                return quality

            # Check null ratios for key columns
            for col in key_columns:
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) FROM [{table_name}] "
                        f"WHERE [{col}] IS NULL OR TRIM([{col}]) = ''"
                    )
                    null_count = cursor.fetchone()[0]
                    null_ratio = round(null_count / total, 3) if total > 0 else 0
                    quality["null_ratios"][col] = {
                        "null_count": null_count,
                        "ratio": null_ratio,
                    }
                    if null_ratio > 0.1:
                        quality["issues"].append(
                            f"High null ratio for '{col}': {null_ratio:.1%} ({null_count}/{total})"
                        )
                except Exception:
                    pass  # Column might not exist

            # Check duplicates (based on key columns)
            if len(key_columns) >= 2:
                cols_str = ", ".join(f"[{c}]" for c in key_columns[:2])
                try:
                    cursor.execute(
                        f"SELECT COUNT(*) - COUNT(DISTINCT {cols_str}) "
                        f"FROM [{table_name}]"
                    )
                    # Fallback: explicit duplicate check
                    cursor.execute(
                        f"SELECT COUNT(*) FROM ("
                        f"  SELECT {cols_str}, COUNT(*) as cnt "
                        f"  FROM [{table_name}] "
                        f"  GROUP BY {cols_str} "
                        f"  HAVING cnt > 1"
                        f")"
                    )
                    dup_groups = cursor.fetchone()[0]
                    quality["duplicate_count"] = dup_groups
                    if dup_groups > 0:
                        quality["issues"].append(
                            f"{dup_groups} duplicate groups on ({', '.join(key_columns[:2])})"
                        )
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Quality check error for {table_name}: {e}")

        return quality

    def check_all_tables(self):
        """Check freshness and quality for all registered tables."""
        print(f"\n  Checking data freshness and quality...\n")

        try:
            with self.db.get_new_connection() as conn:
                for table_name, date_col, key_cols, collector_name, freshness_hours in TABLE_REGISTRY:
                    # Check if table exists
                    if not self._table_exists(conn, table_name):
                        self.health_results.append({
                            "table": table_name,
                            "collector": collector_name,
                            "status": STATUS_NOT_FOUND,
                            "stats": {"total_records": 0},
                            "quality": {},
                            "freshness_hours": freshness_hours,
                        })
                        continue

                    # Get stats
                    stats = self._get_table_stats(conn, table_name, date_col)

                    # Get quality
                    quality = {}
                    if stats["total_records"] > 0:
                        quality = self._check_data_quality(conn, table_name, key_cols)

                    # Determine status
                    if stats["total_records"] == 0:
                        status = STATUS_SETUP_NEEDED
                    elif stats["hours_since_last"] is not None:
                        if stats["hours_since_last"] > freshness_hours * 3:
                            status = STATUS_CRITICAL
                        elif stats["hours_since_last"] > freshness_hours:
                            status = STATUS_WARNING
                        else:
                            status = STATUS_HEALTHY
                    else:
                        status = STATUS_WARNING

                    # Downgrade for quality issues
                    if quality.get("issues") and status == STATUS_HEALTHY:
                        # Only downgrade to WARNING, not CRITICAL, for quality issues alone
                        high_null = any(
                            v.get("ratio", 0) > 0.3
                            for v in quality.get("null_ratios", {}).values()
                        )
                        if high_null:
                            status = STATUS_WARNING

                    self.health_results.append({
                        "table": table_name,
                        "collector": collector_name,
                        "status": status,
                        "stats": stats,
                        "quality": quality,
                        "freshness_hours": freshness_hours,
                    })

                    # Track quality issues globally
                    for issue in quality.get("issues", []):
                        self.quality_issues.append({
                            "table": table_name,
                            "issue": issue,
                        })

        except Exception as e:
            logger.error(f"Table check error: {e}")
            logger.debug(traceback.format_exc())

    def check_api_keys(self):
        """Make lightweight test calls to verify API key validity."""
        print(f"  Checking API key validity...\n")

        # 1. Naver Search API
        self._check_naver_search_api()

        # 2. Kakao REST API
        self._check_kakao_api()

        # 3. Telegram Bot API
        self._check_telegram_api()

        # 4. Instagram Graph API
        self._check_instagram_api()

        # 5. Naver Ads API
        self._check_naver_ads_api()

    def _check_naver_search_api(self):
        """Test Naver Search API with a lightweight call."""
        result = {"api": "Naver Search API", "status": "UNKNOWN", "detail": ""}

        try:
            keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")
            if not keys:
                client_id = self.config.get_api_key("NAVER_CLIENT_ID")
                client_secret = self.config.get_api_key("NAVER_CLIENT_SECRET")
                if client_id and client_secret:
                    keys = [{"id": client_id, "secret": client_secret}]

            if not keys:
                result["status"] = "NOT_CONFIGURED"
                result["detail"] = "No API keys found"
                self.api_health.append(result)
                return

            # Test with first key
            key = keys[0]
            headers = {
                "X-Naver-Client-Id": key["id"],
                "X-Naver-Client-Secret": key["secret"],
            }
            response = requests.get(
                "https://openapi.naver.com/v1/search/local.json",
                params={"query": "테스트", "display": 1},
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                result["status"] = "VALID"
                result["detail"] = f"{len(keys)} key(s) available"
            elif response.status_code == 401:
                result["status"] = "INVALID"
                result["detail"] = "Authentication failed"
            elif response.status_code == 429:
                result["status"] = "RATE_LIMITED"
                result["detail"] = "Rate limit exceeded (key works but throttled)"
            else:
                result["status"] = "ERROR"
                result["detail"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["status"] = "TIMEOUT"
            result["detail"] = "Request timed out"
        except requests.exceptions.ConnectionError:
            result["status"] = "CONN_ERROR"
            result["detail"] = "Connection failed"
        except Exception as e:
            result["status"] = "ERROR"
            result["detail"] = str(e)

        self.api_health.append(result)

    def _check_kakao_api(self):
        """Test Kakao REST API."""
        result = {"api": "Kakao REST API", "status": "UNKNOWN", "detail": ""}

        try:
            api_key = self.config.get_api_key("KAKAO_REST_API_KEY")
            if not api_key:
                result["status"] = "NOT_CONFIGURED"
                result["detail"] = "KAKAO_REST_API_KEY not found"
                self.api_health.append(result)
                return

            headers = {"Authorization": f"KakaoAK {api_key}"}
            response = requests.get(
                "https://dapi.kakao.com/v2/local/search/keyword.json",
                params={"query": "테스트", "size": 1},
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                result["status"] = "VALID"
                result["detail"] = "Key is valid"
            elif response.status_code == 401:
                result["status"] = "INVALID"
                result["detail"] = "Authentication failed"
            else:
                result["status"] = "ERROR"
                result["detail"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["status"] = "TIMEOUT"
            result["detail"] = "Request timed out"
        except Exception as e:
            result["status"] = "ERROR"
            result["detail"] = str(e)

        self.api_health.append(result)

    def _check_telegram_api(self):
        """Test Telegram Bot API."""
        result = {"api": "Telegram Bot API", "status": "UNKNOWN", "detail": ""}

        try:
            token = self.config.get_api_key("TELEGRAM_BOT_TOKEN")
            chat_id = self.config.get_api_key("TELEGRAM_CHAT_ID")

            if not token:
                result["status"] = "NOT_CONFIGURED"
                result["detail"] = "TELEGRAM_BOT_TOKEN not found"
                self.api_health.append(result)
                return

            response = requests.get(
                f"https://api.telegram.org/bot{token}/getMe",
                timeout=10,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("ok"):
                    bot_name = data.get("result", {}).get("username", "unknown")
                    result["status"] = "VALID"
                    result["detail"] = f"Bot: @{bot_name}" + (", chat_id set" if chat_id else ", NO chat_id")
                else:
                    result["status"] = "INVALID"
                    result["detail"] = "Token invalid"
            else:
                result["status"] = "INVALID"
                result["detail"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["status"] = "TIMEOUT"
            result["detail"] = "Request timed out"
        except Exception as e:
            result["status"] = "ERROR"
            result["detail"] = str(e)

        self.api_health.append(result)

    def _check_instagram_api(self):
        """Test Instagram Graph API."""
        result = {"api": "Instagram Graph API", "status": "UNKNOWN", "detail": ""}

        try:
            if not self.config.is_instagram_configured():
                result["status"] = "NOT_CONFIGURED"
                result["detail"] = "Instagram credentials incomplete"
                self.api_health.append(result)
                return

            creds = self.config.get_instagram_credentials()
            access_token = creds.get("access_token")

            # Check token expiry
            expiry_str = creds.get("token_expiry")
            if expiry_str:
                try:
                    expiry = datetime.fromisoformat(expiry_str)
                    days_left = (expiry - datetime.now()).days
                    if days_left <= 0:
                        result["status"] = "EXPIRED"
                        result["detail"] = f"Token expired {abs(days_left)} days ago"
                        self.api_health.append(result)
                        return
                    elif days_left <= 7:
                        result["detail"] = f"Token expires in {days_left} days!"
                except Exception:
                    pass

            response = requests.get(
                "https://graph.facebook.com/v18.0/me",
                params={"access_token": access_token, "fields": "id,name"},
                timeout=10,
            )

            if response.status_code == 200:
                result["status"] = "VALID"
                if not result["detail"]:
                    result["detail"] = "Token is valid"
            elif response.status_code == 401:
                result["status"] = "EXPIRED"
                result["detail"] = "Token expired or invalid"
            else:
                result["status"] = "ERROR"
                result["detail"] = f"HTTP {response.status_code}"

        except requests.exceptions.Timeout:
            result["status"] = "TIMEOUT"
            result["detail"] = "Request timed out"
        except Exception as e:
            result["status"] = "ERROR"
            result["detail"] = str(e)

        self.api_health.append(result)

    def _check_naver_ads_api(self):
        """Test Naver Ads API key presence (no lightweight endpoint available)."""
        result = {"api": "Naver Ads API", "status": "UNKNOWN", "detail": ""}

        try:
            access_key = self.config.get_api_key("NAVER_AD_ACCESS_KEY")
            secret_key = self.config.get_api_key("NAVER_AD_SECRET_KEY")
            customer_id = self.config.get_api_key("NAVER_AD_CUSTOMER_ID")

            if access_key and secret_key and customer_id:
                result["status"] = "CONFIGURED"
                result["detail"] = "Keys present (no lightweight test endpoint)"
            else:
                missing = []
                if not access_key:
                    missing.append("ACCESS_KEY")
                if not secret_key:
                    missing.append("SECRET_KEY")
                if not customer_id:
                    missing.append("CUSTOMER_ID")
                result["status"] = "NOT_CONFIGURED"
                result["detail"] = f"Missing: {', '.join(missing)}"

        except Exception as e:
            result["status"] = "ERROR"
            result["detail"] = str(e)

        self.api_health.append(result)

    def _print_dashboard(self):
        """Print the health dashboard with color-coded status."""
        print(f"\n{'='*80}")
        print(f"  DATA HEALTH MONITOR - {self.report_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # Summary counts
        status_counts = {
            STATUS_HEALTHY: 0,
            STATUS_WARNING: 0,
            STATUS_CRITICAL: 0,
            STATUS_SETUP_NEEDED: 0,
            STATUS_NOT_FOUND: 0,
        }
        for r in self.health_results:
            status_counts[r["status"]] = status_counts.get(r["status"], 0) + 1

        print(f"\n  Summary: "
              f"{STATUS_ICONS[STATUS_HEALTHY]} {status_counts[STATUS_HEALTHY]} Healthy  "
              f"{STATUS_ICONS[STATUS_WARNING]} {status_counts[STATUS_WARNING]} Warning  "
              f"{STATUS_ICONS[STATUS_CRITICAL]} {status_counts[STATUS_CRITICAL]} Critical  "
              f"{STATUS_ICONS[STATUS_SETUP_NEEDED]} {status_counts[STATUS_SETUP_NEEDED]} Setup Needed  "
              f"{STATUS_ICONS[STATUS_NOT_FOUND]} {status_counts[STATUS_NOT_FOUND]} Not Found")

        # Table health
        print(f"\n  {'='*76}")
        print(f"  {'Collector':<30} {'Status':>10} {'Total':>8} {'24h':>6} {'7d':>6} {'Last Update':>14}")
        print(f"  {'-'*76}")

        # Sort: CRITICAL first, then WARNING, SETUP_NEEDED, NOT_FOUND, HEALTHY
        status_priority = {
            STATUS_CRITICAL: 0,
            STATUS_WARNING: 1,
            STATUS_SETUP_NEEDED: 2,
            STATUS_NOT_FOUND: 3,
            STATUS_HEALTHY: 4,
        }
        sorted_results = sorted(
            self.health_results,
            key=lambda x: (status_priority.get(x["status"], 99), x["collector"])
        )

        for r in sorted_results:
            stats = r["stats"]
            icon = STATUS_ICONS.get(r["status"], "[??]")
            total = stats.get("total_records", 0)

            if r["status"] == STATUS_NOT_FOUND:
                print(f"  {r['collector']:<30} {icon:>10} {'N/A':>8} {'N/A':>6} {'N/A':>6} {'Table missing':>14}")
                continue

            records_24h = stats.get("records_24h", 0)
            records_7d = stats.get("records_7d", 0)

            hours = stats.get("hours_since_last")
            if hours is not None:
                if hours < 1:
                    last_str = f"{int(hours*60)}m ago"
                elif hours < 24:
                    last_str = f"{hours:.0f}h ago"
                else:
                    last_str = f"{hours/24:.1f}d ago"
            else:
                last_str = "N/A" if total > 0 else "empty"

            print(f"  {r['collector']:<30} {icon:>10} {total:>8} {records_24h:>6} {records_7d:>6} {last_str:>14}")

        # API Health
        if self.api_health:
            print(f"\n  {'='*76}")
            print(f"  API KEY STATUS")
            print(f"  {'-'*76}")
            print(f"  {'API':.<40} {'Status':>15} {'Detail'}")
            print(f"  {'-'*76}")

            api_icons = {
                "VALID": "[OK]",
                "CONFIGURED": "[OK]",
                "NOT_CONFIGURED": "[--]",
                "INVALID": "[XX]",
                "EXPIRED": "[XX]",
                "RATE_LIMITED": "[!!]",
                "TIMEOUT": "[!!]",
                "CONN_ERROR": "[!!]",
                "ERROR": "[XX]",
                "UNKNOWN": "[??]",
            }

            for api in self.api_health:
                icon = api_icons.get(api["status"], "[??]")
                print(f"  {api['api']:<40} {icon:>15} {api.get('detail', '')}")

        # Quality Issues
        if self.quality_issues:
            print(f"\n  {'='*76}")
            print(f"  DATA QUALITY ISSUES ({len(self.quality_issues)})")
            print(f"  {'-'*76}")
            for issue in self.quality_issues[:15]:
                print(f"  [!] {issue['table']}: {issue['issue']}")

        print(f"\n{'='*80}")

    def get_health_json(self) -> Dict[str, Any]:
        """Return health data as JSON (for API endpoint use)."""
        return {
            "report_time": self.report_time.strftime("%Y-%m-%d %H:%M:%S"),
            "summary": {
                "healthy": sum(1 for r in self.health_results if r["status"] == STATUS_HEALTHY),
                "warning": sum(1 for r in self.health_results if r["status"] == STATUS_WARNING),
                "critical": sum(1 for r in self.health_results if r["status"] == STATUS_CRITICAL),
                "setup_needed": sum(1 for r in self.health_results if r["status"] == STATUS_SETUP_NEEDED),
                "not_found": sum(1 for r in self.health_results if r["status"] == STATUS_NOT_FOUND),
            },
            "tables": [
                {
                    "table": r["table"],
                    "collector": r["collector"],
                    "status": r["status"],
                    "total_records": r["stats"].get("total_records", 0),
                    "records_24h": r["stats"].get("records_24h", 0),
                    "records_7d": r["stats"].get("records_7d", 0),
                    "last_record": r["stats"].get("last_record"),
                    "hours_since_last": r["stats"].get("hours_since_last"),
                    "quality_issues": r.get("quality", {}).get("issues", []),
                }
                for r in self.health_results
            ],
            "api_keys": self.api_health,
            "quality_issues": self.quality_issues,
        }

    def run(self):
        """Run the full health monitoring check."""
        print(f"\n{'='*80}")
        print(f"  Data Health Monitor")
        print(f"  Started: {self.report_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")

        # Check all tables
        self.check_all_tables()

        # Check API keys
        self.check_api_keys()

        # Print dashboard
        self._print_dashboard()

        # Print suggested endpoint
        print(f"\n  Suggested API Endpoint:")
        print(f"    GET /api/data-intelligence/health")
        print(f"    Router: marketing_bot_web/backend/routers/data_intelligence.py")
        print(f"    Usage: health_monitor = DataHealthMonitor()")
        print(f"           health_monitor.check_all_tables()")
        print(f"           health_monitor.check_api_keys()")
        print(f"           return health_monitor.get_health_json()")
        print(f"\n  Completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}\n")

        return self.get_health_json()


if __name__ == "__main__":
    try:
        monitor = DataHealthMonitor()
        monitor.run()
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        logger.error(traceback.format_exc())
        sys.exit(1)
