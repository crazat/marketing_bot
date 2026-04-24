"""
Health Check API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 3-1] 시스템 상태 모니터링 API
- 데이터베이스 연결 상태
- 디스크 용량
- 메모리 사용량
- 마지막 스캔 시간
- 외부 서비스 상태
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from datetime import datetime
import sqlite3
import os
import sys
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from backend_utils.performance import get_performance_monitor
from backend_utils.cache import get_cache_stats

router = APIRouter()

# 프로젝트 경로
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DB_PATH = PROJECT_ROOT / 'db' / 'marketing_data.db'
CONFIG_PATH = PROJECT_ROOT / 'config'


def check_database() -> Dict[str, Any]:
    """데이터베이스 상태 확인"""
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 무결성 검사
        cursor.execute("PRAGMA integrity_check")
        integrity = cursor.fetchone()[0]

        # 테이블 수
        cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
        table_count = cursor.fetchone()[0]

        # DB 파일 크기
        db_size_mb = os.path.getsize(db.db_path) / (1024 * 1024) if os.path.exists(db.db_path) else 0

        conn.close()

        return {
            "status": "healthy" if integrity == "ok" else "degraded",
            "integrity": integrity,
            "table_count": table_count,
            "size_mb": round(db_size_mb, 2),
            "path": str(db.db_path)
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }


def check_disk_space() -> Dict[str, Any]:
    """디스크 용량 확인"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(PROJECT_ROOT)

        free_gb = free / (1024 ** 3)
        total_gb = total / (1024 ** 3)
        used_percent = (used / total) * 100

        # 10GB 미만이면 경고
        status = "healthy" if free_gb > 10 else ("warning" if free_gb > 5 else "critical")

        return {
            "status": status,
            "total_gb": round(total_gb, 2),
            "free_gb": round(free_gb, 2),
            "used_percent": round(used_percent, 1)
        }
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }


def check_memory() -> Dict[str, Any]:
    """메모리 사용량 확인"""
    try:
        import psutil
        memory = psutil.virtual_memory()

        status = "healthy" if memory.percent < 80 else ("warning" if memory.percent < 90 else "critical")

        return {
            "status": status,
            "total_gb": round(memory.total / (1024 ** 3), 2),
            "available_gb": round(memory.available / (1024 ** 3), 2),
            "used_percent": memory.percent
        }
    except ImportError:
        return {
            "status": "unknown",
            "error": "psutil not installed"
        }
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }


def check_last_scans() -> Dict[str, Any]:
    """마지막 스캔 시간 확인"""
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        scans = {}

        # 순위 스캔
        cursor.execute("""
            SELECT MAX(scanned_at) FROM rank_history
        """)
        result = cursor.fetchone()
        scans["rank_scan"] = result[0] if result and result[0] else None

        # Pathfinder 스캔
        cursor.execute("""
            SELECT MAX(created_at) FROM keyword_insights
        """)
        result = cursor.fetchone()
        scans["pathfinder_scan"] = result[0] if result and result[0] else None

        # 바이럴 스캔
        cursor.execute("""
            SELECT MAX(created_at) FROM viral_targets
        """)
        result = cursor.fetchone()
        scans["viral_scan"] = result[0] if result and result[0] else None

        conn.close()

        return {
            "status": "healthy",
            "scans": scans
        }
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }


def check_config_files() -> Dict[str, Any]:
    """설정 파일 상태 확인"""
    required_files = [
        "config.json",
        "keywords.json",
        "business_profile.json",
        "schedule.json"
    ]

    results = {}
    missing = []

    for filename in required_files:
        filepath = CONFIG_PATH / filename
        if filepath.exists():
            results[filename] = {
                "exists": True,
                "size_kb": round(os.path.getsize(filepath) / 1024, 1)
            }
        else:
            results[filename] = {"exists": False}
            missing.append(filename)

    return {
        "status": "healthy" if not missing else "warning",
        "files": results,
        "missing": missing
    }


def check_external_services() -> Dict[str, Any]:
    """외부 서비스 연결 상태 확인 (API 키 존재 여부만)"""
    try:
        from utils import ConfigManager
        config = ConfigManager()

        services = {}

        # Gemini API
        gemini_key = config.get_api_key("gemini")
        services["gemini"] = {
            "configured": bool(gemini_key),
            "status": "configured" if gemini_key else "not_configured"
        }

        # Naver API
        naver_client_id = config.get_api_key("naver_client_id")
        naver_secret = config.get_api_key("naver_client_secret")
        services["naver"] = {
            "configured": bool(naver_client_id and naver_secret),
            "status": "configured" if (naver_client_id and naver_secret) else "not_configured"
        }

        return {
            "status": "healthy",
            "services": services
        }
    except Exception as e:
        return {
            "status": "unknown",
            "error": str(e)
        }


