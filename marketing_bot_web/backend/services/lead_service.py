"""lead_service — leads.py 라우터에서 분리한 비즈니스 로직 레이어.

이관 대상:
- find_qa_matches: [C5] LIKE 1차 + regex 2차 패턴 매칭
- classify_keywords: 리드 텍스트 토큰화 (QA 매칭·감점 학습 공용)

향후 추가 후보:
- enrich_leads: 스코어/신뢰도/연락처 자동 보강
- stage_timestamp_update
- lead_grade_calculation
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def extract_tokens(text: str, min_length: int = 2, limit: int = 30) -> List[str]:
    """한글/영문 토큰 추출 (중복 제거, 긴 순).

    QA 매칭·skip 학습 등 여러 곳에서 공용으로 사용.
    """
    if not text or not text.strip():
        return []
    tokens = [t for t in re.findall(r"[가-힣]+|[a-zA-Z0-9]+", text.lower()) if len(t) >= min_length]
    # 길이 긴 순(더 specific) + 중복 제거
    return sorted(set(tokens), key=len, reverse=True)[:limit]


def find_qa_matches(
    cursor,
    lead_text: str,
    max_matches: int = 3,
    min_score: int = 20,
) -> List[Dict[str, Any]]:
    """Q&A 매칭.

    [Phase Z] sqlite-vec + KURE/BGE-M3 + bge-reranker 의미 검색 우선.
    실패 또는 결과 없을 때만 기존 LIKE+regex 폴백.

    1) RAG (의미 검색): KURE-v1/BGE-M3 임베딩 + RRF + 리랭커
    2) 폴백 LIKE+regex (기존 로직)
    """
    if not lead_text.strip():
        return []

    # 1차: RAG semantic search
    try:
        from services.rag.qa_search import get_qa_engine
        engine = get_qa_engine()
        rag_hits = engine.search(lead_text, top_k=max_matches, candidates=10, rerank=True)
        if rag_hits:
            # 형식 표준화 (match_score 별칭 추가)
            for h in rag_hits:
                h["match_score"] = round(float(h.get("score", 0.0)) * 100, 1)
            return rag_hits[:max_matches]
    except Exception as e:
        logger.warning(f"[QA] RAG 검색 실패, LIKE 폴백: {e}")

    # 2차: 기존 LIKE + regex 폴백
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
        params = [f"%{t}%" for t in tokens]
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

    matches.sort(key=lambda x: x["match_score"], reverse=True)
    return matches[:max_matches]
