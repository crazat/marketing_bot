"""
Instagram Graph API Client

Instagram Graph API를 사용하여 해시태그 검색, 미디어 상세 정보,
인사이트 조회 등의 기능을 제공합니다.

Requirements:
- Facebook 앱 ID/Secret
- 장기 Access Token (60일 유효)
- Instagram Business Account ID
"""

import sys
import os
import json
import logging
import requests
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)


class InstagramGraphAPI:
    """Instagram Graph API 클라이언트"""

    BASE_URL = "https://graph.facebook.com/v18.0"

    def __init__(self):
        """토큰 및 ID 로드"""
        self.app_id: Optional[str] = None
        self.app_secret: Optional[str] = None
        self.access_token: Optional[str] = None
        self.business_account_id: Optional[str] = None
        self.token_expiry: Optional[datetime] = None

        self._load_credentials()

    def _load_credentials(self) -> bool:
        """자격 증명 로드 (ENV > .env > secrets.json)"""
        try:
            from utils import config

            self.app_id = config.get_api_key('INSTAGRAM_APP_ID')
            self.app_secret = config.get_api_key('INSTAGRAM_APP_SECRET')
            self.access_token = config.get_api_key('INSTAGRAM_ACCESS_TOKEN')
            self.business_account_id = config.get_api_key('INSTAGRAM_BUSINESS_ACCOUNT_ID')

            # 토큰 만료일 로드 (있으면)
            expiry_str = config.get_api_key('INSTAGRAM_TOKEN_EXPIRY')
            if expiry_str:
                try:
                    self.token_expiry = datetime.fromisoformat(expiry_str)
                except Exception:
                    pass

            if not all([self.app_id, self.app_secret, self.access_token, self.business_account_id]):
                logger.warning("Instagram API 자격 증명이 완전하지 않습니다.")
                return False

            logger.info("Instagram API 자격 증명 로드 완료")
            return True

        except Exception as e:
            logger.error(f"Instagram 자격 증명 로드 실패: {e}")
            return False

    def is_configured(self) -> bool:
        """API가 올바르게 설정되었는지 확인"""
        return all([
            self.app_id,
            self.app_secret,
            self.access_token,
            self.business_account_id
        ])

    def is_token_expiring_soon(self, days: int = 7) -> bool:
        """토큰이 곧 만료되는지 확인"""
        if not self.token_expiry:
            return True  # 만료일 모름 -> 갱신 권장
        return datetime.now() + timedelta(days=days) > self.token_expiry

    def _make_request(self, endpoint: str, params: Optional[Dict] = None, method: str = "GET",
                      max_retries: int = 3, base_delay: float = 1.0) -> Optional[Dict]:
        """
        API 요청 실행 (Rate Limit 재시도 포함)

        Args:
            endpoint: API 엔드포인트
            params: 요청 파라미터
            method: HTTP 메서드 (GET/POST)
            max_retries: 최대 재시도 횟수
            base_delay: 기본 대기 시간 (초)
        """
        if not self.is_configured():
            logger.error("Instagram API가 설정되지 않았습니다.")
            return None

        url = f"{self.BASE_URL}/{endpoint}"

        if params is None:
            params = {}
        params['access_token'] = self.access_token

        # 재시도 로직
        for attempt in range(max_retries):
            try:
                # Rate Limit 방지용 딜레이 (첫 시도 제외)
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # 지수 백오프
                    logger.info(f"Rate Limit 재시도 대기 중... ({delay}초)")
                    time.sleep(delay)

                # 요청 간 기본 딜레이 (0.3초)
                time.sleep(0.3)

                if method == "GET":
                    response = requests.get(url, params=params, timeout=30)
                else:
                    response = requests.post(url, data=params, timeout=30)

                response.raise_for_status()
                return response.json()

            except requests.exceptions.HTTPError as e:
                error_data = {}
                try:
                    error_data = e.response.json()
                except Exception:
                    pass

                error_msg = error_data.get('error', {}).get('message', str(e))
                error_code = error_data.get('error', {}).get('code', 0)

                # Rate Limit 에러 (코드 4 또는 17)
                if error_code in [4, 17, 32]:
                    if attempt < max_retries - 1:
                        wait_time = base_delay * (2 ** attempt)
                        logger.warning(f"Rate Limit 도달. {wait_time}초 후 재시도... (시도 {attempt + 1}/{max_retries})")
                        continue  # 재시도
                    else:
                        logger.error(f"Rate Limit: 최대 재시도 횟수 초과")
                        return None

                # 토큰 만료 오류
                if error_code in [190, 102]:
                    logger.warning("Access Token이 만료되었습니다. 토큰 갱신이 필요합니다.")
                    return None

                logger.error(f"Instagram API 오류 (코드: {error_code}): {error_msg}")

                # 재시도 가능한 에러가 아니면 즉시 반환
                if error_code not in [4, 17, 32]:
                    return None

            except requests.exceptions.Timeout:
                logger.error("Instagram API 요청 시간 초과")
                return None
            except Exception as e:
                logger.error(f"Instagram API 요청 실패: {e}")
                return None

        return None

    def search_hashtag(self, hashtag: str, limit: int = 25) -> List[Dict]:
        """
        해시태그 검색

        Args:
            hashtag: 검색할 해시태그 (# 제외)
            limit: 최대 결과 수 (기본 25, 최대 50)

        Returns:
            미디어 목록 [{"id", "caption", "media_type", "permalink", "timestamp", ...}]
        """
        results = []

        # 1단계: 해시태그 ID 조회
        hashtag_clean = hashtag.replace("#", "").strip()

        search_params = {
            'user_id': self.business_account_id,
            'q': hashtag_clean
        }

        search_result = self._make_request("ig_hashtag_search", search_params)

        if not search_result or 'data' not in search_result or not search_result['data']:
            logger.warning(f"해시태그 '{hashtag_clean}'을 찾을 수 없습니다.")
            return results

        hashtag_id = search_result['data'][0]['id']
        logger.info(f"해시태그 ID 조회: #{hashtag_clean} -> {hashtag_id}")

        # 2단계: 최근 미디어 조회 (recent_media)
        media_params = {
            'user_id': self.business_account_id,
            'fields': 'id,caption,media_type,permalink,timestamp,like_count,comments_count,media_url',
            'limit': min(limit, 50)
        }

        media_result = self._make_request(f"{hashtag_id}/recent_media", media_params)

        if media_result and 'data' in media_result:
            results = media_result['data']
            logger.info(f"해시태그 #{hashtag_clean}: {len(results)}개 미디어 조회")

        return results

    def search_hashtag_top(self, hashtag: str, limit: int = 25) -> List[Dict]:
        """
        해시태그 인기 게시물 검색 (top_media)

        Args:
            hashtag: 검색할 해시태그 (# 제외)
            limit: 최대 결과 수

        Returns:
            인기 미디어 목록
        """
        results = []

        hashtag_clean = hashtag.replace("#", "").strip()

        # 해시태그 ID 조회
        search_params = {
            'user_id': self.business_account_id,
            'q': hashtag_clean
        }

        search_result = self._make_request("ig_hashtag_search", search_params)

        if not search_result or 'data' not in search_result or not search_result['data']:
            return results

        hashtag_id = search_result['data'][0]['id']

        # 인기 미디어 조회
        media_params = {
            'user_id': self.business_account_id,
            'fields': 'id,caption,media_type,permalink,timestamp,like_count,comments_count,media_url',
            'limit': min(limit, 50)
        }

        media_result = self._make_request(f"{hashtag_id}/top_media", media_params)

        if media_result and 'data' in media_result:
            results = media_result['data']
            logger.info(f"해시태그 #{hashtag_clean} 인기 게시물: {len(results)}개")

        return results

    def get_media_details(self, media_id: str) -> Optional[Dict]:
        """
        미디어 상세 정보 조회

        Args:
            media_id: 미디어 ID

        Returns:
            미디어 상세 정보
        """
        params = {
            'fields': 'id,caption,media_type,permalink,timestamp,like_count,comments_count,media_url,thumbnail_url,username,owner'
        }

        result = self._make_request(media_id, params)
        return result

    def get_media_insights(self, media_id: str) -> Optional[Dict]:
        """
        미디어 인사이트 조회 (자사 계정 미디어만 가능)

        Args:
            media_id: 미디어 ID

        Returns:
            인사이트 데이터 (reach, impressions, engagement 등)
        """
        params = {
            'metric': 'reach,impressions,engagement,saved'
        }

        result = self._make_request(f"{media_id}/insights", params)

        if result and 'data' in result:
            insights = {}
            for item in result['data']:
                insights[item['name']] = item['values'][0]['value']
            return insights

        return None

    def get_account_info(self) -> Optional[Dict]:
        """
        비즈니스 계정 정보 조회

        Returns:
            계정 정보 (followers_count, media_count, username 등)
        """
        params = {
            'fields': 'id,username,name,biography,followers_count,follows_count,media_count,profile_picture_url,website'
        }

        result = self._make_request(self.business_account_id, params)
        return result

    def refresh_token(self) -> Optional[str]:
        """
        장기 토큰 갱신 (만료 전에 호출)

        Note: 토큰은 60일 유효. 만료 전 갱신 필요.

        Returns:
            새 Access Token (None이면 실패)
        """
        if not self.access_token:
            logger.error("갱신할 토큰이 없습니다.")
            return None

        url = f"{self.BASE_URL}/oauth/access_token"
        params = {
            'grant_type': 'fb_exchange_token',
            'client_id': self.app_id,
            'client_secret': self.app_secret,
            'fb_exchange_token': self.access_token
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            new_token = data.get('access_token')
            expires_in = data.get('expires_in', 5184000)  # 기본 60일

            if new_token:
                self.access_token = new_token
                self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
                logger.info(f"토큰 갱신 완료. 만료일: {self.token_expiry.isoformat()}")

                # secrets.json 업데이트 (선택적)
                self._save_new_token(new_token, self.token_expiry)

                return new_token

            return None

        except Exception as e:
            logger.error(f"토큰 갱신 실패: {e}")
            return None

    def _save_new_token(self, new_token: str, expiry: datetime) -> bool:
        """새 토큰을 secrets.json에 저장"""
        try:
            from utils import config
            secrets_path = config.secrets_path

            if not os.path.exists(secrets_path):
                return False

            with open(secrets_path, 'r', encoding='utf-8') as f:
                secrets = json.load(f)

            secrets['INSTAGRAM_ACCESS_TOKEN'] = new_token
            secrets['INSTAGRAM_TOKEN_EXPIRY'] = expiry.isoformat()

            with open(secrets_path, 'w', encoding='utf-8') as f:
                json.dump(secrets, f, indent=4, ensure_ascii=False)

            logger.info("secrets.json에 새 토큰 저장 완료")
            return True

        except Exception as e:
            logger.warning(f"토큰 저장 실패 (수동 업데이트 필요): {e}")
            return False

    def test_connection(self) -> Dict[str, Any]:
        """
        API 연결 테스트

        Returns:
            테스트 결과 {"success": bool, "account": dict, "message": str}
        """
        result = {
            "success": False,
            "account": None,
            "message": ""
        }

        if not self.is_configured():
            result["message"] = "Instagram API 자격 증명이 설정되지 않았습니다."
            return result

        account_info = self.get_account_info()

        if account_info:
            result["success"] = True
            result["account"] = account_info
            result["message"] = f"연결 성공: @{account_info.get('username', 'unknown')}"

            # 토큰 만료 경고
            if self.is_token_expiring_soon():
                result["message"] += " (토큰 만료 임박 - 갱신 필요)"
        else:
            result["message"] = "API 연결 실패. 자격 증명을 확인하세요."

        return result


def test_api():
    """API 연결 테스트 (직접 실행용)"""
    print(f"[{datetime.now()}] Instagram Graph API 연결 테스트")
    print("-" * 50)

    api = InstagramGraphAPI()

    if not api.is_configured():
        print("설정 필요: Instagram API 자격 증명이 구성되지 않았습니다.")
        print("\n필요한 환경변수 또는 secrets.json 키:")
        print("  - INSTAGRAM_APP_ID")
        print("  - INSTAGRAM_APP_SECRET")
        print("  - INSTAGRAM_ACCESS_TOKEN")
        print("  - INSTAGRAM_BUSINESS_ACCOUNT_ID")
        print("\n설정 가이드: docs/INSTAGRAM_SETUP_GUIDE.md")
        return

    result = api.test_connection()

    if result["success"]:
        print(f"[OK] {result['message']}")
        print(f"\n계정 정보:")
        account = result["account"]
        print(f"  Username: @{account.get('username', 'N/A')}")
        print(f"  Followers: {account.get('followers_count', 'N/A')}")
        print(f"  Media Count: {account.get('media_count', 'N/A')}")

        # 해시태그 테스트
        print(f"\n해시태그 검색 테스트 (#청주다이어트)...")
        media = api.search_hashtag("청주다이어트", limit=5)
        print(f"  결과: {len(media)}개 미디어")
        for m in media[:3]:
            caption = (m.get('caption') or '')[:50]
            print(f"    - {caption}...")
    else:
        print(f"[FAIL] {result['message']}")


if __name__ == "__main__":
    test_api()
