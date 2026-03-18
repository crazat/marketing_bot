"""
Unified API Response Schemas
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 코드 품질 개선 - 통일된 API 응답 형식
[Phase 3-2] 응답 모델 표준화 강화

모든 API가 일관된 형식으로 응답:
- status: "success" | "error"
- data: 실제 데이터 (성공 시)
- error: 에러 메시지 (실패 시)
- meta: 페이지네이션 등 메타데이터

사용법:
    from schemas.response import success_response, error_response, paginated_response

    # 성공 응답
    return success_response({"items": items})

    # 에러 응답
    return error_response("리소스를 찾을 수 없습니다", code="NOT_FOUND")

    # 페이지네이션 응답
    return paginated_response(items, total=100, page=1, per_page=20)
"""

from typing import TypeVar, Generic, Optional, List, Any, Dict
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class ResponseStatus(str, Enum):
    """응답 상태"""
    SUCCESS = "success"
    ERROR = "error"


T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """
    통일된 API 응답 스키마

    모든 API 엔드포인트에서 이 형식을 사용합니다.

    Examples:
        성공 응답:
        {
            "status": "success",
            "data": { ... },
            "error": null,
            "timestamp": "2026-02-09T10:30:00"
        }

        에러 응답:
        {
            "status": "error",
            "data": null,
            "error": "리소스를 찾을 수 없습니다",
            "timestamp": "2026-02-09T10:30:00"
        }
    """
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Optional[T] = None
    error: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    @classmethod
    def success(cls, data: T) -> 'ApiResponse[T]':
        """성공 응답 생성"""
        return cls(status=ResponseStatus.SUCCESS, data=data)

    @classmethod
    def fail(cls, error: str) -> 'ApiResponse[T]':
        """실패 응답 생성"""
        return cls(status=ResponseStatus.ERROR, error=error)


class PaginationMeta(BaseModel):
    """페이지네이션 메타데이터"""
    total: int = Field(description="전체 아이템 수")
    page: int = Field(description="현재 페이지 (1부터 시작)")
    per_page: int = Field(description="페이지당 아이템 수")
    total_pages: int = Field(description="전체 페이지 수")
    has_next: bool = Field(description="다음 페이지 존재 여부")
    has_prev: bool = Field(description="이전 페이지 존재 여부")

    @classmethod
    def create(cls, total: int, page: int, per_page: int) -> 'PaginationMeta':
        """페이지네이션 메타 생성"""
        total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
        return cls(
            total=total,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1
        )


class PaginatedResponse(BaseModel, Generic[T]):
    """
    페이지네이션이 포함된 응답 스키마

    Examples:
        {
            "status": "success",
            "data": [ ... ],
            "meta": {
                "total": 150,
                "page": 1,
                "per_page": 20,
                "total_pages": 8,
                "has_next": true,
                "has_prev": false
            },
            "timestamp": "2026-02-09T10:30:00"
        }
    """
    status: ResponseStatus = ResponseStatus.SUCCESS
    data: Optional[List[T]] = None
    error: Optional[str] = None
    meta: Optional[PaginationMeta] = None
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    @classmethod
    def success(
        cls,
        data: List[T],
        total: int,
        page: int = 1,
        per_page: int = 20
    ) -> 'PaginatedResponse[T]':
        """페이지네이션 성공 응답 생성"""
        return cls(
            status=ResponseStatus.SUCCESS,
            data=data,
            meta=PaginationMeta.create(total, page, per_page)
        )

    @classmethod
    def fail(cls, error: str) -> 'PaginatedResponse[T]':
        """페이지네이션 실패 응답 생성"""
        return cls(status=ResponseStatus.ERROR, error=error)


class ErrorDetail(BaseModel):
    """상세 에러 정보"""
    code: str = Field(description="에러 코드")
    message: str = Field(description="에러 메시지")
    field: Optional[str] = Field(None, description="문제가 발생한 필드")
    details: Optional[Dict[str, Any]] = Field(None, description="추가 상세 정보")


class ErrorResponse(BaseModel):
    """
    에러 응답 스키마 (상세 에러 정보 포함)

    Examples:
        {
            "status": "error",
            "error": "유효성 검사 실패",
            "errors": [
                {
                    "code": "INVALID_EMAIL",
                    "message": "올바른 이메일 형식이 아닙니다",
                    "field": "email"
                }
            ],
            "timestamp": "2026-02-09T10:30:00"
        }
    """
    status: ResponseStatus = ResponseStatus.ERROR
    error: str = Field(description="주요 에러 메시지")
    errors: Optional[List[ErrorDetail]] = Field(None, description="상세 에러 목록")
    timestamp: datetime = Field(default_factory=datetime.now)

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

    @classmethod
    def create(
        cls,
        message: str,
        errors: List[ErrorDetail] = None
    ) -> 'ErrorResponse':
        """에러 응답 생성"""
        return cls(error=message, errors=errors)

    @classmethod
    def validation_error(
        cls,
        field: str,
        message: str,
        code: str = "VALIDATION_ERROR"
    ) -> 'ErrorResponse':
        """유효성 검사 에러 응답 생성"""
        return cls(
            error="유효성 검사 실패",
            errors=[ErrorDetail(code=code, message=message, field=field)]
        )

    @classmethod
    def not_found(cls, resource: str) -> 'ErrorResponse':
        """리소스 없음 에러 응답 생성"""
        return cls(
            error=f"{resource}을(를) 찾을 수 없습니다",
            errors=[ErrorDetail(code="NOT_FOUND", message=f"{resource} not found")]
        )


# 편의를 위한 헬퍼 함수
def success_response(data: Any) -> Dict[str, Any]:
    """
    성공 응답 딕셔너리 생성 (기존 코드 호환용)

    사용법:
        return success_response({"keywords": keywords})
    """
    return {
        "status": "success",
        "data": data,
        "timestamp": datetime.now().isoformat()
    }


def error_response(message: str, code: str = None) -> Dict[str, Any]:
    """
    에러 응답 딕셔너리 생성 (기존 코드 호환용)

    [성능 최적화] success_response와 구조 통일을 위해 data: null 추가
    → 프론트엔드에서 일관된 응답 파싱 가능

    사용법:
        return error_response("리소스를 찾을 수 없습니다")
    """
    result = {
        "status": "error",
        "data": None,  # success_response와 구조 통일
        "error": message,
        "timestamp": datetime.now().isoformat()
    }
    if code:
        result["code"] = code
    return result


def paginated_response(
    data: List[Any],
    total: int,
    page: int = 1,
    per_page: int = 20
) -> Dict[str, Any]:
    """
    페이지네이션 응답 딕셔너리 생성 (기존 코드 호환용)

    사용법:
        return paginated_response(items, total=100, page=1, per_page=20)
    """
    total_pages = (total + per_page - 1) // per_page if per_page > 0 else 0
    return {
        "status": "success",
        "data": data,
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1
        },
        "timestamp": datetime.now().isoformat()
    }
