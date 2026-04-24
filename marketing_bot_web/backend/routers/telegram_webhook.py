"""
Telegram Webhook API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 V2-2] 텔레그램 인라인 키보드 콜백 수신

텔레그램에서 [승인] [수정] [거부] 버튼 클릭 시
callback_query를 수신하여 해당 작업을 처리합니다.

설정: 텔레그램 Bot API에 webhook URL 등록 필요
  https://api.telegram.org/bot{TOKEN}/setWebhook?url=https://your-domain/api/telegram/webhook
"""

from fastapi import APIRouter, Request, HTTPException
from typing import Dict, Any
import sys
import os
import json
import sqlite3
import logging
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Dict[str, str]:
    """
    텔레그램 webhook 수신 엔드포인트

    인라인 키보드 콜백 데이터 형식:
    - "review_response:approve:123"  → 리뷰 응답 ID 123 승인
    - "review_response:revise:123"   → 리뷰 응답 ID 123 수정 요청
    - "review_response:reject:123"   → 리뷰 응답 ID 123 거부
    - "content_publish:approve:456"  → 콘텐츠 ID 456 게시 승인
    """
    try:
        body = await request.json()

        # 콜백 쿼리 처리
        callback_query = body.get("callback_query")
        if not callback_query:
            return {"status": "ok"}

        callback_data = callback_query.get("data", "")
        callback_id = callback_query.get("id", "")
        user = callback_query.get("from", {})
        user_name = user.get("first_name", "Unknown")

        logger.info(f"📱 텔레그램 콜백: {callback_data} (from: {user_name})")

        # 콜백 데이터 파싱: "prefix:action:item_id"
        parts = callback_data.split(":")
        if len(parts) != 3:
            await _answer_callback(callback_id, "잘못된 요청입니다.")
            return {"status": "error", "reason": "invalid callback data"}

        prefix, action, item_id_str = parts

        try:
            item_id = int(item_id_str)
        except ValueError:
            await _answer_callback(callback_id, "잘못된 ID입니다.")
            return {"status": "error"}

        # 라우팅
        if prefix == "review_response":
            result = await _handle_review_callback(action, item_id, user_name)
        elif prefix == "content_publish":
            result = await _handle_content_callback(action, item_id, user_name)
        else:
            result = {"message": f"알 수 없는 접두사: {prefix}"}

        # 텔레그램에 콜백 응답
        await _answer_callback(callback_id, result.get("message", "처리 완료"))

        return {"status": "ok", "result": result}

    except Exception as e:
        logger.error(f"텔레그램 webhook 오류: {e}", exc_info=True)
        return {"status": "error"}


async def _handle_review_callback(action: str, review_id: int, user_name: str) -> Dict[str, str]:
    """리뷰 응답 승인/수정/거부 처리"""
    db = DatabaseManager()
    conn = None
    try:
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        status_map = {
            "approve": "approved",
            "revise": "revision_requested",
            "reject": "dismissed",
        }

        new_status = status_map.get(action)
        if not new_status:
            return {"message": f"알 수 없는 액션: {action}"}

        cursor.execute("""
            UPDATE review_responses
            SET status = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_status, review_id))

        conn.commit()

        action_emoji = {"approve": "✅", "revise": "✏️", "reject": "❌"}.get(action, "")
        action_text = {"approve": "승인됨", "revise": "수정 요청", "reject": "거부됨"}.get(action, action)

        message = f"{action_emoji} 리뷰 응답 #{review_id} {action_text} (by {user_name})"
        logger.info(message)
        return {"message": message}

    except Exception as e:
        logger.error(f"리뷰 콜백 처리 실패: {e}")
        return {"message": f"처리 실패: {str(e)}"}
    finally:
        if conn:
            conn.close()


async def _handle_content_callback(action: str, content_id: int, user_name: str) -> Dict[str, str]:
    """콘텐츠 게시 승인/수정/거부 처리"""
    action_emoji = {"approve": "✅", "revise": "✏️", "reject": "❌"}.get(action, "")
    action_text = {"approve": "게시 승인", "revise": "수정 요청", "reject": "게시 거부"}.get(action, action)

    message = f"{action_emoji} 콘텐츠 #{content_id} {action_text} (by {user_name})"
    logger.info(message)
    return {"message": message}


async def _answer_callback(callback_id: str, text: str):
    """텔레그램 콜백 쿼리 응답 (알림 팝업)"""
    try:
        import httpx

        project_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        config_path = os.path.join(project_root, "config", "config.json")

        token = ""
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                token = config.get("telegram", {}).get("bot_token", "")

        if not token:
            return

        url = f"https://api.telegram.org/bot{token}/answerCallbackQuery"
        async with httpx.AsyncClient() as client:
            await client.post(url, json={
                "callback_query_id": callback_id,
                "text": text,
                "show_alert": False,
            }, timeout=5.0)

    except Exception as e:
        logger.debug(f"콜백 응답 실패: {e}")
