
import os
import sys
import requests
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ConfigManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DebugNaverAPI")

def test_naver_api():
    config = ConfigManager()
    client_id = config.get_api_key("NAVER_CLIENT_ID")
    client_secret = config.get_api_key("NAVER_CLIENT_SECRET")
    
    logger.info(f"Loaded Client ID: {client_id[:4]}****" if client_id else "Client ID: None")
    
    if not client_id or not client_secret:
        logger.error("❌ Credentials missing!")
        return

    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret
    }
    # Simple query
    params = {"query": "청주맛집", "display": 1, "sort": "sim"}
    
    logger.info(f"Sending request to {url}...")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
        
        logger.info(f"Status Code: {resp.status_code}")
        logger.info(f"Response Headers: {resp.headers}")
        logger.info(f"Response Body: {resp.text[:500]}") # Print first 500 chars
        
        if resp.status_code == 200:
            logger.info("✅ API Test SUCCESS! Credentials are valid.")
        elif resp.status_code == 401:
            logger.error("❌ 401 Unauthorized. Check Client ID/Secret or API Permissions (Web Search/Blog Search).")
        elif resp.status_code == 429:
            logger.error("❌ 429 Too Many Requests. Daily Quota might be exceeded.")
        else:
            logger.error(f"❌ API Failed with status {resp.status_code}")

    except Exception as e:
        logger.error(f"❌ Exception during request: {e}")

if __name__ == "__main__":
    test_naver_api()
