"""
Q&A Semantic Search (sqlite-vec + Korean embeddings + reranker)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 LIKE + regex 패턴 매칭의 recall ceiling (~0.40)을 의미 기반 검색
+ 리랭커 (목표 0.82)로 끌어올린다.

스택:
- 임베딩: BAAI/bge-m3 (한국어 포함 다국어, 568MB) — env로 KURE-v1 등 변경 가능
- 저장소: sqlite-vec (기존 marketing_data.db에 가상 테이블)
- 하이브리드: SQLite FTS5 BM25 + dense + RRF
- 리랭커: BAAI/bge-reranker-v2-m3 (lazy load)

사용:
    from services.rag.qa_search import get_qa_engine
    engine = get_qa_engine()
    engine.index_all()  # 최초 1회 (또는 데이터 변경 시)
    results = engine.search("청주에서 다이어트 한약 얼마예요?", top_k=3)
"""

from __future__ import annotations

import logging
import sqlite3
import struct
import threading
import os
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# 환경변수로 모델 변경 가능
DEFAULT_EMBED_MODEL = os.getenv("MARKETING_BOT_EMBED_MODEL", "BAAI/bge-m3")
DEFAULT_RERANKER_MODEL = os.getenv("MARKETING_BOT_RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")

# bge-m3 default dim
EMBED_DIM = int(os.getenv("MARKETING_BOT_EMBED_DIM", "1024"))


def _vec_to_bytes(vec: List[float]) -> bytes:
    """sqlite-vec float32 BLOB 형식."""
    return struct.pack(f"{len(vec)}f", *vec)


