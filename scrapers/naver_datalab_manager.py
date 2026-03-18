import requests
import time
from datetime import datetime, timedelta
from utils import logger, ConfigManager

class NaverDataLabManager:
    """
    Manages interactions with Naver DataLab API to analyze search trends.
    """
    def __init__(self):
        self.config = ConfigManager()
        
        # [Multi-Key Support] Load all available DataLab keys
        self.api_keys = self.config.get_api_key_list("NAVER_DATALAB_KEYS")
        
        # Fallback to legacy loop or single key if list is empty
        if not self.api_keys:
            # 1. Try generic key first (Legacy/Primary)
            cid = self.config.get_api_key("NAVER_DATALAB_CLIENT_ID")
            sec = self.config.get_api_key("NAVER_DATALAB_SECRET")
            if cid and sec:
                self.api_keys.append({"id": cid, "secret": sec})
                
            # 2. Try numbered keys (Legacy)
            for i in range(2, 10):
                cid = self.config.get_api_key(f"NAVER_DATALAB_CLIENT_ID_{i}")
                sec = self.config.get_api_key(f"NAVER_DATALAB_SECRET_{i}")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})
                    
            # 3. Fallback to global keys
            if not self.api_keys:
                cid = self.config.get_api_key("NAVER_CLIENT_ID")
                sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})
        
        self.current_key_index = 0
        if self.api_keys:
            logger.info(f"🧪 Loaded {len(self.api_keys)} DataLab API Key(s) for rotation.")
        else:
            logger.warning("⚠️ Naver DataLab API credentials not found. Trend analysis will be disabled.")
            
        self.base_url = "https://openapi.naver.com/v1/datalab/search"

    def _get_next_headers(self):
        """Rotates API keys and returns headers for the next request."""
        if not self.api_keys:
            return {}
            
        # Round-robin rotation (Use current index)
        key_data = self.api_keys[self.current_key_index]
        
        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"],
            "Content-Type": "application/json"
        }
        
    def _rotate_key(self):
        """Forces rotation to the next key."""
        if len(self.api_keys) > 1:
            self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
            logger.info(f"🔄 DataLab Key Rotated to Index {self.current_key_index}")

    def get_trend_slope(self, keyword):
        """
        Calculates the linear regression slope of search trends for the last 30 days.
        Returns:
            float: Slope value (positive = rising, negative = falling)
            None: If API fails or data is insufficient
        """
        if not self.api_keys:
            logger.warning("Trend analysis skipped: No API credentials.")
            return None
            
        today = datetime.now()
        start_date = (today - timedelta(days=30)).strftime("%Y-%m-%d")
        end_date = today.strftime("%Y-%m-%d")
        
        body = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": "date",
            "keywordGroups": [
                {"groupName": keyword, "keywords": [keyword]}
            ]
        }
        
        max_retries = len(self.api_keys) + 1
        
        for _ in range(max_retries):
            headers = self._get_next_headers()
            try:
                response = requests.post(self.base_url, headers=headers, json=body, timeout=5)
                
                if response.status_code == 200:
                    data = response.json()
                    return self._calculate_slope(data)
                
                elif response.status_code in [401, 429]:
                    logger.warning(f"⚠️ DataLab API Error {response.status_code}. Rotating key...")
                    self._rotate_key()
                    time.sleep(0.5)
                    continue
                else:
                    # Other errors (400, 500) - don't retry same request
                    # logger.warning(f"DataLab API Error {response.status_code}: {response.text}")
                    break
            except Exception as e:
                logger.error(f"DataLab Request Failed: {e}")
                break
                
        return None
        return None

    def _calculate_slope(self, data):
        """
        Calculates the slope of the trend line using simple linear regression.
        """
        results = data.get('results', [])
        if not results: 
            return None
        
        metrics = results[0].get('data', [])
        if len(metrics) < 5: # Need at least a few data points
            return 0.0 
        
        # Simple Linear Regression
        # x = [0, 1, 2...], y = [ratios]
        n = len(metrics)
        xs = range(n)
        ys = [float(m['ratio']) for m in metrics]
        
        sum_x = sum(xs)
        sum_y = sum(ys)
        sum_xy = sum(x*y for x,y in zip(xs, ys))
        sum_xx = sum(x*x for x in xs)
        
        denominator = (n * sum_xx - sum_x * sum_x)
        if denominator == 0: 
            return 0.0
        
        slope = (n * sum_xy - sum_x * sum_y) / denominator
        return round(slope, 4)
