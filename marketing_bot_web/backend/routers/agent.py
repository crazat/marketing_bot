"""
AI Agent API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

AI 에이전트 사용량 모니터링 및 액션 로그 관리
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List, Optional
from pydantic import BaseModel
import sys
import os
from pathlib import Path
import sqlite3
import json
from datetime import datetime, timedelta

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager
from core_services.sql_builder import validate_table_name, get_table_columns
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()

# AI Agent 사용량 추적 파일
AGENT_USAGE_FILE = os.path.join(parent_dir, 'db', 'agent_usage.json')
AGENT_CONFIG_FILE = os.path.join(parent_dir, 'config', 'config.json')

# 기본 일일 한도
DEFAULT_DAILY_LIMIT = 100
DEFAULT_COOLDOWN_SECONDS = 60


def load_agent_usage() -> Dict[str, Any]:
    """AI Agent 사용량 데이터 로드"""
    default_usage = {
        "daily_calls": 0,
        "last_reset": datetime.now().strftime("%Y-%m-%d"),
        "last_call": None,
        "total_calls": 0,
        "actions": []
    }

    if os.path.exists(AGENT_USAGE_FILE):
        try:
            with open(AGENT_USAGE_FILE, 'r', encoding='utf-8') as f:
                usage = json.load(f)

            # 날짜가 바뀌었으면 일일 카운트 리셋
            today = datetime.now().strftime("%Y-%m-%d")
            if usage.get("last_reset") != today:
                usage["daily_calls"] = 0
                usage["last_reset"] = today
                save_agent_usage(usage)

            return usage
        except Exception as e:
            print(f"[Agent] 사용량 파일 로드 실패: {e}")

    return default_usage


def save_agent_usage(usage: Dict[str, Any]):
    """AI Agent 사용량 데이터 저장"""
    os.makedirs(os.path.dirname(AGENT_USAGE_FILE), exist_ok=True)
    with open(AGENT_USAGE_FILE, 'w', encoding='utf-8') as f:
        json.dump(usage, f, indent=2, ensure_ascii=False)


def get_agent_config() -> Dict[str, Any]:
    """AI Agent 설정 로드"""
    default_config = {
        "daily_limit": DEFAULT_DAILY_LIMIT,
        "cooldown_seconds": DEFAULT_COOLDOWN_SECONDS,
        "enabled": True
    }

    if os.path.exists(AGENT_CONFIG_FILE):
        try:
            with open(AGENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get("ai_agent", default_config)
        except (FileNotFoundError, json.JSONDecodeError, PermissionError) as e:
            print(f"[Agent] 설정 파일 로드 실패: {e}")

    return default_config


@router.get("/usage-stats")
@handle_exceptions
async def get_usage_stats() -> Dict[str, Any]:
    """
    AI Agent 사용량 통계 조회

    Returns:
        - daily_calls: 오늘 사용한 호출 수
        - daily_limit: 일일 한도
        - remaining: 남은 호출 수
        - usage_percent: 사용률 (%)
        - total_calls: 총 누적 호출 수
        - last_call: 마지막 호출 시간
        - cooldown_remaining: 쿨다운 남은 시간 (초)
        - status: 상태 (available, cooldown, limit_reached)
    """
    try:
        usage = load_agent_usage()
        config = get_agent_config()

        daily_limit = config.get("daily_limit", DEFAULT_DAILY_LIMIT)
        cooldown_seconds = config.get("cooldown_seconds", DEFAULT_COOLDOWN_SECONDS)

        daily_calls = usage.get("daily_calls", 0)
        remaining = max(0, daily_limit - daily_calls)
        usage_percent = min(100, (daily_calls / daily_limit) * 100) if daily_limit > 0 else 0

        # 쿨다운 계산
        cooldown_remaining = 0
        status = "available"

        if daily_calls >= daily_limit:
            status = "limit_reached"
        elif usage.get("last_call"):
            try:
                last_call = datetime.fromisoformat(usage["last_call"])
                elapsed = (datetime.now() - last_call).total_seconds()
                if elapsed < cooldown_seconds:
                    cooldown_remaining = int(cooldown_seconds - elapsed)
                    status = "cooldown"
            except (ValueError, TypeError, KeyError):
                pass  # datetime 파싱 실패 시 무시

        return {
            "daily_calls": daily_calls,
            "daily_limit": daily_limit,
            "remaining": remaining,
            "usage_percent": round(usage_percent, 1),
            "total_calls": usage.get("total_calls", 0),
            "last_call": usage.get("last_call"),
            "cooldown_seconds": cooldown_seconds,
            "cooldown_remaining": cooldown_remaining,
            "status": status,
            "enabled": config.get("enabled", True)
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"사용량 통계 조회 실패: {str(e)}"
        )


@router.get("/actions-log")
@handle_exceptions
async def get_actions_log(
    limit: int = 50,
    offset: int = 0,
    status: Optional[str] = None,
    action_type: Optional[str] = None
) -> Dict[str, Any]:
    """
    AI Agent 액션 로그 조회

    Args:
        limit: 조회할 로그 수 (기본 50)
        offset: 시작 위치
        status: 상태 필터 (pending, approved, rejected, completed)
        action_type: 액션 타입 필터 (comment, analysis, content, etc.)

    Returns:
        - actions: 액션 로그 목록
        - total: 전체 로그 수
        - pending_count: 대기 중인 액션 수
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # agent_actions 테이블이 없으면 생성
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_actions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                action_type TEXT NOT NULL,
                target_type TEXT,
                target_id TEXT,
                input_data TEXT,
                output_data TEXT,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                approved_at TIMESTAMP,
                completed_at TIMESTAMP,
                error_message TEXT,
                tokens_used INTEGER DEFAULT 0
            )
        ''')
        conn.commit()

        # 쿼리 조건 구성
        where_conditions = []
        params = []

        if status:
            where_conditions.append("status = ?")
            params.append(status)

        if action_type:
            where_conditions.append("action_type = ?")
            params.append(action_type)

        where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

        # 총 개수 조회
        cursor.execute(f"SELECT COUNT(*) FROM agent_actions {where_clause}", params)
        total = cursor.fetchone()[0]

        # 대기 중인 액션 수
        cursor.execute("SELECT COUNT(*) FROM agent_actions WHERE status = 'pending'")
        pending_count = cursor.fetchone()[0]

        # 액션 로그 조회
        query = f"""
            SELECT id, action_type, target_type, target_id,
                   input_data, output_data, status,
                   created_at, approved_at, completed_at,
                   error_message, tokens_used
            FROM agent_actions
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        cursor.execute(query, params + [limit, offset])

        actions = []
        for row in cursor.fetchall():
            action = {
                "id": row["id"],
                "action_type": row["action_type"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "input_data": json.loads(row["input_data"]) if row["input_data"] else None,
                "output_data": json.loads(row["output_data"]) if row["output_data"] else None,
                "status": row["status"],
                "created_at": row["created_at"],
                "approved_at": row["approved_at"],
                "completed_at": row["completed_at"],
                "error_message": row["error_message"],
                "tokens_used": row["tokens_used"]
            }
            actions.append(action)

        return {
            "actions": actions,
            "total": total,
            "pending_count": pending_count,
            "limit": limit,
            "offset": offset
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"액션 로그 조회 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


class ActionApprovalRequest(BaseModel):
    notes: Optional[str] = None


@router.post("/approve/{action_id}")
@handle_exceptions
async def approve_action(action_id: int, request: ActionApprovalRequest = None) -> Dict[str, Any]:
    """
    AI Agent 액션 승인

    Args:
        action_id: 승인할 액션 ID

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 액션 존재 여부 확인
        cursor.execute("SELECT id, status FROM agent_actions WHERE id = ?", (action_id,))
        action = cursor.fetchone()

        if not action:
            raise HTTPException(status_code=404, detail="액션을 찾을 수 없습니다")

        if action[1] != 'pending':
            raise HTTPException(status_code=400, detail=f"이미 처리된 액션입니다 (상태: {action[1]})")

        # 승인 처리
        cursor.execute("""
            UPDATE agent_actions
            SET status = 'approved', approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (action_id,))
        conn.commit()

        return {
            "success": True,
            "message": "액션이 승인되었습니다",
            "action_id": action_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"액션 승인 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.post("/reject/{action_id}")
@handle_exceptions
async def reject_action(action_id: int, request: ActionApprovalRequest = None) -> Dict[str, Any]:
    """
    AI Agent 액션 거절

    Args:
        action_id: 거절할 액션 ID

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 액션 존재 여부 확인
        cursor.execute("SELECT id, status FROM agent_actions WHERE id = ?", (action_id,))
        action = cursor.fetchone()

        if not action:
            raise HTTPException(status_code=404, detail="액션을 찾을 수 없습니다")

        if action[1] != 'pending':
            raise HTTPException(status_code=400, detail=f"이미 처리된 액션입니다 (상태: {action[1]})")

        # 거절 처리
        notes = request.notes if request else None
        cursor.execute("""
            UPDATE agent_actions
            SET status = 'rejected',
                completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
        """, (notes, action_id))
        conn.commit()

        return {
            "success": True,
            "message": "액션이 거절되었습니다",
            "action_id": action_id
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"액션 거절 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


class AutoApproveConfig(BaseModel):
    """자동 승인 설정"""
    enabled: bool = False
    action_types: List[str] = []  # 자동 승인할 액션 타입


@router.post("/auto-approve")
async def set_auto_approve(config: AutoApproveConfig) -> Dict[str, Any]:
    """
    [Phase 8.0] 자동 승인 설정

    Args:
        enabled: 자동 승인 활성화 여부
        action_types: 자동 승인할 액션 타입 목록

    Returns:
        - success: 성공 여부
        - config: 적용된 설정
    """
    try:
        # 설정 파일 로드
        config_data = {}
        if os.path.exists(AGENT_CONFIG_FILE):
            with open(AGENT_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

        # AI Agent 설정 업데이트
        if 'ai_agent' not in config_data:
            config_data['ai_agent'] = {}

        config_data['ai_agent']['auto_approve'] = {
            'enabled': config.enabled,
            'action_types': config.action_types
        }

        # 설정 저장
        os.makedirs(os.path.dirname(AGENT_CONFIG_FILE), exist_ok=True)
        with open(AGENT_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return {
            'success': True,
            'message': '자동 승인 설정이 업데이트되었습니다',
            'config': config_data['ai_agent']['auto_approve']
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"자동 승인 설정 실패: {str(e)}"
        )


@router.get("/auto-approve")
async def get_auto_approve() -> Dict[str, Any]:
    """
    자동 승인 설정 조회

    Returns:
        - enabled: 자동 승인 활성화 여부
        - action_types: 자동 승인할 액션 타입 목록
    """
    try:
        config = get_agent_config()
        auto_approve = config.get('auto_approve', {
            'enabled': False,
            'action_types': []
        })

        return auto_approve

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"자동 승인 설정 조회 실패: {str(e)}"
        )


@router.post("/batch-approve")
async def batch_approve_actions(action_type: Optional[str] = None) -> Dict[str, Any]:
    """
    [Phase 8.0] 대기 중인 액션 일괄 승인

    Args:
        action_type: 특정 액션 타입만 승인 (없으면 모두)

    Returns:
        - approved_count: 승인된 액션 수
        - action_ids: 승인된 액션 ID 목록
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 대기 중인 액션 조회
        if action_type:
            cursor.execute("""
                SELECT id FROM agent_actions
                WHERE status = 'pending' AND action_type = ?
            """, (action_type,))
        else:
            cursor.execute("""
                SELECT id FROM agent_actions
                WHERE status = 'pending'
            """)

        pending_ids = [row[0] for row in cursor.fetchall()]

        if not pending_ids:
            return {
                'success': True,
                'message': '승인할 대기 중인 액션이 없습니다',
                'approved_count': 0,
                'action_ids': []
            }

        # 일괄 승인
        cursor.executemany("""
            UPDATE agent_actions
            SET status = 'approved', approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, [(id,) for id in pending_ids])

        conn.commit()

        return {
            'success': True,
            'message': f'{len(pending_ids)}개 액션이 승인되었습니다',
            'approved_count': len(pending_ids),
            'action_ids': pending_ids
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"일괄 승인 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.post("/batch-reject")
async def batch_reject_actions(action_type: Optional[str] = None, reason: Optional[str] = None) -> Dict[str, Any]:
    """
    [Phase 6.1] 대기 중인 액션 일괄 거절

    Args:
        action_type: 특정 액션 타입만 거절 (없으면 모두)
        reason: 거절 사유

    Returns:
        - rejected_count: 거절된 액션 수
        - action_ids: 거절된 액션 ID 목록
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 대기 중인 액션 조회
        if action_type:
            cursor.execute("""
                SELECT id FROM agent_actions
                WHERE status = 'pending' AND action_type = ?
            """, (action_type,))
        else:
            cursor.execute("""
                SELECT id FROM agent_actions
                WHERE status = 'pending'
            """)

        pending_ids = [row[0] for row in cursor.fetchall()]

        if not pending_ids:
            return {
                'success': True,
                'message': '거절할 대기 중인 액션이 없습니다',
                'rejected_count': 0,
                'action_ids': []
            }

        # 일괄 거절
        rejection_reason = reason or '일괄 거절됨'
        cursor.executemany("""
            UPDATE agent_actions
            SET status = 'rejected',
                completed_at = CURRENT_TIMESTAMP,
                error_message = ?
            WHERE id = ?
        """, [(rejection_reason, id) for id in pending_ids])

        conn.commit()

        return {
            'success': True,
            'message': f'{len(pending_ids)}개 액션이 거절되었습니다',
            'rejected_count': len(pending_ids),
            'action_ids': pending_ids
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"일괄 거절 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get("/summary")
async def get_agent_summary() -> Dict[str, Any]:
    """
    AI Agent 요약 정보 (대시보드용)

    Returns:
        - usage: 사용량 통계
        - actions_summary: 액션 요약 (상태별 개수)
        - recent_actions: 최근 액션 5개
    """
    # 사용량 통계
    usage = load_agent_usage()
    config = get_agent_config()

    daily_limit = config.get("daily_limit", DEFAULT_DAILY_LIMIT)
    daily_calls = usage.get("daily_calls", 0)

    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_actions'")
        if not cursor.fetchone():
            return {
                "usage": {
                    "daily_calls": daily_calls,
                    "daily_limit": daily_limit,
                    "remaining": max(0, daily_limit - daily_calls),
                    "usage_percent": round((daily_calls / daily_limit) * 100, 1) if daily_limit > 0 else 0
                },
                "actions_summary": {
                    "pending": 0,
                    "approved": 0,
                    "rejected": 0,
                    "completed": 0
                },
                "recent_actions": []
            }

        # 상태별 액션 개수
        cursor.execute("""
            SELECT status, COUNT(*) as count
            FROM agent_actions
            WHERE created_at >= datetime('now', '-7 days')
            GROUP BY status
        """)

        actions_summary = {
            "pending": 0,
            "approved": 0,
            "rejected": 0,
            "completed": 0
        }
        for row in cursor.fetchall():
            if row["status"] in actions_summary:
                actions_summary[row["status"]] = row["count"]

        # 최근 액션 5개
        cursor.execute("""
            SELECT id, action_type, target_type, status, created_at
            FROM agent_actions
            ORDER BY created_at DESC
            LIMIT 5
        """)

        recent_actions = []
        for row in cursor.fetchall():
            recent_actions.append({
                "id": row["id"],
                "action_type": row["action_type"],
                "target_type": row["target_type"],
                "status": row["status"],
                "created_at": row["created_at"]
            })

        return {
            "usage": {
                "daily_calls": daily_calls,
                "daily_limit": daily_limit,
                "remaining": max(0, daily_limit - daily_calls),
                "usage_percent": round((daily_calls / daily_limit) * 100, 1) if daily_limit > 0 else 0
            },
            "actions_summary": actions_summary,
            "recent_actions": recent_actions
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"요약 정보 조회 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.get("/approval-rates")
async def get_approval_rates() -> Dict[str, Any]:
    """
    액션 유형별 승인/거절 비율 조회

    Returns:
        - by_action_type: 액션 유형별 통계
        - overall: 전체 통계
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 여부 확인
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='agent_actions'")
        if not cursor.fetchone():
            return {
                "by_action_type": {},
                "overall": {
                    "total": 0,
                    "approved": 0,
                    "rejected": 0,
                    "completed": 0,
                    "approval_rate": 0,
                    "rejection_rate": 0,
                    "completion_rate": 0
                }
            }

        # 액션 유형별 상태 통계 (최근 30일)
        cursor.execute("""
            SELECT
                action_type,
                status,
                COUNT(*) as count
            FROM agent_actions
            WHERE created_at >= datetime('now', '-30 days')
            GROUP BY action_type, status
        """)

        action_stats: Dict[str, Dict[str, int]] = {}
        for row in cursor.fetchall():
            action_type = row["action_type"]
            status = row["status"]
            count = row["count"]

            if action_type not in action_stats:
                action_stats[action_type] = {
                    "pending": 0, "approved": 0, "rejected": 0, "completed": 0, "total": 0
                }
            action_stats[action_type][status] = count
            action_stats[action_type]["total"] += count

        # 비율 계산
        by_action_type = {}
        overall_total = 0
        overall_approved = 0
        overall_rejected = 0
        overall_completed = 0

        for action_type, stats in action_stats.items():
            total = stats["total"]
            approved = stats.get("approved", 0) + stats.get("completed", 0)
            rejected = stats.get("rejected", 0)
            completed = stats.get("completed", 0)

            by_action_type[action_type] = {
                "total": total,
                "approved": stats.get("approved", 0),
                "rejected": rejected,
                "completed": completed,
                "pending": stats.get("pending", 0),
                "approval_rate": round((approved / total * 100) if total > 0 else 0, 1),
                "rejection_rate": round((rejected / total * 100) if total > 0 else 0, 1),
                "completion_rate": round((completed / total * 100) if total > 0 else 0, 1)
            }

            overall_total += total
            overall_approved += stats.get("approved", 0)
            overall_rejected += rejected
            overall_completed += completed

        overall_approved_total = overall_approved + overall_completed

        return {
            "by_action_type": by_action_type,
            "overall": {
                "total": overall_total,
                "approved": overall_approved,
                "rejected": overall_rejected,
                "completed": overall_completed,
                "approval_rate": round((overall_approved_total / overall_total * 100) if overall_total > 0 else 0, 1),
                "rejection_rate": round((overall_rejected / overall_total * 100) if overall_total > 0 else 0, 1),
                "completion_rate": round((overall_completed / overall_total * 100) if overall_total > 0 else 0, 1)
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"승인/거절 비율 조회 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# [Phase 6.2] 자동 승인 규칙 관리 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class AutoApprovalRuleCreate(BaseModel):
    """자동 승인 규칙 생성"""
    name: str
    description: Optional[str] = None
    condition_type: str  # action_type, score_threshold, trust_level, platform
    condition_value: str  # comment, 80, trusted, naver_cafe
    action: str = "approve"  # approve, skip, flag
    priority: int = 0
    is_active: bool = True


class AutoApprovalRuleUpdate(BaseModel):
    """자동 승인 규칙 수정"""
    name: Optional[str] = None
    description: Optional[str] = None
    condition_type: Optional[str] = None
    condition_value: Optional[str] = None
    action: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None


@router.get("/rules")
async def get_auto_approval_rules() -> Dict[str, Any]:
    """
    [Phase 6.2] 자동 승인 규칙 목록 조회

    Returns:
        - rules: 규칙 목록
        - total: 전체 규칙 수
        - active_count: 활성화된 규칙 수
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 생성 (없으면)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS auto_approval_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT,
                condition_type TEXT NOT NULL,
                condition_value TEXT NOT NULL,
                action TEXT DEFAULT 'approve',
                priority INTEGER DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

        # [Phase 7] SELECT * 제거
        columns = "id, name, description, condition_type, condition_value, action, priority, is_active, created_at, updated_at"
        cursor.execute(f"""
            SELECT {columns} FROM auto_approval_rules
            ORDER BY priority DESC, created_at DESC
        """)

        rules = [dict(row) for row in cursor.fetchall()]

        # 활성화된 규칙 수
        active_count = sum(1 for r in rules if r.get('is_active'))

        return {
            "rules": rules,
            "total": len(rules),
            "active_count": active_count
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"규칙 조회 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.post("/rules")
async def create_auto_approval_rule(rule: AutoApprovalRuleCreate) -> Dict[str, Any]:
    """
    [Phase 6.2] 자동 승인 규칙 생성

    condition_type 옵션:
    - action_type: 특정 액션 타입 (comment, analysis, content 등)
    - score_threshold: 리드 점수 임계값 (80 이상이면 자동 승인)
    - trust_level: 신뢰도 레벨 (trusted, review)
    - platform: 플랫폼 (naver_cafe, youtube 등)
    - engagement_signal: 참여 신호 (ready_to_act, seeking_info)

    action 옵션:
    - approve: 자동 승인
    - skip: 건너뛰기
    - flag: 플래그 표시 (수동 검토 필요)

    Args:
        rule: 규칙 데이터

    Returns:
        생성된 규칙 ID
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO auto_approval_rules
            (name, description, condition_type, condition_value, action, priority, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            rule.name,
            rule.description,
            rule.condition_type,
            rule.condition_value,
            rule.action,
            rule.priority,
            1 if rule.is_active else 0
        ))

        rule_id = cursor.lastrowid
        conn.commit()

        return {
            "success": True,
            "id": rule_id,
            "message": f"규칙 '{rule.name}'이(가) 생성되었습니다"
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"규칙 생성 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.put("/rules/{rule_id}")
async def update_auto_approval_rule(rule_id: int, rule: AutoApprovalRuleUpdate) -> Dict[str, Any]:
    """
    [Phase 6.2] 자동 승인 규칙 수정

    Args:
        rule_id: 규칙 ID
        rule: 수정할 필드

    Returns:
        성공 여부
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        # 규칙 존재 확인
        cursor.execute("SELECT id FROM auto_approval_rules WHERE id = ?", (rule_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다")

        # 업데이트할 필드 수집
        updates = []
        params = []

        if rule.name is not None:
            updates.append("name = ?")
            params.append(rule.name)
        if rule.description is not None:
            updates.append("description = ?")
            params.append(rule.description)
        if rule.condition_type is not None:
            updates.append("condition_type = ?")
            params.append(rule.condition_type)
        if rule.condition_value is not None:
            updates.append("condition_value = ?")
            params.append(rule.condition_value)
        if rule.action is not None:
            updates.append("action = ?")
            params.append(rule.action)
        if rule.priority is not None:
            updates.append("priority = ?")
            params.append(rule.priority)
        if rule.is_active is not None:
            updates.append("is_active = ?")
            params.append(1 if rule.is_active else 0)

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(rule_id)
            cursor.execute(
                f"UPDATE auto_approval_rules SET {', '.join(updates)} WHERE id = ?",
                params
            )
            conn.commit()

        return {
            "success": True,
            "message": "규칙이 수정되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"규칙 수정 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.delete("/rules/{rule_id}")
async def delete_auto_approval_rule(rule_id: int) -> Dict[str, Any]:
    """
    [Phase 6.2] 자동 승인 규칙 삭제

    Args:
        rule_id: 규칙 ID

    Returns:
        성공 여부
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM auto_approval_rules WHERE id = ?", (rule_id,))
        deleted = cursor.rowcount > 0
        conn.commit()

        if not deleted:
            raise HTTPException(status_code=404, detail="규칙을 찾을 수 없습니다")

        return {
            "success": True,
            "message": "규칙이 삭제되었습니다"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"규칙 삭제 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()


@router.post("/rules/apply")
async def apply_auto_approval_rules() -> Dict[str, Any]:
    """
    [Phase 6.2] 대기 중인 액션에 자동 승인 규칙 적용

    활성화된 규칙들을 우선순위 순으로 적용하여
    조건에 맞는 대기 중인 액션을 자동으로 처리합니다.

    Returns:
        - processed_count: 처리된 액션 수
        - approved: 승인된 수
        - skipped: 건너뛴 수
        - flagged: 플래그된 수
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거 - 활성화된 규칙 조회 (우선순위 순)
        columns = "id, name, description, condition_type, condition_value, action, priority, is_active"
        cursor.execute(f"""
            SELECT {columns} FROM auto_approval_rules
            WHERE is_active = 1
            ORDER BY priority DESC
        """)
        rules = [dict(row) for row in cursor.fetchall()]

        if not rules:
            return {
                "success": True,
                "message": "활성화된 규칙이 없습니다",
                "processed_count": 0,
                "approved": 0,
                "skipped": 0,
                "flagged": 0
            }

        # 대기 중인 액션 조회
        cursor.execute("""
            SELECT id, action_type, target_type, input_data
            FROM agent_actions
            WHERE status = 'pending'
        """)
        pending_actions = [dict(row) for row in cursor.fetchall()]

        results = {"approved": 0, "skipped": 0, "flagged": 0}

        for action in pending_actions:
            action_id = action['id']
            input_data = json.loads(action['input_data']) if action['input_data'] else {}

            # 규칙 매칭 (첫 번째 매칭 규칙 적용)
            for rule in rules:
                matched = False
                condition_type = rule['condition_type']
                condition_value = rule['condition_value']

                # 조건 확인
                if condition_type == 'action_type':
                    matched = action['action_type'] == condition_value
                elif condition_type == 'score_threshold':
                    score = input_data.get('score', 0)
                    matched = score >= int(condition_value)
                elif condition_type == 'trust_level':
                    trust_level = input_data.get('trust_level', '')
                    matched = trust_level == condition_value
                elif condition_type == 'platform':
                    platform = input_data.get('platform', '')
                    matched = platform == condition_value
                elif condition_type == 'engagement_signal':
                    signal = input_data.get('engagement_signal', '')
                    matched = signal == condition_value

                if matched:
                    # 액션 적용
                    rule_action = rule['action']
                    if rule_action == 'approve':
                        cursor.execute("""
                            UPDATE agent_actions
                            SET status = 'approved', approved_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (action_id,))
                        results['approved'] += 1
                    elif rule_action == 'skip':
                        cursor.execute("""
                            UPDATE agent_actions
                            SET status = 'skipped', completed_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                        """, (action_id,))
                        results['skipped'] += 1
                    elif rule_action == 'flag':
                        cursor.execute("""
                            UPDATE agent_actions
                            SET status = 'flagged'
                            WHERE id = ?
                        """, (action_id,))
                        results['flagged'] += 1

                    break  # 첫 번째 매칭 규칙만 적용

        conn.commit()

        processed = results['approved'] + results['skipped'] + results['flagged']

        return {
            "success": True,
            "message": f"{processed}개 액션이 처리되었습니다",
            "processed_count": processed,
            **results
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"규칙 적용 실패: {str(e)}"
        )
    finally:
        if conn:
            conn.close()
