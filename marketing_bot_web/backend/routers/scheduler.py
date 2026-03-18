"""
Scheduler API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4] 스케줄러 상태 및 제어 API
- /api/scheduler/health: 스케줄러 건강도
- /api/scheduler/apply-recommendations: 권장사항 적용
- /api/scheduler/peak-hours: 피크 시간대 분석
- /api/scheduler/keyword-priorities: 키워드 우선순위 조회
- /api/scheduler/auto-rescan: 자동 재스캔 상태
- /api/scheduler/lead-reminders: Hot Lead 재알림 상태
- /api/scheduler/lead-transitions: 리드 상태 전이 실행
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path

# 상위 디렉토리를 path에 추가
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class KeywordPriorityRequest(BaseModel):
    keyword: str
    priority: str  # critical, high, medium, low


class TransitionRunRequest(BaseModel):
    dry_run: bool = True


# =============================================================================
# Adaptive Scheduler API
# =============================================================================

@router.get("/health")
@handle_exceptions
async def get_scheduler_health() -> Dict[str, Any]:
    """
    스케줄러 건강도 조회

    Returns:
        - summary: 전체 요약 (총 작업 수, 성공률 등)
        - jobs: 작업별 상세 정보
        - recommendations: 권장 조치사항
        - health_counts: 상태별 작업 수
    """
    try:
        from core.adaptive_scheduler import get_adaptive_scheduler_extended

        scheduler = get_adaptive_scheduler_extended()
        data = scheduler.get_extended_dashboard_data()

        return {
            "success": True,
            "data": data
        }

    except ImportError:
        # 기본 스케줄러 사용
        from core.adaptive_scheduler import get_adaptive_scheduler

        scheduler = get_adaptive_scheduler()
        data = scheduler.get_dashboard_data()

        return {
            "success": True,
            "data": data
        }


@router.post("/apply-recommendations")
@handle_exceptions
async def apply_recommendations() -> Dict[str, Any]:
    """
    권장사항 자동 적용

    auto_apply=True인 권장사항을 적용합니다.

    Returns:
        - applied: 적용된 권장사항 목록
        - skipped: 건너뛴 권장사항 목록
        - errors: 오류 목록
    """
    try:
        from core.adaptive_scheduler import get_adaptive_scheduler_extended

        scheduler = get_adaptive_scheduler_extended()
        result = scheduler.apply_auto_adjustments()

        return {
            "success": True,
            "data": result
        }

    except ImportError:
        raise HTTPException(
            status_code=501,
            detail="Extended scheduler not available"
        )


@router.get("/peak-hours")
@handle_exceptions
async def get_peak_hours() -> Dict[str, Any]:
    """
    피크 시간대 분석

    최근 7일간의 시간대별 실행 통계를 분석합니다.

    Returns:
        - hourly_stats: 시간대별 통계
        - best_hours: 최적 실행 시간대
        - worst_hours: 비추천 실행 시간대
    """
    from core.adaptive_scheduler import get_adaptive_scheduler

    scheduler = get_adaptive_scheduler()
    result = scheduler.analyze_peak_hours()

    return {
        "success": True,
        "data": result
    }


@router.get("/report")
@handle_exceptions
async def get_health_report() -> Dict[str, Any]:
    """건강도 보고서 텍스트 조회"""
    from core.adaptive_scheduler import get_adaptive_scheduler

    scheduler = get_adaptive_scheduler()
    report = scheduler.get_health_report()

    return {
        "success": True,
        "report": report
    }


# =============================================================================
# Keyword Priority Scheduler API
# =============================================================================

@router.get("/keyword-priorities")
@handle_exceptions
async def get_keyword_priorities() -> Dict[str, Any]:
    """
    키워드 우선순위 조회

    Returns:
        - total_keywords: 총 키워드 수
        - by_priority: 우선순위별 키워드 목록
        - pending_scans: 스캔 대기 키워드
    """
    from core.keyword_priority_scheduler import get_keyword_priority_scheduler

    scheduler = get_keyword_priority_scheduler()
    summary = scheduler.get_schedule_summary()

    return {
        "success": True,
        "data": summary
    }


@router.get("/keyword-priorities/{keyword}")
@handle_exceptions
async def get_keyword_priority(keyword: str) -> Dict[str, Any]:
    """특정 키워드의 우선순위 정보 조회"""
    from core.keyword_priority_scheduler import get_keyword_priority_scheduler

    scheduler = get_keyword_priority_scheduler()
    info = scheduler.get_keyword_info(keyword)

    if info is None:
        raise HTTPException(status_code=404, detail=f"Keyword not found: {keyword}")

    return {
        "success": True,
        "data": info
    }


@router.post("/keyword-priorities/set")
@handle_exceptions
async def set_keyword_priority(request: KeywordPriorityRequest) -> Dict[str, Any]:
    """키워드 우선순위 수동 설정"""
    from core.keyword_priority_scheduler import get_keyword_priority_scheduler

    if request.priority not in ("critical", "high", "medium", "low"):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority: {request.priority}"
        )

    scheduler = get_keyword_priority_scheduler()
    scheduler.set_manual_priority(request.keyword, request.priority)

    return {
        "success": True,
        "message": f"Priority set: {request.keyword} → {request.priority}"
    }


@router.get("/keywords-to-scan")
@handle_exceptions
async def get_keywords_to_scan() -> Dict[str, Any]:
    """현재 스캔해야 할 키워드 목록 조회"""
    from core.keyword_priority_scheduler import get_keyword_priority_scheduler

    scheduler = get_keyword_priority_scheduler()
    keywords = scheduler.get_keywords_to_scan()

    return {
        "success": True,
        "keywords": keywords,
        "count": len(keywords)
    }


# =============================================================================
# Auto Rescan Handler API
# =============================================================================

@router.get("/auto-rescan/status")
@handle_exceptions
async def get_auto_rescan_status() -> Dict[str, Any]:
    """
    자동 재스캔 상태 조회

    Returns:
        - min_drop: 최소 하락폭
        - cooldown_minutes: 쿨다운 시간
        - active_cooldowns: 활성 쿨다운 목록
        - recent_rescans: 최근 재스캔 이력
    """
    from core.auto_rescan_handler import get_auto_rescan_handler

    handler = get_auto_rescan_handler()
    status = handler.get_status()

    return {
        "success": True,
        "data": status
    }


@router.post("/auto-rescan/clear-cooldown")
@handle_exceptions
async def clear_rescan_cooldown(keyword: Optional[str] = None) -> Dict[str, Any]:
    """재스캔 쿨다운 초기화"""
    from core.auto_rescan_handler import get_auto_rescan_handler

    handler = get_auto_rescan_handler()
    handler.clear_cooldown(keyword)

    return {
        "success": True,
        "message": f"Cooldown cleared: {keyword or 'all'}"
    }


# =============================================================================
# Lead Reminder API
# =============================================================================

@router.get("/lead-reminders/status")
@handle_exceptions
async def get_lead_reminder_status() -> Dict[str, Any]:
    """
    Hot Lead 재알림 상태 조회

    Returns:
        - pending_reminders: 재알림 대기 목록
        - stats: 재알림 통계
    """
    from services.lead_reminder_scheduler import get_reminder_status

    status = get_reminder_status()

    return {
        "success": True,
        "data": status
    }


@router.post("/lead-reminders/send")
@handle_exceptions
async def send_lead_reminders(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """Hot Lead 재알림 발송"""
    from services.lead_reminder_scheduler import run_lead_reminders

    # 백그라운드로 실행
    background_tasks.add_task(run_lead_reminders)

    return {
        "success": True,
        "message": "Reminder task started in background"
    }


# =============================================================================
# Lead Status Transition API
# =============================================================================

@router.get("/lead-transitions/preview")
@handle_exceptions
async def preview_lead_transitions() -> Dict[str, Any]:
    """
    리드 상태 전이 미리보기 (dry run)

    Returns:
        - total_candidates: 전이 대상 총 수
        - by_rule: 규칙별 전이 대상 수
        - details: 각 전이 상세
    """
    from services.lead_status_automator import get_transition_preview

    preview = get_transition_preview()

    return {
        "success": True,
        "data": preview
    }


@router.post("/lead-transitions/run")
@handle_exceptions
async def run_lead_transitions(request: TransitionRunRequest) -> Dict[str, Any]:
    """
    리드 상태 전이 실행

    Args:
        dry_run: True면 시뮬레이션만 (기본값)
    """
    from services.lead_status_automator import run_status_transitions

    result = run_status_transitions(dry_run=request.dry_run)

    return {
        "success": True,
        "data": result
    }


@router.get("/lead-transitions/history")
@handle_exceptions
async def get_transition_history(days: int = 7, limit: int = 100) -> Dict[str, Any]:
    """리드 상태 전이 이력 조회"""
    from services.lead_status_automator import LeadStatusAutomator

    automator = LeadStatusAutomator()
    history = automator.get_transition_history(days=days, limit=limit)

    return {
        "success": True,
        "history": history,
        "count": len(history)
    }


@router.get("/lead-status/summary")
@handle_exceptions
async def get_lead_status_summary() -> Dict[str, Any]:
    """리드 상태 요약 조회"""
    from services.lead_status_automator import get_lead_status_summary

    summary = get_lead_status_summary()

    return {
        "success": True,
        "data": summary
    }
