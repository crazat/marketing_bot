"""
비밀 관리 서비스 (Windows DPAPI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-4] Windows Credential Manager (DPAPI) 기반 비밀 관리

config.json의 API 키를 평문 파일 대신 Windows 자격 증명 관리자에 저장.
DPAPI로 암호화되어 해당 Windows 사용자만 복호화 가능.

의존성: pip install keyring (Windows에서는 추가 백엔드 불필요)

사용법:
    from services.secrets_manager import SecretsManager

    # 저장
    SecretsManager.store("gemini_api_key", "your-key-here")

    # 조회
    key = SecretsManager.get("gemini_api_key")

    # config.json 마이그레이션
    SecretsManager.migrate_from_config()
"""

import json
import os
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

SERVICE_NAME = "marketing_bot"

# keyring 가용 여부
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False
    logger.info("keyring 미설치 - config.json 평문 모드로 동작. pip install keyring 권장")


class SecretsManager:
    """
    Windows DPAPI 기반 비밀 관리

    keyring 설치 시: Windows Credential Manager에 암호화 저장
    미설치 시: config.json 평문 폴백 (기존 동작)
    """

    @staticmethod
    def store(key: str, value: str) -> bool:
        """비밀 저장"""
        if not HAS_KEYRING:
            logger.warning(f"keyring 미설치 - '{key}' 저장 스킵")
            return False

        try:
            keyring.set_password(SERVICE_NAME, key, value)
            logger.info(f"🔒 비밀 저장: {key}")
            return True
        except Exception as e:
            logger.error(f"비밀 저장 실패 ({key}): {e}")
            return False

    @staticmethod
    def get(key: str, fallback_config: bool = True) -> Optional[str]:
        """
        비밀 조회

        Args:
            key: 비밀 키
            fallback_config: True이면 keyring에 없을 때 config.json에서 조회
        """
        # 1. keyring에서 조회
        if HAS_KEYRING:
            try:
                value = keyring.get_password(SERVICE_NAME, key)
                if value:
                    return value
            except Exception:
                pass

        # 2. config.json 폴백
        if fallback_config:
            return SecretsManager._get_from_config(key)

        return None

    @staticmethod
    def delete(key: str) -> bool:
        """비밀 삭제"""
        if not HAS_KEYRING:
            return False

        try:
            keyring.delete_password(SERVICE_NAME, key)
            logger.info(f"🔓 비밀 삭제: {key}")
            return True
        except Exception as e:
            logger.debug(f"비밀 삭제 실패 ({key}): {e}")
            return False

    @staticmethod
    def migrate_from_config() -> Dict[str, bool]:
        """
        config.json의 API 키를 keyring으로 마이그레이션

        마이그레이션 대상:
        - gemini.api_key
        - naver_api.client_id / client_secret
        - telegram.bot_token / chat_id
        - openweathermap.api_key
        """
        if not HAS_KEYRING:
            return {"error": "keyring 미설치"}

        config = SecretsManager._load_config()
        if not config:
            return {"error": "config.json 로드 실패"}

        results = {}

        # 마이그레이션 매핑: config 경로 → keyring 키
        migrations = [
            (["gemini", "api_key"], "gemini_api_key"),
            (["naver_api", "client_id"], "naver_client_id"),
            (["naver_api", "client_secret"], "naver_client_secret"),
            (["telegram", "bot_token"], "telegram_bot_token"),
            (["telegram", "chat_id"], "telegram_chat_id"),
            (["openweathermap", "api_key"], "openweathermap_api_key"),
            (["kakao", "admin_key"], "kakao_admin_key"),
        ]

        for path, keyring_key in migrations:
            value = config
            try:
                for p in path:
                    value = value[p]
                if value and isinstance(value, str) and value.strip():
                    success = SecretsManager.store(keyring_key, value)
                    results[keyring_key] = success
            except (KeyError, TypeError):
                results[keyring_key] = False

        migrated = sum(1 for v in results.values() if v)
        logger.info(f"🔒 비밀 마이그레이션 완료: {migrated}/{len(results)}건")
        return results

    @staticmethod
    def _load_config() -> Optional[Dict]:
        """config.json 로드"""
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            config_path = os.path.join(project_root, "config", "config.json")
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    @staticmethod
    def _get_from_config(key: str) -> Optional[str]:
        """config.json에서 키 조회 (폴백)"""
        config = SecretsManager._load_config()
        if not config:
            return None

        # keyring 키 → config 경로 역매핑
        key_map = {
            "gemini_api_key": ["gemini", "api_key"],
            "naver_client_id": ["naver_api", "client_id"],
            "naver_client_secret": ["naver_api", "client_secret"],
            "telegram_bot_token": ["telegram", "bot_token"],
            "telegram_chat_id": ["telegram", "chat_id"],
            "openweathermap_api_key": ["openweathermap", "api_key"],
            "kakao_admin_key": ["kakao", "admin_key"],
        }

        path = key_map.get(key)
        if not path:
            return None

        value = config
        try:
            for p in path:
                value = value[p]
            return value if isinstance(value, str) else None
        except (KeyError, TypeError):
            return None

    @staticmethod
    def is_available() -> bool:
        """keyring 사용 가능 여부"""
        return HAS_KEYRING

    @staticmethod
    def get_status() -> Dict[str, Any]:
        """비밀 관리 상태"""
        if not HAS_KEYRING:
            return {
                "backend": "config.json (평문)",
                "secure": False,
                "recommendation": "pip install keyring 설치 후 migrate_from_config() 실행",
            }

        stored_keys = []
        test_keys = [
            "gemini_api_key", "naver_client_id", "naver_client_secret",
            "telegram_bot_token", "openweathermap_api_key",
        ]
        for key in test_keys:
            try:
                if keyring.get_password(SERVICE_NAME, key):
                    stored_keys.append(key)
            except Exception:
                pass

        return {
            "backend": "Windows Credential Manager (DPAPI)",
            "secure": True,
            "stored_keys": stored_keys,
            "total_secured": len(stored_keys),
        }
