
import unittest
import sys
import os
import json
from unittest.mock import MagicMock, patch

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from insight_manager import InsightManager
from vision_analyst import VisionAnalyst

class TestPhase4Integration(unittest.TestCase):
    
    @patch('prophet.TheProphet.predict_next_week')
    @patch('vision_analyst.genai.GenerativeModel')
    @patch('logging_config.DatabaseLogHandler.emit') # Supress DB writes
    def test_sentinel_scan_flow(self, MockDBLog, MockGenAI, MockProphet):
        """
        Simulate the 'Force Scan' button logic from Dashboard.
        Verifies that Prophet and Vision logic are triggered and generate insights.
        """
        # 1. Setup Mock Prophet Return
        MockProphet.return_value = {
            "target_period": "2024-01-20 Week",
            "rising_trends": [
                {
                    "keyword": "청주 다이어트",
                    "predicted_growth": "🔥 급상승 (Real Data)",
                    "evidence": "Trend Slope: 1.5",
                    "action": "content_preloading"
                }
            ]
        }
        
        # 2. Setup Mock Vision Return
        mock_model = MagicMock()
        mock_model.generate_content.return_value.text = "Visual Report Content"
        MockGenAI.return_value = mock_model
        
        # 3. Initialize Manager
        manager = InsightManager()
        # Mock DB connection to avoid real DB writes or use in-memory
        manager.get_connection = MagicMock()
        manager.create_insight = MagicMock()
        
        # 4. Run Prophet Generation
        manager.generate_prophet_insights()
        
        # Verify Prophet Insight Created
        manager.create_insight.assert_called_with(
            i_type="trend_forecast",
            title="🔮 [Prophet] 🔥 급상승 (Real Data) : '청주 다이어트'",
            content=unittest.mock.ANY,
            meta=unittest.mock.ANY
        )
        print("[OK] Prophet Integration Verified")
        
        # 5. Run Vision Generation
        # Need to mock image finding
        with patch('glob.glob', return_value=['dummy.jpg']):
             with patch('os.path.exists', return_value=True):
                 with patch('PIL.Image.open', return_value=MagicMock()):
                     manager.generate_visual_trend_insights()
                     
        # Verify Vision Insight Created
        # Note: create_insight might be called multiple times, check if called with visual_trend
        calls = manager.create_insight.call_args_list
        visual_called = any(call.kwargs.get('i_type') == 'visual_trend' for call in calls)
        self.assertTrue(visual_called, "Visual Trend insight should be generated")
        print("[OK] Vision Integration Verified")

if __name__ == '__main__':
    unittest.main()
