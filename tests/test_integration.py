"""
Integration Tests for Marketing Bot
Tests core functionality and integration between modules.
"""

import unittest
import os
import sys
import sqlite3
from unittest.mock import patch, MagicMock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestConfigManager(unittest.TestCase):
    """Tests for ConfigManager with .env and secrets.json support."""
    
    def test_env_priority_over_secrets(self):
        """Environment variables should take priority over secrets.json."""
        from utils import ConfigManager
        
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'env_test_key'}):
            config = ConfigManager()
            result = config.get_api_key('GEMINI_API_KEY')
            self.assertEqual(result, 'env_test_key')
    
    def test_fallback_to_secrets_json(self):
        """Should fall back to secrets.json when env var not set."""
        from utils import ConfigManager
        
        # Clear the env var if set
        original = os.environ.pop('TEST_KEY_12345', None)
        try:
            config = ConfigManager()
            with patch.object(config, 'load_secrets', return_value={'TEST_KEY_12345': 'json_value'}):
                result = config.get_api_key('TEST_KEY_12345')
                self.assertEqual(result, 'json_value')
        finally:
            if original:
                os.environ['TEST_KEY_12345'] = original


class TestDatabaseIntegration(unittest.TestCase):
    """Tests for database operations."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test database."""
        cls.test_db = os.path.join(os.path.dirname(__file__), 'test_integration.db')
        
    @classmethod
    def tearDownClass(cls):
        """Clean up test database."""
        try:
            if os.path.exists(cls.test_db):
                os.remove(cls.test_db)
        except PermissionError:
            pass  # File in use, will be cleaned up later
    
    def test_database_connection_context_manager(self):
        """Test that context manager properly closes connections."""
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY)")
            conn.commit()
        
        # Connection should be automatically closed
        # Verify by reopening
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test'")
            result = cursor.fetchone()
            self.assertIsNotNone(result)
    
    def test_system_logs_schema(self):
        """Test that system_logs uses 'module' column correctly."""
        with sqlite3.connect(self.test_db) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    level TEXT,
                    module TEXT,
                    message TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Test insert with 'module' column
            cursor.execute(
                "INSERT INTO system_logs (module, message, level) VALUES (?, ?, ?)",
                ("test_module", "test message", "INFO")
            )
            conn.commit()
            
            # Verify
            cursor.execute("SELECT module, message FROM system_logs WHERE module='test_module'")
            result = cursor.fetchone()
            self.assertEqual(result[0], "test_module")
            self.assertEqual(result[1], "test message")


class TestRetryLogic(unittest.TestCase):
    """Tests for retry mechanisms."""
    
    def test_retry_decorator_import(self):
        """Test that retry_helper module is importable."""
        try:
            from retry_helper import retry_with_backoff, with_fallback
            self.assertTrue(callable(retry_with_backoff))
            self.assertTrue(callable(with_fallback))
        except ImportError:
            self.fail("Could not import retry_helper module")
    
    def test_retry_with_backoff_success(self):
        """Test retry decorator on successful function."""
        from retry_helper import retry_with_backoff
        
        call_count = 0
        
        @retry_with_backoff(max_retries=3)
        def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = success_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 1)  # Should succeed first try
    
    def test_retry_with_backoff_failure_then_success(self):
        """Test retry decorator with initial failures."""
        from retry_helper import retry_with_backoff
        
        call_count = 0
        
        @retry_with_backoff(max_retries=3, initial_delay=0.1)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient error")
            return "success"
        
        result = flaky_func()
        self.assertEqual(result, "success")
        self.assertEqual(call_count, 3)  # Should take 3 attempts


