"""Viral Hunter — 게시된 댓글 추적·성과 분석 하위 라우터.

viral.py에서 분리한 세 번째 서브 라우터.
- POST /api/viral/comments/post              : 게시된 댓글 기록
- PUT  /api/viral/comments/{id}/engagement  : 참여 지표 업데이트
- GET  /api/viral/comments/performance      : 성과 통계 (퍼널·템플릿별)
- GET  /api/viral/comments/list             : 댓글 목록
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

backend_dir = str(Path(__file__).parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from db.database import DatabaseManager
from backend_utils.database import db_conn

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/viral", tags=["viral-comments"])


class PostedComment(BaseModel):
    """게시된 댓글 기록."""
    target_id: int
    template_id: Optional[int] = None
    content: str
    platform: str
    url: str
    posted_at: Optional[str] = None


class CommentEngagement(BaseModel):
    """댓글 참여 지표."""
    likes: Optional[int] = 0
    replies: Optional[int] = 0
    clicks: Optional[int] = 0
    led_to_contact: Optional[bool] = False
    led_to_conversion: Optional[bool] = False


def _ensure_posted_comments_table(cursor) -> None:
    """posted_comments 테이블·인덱스 보장."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS posted_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_id INTEGER,
            template_id INTEGER,
            content TEXT NOT NULL,
            platform TEXT,
            url TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            likes INTEGER DEFAULT 0,
            replies INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            led_to_contact INTEGER DEFAULT 0,
            led_to_conversion INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (target_id) REFERENCES viral_targets(id),
            FOREIGN KEY (template_id) REFERENCES comment_templates(id)
        )
        """
    )
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posted_comments_platform ON posted_comments(platform)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_posted_comments_posted_at ON posted_comments(posted_at)")


@router.post("/comments/post")
async def record_posted_comment(comment: PostedComment) -> Dict[str, Any]:
    """게시된 댓글 기록 + 템플릿 사용 횟수·타겟 상태 업데이트."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            _ensure_posted_comments_table(cur)
            cur.execute(
                """
                INSERT INTO posted_comments (target_id, template_id, content, platform, url, posted_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    comment.target_id, comment.template_id, comment.content,
                    comment.platform, comment.url,
                    comment.posted_at or datetime.now().isoformat(),
                ),
            )
            comment_id = cur.lastrowid

            if comment.template_id:
                cur.execute(
                    """
                    UPDATE comment_templates
                    SET use_count = use_count + 1, updated_at = datetime('now')
                    WHERE id = ?
                    """,
                    (comment.template_id,),
                )
            cur.execute("UPDATE viral_targets SET status = 'commented' WHERE id = ?", (comment.target_id,))
            conn.commit()
        return {"status": "success", "comment_id": comment_id, "message": "댓글이 기록되었습니다"}
    except Exception as e:
        logger.error(f"[Post Comment Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/comments/{comment_id}/engagement")
async def update_comment_engagement(comment_id: int, engagement: CommentEngagement) -> Dict[str, Any]:
    """댓글 참여 지표 업데이트."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            _ensure_posted_comments_table(cur)
            cur.execute("SELECT id FROM posted_comments WHERE id = ?", (comment_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="댓글을 찾을 수 없습니다")
            cur.execute(
                """
                UPDATE posted_comments
                SET likes = ?, replies = ?, clicks = ?,
                    led_to_contact = ?, led_to_conversion = ?,
                    updated_at = datetime('now')
                WHERE id = ?
                """,
                (
                    engagement.likes or 0, engagement.replies or 0, engagement.clicks or 0,
                    1 if engagement.led_to_contact else 0,
                    1 if engagement.led_to_conversion else 0,
                    comment_id,
                ),
            )
            conn.commit()
        return {"status": "success", "message": "참여 지표가 업데이트되었습니다"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[Update Engagement Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments/performance")
async def get_comment_performance(days: int = 30) -> Dict[str, Any]:
    """댓글 성과 통계 — 플랫폼별·템플릿별·전환 퍼널."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            _ensure_posted_comments_table(cur)
            date_offset = f"-{min(days, 365)} days"

            cur.execute("SELECT COUNT(*) FROM posted_comments WHERE posted_at >= datetime('now', ?)", (date_offset,))
            total = cur.fetchone()[0]

            cur.execute(
                """
                SELECT platform, COUNT(*) as count,
                       SUM(likes) as total_likes, SUM(replies) as total_replies, SUM(clicks) as total_clicks,
                       SUM(led_to_contact) as contacts, SUM(led_to_conversion) as conversions
                FROM posted_comments
                WHERE posted_at >= datetime('now', ?)
                GROUP BY platform ORDER BY count DESC
                """,
                (date_offset,),
            )
            by_platform = [dict(row) for row in cur.fetchall()]

            cur.execute(
                """
                SELECT ct.name as template_name, ct.category,
                       COUNT(pc.id) as use_count,
                       AVG(pc.likes) as avg_likes, AVG(pc.replies) as avg_replies,
                       SUM(pc.led_to_conversion) as conversions
                FROM posted_comments pc
                LEFT JOIN comment_templates ct ON pc.template_id = ct.id
                WHERE pc.posted_at >= datetime('now', ?) AND pc.template_id IS NOT NULL
                GROUP BY pc.template_id ORDER BY use_count DESC LIMIT 10
                """,
                (date_offset,),
            )
            by_template = [
                {
                    "template_name": row["template_name"] or "(삭제된 템플릿)",
                    "category": row["category"],
                    "use_count": row["use_count"],
                    "avg_likes": round(row["avg_likes"] or 0, 1),
                    "avg_replies": round(row["avg_replies"] or 0, 1),
                    "conversions": row["conversions"] or 0,
                }
                for row in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT SUM(likes) as total_likes, SUM(replies) as total_replies, SUM(clicks) as total_clicks,
                       AVG(likes) as avg_likes, AVG(replies) as avg_replies
                FROM posted_comments WHERE posted_at >= datetime('now', ?)
                """,
                (date_offset,),
            )
            eng_row = cur.fetchone()
            engagement_summary = {
                "total_likes": eng_row["total_likes"] or 0,
                "total_replies": eng_row["total_replies"] or 0,
                "total_clicks": eng_row["total_clicks"] or 0,
                "avg_likes_per_comment": round(eng_row["avg_likes"] or 0, 2),
                "avg_replies_per_comment": round(eng_row["avg_replies"] or 0, 2),
            }

            cur.execute(
                """
                SELECT COUNT(*) as total,
                       SUM(CASE WHEN likes > 0 OR replies > 0 THEN 1 ELSE 0 END) as engaged,
                       SUM(led_to_contact) as contacts,
                       SUM(led_to_conversion) as conversions
                FROM posted_comments WHERE posted_at >= datetime('now', ?)
                """,
                (date_offset,),
            )
            f = cur.fetchone()
            _total = (f["total"] or 1)
            conversion_funnel = {
                "posted": f["total"] or 0,
                "engaged": f["engaged"] or 0,
                "contacted": f["contacts"] or 0,
                "converted": f["conversions"] or 0,
                "engagement_rate": round((f["engaged"] or 0) / _total * 100, 1),
                "contact_rate": round((f["contacts"] or 0) / _total * 100, 1),
                "conversion_rate": round((f["conversions"] or 0) / _total * 100, 1),
            }

            cur.execute(
                """
                SELECT pc.id, pc.content, pc.platform, pc.url,
                       pc.likes, pc.replies, pc.clicks,
                       pc.led_to_contact, pc.led_to_conversion,
                       pc.posted_at, ct.name as template_name
                FROM posted_comments pc
                LEFT JOIN comment_templates ct ON pc.template_id = ct.id
                WHERE pc.posted_at >= datetime('now', ?)
                ORDER BY pc.posted_at DESC LIMIT 20
                """,
                (date_offset,),
            )
            recent = [dict(row) for row in cur.fetchall()]

        return {
            "total_comments": total,
            "period_days": days,
            "by_platform": by_platform,
            "by_template": by_template,
            "engagement_summary": engagement_summary,
            "conversion_funnel": conversion_funnel,
            "recent_comments": recent,
        }
    except Exception as e:
        logger.error(f"[Comment Performance Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/comments/list")
async def get_posted_comments(
    platform: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> Dict[str, Any]:
    """게시된 댓글 목록 조회."""
    try:
        db = DatabaseManager()
        with db_conn(db.db_path) as conn:
            cur = conn.cursor()
            _ensure_posted_comments_table(cur)

            query = """
                SELECT pc.id, pc.content, pc.platform, pc.url,
                       pc.likes, pc.replies, pc.clicks,
                       pc.led_to_contact, pc.led_to_conversion,
                       pc.posted_at, pc.status,
                       ct.name as template_name, vt.title as target_title
                FROM posted_comments pc
                LEFT JOIN comment_templates ct ON pc.template_id = ct.id
                LEFT JOIN viral_targets vt ON pc.target_id = vt.id
                WHERE 1=1
            """
            params = []
            if platform:
                query += " AND pc.platform = ?"
                params.append(platform)
            query += " ORDER BY pc.posted_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            cur.execute(query, params)
            comments = [dict(row) for row in cur.fetchall()]

            cnt_q = "SELECT COUNT(*) FROM posted_comments WHERE 1=1"
            cnt_p = []
            if platform:
                cnt_q += " AND platform = ?"
                cnt_p.append(platform)
            cur.execute(cnt_q, cnt_p)
            total = cur.fetchone()[0]

        return {"comments": comments, "total": total, "limit": limit, "offset": offset}
    except Exception as e:
        logger.error(f"[List Comments Error] {e}")
        raise HTTPException(status_code=500, detail=str(e))
