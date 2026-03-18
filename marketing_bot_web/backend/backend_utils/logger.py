"""
Backend Logger Utility
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3-4] 구조화된 로깅 시스템
- 모듈별 로거 생성
- JSON 형식 로깅 지원
- 요청 ID 추적
- 로그 로테이션
- 일관된 포맷 적용
"""

import logging
import logging.handlers
import sys
import json
import uuid
import contextvars
from pathlib import Path
from typing import Optional, Any, Dict
from datetime import datetime


# 로그 디렉토리 설정
LOG_DIR = Path(__file__).parent.parent.parent.parent / 'logs'
LOG_DIR.mkdir(parents=True, exist_ok=True)

# 요청 ID를 위한 Context Variable
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar('request_id', default='')


def get_request_id() -> str:
    """현재 요청 ID 조회"""
    return request_id_var.get()


def set_request_id(request_id: str = None) -> str:
    """요청 ID 설정 (없으면 새로 생성)"""
    if not request_id:
        request_id = str(uuid.uuid4())[:8]
    request_id_var.set(request_id)
    return request_id


class JsonFormatter(logging.Formatter):
    """JSON 형식 로그 포맷터"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": get_request_id() or None,
        }

        # 추가 필드 (extra로 전달된 데이터)
        if hasattr(record, 'extra_data'):
            log_data["data"] = record.extra_data

        # 에러 정보
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # 소스 위치
        if record.levelno >= logging.WARNING:
            log_data["source"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName
            }

        return json.dumps(log_data, ensure_ascii=False, default=str)


class StructuredLogger(logging.Logger):
    """구조화된 로깅을 지원하는 확장 Logger"""

    def _log_with_extra(self, level: int, msg: str, extra_data: Dict[str, Any] = None, **kwargs):
        """추가 데이터와 함께 로깅"""
        if extra_data:
            kwargs['extra'] = kwargs.get('extra', {})
            kwargs['extra']['extra_data'] = extra_data
        super().log(level, msg, **kwargs)

    def info_with_data(self, msg: str, data: Dict[str, Any] = None, **kwargs):
        """데이터와 함께 INFO 로깅"""
        self._log_with_extra(logging.INFO, msg, data, **kwargs)

    def error_with_data(self, msg: str, data: Dict[str, Any] = None, **kwargs):
        """데이터와 함께 ERROR 로깅"""
        self._log_with_extra(logging.ERROR, msg, data, **kwargs)

    def warning_with_data(self, msg: str, data: Dict[str, Any] = None, **kwargs):
        """데이터와 함께 WARNING 로깅"""
        self._log_with_extra(logging.WARNING, msg, data, **kwargs)


# 커스텀 Logger 클래스 등록
logging.setLoggerClass(StructuredLogger)


def get_logger(name: str, log_file: Optional[str] = None, json_format: bool = False) -> StructuredLogger:
    """
    모듈별 로거 생성

    Args:
        name: 로거 이름 (보통 __name__ 사용)
        log_file: 로그 파일명 (선택적)
        json_format: JSON 형식 로깅 사용 여부

    Returns:
        StructuredLogger 인스턴스

    Example:
        from backend_utils.logger import get_logger
        logger = get_logger(__name__)
        logger.info("작업 시작")
        logger.info_with_data("사용자 생성", {"user_id": 123, "email": "test@test.com"})
    """
    logger = logging.getLogger(name)

    # 이미 핸들러가 설정되어 있으면 재설정 방지
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 콘솔 핸들러
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)

    if json_format:
        console_handler.setFormatter(JsonFormatter())
    else:
        console_format = logging.Formatter(
            '%(asctime)s - [%(request_id)s] %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            defaults={'request_id': '-'}
        )
        console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # 파일 핸들러 (선택적, 로테이션 적용)
    if log_file:
        file_path = LOG_DIR / log_file
        # 10MB 단위로 로테이션, 최대 5개 백업 유지
        file_handler = logging.handlers.RotatingFileHandler(
            file_path,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(JsonFormatter())  # 파일은 항상 JSON
        logger.addHandler(file_handler)

    return logger


# 기본 백엔드 로거 (main.py 등에서 사용)
backend_logger = get_logger('backend')


# 라우터별 로거 생성 헬퍼
def get_router_logger(router_name: str) -> logging.Logger:
    """
    라우터용 로거 생성

    Args:
        router_name: 라우터 이름 (예: 'battle', 'leads')

    Returns:
        logging.Logger 인스턴스
    """
    return get_logger(f'backend.routers.{router_name}')


def get_service_logger(service_name: str) -> logging.Logger:
    """
    서비스용 로거 생성

    Args:
        service_name: 서비스 이름 (예: 'file_watcher', 'websocket')

    Returns:
        logging.Logger 인스턴스
    """
    return get_logger(f'backend.services.{service_name}')
