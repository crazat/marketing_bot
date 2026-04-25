"""
Lead → Comment Agent Runtime (Pydantic AI 기반)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

5-tool 결정 루프:
  1. search_qa_repository: BGE-M3 RAG로 표준 답변 후보 검색
  2. draft_korean_comment: ai_generate_korean()로 1차 초안
  3. critique_compliance: 멀티-크리테리아 (compliance + naturalness + tone)
  4. verify_destination_url: comment_verifier.verify_url_async
  5. check_dup_history: 같은 author·URL 중복 컨택 방지

자동 게시 안 함. 모든 결과는 pending_approvals 테이블에 적재 → HITL 승인.

사용:
    from services.agent_runtime import process_lead
    result = await process_lead(lead_id=12345)
    # result: {"status": "pending_approval", "approval_id": 789, ...}
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, "db", "marketing_data.db")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 1: search_qa_repository (BGE-M3 RAG)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def search_qa_repository(lead_text: str, top_k: int = 3) -> List[Dict[str, Any]]:
    """sqlite-vec + BGE-M3로 의미 유사 Q&A 후보 검색."""
    try:
        from services.rag.qa_search import get_qa_engine
        engine = get_qa_engine()
        return engine.search(lead_text, top_k=top_k, candidates=10, rerank=True)
    except Exception as e:
        logger.error(f"[agent] search_qa 실패: {e}")
        return []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 2: draft_korean_comment (ai_client.ai_generate_korean wrap)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_DRAFT_SYSTEM = """당신은 청주 규림한의원의 친근한 마케팅 카피라이터입니다.
타깃 글에 자연스럽게 어울리는 1-2 문장 한국어 댓글을 작성합니다.
규칙:
- 단정적 효과 표현(완치/100%/확실히/반드시) 금지
- 비교/최상급(1등/최고/유일) 금지
- 1인칭 후기 화법(저는/제가/내가 받았어요) 금지
- 의료진 추천 표현 금지
- '도움이 될 수 있다' 같은 가능성 표현 사용
- 친근한 ㅎㅎ/^^ 1개 이내, 자연스러운 톤 유지
"""


def draft_korean_comment(
    lead_text: str,
    qa_matches: List[Dict[str, Any]],
    revision_feedback: Optional[str] = None,
    tone: str = "empathic",
) -> str:
    """초안 댓글 생성. revision_feedback이 있으면 critique 결과 반영."""
    from services.ai_client import ai_generate_korean

    qa_context = ""
    for i, m in enumerate(qa_matches[:3], 1):
        qa_context += f"\n[참고 답변 {i}] {m.get('standard_answer', '')[:200]}"

    feedback = ""
    if revision_feedback:
        feedback = f"\n\n[수정 지시]\n{revision_feedback}\n위 지시를 반드시 반영하여 다시 작성."

    prompt = f"""[타깃 글]
{lead_text[:600]}
{qa_context}
{feedback}

[작성 지시]
타깃 글에 자연스럽게 어울리는 댓글 1-2 문장. 톤: {tone}.
의료광고법 준수 (가능성 표현 사용)."""

    return ai_generate_korean(
        prompt,
        system_prompt=_DRAFT_SYSTEM,
        temperature=0.7,
        max_tokens=400,
        compliance_screen=False,  # 별도 critique tool에서 처리
        ai_disclosure_required=False,  # 최종 단계에서 첨부
        call_site="agent_runtime.draft",
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 3: critique_compliance (multi-criteria)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def critique_compliance(draft: str, lead_text: str = "") -> Dict[str, Any]:
    """3축 평가:
       - compliance: 의료광고법 준수 (regex 기반, 결정적)
       - naturalness: 한국어 자연스러움 (LLM 판정, 0-1)
       - tone_match: 타깃 글 톤과 어울림 (LLM 판정, 0-1)

    Returns:
        {
            "score": 0-1 (가중평균),
            "compliance": {passed, violations, severity},
            "naturalness": {score, comment},
            "tone": {score, comment},
            "issues": [...],  # revise loop에 전달할 문자열 모음
        }
    """
    from services.content_compliance import screen_korean_comment
    from services.ai_client import ai_generate_structured
    from pydantic import BaseModel, Field

    # 1) Compliance (regex, 결정적)
    comp = screen_korean_comment(draft)
    comp_passed = comp.get("passed", False)

    issues: List[str] = []
    if not comp_passed:
        for v in comp.get("violations", []):
            if v.get("severity") == "high":
                issues.append(f"[컴플라이언스 위반] {v.get('category')}: {v.get('recommendation', '')}")

    # 2) Naturalness + tone (LLM judge)
    class Judgement(BaseModel):
        naturalness_score: float = Field(ge=0.0, le=1.0, description="0-1, 한국어 자연스러움")
        naturalness_comment: str = Field(description="짧은 한국어 평가")
        tone_score: float = Field(ge=0.0, le=1.0, description="0-1, 타깃 톤과 어울림")
        tone_comment: str = Field(description="짧은 한국어 평가")

    judge_prompt = f"""다음 한국어 마케팅 댓글을 평가하세요.

