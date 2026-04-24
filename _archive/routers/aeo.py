"""
AEO/GEO 추적 API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[고도화 B-2] AI 검색 최적화 (AEO/GEO) 가시성 추적

- AEO (Answer Engine Optimization): 네이버 AI 브리핑 노출 추적
- GEO (Generative Engine Optimization): 생성형 AI 브랜드 인용 추적
- 스마트블록 타입 분석
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, List, Optional
import sys
import os
from pathlib import Path
import sqlite3
import json
import logging

parent_dir = str(Path(__file__).parent.parent.parent.parent)
backend_dir = str(Path(__file__).parent.parent)
sys.path.insert(0, parent_dir)
sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.error_handlers import handle_exceptions
from backend_utils.cache import cached
from schemas.response import success_response, error_response

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/visibility")
@cached(ttl=300)
@handle_exceptions
async def get_ai_search_visibility(
    days: int = Query(default=30, ge=1, le=365, description="조회 기간"),
    keyword: Optional[str] = Query(None, description="특정 키워드 필터"),
) -> Dict[str, Any]:
    """
    AI 검색 가시성 데이터 조회

    Returns:
        - records: 키워드별 AI 브리핑 노출 기록
        - summary: 전체 노출률, 자사 멘션율
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 테이블 존재 확인
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_search_visibility'"
        )
        if not cursor.fetchone():
            return success_response({
                "records": [],
                "summary": {
                    "total_scans": 0,
                    "ai_briefing_rate": 0,
                    "our_mention_rate": 0,
                },
                "message": "아직 AEO 스캔 데이터가 없습니다. scrapers/ai_search_tracker.py를 실행해주세요."
            })

        query = """
            SELECT * FROM ai_search_visibility
            WHERE scanned_at >= datetime('now', ? || ' days')
        """
        params = [f"-{days}"]

        if keyword:
            query += " AND keyword = ?"
            params.append(keyword)

        query += " ORDER BY scanned_at DESC"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        records = []
        for row in rows:
            record = dict(row)
            # JSON 필드 파싱
            for field in ['source_urls', 'competitor_mentioned', 'smartblock_types']:
                if isinstance(record.get(field), str):
                    try:
                        record[field] = json.loads(record[field])
                    except (json.JSONDecodeError, TypeError):
                        record[field] = []
            records.append(record)

        # 요약 통계
        total_scans = len(records)
        briefing_count = sum(1 for r in records if r.get('ai_briefing_detected'))
        our_mention_count = sum(1 for r in records if r.get('our_mention'))

        return success_response({
            "records": records,
            "summary": {
                "total_scans": total_scans,
                "ai_briefing_rate": round(
                    (briefing_count / max(total_scans, 1)) * 100, 1
                ),
                "our_mention_rate": round(
                    (our_mention_count / max(total_scans, 1)) * 100, 1
                ),
                "briefing_count": briefing_count,
                "our_mention_count": our_mention_count,
            }
        })

    except Exception as e:
        logger.error(f"AEO 가시성 조회 오류: {e}", exc_info=True)
        return error_response(f"AEO 데이터 조회 실패: {str(e)}", status_code=500)
    finally:
        if conn:
            conn.close()


@router.get("/keyword-summary")
@cached(ttl=600)
@handle_exceptions
async def get_aeo_keyword_summary(
    days: int = Query(default=30, ge=1, le=365),
) -> Dict[str, Any]:
    """
    키워드별 AEO 노출 요약

    Returns:
        키워드별 AI 브리핑 노출 횟수, 자사 멘션 횟수
    """
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='ai_search_visibility'"
        )
        if not cursor.fetchone():
            return success_response({"keywords": []})

        cursor.execute("""
            SELECT
                keyword,
                COUNT(*) as total_scans,
                SUM(CASE WHEN ai_briefing_detected = 1 THEN 1 ELSE 0 END) as briefing_count,
                SUM(CASE WHEN our_mention = 1 THEN 1 ELSE 0 END) as our_mention_count,
                MAX(scanned_at) as last_scanned
            FROM ai_search_visibility
            WHERE scanned_at >= datetime('now', ? || ' days')
            GROUP BY keyword
            ORDER BY briefing_count DESC
        """, (f"-{days}",))

        keywords = []
        for row in cursor.fetchall():
            r = dict(row)
            r['briefing_rate'] = round(
                (r['briefing_count'] / max(r['total_scans'], 1)) * 100, 1
            )
            r['our_mention_rate'] = round(
                (r['our_mention_count'] / max(r['total_scans'], 1)) * 100, 1
            )
            keywords.append(r)

        return success_response({"keywords": keywords})

    except Exception as e:
        logger.error(f"AEO 키워드 요약 오류: {e}", exc_info=True)
        return error_response(f"AEO 키워드 요약 실패: {str(e)}", status_code=500)
    finally:
        if conn:
            conn.close()
