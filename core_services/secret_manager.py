"""
Secret Manager
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 보안 강화 - API 키 관리 서비스

환경 변수 기반 시크릿 관리:
- .env 파일에서 시크릿 로드
- 싱글톤 패턴으로 전역 접근
- 누락된 시크릿 명확한 에러 처리
"""

import os
import logging
from typing import Optional, Dict, Any
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent


class SecretNotFoundError(Exception):
    """시크릿을 찾을 수 없을 때 발생하는 예외"""
    pass


class SecretManager:
    """
    API 키 및 시크릿 관리 싱글톤 클래스

    환경 변수에서 시크릿을 로드하고 안전하게 접근 제공.
    .env 파일 또는 시스템 환경 변수 모두 지원.

    사용법:
        from services.secret_manager import get_secret_manager

        sm = get_secret_manager()
        api_key = sm.get_secret("GEMINI_API_KEY")
    """

    _instance: Optional['SecretManager'] = None
    _initialized: bool = False

    # 필수 시크릿 목록 (없으면 경고)
    REQUIRED_SECRETS = [
        'GEMINI_API_KEY',
    ]

    # 선택적 시크릿 목록
    OPTIONAL_SECRETS = [
        'NAVER_CLIENT_ID',
        'NAVER_CLIENT_SECRET',
        'KAKAO_REST_API_KEY',
        'INSTAGRAM_ACCESS_TOKEN',
        'OPENAI_API_KEY',
    ]

    def __new__(cls) -> 'SecretManager':
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self) -> None:
        if SecretManager._initialized:
            return

        self._secrets: Dict[str, str] = {}
        self._load_secrets()
        SecretManager._initialized = True

    def _load_secrets(self) -> None:
        """환경 변수 및 .env 파일에서 시크릿 로드"""
        # dotenv 로드 시도
        try:
            from dotenv import load_dotenv

            # 여러 .env 파일 위치 시도
            env_paths = [
                PROJECT_ROOT / '.env',
                PROJECT_ROOT / 'config' / '.env',
                Path.home() / '.marketing_bot' / '.env',
            ]

            for env_path in env_paths:
                if env_path.exists():
                    load_dotenv(env_path)
                    logger.info(f"✅ .env 로드됨: {env_path}")
                    break
            else:
                logger.warning("⚠️ .env 파일을 찾을 수 없음. 시스템 환경 변수만 사용.")

        except ImportError:
            logger.warning("⚠️ python-dotenv 미설치. 시스템 환경 변수만 사용.")

        # 환경 변수에서 시크릿 캐시
        all_secrets = self.REQUIRED_SECRETS + self.OPTIONAL_SECRETS
        for key in all_secrets:
            value = os.environ.get(key)
            if value:
                self._secrets[key] = value

        # 필수 시크릿 검증
        missing = [k for k in self.REQUIRED_SECRETS if k not in self._secrets]
        if missing:
            logger.warning(f"⚠️ 필수 시크릿 누락: {missing}")

        loaded_count = len(self._secrets)
        logger.info(f"🔐 SecretManager 초기화: {loaded_count}개 시크릿 로드됨")

    def get_secret(self, key: str, default: Optional[str] = None) -> str:
        """
        시크릿 값 조회

        Args:
            key: 시크릿 키 (예: 'GEMINI_API_KEY')
            default: 기본값 (None이면 에러 발생)

        Returns:
            시크릿 값

        Raises:
            SecretNotFoundError: 시크릿이 없고 기본값도 없을 때
        """
        # 캐시된 값 먼저 확인
        if key in self._secrets:
            return self._secrets[key]

        # 환경 변수 직접 확인 (동적 추가된 경우)
        value = os.environ.get(key)
        if value:
            self._secrets[key] = value
            return value

        # 기본값 반환 또는 에러
        if default is not None:
            return default

        raise SecretNotFoundError(
            f"시크릿 '{key}'를 찾을 수 없습니다. "
            f".env 파일에 {key}=<값>을 추가하거나 환경 변수를 설정하세요."
        )

    def get_secret_safe(self, key: str, default: str = "") -> str:
        """
        안전한 시크릿 조회 (에러 발생 안함)

        Args:
            key: 시크릿 키
            default: 기본값 (기본: 빈 문자열)

        Returns:
            시크릿 값 또는 기본값
        """
        try:
            return self.get_secret(key, default)
        except SecretNotFoundError:
            return default

    def has_secret(self, key: str) -> bool:
        """시크릿 존재 여부 확인"""
        return key in self._secrets or os.environ.get(key) is not None

    def get_all_keys(self) -> list:
        """로드된 시크릿 키 목록 (값은 노출 안함)"""
        return list(self._secrets.keys())

    def mask_secret(self, value: str) -> str:
        """시크릿 값 마스킹 (로그용)"""
        if not value or len(value) < 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"

    def validate(self) -> Dict[str, Any]:
        """
        시크릿 상태 검증

        Returns:
            검증 결과 딕셔너리
        """
        result = {
            'valid': True,
            'loaded': len(self._secrets),
            'missing_required': [],
            'missing_optional': [],
            'status': {}
        }

        for key in self.REQUIRED_SECRETS:
            if self.has_secret(key):
                result['status'][key] = 'OK'
            else:
                result['status'][key] = 'MISSING'
                result['missing_required'].append(key)
                result['valid'] = False

        for key in self.OPTIONAL_SECRETS:
            if self.has_secret(key):
                result['status'][key] = 'OK'
            else:
                result['status'][key] = 'NOT_SET'
                result['missing_optional'].append(key)

        return result


# 싱글톤 인스턴스 접근자
_manager_instance: Optional[SecretManager] = None


def get_secret_manager() -> SecretManager:
    """SecretManager 싱글톤 인스턴스 반환"""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = SecretManager()
    return _manager_instance


@lru_cache(maxsize=32)
def get_secret(key: str, default: Optional[str] = None) -> str:
    """
    편의 함수: 시크릿 직접 조회

    사용법:
        from services.secret_manager import get_secret
        api_key = get_secret("GEMINI_API_KEY")
    """
    return get_secret_manager().get_secret(key, default)
