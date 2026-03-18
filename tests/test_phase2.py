
import unittest
import sys
import os
import logging
import json
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from logging_config import setup_logging, DatabaseLogHandler
from utils import ConfigManager

class TestPhase2Fixes(unittest.TestCase):
    
    def setUp(self):
        # Reset logger handlers
        logging.getLogger().handlers = []
        
    def test_setup_logging_adds_db_handler(self):
        """Verify setup_logging adds DatabaseLogHandler."""
        root = setup_logging(console_output=False, file_output=False)
        
        has_db_handler = False
        for h in root.handlers:
            if isinstance(h, DatabaseLogHandler):
                has_db_handler = True
                break
                
        self.assertTrue(has_db_handler, "DatabaseLogHandler should be attached to root logger")
        
    def test_config_validate_checks_targets(self):
        """Verify ConfigManager.validate checks for targets.json."""
        config = ConfigManager()
        
        # Mock load_targets to return empty
        with patch.object(config, 'load_targets', return_value={}):
            result = config.validate()
            
            # Should have warning about empty targets
            warnings = result['warnings']
            found = any("targets.json is empty" in w for w in warnings)
            self.assertTrue(found, "Should warn about empty targets.json")

    def test_config_validate_checks_keys(self):
         """Verify ConfigManager.validate checks for missing targets key."""
         config = ConfigManager()
         
         # Mock load_targets to return just some junk
         with patch.object(config, 'load_targets', return_value={"junk": 1}):
             result = config.validate()
             
             # Should have warning about missing keys
             warnings = result['warnings']
             found = any("missing 'targets' or 'competitors'" in w for w in warnings)
             self.assertTrue(found, "Should warn about missing target keys")

if __name__ == '__main__':
    unittest.main()
