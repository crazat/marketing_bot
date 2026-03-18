"""
Error Handler Utility
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

보안을 위한 에러 처리 유틸리티
- 클라이언트에 스택트레이스 노출 방지
- 내부 로깅 유지
"""

import traceback
from typing import Optional
from fastapi import HTTPException


# 사용자에게 보여줄 일반적인 에러 메시지
DEFAULT_ERROR_MESSAGES = {
    400: "잘못된 요청입니다.",
    401: "인증이 필요합니다.",
    403: "접근 권한이 없습니다.",
    404: "요청한 리소스를 찾을 수 없습니다.",
    500: "서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.",
    502: "서버가 응답하지 않습니다.",
    503: "서비스를 일시적으로 사용할 수 없습니다.",
}


def log_error(context: str, error: Exception, print_traceback: bool = True) -> None:
    """
    에러를 서버 로그에 기록

    Args:
        context: 에러 발생 컨텍스트 (함수명, API 경로 등)
        error: 발생한 예외
        print_traceback: 스택트레이스 출력 여부
    """
    print(f"[ERROR] {context}: {str(error)}")
    if print_traceback:
        traceback.print_exc()


def raise_safe_http_error(
    status_code: int = 500,
    context: str = "",
    error: Optional[Exception] = None,
    user_message: Optional[str] = None,
    log_traceback: bool = True
) -> None:
    """
    안전한 HTTP 에러 발생
    - 클라이언트에는 일반적인 메시지만 반환
    - 서버 로그에는 상세 정보 기록

    Args:
        status_code: HTTP 상태 코드
        context: 에러 발생 컨텍스트
        error: 발생한 예외 (로깅용)
        user_message: 사용자에게 보여줄 커스텀 메시지
        log_traceback: 스택트레이스 로깅 여부

    Raises:
        HTTPException: 안전한 에러 메시지가 포함된 HTTP 예외
    """
    # 서버 로그에 상세 정보 기록
    if error:
        log_error(context, error, log_traceback)

    # 사용자에게 보여줄 메시지 결정
    detail = user_message or DEFAULT_ERROR_MESSAGES.get(
        status_code,
        DEFAULT_ERROR_MESSAGES[500]
    )

    raise HTTPException(status_code=status_code, detail=detail)


def handle_db_error(context: str, error: Exception) -> None:
    """
    데이터베이스 에러 처리

    Args:
        context: 에러 발생 컨텍스트
        error: 발생한 예외

    Raises:
        HTTPException: 데이터베이스 에러 메시지가 포함된 HTTP 예외
    """
    raise_safe_http_error(
        status_code=500,
        context=f"[DB] {context}",
        error=error,
        user_message="데이터베이스 오류가 발생했습니다."
    )


def handle_api_error(context: str, error: Exception) -> None:
    """
    외부 API 에러 처리

    Args:
        context: 에러 발생 컨텍스트
        error: 발생한 예외

    Raises:
        HTTPException: API 에러 메시지가 포함된 HTTP 예외
    """
    raise_safe_http_error(
        status_code=502,
        context=f"[API] {context}",
        error=error,
        user_message="외부 서비스 연동 중 오류가 발생했습니다."
    )


def handle_validation_error(context: str, message: str) -> None:
    """
    입력 검증 에러 처리

    Args:
        context: 에러 발생 컨텍스트
        message: 검증 실패 메시지 (사용자에게 표시됨)

    Raises:
        HTTPException: 검증 에러 메시지가 포함된 HTTP 예외
    """
    print(f"[VALIDATION] {context}: {message}")
    raise HTTPException(status_code=400, detail=message)
