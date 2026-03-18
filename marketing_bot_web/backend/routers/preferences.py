"""
User Preferences API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4.3] 사용자 설정
- 대시보드 위젯 표시/숨김 설정
- 레이아웃 저장
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)  # 프로젝트 루트
backend_dir = str(Path(__file__).parent.parent)  # backend 디렉토리
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from schemas.response import success_response, error_response

router = APIRouter()


# 기본 대시보드 위젯 설정
DEFAULT_DASHBOARD_WIDGETS = {
    "metrics_overview": {"enabled": True, "order": 1, "title": "주요 지표"},
    "daily_briefing": {"enabled": True, "order": 2, "title": "일일 브리핑"},
    "sentinel_alerts": {"enabled": True, "order": 3, "title": "Sentinel 경고"},
    "chronos_timeline": {"enabled": True, "order": 4, "title": "Chronos 일정"},
    "rank_alerts": {"enabled": True, "order": 5, "title": "순위 알림"},
    "pending_actions": {"enabled": True, "order": 6, "title": "대기 중인 작업"},
    "recent_activities": {"enabled": True, "order": 7, "title": "최근 활동"},
    "suggested_actions": {"enabled": True, "order": 8, "title": "추천 액션"},
}


class WidgetPreference(BaseModel):
    enabled: bool
    order: Optional[int] = None


class DashboardPreferences(BaseModel):
    widgets: Dict[str, WidgetPreference]


def _ensure_preferences_table(cursor):
    """preferences 테이블 생성"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_preferences (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key TEXT UNIQUE NOT NULL,
            value TEXT NOT NULL,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_preferences_key ON user_preferences(key)")


def _get_preference(cursor, key: str, default=None):
    """설정 값 조회"""
    cursor.execute("SELECT value FROM user_preferences WHERE key = ?", (key,))
    row = cursor.fetchone()
    if row:
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return row[0]
    return default


def _set_preference(cursor, key: str, value):
    """설정 값 저장"""
    value_json = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
    cursor.execute("""
        INSERT INTO user_preferences (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            value = excluded.value,
            updated_at = CURRENT_TIMESTAMP
    """, (key, value_json))


@router.get("/dashboard")
@handle_exceptions
async def get_dashboard_preferences() -> Dict[str, Any]:
    """
    대시보드 설정 조회
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)
    conn.commit()

    widgets = _get_preference(cursor, 'dashboard_widgets', DEFAULT_DASHBOARD_WIDGETS)

    # 기본 위젯이 누락된 경우 추가
    for widget_id, default_config in DEFAULT_DASHBOARD_WIDGETS.items():
        if widget_id not in widgets:
            widgets[widget_id] = default_config

    conn.close()

    return success_response({
        "widgets": widgets,
        "available_widgets": list(DEFAULT_DASHBOARD_WIDGETS.keys())
    })


@router.put("/dashboard")
@handle_exceptions
async def update_dashboard_preferences(preferences: DashboardPreferences) -> Dict[str, Any]:
    """
    대시보드 설정 업데이트
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)

    # 기존 설정 로드
    current = _get_preference(cursor, 'dashboard_widgets', DEFAULT_DASHBOARD_WIDGETS)

    # 업데이트 적용
    for widget_id, pref in preferences.widgets.items():
        if widget_id in DEFAULT_DASHBOARD_WIDGETS:
            if widget_id not in current:
                current[widget_id] = DEFAULT_DASHBOARD_WIDGETS[widget_id].copy()
            current[widget_id]['enabled'] = pref.enabled
            if pref.order is not None:
                current[widget_id]['order'] = pref.order

    _set_preference(cursor, 'dashboard_widgets', current)
    conn.commit()
    conn.close()

    return success_response({
        "message": "대시보드 설정이 저장되었습니다",
        "widgets": current
    })


@router.post("/dashboard/reset")
@handle_exceptions
async def reset_dashboard_preferences() -> Dict[str, Any]:
    """
    대시보드 설정 초기화
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)
    _set_preference(cursor, 'dashboard_widgets', DEFAULT_DASHBOARD_WIDGETS)

    conn.commit()
    conn.close()

    return success_response({
        "message": "대시보드 설정이 초기화되었습니다",
        "widgets": DEFAULT_DASHBOARD_WIDGETS
    })


@router.put("/dashboard/widget/{widget_id}")
@handle_exceptions
async def toggle_widget(widget_id: str, enabled: bool = True) -> Dict[str, Any]:
    """
    개별 위젯 표시/숨김 토글
    """
    if widget_id not in DEFAULT_DASHBOARD_WIDGETS:
        raise HTTPException(status_code=400, detail=f"알 수 없는 위젯: {widget_id}")

    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)

    current = _get_preference(cursor, 'dashboard_widgets', DEFAULT_DASHBOARD_WIDGETS)

    if widget_id not in current:
        current[widget_id] = DEFAULT_DASHBOARD_WIDGETS[widget_id].copy()

    current[widget_id]['enabled'] = enabled
    _set_preference(cursor, 'dashboard_widgets', current)

    conn.commit()
    conn.close()

    return success_response({
        "message": f"위젯 '{DEFAULT_DASHBOARD_WIDGETS[widget_id]['title']}' 설정이 변경되었습니다",
        "widget_id": widget_id,
        "enabled": enabled
    })


@router.put("/dashboard/reorder")
@handle_exceptions
async def reorder_widgets(widget_order: List[str]) -> Dict[str, Any]:
    """
    위젯 순서 변경

    Args:
        widget_order: 위젯 ID 목록 (원하는 순서대로)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)

    current = _get_preference(cursor, 'dashboard_widgets', DEFAULT_DASHBOARD_WIDGETS)

    for idx, widget_id in enumerate(widget_order):
        if widget_id in current:
            current[widget_id]['order'] = idx + 1

    _set_preference(cursor, 'dashboard_widgets', current)

    conn.commit()
    conn.close()

    return success_response({
        "message": "위젯 순서가 변경되었습니다",
        "widgets": current
    })


@router.get("/all")
@handle_exceptions
async def get_all_preferences() -> Dict[str, Any]:
    """
    모든 사용자 설정 조회
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_preferences_table(cursor)

    cursor.execute("SELECT key, value FROM user_preferences")
    rows = cursor.fetchall()

    conn.close()

    preferences = {}
    for row in rows:
        try:
            preferences[row['key']] = json.loads(row['value'])
        except (json.JSONDecodeError, TypeError):
            preferences[row['key']] = row['value']

    return success_response(preferences)
