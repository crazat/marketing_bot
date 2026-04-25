"""
Q&A Gold Set 합성 + recall@k baseline 측정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. qa_repository 모든 row마다 Gemini Pro로 자연어 query 변형 3개 합성
2. qa_eval_dataset에 적재 (eval_set_name 별로 버전 관리)
3. 각 query를 qa_search.search()로 retrieve → expected_qa_id 포함 여부로 recall@5 계산
4. qa_eval_runs에 결과 적재

비용: qa_repository 200건 가정 시 Gemini Pro × 200 호출 ≈ $0.2-0.6 (1회만)

사용:
    # 1) 합성
    python scripts/build_qa_goldset.py build --eval-set v1
    # 2) 평가
    python scripts/build_qa_goldset.py eval --eval-set v1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sqlite3
import sys
import time
from typing import List, Dict, Any

# Path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 'marketing_bot_web', 'backend'))

logger = logging.getLogger(__name__)


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "db", "marketing_data.db")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1) Build (synthesis)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _synthesize_queries_for_qa(qa: Dict[str, Any], n: int = 3) -> List[str]:
    """1개 Q&A row → n개 자연어 query 합성."""
    from services.ai_client import ai_generate_structured
    from pydantic import BaseModel, Field

    class QuerySet(BaseModel):
        queries: List[str] = Field(min_length=1, max_length=10,
                                   description="환자가 실제로 물을 자연어 질문")

    prompt = f"""다음 한의원 Q&A의 표준 답변을 보고, 환자가 실제로 물어볼 자연어 질문 {n}개를 만드세요.
구어체/오타/축약/존댓말/반말 등 다양한 표현 포함.

[표준 답변] {qa.get('standard_answer', '')[:300]}
[카테고리] {qa.get('question_category', '')}

JSON 형식으로 {n}개 query 반환."""

    result = ai_generate_structured(
        prompt,
        response_schema=QuerySet,
        temperature=0.8,  # 다양성
        max_tokens=400,
    )
    if result is None or not result.queries:
        return []
    return result.queries[:n]


def build_goldset(eval_set: str, queries_per_qa: int = 3, limit: int = None) -> int:
    """qa_repository → qa_eval_dataset 합성 적재."""
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    sql = "SELECT id, question_pattern, question_category, standard_answer FROM qa_repository"
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    qas = [dict(r) for r in cur.fetchall()]
    conn.close()

    inserted = 0
    for i, qa in enumerate(qas, 1):
        try:
            queries = _synthesize_queries_for_qa(qa, n=queries_per_qa)
        except Exception as e:
            logger.warning(f"[gold] qa_id={qa['id']} 합성 실패: {e}")
            continue
        if not queries:
            continue
        conn = sqlite3.connect(_db_path())
        cur = conn.cursor()
        for q in queries:
            cur.execute("""
                INSERT INTO qa_eval_dataset (eval_set_name, query, expected_qa_id)
                VALUES (?, ?, ?)
            """, (eval_set, q, qa["id"]))
        conn.commit()
        conn.close()
        inserted += len(queries)
        logger.info(f"[gold] {i}/{len(qas)} qa_id={qa['id']}: {len(queries)} queries (누적 {inserted})")
        time.sleep(0.3)  # rate limit
    return inserted


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2) Eval (recall@5, MRR)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def evaluate(eval_set: str, top_k: int = 5) -> Dict[str, Any]:
    """qa_search.search()로 retrieve → recall@k + MRR 계산."""
    from services.rag.qa_search import get_qa_engine

    engine = get_qa_engine()

    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT query, expected_qa_id FROM qa_eval_dataset WHERE eval_set_name=?",
                (eval_set,))
    items = [dict(r) for r in cur.fetchall()]
    conn.close()

    if not items:
        return {"error": f"eval_set '{eval_set}' empty"}

    n = len(items)
    hits = 0
    rr_sum = 0.0
    t0 = time.time()
    for it in items:
        results = engine.search(it["query"], top_k=top_k, candidates=10, rerank=True)
        ids = [r.get("id") for r in results]
        if it["expected_qa_id"] in ids:
            hits += 1
            rank = ids.index(it["expected_qa_id"]) + 1
            rr_sum += 1.0 / rank

    recall = hits / n
    mrr = rr_sum / n
    duration = time.time() - t0

    # 결과 적재
    conn = sqlite3.connect(_db_path())
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO qa_eval_runs
          (eval_set_name, model_id, recall_at_5, mrr, n_queries, duration_seconds, metadata_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        eval_set, "BGE-M3+bge-reranker-v2-m3",
        recall, mrr, n, duration,
        json.dumps({"top_k": top_k, "rerank": True}),
    ))
    conn.commit()
    conn.close()

    return {
        "eval_set": eval_set,
        "n_queries": n,
        "hits": hits,
        f"recall_at_{top_k}": round(recall, 4),
        "mrr": round(mrr, 4),
        "duration_seconds": round(duration, 1),
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    pb = sub.add_parser("build")
    pb.add_argument("--eval-set", default="v1")
    pb.add_argument("--queries-per-qa", type=int, default=3)
    pb.add_argument("--limit", type=int, default=None)

    pe = sub.add_parser("eval")
    pe.add_argument("--eval-set", default="v1")
    pe.add_argument("--top-k", type=int, default=5)

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s | %(levelname)s | %(message)s")

    if args.cmd == "build":
        n = build_goldset(args.eval_set, args.queries_per_qa, args.limit)
        print(f"\nInserted {n} synthetic queries into eval_set='{args.eval_set}'")
    elif args.cmd == "eval":
        r = evaluate(args.eval_set, args.top_k)
        print(json.dumps(r, indent=2, ensure_ascii=False))
