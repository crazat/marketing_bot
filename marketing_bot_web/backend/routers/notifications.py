"""
Notifications API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 4.2] 알림 시스템
- 중요 이벤트 알림 (순위 변동, 새 리드, 경쟁사 활동)
- 알림 읽음 처리
- 알림 설정

[Marketing Enhancement 2.0] 실시간 알림 시스템
- 텔레그램/카카오톡 알림 설정
- 테스트 발송
- 알림 이력 조회
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from enum import Enum
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


class NotificationType(str, Enum):
    RANK_CHANGE = "rank_change"       # 순위 변동
    NEW_LEAD = "new_lead"             # 새 리드
    COMPETITOR_ACTIVITY = "competitor" # 경쟁사 활동
    SYSTEM = "system"                 # 시스템 알림
    KEYWORD = "keyword"               # 키워드 관련
    VIRAL = "viral"                   # 바이럴 관련


class NotificationPriority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NotificationCreate(BaseModel):
    type: NotificationType
    priority: NotificationPriority = NotificationPriority.MEDIUM
    title: str
    message: str
    link: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


# ============================================
# [Marketing Enhancement 2.0] 알림 설정 모델
# ============================================

class NotificationSettingsUpdate(BaseModel):
    """알림 설정 업데이트 모델"""
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    kakao_enabled: Optional[bool] = None
    kakao_access_token: Optional[str] = None
    rank_drop_threshold: Optional[int] = Field(None, ge=1, le=50)
    new_lead_min_score: Optional[int] = Field(None, ge=0, le=100)
    competitor_activity_alert: Optional[bool] = None
    system_error_alert: Optional[bool] = None
    alert_quiet_start: Optional[str] = None  # HH:MM 형식
    alert_quiet_end: Optional[str] = None    # HH:MM 형식


class TestNotificationRequest(BaseModel):
    """테스트 알림 요청 모델"""
    channel: str = Field(..., pattern="^(telegram|kakao)$")
    message: Optional[str] = "테스트 알림입니다. Marketing Bot에서 발송되었습니다."


def _ensure_notifications_table(cursor):
    """notifications 테이블 생성"""
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            priority TEXT DEFAULT 'medium',
            title TEXT NOT NULL,
            message TEXT,
            link TEXT,
            metadata TEXT,
            is_read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_created ON notifications(created_at DESC)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_type ON notifications(type)")


@router.get("/list")
@handle_exceptions
async def get_notifications(
    unread_only: bool = False,
    notification_type: Optional[NotificationType] = None,
    limit: int = Query(default=50, ge=1, le=200, description="최대 조회 수")
) -> Dict[str, Any]:
    """
    알림 목록 조회

    Args:
        unread_only: 읽지 않은 알림만 조회
        notification_type: 알림 유형 필터
        limit: 최대 개수 (기본 50, 최대 200)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_notifications_table(cursor)
    conn.commit()

    where_clauses = []
    params = []

    if unread_only:
        where_clauses.append("is_read = 0")

    if notification_type:
        where_clauses.append("type = ?")
        params.append(notification_type.value)

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cursor.execute(f"""
        SELECT
            id, type, priority, title, message, link, metadata,
            is_read, created_at
        FROM notifications
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
    """, params + [limit])

    rows = cursor.fetchall()

    # 읽지 않은 알림 수
    cursor.execute("SELECT COUNT(*) FROM notifications WHERE is_read = 0")
    unread_count = cursor.fetchone()[0]

    conn.close()

    notifications = []
    for row in rows:
        notif = dict(row)
        if notif['metadata']:
            try:
                notif['metadata'] = json.loads(notif['metadata'])
            except (json.JSONDecodeError, TypeError):
                notif['metadata'] = {}
        notifications.append(notif)

    return success_response({
        "notifications": notifications,
        "unread_count": unread_count,
        "total": len(notifications)
    })


