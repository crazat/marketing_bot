"""
애플리케이션 설정 관리
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[안정성 개선] 하드코딩된 설정값을 중앙 관리
- 환경 변수 또는 .env 파일에서 로드 가능
- 기본값 제공으로 즉시 사용 가능
- 타입 안전성 보장
"""

import os
from pathlib import Path
from functools import lru_cache
from typing import Optional

# 프로젝트 루트 경로
PROJECT_ROOT = Path(__file__).parent.parent


class AppSettings:
    """
    애플리케이션 설정

    환경 변수로 오버라이드 가능 (접두사: APP_)
    예: APP_DB_TIMEOUT=60
    """

    def __init__(self):
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 데이터베이스 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.db_timeout: int = self._get_int('DB_TIMEOUT', 30)
        self.db_max_connections: int = self._get_int('DB_MAX_CONNECTIONS', 5)
        self.db_path: str = self._get_str(
            'DB_PATH',
            str(PROJECT_ROOT / 'db' / 'marketing_data.db')
        )

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 스레드 풀 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.thread_pool_workers: int = self._get_int('THREAD_POOL_WORKERS', 2)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 캐시 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.cache_ttl_seconds: int = self._get_int('CACHE_TTL_SECONDS', 3600)
        self.cache_max_size: int = self._get_int('CACHE_MAX_SIZE', 1000)
        self.cache_cleanup_threshold: int = self._get_int('CACHE_CLEANUP_THRESHOLD', 800)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 스크래퍼 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.scraper_max_browsers: int = self._get_int('SCRAPER_MAX_BROWSERS', 5)
        self.scraper_delay_seconds: float = self._get_float('SCRAPER_DELAY_SECONDS', 2.0)
        self.scraper_page_load_timeout: int = self._get_int('SCRAPER_PAGE_LOAD_TIMEOUT', 30)
        self.scraper_element_timeout: int = self._get_int('SCRAPER_ELEMENT_TIMEOUT', 10)
        self.scraper_engine: str = self._get_str('SCRAPER_ENGINE', 'selenium')  # 'selenium' or 'playwright'

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # API 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.api_rate_limit_per_minute: int = self._get_int('API_RATE_LIMIT_PER_MINUTE', 1000)
        self.api_timeout_seconds: int = self._get_int('API_TIMEOUT_SECONDS', 30)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 스케줄러 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.hud_refresh_interval: int = self._get_int('HUD_REFRESH_INTERVAL', 60)
        self.scheduler_check_interval: int = self._get_int('SCHEDULER_CHECK_INTERVAL', 60)
        self.scheduler_enabled: bool = self._get_bool('SCHEDULER_ENABLED', False)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 리드 스코어링 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.lead_hot_threshold: int = self._get_int('LEAD_HOT_THRESHOLD', 75)
        self.lead_warm_threshold: int = self._get_int('LEAD_WARM_THRESHOLD', 55)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 백업 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.backup_retention_days: int = self._get_int('BACKUP_RETENTION_DAYS', 30)
        self.backup_max_count: int = self._get_int('BACKUP_MAX_COUNT', 30)
        self.backup_warning_days: int = self._get_int('BACKUP_WARNING_DAYS', 3)
        self.backup_critical_days: int = self._get_int('BACKUP_CRITICAL_DAYS', 7)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 로깅 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.log_level: str = self._get_str('LOG_LEVEL', 'INFO')
        self.log_dir: str = self._get_str('LOG_DIR', str(PROJECT_ROOT / 'logs'))
        self.log_max_size_mb: int = self._get_int('LOG_MAX_SIZE_MB', 5)
        self.log_backup_count: int = self._get_int('LOG_BACKUP_COUNT', 5)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 재시도 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.retry_max_attempts: int = self._get_int('RETRY_MAX_ATTEMPTS', 3)
        self.retry_delay_seconds: float = self._get_float('RETRY_DELAY_SECONDS', 1.0)
        self.retry_backoff_factor: float = self._get_float('RETRY_BACKOFF_FACTOR', 2.0)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 서브프로세스 및 작업 타임아웃 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.subprocess_timeout: int = self._get_int('SUBPROCESS_TIMEOUT', 600)  # 10분
        self.ai_reply_timeout: int = self._get_int('AI_REPLY_TIMEOUT', 60)  # AI 응답 대기
        self.insight_task_timeout: int = self._get_int('INSIGHT_TASK_TIMEOUT', 300)  # 인사이트 작업

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # 병렬 처리 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.carrot_max_workers: int = self._get_int('CARROT_MAX_WORKERS', 3)
        self.insight_max_workers: int = self._get_int('INSIGHT_MAX_WORKERS', 3)

        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        # Sentry 에러 모니터링 설정
        # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        self.sentry_dsn: str = self._get_str('SENTRY_DSN', '')
        self.sentry_traces_sample_rate: float = self._get_float('SENTRY_TRACES_SAMPLE_RATE', 0.1)
        self.sentry_environment: str = self._get_str('SENTRY_ENVIRONMENT', 'production')

    def _get_str(self, key: str, default: str) -> str:
        """문자열 환경 변수 가져오기"""
        return os.environ.get(f'APP_{key}', default)

    def _get_int(self, key: str, default: int) -> int:
        """정수 환경 변수 가져오기"""
        value = os.environ.get(f'APP_{key}')
        if value is not None:
            try:
                return int(value)
            except ValueError:
                pass
        return default

    def _get_float(self, key: str, default: float) -> float:
        """실수 환경 변수 가져오기"""
        value = os.environ.get(f'APP_{key}')
        if value is not None:
            try:
                return float(value)
            except ValueError:
                pass
        return default

    def _get_bool(self, key: str, default: bool) -> bool:
        """불리언 환경 변수 가져오기"""
        value = os.environ.get(f'APP_{key}')
        if value is not None:
            return value.lower() in ('true', '1', 'yes', 'on')
        return default


@lru_cache()
def get_settings() -> AppSettings:
    """
    싱글톤 설정 인스턴스 반환

    사용법:
        from config.app_settings import get_settings
        settings = get_settings()
        print(settings.db_timeout)
    """
    return AppSettings()


# 편의를 위한 전역 인스턴스
settings = get_settings()
