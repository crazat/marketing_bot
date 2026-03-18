"""
System Validator for Marketing Bot.
Validates all required configurations and dependencies on startup.
"""
import os
import sys
import json
import logging
import sqlite3

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

logger = logging.getLogger("SystemValidator")

class SystemValidator:
    """
    Validates system configuration, API keys, and dependencies.
    Run this at startup to catch issues early.
    """
    
    def __init__(self, root_dir=None):
        self.root_dir = root_dir or os.path.dirname(os.path.abspath(__file__))
        self.errors = []
        self.warnings = []
        
    def validate_all(self, exit_on_error=False):
        """
        Run all validation checks.
        
        Args:
            exit_on_error: If True, sys.exit(1) on critical errors
            
        Returns:
            dict: {"success": bool, "errors": [...], "warnings": [...]}
        """
        print("🔍 Marketing Bot System Validation Starting...")
        
        # Run all checks
        self._check_directories()
        self._check_config_files()
        self._check_api_keys()
        self._check_database()
        self._check_dependencies()
        self._check_connectivity()
        
        # Report results
        self._report()

        if self.errors and exit_on_error:
            print("\n❌ Critical errors found. Exiting.")
            sys.exit(1)
            
        return {
            "success": len(self.errors) == 0,
            "errors": self.errors,
            "warnings": self.warnings
        }
    
    def _check_directories(self):
        """Verify required directories exist, create if missing."""
        required_dirs = [
            'config',
            'db',
            'scrapers',
            'reports_competitor',
            'reports_cafe',
            'reports_blog',
            'reports_strategy',
            'data',
            'data/images_scraped'
        ]
        
        for dir_name in required_dirs:
            dir_path = os.path.join(self.root_dir, dir_name)
            if not os.path.exists(dir_path):
                try:
                    os.makedirs(dir_path, exist_ok=True)
                    self.warnings.append(f"Created missing directory: {dir_name}")
                except Exception as e:
                    self.errors.append(f"Failed to create directory {dir_name}: {e}")
        
        print("   ✓ Directories checked")
    
    def _check_config_files(self):
        """Verify required config files exist and are valid JSON."""
        required_files = {
            'config/secrets.json': ['google_api_key'],  # Required keys
            'config/targets.json': [],
            'config/prompts.json': []
        }
        
        for file_path, required_keys in required_files.items():
            full_path = os.path.join(self.root_dir, file_path)
            
            if not os.path.exists(full_path):
                if 'secrets' in file_path:
                    self.errors.append(f"Missing critical config: {file_path}")
                else:
                    self.warnings.append(f"Missing config file: {file_path}")
                continue
            
            # Validate JSON
            try:
                with open(full_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                # Check required keys
                for key in required_keys:
                    # Case-insensitive key check
                    found = any(k.lower() == key.lower() for k in data.keys())
                    if not found:
                        self.warnings.append(f"{file_path}: Missing recommended key '{key}'")
                        
            except json.JSONDecodeError as e:
                self.errors.append(f"Invalid JSON in {file_path}: {e}")
            except Exception as e:
                self.errors.append(f"Error reading {file_path}: {e}")
        
        print("   ✓ Config files checked")
    
    def _check_api_keys(self):
        """Validate API keys are present and have valid format."""
        secrets_path = os.path.join(self.root_dir, 'config', 'secrets.json')
        
        if not os.path.exists(secrets_path):
            return  # Already reported in config check
            
        try:
            with open(secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
            
            # Check Google/Gemini API Key
            api_key = (secrets.get('google_api_key') or 
                      secrets.get('GOOGLE_API_KEY') or 
                      secrets.get('GEMINI_API_KEY'))
            
            if not api_key:
                self.errors.append("No Google/Gemini API key found in secrets.json")
            elif len(api_key) < 20:
                self.warnings.append("API key seems too short - verify it's correct")
            elif api_key.startswith('YOUR_') or api_key == 'placeholder':
                self.errors.append("API key is a placeholder - please set a real key")
            
            # Check Telegram Token (optional)
            telegram_token = secrets.get('telegram_token') or secrets.get('TELEGRAM_TOKEN')
            if not telegram_token:
                self.warnings.append("No Telegram token - alerts will run in mock mode")
                
            # Check Naver API (optional)
            naver_id = secrets.get('NAVER_CLIENT_ID') or secrets.get('naver_client_id')
            if not naver_id:
                self.warnings.append("No Naver API credentials - some scrapers may not work")
                
        except Exception as e:
            self.errors.append(f"Error validating API keys: {e}")
        
        print("   ✓ API keys checked")
    
    def _check_database(self):
        """Verify database connection and schema."""
        db_path = os.path.join(self.root_dir, 'db', 'marketing_data.db')
        
        try:
            conn = sqlite3.connect(db_path, timeout=5)
            cursor = conn.cursor()
            
            # Check required tables exist
            required_tables = [
                'mentions',
                'rank_history',
                'competitor_reviews',
                'chat_sessions',
                'chat_messages',
                'insights'
            ]
            
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            existing_tables = [row[0] for row in cursor.fetchall()]
            
            for table in required_tables:
                if table not in existing_tables:
                    self.warnings.append(f"Missing table: {table} (will be created on first use)")
            
            conn.close()
            
        except sqlite3.Error as e:
            self.errors.append(f"Database connection failed: {e}")
        except Exception as e:
            self.errors.append(f"Database check error: {e}")
        
        print("   ✓ Database checked")
    
    def _check_dependencies(self):
        """Check that required Python packages are installed."""
        required_packages = [
            ('streamlit', 'streamlit'),
            ('pandas', 'pandas'),
            ('selenium', 'selenium'),
            ('webdriver_manager', 'webdriver-manager'),
            ('google.generativeai', 'google-generativeai'),
            ('bs4', 'beautifulsoup4'),
            ('requests', 'requests'),
            ('schedule', 'schedule'),
            ('PIL', 'Pillow')
        ]
        
        missing = []
        for import_name, pip_name in required_packages:
            try:
                __import__(import_name.split('.')[0])
            except ImportError:
                missing.append(pip_name)
        
        if missing:
            self.warnings.append(f"Missing packages: {', '.join(missing)}. Run: pip install {' '.join(missing)}")
        
        print("   ✓ Dependencies checked")

    def _check_connectivity(self):
        """Test actual network connectivity to external services."""
        import requests
        from naver_api_client import NaverApiClient
        
        # 1. Basic Internet Check
        try:
            requests.get("https://www.google.com", timeout=3)
        except Exception:
            self.errors.append("Checking Internet: ❌ Failed (Google.com unreachable)")
            return

        # 2. Naver API Check
        client = NaverApiClient()
        if client.client_id:
            res = client.search_news("테스트", count=1)
            if "error" in res:
                self.warnings.append(f"Naver API Test: ❌ Failed ({res['error']})")
            else:
                pass # Success
        
        print("   ✓ Network & API Connectivity checked")
    
    def _report(self):
        """Print validation results."""
        print("\n" + "="*50)
        
        if self.errors:
            print(f"❌ {len(self.errors)} ERRORS:")
            for err in self.errors:
                print(f"   • {err}")
        
        if self.warnings:
            print(f"⚠️  {len(self.warnings)} WARNINGS:")
            for warn in self.warnings:
                print(f"   • {warn}")
        
        if not self.errors and not self.warnings:
            print("✅ All checks passed!")
        elif not self.errors:
            print("\n✅ System ready (with warnings)")
        else:
            print("\n❌ System has critical issues")
        
        print("="*50)


def validate_on_startup():
    """Quick validation for use in other modules."""
    validator = SystemValidator()
    return validator.validate_all(exit_on_error=False)


if __name__ == "__main__":
    validator = SystemValidator()
    result = validator.validate_all(exit_on_error=True)
    
    if result["success"]:
        print("\n🚀 System ready to run!")