@router.post("/create")
@handle_exceptions
async def create_notification(notification: NotificationCreate) -> Dict[str, Any]:
    """
    알림 생성 (내부 시스템용)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    _ensure_notifications_table(cursor)

    metadata_json = json.dumps(notification.metadata) if notification.metadata else None

    cursor.execute("""
        INSERT INTO notifications (type, priority, title, message, link, metadata)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        notification.type.value,
        notification.priority.value,
        notification.title,
        notification.message,
        notification.link,
        metadata_json
    ))

    notification_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return success_response({
        "id": notification_id,
        "message": "알림이 생성되었습니다"
    })


@router.put("/{notification_id}/read")
@handle_exceptions
async def mark_as_read(notification_id: int) -> Dict[str, Any]:
    """
    알림 읽음 처리
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE notifications SET is_read = 1 WHERE id = ?",
        (notification_id,)
    )

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    conn.commit()
    conn.close()

    return success_response({"message": "알림이 읽음 처리되었습니다"})


@router.put("/read-all")
@handle_exceptions
async def mark_all_as_read() -> Dict[str, Any]:
    """
    모든 알림 읽음 처리
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
    updated_count = cursor.rowcount

    conn.commit()
    conn.close()

    return success_response({
        "message": f"{updated_count}개 알림이 읽음 처리되었습니다",
        "count": updated_count
    })


@router.delete("/{notification_id}")
@handle_exceptions
async def delete_notification(notification_id: int) -> Dict[str, Any]:
    """
    알림 삭제
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    cursor.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))

    if cursor.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="알림을 찾을 수 없습니다")

    conn.commit()
    conn.close()

    return success_response({"message": "알림이 삭제되었습니다"})


@router.delete("/clear-old")
@handle_exceptions
async def clear_old_notifications(days: int = 30) -> Dict[str, Any]:
    """
    오래된 알림 정리

    Args:
        days: N일 이전 알림 삭제 (기본 30일)
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    threshold = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

    cursor.execute(
        "DELETE FROM notifications WHERE created_at < ? AND is_read = 1",
        (threshold,)
    )
    deleted_count = cursor.rowcount

    conn.commit()
    conn.close()

    return success_response({
        "message": f"{deleted_count}개 오래된 알림이 삭제되었습니다",
        "count": deleted_count
    })


