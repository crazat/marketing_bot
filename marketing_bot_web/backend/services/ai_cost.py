"""
AI 호출 비용 추적
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ai_client.py가 매 호출 끝에 record_call()을 호출 → ai_call_log 테이블.
Logfire span에 attribute로 토큰·비용 추가.

Pricing: 2026-04 기준 (Gemini API)
- gemini-2.5-flash-lite: $0.10 / $0.40 per 1M tok (input/output)
- gemini-3.1-flash-lite-preview: $0.25 / $1.50
- 캐시 hit input: 75-90% 할인 (보수적으로 80% 적용)
"""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

# 단가 표 ($/1M tok)
_PRICING = {
    "gemini-2.5-flash-lite":           {"in": 0.10, "out": 0.40, "cached_in": 0.025},  # 75% off
    "gemini-3.1-flash-lite-preview":   {"in": 0.25, "out": 1.50, "cached_in": 0.0625},
    "gemini-2.5-flash":                {"in": 0.30, "out": 2.50, "cached_in": 0.075},
    "gemini-2.5-pro":                  {"in": 1.25, "out": 10.0, "cached_in": 0.3125},
    "gemini-3-flash":                  {"in": 0.30, "out": 2.50, "cached_in": 0.075},
    "gemini-3-pro":                    {"in": 1.25, "out": 10.0, "cached_in": 0.3125},
}


def calc_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    """단가표 기반 비용 계산. 모델 미지원 시 0 반환."""
    p = _PRICING.get(model)
    if not p:
        # 일반화 — 모델명에 'lite' 있으면 lite 단가
        if "lite" in model.lower():
            p = _PRICING["gemini-2.5-flash-lite"]
        elif "pro" in model.lower():
            p = _PRICING["gemini-2.5-pro"]
        elif "flash" in model.lower():
            p = _PRICING["gemini-2.5-flash"]
        else:
            return 0.0
    fresh_in = max(0, input_tokens - cached_tokens)
    cost = (
        (fresh_in / 1_000_000) * p["in"]
        + (cached_tokens / 1_000_000) * p["cached_in"]
        + (output_tokens / 1_000_000) * p["out"]
    )
    return round(cost, 8)


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, "db", "marketing_data.db")


def record_call(
    *,
    caller_module: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cached_tokens: int = 0,
    latency_ms: Optional[int] = None,
) -> Optional[int]:
    """ai_call_log INSERT. 실패는 silent."""
    cost = calc_cost_usd(model, input_tokens, output_tokens, cached_tokens)
    cache_hit = 1 if cached_tokens > 0 else 0
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ai_call_log
              (caller_module, model, input_tokens, output_tokens, cached_tokens,
               cost_usd, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (caller_module, model, input_tokens, output_tokens, cached_tokens,
              cost, latency_ms, cache_hit))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.debug(f"[ai_cost] record 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


def daily_summary(days: int = 7) -> dict:
    """일별/모델별 비용 요약 — Dashboard 표시용."""
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"""
            SELECT
                date(created_at) as day,
                model,
                COUNT(*) as calls,
                SUM(input_tokens) as in_tok,
                SUM(output_tokens) as out_tok,
                SUM(cached_tokens) as cached_tok,
                SUM(cost_usd) as cost,
                SUM(cache_hit) as cache_hits
            FROM ai_call_log
            WHERE created_at >= datetime('now', '-{int(days)} days')
            GROUP BY day, model
            ORDER BY day DESC, cost DESC
        """)
        rows = [dict(r) for r in cur.fetchall()]
        # 누적
        cur.execute(f"""
            SELECT
                COUNT(*) as total_calls,
                SUM(cost_usd) as total_cost,
                SUM(cache_hit) as total_cache_hits
            FROM ai_call_log
            WHERE created_at >= datetime('now', '-{int(days)} days')
        """)
        totals = dict(cur.fetchone())
        return {"by_day_model": rows, "totals": totals, "window_days": days}
    finally:
        if conn:
            conn.close()


def caller_summary(days: int = 7) -> list:
    """caller_module별 비용 (어떤 기능이 가장 비용 많이 쓰는지)."""
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(f"""
            SELECT caller_module, COUNT(*) as calls, SUM(cost_usd) as cost
            FROM ai_call_log
            WHERE created_at >= datetime('now', '-{int(days)} days')
              AND caller_module IS NOT NULL AND caller_module != ''
            GROUP BY caller_module
            ORDER BY cost DESC
            LIMIT 30
        """)
        return [dict(r) for r in cur.fetchall()]
    finally:
        if conn:
            conn.close()
