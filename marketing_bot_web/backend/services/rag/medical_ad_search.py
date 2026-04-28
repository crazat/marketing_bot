"""[R13] 의료광고심의 가이드북 RAG 검색.

scripts/build_medical_ad_index.py로 빌드된 medical_ad_chunks/medical_ad_vec 테이블 검색.
content_compliance.py가 호출하여 발굴 키워드/댓글에 자동 게이트 적용.

사용:
    from services.rag.medical_ad_search import search_guideline, is_guideline_indexed

    if is_guideline_indexed():
        hits = search_guideline("비급여 30% 할인", top_k=3)
        for h in hits:
            print(h['chunk_text'], h['score'])

인덱스 미구축 시 함수는 빈 리스트 반환 (silent 폴백).
"""
from __future__ import annotations

import logging
import os
import sqlite3
import struct
import threading
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    '..', 'db', 'marketing_data.db'
)
DB_PATH = os.path.normpath(DB_PATH)

_embedder = None
_lock = threading.Lock()


def _get_embedder():
    global _embedder
    with _lock:
        if _embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
                model_id = os.environ.get('MARKETING_BOT_EMBED_MODEL', 'BAAI/bge-m3')
                _embedder = SentenceTransformer(model_id)
            except Exception as e:
                logger.warning(f"임베딩 모델 로드 실패: {e}")
                _embedder = False
        return _embedder if _embedder else None


def _open_with_vec() -> Optional[sqlite3.Connection]:
    try:
        import sqlite_vec
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        return conn
    except Exception as e:
        logger.debug(f"sqlite-vec 로드 실패: {e}")
        return None


@lru_cache(maxsize=1)
def is_guideline_indexed() -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='medical_ad_chunks'"
        )
        if not cur.fetchone():
            return False
        n = cur.execute('SELECT COUNT(*) FROM medical_ad_chunks').fetchone()[0]
        return n > 0
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def search_guideline(query: str, top_k: int = 3) -> list[dict]:
    """가이드북에서 query와 의미 유사한 청크 top_k 반환.

    각 결과: {'chunk_text', 'section', 'score'}
    인덱스/임베딩 미가용이면 빈 리스트.
    """
    if not query or not is_guideline_indexed():
        return []

    embedder = _get_embedder()
    if embedder is None:
        return []

    conn = _open_with_vec()
    if conn is None:
        return []

    try:
        vec = embedder.encode(query, normalize_embeddings=True).tolist()
        blob = struct.pack(f'{len(vec)}f', *vec)
        rows = conn.execute(
            """
            SELECT c.chunk_text, c.section, v.distance
              FROM medical_ad_vec v
              JOIN medical_ad_chunks c ON c.id = v.chunk_id
             WHERE v.embedding MATCH ? AND k = ?
             ORDER BY v.distance
            """,
            (blob, top_k),
        ).fetchall()
        return [
            {'chunk_text': r['chunk_text'], 'section': r['section'],
             'score': 1.0 - r['distance']}
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"가이드북 검색 실패: {e}")
        return []
    finally:
        conn.close()


__all__ = ['search_guideline', 'is_guideline_indexed']