@router.get("/auto-generate")
@handle_exceptions
async def auto_generate_notifications() -> Dict[str, Any]:
    """
    자동 알림 생성 (순위 변동, 새 리드 등 감지)

    주기적으로 호출하여 중요 이벤트 감지 및 알림 생성
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    _ensure_notifications_table(cursor)
    generated = []

    # 1. 순위 변동 감지 (최근 24시간)
    try:
        cursor.execute("""
            SELECT r1.keyword, r1.rank as current_rank, r2.rank as prev_rank
            FROM rank_history r1
            JOIN rank_history r2 ON r1.keyword = r2.keyword
            WHERE r1.date = date('now')
              AND r2.date = date('now', '-1 day')
              AND r1.rank != r2.rank
              AND r1.status = 'found'
              AND r2.status = 'found'
            ORDER BY ABS(r1.rank - r2.rank) DESC
            LIMIT 5
        """)
        rank_changes = cursor.fetchall()

        for change in rank_changes:
            diff = change['prev_rank'] - change['current_rank']
            if abs(diff) >= 3:  # 3순위 이상 변동만 알림
                priority = 'high' if diff > 0 else 'medium'
                direction = "상승" if diff > 0 else "하락"
                emoji = "📈" if diff > 0 else "📉"

                # 중복 알림 방지
                cursor.execute("""
                    SELECT id FROM notifications
                    WHERE type = 'rank_change'
                      AND title LIKE ?
                      AND created_at > datetime('now', '-1 hour')
                """, (f"%{change['keyword']}%",))

                if not cursor.fetchone():
                    cursor.execute("""
                        INSERT INTO notifications (type, priority, title, message, link)
                        VALUES (?, ?, ?, ?, ?)
                    """, (
                        'rank_change',
                        priority,
                        f"{emoji} {change['keyword']} 순위 {direction}",
                        f"{change['prev_rank']}위 → {change['current_rank']}위 ({abs(diff)}순위 {direction})",
                        "/battle"
                    ))
                    generated.append(f"순위 변동: {change['keyword']}")
    except Exception as e:
        print(f"[Notifications] 순위 변동 감지 오류: {e}")

    # 2. 새 고점수 리드 감지 (최근 6시간)
    try:
        cursor.execute("""
            SELECT COUNT(*) as new_leads
            FROM mentions
            WHERE (created_at > datetime('now', '-6 hours')
               OR scraped_at > datetime('now', '-6 hours'))
              AND status = 'pending'
        """)
        new_lead_count = cursor.fetchone()['new_leads']

        if new_lead_count >= 5:
            cursor.execute("""
                SELECT id FROM notifications
                WHERE type = 'new_lead'
                  AND created_at > datetime('now', '-6 hours')
            """)
            if not cursor.fetchone():
                cursor.execute("""
                    INSERT INTO notifications (type, priority, title, message, link)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    'new_lead',
                    'high',
                    f"🎯 새 리드 {new_lead_count}개 발견",
                    f"최근 6시간 동안 {new_lead_count}개의 새 리드가 발견되었습니다",
                    "/leads"
                ))
                generated.append(f"새 리드: {new_lead_count}개")
    except Exception as e:
        print(f"[Notifications] 새 리드 감지 오류: {e}")

    # 3. S급 키워드 발견 (최근 24시간) - [성능 개선] 배치 처리로 N+1 쿼리 제거
    try:
        cursor.execute("""
            SELECT keyword, search_volume
            FROM keyword_insights
            WHERE grade = 'S'
              AND created_at > datetime('now', '-24 hours')
            ORDER BY created_at DESC
            LIMIT 3
        """)
        new_s_keywords = cursor.fetchall()

        if new_s_keywords:
            # 1단계: 한 번에 기존 알림 조회 (N+1 쿼리 대신 단일 쿼리)
            cursor.execute("""
                SELECT title FROM notifications
                WHERE type = 'keyword'
                  AND created_at > datetime('now', '-24 hours')
            """)
            existing_titles = {row['title'] for row in cursor.fetchall()}

            # 2단계: 삽입할 알림 데이터 준비
            notifications_to_insert = []
            for kw in new_s_keywords:
                title = f"⭐ S급 키워드 발견: {kw['keyword']}"
                # 기존 알림에 없는 경우만 추가
                if title not in existing_titles:
                    notifications_to_insert.append((
                        'keyword',
                        'high',
                        title,
                        f"검색량 {kw['search_volume']:,}의 S급 키워드가 발견되었습니다",
                        "/pathfinder"
                    ))
                    generated.append(f"S급 키워드: {kw['keyword']}")

            # 3단계: 배치 INSERT (한 번의 쿼리로 모두 삽입)
            if notifications_to_insert:
                cursor.executemany("""
                    INSERT INTO notifications (type, priority, title, message, link)
                    VALUES (?, ?, ?, ?, ?)
                """, notifications_to_insert)
    except Exception as e:
        print(f"[Notifications] S급 키워드 감지 오류: {e}")

    conn.commit()
    conn.close()

    return success_response({
        "message": f"{len(generated)}개 알림이 생성되었습니다",
        "generated": generated
    })


# ============================================
# [Marketing Enhancement 2.0] 실시간 알림 시스템 API
# ============================================