class QASearchEngine:
    """Q&A 의미 기반 검색 + 리랭커.

    싱글톤 (무거운 모델 로드 1회). 스레드 안전.
    """

    _instance: Optional["QASearchEngine"] = None
    _instance_lock = threading.Lock()

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._embed_model = None
        self._reranker = None
        self._model_lock = threading.Lock()
        self._init_vec_table()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> "QASearchEngine":
        """싱글톤 반환. db_path 기본은 db/marketing_data.db."""
        with cls._instance_lock:
            if cls._instance is None:
                if db_path is None:
                    here = os.path.dirname(os.path.abspath(__file__))
                    # rag → services → backend → marketing_bot_web → root
                    root = os.path.dirname(os.path.dirname(os.path.dirname(
                        os.path.dirname(here))))
                    db_path = os.path.join(root, "db", "marketing_data.db")
                cls._instance = cls(db_path)
            return cls._instance

    # ── DB schema ──────────────────────────────────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        try:
            import sqlite_vec
            conn.enable_load_extension(True)
            sqlite_vec.load(conn)
            conn.enable_load_extension(False)
        except Exception as e:
            logger.warning(f"[QA-RAG] sqlite-vec 로드 실패: {e}")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_vec_table(self):
        conn = self._connect()
        try:
            cur = conn.cursor()
            # Vector virtual table
            cur.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS qa_embeddings
                USING vec0(
                    qa_id INTEGER PRIMARY KEY,
                    embedding float[{EMBED_DIM}]
                )
            """)
            # FTS5 for BM25 hybrid
            cur.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS qa_fts
                USING fts5(qa_id UNINDEXED, text)
            """)
            conn.commit()
            logger.info("[QA-RAG] qa_embeddings + qa_fts tables ensured")
        except Exception as e:
            logger.error(f"[QA-RAG] 테이블 생성 실패: {e}")
        finally:
            conn.close()

    # ── Models (lazy) ──────────────────────────────────────────────────

    def _ensure_embed(self):
        if self._embed_model is not None:
            return
        with self._model_lock:
            if self._embed_model is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    logger.info(f"[QA-RAG] loading embed model: {DEFAULT_EMBED_MODEL}")
                    self._embed_model = SentenceTransformer(DEFAULT_EMBED_MODEL)
                    logger.info("[QA-RAG] embed model loaded")
                except Exception as e:
                    logger.error(f"[QA-RAG] embed model 로드 실패: {e}")
                    raise

    def _ensure_reranker(self):
        if self._reranker is not None:
            return
        with self._model_lock:
            if self._reranker is None:
                try:
                    from sentence_transformers import CrossEncoder
                    logger.info(f"[QA-RAG] loading reranker: {DEFAULT_RERANKER_MODEL}")
                    self._reranker = CrossEncoder(DEFAULT_RERANKER_MODEL, max_length=512)
                    logger.info("[QA-RAG] reranker loaded")
                except Exception as e:
                    logger.warning(f"[QA-RAG] reranker 로드 실패 (스킵): {e}")
                    self._reranker = False  # 폴백 마커

    def embed(self, texts: List[str]) -> List[List[float]]:
        self._ensure_embed()
        embs = self._embed_model.encode(texts, normalize_embeddings=True)
        return [list(map(float, e)) for e in embs]

    # ── Index ──────────────────────────────────────────────────────────

    def index_all(self) -> int:
        """qa_repository 전체를 임베딩 + FTS 등록 (idempotent)."""
        conn = self._connect()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT id, question_pattern, question_category, standard_answer, variations
                FROM qa_repository
            """)
            rows = cur.fetchall()
            if not rows:
                logger.warning("[QA-RAG] qa_repository 비어있음, 인덱싱 skip")
                return 0

            # variations + question_pattern + standard_answer를 합쳐 의미 텍스트 구성
            texts = []
            for r in rows:
                pat = r["question_pattern"] or ""
                ans = r["standard_answer"] or ""
                vars_str = r["variations"] or ""
                # variations가 JSON array string일 수도 있음
                try:
                    import json
                    var_list = json.loads(vars_str) if vars_str.startswith("[") else []
                    if isinstance(var_list, list):
                        vars_str = " ".join(str(v) for v in var_list)
                except Exception:
                    pass
                # 매칭 텍스트 = pattern (정규식 그룹) 토큰 + variations + answer 일부
                pat_clean = pat.replace("(", "").replace(")", "").replace("|", " ").replace("?", "")
                composite = f"{pat_clean} {vars_str} {ans[:200]}"
                texts.append((r["id"], composite, ans))

            # 임베딩
            embeddings = self.embed([t[1] for t in texts])

            # 기존 데이터 클리어 (재인덱싱)
            cur.execute("DELETE FROM qa_embeddings")
            cur.execute("DELETE FROM qa_fts")
            for (qa_id, composite, _), emb in zip(texts, embeddings):
                cur.execute(
                    "INSERT INTO qa_embeddings (qa_id, embedding) VALUES (?, ?)",
                    (qa_id, _vec_to_bytes(emb)),
                )
                cur.execute(
                    "INSERT INTO qa_fts (qa_id, text) VALUES (?, ?)",
                    (qa_id, composite),
                )
            conn.commit()
            logger.info(f"[QA-RAG] indexed {len(texts)} Q&A entries")
            return len(texts)
        except Exception as e:
            logger.error(f"[QA-RAG] index_all 실패: {e}")
            return 0
        finally:
            conn.close()

    # ── Search ─────────────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 3,
        candidates: int = 10,
        rerank: bool = True,
    ) -> List[Dict[str, Any]]:
        """하이브리드 검색 + 리랭커.

        1) BM25 (FTS5) top-N + dense vector top-N → RRF fusion → top-2N 후보
        2) 리랭커로 재정렬
        3) top-k 반환

        Returns:
            [{id, question_pattern, question_category, standard_answer, score}, ...]
        """
        if not query.strip():
            return []
        conn = self._connect()
        try:
            cur = conn.cursor()

            # BM25 후보
            try:
                cur.execute(
                    "SELECT qa_id, rank FROM qa_fts WHERE qa_fts MATCH ? ORDER BY rank LIMIT ?",
                    (query, candidates),
                )
                bm25 = [(r["qa_id"], i + 1) for i, r in enumerate(cur.fetchall())]
            except Exception:
                bm25 = []

            # Dense 후보
            qvec = self.embed([query])[0]
            try:
                cur.execute(
                    """
                    SELECT qa_id, distance
                    FROM qa_embeddings
                    WHERE embedding MATCH ? AND k = ?
                    ORDER BY distance
                    """,
                    (_vec_to_bytes(qvec), candidates),
                )
                dense = [(r["qa_id"], i + 1) for i, r in enumerate(cur.fetchall())]
            except Exception as e:
                logger.warning(f"[QA-RAG] vector search 실패: {e}")
                dense = []

            # RRF fusion (k=60 표준)
            rrf_k = 60
            scores: Dict[int, float] = {}
            for qa_id, rank in bm25:
                scores[qa_id] = scores.get(qa_id, 0.0) + 1.0 / (rrf_k + rank)
            for qa_id, rank in dense:
                scores[qa_id] = scores.get(qa_id, 0.0) + 1.0 / (rrf_k + rank)

            if not scores:
                return []

            # 후보 가져오기
            ranked_ids = sorted(scores, key=scores.get, reverse=True)[: candidates * 2]
            placeholders = ",".join(["?"] * len(ranked_ids))
            cur.execute(
                f"""
                SELECT id, question_pattern, question_category, standard_answer, variations
                FROM qa_repository WHERE id IN ({placeholders})
                """,
                ranked_ids,
            )
            id_to_row = {r["id"]: dict(r) for r in cur.fetchall()}
            candidates_list = [id_to_row[i] for i in ranked_ids if i in id_to_row]

            # 리랭커
            if rerank and len(candidates_list) > 1:
                self._ensure_reranker()
                if self._reranker not in (None, False):
                    pairs = [(query, c["question_pattern"] + " " + c["standard_answer"][:150])
                             for c in candidates_list]
                    try:
                        rerank_scores = self._reranker.predict(pairs)
                        for c, s in zip(candidates_list, rerank_scores):
                            c["score"] = float(s)
                        candidates_list.sort(key=lambda x: x["score"], reverse=True)
                    except Exception as e:
                        logger.warning(f"[QA-RAG] rerank 실패: {e}")
                        # RRF score 사용
                        for c in candidates_list:
                            c["score"] = scores.get(c["id"], 0.0)
                else:
                    for c in candidates_list:
                        c["score"] = scores.get(c["id"], 0.0)
            else:
                for c in candidates_list:
                    c["score"] = scores.get(c["id"], 0.0)

            return candidates_list[:top_k]

        except Exception as e:
            logger.error(f"[QA-RAG] search 실패: {e}")
            return []
        finally:
            conn.close()


def get_qa_engine() -> QASearchEngine:
    """전역 싱글톤 접근."""
    return QASearchEngine.get_instance()


# ── CLI: 인덱싱 + 스모크 ──────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    engine = get_qa_engine()
    n = engine.index_all()
    print(f"Indexed {n} Q&A entries")

    # 자연어 쿼리 테스트
    queries = [
        "청주 다이어트 한약 얼마예요?",  # → price
        "한약 먹으면 살 빠져요?",         # → effect
        "거기 위치가 어디인가요?",         # → location
        "예약하려면 어떻게 해요?",         # → reservation
        "부작용 있어요?",                  # → safety
    ]
    for q in queries:
        results = engine.search(q, top_k=2)
        print(f"\nQ: {q}")
        for r in results:
            print(f"  [{r.get('question_category')}] score={r.get('score'):.3f} pattern={r['question_pattern']}")
