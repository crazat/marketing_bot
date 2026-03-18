import requests
import json
import os
import sys
from datetime import datetime

class KakaoSender:
    def __init__(self):
        self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.secrets_path = os.path.join(self.base_dir, 'config', 'secrets.json')
        self.tokens_path = os.path.join(self.base_dir, 'config', 'kakao_tokens.json')
        self._load_config()

    def _load_config(self):
        with open(self.secrets_path, 'r', encoding='utf-8') as f:
            self.api_key = json.load(f)['KAKAO_REST_API_KEY']

    def _load_tokens(self):
        if not os.path.exists(self.tokens_path):
            print("❌ Error: Kakao tokens not found. Please run kakao_auth.py first.")
            return None
        with open(self.tokens_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_tokens(self, tokens):
        with open(self.tokens_path, 'w', encoding='utf-8') as f:
            json.dump(tokens, f, indent=4)

    def _refresh_token(self, tokens):
        url = "https://kauth.kakao.com/oauth/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": self.api_key,
            "refresh_token": tokens['refresh_token']
        }
        
        response = requests.post(url, data=data, timeout=10)
        new_tokens = response.json()
        
        if 'access_token' in new_tokens:
            # Update access token
            tokens['access_token'] = new_tokens['access_token']
            # Update refresh token if provided (it usually rotates)
            if 'refresh_token' in new_tokens:
                tokens['refresh_token'] = new_tokens['refresh_token']
            
            self._save_tokens(tokens)
            return tokens
        else:
            print(f"❌ Token Refresh Failed: {new_tokens}")
            return None

    def send_message(self, text, link_url="https://m.naver.com"):
        tokens = self._load_tokens()
        if not tokens: return False
        
        headers = {"Authorization": "Bearer " + tokens["access_token"]}
        
        # Template for "Feed" type message (Look nicer than text)
        data = {
            "template_object": json.dumps({
                "object_type": "text",
                "text": text,
                "link": {
                    "web_url": link_url,
                    "mobile_web_url": link_url
                },
                "button_title": "자세히 보기"
            })
        }
        
        url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
        response = requests.post(url, headers=headers, data=data, timeout=10)
        
        # Check if token expired (-401)
        if response.status_code == 401 or response.json().get('code') == -401:
            print("🔄 Token expired. Refreshing...")
            tokens = self._refresh_token(tokens)
            if tokens:
                headers = {"Authorization": "Bearer " + tokens["access_token"]}
                response = requests.post(url, headers=headers, data=data, timeout=10)
        
        if response.status_code == 200 and response.json().get('result_code') == 0:
            print(f"✅ Kakao Alert Sent: {text[:20]}...")
            return True
        else:
            print(f"❌ Failed to send: {response.text}")
            return False

if __name__ == "__main__":
    sender = KakaoSender()
    sender.send_message("🔔 규림 마케팅 봇 테스트 메시지입니다.")
