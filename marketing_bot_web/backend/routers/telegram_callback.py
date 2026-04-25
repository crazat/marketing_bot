"""
Telegram callback_query webhook receiver.

원장이 텔레그램 inline button 누르면 텔레그램이 이 endpoint로 webhook 전송.
승인/기각/수정 액션을 pending_approvals에 반영.

Setup:
    POST https://api.telegram.org/bot{TOKEN}/setWebhook
      url=https://your-host/api/telegram/webhook

본 라우터는 inbound webhook 수신만 담당. outbound는 services/telegram_approval.py.
"""

from typing import Any, Dict
from fastapi import APIRouter, Request, HTTPException
import logging
import os

from services.telegram_approval import handle_callback

router = APIRouter(prefix="/api/telegram", tags=["telegram"])
logger = logging.getLogger(__name__)


@router.post("/webhook")
async def telegram_webhook(request: Request) -> Dict[str, Any]:
    """Telegram update receiver. callback_query 처리."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_json")

    cq = body.get("callback_query")
    if not cq:
        # 다른 update type — 일단 ok
        return {"ok": True, "skipped": "no_callback_query"}

    callback_data = cq.get("data", "")
    msg = cq.get("message") or {}
    msg_id = msg.get("message_id")

    result = handle_callback(callback_data, callback_message_id=msg_id)

    # answer_callback_query — 사용자에 즉시 토스트 응답
    cq_id = cq.get("id")
    if cq_id:
        _answer_callback_query(cq_id, result)

    return {"ok": result.get("ok", False), "action": result.get("action")}


def _answer_callback_query(callback_query_id: str, result: Dict[str, Any]) -> None:
    """answerCallbackQuery로 텔레그램 진행중 spinner 종료 + toast 표시."""
    import sys, json
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from alert_bot import AlertSystem
        bot = AlertSystem().bot
    except Exception as e:
        logger.warning(f"answerCallbackQuery alert_bot import 실패: {e}")
        return
    if not getattr(bot, "token", None):
        return
    import requests
    text_map = {
        "approve": "✅ 승인 처리됨",
        "reject": "🚫 기각됨",
        "revise": "✏️ 수정 큐로 이동",
        "view_qa": "📋 Q&A 매칭 정보 (별도 메시지)",
    }
    text = text_map.get(result.get("action", ""), "처리 완료")
    if not result.get("ok"):
        text = "❌ 처리 실패"
    try:
        url = f"https://api.telegram.org/bot{bot.token}/answerCallbackQuery"
        requests.post(url, json={
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": False,
        }, timeout=5)
        # view_qa는 추가 메시지로 정보 전송
        if result.get("action") == "view_qa" and result.get("info"):
            qa_matches = result["info"].get("qa_matches", [])
            lines = ["📋 *Q&A 매칭 정보*"]
            for m in qa_matches[:3]:
                lines.append(f"\n• [{m.get('question_category')}]")
                lines.append(f"  Q: {m.get('question_pattern','')[:80]}")
                lines.append(f"  A: {(m.get('standard_answer','') or '')[:140]}")
            requests.post(
                f"https://api.telegram.org/bot{bot.token}/sendMessage",
                json={"chat_id": bot.chat_id, "text": "\n".join(lines), "parse_mode": "Markdown"},
                timeout=10,
            )
    except Exception as e:
        logger.debug(f"answerCallbackQuery 실패: {e}")


@router.get("/health")
def telegram_health() -> Dict[str, Any]:
    """webhook URL 등록 여부 등 헬스 체크용."""
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from alert_bot import AlertSystem
        bot = AlertSystem().bot
        return {
            "telegram_configured": bool(getattr(bot, "token", None) and getattr(bot, "chat_id", None)),
            "mode": "live" if getattr(bot, "token", None) else "mock",
        }
    except Exception as e:
        return {"telegram_configured": False, "error": str(e)}
