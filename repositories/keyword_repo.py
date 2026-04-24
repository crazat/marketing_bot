"""KeywordRepository — keyword_insights + rank_history 전담 Repository."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional


class KeywordRepository:
    """키워드 인사이트·순위 이력 접근 전담."""

    # 자주 쓰이는 정렬 컬럼 화이트리스트 (SQL injection 방지)
    _SORT_COLUMNS = {
        "priority_v3", "kei", "search_volume", "volume",
        "opp_score", "document_count", "created_at",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # ── Keyword Insights ───────────────────────────────────────────────
    def get(self, keyword: str) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT * FROM keyword_insights WHERE keyword = ? ORDER BY created_at DESC LIMIT 1",
                (keyword,),
            )
            r = cur.fetchone()
            return dict(r) if r else None

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort: str = "priority_v3",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where, params = self._build_where(filters or {})
        sort_col = sort if sort in self._SORT_COLUMNS else "priority_v3"
        order_by = f"ORDER BY {sort_col} DESC NULLS LAST, created_at DESC"
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM keyword_insights {where} {order_by} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        where, params = self._build_where(filters or {})
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM keyword_insights {where}", params)
            return int(cur.fetchone()[0])

    def group_by_grade(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        where, params = self._build_where(filters or {})
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT grade, COUNT(*) FROM keyword_insights {where} GROUP BY grade",
                params,
            )
            return {r[0] or "unknown": r[1] for r in cur.fetchall()}

    # ── Rank History ───────────────────────────────────────────────────
    def record_rank(
        self,
        keyword: str,
        rank: int,
        target_name: Optional[str] = None,
        status: str = "found",
        device_type: str = "mobile",
        note: Optional[str] = None,
    ) -> bool:
        now = datetime.now().isoformat()
        today = datetime.now().strftime("%Y-%m-%d")
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO rank_history(keyword, rank, target_name, checked_at, date, status, device_type, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (keyword, rank, target_name, now, today, status, device_type, note),
            )
            conn.commit()
            return True

    def latest_rank(
        self,
        keyword: str,
        device_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        where = ["keyword = ?"]
        params: List[Any] = [keyword]
        if device_type:
            where.append("device_type = ?")
            params.append(device_type)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM rank_history WHERE {' AND '.join(where)} "
                f"ORDER BY checked_at DESC LIMIT 1",
                params,
            )
            r = cur.fetchone()
            return dict(r) if r else None

    def rank_history(
        self,
        keyword: str,
        days: int = 30,
        device_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = ["keyword = ?", f"checked_at >= datetime('now', '-{int(days)} days')"]
        params: List[Any] = [keyword]
        if device_type:
            where.append("device_type = ?")
            params.append(device_type)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT rank, checked_at, date, status, device_type FROM rank_history "
                f"WHERE {' AND '.join(where)} ORDER BY checked_at ASC",
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    # ── Filters ────────────────────────────────────────────────────────
    @staticmethod
    def _build_where(filters: Dict[str, Any]) -> tuple[str, list]:
        clauses: List[str] = ["1=1"]
        params: List[Any] = []
        if filters.get("grade"):
            clauses.append("grade = ?")
            params.append(filters["grade"])
        if filters.get("category"):
            clauses.append("category = ?")
            params.append(filters["category"])
        grades = filters.get("grades")
        if grades:
            if isinstance(grades, str):
                grades = [g.strip() for g in grades.split(",") if g.strip()]
            if grades:
                placeholders = ",".join(["?"] * len(grades))
                clauses.append(f"grade IN ({placeholders})")
                params.extend(grades)
        if filters.get("status"):
            clauses.append("status = ?")
            params.append(filters["status"])
        min_vol = filters.get("min_search_volume")
        if min_vol:
            clauses.append("COALESCE(search_volume, 0) >= ?")
            params.append(min_vol)
        search = filters.get("search")
        if search:
            clauses.append("keyword LIKE ?")
            params.append(f"%{search}%")
        return ("WHERE " + " AND ".join(clauses), params)
