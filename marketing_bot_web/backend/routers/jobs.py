"""
Jobs API — 스케줄 잡 실행 이력 조회.

services/job_runs.py 데코레이터가 기록한 데이터를 노출.
Dashboard Chronos Timeline에서 잡별 색상 (success/failed/skipped) 표시 용도.
"""

from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Query

from services.job_runs import recent_runs, job_summary

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/runs")
def get_runs(
    limit: int = Query(default=100, ge=1, le=500),
    job_name: Optional[str] = Query(default=None, description="필터: 특정 잡명만"),
) -> List[Dict[str, Any]]:
    """최근 실행 이력 (시간 역순)."""
    return recent_runs(limit=limit, job_name=job_name)


@router.get("/summary")
def get_summary() -> Dict[str, Dict[str, Any]]:
    """잡별 7일 요약 (last_status / avg_duration / n_success / n_failed).

    Dashboard에서 Chronos Timeline 위에 표시:
    - 마지막 status가 'failed' / 24h 내 미실행 → 빨강
    - n_failed > 0 / 7d → 주황
    - 정상 → 녹색
    """
    return job_summary()


@router.get("/ai-cost")
def get_ai_cost(days: int = Query(default=7, ge=1, le=90)) -> Dict[str, Any]:
    """일별/모델별 + caller_module별 AI 호출 비용 요약."""
    from services.ai_cost import daily_summary, caller_summary
    return {
        "summary": daily_summary(days=days),
        "by_caller": caller_summary(days=days),
    }


@router.get("/health")
def get_health() -> Dict[str, Any]:
    """잡 헬스 요약 — 단일 숫자/색깔로 Dashboard에 1줄 표시."""
    summary = job_summary()
    n_jobs = len(summary)
    n_failed = sum(1 for v in summary.values() if v.get("last_status") == "failed")
    n_skipped = sum(1 for v in summary.values() if v.get("last_status") == "skipped")
    severity = "ok"
    if n_failed > 0:
        severity = "critical" if n_failed >= 3 else "warning"
    elif n_skipped > 2:
        severity = "warning"
    return {
        "n_jobs": n_jobs,
        "n_failed": n_failed,
        "n_skipped": n_skipped,
        "severity": severity,
    }
