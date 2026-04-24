"""Viral Hunter — UTM 추적 관련 하위 라우터.

viral.py(4488줄)에서 분리한 첫 번째 서브 라우터 (PoC).
- POST /api/viral/generate-utm: UTM 매개변수 URL 생성
- GET /api/viral/utm-stats: UTM 링크 통계 조회

이 파일은 `main.py`에서 별도 등록되어야 합니다.
"""
from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# 상위 패키지 경로 추가
backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.database import db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/viral", tags=["viral-utm"])

UTM_TRACKING_ENABLED = True


class UTMRequest(BaseModel):
    """UTM 매개변수 생성 요청."""
    url: str = Field(..., min_length=1, max_length=2000)
    campaign: Optional[str] = Field(None, max_length=100)
    content: Optional[str] = Field(None, max_length=200)
    term: Optional[str] = Field(None, max_length=100)
    source: str = Field("viral_hunter", max_length=100)
    medium: str = Field("comment", max_length=100)


def generate_utm_url(
    base_url: str,
    source: str = "viral_hunter",
    medium: str = "comment",
    campaign: str = "",
    content: str = "",
    term: str = "",
) -> str:
    """UTM 매개변수가 포함된 URL 생성.

    [투명성] 마케팅 활동 효과 측정 목적. 개인정보 수집 없음.
    UTM_TRACKING_ENABLED=False 로 비활성화 가능 → 원본 URL 그대로 반환.
    """
    if not UTM_TRACKING_ENABLED or not base_url:
        return base_url or ""

    try:
        parsed = urlparse(base_url)
        existing = parse_qs(parsed.query)
        utm_params: Dict[str, str] = {"utm_source": source, "utm_medium": medium}
        if campaign:
            utm_params["utm_campaign"] = campaign
        if content:
            utm_params["utm_content"] = content
        if term:
            utm_params["utm_term"] = term

        existing.update({k: [v] for k, v in utm_params.items()})
        new_query = urlencode({k: v[0] for k, v in existing.items()})
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
    except Exception as e:
        logger.warning(f"[UTM] URL 생성 실패: {e}")
        return base_url


@router.post("/generate-utm")
async def generate_utm(request: UTMRequest) -> Dict[str, Any]:
    """UTM 매개변수가 포함된 URL 생성."""
    try:
        utm_url = generate_utm_url(
            base_url=request.url,
            source=request.source,
            medium=request.medium,
            campaign=request.campaign or "",
            content=request.content or "",
            term=request.term or "",
        )
        return {
            "success": True,
            "original_url": request.url,
            "utm_url": utm_url,
            "utm_params": {
                "utm_source": request.source,
                "utm_medium": request.medium,
                "utm_campaign": request.campaign,
                "utm_content": request.content,
                "utm_term": request.term,
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/utm-stats")
async def get_utm_stats() -> Dict[str, Any]:
    """UTM 추적 통계 조회."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            # utm_links 테이블 생성 (없으면)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS utm_links (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT NOT NULL,
                    utm_url TEXT NOT NULL,
                    campaign TEXT,
                    content TEXT,
                    term TEXT,
                    click_count INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT (datetime('now', 'localtime'))
                )
                """
            )
            conn.commit()

            cur.execute("SELECT COUNT(*) FROM utm_links")
            total = cur.fetchone()[0]

            cur.execute(
                """
                SELECT campaign, COUNT(*) as count, SUM(click_count) as clicks
                FROM utm_links
                WHERE campaign IS NOT NULL AND campaign != ''
                GROUP BY campaign
                ORDER BY clicks DESC
                LIMIT 10
                """
            )
            by_campaign = [
                {"campaign": row[0], "links": row[1], "clicks": row[2] or 0}
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT original_url, utm_url, campaign, click_count, created_at
                FROM utm_links
                ORDER BY created_at DESC
                LIMIT 10
                """
            )
            recent = [
                {
                    "original_url": row[0],
                    "utm_url": row[1],
                    "campaign": row[2],
                    "clicks": row[3],
                    "created_at": row[4],
                }
                for row in cur.fetchall()
            ]

        return {"total_utm_links": total, "by_campaign": by_campaign, "recent_links": recent}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