class TestSeleniumDriverLifecycle(unittest.TestCase):
    """Tests for Selenium driver cleanup patterns."""
    
    def test_driver_none_initialization(self):
        """Verify driver=None pattern is used in key files."""
        files_to_check = [
            'prophet.py',
            'carrot_farmer.py',
            'pathfinder.py',
            'ambassador.py'
        ]
        
        parent_dir = os.path.dirname(os.path.dirname(__file__))
        
        for filename in files_to_check:
            filepath = os.path.join(parent_dir, filename)
            if os.path.exists(filepath):
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # Check for proper pattern
                    has_driver_none = 'driver = None' in content
                    has_finally = 'finally:' in content
                    
                    self.assertTrue(
                        has_driver_none or has_finally,
                        f"{filename} should have driver=None pattern or finally block"
                    )


class TestCircuitBreaker(unittest.TestCase):
    """Integration tests for Circuit Breaker pattern."""
    
    def test_circuit_opens_after_threshold(self):
        """Test that circuit opens after reaching failure threshold."""
        from retry_helper import CircuitBreaker
        
        breaker = CircuitBreaker(name="test", threshold=3, reset_after=1)
        
        # Circuit should be closed initially
        self.assertFalse(breaker.is_open())
        self.assertEqual(breaker.state, "CLOSED")
        
        # Record failures
        breaker.record_failure()
        breaker.record_failure()
        self.assertFalse(breaker.is_open())  # Still below threshold
        
        breaker.record_failure()
        self.assertEqual(breaker.state, "OPEN")
        self.assertTrue(breaker.is_open())
    
    def test_circuit_recovers_after_success(self):
        """Test that circuit closes after successful recovery."""
        from retry_helper import CircuitBreaker
        import time
        
        breaker = CircuitBreaker(name="test_recovery", threshold=2, reset_after=0.1)
        
        # Open the circuit
        breaker.record_failure()
        breaker.record_failure()
        self.assertTrue(breaker.is_open())
        
        # Wait for reset
        time.sleep(0.15)
        self.assertFalse(breaker.is_open())
        self.assertEqual(breaker.state, "HALF_OPEN")
        
        # Successful call should close circuit
        breaker.record_success()
        self.assertEqual(breaker.state, "CLOSED")


class TestSafeSubprocess(unittest.TestCase):
    """Integration tests for safe_subprocess function."""
    
    def test_successful_command(self):
        """Test safe_subprocess with successful command."""
        from retry_helper import safe_subprocess
        
        result = safe_subprocess(["python", "-c", "print('hello')"], timeout=10)
        
        self.assertTrue(result["success"])
        self.assertIn("hello", result["stdout"])
        self.assertEqual(result["returncode"], 0)
    
    def test_failed_command(self):
        """Test safe_subprocess with failing command."""
        from retry_helper import safe_subprocess
        
        result = safe_subprocess(["python", "-c", "import sys; sys.exit(1)"], timeout=10)
        
        self.assertFalse(result["success"])
        self.assertEqual(result["returncode"], 1)
    
    def test_timeout_handling(self):
        """Test safe_subprocess timeout handling."""
        from retry_helper import safe_subprocess
        
        # This should timeout quickly
        result = safe_subprocess(
            ["python", "-c", "import time; time.sleep(10)"], 
            timeout=1
        )
        
        self.assertFalse(result["success"])
        self.assertIn("Timeout", result["stderr"])
        self.assertEqual(result["returncode"], -1)


class TestSafeSeleniumDriverExtended(unittest.TestCase):
    """Integration tests for extended SafeSeleniumDriver."""
    
    def test_mobile_emulation_option(self):
        """Test that SafeSeleniumDriver supports mobile emulation."""
        from retry_helper import SafeSeleniumDriver
        import inspect
        
        # Check that mobile parameter exists
        sig = inspect.signature(SafeSeleniumDriver.__init__)
        params = list(sig.parameters.keys())
        
        self.assertIn("mobile", params, "SafeSeleniumDriver should have 'mobile' parameter")
        self.assertIn("extra_options", params, "SafeSeleniumDriver should have 'extra_options' parameter")


if __name__ == '__main__':
    unittest.main(verbosity=2)
