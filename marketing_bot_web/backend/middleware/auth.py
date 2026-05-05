"""
API 인증 미들웨어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 8] API 키 기반 인증 시스템
- 민감 엔드포인트 보호 (/api/export, /api/backup, /api/automation 등)
- 환경변수 또는 설정 파일에서 API 키 로드
- X-API-Key 헤더로 인증
"""

import os
from typing import List, Optional, Callable
from fastapi import Request, HTTPException, Depends
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
import hashlib
import secrets

# API 키 헤더 정의
API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

# 보호할 경로 패턴 (민감 엔드포인트)
PROTECTED_PATHS = [
    "/api/export",
    "/api/backup",
    "/api/automation",
    "/api/scheduler",
    "/api/migration",
    "/api/preferences",
]

# 항상 허용할 경로 (인증 불필요)
PUBLIC_PATHS = [
    "/api/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
    "/static",
]


def get_api_key() -> Optional[str]:
    """
    환경변수에서 API 키 로드.

    [C1] Fail-closed: 환경변수 미설정 시 None 반환 → 인증 거부.
    개발 시에는 .env 또는 환경변수에 MARKETING_BOT_API_KEY를 반드시 설정.
    """
    return os.getenv("MARKETING_BOT_API_KEY")


def verify_api_key(api_key: str) -> bool:
    """API 키 검증.

    [C1] expected_key가 설정돼 있지 않으면 항상 False (fail-closed).
    """
    expected_key = get_api_key()
    if not expected_key:
        return False
    # 타이밍 공격 방지 상수 시간 비교
    return secrets.compare_digest(api_key, expected_key)


async def get_api_key_header(
    api_key: Optional[str] = Depends(API_KEY_HEADER)
) -> Optional[str]:
    """API 키 헤더에서 키 추출 (Dependency)"""
    return api_key


def require_api_key(api_key: Optional[str] = Depends(get_api_key_header)) -> str:
    """
    API 키 필수 검증 Dependency
    보호된 엔드포인트에서 사용

    사용법:
        @router.get("/protected")
        async def protected_endpoint(_: str = Depends(require_api_key)):
            return {"message": "인증됨"}
    """
    if not api_key:
        raise HTTPException(
            status_code=401,
            detail="API 키가 필요합니다. X-API-Key 헤더를 설정하세요.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    # [C1] 서버 측 기대 키 미설정은 구성 오류 — 500 반환
    if not get_api_key():
        raise HTTPException(
            status_code=500,
            detail="서버가 MARKETING_BOT_API_KEY로 구성되지 않았습니다.",
        )

    if not verify_api_key(api_key):
        raise HTTPException(
            status_code=403,
            detail="유효하지 않은 API 키입니다.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return api_key


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    API 키 인증 미들웨어

    특정 경로 패턴에 대해 자동으로 API 키 검증
    """

    def __init__(
        self,
        app,
        protected_paths: List[str] = None,
        public_paths: List[str] = None,
        enabled: bool = True
    ):
        super().__init__(app)
        self.protected_paths = protected_paths or PROTECTED_PATHS
        self.public_paths = public_paths or PUBLIC_PATHS
        self.enabled = enabled

    @staticmethod
    def _path_matches(path: str, prefix: str) -> bool:
        """Return True for exact path matches or path-segment prefix matches."""
        normalized = prefix.rstrip("/") or "/"
        if normalized == "/":
            return path == "/"
        return path == normalized or path.startswith(f"{normalized}/")

    def _is_protected_path(self, path: str) -> bool:
        """보호된 경로인지 확인"""
        for protected in self.protected_paths:
            if self._path_matches(path, protected):
                return True
        return False

    def _is_public_path(self, path: str) -> bool:
        """공개 경로인지 확인"""
        for public in self.public_paths:
            if self._path_matches(path, public):
                return True
        return False

    async def dispatch(self, request: Request, call_next: Callable):
        # 미들웨어 비활성화 시 통과
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # 공개 경로는 인증 불필요
        if self._is_public_path(path):
            return await call_next(request)

        # 보호된 경로는 API 키 필수
        if self._is_protected_path(path):
            api_key = request.headers.get("X-API-Key")

            if not api_key:
                return JSONResponse(
                    status_code=401,
                    content={
                        "status": "error",
                        "error": "API 키가 필요합니다",
                        "detail": "X-API-Key 헤더를 설정하세요",
                        "path": path
                    }
                )

            # [C1] 서버 측 기대 키 미설정은 구성 오류
            if not get_api_key():
                return JSONResponse(
                    status_code=500,
                    content={
                        "status": "error",
                        "error": "서버 구성 오류",
                        "detail": "MARKETING_BOT_API_KEY 환경변수를 설정하세요",
                    }
                )

            if not verify_api_key(api_key):
                return JSONResponse(
                    status_code=403,
                    content={
                        "status": "error",
                        "error": "유효하지 않은 API 키",
                        "path": path
                    }
                )

        # 인증 통과 - 요청 처리
        response = await call_next(request)
        return response


def generate_api_key() -> str:
    """
    새로운 API 키 생성 (관리자용)

    Returns:
        32자 길이의 안전한 랜덤 키
    """
    return secrets.token_urlsafe(32)


# 편의를 위한 키 생성 스크립트
if __name__ == "__main__":
    new_key = generate_api_key()
    print(f"새 API 키가 생성되었습니다:")
    print(f"  {new_key}")
    print(f"\n환경변수로 설정:")
    print(f"  export MARKETING_BOT_API_KEY={new_key}")
    print(f"\n.env 파일에 추가:")
    print(f"  MARKETING_BOT_API_KEY={new_key}")
