"""
Request ID Middleware
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3-4] 요청 ID 추적 미들웨어
- 각 요청에 고유 ID 부여
- 로그 추적 및 디버깅 용이
"""

import uuid
import time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend_utils.logger import set_request_id, get_request_id, get_logger

logger = get_logger(__name__)


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    요청 ID 미들웨어

    각 요청에 고유한 ID를 부여하여:
    - 로그 추적 용이
    - 디버깅 시 요청 흐름 파악
    - 응답 헤더에 X-Request-ID 포함
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 요청 ID 설정 (기존 헤더에 있으면 사용, 없으면 생성)
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())[:8]

        # Context에 요청 ID 설정
        set_request_id(request_id)

        # 요청 시작 시간
        start_time = time.time()

        # 요청 로깅
        logger.debug(
            f"Request started: {request.method} {request.url.path}",
            extra={'extra_data': {
                'method': request.method,
                'path': request.url.path,
                'query': str(request.query_params),
                'client_ip': self._get_client_ip(request)
            }}
        )

        # 요청 처리
        response = await call_next(request)

        # 응답 시간 계산
        process_time = time.time() - start_time

        # 응답 헤더에 요청 ID 및 처리 시간 추가
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Process-Time"] = f"{process_time:.4f}"

        # 응답 로깅
        log_level = logger.warning if response.status_code >= 400 else logger.debug
        log_level(
            f"Request completed: {request.method} {request.url.path} - {response.status_code}",
            extra={'extra_data': {
                'method': request.method,
                'path': request.url.path,
                'status_code': response.status_code,
                'process_time_ms': round(process_time * 1000, 2)
            }}
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 추출"""
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"
