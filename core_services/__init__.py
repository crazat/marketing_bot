"""
Services Package
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

핵심 서비스 모듈:
- secret_manager: API 키 관리
- sql_builder: SQL 인젝션 방지
- db_pool: DB 연결 풀링
- retry_helper: 재시도 로직
- query_optimizer: N+1 쿼리 최적화
- deduplicator: 중복 제거
- trend_detector: 트렌드 감지
"""

from .secret_manager import get_secret_manager, get_secret, SecretNotFoundError
from .sql_builder import (
    validate_table_name,
    validate_column_name,
    get_table_columns,
    build_select_query,
    SQLInjectionError
)
from .db_pool import get_db_pool, DatabasePool, DatabaseConnectionError
from .retry_helper import (
    retry_with_backoff,
    async_retry_with_backoff,
    RetryExhaustedError,
    network_retry,
    api_retry,
    scraping_retry
)
from .query_optimizer import get_query_optimizer, QueryOptimizer

__all__ = [
    # secret_manager
    'get_secret_manager',
    'get_secret',
    'SecretNotFoundError',

    # sql_builder
    'validate_table_name',
    'validate_column_name',
    'get_table_columns',
    'build_select_query',
    'SQLInjectionError',

    # db_pool
    'get_db_pool',
    'DatabasePool',
    'DatabaseConnectionError',

    # retry_helper
    'retry_with_backoff',
    'async_retry_with_backoff',
    'RetryExhaustedError',
    'network_retry',
    'api_retry',
    'scraping_retry',

    # query_optimizer
    'get_query_optimizer',
    'QueryOptimizer',
]
