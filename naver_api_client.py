import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from utils import ConfigManager, logger

class NaverApiClient:
    """
    Official Naver Search API Client.
    Reliable, fast, and legal. 25,000 requests/day limit per key.
    Supports key rotation from NAVER_SEARCH_KEYS array.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.secrets = self.config.load_secrets()

        # Key rotation: Use NAVER_SEARCH_KEYS array if available
        self.search_keys = self.secrets.get("NAVER_SEARCH_KEYS", [])
        self.current_key_index = 0

        # Fallback to single key
        if not self.search_keys:
            single_id = self.secrets.get("NAVER_CLIENT_ID", "")
            single_secret = self.secrets.get("NAVER_CLIENT_SECRET", "")
            if single_id and single_secret:
                self.search_keys = [{"id": single_id, "secret": single_secret}]

        if not self.search_keys:
            logger.warning("⚠️ Naver API Keys missing in secrets.json. API calls will fail.")
            self.client_id = ""
            self.client_secret = ""
        else:
            self._rotate_key()

        # Setup Session with Retry
        self.session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        self.session.mount('https://', HTTPAdapter(max_retries=retries))

    def _rotate_key(self):
        """Rotate to next API key"""
        if self.search_keys:
            key = self.search_keys[self.current_key_index]
            self.client_id = key["id"]
            self.client_secret = key["secret"]
            self.current_key_index = (self.current_key_index + 1) % len(self.search_keys)

    def search(self, category, keyword, display=10, sort='date'):
        """
        Generic Search Function.
        :param category: 'blog', 'news', 'cafearticle'
        :param keyword: search term
        :param display: number of results (1-100)
        :param sort: 'date' (recent) or 'sim' (relevant)
        """
        if not self.search_keys:
            return {"error": "Missing API Key", "items": []}

        # Rotate key for each request (load balancing)
        self._rotate_key()

        try:
            url = f"https://openapi.naver.com/v1/search/{category}"
            headers = {
                "X-Naver-Client-Id": self.client_id,
                "X-Naver-Client-Secret": self.client_secret
            }
            params = {
                "query": keyword,
                "display": display,
                "sort": sort
            }
            
            response = self.session.get(url, headers=headers, params=params, timeout=5)
            response.raise_for_status()
            
            # Track API usage
            try:
                from api_tracker import get_tracker
                get_tracker().log_call('naver_search', f'{category}/{keyword}', success=True)
            except Exception:
                pass  # Don't fail if tracker unavailable
            
            return response.json()
                
        except Exception as e:
            # Track failed call
            try:
                from api_tracker import get_tracker
                get_tracker().log_call('naver_search', f'{category}/{keyword}', success=False, error=str(e)[:100])
            except Exception:
                pass
            logger.error(f"Naver API Exception: {e}")
            return {"error": str(e), "items": []}

    def search_blog(self, keyword, count=10):
        return self.search('blog', keyword, count)

    def search_news(self, keyword, count=10):
        return self.search('news', keyword, count)

    def search_cafe(self, keyword, count=10):
        return self.search('cafearticle', keyword, count)

if __name__ == "__main__":
    # Test
    client = NaverApiClient()
    # Testing call if keys exist
    if client.client_id:
        print(client.search_news("한의원"))
    else:
        print("Set NAVER_CLIENT_ID and NAVER_CLIENT_SECRET in secrets.json to test.")