@router.get("")
@router.get("/")
@handle_exceptions
async def health_check() -> Dict[str, Any]:
    """
    시스템 전체 상태 확인 (간략)

    Returns:
        - status: overall | healthy | degraded | unhealthy
        - timestamp: 확인 시간
        - checks: 각 항목별 상태
    """
    checks = {
        "database": check_database(),
        "disk": check_disk_space(),
        "config": check_config_files(),
        "last_scans": check_last_scans()
    }

    # 전체 상태 결정
    statuses = [c.get("status", "unknown") for c in checks.values()]

    if "unhealthy" in statuses or "critical" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses or "warning" in statuses:
        overall = "degraded"
    elif all(s in ["healthy", "unknown"] for s in statuses):
        overall = "healthy"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "checks": checks
    }


@router.get("/detailed")
@handle_exceptions
async def detailed_health_check() -> Dict[str, Any]:
    """
    시스템 상세 상태 확인

    Returns:
        - 기본 헬스체크 + 메모리, 외부 서비스 상태
    """
    checks = {
        "database": check_database(),
        "disk": check_disk_space(),
        "memory": check_memory(),
        "config": check_config_files(),
        "last_scans": check_last_scans(),
        "external_services": check_external_services()
    }

    # 전체 상태 결정
    statuses = [c.get("status", "unknown") for c in checks.values()]

    if "unhealthy" in statuses or "critical" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses or "warning" in statuses:
        overall = "degraded"
    elif all(s in ["healthy", "unknown", "configured", "not_configured"] for s in statuses):
        overall = "healthy"
    else:
        overall = "unknown"

    return {
        "status": overall,
        "timestamp": datetime.now().isoformat(),
        "version": "1.0.0",
        "checks": checks
    }


@router.get("/db")
@handle_exceptions
async def database_health() -> Dict[str, Any]:
    """데이터베이스 상태만 확인"""
    return check_database()


@router.get("/ready")
@handle_exceptions
async def readiness_check() -> Dict[str, Any]:
    """
    서비스 준비 상태 확인 (Kubernetes readiness probe용)

    Returns:
        - ready: True/False
        - checks: 필수 항목 상태
    """
    db_check = check_database()
    config_check = check_config_files()

    ready = (
        db_check.get("status") == "healthy" and
        config_check.get("status") in ["healthy", "warning"]
    )

    return {
        "ready": ready,
        "checks": {
            "database": db_check.get("status"),
            "config": config_check.get("status")
        }
    }


@router.get("/live")
@handle_exceptions
async def liveness_check() -> Dict[str, Any]:
    """
    서비스 생존 상태 확인 (Kubernetes liveness probe용)

    Returns:
        - alive: True
        - timestamp: 확인 시간
    """
    return {
        "alive": True,
        "timestamp": datetime.now().isoformat()
    }


@router.get("/scraper-health")
@handle_exceptions
async def scraper_health_check(
    scraper: str = None,
) -> Dict[str, Any]:
    """
    [고도화 V3-2] 스크래퍼 헬스 모니터

    전체 스크래퍼 건강 상태 + 이상 감지 결과.
    scraper 파라미터로 특정 스크래퍼만 조회 가능.
    """
    try:
        from services.scraper_health import ScraperHealthMonitor
        from db.database import DatabaseManager

        db = DatabaseManager()
        monitor = ScraperHealthMonitor(db.db_path)

        if scraper:
            return monitor.check_health(scraper_name=scraper)
        else:
            return monitor.get_dashboard_summary()

    except Exception as e:
        return {"overall": "error", "detail": str(e)}


@router.get("/performance")
@handle_exceptions
async def performance_stats() -> Dict[str, Any]:
    """
    API 성능 통계 조회

    Returns:
        - api_stats: API 엔드포인트별 응답 시간 통계
        - cache_stats: 캐시 히트율 및 상태
        - slow_endpoints: 느린 엔드포인트 목록
    """
    monitor = get_performance_monitor()

    return {
        "timestamp": datetime.now().isoformat(),
        "api_stats": monitor.get_stats(),
        "slow_endpoints": monitor.get_slow_endpoints(),
        "cache_stats": get_cache_stats()
    }