@router.get("/settings")
@handle_exceptions
async def get_notification_settings() -> Dict[str, Any]:
    """
    알림 설정 조회

    텔레그램/카카오톡 알림 설정 및 임계값 설정을 반환합니다.
    민감한 토큰 정보는 마스킹 처리됩니다.
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # notification_settings 테이블 확인/생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            telegram_enabled INTEGER DEFAULT 0,
            telegram_bot_token TEXT,
            telegram_chat_id TEXT,
            kakao_enabled INTEGER DEFAULT 0,
            kakao_rest_api_key TEXT,
            kakao_access_token TEXT,
            rank_drop_threshold INTEGER DEFAULT 5,
            new_lead_min_score INTEGER DEFAULT 70,
            competitor_activity_alert INTEGER DEFAULT 1,
            system_error_alert INTEGER DEFAULT 1,
            alert_quiet_start TEXT DEFAULT '22:00',
            alert_quiet_end TEXT DEFAULT '08:00',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # [Phase 7] SELECT * 제거
    columns = """id, telegram_enabled, telegram_bot_token, telegram_chat_id,
                 kakao_enabled, kakao_rest_api_key, kakao_access_token,
                 rank_drop_threshold, new_lead_min_score, competitor_activity_alert,
                 system_error_alert, alert_quiet_start, alert_quiet_end, created_at, updated_at"""
    cursor.execute(f"SELECT {columns} FROM notification_settings LIMIT 1")
    row = cursor.fetchone()

    if not row:
        # 기본 설정 생성
        cursor.execute("""
            INSERT INTO notification_settings (telegram_enabled, kakao_enabled)
            VALUES (0, 0)
        """)
        conn.commit()
        cursor.execute(f"SELECT {columns} FROM notification_settings LIMIT 1")
        row = cursor.fetchone()

    conn.close()

    settings = dict(row)

    # 토큰 마스킹
    if settings.get('telegram_bot_token'):
        token = settings['telegram_bot_token']
        settings['telegram_bot_token_masked'] = f"{token[:10]}...{token[-4:]}" if len(token) > 14 else "***"
        settings['telegram_bot_token'] = None  # 실제 값은 반환하지 않음

    if settings.get('kakao_access_token'):
        token = settings['kakao_access_token']
        settings['kakao_access_token_masked'] = f"{token[:10]}...{token[-4:]}" if len(token) > 14 else "***"
        settings['kakao_access_token'] = None

    if settings.get('kakao_rest_api_key'):
        settings['kakao_rest_api_key'] = None

    return success_response(settings)


@router.put("/settings")
@handle_exceptions
async def update_notification_settings(settings: NotificationSettingsUpdate) -> Dict[str, Any]:
    """
    알림 설정 업데이트

    텔레그램/카카오톡 알림 설정을 업데이트합니다.
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    cursor = conn.cursor()

    # 업데이트할 필드 구성
    update_fields = []
    params = []

    settings_dict = settings.model_dump(exclude_none=True)

    for key, value in settings_dict.items():
        if isinstance(value, bool):
            value = 1 if value else 0
        update_fields.append(f"{key} = ?")
        params.append(value)

    if not update_fields:
        conn.close()
        return success_response({"message": "변경사항이 없습니다"})

    # updated_at 추가
    update_fields.append("updated_at = CURRENT_TIMESTAMP")

    # 업데이트 실행
    cursor.execute(f"""
        UPDATE notification_settings
        SET {', '.join(update_fields)}
        WHERE id = (SELECT id FROM notification_settings LIMIT 1)
    """, params)

    # 설정이 없으면 새로 생성
    if cursor.rowcount == 0:
        # 먼저 기본 설정 생성
        cursor.execute("INSERT INTO notification_settings (telegram_enabled, kakao_enabled) VALUES (0, 0)")
        # 다시 업데이트
        cursor.execute(f"""
            UPDATE notification_settings
            SET {', '.join(update_fields)}
            WHERE id = (SELECT id FROM notification_settings LIMIT 1)
        """, params)

    conn.commit()
    conn.close()

    # 알림 서비스 설정 새로고침
    try:
        from services.notification_sender import get_notification_sender
        sender = get_notification_sender()
        sender.reload_settings()
    except Exception as e:
        print(f"[Notifications] 알림 서비스 설정 새로고침 오류: {e}")

    return success_response({"message": "알림 설정이 업데이트되었습니다"})


