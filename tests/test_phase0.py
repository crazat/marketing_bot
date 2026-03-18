
import unittest
import os
import json
import time
from unittest.mock import MagicMock, patch
import sys

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from task_manager import TaskManager
from prophet import TheProphet

class TestPhase0Fixes(unittest.TestCase):
    
    def test_task_manager_atomic_write(self):
        """Verify that TaskManager writes atomically using a tmp file."""
        tm = TaskManager()
        tm.db_path = "test_tasks.json" # Use a test file
        
        # Add a dummy task
        tm.tasks = {"test_task": {"status": "pending"}}
        tm._save_tasks()
        
        # Check if file exists
        self.assertTrue(os.path.exists("test_tasks.json"))
        
        # Clean up
        if os.path.exists("test_tasks.json"):
            os.remove("test_tasks.json")

    def test_task_manager_corruption_recovery(self):
        """Verify that TaskManager backs up corrupted files."""
        tm = TaskManager()
        tm.db_path = "test_corrupt.json"
        
        # Create a corrupted file
        with open("test_corrupt.json", "w") as f:
            f.write("{corrupted_json")
            
        # Try to load (should fallback and backup)
        data = tm._load_tasks()
        self.assertEqual(data, {}) # Should return empty dict on reset
        
        # Check for backup file
        backup_files = [f for f in os.listdir(".") if f.startswith("test_corrupt.json") and f.endswith(".bak")]
        self.assertTrue(len(backup_files) > 0, "Backup file should be created")
        
        # Clean up
        if os.path.exists("test_corrupt.json"):
            os.remove("test_corrupt.json")
        for f in backup_files:
            os.remove(f)

    @patch('retry_helper.SafeSeleniumDriver')
    def test_prophet_uses_safe_driver(self, MockDriver):
        """Verify that Prophet uses SafeSeleniumDriver context manager."""
        # Setup mock behavior
        mock_driver_instance = MagicMock()
        MockDriver.return_value.__enter__.return_value = mock_driver_instance
        
        prophet = TheProphet()
        # Mock finding elements to prevent actual interaction errors
        mock_driver_instance.find_element.return_value.text = "현재 온도 10.5°"
        
        result = prophet._fetch_real_weather()
        
        # Assert SafeSeleniumDriver was called
        MockDriver.assert_called_once()
        # Assert it was used as a context manager
        MockDriver.return_value.__enter__.assert_called()
        MockDriver.return_value.__exit__.assert_called()

if __name__ == '__main__':
    unittest.main()
