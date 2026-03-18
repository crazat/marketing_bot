
import unittest
import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from prophet import TheProphet

class TestPhase3Fixes(unittest.TestCase):
    
    @patch('prophet.requests.post')
    @patch('prophet.ConfigManager')
    def test_fetch_datalab_trend_success(self, MockConfig, MockPost):
        """Verify _fetch_datalab_trend calculates slope correctly from API data."""
        # Setup Config
        mock_config_instance = MagicMock()
        MockConfig.return_value = mock_config_instance
        mock_config_instance.get_api_key.return_value = "dummy_key"
        
        # Setup API Response (Strictly increasing trend)
        # Data: [10, 20, 30] -> Slope should be positive
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [{
                "data": [
                    {"period": "2024-01-01", "ratio": "10"},
                    {"period": "2024-01-02", "ratio": "20"},
                    {"period": "2024-01-03", "ratio": "30"}
                ]
            }]
        }
        MockPost.return_value = mock_response
        
        prophet = TheProphet()
        # Mock weather to avoid selenium call during init or predict (if any)
        prophet._fetch_real_weather = MagicMock(return_value=None)
        
        slope = prophet._fetch_datalab_trend("test_keyword")
        
        # Verify API called
        MockPost.assert_called_once()
        self.assertIsNotNone(slope)
        self.assertTrue(slope > 0, f"Slope {slope} should be positive for increasing data")
        
    @patch('prophet.requests.post')
    @patch('prophet.ConfigManager')
    def test_fetch_datalab_trend_api_fail(self, MockConfig, MockPost):
        """Verify _fetch_datalab_trend returns None on API failure."""
        mock_config_instance = MagicMock()
        MockConfig.return_value = mock_config_instance
        mock_config_instance.get_api_key.return_value = "dummy_key"
        
        # Setup API Exception
        MockPost.side_effect = Exception("API Error")
        
        prophet = TheProphet()
        slope = prophet._fetch_datalab_trend("test_keyword")
        
        self.assertIsNone(slope)

if __name__ == '__main__':
    unittest.main()
