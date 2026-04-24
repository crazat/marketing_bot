"""
보안 헤더 미들웨어
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-4] Content-Security-Policy 및 보안 헤더 추가

OWASP 권장 보안 헤더:
- Content-Security-Policy (CSP)
- X-Content-Type-Options
- X-Frame-Options
- Referrer-Policy
- Permissions-Policy
"""

import secrets
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    보안 헤더 미들웨어

    API 엔드포인트와 정적 파일 서빙 모두에 보안 헤더 추가
    """

    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # API 엔드포인트에는 CSP 불필요 (JSON 응답)
        is_api = request.url.path.startswith("/api/")

        if not is_api:
            # HTML 응답용 CSP
            nonce = secrets.token_urlsafe(16)
            response.headers["Content-Security-Policy"] = (
                f"default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                f"style-src 'self' 'unsafe-inline'; "  # Tailwind 인라인 스타일 허용
                f"img-src 'self' data: blob: https:; "
                f"connect-src 'self' ws: wss: https://api.openweathermap.org; "
                f"font-src 'self'; "
                f"object-src 'none'; "
                f"base-uri 'self'; "
                f"frame-ancestors 'none'"
            )

        # 모든 응답에 적용되는 보안 헤더
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(self), payment=()"
        )
        response.headers["X-XSS-Protection"] = "0"  # 최신 브라우저는 CSP로 대체

        return response