[타깃 글] {lead_text[:300] if lead_text else '(미제공)'}

[댓글 초안] {draft[:600]}

평가 기준:
1. naturalness (0-1): 한국어 자연스러움. 1.0 = 사람이 쓴 듯, 0.5 = 어색, 0.0 = AI 티 명백
2. tone_score (0-1): 타깃 글 분위기와 어울림. 1.0 = 자연스럽게 어울림, 0.0 = 어색

JSON으로 응답."""

    judge = ai_generate_structured(
        judge_prompt,
        response_schema=Judgement,
        temperature=0.2,
        max_tokens=400,
    )
    if judge is None:
        judge = Judgement(naturalness_score=0.7, naturalness_comment="자동 평가 실패",
                          tone_score=0.7, tone_comment="자동 평가 실패")

    if judge.naturalness_score < 0.6:
        issues.append(f"[자연스러움 낮음 {judge.naturalness_score:.2f}] {judge.naturalness_comment}")
    if judge.tone_score < 0.6:
        issues.append(f"[톤 부조화 {judge.tone_score:.2f}] {judge.tone_comment}")

    # 가중 합산
    comp_score = 1.0 if comp_passed else 0.0
    overall = comp_score * 0.5 + judge.naturalness_score * 0.25 + judge.tone_score * 0.25

    return {
        "score": round(overall, 3),
        "compliance": {
            "passed": comp_passed,
            "violations": comp.get("violations", []),
            "severity": comp.get("max_severity", "info"),
        },
        "naturalness": {"score": judge.naturalness_score, "comment": judge.naturalness_comment},
        "tone": {"score": judge.tone_score, "comment": judge.tone_comment},
        "issues": issues,
        "passed_threshold": comp_passed and overall >= 0.75,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 4: verify_destination_url (existing comment_verifier wrap)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def verify_destination_url(url: str, platform: str = "auto") -> Dict[str, Any]:
    """기존 비동기 검증기 활용."""
    if not url:
        return {"alive": False, "reason": "no_url"}
    try:
        from services.comment_verifier import verify_url_async
        result = await verify_url_async(url, platform)
        return result if isinstance(result, dict) else {"alive": bool(result)}
    except Exception as e:
        logger.warning(f"[agent] verify_url 실패 ({e}), 사람 검수로 진행")
        return {"alive": True, "warning": f"검증 실패: {e}"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Tool 5: check_dup_history
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def check_dup_history(
    lead_id: int,
    author: str = "",
    url: str = "",
    days: int = 30,
) -> Dict[str, Any]:
    """contact_history + viral_targets에서 중복 컨택 검사."""
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        # author 또는 url 기준 최근 컨택
        cur.execute("""
            SELECT COUNT(*) FROM contact_history
            WHERE (author = ? OR url = ?) AND contacted_at >= datetime('now', ?)
        """, (author, url, f"-{days} days"))
        n = cur.fetchone()[0]
        return {
            "already_contacted": n > 0,
            "count_in_window": n,
            "window_days": days,
        }
    except Exception as e:
        logger.warning(f"[agent] check_dup 실패 (안전상 False 반환): {e}")
        return {"already_contacted": False, "error": str(e)}
    finally:
        if conn:
            conn.close()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인 루프
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_lead(lead_id: int) -> Optional[Dict[str, Any]]:
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # viral_targets에서 lead 정보 fetch (id가 TEXT임에 주의)
        cur.execute("""
            SELECT id, platform, url, title, content_preview, content,
                   matched_keyword, author
            FROM viral_targets WHERE id = ?
        """, (str(lead_id),))
        r = cur.fetchone()
        return dict(r) if r else None
    finally:
        if conn:
            conn.close()


def _enqueue_approval(
    lead_id: int,
    draft: str,
    qa_match_ids: List[int],
    critique: Dict[str, Any],
    url_check: Dict[str, Any],
) -> Optional[int]:
    """pending_approvals 테이블에 적재 → Telegram HITL이 픽업."""
    import json as _json
    from datetime import datetime, timedelta
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        # 테이블 보장 (db_init에서도 만들지만 안전망)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pending_approvals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP,
                lead_id TEXT NOT NULL,
                draft TEXT NOT NULL,
                qa_match_ids TEXT,
                critique_json TEXT,
                url_check_json TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)
        expires = (datetime.utcnow() + timedelta(minutes=30)).isoformat(timespec="seconds")
        cur.execute("""
            INSERT INTO pending_approvals
              (expires_at, lead_id, draft, qa_match_ids, critique_json, url_check_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            expires,
            str(lead_id),
            draft,
            _json.dumps(qa_match_ids),
            _json.dumps(critique, ensure_ascii=False, default=str),
            _json.dumps(url_check, ensure_ascii=False),
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.error(f"[agent] enqueue_approval 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


async def process_lead(
    lead_id: int,
    *,
    max_revisions: int = 2,
    notify_telegram: bool = True,
) -> Dict[str, Any]:
    """Lead 1건의 agent loop 1회 실행.

    Steps:
        1. lead fetch
        2. dup check → abort 시 종료
        3. RAG QA 검색
        4. 초안 → critique → revise (max_revisions번)
        5. URL 검증
        6. pending_approvals 적재 (자동 게시 안 함)
        7. (선택) Telegram 알림
    """
    lead = _fetch_lead(lead_id)
    if not lead:
        return {"status": "abort", "reason": "lead_not_found"}

    lead_text = (lead.get("title") or "") + "\n" + (lead.get("content_preview") or lead.get("content") or "")
    if len(lead_text.strip()) < 10:
        return {"status": "abort", "reason": "empty_lead"}

    # Step 2: dup check
    dup = check_dup_history(lead_id, author=lead.get("author", ""), url=lead.get("url", ""))
    if dup.get("already_contacted"):
        return {"status": "abort", "reason": "already_contacted", "dup": dup}

    # Step 3: RAG search
    qa_matches = search_qa_repository(lead_text, top_k=3)
    if not qa_matches:
        return {"status": "escalate", "reason": "no_qa_match"}

    # Step 4: draft + critique + revise
    feedback: Optional[str] = None
    draft = ""
    critique: Dict[str, Any] = {}
    for attempt in range(max_revisions + 1):
        draft = draft_korean_comment(lead_text, qa_matches, revision_feedback=feedback)
        if draft.startswith("[AI]"):
            return {"status": "abort", "reason": "draft_failed", "error": draft}
        critique = critique_compliance(draft, lead_text)
        if critique.get("passed_threshold"):
            break
        feedback = "\n".join(critique.get("issues", []))
    else:
        return {
            "status": "escalate",
            "reason": "compliance_or_quality_failed",
            "draft": draft,
            "critique": critique,
        }

    # Step 5: URL 검증
    url_check = await verify_destination_url(lead.get("url", ""), lead.get("platform", "auto"))
    if not url_check.get("alive", True):
        return {"status": "abort", "reason": "url_dead", "url_check": url_check}

    # AI 고지 푸터 첨부
    from services.content_compliance import append_ai_disclosure
    final_draft = append_ai_disclosure(draft)

    # Step 6: HITL 큐
    qa_ids = [m.get("id") for m in qa_matches if m.get("id") is not None]
    approval_id = _enqueue_approval(lead_id, final_draft, qa_ids, critique, url_check)

    # Step 7: Telegram 알림 (선택)
    if notify_telegram and approval_id:
        try:
            from services.telegram_approval import notify_pending_approval
            notify_pending_approval(approval_id, lead, final_draft, critique)
        except Exception as e:
            logger.debug(f"[agent] telegram notify 실패 (계속): {e}")

    return {
        "status": "pending_approval",
        "approval_id": approval_id,
        "draft": final_draft,
        "critique_score": critique.get("score"),
        "qa_match_ids": qa_ids,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Approval status 조작 (Telegram callback에서 호출)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def approve_pending(approval_id: int) -> bool:
    return _set_approval_status(approval_id, "approved")


def reject_pending(approval_id: int, reason: str = "") -> bool:
    return _set_approval_status(approval_id, "rejected", reason)


def expire_overdue() -> int:
    """30분 초과한 pending → expired 처리."""
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        cur.execute("""
            UPDATE pending_approvals
            SET status = 'expired'
            WHERE status = 'pending'
              AND expires_at <= datetime('now')
        """)
        conn.commit()
        return cur.rowcount
    except Exception as e:
        logger.warning(f"[agent] expire_overdue 실패: {e}")
        return 0
    finally:
        if conn:
            conn.close()


def _set_approval_status(approval_id: int, status: str, reason: str = "") -> bool:
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        cur.execute("""
            UPDATE pending_approvals
            SET status = ?, critique_json = json_set(COALESCE(critique_json, '{}'), '$.reject_reason', ?)
            WHERE id = ?
        """, (status, reason, approval_id))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        logger.error(f"[agent] set_status 실패: {e}")
        return False
    finally:
        if conn:
            conn.close()
