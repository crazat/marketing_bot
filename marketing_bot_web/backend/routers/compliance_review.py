"""
Weekly Compliance Review Queue API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ai_korean_screen_log에 쌓인 자동 게이트 결과를 사람이 검수.
3-button 라벨 (correct / false_positive / false_negative) → screen_review 테이블.

4주 누적 후 게이트 precision/recall 측정 + 프롬프트 튜닝 시그널.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel, Field
import sqlite3
import os
import random
from datetime import datetime, timedelta

router = APIRouter(prefix="/api/compliance-review", tags=["compliance"])


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(here))),
                        "db", "marketing_data.db")


@router.get("/queue")
def get_review_queue(
    limit: int = Query(default=20, ge=1, le=100),
    days: int = Query(default=7, ge=1, le=90),
    sample_balanced: bool = Query(default=True, description="차단/통과 균형 샘플링"),
) -> Dict[str, Any]:
    """검수 대기 샘플 — 차단/통과 각각 절반씩 무작위.

    이미 screen_review에 라벨된 항목은 제외.
    """
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
        # 이미 라벨된 ID 제외
        cur.execute("SELECT screen_log_id FROM screen_review")
        labeled = {r["screen_log_id"] for r in cur.fetchall()}

        if sample_balanced:
            half = max(1, limit // 2)
            cur.execute("""
                SELECT * FROM ai_korean_screen_log
                WHERE created_at >= ? AND passed = 1
                ORDER BY RANDOM() LIMIT ?
            """, (cutoff, half * 3))
            passed_pool = [dict(r) for r in cur.fetchall() if r["id"] not in labeled]
            cur.execute("""
                SELECT * FROM ai_korean_screen_log
                WHERE created_at >= ? AND passed = 0
                ORDER BY RANDOM() LIMIT ?
            """, (cutoff, half * 3))
            blocked_pool = [dict(r) for r in cur.fetchall() if r["id"] not in labeled]
            samples = passed_pool[:half] + blocked_pool[:half]
            random.shuffle(samples)
        else:
            cur.execute("""
                SELECT * FROM ai_korean_screen_log
                WHERE created_at >= ?
                ORDER BY RANDOM() LIMIT ?
            """, (cutoff, limit * 2))
            pool = [dict(r) for r in cur.fetchall() if r["id"] not in labeled]
            samples = pool[:limit]
        return {"samples": samples, "n": len(samples)}
    finally:
        conn.close()


class LabelRequest(BaseModel):
    screen_log_id: int
    label: str = Field(pattern="^(correct|false_positive|false_negative)$")
    reasoning: Optional[str] = None
    reviewer: str = "owner"


@router.post("/label")
def submit_label(req: LabelRequest) -> Dict[str, Any]:
    """1-click 라벨 제출."""
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.cursor()
        # 중복 라벨 방지
        cur.execute("SELECT 1 FROM screen_review WHERE screen_log_id=?", (req.screen_log_id,))
        if cur.fetchone():
            raise HTTPException(status_code=409, detail="이미 라벨된 항목")
        cur.execute("""
            INSERT INTO screen_review (screen_log_id, label, reasoning, reviewer)
            VALUES (?, ?, ?, ?)
        """, (req.screen_log_id, req.label, req.reasoning or "", req.reviewer))
        conn.commit()
        return {"ok": True, "id": cur.lastrowid}
    finally:
        conn.close()


@router.get("/metrics")
def get_metrics(days: int = Query(default=30, ge=1, le=180)) -> Dict[str, Any]:
    """Precision/Recall 추정 (사람 라벨 기반)."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat(timespec="seconds")
        cur.execute(f"""
            SELECT sr.label, akl.passed
            FROM screen_review sr
            JOIN ai_korean_screen_log akl ON sr.screen_log_id = akl.id
            WHERE sr.created_at >= ?
        """, (cutoff,))
        rows = cur.fetchall()

        # passed=0(차단) + label=correct → True Positive
        # passed=0 + label=false_positive → False Positive (과차단)
        # passed=1(통과) + label=false_negative → False Negative (누락)
        # passed=1 + label=correct → True Negative
        tp = sum(1 for r in rows if r["passed"] == 0 and r["label"] == "correct")
        fp = sum(1 for r in rows if r["passed"] == 0 and r["label"] == "false_positive")
        fn = sum(1 for r in rows if r["passed"] == 1 and r["label"] == "false_negative")
        tn = sum(1 for r in rows if r["passed"] == 1 and r["label"] == "correct")

        precision = tp / (tp + fp) if (tp + fp) else None
        recall = tp / (tp + fn) if (tp + fn) else None
        accuracy = (tp + tn) / (tp + fp + fn + tn) if rows else None

        return {
            "n_labeled": len(rows),
            "true_positive": tp,
            "false_positive": fp,
            "false_negative": fn,
            "true_negative": tn,
            "precision": round(precision, 3) if precision is not None else None,
            "recall": round(recall, 3) if recall is not None else None,
            "accuracy": round(accuracy, 3) if accuracy is not None else None,
            "window_days": days,
            "warning": ("FP율 >15% — 프롬프트 완화 검토 필요"
                        if precision is not None and precision < 0.85 else None),
        }
    finally:
        conn.close()