@router.post("/test-telegram")
@handle_exceptions
async def test_telegram_notification(request: TestNotificationRequest = None) -> Dict[str, Any]:
    """
    텔레그램 테스트 알림 발송

    텔레그램 설정이 올바르게 되어 있는지 확인합니다.
    """
    try:
        from services.notification_sender import get_notification_sender

        sender = get_notification_sender()
        sender.reload_settings()

        message = request.message if request else "테스트 알림입니다. Marketing Bot에서 발송되었습니다."

        result = await sender.send_telegram(
            title="Marketing Bot 테스트",
            message=message,
            notification_type="test"
        )

        if result.get('success'):
            return success_response({
                "message": "텔레그램 테스트 알림이 발송되었습니다",
                "message_id": result.get('message_id')
            })
        else:
            return error_response(result.get('error', '알 수 없는 오류'))

    except ImportError:
        return error_response("알림 서비스를 로드할 수 없습니다")
    except Exception as e:
        return error_response(str(e))


@router.post("/test-kakao")
@handle_exceptions
async def test_kakao_notification(request: TestNotificationRequest = None) -> Dict[str, Any]:
    """
    카카오톡 테스트 알림 발송

    카카오톡 설정이 올바르게 되어 있는지 확인합니다.
    """
    try:
        from services.notification_sender import get_notification_sender

        sender = get_notification_sender()
        sender.reload_settings()

        message = request.message if request else "테스트 알림입니다. Marketing Bot에서 발송되었습니다."

        result = await sender.send_kakao(
            title="Marketing Bot 테스트",
            message=message,
            notification_type="test"
        )

        if result.get('success'):
            return success_response({
                "message": "카카오톡 테스트 알림이 발송되었습니다"
            })
        else:
            return error_response(result.get('error', '알 수 없는 오류'))

    except ImportError:
        return error_response("알림 서비스를 로드할 수 없습니다")
    except Exception as e:
        return error_response(str(e))


@router.get("/history")
@handle_exceptions
async def get_notification_history(
    channel: Optional[str] = None,
    notification_type: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """
    알림 발송 이력 조회

    Args:
        channel: 채널 필터 ('telegram', 'kakao')
        notification_type: 알림 유형 필터
        limit: 최대 개수
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # notification_history 테이블 확인/생성
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            notification_type TEXT NOT NULL,
            channel TEXT NOT NULL,
            title TEXT NOT NULL,
            message TEXT,
            metadata TEXT DEFAULT '{}',
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    # 쿼리 구성
    where_clauses = []
    params = []

    if channel:
        where_clauses.append("channel = ?")
        params.append(channel)

    if notification_type:
        where_clauses.append("notification_type = ?")
        params.append(notification_type)

    where_clause = "WHERE " + " AND ".join(where_clauses) if where_clauses else ""

    cursor.execute(f"""
        SELECT id, notification_type, channel, title, message, status, error_message, sent_at
        FROM notification_history
        {where_clause}
        ORDER BY sent_at DESC
        LIMIT ?
    """, params + [limit])

    rows = cursor.fetchall()

    # 통계
    cursor.execute("SELECT COUNT(*) FROM notification_history WHERE status = 'sent'")
    sent_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM notification_history WHERE status = 'failed'")
    failed_count = cursor.fetchone()[0]

    conn.close()

    history = [dict(row) for row in rows]

    return success_response({
        "history": history,
        "total": len(history),
        "stats": {
            "sent": sent_count,
            "failed": failed_count
        }
    })


@router.post("/trigger-check")
@handle_exceptions
async def trigger_notification_check() -> Dict[str, Any]:
    """
    알림 트리거 수동 실행

    순위 급락, 신규 Hot Lead, 경쟁사 활동 등을 체크하고
    조건에 맞으면 알림을 발송합니다.
    """
    try:
        from services.notification_trigger import run_notification_checks

        results = await run_notification_checks()

        total_alerts = sum(len(v) for v in results.values())

        return success_response({
            "message": f"{total_alerts}개 알림이 발송되었습니다",
            "results": {
                "rank_drops": len(results.get('rank_drops', [])),
                "new_leads": len(results.get('new_leads', [])),
                "competitor_activity": len(results.get('competitor_activity', []))
            }
        })

    except ImportError:
        return error_response("알림 트리거 서비스를 로드할 수 없습니다")
    except Exception as e:
        return error_response(str(e))
