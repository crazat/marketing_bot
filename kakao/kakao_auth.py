import requests
import json
import os
import webbrowser
import sys

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# ConfigManager 사용으로 통일
try:
    from utils import ConfigManager
except ImportError:
    # 직접 실행 시 경로 추가
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from utils import ConfigManager


class KakaoAuth:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.tokens_path = os.path.join(self.base_dir, 'config', 'kakao_tokens.json')
        self.redirect_uri = "https://example.com/oauth"  # Generic redirect URI for local testing
        self._load_secrets()

    def _load_secrets(self):
        """ConfigManager를 통해 API 키 로드"""
        config = ConfigManager(self.base_dir)
        self.api_key = config.get_api_key('KAKAO_REST_API_KEY')
        if not self.api_key:
            raise ValueError(
                "KAKAO_REST_API_KEY가 설정되지 않았습니다. "
                ".env 파일 또는 config/secrets.json에 설정해주세요."
            )

    def authorize(self):
        """Step 1: Get User Permission (Mock Server or Manual Copy-Paste)"""
        auth_url = f"https://kauth.kakao.com/oauth/authorize?client_id={self.api_key}&redirect_uri={self.redirect_uri}&response_type=code&scope=talk_message"
        
        print("\n🚀 [카카오톡 인증 시작]")
        print("1. 브라우저가 열리면 카카오 계정으로 로그인해주세요.")
        print("2. '동의하고 계속하기'를 누르면, 빈 페이지(example.com)로 이동합니다.")
        print("3. 그 페이지 주소창에 있는 URL 전체를 복사해서 아래에 붙여넣어 주세요.")
        print(f"\n🔗 인증 URL: {auth_url}\n")
        
        webbrowser.open(auth_url)
        
        url_input = input("📋 주소창 URL 전체 붙여넣기: ").strip()
        
        try:
            code = url_input.split('code=')[1]
            self._get_token(code)
        except IndexError:
            print("❌ 오류: URL에서 인증 코드를 찾을 수 없습니다. (code=... 부분이 보여야 합니다)")

    def _get_token(self, code):
        """Step 2: Exchange Code for Tokens"""
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": self.api_key,
            "redirect_uri": self.redirect_uri,
            "code": code
        }
        
        response = requests.post(url, data=data, timeout=10)
        tokens = response.json()
        
        if 'access_token' in tokens:
            self._save_tokens(tokens)
            print("✅ [인증 성공] 토큰이 저장되었습니다. 이제 알림을 받을 수 있습니다!")
        else:
            print(f"❌ [인증 실패] {tokens}")

    def _save_tokens(self, tokens):
        with open(self.tokens_path, 'w', encoding='utf-8') as f:
            json.dump(tokens, f, indent=4)
            
if __name__ == "__main__":
    auth = KakaoAuth()
    auth.authorize()
