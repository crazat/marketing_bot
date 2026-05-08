"""API-key authentication helpers and middleware."""

from __future__ import annotations

import os
import secrets
from typing import Callable, List, Optional

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)

PROTECTED_PATHS = [
    "/api/export",
    "/api/backup",
    "/api/automation",
    "/api/scheduler",
    "/api/migration",
    "/api/preferences",
    "/api/config",
    "/api/hud/mission",
]

PUBLIC_PATHS = [
    "/api/health",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
    "/static",
    "/api/telegram/webhook",
    "/api/telegram/legacy/webhook",
    "/api/kakao/webhook",
    "/api/analytics/conversion/visit",
]

QUERY_TOKEN_STREAM_PATH_SUFFIXES = ("/progress/stream",)
QUERY_TOKEN_STREAM_PATHS = {"/api/agent/stream"}


def get_api_key() -> Optional[str]:
    """Load the configured API key from the environment."""
    return os.getenv("MARKETING_BOT_API_KEY")


def verify_api_key(api_key: str) -> bool:
    """Return True when the supplied API key matches the configured key."""
    expected_key = get_api_key()
    if not expected_key:
        return False
    return secrets.compare_digest(api_key, expected_key)


def api_auth_enabled() -> bool:
    """Return whether API-key auth should be enforced."""
    return os.getenv("DISABLE_API_AUTH", "false").lower() != "true"


def validate_api_key_value(api_key: Optional[str]) -> tuple[bool, int, str]:
    """Validate a supplied API key and return (ok, status, message)."""
    if not api_key:
        return False, 401, "API key is required"
    if not get_api_key():
        return False, 500, "MARKETING_BOT_API_KEY is not configured"
    if not verify_api_key(api_key):
        return False, 403, "Invalid API key"
    return True, 200, "ok"


def allows_query_api_key(path: str) -> bool:
    """Query-string API keys are only allowed where browser APIs cannot set headers."""
    return path in QUERY_TOKEN_STREAM_PATHS or any(
        path.endswith(suffix) for suffix in QUERY_TOKEN_STREAM_PATH_SUFFIXES
    )


async def get_api_key_header(
    api_key: Optional[str] = Depends(API_KEY_HEADER),
) -> Optional[str]:
    """Extract the API key header for FastAPI dependencies."""
    return api_key


def require_api_key(api_key: Optional[str] = Depends(get_api_key_header)) -> str:
    """FastAPI dependency that rejects requests without a valid API key."""
    ok, status_code, message = validate_api_key_value(api_key)
    if not ok:
        raise HTTPException(
            status_code=status_code,
            detail=message,
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return api_key


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Enforce API-key authentication for non-public API routes."""

    def __init__(
        self,
        app,
        protected_paths: List[str] = None,
        public_paths: List[str] = None,
        enabled: bool = True,
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
        return any(self._path_matches(path, protected) for protected in self.protected_paths)

    def _is_public_path(self, path: str) -> bool:
        return any(self._path_matches(path, public) for public in self.public_paths)

    def _requires_api_key(self, path: str, method: str) -> bool:
        return path == "/api" or path.startswith("/api/") or self._is_protected_path(path)

    async def dispatch(self, request: Request, call_next: Callable):
        if not self.enabled:
            return await call_next(request)

        path = request.url.path

        # CORS preflight requests cannot carry X-API-Key in browsers.
        if request.method.upper() == "OPTIONS":
            return await call_next(request)

        if self._is_public_path(path):
            return await call_next(request)

        if self._requires_api_key(path, request.method):
            api_key = request.headers.get("X-API-Key")
            if not api_key and allows_query_api_key(path):
                api_key = request.query_params.get("api_key")

            ok, status_code, message = validate_api_key_value(api_key)
            if not ok:
                return JSONResponse(
                    status_code=status_code,
                    content={
                        "status": "error",
                        "error": "API key validation failed",
                        "detail": message,
                        "path": path,
                    },
                )

        return await call_next(request)


def generate_api_key() -> str:
    """Generate a URL-safe API key for administrative setup."""
    return secrets.token_urlsafe(32)


if __name__ == "__main__":
    new_key = generate_api_key()
    print("New API key generated:")
    print(f"  {new_key}")
    print("\nSet it as an environment variable:")
    print(f"  MARKETING_BOT_API_KEY={new_key}")
