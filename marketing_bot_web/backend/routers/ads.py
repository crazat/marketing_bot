"""
Ads Management API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-3] 통합 광고 관리 API
"""

from fastapi import APIRouter, Query
from typing import Dict, Any
import sys
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from backend_utils.cache import cached

router = APIRouter()


@router.get("/summary")
@cached(ttl=300)
@handle_exceptions
async def get_ad_summary(
    days: int = Query(default=30, ge=7, le=365),
) -> Dict[str, Any]:
    """광고 키워드 및 경쟁 현황 요약"""
    from services.ad_manager import AdPerformanceTracker
    db = DatabaseManager()
    tracker = AdPerformanceTracker(db_path=db.db_path)
    return tracker.get_ad_summary(days=days)


@router.get("/roas-estimate")
@cached(ttl=600)
@handle_exceptions
async def get_roas_estimate(
    days: int = Query(default=30, ge=7, le=365),
) -> Dict[str, Any]:
    """ROAS 추정 (키워드 입찰가 × 예상 클릭수 기반)"""
    from services.ad_manager import AdPerformanceTracker
    db = DatabaseManager()
    tracker = AdPerformanceTracker(db_path=db.db_path)
    return tracker.calculate_roas_estimate(days=days)
