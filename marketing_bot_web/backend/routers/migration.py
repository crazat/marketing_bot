"""
Database Migration API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 1-4] 마이그레이션 버전 관리 API
- 마이그레이션 상태 조회
- 수동 마이그레이션 실행
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any
import sys
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, parent_dir)

from services.migration_manager import MigrationManager, run_all_migrations, get_migration_status
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


@router.get("/status")
@handle_exceptions
async def get_status() -> Dict[str, Any]:
    """
    마이그레이션 상태 조회

    Returns:
        - current_version: 현재 적용된 최신 버전
        - total_migrations: 전체 마이그레이션 수
        - applied_count: 적용된 마이그레이션 수
        - pending_count: 대기 중인 마이그레이션 수
        - applied: 적용된 마이그레이션 목록
        - pending: 대기 중인 마이그레이션 목록
    """
    try:
        status = get_migration_status()
        return {
            "success": True,
            "data": status
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마이그레이션 상태 조회 실패: {str(e)}")


@router.post("/run")
@handle_exceptions
async def run_migrations() -> Dict[str, Any]:
    """
    대기 중인 마이그레이션 실행

    Returns:
        - applied: 이번에 적용된 마이그레이션 목록
        - skipped: 이미 적용되어 건너뛴 마이그레이션 목록
        - errors: 오류 발생 목록
    """
    try:
        result = run_all_migrations()
        return {
            "success": True,
            "message": f"마이그레이션 {len(result['applied'])}개 적용 완료",
            "data": result
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"마이그레이션 실행 실패: {str(e)}")


@router.get("/history")
@handle_exceptions
async def get_history() -> Dict[str, Any]:
    """
    마이그레이션 히스토리 조회

    Returns:
        적용된 마이그레이션 목록 (버전, 설명, 적용 시간)
    """
    try:
        status = get_migration_status()
        return {
            "success": True,
            "data": {
                "history": status.get("applied", []),
                "current_version": status.get("current_version"),
                "total_applied": status.get("applied_count", 0)
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"히스토리 조회 실패: {str(e)}")
