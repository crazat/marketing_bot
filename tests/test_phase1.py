
import unittest
import sys
import os
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.scraper_google import GoogleRanker
from scrapers.scraper_competitor import CompetitorScout

class TestPhase1Fixes(unittest.TestCase):
    
    @patch('scrapers.scraper_google.SafeSeleniumDriver')
    def test_google_ranker_uses_safe_driver(self, MockDriver):
        """Verify GoogleRanker uses SafeSeleniumDriver context manager."""
        mock_driver_instance = MagicMock()
        MockDriver.return_value.__enter__.return_value = mock_driver_instance
        
        # Setup logic to return minimal HTML to avoid parsing errors
        mock_driver_instance.page_source = "<html><body><div class='g'>Test Result</div></body></html>"
        
        ranker = GoogleRanker(headless=True)
        # Verify logger is present (patched in file)
        import scrapers.scraper_google
        self.assertTrue(hasattr(scrapers.scraper_google, 'logger'))
        
        ranker.run()
        
        MockDriver.assert_called_once()
        MockDriver.return_value.__enter__.assert_called()
    
    def test_competitor_scout_has_logger(self):
        """Verify CompetitorScout module has logger initialized."""
        import scrapers.scraper_competitor
        self.assertTrue(hasattr(scrapers.scraper_competitor, 'logger'))
        self.assertIsInstance(scrapers.scraper_competitor.logger, logging.Logger)

import logging
if __name__ == '__main__':
    logging.basicConfig(level=logging.ERROR)
    unittest.main()
