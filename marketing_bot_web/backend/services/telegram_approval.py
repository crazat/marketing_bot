"""
Telegram HITL Approval — Lead → Comment 워크플로우의 사람 승인 채널
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

agent_runtime.process_lead()가 pending_approvals에 적재 후 호출.
원장이 텔레그램에서 1-tap 승인/수정/기각/Q&A 보기.

callback_data 포맷: "lead_appr:<action>:<approval_id>"
- action: approve | revise | reject | view_qa
"""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# alert_bot 위치는 프로젝트 루트
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

CALLBACK_PREFIX = "lead_appr"


def _format_message(lead: Dict[str, Any], draft: str, critique: Dict[str, Any]) -> str:
    """텔레그램 카드 텍스트 (Markdown). 4096자 한도 고려."""
    title = (lead.get("title") or "").replace("`", "'")[:80]
    url = lead.get("url") or ""
    platform = lead.get("platform") or "?"
    score = critique.get("score", 0.0)
    nat = critique.get("naturalness", {}).get("score", 0.0)
    tone = critique.get("tone", {}).get("score", 0.0)
    comp_passed = critique.get("compliance", {}).get("passed", False)
    comp_emoji = "✅" if comp_passed else "⚠️"

    lines = [
        f"📝 *댓글 승인 요청* (score {score:.2f})",
        f"플랫폼: {platform}",
        f"제목: {title}",
        f"링크: {url}",
        "",
        "📋 *초안*",
        f"```\n{draft[:1500]}\n```",
        "",
        f"{comp_emoji} 컴플라이언스: {'통과' if comp_passed else '경고'}",
        f"💬 자연스러움: {nat:.2f}  |  🎨 톤매칭: {tone:.2f}",
    ]
    return "\n".join(lines)


def _send_inline_4button(message: str, approval_id: int) -> Optional[int]:
    """4-button inline keyboard 전송. 메시지 ID 반환 (DB 저장용).

    [승인 ✅] [수정 ✏️] [기각 🚫] [Q&A 보기 📋]
    """
    try:
        from alert_bot import AlertSystem
        bot = AlertSystem().bot
    except Exception as e:
        logger.warning(f"[telegram_approval] AlertSystem 로드 실패: {e}")
        return None

    # token 없으면 console mock
    if not getattr(bot, "token", None) or not getattr(bot, "chat_id", None):
        print(f"\n[MOCK APPROVAL approval_id={approval_id}]\n{message}\n"
              "[승인 ✅] [수정 ✏️] [기각 🚫] [Q&A 보기 📋]\n" + "-" * 30)
        return None

    import requests
    url = f"https://api.telegram.org/bot{bot.token}/sendMessage"
    inline = {
        "inline_keyboard": [
            [
                {"text": "승인 ✅", "callback_data": f"{CALLBACK_PREFIX}:approve:{approval_id}"},
                {"text": "수정 ✏️", "callback_data": f"{CALLBACK_PREFIX}:revise:{approval_id}"},
            ],
            [
                {"text": "기각 🚫", "callback_data": f"{CALLBACK_PREFIX}:reject:{approval_id}"},
                {"text": "Q&A 보기 📋", "callback_data": f"{CALLBACK_PREFIX}:view_qa:{approval_id}"},
            ],
        ]
    }
    payload = {
        "chat_id": bot.chat_id,
        "text": message,
        "parse_mode": "Markdown",
        "reply_markup": json.dumps(inline),
    }
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            data = r.json()
            return data.get("result", {}).get("message_id")
        # Markdown 실패 시 plain
        payload.pop("parse_mode", None)
        r2 = requests.post(url, json=payload, timeout=10)
        if r2.status_code == 200:
            return r2.json().get("result", {}).get("message_id")
        logger.error(f"[telegram_approval] send 실패: {r.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"[telegram_approval] 전송 오류: {e}")
        return None


def notify_pending_approval(
    approval_id: int,
    lead: Dict[str, Any],
    draft: str,
    critique: Dict[str, Any],
) -> Optional[int]:
    """승인 카드 전송 + telegram_message_id를 pending_approvals에 저장."""
    msg = _format_message(lead, draft, critique)
    msg_id = _send_inline_4button(msg, approval_id)
    if msg_id:
        _store_message_id(approval_id, msg_id)
    return msg_id


def _store_message_id(approval_id: int, message_id: int) -> None:
    import sqlite3
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    db = os.path.join(root, "db", "marketing_data.db")
    conn = None
    try:
        conn = sqlite3.connect(db)
        cur = conn.cursor()
        cur.execute(
            "UPDATE pending_approvals SET telegram_message_id=? WHERE id=?",
            (message_id, approval_id),
        )
        conn.commit()
    except Exception as e:
        logger.warning(f"[telegram_approval] message_id 저장 실패: {e}")
    finally:
        if conn:
            conn.close()


def handle_callback(callback_data: str, callback_message_id: Optional[int] = None) -> Dict[str, Any]:
    """Telegram callback_query handler.

    Args:
        callback_data: "lead_appr:<action>:<approval_id>"
        callback_message_id: 원본 메시지 ID (옵션, 응답 편집용)

    Returns:
        {"ok": bool, "action": str, "result": ...}
    """
    parts = callback_data.split(":")
    if len(parts) != 3 or parts[0] != CALLBACK_PREFIX:
        return {"ok": False, "error": "invalid_callback_data"}
    _, action, approval_id_str = parts
    try:
        approval_id = int(approval_id_str)
    except ValueError:
        return {"ok": False, "error": "invalid_approval_id"}

    from services.agent_runtime import approve_pending, reject_pending

    if action == "approve":
        ok = approve_pending(approval_id)
        return {"ok": ok, "action": action, "approval_id": approval_id}

    if action == "reject":
        ok = reject_pending(approval_id, reason="telegram_user_reject")
        return {"ok": ok, "action": action, "approval_id": approval_id}

    if action == "revise":
        # revise는 별도 채팅 흐름 — 일단 status를 needs_revision으로
        from services.agent_runtime import _set_approval_status
        ok = _set_approval_status(approval_id, "needs_revision", reason="telegram_user_revise")
        return {"ok": ok, "action": action, "approval_id": approval_id,
                "next_step": "원장이 web UI에서 수정 또는 chat에서 추가 지시 입력"}

    if action == "view_qa":
        # Q&A 매칭 정보 반환 (텔레그램에 별도 메시지로 전송 가능)
        return {"ok": True, "action": action, "approval_id": approval_id,
                "info": _fetch_qa_summary(approval_id)}

    return {"ok": False, "error": f"unknown_action:{action}"}


def _fetch_qa_summary(approval_id: int) -> Dict[str, Any]:
    import sqlite3
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    db = os.path.join(root, "db", "marketing_data.db")
    conn = None
    try:
        conn = sqlite3.connect(db)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT qa_match_ids, critique_json FROM pending_approvals WHERE id=?",
                    (approval_id,))
        r = cur.fetchone()
        if not r:
            return {"error": "approval_not_found"}
        qa_ids = json.loads(r["qa_match_ids"]) if r["qa_match_ids"] else []
        if not qa_ids:
            return {"qa_matches": []}
        placeholders = ",".join(["?"] * len(qa_ids))
        cur.execute(f"""
            SELECT id, question_pattern, question_category, standard_answer
            FROM qa_repository WHERE id IN ({placeholders})
        """, qa_ids)
        return {"qa_matches": [dict(row) for row in cur.fetchall()]}
    finally:
        if conn:
            conn.close()
