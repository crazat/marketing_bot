"""Cost logging for Codex CLI-backed AI calls."""

from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

logger = logging.getLogger(__name__)

_PRICING = {
    "codex-cli": {"in": 5.00, "out": 30.00, "cached_in": 0.50},
    "gpt-5.5": {"in": 5.00, "out": 30.00, "cached_in": 0.50},
    "gpt-5.4": {"in": 2.50, "out": 15.00, "cached_in": 0.25},
    "gpt-5.4-mini": {"in": 0.75, "out": 4.50, "cached_in": 0.075},
    "gpt-5.3-codex-spark": {"in": 1.75, "out": 14.00, "cached_in": 0.175},
    "codex-auto-review": {"in": 2.50, "out": 15.00, "cached_in": 0.25},
}


def _pricing_for(model: str) -> Optional[dict]:
    key = (model or "").strip()
    if key in _PRICING:
        return _PRICING[key]
    lowered = key.lower()
    if "mini" in lowered:
        return _PRICING["gpt-5.4-mini"]
    if "spark" in lowered:
        return _PRICING["gpt-5.3-codex-spark"]
    if lowered.startswith("gpt-5.5"):
        return _PRICING["gpt-5.5"]
    if lowered.startswith("gpt-5.4"):
        return _PRICING["gpt-5.4"]
    if lowered.startswith("codex"):
        return _PRICING["codex-cli"]
    return None


def calc_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
) -> float:
    pricing = _pricing_for(model)
    if not pricing:
        return 0.0
    fresh_in = max(0, input_tokens - cached_tokens)
    cost = (
        (fresh_in / 1_000_000) * pricing["in"]
        + (cached_tokens / 1_000_000) * pricing["cached_in"]
        + (output_tokens / 1_000_000) * pricing["out"]
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
    cost = calc_cost_usd(model, input_tokens, output_tokens, cached_tokens)
    cache_hit = 1 if cached_tokens > 0 else 0
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO ai_call_log
              (caller_module, model, input_tokens, output_tokens, cached_tokens,
               cost_usd, latency_ms, cache_hit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                caller_module,
                model,
                input_tokens,
                output_tokens,
                cached_tokens,
                cost,
                latency_ms,
                cache_hit,
            ),
        )
        conn.commit()
        return cur.lastrowid
    except Exception as exc:
        logger.debug("[ai_cost] record skipped: %s", exc)
        return None
    finally:
        if conn:
            conn.close()


def daily_summary(days: int = 7) -> dict:
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            f"""
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
            """
        )
        rows = [dict(row) for row in cur.fetchall()]
        cur.execute(
            f"""
            SELECT
                COUNT(*) as total_calls,
                SUM(cost_usd) as total_cost,
                SUM(cache_hit) as total_cache_hits
            FROM ai_call_log
            WHERE created_at >= datetime('now', '-{int(days)} days')
            """
        )
        totals = dict(cur.fetchone())
        return {"by_day_model": rows, "totals": totals, "window_days": days}
    finally:
        if conn:
            conn.close()


def caller_summary(days: int = 7) -> list:
    conn = None
    try:
        conn = sqlite3.connect(_db_path())
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT caller_module, COUNT(*) as calls, SUM(cost_usd) as cost
            FROM ai_call_log
            WHERE created_at >= datetime('now', '-{int(days)} days')
              AND caller_module IS NOT NULL AND caller_module != ''
            GROUP BY caller_module
            ORDER BY cost DESC
            LIMIT 30
            """
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        if conn:
            conn.close()
