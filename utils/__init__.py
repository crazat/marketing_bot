"""
Utils 패키지
DB 검증 및 유틸리티 스크립트 모음
"""

import os
import json
import logging
from typing import Optional, Dict, Any

# Configure logging
try:
    from logging_config import setup_logging
    setup_logging()
except ImportError:
    # Fallback if logging_config is missing or redundant
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

logger = logging.getLogger(__name__)

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    _env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
    if os.path.exists(_env_path):
        load_dotenv(_env_path)
        logger.info("Loaded configuration from .env file")
except ImportError:
    pass  # python-dotenv not installed, will use secrets.json only

class ConfigManager:
    """Centralized configuration manager for the Marketing Bot.

    Supports loading configuration from:
    1. Environment variables (highest priority)
    2. .env file (if python-dotenv installed)
    3. config/secrets.json (fallback)
    """

    def __init__(self, root_dir: Optional[str] = None):
        if root_dir is None:
            self.root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        else:
            self.root_dir = root_dir

        self.secrets_path = os.path.join(self.root_dir, 'config', 'secrets.json')
        self.prompts_path = os.path.join(self.root_dir, 'config', 'prompts.json')
        self.db_path = (
            os.environ.get('MARKETING_BOT_DB_PATH')
            or os.environ.get('APP_DB_PATH')
            or os.path.join(self.root_dir, 'db', 'marketing_data.db')
        )

    def load_secrets(self) -> Dict[str, Any]:
        """Loads secrets from secrets.json."""
        if not os.path.exists(self.secrets_path):
            logger.warning(f"Secrets file not found at {self.secrets_path}")
            return {}

        try:
            with open(self.secrets_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading secrets: {e}")
            return {}

    def get_api_key(self, key_name: str = 'GEMINI_API_KEY') -> Optional[str]:
        """Retrieves API key from environment variable or secrets.json.

        Priority: ENV > secrets.json
        """
        # 1. Try environment variable first
        env_value = os.environ.get(key_name)
        if env_value:
            return env_value

        # 2. Fallback to secrets.json
        secrets = self.load_secrets()
        return secrets.get(key_name)

    def get_api_key_list(self, key_name: str) -> list:
        """Retrieves a list of API keys from environment variables or secrets.json.

        For .env format, reads keys like:
        NAVER_SEARCH_CLIENT_ID_1, NAVER_SEARCH_SECRET_1, etc.

        Returns list of dicts: [{"id": "...", "secret": "..."}, ...]
        """
        # 1. Try secrets.json first (array format)
        secrets = self.load_secrets()
        value = secrets.get(key_name)
        if isinstance(value, list):
            return value

        # 2. Try environment variables with _1, _2, _3 suffix
        result = []

        # Determine prefix based on key_name
        if key_name == "NAVER_SEARCH_KEYS":
            prefix = "NAVER_SEARCH"
        elif key_name == "NAVER_DATALAB_KEYS":
            prefix = "NAVER_DATALAB"
        else:
            return []

        # Read numbered keys
        index = 1
        while True:
            client_id = os.environ.get(f"{prefix}_CLIENT_ID_{index}")
            secret = os.environ.get(f"{prefix}_SECRET_{index}")

            if not client_id or not secret:
                break

            result.append({
                "id": client_id,
                "secret": secret
            })
            index += 1

        return result

    def load_prompts(self):
        """Loads prompts from prompts.json."""
        if not os.path.exists(self.prompts_path):
            return {}
        try:
            with open(self.prompts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            return {}

    def get_prompt(self, key, default=""):
        """Gets a specific prompt by key."""
        prompts = self.load_prompts()
        return prompts.get(key, default)

    def load_targets(self):
        """Loads targets from config/targets.json."""
        target_path = os.path.join(self.root_dir, 'config', 'targets.json')
        if not os.path.exists(target_path):
             # Fallback to root targets.json if config one missing (backward compatibility)
             fallback = os.path.join(self.root_dir, 'targets.json')
             if os.path.exists(fallback):
                 with open(fallback, 'r', encoding='utf-8') as f: return json.load(f)
             return {}
        try:
            with open(target_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading targets: {e}")
            return {}

    def save_targets(self, targets_data: Dict[str, Any]) -> bool:
        """Persists targets to config/targets.json."""
        target_path = os.path.join(self.root_dir, 'config', 'targets.json')
        # If config/targets.json doesn't exist, check root for backward compatibility
        if not os.path.exists(target_path):
             fallback = os.path.join(self.root_dir, 'targets.json')
             if os.path.exists(fallback):
                 target_path = fallback

        try:
            with open(target_path, 'w', encoding='utf-8') as f:
                json.dump(targets_data, f, indent=4, ensure_ascii=False)
            logger.info("✅ Targets updated successfully.")
            return True
        except Exception as e:
            logger.error(f"Error saving targets: {e}")
            return False

    def load_rank_keywords(self) -> list:
        """Loads Naver Place Ranking keywords from config/keywords.json."""
        kw_path = os.path.join(self.root_dir, 'config', 'keywords.json')
        if not os.path.exists(kw_path):
            return []
        try:
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return data.get("naver_place", [])
        except Exception as e:
            logger.error(f"Error loading ranking keywords: {e}")
            return []

    def save_rank_keywords(self, keywords: list) -> bool:
        """Saves Naver Place Ranking keywords to config/keywords.json."""
        kw_path = os.path.join(self.root_dir, 'config', 'keywords.json')
        try:
            data = {"naver_place": keywords}
            with open(kw_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info("✅ Ranking keywords updated successfully.")
            return True
        except Exception as e:
            logger.error(f"Error saving ranking keywords: {e}")
            return False

    def load_selectors(self) -> Dict[str, Any]:
        """Loads CSS/XPath selectors from config/selectors.json."""
        sel_path = os.path.join(self.root_dir, 'config', 'selectors.json')
        if not os.path.exists(sel_path):
            logger.warning("selectors.json not found.")
            return {}
        try:
            with open(sel_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading selectors: {e}")
            return {}

    def get_selector(self, service: str, key: str) -> Any:
        """
        Retrieves a specific selector or group of selectors.
        Usage: cfg.get_selector('cafe_spy', 'portal_search')
        """
        all_selectors = self.load_selectors()
        return all_selectors.get(service, {}).get(key, None)

    def load_trend_matrix(self):
        """Loads trend matrix from config/trend_matrix.json."""
        path = os.path.join(self.root_dir, 'config', 'trend_matrix.json')
        if not os.path.exists(path):
            return {}
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading trend matrix: {e}")
            return {}

    def validate(self, required_keys=None):
        """
        Validates that required API keys are configured.

        Args:
            required_keys: List of key names to check. Defaults to common keys.

        Returns:
            dict: {"valid": bool, "missing": list, "warnings": list}
        """
        if required_keys is None:
            required_keys = ["GEMINI_API_KEY", "GOOGLE_API_KEY"]

        optional_keys = ["NAVER_CLIENT_ID", "NAVER_CLIENT_SECRET",
                         "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]

        missing = []
        warnings = []

        for key in required_keys:
            value = self.get_api_key(key)
            if not value:
                missing.append(key)

        for key in optional_keys:
            value = self.get_api_key(key)
            if not value:
                warnings.append(f"{key} not configured (optional)")

        # [Robustness] Validate targets.json
        targets = self.load_targets()
        if not targets:
            warnings.append("targets.json is empty or missing")
        elif "targets" not in targets and "competitors" not in targets:
             warnings.append("targets.json missing 'targets' or 'competitors' keys")

        is_valid = len(missing) == 0

        if not is_valid:
            logger.warning(f"Config validation failed. Missing: {missing}")

        return {
            "valid": is_valid,
            "missing": missing,
            "warnings": warnings
        }

    def get_model_name(self, model_type="flash"):
        """Returns the configured model name to ensure consistency."""
        # User requested: gemini-3-flash-preview
        if model_type == "flash":
            return "gemini-3-flash-preview"
        elif model_type == "pro":
            return "gemini-3-flash-preview" # Use 3-flash for pro workflows too if superior, or fallback
        return "gemini-3-flash-preview"

    def get_instagram_credentials(self) -> Dict[str, Optional[str]]:
        """
        Instagram Graph API 자격 증명을 반환합니다.

        Returns:
            Dict with keys: app_id, app_secret, access_token, business_account_id, token_expiry
        """
        return {
            "app_id": self.get_api_key("INSTAGRAM_APP_ID"),
            "app_secret": self.get_api_key("INSTAGRAM_APP_SECRET"),
            "access_token": self.get_api_key("INSTAGRAM_ACCESS_TOKEN"),
            "business_account_id": self.get_api_key("INSTAGRAM_BUSINESS_ACCOUNT_ID"),
            "token_expiry": self.get_api_key("INSTAGRAM_TOKEN_EXPIRY")
        }

    def is_instagram_configured(self) -> bool:
        """Instagram API가 올바르게 설정되었는지 확인합니다."""
        creds = self.get_instagram_credentials()
        required = ["app_id", "app_secret", "access_token", "business_account_id"]
        return all(creds.get(k) for k in required)

    def get_tiktok_credentials(self) -> Dict[str, Optional[str]]:
        """
        TikTok Research API 자격 증명을 반환합니다.

        Returns:
            Dict with keys: client_key, client_secret
        """
        return {
            "client_key": self.get_api_key("TIKTOK_CLIENT_KEY"),
            "client_secret": self.get_api_key("TIKTOK_CLIENT_SECRET")
        }

    def is_tiktok_configured(self) -> bool:
        """TikTok Research API가 올바르게 설정되었는지 확인합니다."""
        creds = self.get_tiktok_credentials()
        return all(creds.get(k) for k in ["client_key", "client_secret"])

# Singleton instance for easy import
config = ConfigManager()

def download_image_robust(src: str, save_path: str) -> bool:
    """
    Downloads an image from a URL or saves a Base64 string.

    Args:
        src: Image source (URL or base64 string)
        save_path: Full path to save the image

    Returns:
        bool: True if successful, False otherwise
    """
    import base64
    import requests

    try:
        # Case 1: Base64
        if src.startswith('data:image'):
            # format: data:image/jpeg;base64,/9j/4AAQSk...
            header, encoded = src.split(',', 1)
            data = base64.b64decode(encoded)
            with open(save_path, 'wb') as f:
                f.write(data)
            return True

        # Case 2: URL
        else:
            res = requests.get(src, timeout=5)
            if res.status_code == 200:
                with open(save_path, 'wb') as f:
                    f.write(res.content)
                return True
            else:
                logger.warning(f"Failed to download image (Status {res.status_code}): {src[:50]}...")
                return False

    except Exception as e:
        logger.warning(f"Error saving image: {e}")
        return False


# ============================================
# 네이버 API 요청 헬퍼 (공통 사용)
# ============================================
class NaverRequestHelper:
    """
    네이버 API/웹 요청을 위한 공통 헬퍼 클래스

    기능:
    - Exponential backoff 재시도
    - 429/503/403 에러 자동 대기
    - User-Agent 로테이션
    - Rate limiting
    - 요청 통계 추적

    사용법:
        helper = NaverRequestHelper(delay=2.0)
        response = helper.request_with_retry(url, params)
        if response:
            data = response.json()
    """

    def __init__(self, delay: float = 2.0, max_retries: int = 3):
        import requests
        self.delay = delay
        self.max_retries = max_retries
        self.session = requests.Session()
        self._last_call = 0
        self._request_count = 0
        self._error_count = 0

        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        ]
        self._ua_index = 0

    def _get_headers(self) -> dict:
        """헤더 생성 (User-Agent 로테이션)"""
        ua = self.user_agents[self._ua_index % len(self.user_agents)]
        self._ua_index += 1
        return {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
            "Referer": "https://www.naver.com/",
        }

    def _rate_limit(self):
        """API 호출 간격 제어"""
        import time
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)
        self._last_call = time.time()

    def request_with_retry(self, url: str, params: dict = None, timeout: int = 20):
        """
        Exponential backoff 재시도 로직

        Args:
            url: 요청 URL
            params: 쿼리 파라미터
            timeout: 타임아웃 (초)

        Returns:
            Response 객체 또는 None (실패 시)
        """
        import time
        import requests

        for attempt in range(self.max_retries):
            try:
                self._rate_limit()
                self._request_count += 1

                response = self.session.get(
                    url,
                    params=params,
                    headers=self._get_headers(),
                    timeout=timeout
                )

                # 429 Too Many Requests
                if response.status_code == 429:
                    wait_time = 60 + (attempt * 30)
                    logger.warning(f"⚠️ 429 Too Many Requests - {wait_time}초 대기...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 503 Service Unavailable
                if response.status_code == 503:
                    wait_time = 30 + (attempt * 15)
                    logger.warning(f"⚠️ 503 Service Unavailable - {wait_time}초 대기...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                # 403 Forbidden
                if response.status_code == 403:
                    wait_time = 120 + (attempt * 60)
                    logger.warning(f"⚠️ 403 Forbidden - {wait_time}초 대기...")
                    self._error_count += 1
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                return response

            except requests.exceptions.Timeout:
                wait_time = 5 * (attempt + 1)
                logger.warning(f"⚠️ Timeout - {wait_time}초 후 재시도 ({attempt+1}/{self.max_retries})")
                self._error_count += 1
                time.sleep(wait_time)

            except requests.exceptions.RequestException as e:
                wait_time = 2 ** (attempt + 1)
                logger.warning(f"⚠️ Request failed: {e} - {wait_time}초 후 재시도")
                self._error_count += 1
                time.sleep(wait_time)

        logger.error(f"❌ 최대 재시도 횟수 초과: {url}")
        return None

    def get_stats(self) -> dict:
        """요청 통계"""
        return {
            "requests": self._request_count,
            "errors": self._error_count,
            "error_rate": f"{(self._error_count / max(1, self._request_count)) * 100:.1f}%"
        }

# Export main classes and functions
__all__ = ['ConfigManager', 'config', 'logger', 'download_image_robust', 'NaverRequestHelper']
