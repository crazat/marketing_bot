"""
API Usage Tracker for Marketing Bot
=====================================
Tracks API calls to external services (Gemini, Naver, etc.)
Provides usage statistics and cost estimation.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime, timedelta
from contextlib import closing
from functools import wraps

# Add project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import ConfigManager

logger = logging.getLogger("APITracker")


class APIUsageTracker:
    """
    Tracks API usage for cost monitoring and quota management.
    
    Features:
    - Per-API call counting
    - Daily/monthly aggregation
    - Cost estimation
    - Rate limit warnings
    """
    
    # Cost estimates per API call (KRW)
    COST_PER_CALL = {
        'gemini': 0.5,           # Gemini Flash: very cheap
        'gemini_pro': 5.0,       # Gemini Pro: more expensive
        'naver_search': 0,       # Free tier
        'naver_ad': 0,           # Free tier
        'telegram': 0,           # Free
    }
    
    # Daily limits (for warnings)
    DAILY_LIMITS = {
        'gemini': 1500,          # RPD limit
        'naver_search': 25000,   # Daily quota
        'naver_ad': 100000,      # High limit
    }
    
    def __init__(self):
        self.config = ConfigManager()
        self.db_path = self.config.db_path
        self._ensure_table()
    
    def _ensure_table(self):
        """Create api_usage table if not exists"""
        with closing(sqlite3.connect(self.db_path)) as conn:
            cursor = conn.cursor()
            cursor.execute("""
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
            """)
            
            # Index for fast date-based queries
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_api_usage_date 
                ON api_usage(api_name, created_at)
            """)
            conn.commit()
    
    def log_call(self, api_name, endpoint=None, tokens=0, success=True, error=None):
        """
        Log an API call.
        
        Args:
            api_name: 'gemini', 'naver_search', 'naver_ad', 'telegram'
            endpoint: Optional endpoint details
            tokens: Token count (for LLM APIs)
            success: Whether call succeeded
            error: Error message if failed
        """
        cost = self.COST_PER_CALL.get(api_name, 0)
        if tokens > 0 and api_name == 'gemini':
            # Estimate cost based on tokens (input + output)
            cost = tokens * 0.0001  # Rough estimate
        
        try:
            with closing(sqlite3.connect(self.db_path, timeout=5)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO api_usage (api_name, endpoint, tokens_used, cost_estimate, success, error_message, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    api_name,
                    endpoint,
                    tokens,
                    cost,
                    1 if success else 0,
                    error,
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                ))
                conn.commit()
            
            # Check daily limit warning
            self._check_limits(api_name)
            
        except Exception as e:
            logger.warning(f"Failed to log API call: {e}")
    
    def _check_limits(self, api_name):
        """Warn if approaching daily limit"""
        limit = self.DAILY_LIMITS.get(api_name)
        if not limit:
            return
        
        today_count = self.get_daily_count(api_name)
        
        if today_count >= limit * 0.9:
            logger.warning(f"⚠️ API Limit Warning: {api_name} at {today_count}/{limit} ({today_count/limit*100:.0f}%)")
    
    def get_daily_count(self, api_name, date=None):
        """Get call count for a specific day"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT COUNT(*) FROM api_usage
                    WHERE api_name = ? AND created_at LIKE ?
                """, (api_name, f"{date}%"))
                return cursor.fetchone()[0]
        except Exception:
            return 0
    
    def get_daily_stats(self, date=None):
        """Get all API stats for a day"""
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")
        
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        api_name,
                        COUNT(*) as calls,
                        SUM(tokens_used) as total_tokens,
                        SUM(cost_estimate) as total_cost,
                        SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as failures
                    FROM api_usage 
                    WHERE created_at LIKE ?
                    GROUP BY api_name
                """, (f"{date}%",))
                
                results = {}
                for row in cursor.fetchall():
                    results[row[0]] = {
                        'calls': row[1],
                        'tokens': row[2] or 0,
                        'cost': round(row[3] or 0, 2),
                        'failures': row[4]
                    }
                return results
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return {}
    
    def get_monthly_summary(self, year=None, month=None):
        """Get monthly usage summary"""
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month
        
        date_prefix = f"{year}-{month:02d}"
        
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT 
                        api_name,
                        COUNT(*) as calls,
                        SUM(tokens_used) as total_tokens,
                        SUM(cost_estimate) as total_cost
                    FROM api_usage 
                    WHERE created_at LIKE ?
                    GROUP BY api_name
                """, (f"{date_prefix}%",))
                
                results = {}
                total_cost = 0
                for row in cursor.fetchall():
                    cost = round(row[3] or 0, 2)
                    results[row[0]] = {
                        'calls': row[1],
                        'tokens': row[2] or 0,
                        'cost': cost
                    }
                    total_cost += cost
                
                return {
                    'month': date_prefix,
                    'apis': results,
                    'total_cost': round(total_cost, 2)
                }
        except Exception as e:
            logger.error(f"Failed to get monthly summary: {e}")
            return {}
    
    def get_usage_report(self):
        """Generate a human-readable usage report"""
        today = self.get_daily_stats()
        monthly = self.get_monthly_summary()
        
        report = []
        report.append("=" * 40)
        report.append("API Usage Report")
        report.append("=" * 40)
        
        report.append(f"\n📅 Today ({datetime.now().strftime('%Y-%m-%d')}):")
        if today:
            for api, stats in today.items():
                limit = self.DAILY_LIMITS.get(api, '-')
                report.append(f"  {api}: {stats['calls']} calls" + 
                             (f" ({stats['calls']}/{limit})" if limit != '-' else "") +
                             (f" [⚠️ {stats['failures']} errors]" if stats['failures'] else ""))
        else:
            report.append("  No API calls recorded today")
        
        report.append(f"\n📊 This Month ({monthly.get('month', 'N/A')}):")
        if monthly.get('apis'):
            for api, stats in monthly['apis'].items():
                report.append(f"  {api}: {stats['calls']} calls, ~₩{stats['cost']}")
            report.append(f"\n💰 Estimated Total Cost: ₩{monthly.get('total_cost', 0)}")
        else:
            report.append("  No data available")
        
        report.append("=" * 40)
        
        return "\n".join(report)


# Decorator for automatic tracking
def track_api_call(api_name, endpoint=None):
    """
    Decorator to automatically track API calls.
    
    Usage:
        @track_api_call('gemini', 'generate_content')
        def call_gemini(prompt):
            ...
    """
    tracker = APIUsageTracker()
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                result = func(*args, **kwargs)
                tracker.log_call(api_name, endpoint, success=True)
                return result
            except Exception as e:
                tracker.log_call(api_name, endpoint, success=False, error=str(e)[:100])
                raise
        return wrapper
    return decorator


# Singleton instance for easy import
_tracker_instance = None

def get_tracker():
    """Get or create singleton tracker instance"""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = APIUsageTracker()
    return _tracker_instance


if __name__ == "__main__":
    # Test and show report
    tracker = APIUsageTracker()
    
    # Log some test calls
    tracker.log_call('gemini', 'test_endpoint', tokens=100)
    tracker.log_call('naver_search', 'blog')
    tracker.log_call('gemini', 'batch_analysis', tokens=500)
    
    print(tracker.get_usage_report())
