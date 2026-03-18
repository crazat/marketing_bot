"""
YouTube Data API v3 Client for Marketing Bot.

Provides authenticated access to YouTube search and comments
with Circuit Breaker pattern for reliability.
"""
import os
import sys
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retry_helper import retry_with_backoff, CircuitBreaker

# YouTube API 할당량 초과 예외
class QuotaExceededError(Exception):
    """YouTube API 일일 할당량 초과"""
    pass


class YouTubeAPIClient:
    """
    YouTube Data API v3 클라이언트.

    환경변수 YOUTUBE_API_KEY가 설정되어 있어야 합니다.

    Usage:
        client = YouTubeAPIClient()
        if client.is_available():
            videos = client.search_videos("청주 다이어트", max_results=5)
            comments = client.get_video_comments(video_id, max_results=20)
    """

    def __init__(self):
        self.api_key = os.environ.get('YOUTUBE_API_KEY')
        self.youtube = None
        self.circuit_breaker = CircuitBreaker(
            name="youtube_api",
            threshold=3,
            reset_after=3600  # 1시간 후 재시도
        )

        if self.api_key:
            try:
                from googleapiclient.discovery import build
                self.youtube = build('youtube', 'v3', developerKey=self.api_key)
                print(f"[{datetime.now()}] YouTube API mode enabled")
            except ImportError:
                print("[YouTubeAPIClient] google-api-python-client not installed")
                self.youtube = None
            except Exception as e:
                print(f"[YouTubeAPIClient] Init failed: {e}")
                self.youtube = None

    def is_available(self) -> bool:
        """API 클라이언트 사용 가능 여부 확인"""
        if self.circuit_breaker.is_open():
            return False
        return self.youtube is not None

    @retry_with_backoff(max_retries=2, initial_delay=1.0, exceptions=(Exception,))
    def search_videos(self, query: str, max_results: int = 5) -> list:
        """
        YouTube 동영상 검색.

        Args:
            query: 검색어
            max_results: 최대 결과 수 (기본값: 5)

        Returns:
            list: [{"video_id": str, "title": str, "url": str}, ...]
        """
        if not self.is_available():
            raise QuotaExceededError("YouTube API not available (circuit open)")

        try:
            request = self.youtube.search().list(
                part="snippet",
                q=query,
                type="video",
                maxResults=max_results,
                relevanceLanguage="ko",
                regionCode="KR"
            )
            response = request.execute()

            self.circuit_breaker.record_success()

            results = []
            for item in response.get('items', []):
                video_id = item['id']['videoId']
                results.append({
                    'video_id': video_id,
                    'title': item['snippet']['title'],
                    'url': f"https://www.youtube.com/watch?v={video_id}",
                    'channel': item['snippet']['channelTitle'],
                    'published_at': item['snippet']['publishedAt']
                })

            return results

        except Exception as e:
            error_str = str(e).lower()
            if 'quota' in error_str or 'exceeded' in error_str:
                self.circuit_breaker.record_failure()
                raise QuotaExceededError(f"YouTube API quota exceeded: {e}")
            self.circuit_breaker.record_failure()
            raise

    @retry_with_backoff(max_retries=2, initial_delay=1.0, exceptions=(Exception,))
    def get_video_comments(self, video_id: str, max_results: int = 20) -> list:
        """
        동영상 댓글 가져오기.

        Args:
            video_id: YouTube 동영상 ID
            max_results: 최대 댓글 수 (기본값: 20)

        Returns:
            list: [{"author": str, "text": str, "published_at": str, "like_count": int}, ...]
        """
        if not self.is_available():
            raise QuotaExceededError("YouTube API not available (circuit open)")

        try:
            request = self.youtube.commentThreads().list(
                part="snippet",
                videoId=video_id,
                maxResults=max_results,
                order="relevance",
                textFormat="plainText"
            )
            response = request.execute()

            self.circuit_breaker.record_success()

            comments = []
            for item in response.get('items', []):
                snippet = item['snippet']['topLevelComment']['snippet']
                comments.append({
                    'author': snippet['authorDisplayName'],
                    'text': snippet['textDisplay'],
                    'published_at': snippet['publishedAt'],
                    'like_count': snippet.get('likeCount', 0)
                })

            return comments

        except Exception as e:
            error_str = str(e).lower()
            # 댓글 비활성화된 동영상
            if 'disabled' in error_str or 'commentsDisabled' in error_str:
                return []
            if 'quota' in error_str or 'exceeded' in error_str:
                self.circuit_breaker.record_failure()
                raise QuotaExceededError(f"YouTube API quota exceeded: {e}")
            self.circuit_breaker.record_failure()
            raise

    def get_quota_status(self) -> dict:
        """Circuit Breaker 상태 반환"""
        return self.circuit_breaker.get_status()


if __name__ == "__main__":
    # 테스트
    client = YouTubeAPIClient()
    print(f"API Available: {client.is_available()}")

    if client.is_available():
        try:
            videos = client.search_videos("청주 다이어트", max_results=3)
            print(f"Found {len(videos)} videos")
            for v in videos:
                print(f"  - {v['title']}")
        except QuotaExceededError as e:
            print(f"Quota Error: {e}")
        except Exception as e:
            print(f"Error: {e}")
