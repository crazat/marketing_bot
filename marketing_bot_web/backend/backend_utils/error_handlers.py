"""
공통 에러 처리 유틸리티
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모든 라우터에서 일관된 에러 처리를 위한 유틸리티
"""

from fastapi import HTTPException
from functools import wraps
from typing import Callable, TypeVar, Any
import traceback
import logging

# 로거 설정
logger = logging.getLogger(__name__)

T = TypeVar('T')


class APIError(HTTPException):
    """커스텀 API 에러"""
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: str | None = None
    ):
        super().__init__(status_code=status_code, detail=detail)
        self.error_code = error_code


class NotFoundError(APIError):
    """리소스를 찾을 수 없음"""
    def __init__(self, resource: str, identifier: Any = None):
        detail = f"{resource}을(를) 찾을 수 없습니다"
        if identifier:
            detail = f"{resource} '{identifier}'을(를) 찾을 수 없습니다"
        super().__init__(status_code=404, detail=detail, error_code="NOT_FOUND")


class ValidationError(APIError):
    """유효성 검사 실패"""
    def __init__(self, detail: str):
        super().__init__(status_code=400, detail=detail, error_code="VALIDATION_ERROR")


class DatabaseError(APIError):
    """데이터베이스 에러"""
    def __init__(self, detail: str = "데이터베이스 오류가 발생했습니다"):
        super().__init__(status_code=500, detail=detail, error_code="DATABASE_ERROR")


class ExternalServiceError(APIError):
    """외부 서비스 에러"""
    def __init__(self, service: str, detail: str | None = None):
        msg = f"{service} 서비스 연결에 실패했습니다"
        if detail:
            msg = f"{msg}: {detail}"
        super().__init__(status_code=503, detail=msg, error_code="EXTERNAL_SERVICE_ERROR")


def handle_exceptions(func: Callable[..., T]) -> Callable[..., T]:
    """
    라우터 함수의 예외를 처리하는 데코레이터

    사용법:
        @router.get("/items")
        @handle_exceptions
        async def get_items():
            ...
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except HTTPException:
            # FastAPI HTTPException은 그대로 전달
            raise
        except Exception as e:
            # 예상치 못한 에러 로깅
            logger.error(f"[{func.__name__}] Unexpected error: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500,
                detail=f"내부 서버 오류가 발생했습니다: {str(e)}"
            )
    return wrapper


def safe_db_operation(operation_name: str = "데이터베이스 작업"):
    """
    데이터베이스 작업을 안전하게 처리하는 데코레이터

    사용법:
        @safe_db_operation("키워드 조회")
        async def get_keywords():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"[{func.__name__}] Database error during {operation_name}: {str(e)}")
                logger.error(traceback.format_exc())
                raise DatabaseError(f"{operation_name} 중 오류가 발생했습니다: {str(e)}")
        return wrapper
    return decorator


def create_success_response(data: Any = None, message: str = "성공") -> dict:
    """성공 응답 생성"""
    response = {"status": "success", "message": message}
    if data is not None:
        response["data"] = data
    return response


def create_error_response(detail: str, error_code: str | None = None) -> dict:
    """에러 응답 생성"""
    response = {"status": "error", "detail": detail}
    if error_code:
        response["error_code"] = error_code
    return response


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [안정성 개선] 상세 에러 코드 및 사용자 친화적 메시지
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

from enum import Enum
from typing import Optional, Dict
from datetime import datetime


class ErrorSeverity(Enum):
    """에러 심각도"""
    LOW = "low"           # 경고만, 계속 진행 가능
    MEDIUM = "medium"     # 로깅 + 알림 필요
    HIGH = "high"         # 로깅 + 알림 + 재시도 필요
    CRITICAL = "critical" # 즉시 대응 필요


# 에러 코드별 사용자 친화적 메시지 및 힌트
ERROR_MESSAGES: Dict[str, Dict[str, str]] = {
    'DB_CONNECTION_FAILED': {
        'message': '데이터베이스 연결 실패',
        'hint': '서버를 재시작하거나 잠시 후 다시 시도해주세요.',
        'severity': 'high'
    },
    'DB_QUERY_FAILED': {
        'message': '데이터베이스 조회 오류',
        'hint': '데이터 형식을 확인하고 다시 시도해주세요.',
        'severity': 'medium'
    },
    'NAVER_API_LIMIT': {
        'message': 'Naver API 호출 한도 초과',
        'hint': '1시간 후 자동으로 복구됩니다. 급하시면 관리자에게 문의하세요.',
        'severity': 'medium'
    },
    'NAVER_API_ERROR': {
        'message': 'Naver API 오류',
        'hint': 'Naver 서비스가 일시적으로 불안정할 수 있습니다. 잠시 후 다시 시도해주세요.',
        'severity': 'medium'
    },
    'SCRAPER_BLOCKED': {
        'message': '스크래핑 일시 차단',
        'hint': '2-4시간 후 자동 해제됩니다. 다른 작업을 먼저 진행해주세요.',
        'severity': 'medium'
    },
    'NETWORK_ERROR': {
        'message': '네트워크 오류',
        'hint': '인터넷 연결을 확인하고 다시 시도해주세요.',
        'severity': 'high'
    },
    'GEMINI_API_ERROR': {
        'message': 'AI 서비스 오류',
        'hint': 'AI 서비스가 일시적으로 불안정합니다. 잠시 후 다시 시도해주세요.',
        'severity': 'medium'
    },
    'VALIDATION_ERROR': {
        'message': '입력값 오류',
        'hint': '입력 내용을 확인하고 다시 시도해주세요.',
        'severity': 'low'
    },
    'NOT_FOUND': {
        'message': '요청한 항목을 찾을 수 없습니다',
        'hint': '항목이 삭제되었거나 잘못된 요청일 수 있습니다.',
        'severity': 'low'
    },
    'RATE_LIMIT_EXCEEDED': {
        'message': '요청 한도 초과',
        'hint': '너무 많은 요청을 보내셨습니다. 잠시 후 다시 시도해주세요.',
        'severity': 'low'
    },
    'INTERNAL_SERVER_ERROR': {
        'message': '서버 내부 오류',
        'hint': '문제가 지속되면 관리자에게 문의해주세요.',
        'severity': 'critical'
    }
}


