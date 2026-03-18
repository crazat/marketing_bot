"""
Retry Helper
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 안정성 강화 - 지수 백오프 재시도 로직

네트워크 요청, 외부 API 호출에 대한 자동 재시도:
- 지수 백오프 (exponential backoff)
- 지터 (jitter) 추가로 thundering herd 방지
- 특정 예외만 재시도
- 로깅 통합
"""

import time
import random
import logging
from typing import TypeVar, Callable, Optional, Tuple, Type, Any
from functools import wraps
import asyncio

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryExhaustedError(Exception):
    """모든 재시도가 실패했을 때 발생하는 예외"""
    def __init__(self, message: str, last_exception: Exception = None):
        super().__init__(message)
        self.last_exception = last_exception


def retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
) -> Callable:
    """
    지수 백오프 재시도 데코레이터 (동기 함수용)

    Args:
        max_retries: 최대 재시도 횟수 (기본: 3)
        base_delay: 기본 대기 시간 (초, 기본: 1.0)
        max_delay: 최대 대기 시간 (초, 기본: 60.0)
        exponential_base: 지수 베이스 (기본: 2.0)
        jitter: 랜덤 지터 추가 여부 (기본: True)
        exceptions: 재시도할 예외 타입들 (기본: 모든 예외)
        on_retry: 재시도 시 호출할 콜백 (선택)

    Returns:
        데코레이터 함수

    Example:
        @retry_with_backoff(max_retries=3, base_delay=2)
        def fetch_data():
            return requests.get(url)

        @retry_with_backoff(
            max_retries=5,
            exceptions=(ConnectionError, TimeoutError)
        )
        def call_external_api():
            return api_client.request()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"❌ {func.__name__} 재시도 한도 초과 "
                            f"(시도: {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        raise RetryExhaustedError(
                            f"{func.__name__} 최대 재시도 횟수 초과",
                            last_exception=e
                        )

                    # 대기 시간 계산
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # 지터 추가 (0.5~1.5배 사이)
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"⚠️ {func.__name__} 재시도 "
                        f"({attempt + 1}/{max_retries + 1}) - "
                        f"{delay:.1f}초 후 재시도: {e}"
                    )

                    # 콜백 호출
                    if on_retry:
                        on_retry(e, attempt + 1)

                    time.sleep(delay)

            # 여기에 도달하면 안됨
            raise RetryExhaustedError(
                f"{func.__name__} 재시도 실패",
                last_exception=last_exception
            )

        return wrapper
    return decorator


def async_retry_with_backoff(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None
) -> Callable:
    """
    지수 백오프 재시도 데코레이터 (비동기 함수용)

    Args:
        (retry_with_backoff와 동일)

    Example:
        @async_retry_with_backoff(max_retries=3)
        async def fetch_async_data():
            async with aiohttp.ClientSession() as session:
                return await session.get(url)
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)

                except exceptions as e:
                    last_exception = e

                    if attempt == max_retries:
                        logger.error(
                            f"❌ {func.__name__} 재시도 한도 초과 "
                            f"(시도: {attempt + 1}/{max_retries + 1}): {e}"
                        )
                        raise RetryExhaustedError(
                            f"{func.__name__} 최대 재시도 횟수 초과",
                            last_exception=e
                        )

                    # 대기 시간 계산
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # 지터 추가
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"⚠️ {func.__name__} 재시도 "
                        f"({attempt + 1}/{max_retries + 1}) - "
                        f"{delay:.1f}초 후 재시도: {e}"
                    )

                    # 콜백 호출
                    if on_retry:
                        on_retry(e, attempt + 1)

                    await asyncio.sleep(delay)

            raise RetryExhaustedError(
                f"{func.__name__} 재시도 실패",
                last_exception=last_exception
            )

        return wrapper
    return decorator


class RetryContext:
    """
    재시도 컨텍스트 매니저

    with 문으로 사용할 때 유용합니다.

    Example:
        with RetryContext(max_retries=3) as retry:
            while retry.should_continue():
                try:
                    result = risky_operation()
                    break
                except Exception as e:
                    retry.handle_exception(e)
    """

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter
        self.attempt = 0
        self.last_exception = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def should_continue(self) -> bool:
        """재시도를 계속해야 하는지 확인"""
        return self.attempt <= self.max_retries

    def handle_exception(self, e: Exception) -> None:
        """
        예외 처리 및 대기

        Args:
            e: 발생한 예외

        Raises:
            RetryExhaustedError: 재시도 한도 초과 시
        """
        self.last_exception = e
        self.attempt += 1

        if self.attempt > self.max_retries:
            raise RetryExhaustedError(
                f"최대 재시도 횟수 초과",
                last_exception=e
            )

        # 대기 시간 계산
        delay = min(
            self.base_delay * (self.exponential_base ** (self.attempt - 1)),
            self.max_delay
        )

        if self.jitter:
            delay = delay * (0.5 + random.random())

        logger.warning(
            f"⚠️ 재시도 ({self.attempt}/{self.max_retries + 1}) - "
            f"{delay:.1f}초 후 재시도: {e}"
        )

        time.sleep(delay)


# 미리 설정된 재시도 데코레이터
# 네트워크 요청용 (더 공격적인 재시도)
network_retry = retry_with_backoff(
    max_retries=5,
    base_delay=1.0,
    max_delay=30.0,
    exceptions=(ConnectionError, TimeoutError, OSError)
)

# API 호출용 (보수적인 재시도)
api_retry = retry_with_backoff(
    max_retries=3,
    base_delay=2.0,
    max_delay=60.0
)

# 스크래핑용 (중간 수준)
scraping_retry = retry_with_backoff(
    max_retries=4,
    base_delay=1.5,
    max_delay=45.0
)
