"""
스크래퍼 Sentry 초기화 헬퍼
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 A-1] subprocess로 실행되는 스크래퍼에서 Sentry 에러 모니터링 활성화

사용법:
    from scrapers.sentry_init import init_sentry
    init_sentry("scraper_naver_place")
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)


def init_sentry(module_name: str = "scraper") -> bool:
    """
    스크래퍼용 Sentry 초기화

    Args:
        module_name: 스크래퍼 모듈명 (태그로 사용)

    Returns:
        True if Sentry initialized, False otherwise
    """
    try:
        import sentry_sdk
    except ImportError:
        return False

    dsn = os.environ.get('APP_SENTRY_DSN', '')
    if not dsn:
        # config.json에서도 시도
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sys.path.insert(0, project_root)
            from config.app_settings import get_settings
            dsn = get_settings().sentry_dsn
        except Exception:
            pass

    if not dsn:
        return False

    sentry_sdk.init(
        dsn=dsn,
        traces_sample_rate=0.05,  # 스크래퍼는 낮은 트레이싱 비율
        environment=os.environ.get('APP_SENTRY_ENVIRONMENT', 'production'),
        release="marketing-bot@2.0.0",
        send_default_pii=False,
    )
    sentry_sdk.set_tag("module", module_name)
    logger.info(f"✅ Sentry 초기화 완료 (module: {module_name})")
    return True