class AppError(Exception):
    """
    [안정성 개선] 애플리케이션 전용 에러 클래스
    - 에러 코드 기반 사용자 친화적 메시지
    - 심각도 분류
    - 컨텍스트 정보 포함
    """
    def __init__(
        self,
        code: str,
        message: Optional[str] = None,
        context: Optional[dict] = None,
        original_error: Optional[Exception] = None
    ):
        self.code = code
        self.context = context or {}
        self.original_error = original_error
        self.timestamp = datetime.now().isoformat()

        # 에러 코드에서 메시지 정보 가져오기
        error_info = ERROR_MESSAGES.get(code, ERROR_MESSAGES['INTERNAL_SERVER_ERROR'])
        self.user_message = message or error_info['message']
        self.hint = error_info['hint']
        self.severity = ErrorSeverity(error_info['severity'])

        super().__init__(self.user_message)

    def to_dict(self) -> dict:
        """에러 정보를 딕셔너리로 변환"""
        return {
            'code': self.code,
            'message': self.user_message,
            'hint': self.hint,
            'severity': self.severity.value,
            'timestamp': self.timestamp
        }

    def to_response(self) -> dict:
        """API 응답용 딕셔너리"""
        return {
            'status': 'error',
            'error': {
                'code': self.code,
                'message': self.user_message,
                'hint': self.hint
            },
            'timestamp': self.timestamp
        }


def handle_with_fallback(
    func: Callable[..., T],
    fallback_value: T,
    error_code: str = 'INTERNAL_SERVER_ERROR',
    log_error: bool = True
) -> Callable[..., T]:
    """
    [안정성 개선] Graceful Degradation 데코레이터
    - 에러 발생 시 폴백 값 반환
    - 서비스 중단 방지

    사용법:
        @handle_with_fallback(fallback_value=[], error_code='DB_QUERY_FAILED')
        async def get_items():
            ...
    """
    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            if log_error:
                logger.warning(
                    f"[{func.__name__}] Error (returning fallback): {str(e)}",
                    exc_info=True
                )
            return fallback_value
    return wrapper


from dataclasses import dataclass, field


@dataclass
class OperationResult:
    """
    [안정성 개선] 작업 결과 클래스 - 부분 실패 지원

    사용법:
        result = OperationResult(success=True, data=items)
        result.add_warning("일부 항목 스킵됨")
        result.add_error("ID 123 처리 실패")
        return result.to_dict()
    """
    success: bool = True
    data: Any = None
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    processed_count: int = 0
    failed_count: int = 0

    def add_warning(self, msg: str):
        """경고 추가 (작업은 계속 진행)"""
        self.warnings.append(msg)

    def add_error(self, msg: str):
        """에러 추가 (부분 실패)"""
        self.errors.append(msg)
        self.failed_count += 1

    def mark_processed(self, count: int = 1):
        """처리 완료 카운트 증가"""
        self.processed_count += count

    def finalize(self):
        """최종 상태 결정 - 에러가 있으면 부분 성공으로 표시"""
        if self.errors and self.processed_count == 0:
            self.success = False
        elif self.errors:
            # 부분 성공 - success는 True 유지하되 errors 포함
            pass

    def to_dict(self) -> Dict[str, Any]:
        """API 응답용 딕셔너리"""
        self.finalize()
        response = {
            'success': self.success,
            'data': self.data,
            'processed': self.processed_count,
            'failed': self.failed_count
        }
        if self.errors:
            response['errors'] = self.errors
        if self.warnings:
            response['warnings'] = self.warnings
        return response


def with_retry(
    max_attempts: int = 3,
    delay_seconds: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    [안정성 개선] 재시도 데코레이터
    - 일시적인 오류 시 자동 재시도
    - 지수 백오프 지원

    사용법:
        @with_retry(max_attempts=3, delay_seconds=1.0)
        async def fetch_data():
            ...
    """
    import asyncio

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            last_exception = None
            delay = delay_seconds

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        logger.warning(
                            f"[{func.__name__}] Attempt {attempt + 1}/{max_attempts} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"[{func.__name__}] All {max_attempts} attempts failed: {e}"
                        )

            raise last_exception

        return wrapper
    return decorator
