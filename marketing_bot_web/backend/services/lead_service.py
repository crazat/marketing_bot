"""Business helpers used by the leads router."""

from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def extract_tokens(text: str, min_length: int = 2, limit: int = 30) -> List[str]:
    """Extract unique Korean/ASCII tokens, longest first."""
    if not text or not text.strip():
        return []
    tokens = [
        token
        for token in re.findall(r"[가-힣]+|[a-zA-Z0-9]+", text.lower())
        if len(token) >= min_length
    ]
    return sorted(set(tokens), key=len, reverse=True)[:limit]


def find_qa_matches(
    cursor,
    lead_text: str,
    max_matches: int = 3,
    min_score: int = 20,
) -> List[Dict[str, Any]]:
    """Find matching Q&A entries for a lead text.

    The semantic RAG path is opt-in via MARKETING_BOT_QA_RAG_ENABLED=true.
    The default path is deterministic and local, which keeps API requests and
    unit tests from loading external embedding/reranker models unexpectedly.
    """
    if not lead_text.strip():
        return []

    rag_enabled = os.getenv("MARKETING_BOT_QA_RAG_ENABLED", "false").lower() == "true"
    if rag_enabled:
        try:
            from services.rag.qa_search import get_qa_engine

            rerank = os.getenv("MARKETING_BOT_QA_RAG_RERANK", "false").lower() == "true"
            engine = get_qa_engine()
            rag_hits = engine.search(lead_text, top_k=max_matches, candidates=10, rerank=rerank)
            filtered_hits = []
            for hit in rag_hits:
                raw_score = float(hit.get("score", 0.0))
                match_score = raw_score * 100 if raw_score <= 1 else raw_score
                hit["match_score"] = round(match_score, 1)
                if hit["match_score"] >= min_score:
                    filtered_hits.append(hit)
            if filtered_hits:
                return filtered_hits[:max_matches]
        except Exception as exc:
            logger.warning("[QA] RAG search failed, falling back to LIKE: %s", exc)

    lead_lower = lead_text.lower()
    tokens = extract_tokens(lead_text)

    if not tokens:
        cursor.execute(
            """
            SELECT id, question_pattern, question_category, standard_answer, variations, use_count
            FROM qa_repository ORDER BY use_count DESC LIMIT 50
            """
        )
        candidate_qa = cursor.fetchall()
    else:
        like_clauses = " OR ".join(["LOWER(question_pattern) LIKE ?"] * len(tokens))
        params = [f"%{token}%" for token in tokens]
        cursor.execute(
            f"""
            SELECT id, question_pattern, question_category, standard_answer, variations, use_count
            FROM qa_repository
            WHERE {like_clauses}
            ORDER BY use_count DESC
            LIMIT 200
            """,
            params,
        )
        candidate_qa = cursor.fetchall()

    matches = []
    for qa in candidate_qa:
        qa_dict = dict(qa) if not isinstance(qa, dict) else qa
        pattern = (qa_dict.get("question_pattern") or "").lower()
        score = 0

        try:
            if re.search(pattern, lead_lower):
                score += 50
        except re.error:
            pass

        for keyword in re.findall(r"[가-힣]+|\w+", pattern):
            if len(keyword) >= 2 and keyword in lead_lower:
                score += 10

        if score >= min_score:
            qa_dict["match_score"] = score
            matches.append(qa_dict)

    matches.sort(key=lambda item: item["match_score"], reverse=True)
    return matches[:max_matches]
