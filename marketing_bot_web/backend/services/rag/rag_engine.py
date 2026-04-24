"""
RAG Engine - 벡터 검색 + Gemini 생성
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-2] ChromaDB 기반 벡터 검색과 Gemini 생성을 결합한 RAG 엔진

사용법:
    engine = RAGEngine(db_path="...", chroma_path="...")
    await engine.index_data()  # 최초 1회 또는 갱신 시
    result = await engine.query("경쟁사 A의 최근 약점은?")
"""

import os
import sys
import json
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ChromaDB 가용 여부 확인
try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False
    logger.warning("chromadb가 설치되지 않았습니다. pip install chromadb")


class RAGEngine:
    """
    RAG 엔진: 벡터 검색(ChromaDB) + 생성(Gemini)

    데이터 소스:
    - competitor_reviews: 경쟁사 리뷰
    - competitor_weaknesses: 경쟁사 약점
    - keyword_insights: 키워드 인사이트
    - intelligence_reports: 종합 인텔리전스 보고서
    - community_mentions: 커뮤니티 멘션
    """

    def __init__(self, db_path: str, chroma_path: str = None):
        self.db_path = db_path
        self.chroma_path = chroma_path or os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
            'db', 'chroma'
        )
        self._chroma_client = None
        self._collection = None

    def _get_chroma(self):
        """ChromaDB 클라이언트 (지연 초기화)"""
        if not HAS_CHROMADB:
            return None

        if self._chroma_client is None:
            os.makedirs(self.chroma_path, exist_ok=True)
            self._chroma_client = chromadb.PersistentClient(path=self.chroma_path)
            self._collection = self._chroma_client.get_or_create_collection(
                name="marketing_intelligence",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"📚 ChromaDB initialized at {self.chroma_path}")

        return self._collection

    # _get_gemini removed - using centralized ai_client instead

    async def index_data(self, max_per_source: int = 500) -> Dict[str, int]:
        """
        SQLite 데이터를 ChromaDB에 인덱싱

        Returns:
            소스별 인덱싱된 문서 수
        """
        collection = self._get_chroma()
        if collection is None:
            return {"error": "ChromaDB 사용 불가"}

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        counts = {}

        # 1. 경쟁사 리뷰
        try:
            cursor.execute("""
                SELECT id, competitor_name, content, sentiment, star_rating, review_date
                FROM competitor_reviews
                ORDER BY review_date DESC
                LIMIT ?
            """, (max_per_source,))

            docs, ids, metas = [], [], []
            for row in cursor.fetchall():
                doc_id = f"review_{row['id']}"
                text = f"[리뷰] {row['competitor_name']}: {row['content']}"
                docs.append(text)
                ids.append(doc_id)
                metas.append({
                    "source": "competitor_reviews",
                    "competitor": row['competitor_name'] or "",
                    "sentiment": row['sentiment'] or "neutral",
                    "date": row['review_date'] or "",
                })

            if docs:
                collection.upsert(documents=docs, ids=ids, metadatas=metas)
                counts["competitor_reviews"] = len(docs)
        except Exception as e:
            logger.error(f"리뷰 인덱싱 실패: {e}")
            counts["competitor_reviews"] = 0

        # 2. 경쟁사 약점
        try:
            cursor.execute("""
                SELECT id, competitor_name, weakness_type, description, severity
                FROM competitor_weaknesses
                ORDER BY created_at DESC
                LIMIT ?
            """, (max_per_source,))

            docs, ids, metas = [], [], []
            for row in cursor.fetchall():
                doc_id = f"weakness_{row['id']}"
                text = f"[약점] {row['competitor_name']} - {row['weakness_type']}: {row['description']}"
                docs.append(text)
                ids.append(doc_id)
                metas.append({
                    "source": "competitor_weaknesses",
                    "competitor": row['competitor_name'] or "",
                    "severity": row['severity'] or "medium",
                })

            if docs:
                collection.upsert(documents=docs, ids=ids, metadatas=metas)
                counts["competitor_weaknesses"] = len(docs)
        except Exception as e:
            logger.error(f"약점 인덱싱 실패: {e}")
            counts["competitor_weaknesses"] = 0

        # 3. 인텔리전스 보고서
        try:
            cursor.execute("""
                SELECT id, report_type, content, generated_at
                FROM intelligence_reports
                ORDER BY generated_at DESC
                LIMIT ?
            """, (max_per_source,))

            docs, ids, metas = [], [], []
            for row in cursor.fetchall():
                doc_id = f"report_{row['id']}"
                content = row['content'] or ""
                if len(content) > 2000:
                    content = content[:2000]
                text = f"[보고서] {row['report_type']}: {content}"
                docs.append(text)
                ids.append(doc_id)
                metas.append({
                    "source": "intelligence_reports",
                    "report_type": row['report_type'] or "",
                    "date": row['generated_at'] or "",
                })

            if docs:
                collection.upsert(documents=docs, ids=ids, metadatas=metas)
                counts["intelligence_reports"] = len(docs)
        except Exception as e:
            logger.error(f"보고서 인덱싱 실패: {e}")
            counts["intelligence_reports"] = 0

        # 4. 커뮤니티 멘션
        try:
            cursor.execute("""
                SELECT id, keyword, title, content_preview, platform
                FROM community_mentions
                ORDER BY created_at DESC
                LIMIT ?
            """, (max_per_source,))

            docs, ids, metas = [], [], []
            for row in cursor.fetchall():
                doc_id = f"mention_{row['id']}"
                text = f"[멘션] {row['platform']}/{row['keyword']}: {row['title']} - {row['content_preview'] or ''}"
                docs.append(text[:1000])
                ids.append(doc_id)
                metas.append({
                    "source": "community_mentions",
                    "platform": row['platform'] or "",
                    "keyword": row['keyword'] or "",
                })

            if docs:
                collection.upsert(documents=docs, ids=ids, metadatas=metas)
                counts["community_mentions"] = len(docs)
        except Exception as e:
            logger.error(f"멘션 인덱싱 실패: {e}")
            counts["community_mentions"] = 0

        conn.close()

        total = sum(counts.values())
        logger.info(f"📚 인덱싱 완료: 총 {total}건 ({counts})")
        return counts

    async def query(
        self,
        question: str,
        n_results: int = 10,
        source_filter: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        자연어 질의 → 벡터 검색 → Gemini 생성

        Args:
            question: 사용자 질문
            n_results: 검색할 문서 수
            source_filter: 소스 필터 (competitor_reviews, competitor_weaknesses 등)

        Returns:
            {answer: str, sources: list, query_info: dict}
        """
        collection = self._get_chroma()
        if collection is None:
            return {"answer": "ChromaDB가 설치되지 않았습니다. pip install chromadb", "sources": []}

        # 벡터 검색
        where_filter = {"source": source_filter} if source_filter else None

        try:
            results = collection.query(
                query_texts=[question],
                n_results=n_results,
                where=where_filter,
            )
        except Exception as e:
            logger.error(f"벡터 검색 실패: {e}")
            return {"answer": f"검색 실패: {str(e)}", "sources": []}

        documents = results.get('documents', [[]])[0]
        metadatas = results.get('metadatas', [[]])[0]
        distances = results.get('distances', [[]])[0]

        if not documents:
            return {
                "answer": "관련 데이터를 찾을 수 없습니다. 먼저 데이터 인덱싱이 필요할 수 있습니다.",
                "sources": [],
            }

        # 컨텍스트 구성
        context_parts = []
        sources = []
        for i, (doc, meta, dist) in enumerate(zip(documents, metadatas, distances)):
            context_parts.append(f"[{i+1}] {doc[:500]}")
            sources.append({
                "rank": i + 1,
                "source": meta.get("source", "unknown"),
                "relevance": round(1 - dist, 3) if dist else 0,
                "preview": doc[:200],
                "metadata": meta,
            })

        context = "\n\n".join(context_parts)

        # AI 생성
        try:
            from services.ai_client import ai_generate

            prompt = f"""다음 마케팅 데이터를 참고하여 질문에 답변해주세요.

[참고 데이터]
{context}

[질문]
{question}

[답변 규칙]
- 참고 데이터에 근거하여 답변
- 데이터에 없는 내용은 추측하지 말고 "데이터 부족"으로 표시
- 실용적이고 구체적으로 답변
- 한국어로 답변
"""

            answer = ai_generate(prompt, temperature=0.5, max_tokens=1500)
        except Exception as e:
            logger.error(f"AI 생성 실패: {e}")
            answer = f"AI 생성 실패. 검색된 원본 데이터를 참고하세요."

        return {
            "answer": answer,
            "sources": sources,
            "query_info": {
                "documents_found": len(documents),
                "source_filter": source_filter,
                "timestamp": datetime.now().isoformat(),
            }
        }

    def get_stats(self) -> Dict[str, Any]:
        """벡터 DB 통계"""
        collection = self._get_chroma()
        if collection is None:
            return {"status": "unavailable", "reason": "ChromaDB not installed"}

        try:
            count = collection.count()
            return {
                "status": "ready",
                "total_documents": count,
                "chroma_path": self.chroma_path,
            }
        except Exception as e:
            return {"status": "error", "reason": str(e)}
