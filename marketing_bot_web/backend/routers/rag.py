"""
RAG Intelligence API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 C-2] RAG 기반 마케팅 인텔리전스 질의 API
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Dict, Any, Optional
import sys
from pathlib import Path

parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


class RAGQueryRequest(BaseModel):
    question: str
    n_results: int = 10
    source_filter: Optional[str] = None  # competitor_reviews, competitor_weaknesses, etc.


def _get_rag_engine():
    """RAG 엔진 인스턴스 생성"""
    from services.rag.rag_engine import RAGEngine
    db = DatabaseManager()
    return RAGEngine(db_path=db.db_path)


@router.post("/query")
@handle_exceptions
async def query_rag(request: RAGQueryRequest) -> Dict[str, Any]:
    """
    자연어 질의로 마케팅 데이터 검색 + AI 답변 생성

    Body:
        question: "경쟁사 A의 최근 약점은?"
        n_results: 검색할 문서 수 (기본 10)
        source_filter: 소스 필터 (선택)
    """
    engine = _get_rag_engine()
    result = await engine.query(
        question=request.question,
        n_results=request.n_results,
        source_filter=request.source_filter,
    )
    return result


@router.post("/index")
@handle_exceptions
async def index_data(
    max_per_source: int = Query(default=500, ge=10, le=5000)
) -> Dict[str, Any]:
    """
    마케팅 데이터를 벡터 DB에 인덱싱 (최초 1회 또는 갱신 시)

    리뷰, 약점 분석, 인텔리전스 보고서, 커뮤니티 멘션을 인덱싱합니다.
    """
    engine = _get_rag_engine()
    counts = await engine.index_data(max_per_source=max_per_source)
    return {
        "status": "completed",
        "indexed": counts,
        "total": sum(v for v in counts.values() if isinstance(v, int)),
    }


@router.get("/stats")
@handle_exceptions
async def get_rag_stats() -> Dict[str, Any]:
    """벡터 DB 통계 (문서 수, 상태)"""
    engine = _get_rag_engine()
    return engine.get_stats()
