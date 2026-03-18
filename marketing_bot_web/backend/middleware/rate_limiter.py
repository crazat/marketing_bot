"""
Rate Limiter Middleware
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3-3] API 요청 제한
- IP 기반 요청 제한
- 엔드포인트별 제한 설정
- 슬라이딩 윈도우 알고리즘
"""

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Callable, Optional
from fastapi import Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import threading


@dataclass
class RateLimitRule:
    """Rate limit 규칙"""
    requests: int  # 허용 요청 수
    window: int    # 시간 윈도우 (초)


@dataclass
class RequestRecord:
    """요청 기록"""
    timestamps: list = field(default_factory=list)


class RateLimiter:
    """
    슬라이딩 윈도우 기반 Rate Limiter

    사용법:
        limiter = RateLimiter()
        limiter.set_rule("/api/scrape", RateLimitRule(requests=5, window=60))  # 분당 5회

        if not limiter.is_allowed("192.168.1.1", "/api/scrape"):
            raise HTTPException(429, "Too many requests")
    """

    def __init__(self):
        # IP별 요청 기록: {ip: {path: RequestRecord}}
        self._records: Dict[str, Dict[str, RequestRecord]] = defaultdict(
            lambda: defaultdict(RequestRecord)
        )
        # 경로별 규칙
        self._rules: Dict[str, RateLimitRule] = {}
        # 기본 규칙
        self._default_rule = RateLimitRule(requests=100, window=60)  # 분당 100회
        # 스레드 안전성
        self._lock = threading.Lock()

    def set_rule(self, path_prefix: str, rule: RateLimitRule):
        """특정 경로에 대한 규칙 설정"""
        self._rules[path_prefix] = rule

    def set_default_rule(self, rule: RateLimitRule):
        """기본 규칙 설정"""
        self._default_rule = rule

    def get_rule(self, path: str) -> RateLimitRule:
        """경로에 해당하는 규칙 조회"""
        # 가장 긴 매칭 접두사 찾기
        matching_rules = [
            (prefix, rule)
            for prefix, rule in self._rules.items()
            if path.startswith(prefix)
        ]

        if matching_rules:
            # 가장 긴 접두사 우선
            matching_rules.sort(key=lambda x: len(x[0]), reverse=True)
            return matching_rules[0][1]

        return self._default_rule

    def is_allowed(self, client_ip: str, path: str) -> tuple[bool, dict]:
        """
        요청 허용 여부 확인

        Returns:
            (is_allowed, rate_limit_info)
        """
        rule = self.get_rule(path)
        now = time.time()
        window_start = now - rule.window

        with self._lock:
            record = self._records[client_ip][path]

            # 윈도우 내 요청만 유지
            record.timestamps = [
                ts for ts in record.timestamps
                if ts > window_start
            ]

            current_count = len(record.timestamps)
            remaining = max(0, rule.requests - current_count)

            info = {
                "limit": rule.requests,
                "remaining": remaining,
                "reset": int(window_start + rule.window),
                "window": rule.window
            }

            if current_count >= rule.requests:
                return False, info

            # 요청 기록
            record.timestamps.append(now)
            info["remaining"] = remaining - 1

            return True, info

    def cleanup(self, max_age: int = 3600):
        """오래된 기록 정리"""
        now = time.time()
        cutoff = now - max_age

        with self._lock:
            ips_to_remove = []

            for ip, paths in self._records.items():
                paths_to_remove = []

                for path, record in paths.items():
                    record.timestamps = [
                        ts for ts in record.timestamps
                        if ts > cutoff
                    ]
                    if not record.timestamps:
                        paths_to_remove.append(path)

                for path in paths_to_remove:
                    del paths[path]

                if not paths:
                    ips_to_remove.append(ip)

            for ip in ips_to_remove:
                del self._records[ip]


# 전역 Rate Limiter 인스턴스
rate_limiter = RateLimiter()


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Rate Limiting 미들웨어

    사용법:
        from middleware.rate_limiter import RateLimiterMiddleware, rate_limiter, RateLimitRule

        # 규칙 설정
        rate_limiter.set_rule("/api/scrape", RateLimitRule(requests=5, window=60))

        # 미들웨어 등록
        app.add_middleware(RateLimiterMiddleware)
    """

    # Rate limit을 적용하지 않을 경로
    SKIP_PATHS = [
        "/docs",
        "/redoc",
        "/openapi.json",
        "/static",
        "/api/health"  # 헬스체크는 제한 없음
    ]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 스킵할 경로 확인
        path = request.url.path
        if any(path.startswith(skip) for skip in self.SKIP_PATHS):
            return await call_next(request)

        # 클라이언트 IP 추출
        client_ip = self._get_client_ip(request)

        # Rate limit 확인
        is_allowed, info = rate_limiter.is_allowed(client_ip, path)

        if not is_allowed:
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "error": "요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요.",
                    "rate_limit": info
                },
                headers={
                    "X-RateLimit-Limit": str(info["limit"]),
                    "X-RateLimit-Remaining": str(info["remaining"]),
                    "X-RateLimit-Reset": str(info["reset"]),
                    "Retry-After": str(info["window"])
                }
            )

        # 요청 처리
        response = await call_next(request)

        # Rate limit 헤더 추가
        response.headers["X-RateLimit-Limit"] = str(info["limit"])
        response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
        response.headers["X-RateLimit-Reset"] = str(info["reset"])

        return response

    def _get_client_ip(self, request: Request) -> str:
        """클라이언트 IP 추출"""
        # 프록시 뒤에 있는 경우
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # 직접 연결
        if request.client:
            return request.client.host

        return "unknown"


def configure_rate_limits():
    """
    Rate limit 규칙 설정

    이 함수는 앱 시작 시 호출하여 규칙을 설정합니다.
    """
    # 스크래핑 관련 - 엄격한 제한
    rate_limiter.set_rule("/api/battle/scan", RateLimitRule(requests=3, window=60))
    rate_limiter.set_rule("/api/pathfinder/scan", RateLimitRule(requests=3, window=60))
    rate_limiter.set_rule("/api/viral/scan", RateLimitRule(requests=3, window=60))
    rate_limiter.set_rule("/api/competitors/scan", RateLimitRule(requests=3, window=60))

    # AI 분석 - 중간 제한
    rate_limiter.set_rule("/api/intelligence", RateLimitRule(requests=20, window=60))
    rate_limiter.set_rule("/api/reviews/generate", RateLimitRule(requests=10, window=60))

    # 일반 API - 관대한 제한
    rate_limiter.set_rule("/api/", RateLimitRule(requests=100, window=60))

    # 기본 규칙
    rate_limiter.set_default_rule(RateLimitRule(requests=200, window=60))
