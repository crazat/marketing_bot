"""
Predictive Analytics API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 D-2] 시계열 예측 분석 API
- 순위 예측, 리드 예측, 키워드 트렌드 예측
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional
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


def _get_forecaster():
    from services.predictive.forecaster import Forecaster
    db = DatabaseManager()
    return Forecaster(db_path=db.db_path)


@router.get("/rank")
@cached(ttl=600)
@handle_exceptions
async def forecast_rank(
    keyword: str = Query(..., description="예측할 키워드"),
    device_type: str = Query(default="mobile", description="mobile/desktop"),
    horizon: int = Query(default=14, ge=3, le=60, description="예측 기간 (일)"),
    lookback: int = Query(default=60, ge=14, le=365, description="학습 데이터 기간 (일)"),
) -> Dict[str, Any]:
    """
    키워드 순위 예측

    과거 순위 데이터를 기반으로 향후 N일간의 순위 추이를 예측합니다.
    """
    forecaster = _get_forecaster()
    return forecaster.forecast_rank(
        keyword=keyword,
        device_type=device_type,
        horizon=horizon,
        lookback_days=lookback,
    )


@router.get("/leads")
@cached(ttl=600)
@handle_exceptions
async def forecast_leads(
    horizon: int = Query(default=14, ge=3, le=60),
    lookback: int = Query(default=60, ge=14, le=365),
) -> Dict[str, Any]:
    """일별 리드 수 예측"""
    forecaster = _get_forecaster()
    return forecaster.forecast_leads(horizon=horizon, lookback_days=lookback)


@router.get("/keyword-trend")
@cached(ttl=600)
@handle_exceptions
async def forecast_keyword_trend(
    keyword: str = Query(..., description="예측할 키워드"),
    horizon: int = Query(default=30, ge=7, le=90),
) -> Dict[str, Any]:
    """DataLab 트렌드 기반 키워드 검색량 예측"""
    forecaster = _get_forecaster()
    return forecaster.forecast_keyword_trend(keyword=keyword, horizon=horizon)
