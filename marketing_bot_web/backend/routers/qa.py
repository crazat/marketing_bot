"""
Q&A Repository API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 자주 묻는 질문 패턴 및 표준 응답 관리
- 질문 패턴 등록/수정/삭제
- 질문 매칭으로 적절한 응답 추천

[Phase 6.1] DB 초기화 로직을 services/db_init.py로 이동
- 앱 시작 시 한 번만 테이블 생성 (매 요청마다 확인하지 않음)
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
import sqlite3
import json
import re
import time
import threading
from pathlib import Path

import sys
parent_dir = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager
from schemas.response import success_response, error_response
from backend_utils.logger import get_router_logger
from backend_utils.error_handlers import handle_exceptions

logger = get_router_logger('qa')

router = APIRouter()

# [Phase 7] Q&A 캐시 (5분 TTL) - DB 부하 감소
_qa_cache: Dict[str, tuple[Any, float]] = {}
_qa_cache_lock = threading.Lock()
_qa_cache_ttl = 300  # 5분


class QACreate(BaseModel):
    """Q&A 생성 요청"""
    question_pattern: str = Field(..., min_length=1, max_length=500)
    question_category: str = Field("general", max_length=50)
    standard_answer: str = Field(..., min_length=1, max_length=5000)
    variations: Optional[List[str]] = None


class QAUpdate(BaseModel):
    """Q&A 수정 요청"""
    question_pattern: Optional[str] = Field(None, max_length=500)
    question_category: Optional[str] = Field(None, max_length=50)
    standard_answer: Optional[str] = Field(None, max_length=5000)
    variations: Optional[List[str]] = None


@router.get("/list")
@handle_exceptions
async def get_qa_list(
    category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0)
) -> Dict[str, Any]:
    """
    Q&A 목록 조회

    [Phase 7] TTLCache 적용 (5분) - DB 부하 감소
    """
    # [Phase 7] 캐시 키 생성
    cache_key = f"qa_list:{category or 'all'}:{limit}:{offset}"

    # 캐시 확인
    with _qa_cache_lock:
        if cache_key in _qa_cache:
            cached_data, cached_time = _qa_cache[cache_key]
            if time.time() - cached_time < _qa_cache_ttl:
                return cached_data

    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거 - 필요한 컬럼만 명시
        columns = "id, question_pattern, question_category, standard_answer, variations, use_count, created_at, updated_at"
        if category:
            cursor.execute(f"""
                SELECT {columns} FROM qa_repository
                WHERE question_category = ?
                ORDER BY use_count DESC, updated_at DESC
                LIMIT ? OFFSET ?
            """, (category, limit, offset))
        else:
            cursor.execute(f"""
                SELECT {columns} FROM qa_repository
                ORDER BY use_count DESC, updated_at DESC
                LIMIT ? OFFSET ?
            """, (limit, offset))

        items = []
        for row in cursor.fetchall():
            item = dict(row)
            try:
                item['variations'] = json.loads(item.get('variations', '[]'))
            except (json.JSONDecodeError, TypeError):
                item['variations'] = []
            items.append(item)

        if category:
            cursor.execute("SELECT COUNT(*) FROM qa_repository WHERE question_category = ?", (category,))
        else:
            cursor.execute("SELECT COUNT(*) FROM qa_repository")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT question_category FROM qa_repository ORDER BY question_category")
        categories = [row[0] for row in cursor.fetchall()]

        result = {"items": items, "total": total, "categories": categories, "limit": limit, "offset": offset}

        # [Phase 7] 결과 캐싱
        with _qa_cache_lock:
            _qa_cache[cache_key] = (result, time.time())
            # 캐시 크기 제한 (최대 50개 키)
            if len(_qa_cache) > 50:
                oldest_key = min(_qa_cache, key=lambda k: _qa_cache[k][1])
                del _qa_cache[oldest_key]

        return result
    except Exception as e:
        logger.error(f"목록 조회 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.post("/create")
@handle_exceptions
async def create_qa(data: QACreate) -> Dict[str, Any]:
    """Q&A 등록"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        variations_json = json.dumps(data.variations or [], ensure_ascii=False)
        cursor.execute("""
            INSERT INTO qa_repository
            (question_pattern, question_category, standard_answer, variations)
            VALUES (?, ?, ?, ?)
        """, (data.question_pattern, data.question_category, data.standard_answer, variations_json))

        qa_id = cursor.lastrowid
        conn.commit()

        # [Phase 7] 캐시 무효화 - 새 Q&A 추가 시 목록 캐시 클리어
        with _qa_cache_lock:
            _qa_cache.clear()

        return {"success": True, "id": qa_id, "message": "Q&A가 등록되었습니다"}
    except Exception as e:
        logger.error(f"생성 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.put("/{qa_id}")
@handle_exceptions
async def update_qa(qa_id: int, data: QAUpdate) -> Dict[str, Any]:
    """Q&A 수정"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM qa_repository WHERE id = ?", (qa_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다")

        updates = []
        params = []
        if data.question_pattern is not None:
            updates.append("question_pattern = ?")
            params.append(data.question_pattern)
        if data.question_category is not None:
            updates.append("question_category = ?")
            params.append(data.question_category)
        if data.standard_answer is not None:
            updates.append("standard_answer = ?")
            params.append(data.standard_answer)
        if data.variations is not None:
            updates.append("variations = ?")
            params.append(json.dumps(data.variations, ensure_ascii=False))

        if updates:
            updates.append("updated_at = CURRENT_TIMESTAMP")
            params.append(qa_id)
            cursor.execute(f"UPDATE qa_repository SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

            # [Phase 7] 캐시 무효화 - Q&A 수정 시 목록 캐시 클리어
            with _qa_cache_lock:
                _qa_cache.clear()

        return {"success": True, "message": "Q&A가 수정되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"수정 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.delete("/{qa_id}")
@handle_exceptions
async def delete_qa(qa_id: int) -> Dict[str, Any]:
    """Q&A 삭제"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id FROM qa_repository WHERE id = ?", (qa_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Q&A를 찾을 수 없습니다")

        cursor.execute("DELETE FROM qa_repository WHERE id = ?", (qa_id,))
        conn.commit()

        # [Phase 7] 캐시 무효화 - Q&A 삭제 시 목록 캐시 클리어
        with _qa_cache_lock:
            _qa_cache.clear()

        return {"success": True, "message": "Q&A가 삭제되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"삭제 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/match")
@handle_exceptions
async def match_question(
    text: str = Query(..., min_length=1, max_length=1000),
    limit: int = Query(3, ge=1, le=20)
) -> Dict[str, Any]:
    """텍스트에 매칭되는 Q&A 검색"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # [Phase 7] SELECT * 제거
        cursor.execute("""
            SELECT id, question_pattern, question_category, standard_answer, variations, use_count
            FROM qa_repository ORDER BY use_count DESC
        """)
        all_qa = cursor.fetchall()

        if not all_qa:
            return {"matches": [], "query": text}

        text_lower = text.lower()
        matches = []

        for qa in all_qa:
            qa_dict = dict(qa)
            pattern = qa_dict['question_pattern'].lower()
            score = 0

            try:
                if re.search(pattern, text_lower):
                    score += 50
            except re.error:
                pass

            keywords = re.findall(r'[가-힣]+|\w+', pattern)
            for keyword in keywords:
                if len(keyword) >= 2 and keyword in text_lower:
                    score += 10

            try:
                variations = json.loads(qa_dict.get('variations', '[]'))
                for var in variations:
                    if var.lower() in text_lower:
                        score += 20
            except (json.JSONDecodeError, TypeError):
                pass

            if score > 0:
                qa_dict['match_score'] = score
                try:
                    qa_dict['variations'] = json.loads(qa_dict.get('variations', '[]'))
                except (json.JSONDecodeError, TypeError):
                    qa_dict['variations'] = []
                matches.append(qa_dict)

        matches.sort(key=lambda x: x['match_score'], reverse=True)
        matches = matches[:limit]

        if matches:
            cursor.execute("UPDATE qa_repository SET use_count = use_count + 1 WHERE id = ?", (matches[0]['id'],))
            conn.commit()

        return {"matches": matches, "query": text, "total_found": len(matches)}
    except Exception as e:
        logger.error(f"매칭 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()


@router.get("/stats")
@handle_exceptions
async def get_qa_stats() -> Dict[str, Any]:
    """Q&A 통계 조회"""
    conn = None
    try:
        db = DatabaseManager()
        conn = sqlite3.connect(db.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) FROM qa_repository")
        total = cursor.fetchone()[0]

        cursor.execute("""
            SELECT question_category, COUNT(*) as count
            FROM qa_repository GROUP BY question_category ORDER BY count DESC
        """)
        by_category = {row['question_category']: row['count'] for row in cursor.fetchall()}

        cursor.execute("""
            SELECT id, question_pattern, use_count
            FROM qa_repository ORDER BY use_count DESC LIMIT 5
        """)
        top_used = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT SUM(use_count) FROM qa_repository")
        total_uses = cursor.fetchone()[0] or 0

        return {"total": total, "by_category": by_category, "top_used": top_used, "total_uses": total_uses}
    except Exception as e:
        logger.error(f"통계 오류: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if conn:
            conn.close()
