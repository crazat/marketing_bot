"""Viral Hunter — 댓글 템플릿 관리 하위 라우터.

viral.py에서 분리한 두 번째 서브 라우터.
- GET  /api/viral/templates              : 템플릿 목록 조회 (필터+TTL 캐시)
- POST /api/viral/templates              : 템플릿 생성
- PATCH /api/viral/templates/{id}/use    : 사용 횟수 증가
- DELETE /api/viral/templates/{id}       : 템플릿 삭제
- POST /api/viral/templates/recommend    : 리드 정보 기반 자동 추천
"""
from __future__ import annotations

import logging
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.database import db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/viral", tags=["viral-templates"])

# 공통 타입
EngagementSignal = Literal["any", "seeking_info", "ready_to_act", "passive"]
PrioritySegment = Literal["vip", "high", "medium", "low", "all"]

# TTL 캐시 (5분)
_templates_cache: Dict[str, tuple[List[Dict], float]] = {}
_templates_cache_lock = threading.Lock()
_templates_cache_ttl = 300


# ── 모델 ───────────────────────────────────────────────────────────────
class TemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    content: str = Field(..., min_length=1, max_length=5000)
    category: str = Field("general", max_length=50)
    situation_type: str = Field("general", max_length=50)
    engagement_signal: EngagementSignal = "any"
    priority_segment: PrioritySegment = "all"


class TemplateRecommendRequest(BaseModel):
    priority_rank: int = Field(3, ge=1, le=5)
    engagement_signal: EngagementSignal = "passive"
    category: str = Field("general", max_length=50)
    content_preview: str = Field("", max_length=1000)


# ── 엔드포인트 ─────────────────────────────────────────────────────────
@router.get("/templates")
async def get_comment_templates(
    situation_type: Optional[str] = None,
    engagement_signal: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """댓글 템플릿 목록 조회 (TTL 캐시 5분)."""
    cache_key = f"templates:{situation_type or 'all'}:{engagement_signal or 'all'}"
    with _templates_cache_lock:
        if cache_key in _templates_cache:
            data, cached_time = _templates_cache[cache_key]
            if time.time() - cached_time < _templates_cache_ttl:
                return data

    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            columns = "id, name, content, category, situation_type, engagement_signal, use_count, created_at"
            query = f"SELECT {columns} FROM comment_templates WHERE 1=1"
            params: List[Any] = []
            if situation_type:
                query += " AND (situation_type = ? OR situation_type = 'general')"
                params.append(situation_type)
            if engagement_signal:
                query += " AND (engagement_signal = ? OR engagement_signal = 'any')"
                params.append(engagement_signal)
            query += " ORDER BY use_count DESC, created_at DESC"
            cur.execute(query, params)
            templates = [dict(row) for row in cur.fetchall()]

        with _templates_cache_lock:
            _templates_cache[cache_key] = (templates, time.time())
            if len(_templates_cache) > 50:
                oldest = min(_templates_cache, key=lambda k: _templates_cache[k][1])
                del _templates_cache[oldest]
        return templates
    except Exception as e:
        logger.error(f"[Templates Error] {e}")
        raise HTTPException(status_code=500, detail=f"템플릿 조회 실패: {e}")


@router.post("/templates")
async def create_template(template: TemplateCreate) -> Dict[str, Any]:
    """새 댓글 템플릿 생성."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO comment_templates (name, content, category, situation_type, engagement_signal)
                VALUES (?, ?, ?, ?, ?)
                """,
                (template.name, template.content, template.category,
                 template.situation_type, template.engagement_signal),
            )
            conn.commit()
            template_id = cur.lastrowid
        with _templates_cache_lock:
            _templates_cache.clear()
        return {"status": "success", "message": "템플릿이 저장되었습니다", "template_id": template_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"템플릿 저장 실패: {e}")


@router.patch("/templates/{template_id}/use")
async def increment_template_use(template_id: int) -> Dict[str, str]:
    """템플릿 사용 횟수 증가."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            cur.execute(
                "UPDATE comment_templates SET use_count = use_count + 1, updated_at = datetime('now') WHERE id = ?",
                (template_id,),
            )
            conn.commit()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int) -> Dict[str, str]:
    """댓글 템플릿 삭제."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM comment_templates WHERE id = ?", (template_id,))
            conn.commit()
        with _templates_cache_lock:
            _templates_cache.clear()
        return {"status": "success", "message": "템플릿이 삭제되었습니다"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates/recommend")
async def recommend_template(request: TemplateRecommendRequest) -> Dict[str, Any]:
    """리드 priority_rank · engagement_signal 기반 템플릿 자동 추천."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(comment_templates)")
            columns = [row[1] for row in cur.fetchall()]
            if "priority_segment" not in columns:
                cur.execute("ALTER TABLE comment_templates ADD COLUMN priority_segment TEXT DEFAULT 'all'")
                conn.commit()

            segment_map = {1: "vip", 2: "high", 3: "medium", 4: "low", 5: "low"}
            target_segment = segment_map.get(request.priority_rank, "medium")

            col_list = "id, name, content, category, situation_type, engagement_signal, use_count, created_at, priority_segment"
            query = f"""
                SELECT {col_list},
                       CASE
                           WHEN priority_segment = ? THEN 100
                           WHEN priority_segment = 'all' THEN 50
                           ELSE 10
                       END +
                       CASE
                           WHEN engagement_signal = ? THEN 30
                           WHEN engagement_signal = 'any' THEN 15
                           ELSE 0
                       END +
                       CASE
                           WHEN category = ? THEN 20
                           WHEN category = 'general' THEN 10
                           ELSE 0
                       END as match_score
                FROM comment_templates
                WHERE (priority_segment = ? OR priority_segment = 'all')
                  AND (engagement_signal = ? OR engagement_signal = 'any')
                ORDER BY match_score DESC, use_count DESC
                LIMIT 3
            """
            cur.execute(
                query,
                (target_segment, request.engagement_signal, request.category,
                 target_segment, request.engagement_signal),
            )
            templates = [dict(row) for row in cur.fetchall()]

            if not templates:
                cur.execute(
                    f"""
                    SELECT {col_list} FROM comment_templates
                    WHERE priority_segment = 'all' OR priority_segment IS NULL
                    ORDER BY use_count DESC LIMIT 3
                    """
                )
                templates = [dict(row) for row in cur.fetchall()]

        tone_guides = {
            "vip": "🔥 VIP 세그먼트: 개인화된 프리미엄 응대, 빠른 반응 시간, 전문 상담 제안",
            "high": "⚡ High 세그먼트: 적극적 관심 표현, 상세한 정보 제공, 방문 유도",
            "medium": "📌 Medium 세그먼트: 친절한 안내, 관심사 파악, 후속 연락 제안",
            "low": "📋 Low 세그먼트: 기본 정보 제공, 간결한 응대",
        }
        return {
            "status": "success",
            "priority_rank": request.priority_rank,
            "target_segment": target_segment,
            "tone_guide": tone_guides.get(target_segment, ""),
            "templates": templates,
            "template_count": len(templates),
        }
    except Exception as e:
        logger.error(f"[Template Recommend Error] {e}")
        raise HTTPException(status_code=500, detail=f"템플릿 추천 실패: {e}")
