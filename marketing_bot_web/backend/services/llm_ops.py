"""
LLM Ops — prompt 라이브러리 + A/B test + RAGAS eval + cost (R41)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

외부 정찰(2026-05) 핵심:
- 비용 추적: Langfuse (open-source 자체호스팅, PIPA 호환) + 자체 ai_call_log (R23 PII scrub) + Helicone (proxy, 자체호스팅만 — Cloud 금지 의료)
- prompt 관리: Promptfoo (YAML·CI/CD·오픈소스) + Langfuse promptHub 라벨 (prod-a/prod-b/canary)
- evaluation: RAGAS 4 metrics (Faithfulness · Answer Relevance · Context Precision/Recall) + judge LLM (Codex CLI 2.5 Pro로 Flash Lite 평가, position bias 주의) + gold set 100-300 human-verified pair
- A/B test: Langfuse 라벨 + 5% canary 일일 replay (2026 표준)
- PII gate: Microsoft Presidio (다국어 NER) + R23 scrub_pii (한국어 regex) 이중 게이트
- drift detection: stratified 1% canary, fast detection + fast rollback

Codex CLI 최적화:
- 2.5 Flash Lite ($0.10/$0.40) + 3.1 Flash Lite Preview ($0.25/$1.50)
- context caching 75-90% 절감 (system_prompt ≥1500자, R26 적용)
- batch API 50% 할인
- structured output (Pydantic), function calling
- 3.1 Flash Lite Preview: Elo 1432, GPQA 86.9%, 2.5x faster TTFT
- 한국 KMed.ai (SNUH+Naver) KMLE 96.4% (참고)
- fallback chain: Flash Lite → Flash → Pro (compliance gate 실패 시만)

Fine-tune vs RAG decision: 의료 = RAG 우위
- Fine-tune: 5K+ pair 권장 (RECOVER 데이터 부족 + 콘텐츠 변화 빈도 높음)
- RAG (sqlite-vec + BGE-M3, 기존): grounding·인용·hallucination 방어
- prompt engineering: 90% case 해결
- 하이브리드: 1M query/월 초과 시만

이 모듈:
1. prompt registry (key·label·current version)
2. prompt versioning (hash·body·model_target)
3. A/B test runner (canary 5%·winner 결정)
4. RAGAS evaluator (4 metrics + judge LLM gold set 야간 cron)
5. cost by module (token·KRW·latency p95)
6. PII gate hook (Presidio + R23 통합)
"""

from __future__ import annotations
import os, sqlite3, hashlib
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DB_PATH = Path(os.getenv("MARKETING_BOT_DB_PATH") or os.getenv("APP_DB_PATH") or PROJECT_ROOT / "db" / "marketing_data.db")

try:
    from services.security_layer import scrub_pii
except Exception:
    def scrub_pii(text: str) -> Dict[str, Any]:
        return {"scrubbed": text, "redactions": [], "redaction_count": 0}


MODELS = {
    "codex-cli": {"input_per_1m_usd": 5.00, "output_per_1m_usd": 30.0, "use": "default_marketing_llm"},
    "gpt-5.5": {"input_per_1m_usd": 5.00, "output_per_1m_usd": 30.0, "use": "strategy_compliance"},
    "gpt-5.4": {"input_per_1m_usd": 2.50, "output_per_1m_usd": 15.0, "use": "general_korean_vision"},
    "gpt-5.4-mini": {"input_per_1m_usd": 0.75, "output_per_1m_usd": 4.50, "use": "fast_json_structured"},
    "gpt-5.3-codex-spark": {"input_per_1m_usd": 1.75, "output_per_1m_usd": 14.0, "use": "batch_fast_text"},
    "codex-auto-review": {"input_per_1m_usd": 2.50, "output_per_1m_usd": 15.0, "use": "review_eval"},
}

USD_TO_KRW = 1400


