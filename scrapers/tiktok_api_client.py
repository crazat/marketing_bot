"""
TikTok Research API Client
TikTok Research API v2 연동 (OAuth2 Client Credentials)
- Video Query API (키워드 검색)
- Comments API (댓글 수집)

Note: Requires approved TikTok Research API access.
Apply at: https://developers.tiktok.com/products/research-api
"""
import sys
import os
import time
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager
from retry_helper import CircuitBreaker, retry_with_backoff

logger = logging.getLogger("TikTokAPIClient")


class TikTokResearchAPIClient:
    """
    TikTok Research API v2 클라이언트

    Features:
    - OAuth2 Client Credentials 인증
    - Video Query API (키워드 검색)
    - Comments API (댓글 수집)
    - 자동 토큰 캐싱 및 갱신
    - CircuitBreaker (quota 초과 대비)
    """

    # API Endpoints
    AUTH_URL = "https://open.tiktokapis.com/v2/oauth/token/"
    VIDEO_QUERY_URL = "https://open.tiktokapis.com/v2/research/video/query/"
    COMMENTS_URL = "https://open.tiktokapis.com/v2/research/video/comment/list/"

    # Scopes required for Research API
    RESEARCH_SCOPES = "research.data.basic,user.info.basic"

    def __init__(self, client_key: str = None, client_secret: str = None):
        """
        Initialize TikTok Research API client.

        Args:
            client_key: TikTok API client key (optional, loads from config)
            client_secret: TikTok API client secret (optional, loads from config)
        """
        self.db = DatabaseManager()

        # Load credentials
        self.client_key = client_key or self._get_secret("TIKTOK_CLIENT_KEY")
        self.client_secret = client_secret or self._get_secret("TIKTOK_CLIENT_SECRET")

        # Token cache
        self._access_token = None
        self._token_expiry = None

        # Circuit breaker for quota protection
        self.circuit_breaker = CircuitBreaker(
            name="tiktok_api",
            threshold=5,  # Open after 5 failures
            reset_after=3600  # Reset after 1 hour (quota window)
        )

        # HTTP session with retry
        self.session = self._create_session()

    def _get_secret(self, key: str) -> str:
        """Load secret from environment or secrets.json."""
        # Priority: ENV > .env > secrets.json
        value = os.environ.get(key)
        if value:
            return value

        try:
            secrets_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'secrets.json'
            )
            with open(secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)
                return secrets.get(key, "")
        except Exception:
            return ""

    def _create_session(self) -> requests.Session:
        """Create HTTP session with retry configuration."""
        session = requests.Session()

        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "POST"]
        )

        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", adapter)

        return session

    def is_configured(self) -> bool:
        """Check if API credentials are configured."""
        return bool(self.client_key and self.client_secret)

    def _get_access_token(self) -> str:
        """
        Get access token using Client Credentials flow.
        Implements token caching and auto-refresh.
        """
        # Check cached token
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry - timedelta(minutes=5):
                return self._access_token

        if not self.is_configured():
            raise ValueError("TikTok API credentials not configured")

        try:
            response = self.session.post(
                self.AUTH_URL,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                data={
                    "client_key": self.client_key,
                    "client_secret": self.client_secret,
                    "grant_type": "client_credentials"
                },
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Token request failed: {response.status_code} - {response.text}")
                raise Exception(f"Token request failed: {response.status_code}")

            data = response.json()

            if "access_token" not in data:
                error_msg = data.get("error", {}).get("message", "Unknown error")
                raise Exception(f"Token response error: {error_msg}")

            self._access_token = data["access_token"]
            expires_in = data.get("expires_in", 7200)  # Default 2 hours
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in)

            logger.info(f"TikTok API token obtained (expires in {expires_in}s)")
            return self._access_token

        except Exception as e:
            logger.error(f"Failed to get access token: {e}")
            raise

    @retry_with_backoff(max_retries=2, initial_delay=2.0, exceptions=(requests.RequestException,))
    def search_videos(
        self,
        query: str,
        region_code: str = "KR",
        max_count: int = 20,
        start_date: str = None,
        end_date: str = None
    ) -> List[Dict]:
        """
        Search videos using TikTok Research API.

        Args:
            query: Search keyword
            region_code: Country code (default: KR for Korea)
            max_count: Maximum results (default: 20, max: 100)
            start_date: Filter start date (YYYYMMDD)
            end_date: Filter end date (YYYYMMDD)

        Returns:
            list: Video data list [{id, desc, create_time, author, ...}, ...]
        """
        if self.circuit_breaker.is_open():
            logger.warning("[CircuitBreaker] TikTok API circuit is OPEN. Skipping search.")
            return []

        if not self.is_configured():
            logger.warning("TikTok API not configured. Skipping video search.")
            return []

        print(f"[{datetime.now()}] TikTok API - Searching videos: '{query}'...")

        try:
            token = self._get_access_token()

            # Build query condition
            query_condition = {
                "and": [
                    {"operation": "EQ", "field_name": "region_code", "field_values": [region_code]},
                    {"operation": "IN", "field_name": "keyword", "field_values": [query]}
                ]
            }

            # Date filter
            if start_date and end_date:
                query_condition["and"].append({
                    "operation": "IN",
                    "field_name": "create_date_range",
                    "field_values": [start_date, end_date]
                })

            payload = {
                "query": query_condition,
                "max_count": min(max_count, 100),
                "fields": "id,video_description,create_time,region_code,share_count,view_count,like_count,comment_count,username,hashtag_names"
            }

            response = self.session.post(
                self.VIDEO_QUERY_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )

            if response.status_code == 429:
                logger.warning("TikTok API rate limit exceeded")
                self.circuit_breaker.record_failure()
                return []

            if response.status_code != 200:
                logger.error(f"Video query failed: {response.status_code} - {response.text}")
                self.circuit_breaker.record_failure()
                return []

            data = response.json()
            videos = data.get("data", {}).get("videos", [])

            self.circuit_breaker.record_success()
            print(f"   Found {len(videos)} videos")

            # Save to DB
            for video in videos:
                self._save_video_to_db(video, query)

            return videos

        except Exception as e:
            logger.error(f"Video search failed: {e}")
            self.circuit_breaker.record_failure()
            return []

    @retry_with_backoff(max_retries=2, initial_delay=2.0, exceptions=(requests.RequestException,))
    def get_video_comments(
        self,
        video_id: str,
        max_count: int = 50
    ) -> List[Dict]:
        """
        Get comments for a specific video.

        Args:
            video_id: TikTok video ID
            max_count: Maximum comments to fetch (default: 50, max: 100)

        Returns:
            list: Comment data list [{id, text, create_time, ...}, ...]
        """
        if self.circuit_breaker.is_open():
            logger.warning("[CircuitBreaker] TikTok API circuit is OPEN. Skipping comments.")
            return []

        if not self.is_configured():
            return []

        try:
            token = self._get_access_token()

            payload = {
                "video_id": video_id,
                "max_count": min(max_count, 100),
                "fields": "id,text,create_time,like_count,reply_count,parent_comment_id"
            }

            response = self.session.post(
                self.COMMENTS_URL,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json"
                },
                json=payload,
                timeout=30
            )

            if response.status_code == 429:
                self.circuit_breaker.record_failure()
                return []

            if response.status_code != 200:
                logger.error(f"Comments request failed: {response.status_code}")
                self.circuit_breaker.record_failure()
                return []

            data = response.json()
            comments = data.get("data", {}).get("comments", [])

            self.circuit_breaker.record_success()
            return comments

        except Exception as e:
            logger.error(f"Comments fetch failed: {e}")
            self.circuit_breaker.record_failure()
            return []

    def _save_video_to_db(self, video: Dict, keyword: str):
        """Save video data to mentions table."""
        try:
            video_id = video.get("id", "")
            desc = video.get("video_description", "")[:200]
            username = video.get("username", "Unknown")
            view_count = video.get("view_count", 0)
            like_count = video.get("like_count", 0)
            comment_count = video.get("comment_count", 0)
            create_time = video.get("create_time", "")

            # Format date
            if create_time:
                try:
                    dt = datetime.fromtimestamp(int(create_time))
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

            hashtags = video.get("hashtag_names", [])

            self.db.insert_mention({
                "target_name": "TikTok",
                "keyword": keyword,
                "source": "tiktok_api",
                "title": f"@{username}: {desc[:50]}...",
                "content": f"{desc}\n\nHashtags: {', '.join(hashtags) if hashtags else 'None'}\n\nViews: {view_count:,} | Likes: {like_count:,} | Comments: {comment_count:,}",
                "url": f"https://www.tiktok.com/@{username}/video/{video_id}",
                "image_url": "",
                "date_posted": date_str
            })

        except Exception as e:
            logger.debug(f"Failed to save video to DB: {e}")

    def save_comment_as_lead(self, comment: Dict, video_url: str, keyword: str):
        """Save a comment as a potential lead."""
        try:
            text = comment.get("text", "")
            create_time = comment.get("create_time", "")

            if create_time:
                try:
                    dt = datetime.fromtimestamp(int(create_time))
                    date_str = dt.strftime("%Y-%m-%d")
                except Exception:
                    date_str = datetime.now().strftime("%Y-%m-%d")
            else:
                date_str = datetime.now().strftime("%Y-%m-%d")

            self.db.insert_mention({
                "target_name": "TikTok",
                "keyword": keyword,
                "source": "tiktok_comment",
                "title": f"Comment: {text[:50]}...",
                "content": text,
                "url": video_url,
                "image_url": "",
                "date_posted": date_str
            })

        except Exception as e:
            logger.debug(f"Failed to save comment as lead: {e}")

    def run_keyword_scan(self, keywords: List[str], collect_comments: bool = False) -> Dict:
        """
        Run a full keyword scan.

        Args:
            keywords: List of keywords to search
            collect_comments: Whether to also fetch comments for each video

        Returns:
            dict: {'videos': int, 'comments': int, 'keywords_processed': int}
        """
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] TikTok API - Keyword Scan")
        print(f"   Keywords: {len(keywords)}")
        print(f"   Collect comments: {collect_comments}")
        print(f"{'='*60}\n")

        results = {
            'videos': 0,
            'comments': 0,
            'keywords_processed': 0,
            'errors': []
        }

        for kw in keywords:
            try:
                videos = self.search_videos(kw, max_count=20)
                results['videos'] += len(videos)
                results['keywords_processed'] += 1

                if collect_comments and videos:
                    for video in videos[:5]:  # Limit comment fetching
                        video_id = video.get("id")
                        if video_id:
                            comments = self.get_video_comments(video_id, max_count=30)
                            results['comments'] += len(comments)

                            # Save lead-worthy comments
                            video_url = f"https://www.tiktok.com/video/{video_id}"
                            for comment in comments:
                                text = comment.get("text", "").lower()
                                # Filter for potential leads (asking questions, seeking help)
                                if any(q in text for q in ["?", "어디", "추천", "알려", "찾", "문의"]):
                                    self.save_comment_as_lead(comment, video_url, kw)

                            time.sleep(0.5)  # Rate limiting

                time.sleep(1)  # Rate limiting between keywords

            except Exception as e:
                results['errors'].append(f"{kw}: {e}")
                continue

        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] Scan Complete!")
        print(f"   Videos found: {results['videos']}")
        print(f"   Comments collected: {results['comments']}")
        print(f"   Keywords processed: {results['keywords_processed']}/{len(keywords)}")
        if results['errors']:
            print(f"   Errors: {len(results['errors'])}")
        print(f"{'='*60}\n")

        return results


