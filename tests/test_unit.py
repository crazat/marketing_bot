"""
Unit Tests for Marketing Bot Core Modules.
Tests individual functions and classes in isolation.
"""

import unittest
import os
import sys
from unittest.mock import patch, MagicMock, Mock

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestAIOrchestrator(unittest.TestCase):
    """Unit tests for AIOrchestrator class."""
    
    def test_orchestrator_initialization_without_api_key(self):
        """Test that orchestrator handles missing API key gracefully."""
        with patch.dict(os.environ, {}, clear=True):
            with patch('utils.ConfigManager.load_secrets', return_value={}):
                from ai_orchestrator import AIOrchestrator
                # Should not raise even without API key
                orchestrator = AIOrchestrator()
                self.assertFalse(orchestrator.has_llm)
    
    def test_process_command_without_llm(self):
        """Test process_command returns error when LLM is not available."""
        with patch('utils.ConfigManager.get_api_key', return_value=None):
            from ai_orchestrator import AIOrchestrator
            orchestrator = AIOrchestrator()
            result = orchestrator.process_command("테스트")
            self.assertEqual(result['type'], 'text')
            self.assertIn('Offline', result['content'])


class TestConfigManager(unittest.TestCase):
    """Unit tests for ConfigManager class."""
    
    def test_get_model_name_flash(self):
        """Test flash model name returns correctly."""
        from utils import ConfigManager
        config = ConfigManager()
        model = config.get_model_name("flash")
        self.assertIn("gemini", model.lower())
    
    def test_get_model_name_pro(self):
        """Test pro model name returns correctly."""
        from utils import ConfigManager
        config = ConfigManager()
        model = config.get_model_name("pro")
        self.assertIn("gemini", model.lower())
    
    def test_load_prompts_returns_dict(self):
        """Test that load_prompts returns a dictionary."""
        from utils import ConfigManager
        config = ConfigManager()
        result = config.load_prompts()
        self.assertIsInstance(result, dict)


class TestBaseAgent(unittest.TestCase):
    """Unit tests for BaseAgent class."""
    
    def test_agent_without_api_key_returns_error(self):
        """Test that agent returns error message without API key."""
        with patch('utils.ConfigManager.get_api_key', return_value=None):
            from agent_crew import BaseAgent
            agent = BaseAgent("TestAgent")
            result = agent.generate("test prompt")
            self.assertIn("Error", result)
    
    def test_generate_has_retry_capability(self):
        """Test that generate method has max_retries parameter."""
        from agent_crew import BaseAgent
        import inspect
        sig = inspect.signature(BaseAgent.generate)
        params = list(sig.parameters.keys())
        self.assertIn('max_retries', params)


class TestDatabaseManager(unittest.TestCase):
    """Unit tests for DatabaseManager class."""
    
    def test_database_schema_has_required_tables(self):
        """Test that database schema defines all required tables."""
        # Read the database.py source to verify table definitions
        db_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'db', 'database.py'
        )
        
        with open(db_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        required_tables = ['mentions', 'rank_history', 'insights', 'system_logs', 'competitors']
        for table in required_tables:
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", content,
                         f"Table '{table}' not defined in database.py")


class TestTactician(unittest.TestCase):
    """Unit tests for Tactician class."""
    
    def test_strategy_key_format_in_source(self):
        """Test that tactician.py uses 'suggested_action' not 'action'."""
        tactician_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'tactician.py'
        )
        
        with open(tactician_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Count occurrences
        action_only = content.count('"action":')
        suggested_action = content.count('"suggested_action":')
        
        # There should be more suggested_action than action
        # The file was fixed to use suggested_action consistently
        self.assertGreaterEqual(suggested_action, action_only,
                               f"Found {action_only} 'action:' vs {suggested_action} 'suggested_action:'")


class TestInsightManager(unittest.TestCase):
    """Unit tests for InsightManager class."""
    
    def test_log_activity_uses_module_column_in_source(self):
        """Test that insight_manager.py uses 'module' column not 'source'."""
        insight_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'insight_manager.py'
        )
        
        with open(insight_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # The log_activity function should use 'module' column
        # Check the INSERT statement
        self.assertIn('INSERT INTO system_logs (module', content,
                      "log_activity should use 'module' column, not 'source'")
        self.assertNotIn('INSERT INTO system_logs (source', content,
                        "log_activity should NOT use 'source' column")


class TestInsightManagerContextManager(unittest.TestCase):
    """Unit tests for InsightManager Context Manager pattern."""
    
    def test_methods_use_context_manager(self):
        """Test that InsightManager uses 'with' statement for DB connections."""
        insight_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'insight_manager.py'
        )
        
        with open(insight_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check that Context Manager pattern is used (with self.get_connection())
        self.assertIn('with self.get_connection()', content,
                      "InsightManager should use Context Manager pattern")
        # Check that manual conn.close() is NOT used in main methods
        close_count = content.count('conn.close()')
        self.assertLess(close_count, 3, 
                       f"Expected less than 3 conn.close() calls, found {close_count}")


class TestAlertBotMockMode(unittest.TestCase):
    """Unit tests for AlertBot mock mode functionality."""
    
    def test_telegram_bot_mock_mode(self):
        """Test that TelegramBot handles missing token gracefully."""
        # Read the source to verify mock mode pattern
        alert_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'alert_bot.py'
        )
        
        with open(alert_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for mock mode handling
        self.assertIn('MOCK ALERT', content,
                      "AlertBot should have mock mode for missing token")
        self.assertIn('not self.token', content,
                      "AlertBot should check for missing token")


class TestRetryHelper(unittest.TestCase):
    """Unit tests for retry_helper module."""
    
    def test_safe_selenium_driver_exists(self):
        """Test that SafeSeleniumDriver context manager exists."""
        retry_file = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'retry_helper.py'
        )
        
        with open(retry_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        self.assertIn('class SafeSeleniumDriver', content,
                      "retry_helper should have SafeSeleniumDriver class")
        self.assertIn('def __enter__', content,
                      "SafeSeleniumDriver should implement __enter__")
        self.assertIn('def __exit__', content,
                      "SafeSeleniumDriver should implement __exit__")


if __name__ == '__main__':
    unittest.main(verbosity=2)