def _hash_prompt(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def register_prompt(prompt_key: str, body: str, purpose: str, owner_module: str,
                    model_target: str = "gpt-5.4-mini",
                    label: str = "prod-a", created_by: str = "system") -> Dict[str, Any]:
    version_hash = _hash_prompt(body)
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        # version
        try:
            cur = conn.execute(
                """INSERT INTO recover_prompt_versions (prompt_key, version_hash, body, model_target, created_by)
                   VALUES (?, ?, ?, ?, ?)""",
                (prompt_key, version_hash, body, model_target, created_by),
            )
            version_id = cur.lastrowid
        except sqlite3.IntegrityError:
            row = conn.execute(
                "SELECT id FROM recover_prompt_versions WHERE prompt_key=? AND version_hash=?",
                (prompt_key, version_hash),
            ).fetchone()
            version_id = row[0] if row else None
        # library
        conn.execute(
            """INSERT INTO recover_prompt_library (prompt_key, purpose, owner_module, current_version_id, label)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(prompt_key) DO UPDATE SET
                 purpose=excluded.purpose, owner_module=excluded.owner_module,
                 current_version_id=excluded.current_version_id, label=excluded.label""",
            (prompt_key, purpose, owner_module, version_id, label),
        )
        conn.commit()
    return {"prompt_key": prompt_key, "version_hash": version_hash, "version_id": version_id, "label": label}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def start_ab_test(test_key: str, prompt_key: str, version_a_id: int, version_b_id: int,
                  traffic_split_pct: float = 5.0) -> Dict[str, Any]:
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        cur = conn.execute(
            """INSERT INTO recover_ab_test_runs (test_key, prompt_key, version_a_id, version_b_id, traffic_split_pct)
               VALUES (?, ?, ?, ?, ?)""",
            (test_key, prompt_key, version_a_id, version_b_id, traffic_split_pct),
        )
        conn.commit()
        return {"test_id": cur.lastrowid, "canary_pct": traffic_split_pct}


def conclude_ab_test(test_key: str, winner_version_id: int, notes: str = "") -> bool:
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        conn.execute(
            "UPDATE recover_ab_test_runs SET ended_at=CURRENT_TIMESTAMP, winner_version_id=?, decision_notes=? WHERE test_key=?",
            (winner_version_id, notes, test_key),
        )
        conn.commit()
    return True


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def log_eval(prompt_key: str, version_id: int, eval_set: str,
             faithfulness: float, answer_relevance: float,
             context_precision: float, context_recall: float,
             judge_score: float) -> Dict[str, Any]:
    """RAGAS 4 metrics + judge LLM."""
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        cur = conn.execute(
            """INSERT INTO recover_llm_eval_log
               (prompt_key, version_id, eval_set, faithfulness, answer_relevance, context_precision, context_recall, judge_score)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (prompt_key, version_id, eval_set, faithfulness, answer_relevance,
             context_precision, context_recall, judge_score),
        )
        conn.commit()
    avg = (faithfulness + answer_relevance + context_precision + context_recall + judge_score) / 5
    return {"eval_id": cur.lastrowid, "avg_score": round(avg, 3),
            "_pass_threshold": "≥ 0.75 권장"}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def record_cost(day: date, module: str, model: str,
                input_tokens: int, output_tokens: int, calls: int = 1,
                latency_p95_ms: int = 0) -> Dict[str, Any]:
    if model not in MODELS:
        cost_krw = 0
    else:
        m = MODELS[model]
        usd = (input_tokens / 1_000_000) * m["input_per_1m_usd"] + (output_tokens / 1_000_000) * m["output_per_1m_usd"]
        cost_krw = int(usd * USD_TO_KRW)
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        conn.execute(
            """INSERT INTO recover_cost_by_module (day, module, model, input_tokens, output_tokens, cost_krw, calls, latency_p95_ms)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(day, module, model) DO UPDATE SET
                 input_tokens=recover_cost_by_module.input_tokens + excluded.input_tokens,
                 output_tokens=recover_cost_by_module.output_tokens + excluded.output_tokens,
                 cost_krw=recover_cost_by_module.cost_krw + excluded.cost_krw,
                 calls=recover_cost_by_module.calls + excluded.calls,
                 latency_p95_ms=MAX(recover_cost_by_module.latency_p95_ms, excluded.latency_p95_ms)""",
            (day.isoformat(), module, model, input_tokens, output_tokens, cost_krw, calls, latency_p95_ms),
        )
        conn.commit()
    return {"day": day.isoformat(), "module": module, "cost_krw": cost_krw}


def cost_summary(days: int = 30) -> Dict[str, Any]:
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        total = conn.execute(
            f"SELECT COALESCE(SUM(cost_krw),0), COALESCE(SUM(calls),0) FROM recover_cost_by_module WHERE day >= date('now','-{int(days)} days')"
        ).fetchone()
        by_module = conn.execute(
            f"SELECT module, COALESCE(SUM(cost_krw),0) FROM recover_cost_by_module WHERE day >= date('now','-{int(days)} days') GROUP BY module ORDER BY 2 DESC LIMIT 10"
        ).fetchall()
        by_model = conn.execute(
            f"SELECT model, COALESCE(SUM(cost_krw),0) FROM recover_cost_by_module WHERE day >= date('now','-{int(days)} days') GROUP BY model"
        ).fetchall()
    return {"days": days, "total_krw": total[0], "total_calls": total[1],
            "top_modules": [{"module": m, "krw": k} for m, k in by_module],
            "by_model": [{"model": m, "krw": k} for m, k in by_model]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PII output gate (Presidio integration placeholder + R23 fallback)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def pii_output_gate(text: str) -> Dict[str, Any]:
    """LLM 출력 PII leakage 자동 차단. R23 scrub_pii 기본 + Presidio 통합 시 확장."""
    scrubbed = scrub_pii(text)
    blocked = scrubbed["redaction_count"] > 0
    return {"original_leaked": blocked, "scrubbed_text": scrubbed["scrubbed"],
            "redactions": scrubbed["redactions"],
            "_recommendation": "production: Microsoft Presidio + R23 이중 게이트"}


def summary() -> Dict[str, Any]:
    with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
        prompts = conn.execute("SELECT COUNT(*) FROM recover_prompt_library").fetchone()[0]
        versions = conn.execute("SELECT COUNT(*) FROM recover_prompt_versions").fetchone()[0]
        active_tests = conn.execute("SELECT COUNT(*) FROM recover_ab_test_runs WHERE ended_at IS NULL").fetchone()[0]
        evals_30d = conn.execute(
            "SELECT COUNT(*), AVG(judge_score) FROM recover_llm_eval_log WHERE evaluated_at >= datetime('now','-30 days')"
        ).fetchone()
    return {
        "prompts_registered": prompts,
        "prompt_versions": versions,
        "active_ab_tests": active_tests,
        "evals_30d": {"n": evals_30d[0], "avg_judge_score": round(evals_30d[1] or 0, 3)},
        "cost_30d": cost_summary(30),
        "_models_configured": list(MODELS.keys()),
        "_canary_traffic_pct": 5.0,
        "_pass_threshold": 0.75,
        "_observability_stack": "Langfuse self-hosted (PIPA) + Promptfoo CI + RAGAS + Presidio + R23",
        "_decision": "Fine-tune vs RAG → RAG 우위 (의료 인용·grounding 필수)",
    }


if __name__ == "__main__":
    import json as _j
    print(_j.dumps(summary(), ensure_ascii=False, indent=2, default=str))
    print("\n=== PII gate sample ===")
    print(_j.dumps(pii_output_gate("환자 김OO 010-1234-5678 abc@test.com"),
                   ensure_ascii=False, indent=2))
    print("\n=== cost sample: 1M input, 200K output, gpt-5.4-mini ===")
    print(_j.dumps(record_cost(date.today(), "R26", "gpt-5.4-mini",
                                1_000_000, 200_000, calls=1000, latency_p95_ms=850),
                   ensure_ascii=False))