class TikTokAPIStatus:
    """Helper class to check TikTok API status."""

    @staticmethod
    def check_configuration() -> Dict:
        """Check if TikTok API is properly configured."""
        client = TikTokResearchAPIClient()

        status = {
            'configured': client.is_configured(),
            'client_key_set': bool(client.client_key),
            'client_secret_set': bool(client.client_secret),
            'circuit_breaker_state': client.circuit_breaker.get_status()
        }

        return status

    @staticmethod
    def test_connection() -> Dict:
        """Test API connection (requires valid credentials)."""
        client = TikTokResearchAPIClient()

        result = {
            'success': False,
            'message': '',
            'token_obtained': False
        }

        if not client.is_configured():
            result['message'] = "API credentials not configured"
            return result

        try:
            token = client._get_access_token()
            result['success'] = True
            result['token_obtained'] = True
            result['message'] = "Successfully connected to TikTok API"
        except Exception as e:
            result['message'] = f"Connection failed: {e}"

        return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="TikTok Research API Client")
    parser.add_argument("--status", action="store_true", help="Check API configuration status")
    parser.add_argument("--test", action="store_true", help="Test API connection")
    parser.add_argument("--search", type=str, help="Search keyword")
    args = parser.parse_args()

    if args.status:
        status = TikTokAPIStatus.check_configuration()
        print("\nTikTok API Configuration Status:")
        print(f"   Configured: {status['configured']}")
        print(f"   Client Key Set: {status['client_key_set']}")
        print(f"   Client Secret Set: {status['client_secret_set']}")
        print(f"   Circuit Breaker: {status['circuit_breaker_state']['state']}")

    elif args.test:
        print("\nTesting TikTok API Connection...")
        result = TikTokAPIStatus.test_connection()
        print(f"   Success: {result['success']}")
        print(f"   Message: {result['message']}")

    elif args.search:
        client = TikTokResearchAPIClient()
        if client.is_configured():
            videos = client.search_videos(args.search)
            print(f"\nFound {len(videos)} videos for '{args.search}'")
            for v in videos[:5]:
                print(f"   - {v.get('video_description', 'No description')[:50]}...")
        else:
            print("\nTikTok API not configured. Add credentials to config/secrets.json:")
            print('   "TIKTOK_CLIENT_KEY": "your-client-key"')
            print('   "TIKTOK_CLIENT_SECRET": "your-client-secret"')

    else:
        # Default: Show status
        status = TikTokAPIStatus.check_configuration()
        print("\nTikTok Research API Client")
        print("=" * 40)
        print(f"Status: {'Ready' if status['configured'] else 'Not Configured'}")
        print("\nUsage:")
        print("   --status   Check configuration")
        print("   --test     Test API connection")
        print("   --search   Search for videos")
        print("\nNote: Requires approved TikTok Research API access.")
        print("Apply at: https://developers.tiktok.com/products/research-api")
