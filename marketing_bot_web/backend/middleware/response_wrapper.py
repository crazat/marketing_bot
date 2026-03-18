"""
Response Wrapper Middleware
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3-2] 응답 모델 표준화
- 모든 API 응답을 통일된 형식으로 래핑
- 기존 라우터 수정 없이 표준화 적용
"""

import json
from datetime import datetime
from typing import Callable
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware


class ResponseWrapperMiddleware(BaseHTTPMiddleware):
    """
    API 응답을 표준 형식으로 래핑하는 미들웨어

    표준 응답 형식:
    {
        "status": "success" | "error",
        "data": { ... },
        "timestamp": "2026-02-15T10:30:00"
    }
    """

    # 래핑하지 않을 경로 (정적 파일, 문서 등)
    SKIP_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/static",
        "/favicon.ico"
    ]

    # 이미 표준 형식인 경우 식별 키
    STANDARD_KEYS = {"status", "data", "timestamp"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 스킵할 경로 확인
        path = request.url.path
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            return await call_next(request)

        # 원본 응답 받기
        response = await call_next(request)

        # JSON 응답만 처리
        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type:
            return response

        # 응답 바디 읽기
        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        if not body:
            return response

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            return response

        # 이미 표준 형식인지 확인
        if isinstance(data, dict) and self._is_standard_format(data):
            # timestamp만 없으면 추가
            if "timestamp" not in data:
                data["timestamp"] = datetime.now().isoformat()
                return JSONResponse(
                    content=data,
                    status_code=response.status_code,
                    headers=dict(response.headers)
                )
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type="application/json"
            )

        # 표준 형식으로 래핑
        wrapped = self._wrap_response(data, response.status_code)

        return JSONResponse(
            content=wrapped,
            status_code=response.status_code,
            headers=dict(response.headers)
        )

    def _is_standard_format(self, data: dict) -> bool:
        """이미 표준 형식인지 확인"""
        # status 키가 있고 success/error 값인 경우
        if "status" in data and data["status"] in ("success", "error"):
            return True
        # success 키가 True/False인 경우 (일부 라우터에서 사용)
        if "success" in data and isinstance(data["success"], bool):
            return True
        return False

    def _wrap_response(self, data, status_code: int) -> dict:
        """응답을 표준 형식으로 래핑"""
        is_error = status_code >= 400

        if is_error:
            # 에러 응답
            error_msg = data.get("detail", str(data)) if isinstance(data, dict) else str(data)
            return {
                "status": "error",
                "error": error_msg,
                "data": None,
                "timestamp": datetime.now().isoformat()
            }
        else:
            # 성공 응답
            return {
                "status": "success",
                "data": data,
                "timestamp": datetime.now().isoformat()
            }


def create_response_wrapper_middleware():
    """미들웨어 인스턴스 생성"""
    return ResponseWrapperMiddleware
