"""
Unit Tests for Marketing Bot Core Functions.
Run with: python -m pytest test_core.py -v
"""
import unittest
import os
import sys
import sqlite3
import tempfile
import json

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


class TestDatabaseManager(unittest.TestCase):
    """Tests for db/database.py"""
    
    def setUp(self):
        """Create a temporary database for testing."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        
        from db.database import DatabaseManager
        self.db = DatabaseManager(db_path=self.temp_db.name)
    
    def tearDown(self):
        """Clean up temporary database."""
        try:
            self.db.conn.close()
            os.unlink(self.temp_db.name)
        except:
            pass
    
    def test_tables_created(self):
        """Verify all required tables are created."""
        cursor = self.db.cursor
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        
        required = ['mentions', 'rank_history', 'competitor_reviews', 
                   'chat_sessions', 'chat_messages', 'insights']
        for table in required:
            self.assertIn(table, tables, f"Missing table: {table}")
    
    def test_insert_mention(self):
        """Test mention insertion."""
        data = {
            'target_name': 'TestTarget',
            'keyword': 'test keyword',
            'source': 'test',
            'title': 'Test Title',
            'content': 'Test content',
            'url': 'https://test.com/unique123',
            'date_posted': '2024-01-01'
        }
        
        result = self.db.insert_mention(data)
        self.assertTrue(result)
        
        # Verify data was inserted
        self.db.cursor.execute("SELECT title FROM mentions WHERE url = ?", (data['url'],))
        row = self.db.cursor.fetchone()
        self.assertEqual(row[0], 'Test Title')
    
    def test_duplicate_url_rejected(self):
        """Test that duplicate URLs are rejected."""
        data = {
            'target_name': 'Test',
            'keyword': 'test',
            'source': 'test',
            'title': 'Test',
            'content': 'Test',
            'url': 'https://test.com/same',
            'date_posted': '2024-01-01'
        }
        
        result1 = self.db.insert_mention(data)
        result2 = self.db.insert_mention(data)
        
        self.assertTrue(result1)
        self.assertFalse(result2)
    
    def test_insert_rank(self):
        """Test rank history insertion."""
        result = self.db.insert_rank("청주 다이어트", 5, "Naver View")
        self.assertTrue(result)


class TestRetryHelper(unittest.TestCase):
    """Tests for retry_helper.py"""
    
    def test_retry_success_first_try(self):
        """Test that successful functions don't retry."""
        from retry_helper import retry_with_backoff
        
        call_count = [0]
        
        @retry_with_backoff(max_retries=3, initial_delay=0.01)
        def always_succeeds():
            call_count[0] += 1
            return "success"
        
        result = always_succeeds()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 1)
    
    def test_retry_eventual_success(self):
        """Test retry on initial failures then success."""
        from retry_helper import retry_with_backoff
        
        call_count = [0]
        
        @retry_with_backoff(max_retries=3, initial_delay=0.01, exceptions=(ValueError,))
        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Simulated failure")
            return "success"
        
        result = fails_twice()
        self.assertEqual(result, "success")
        self.assertEqual(call_count[0], 3)
    
    def test_retry_exhausted(self):
        """Test that max retries raises the exception."""
        from retry_helper import retry_with_backoff
        
        @retry_with_backoff(max_retries=2, initial_delay=0.01, exceptions=(RuntimeError,))
        def always_fails():
            raise RuntimeError("Always fails")
        
        with self.assertRaises(RuntimeError):
            always_fails()
    
    def test_fallback_value(self):
        """Test fallback decorator with value."""
        from retry_helper import with_fallback
        
        @with_fallback(fallback_value=[], exceptions=(Exception,))
        def fails_with_fallback():
            raise Exception("Failed")
        
        result = fails_with_fallback()
        self.assertEqual(result, [])


class TestSystemValidator(unittest.TestCase):
    """Tests for system_validator.py"""
    
    def test_validator_runs(self):
        """Test that validator runs without crashing."""
        from system_validator import SystemValidator
        
        validator = SystemValidator()
        result = validator.validate_all(exit_on_error=False)
        
        self.assertIn('success', result)
        self.assertIn('errors', result)
        self.assertIn('warnings', result)


class TestAnalysisEngine(unittest.TestCase):
    """Tests for analysis_engine.py"""
    
    def test_analyze_gap(self):
        """Test gap analysis between content summaries."""
        from analysis_engine import AnalysisEngine
        
        engine = AnalysisEngine()
        
        our_data = {
            'text_len': 500,
            'img_count': 2,
            'keywords': ['diet']
        }
        
        competitor_data = {
            'text_len': 2000,
            'img_count': 10,
            'keywords': ['diet', 'event', 'discount']
        }
        
        result = engine.analyze_gap(our_data, competitor_data)
        
        self.assertIn('score_gap', result)
        self.assertIn('primary_reason', result)
        self.assertIn('detailed_advice', result)
        
        # Should detect text and image gaps
        advice = result['detailed_advice']
        self.assertIn('이미지', advice)
        self.assertIn('분량', advice)


class TestConfigManager(unittest.TestCase):
    """Tests for utils.py ConfigManager"""
    
    def test_config_manager_init(self):
        """Test ConfigManager initialization."""
        from utils import ConfigManager
        
        config = ConfigManager()
        
        # Should have root_dir set
        self.assertIsNotNone(config.root_dir)
        self.assertTrue(os.path.exists(config.root_dir))


if __name__ == "__main__":
    # Run tests
    unittest.main(verbosity=2)
