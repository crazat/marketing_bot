"""
Startup Validator for Marketing Bot
====================================
Performs comprehensive health checks at system startup.
Validates API keys, database connectivity, scraper status, and configuration files.
"""

import os
import sys
import sqlite3
import logging
from datetime import datetime

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from utils import ConfigManager, logger

class StartupValidator:
    """
    System Health Validator
    Runs at dashboard/scheduler startup to report system status.
    """
    
    def __init__(self):
        self.config = ConfigManager()
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'UNKNOWN',
            'checks': []
        }
    
    def run_all_checks(self):
        """Run all validation checks and return summary"""
        logger.info("🔍 Running Startup Validation...")
        
        checks = [
            self._check_api_keys(),
            self._check_database(),
            self._check_config_files(),
            self._check_scraper_status(),
        ]
        
        self.results['checks'] = checks
        
        # Calculate overall status
        failed = [c for c in checks if c['status'] == 'FAIL']
        warnings = [c for c in checks if c['status'] == 'WARN']
        
        if failed:
            self.results['overall_status'] = 'CRITICAL'
        elif warnings:
            self.results['overall_status'] = 'WARNING'
        else:
            self.results['overall_status'] = 'HEALTHY'
        
        self._log_results()
        return self.results
    
    def _check_api_keys(self):
        """Validate required API keys are present"""
        check = {
            'name': 'API Keys',
            'status': 'PASS',
            'details': []
        }
        
        required_keys = [
            ('GEMINI_API_KEY', 'Gemini AI'),
            ('NAVER_CLIENT_ID', 'Naver Search API'),
            ('NAVER_CLIENT_SECRET', 'Naver Search API'),
        ]
        
        optional_keys = [
            ('TELEGRAM_BOT_TOKEN', 'Telegram Alerts'),
            ('NAVER_AD_ACCESS_KEY', 'Naver Ad API'),
            ('NAVER_AD_SECRET_KEY', 'Naver Ad API'),
            ('NAVER_AD_CUSTOMER_ID', 'Naver Ad API'),
        ]
        
        missing_required = []
        missing_optional = []
        
        for key, service in required_keys:
            value = self.config.get_api_key(key)
            if not value:
                missing_required.append(f"{key} ({service})")
        
        for key, service in optional_keys:
            value = self.config.get_api_key(key)
            if not value:
                missing_optional.append(f"{key} ({service})")
        
        if missing_required:
            check['status'] = 'FAIL'
            check['details'].append(f"❌ Missing required: {', '.join(missing_required)}")
        
        if missing_optional:
            check['details'].append(f"⚠️ Missing optional: {', '.join(missing_optional)}")
            if check['status'] == 'PASS':
                check['status'] = 'WARN'
        
        if check['status'] == 'PASS':
            check['details'].append("✅ All required API keys configured")
        
        return check
    
    def _check_database(self):
        """Validate database connectivity and tables"""
        check = {
            'name': 'Database',
            'status': 'PASS',
            'details': []
        }
        
        try:
            db_path = self.config.db_path
            if not os.path.exists(db_path):
                check['status'] = 'WARN'
                check['details'].append(f"⚠️ Database not found, will be created: {db_path}")
                return check
            
            with sqlite3.connect(db_path, timeout=5) as conn:
                cursor = conn.cursor()
                
                # Check required tables
                required_tables = ['system_logs', 'mentions', 'keyword_insights']
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                existing_tables = [row[0] for row in cursor.fetchall()]
                
                missing_tables = [t for t in required_tables if t not in existing_tables]
                
                if missing_tables:
                    check['status'] = 'WARN'
                    check['details'].append(f"⚠️ Missing tables (will be created): {missing_tables}")
                else:
                    check['details'].append(f"✅ Database healthy ({len(existing_tables)} tables)")
                    
        except Exception as e:
            check['status'] = 'FAIL'
            check['details'].append(f"❌ Database error: {str(e)[:50]}")
        
        return check
    
    def _check_config_files(self):
        """Validate configuration files exist"""
        check = {
            'name': 'Config Files',
            'status': 'PASS',
            'details': []
        }
        
        config_files = [
            ('config/campaigns.json', 'Campaign configuration'),
            ('config/keywords_master.json', 'Master keywords'),
            ('config/competitors.json', 'Competitor list'),
        ]
        
        missing = []
        for filename, description in config_files:
            path = os.path.join(self.config.root_dir, filename)
            if not os.path.exists(path):
                missing.append(description)
        
        if missing:
            check['status'] = 'WARN'
            check['details'].append(f"⚠️ Missing configs: {', '.join(missing)}")
        else:
            check['details'].append("✅ All config files present")
        
        return check
    
    def _check_scraper_status(self):
        """Report scraper operational status"""
        check = {
            'name': 'Scraper Status',
            'status': 'WARN',  # Always WARN since some scrapers are disabled
            'details': []
        }
        
        scrapers = {
            'Naver Cafe Spy': 'ACTIVE',
            'Naver Place': 'ACTIVE',
            'YouTube Sentinel': 'ACTIVE',
            'Instagram Monitor': 'LIMITED (Google bypass, 3-7 day delay)',
            'TikTok Monitor': 'DISABLED (requires login)',
            'Ambassador': 'LIMITED (no follower data)',
        }
        
        active = [k for k, v in scrapers.items() if v == 'ACTIVE']
        limited = [k for k, v in scrapers.items() if 'LIMITED' in v]
        disabled = [k for k, v in scrapers.items() if 'DISABLED' in v]
        
        check['details'].append(f"✅ Active: {', '.join(active)}")
        if limited:
            check['details'].append(f"⚠️ Limited: {', '.join(limited)}")
        if disabled:
            check['details'].append(f"❌ Disabled: {', '.join(disabled)}")
        
        return check
    
    def _log_results(self):
        """Log validation results to system_logs"""
        status_emoji = {
            'HEALTHY': '✅',
            'WARNING': '⚠️',
            'CRITICAL': '❌'
        }.get(self.results['overall_status'], '❓')
        
        logger.info(f"{status_emoji} Startup Validation: {self.results['overall_status']}")
        
        for check in self.results['checks']:
            status = check['status']
            name = check['name']
            logger.info(f"   [{status}] {name}")
            for detail in check['details']:
                logger.info(f"       {detail}")
        
        # Also save to DB
        try:
            from db.database import DatabaseManager
            db = DatabaseManager()
            db.log_system_event(
                module="StartupValidator",
                level="INFO" if self.results['overall_status'] == 'HEALTHY' else "WARNING",
                message=f"System validation: {self.results['overall_status']}"
            )
        except Exception:
            pass
    
    def get_summary_text(self):
        """Get human-readable summary for dashboard display"""
        status = self.results['overall_status']
        checks = self.results['checks']
        
        lines = [f"🔍 시스템 상태: {status}", ""]
        
        for check in checks:
            status_icon = {'PASS': '✅', 'WARN': '⚠️', 'FAIL': '❌'}.get(check['status'], '❓')
            lines.append(f"{status_icon} {check['name']}")
            for detail in check['details'][:2]:  # Limit details
                lines.append(f"   {detail}")
        
        return "\n".join(lines)


def validate_on_startup():
    """Convenience function to run validation and return results"""
    validator = StartupValidator()
    return validator.run_all_checks()


if __name__ == "__main__":
    # Test validation
    validator = StartupValidator()
    results = validator.run_all_checks()
    
    print("\n" + "="*50)
    print(validator.get_summary_text())
    print("="*50)
