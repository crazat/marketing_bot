"""LeadRepository — mentions 테이블 전용 Repository.

leads.py(4221줄)의 DB 접근을 캡슐화한 두 번째 Repository.
ViralTargetRepository 패턴을 따름.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional


class LeadRepository:
    """mentions 테이블 접근 전담 Repository."""

    TABLE = "mentions"

    # [M7] 화이트리스트 (update 시 사용) — 함부로 변경 못하게 제한
    ALLOWED_UPDATE_COLUMNS = {
        "status", "memo", "notes", "follow_up_date", "contact_info",
        "score", "score_breakdown", "grade", "trust_score",
        "first_response_at", "response_time_hours",
        "conversion_value", "auto_classified",
        "opportunity_bonus", "engagement_signal",
        "last_reminder_at",
    }

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._columns_cache: Optional[set] = None

    def columns(self) -> set:
        """[T4] mentions 테이블의 컬럼 집합 (캐시).

        동적 컬럼 감지 필요 시 사용. 테이블 스키마가 환경별로 달라도 대응.
        """
        if self._columns_cache is not None:
            return self._columns_cache
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(f"PRAGMA table_info({self.TABLE})")
                self._columns_cache = {row[1] for row in cur.fetchall()}
            except Exception:
                self._columns_cache = set()
        return self._columns_cache

    def has_column(self, name: str) -> bool:
        """컬럼 존재 여부. leads.py의 select_column_safely 대체."""
        return name in self.columns()

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

    # ── Read ───────────────────────────────────────────────────────────
    def get(self, lead_id: int) -> Optional[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {self.TABLE} WHERE id = ?", (lead_id,))
            r = cur.fetchone()
            return dict(r) if r else None

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        where, params = self._build_where(filters or {})
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self.TABLE} {where}", params)
            return int(cur.fetchone()[0])

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort: str = "date",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where, params = self._build_where(filters or {})
        order_by = self._build_order_by(sort)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM {self.TABLE} {where} {order_by} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    def group_by_status(self, filters: Optional[Dict[str, Any]] = None) -> Dict[str, int]:
        """status별 카운트."""
        where, params = self._build_where(filters or {})
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT status, COUNT(*) FROM {self.TABLE} {where} GROUP BY status",
                params,
            )
            return {row[0]: row[1] for row in cur.fetchall() if row[0]}

    # ── Write ──────────────────────────────────────────────────────────
    def update(self, lead_id: int, changes: Dict[str, Any]) -> bool:
        safe = {k: v for k, v in changes.items() if k in self.ALLOWED_UPDATE_COLUMNS}
        if not safe:
            return False
        set_clause = ", ".join(f"{k} = ?" for k in safe.keys())
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {self.TABLE} SET {set_clause} WHERE id = ?",
                [*safe.values(), lead_id],
            )
            conn.commit()
            return cur.rowcount > 0

    def bulk_update_status(self, lead_ids: List[int], new_status: str) -> int:
        if not lead_ids:
            return 0
        placeholders = ",".join(["?"] * len(lead_ids))
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {self.TABLE} SET status = ? WHERE id IN ({placeholders})",
                [new_status, *lead_ids],
            )
            conn.commit()
            return cur.rowcount

    def record_response(
        self,
        lead_id: int,
        response_time_iso: Optional[str] = None,
    ) -> bool:
        """리드 응답 시각 기록 + 응답 시간(시간 단위) 자동 계산."""
        now_iso = response_time_iso or datetime.now().isoformat()
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT scraped_at FROM {self.TABLE} WHERE id = ?", (lead_id,))
            row = cur.fetchone()
            if not row:
                return False
            scraped_at = row[0]
            hours = None
            if scraped_at:
                try:
                    scraped_dt = datetime.fromisoformat(scraped_at.replace("Z", ""))
                    resp_dt = datetime.fromisoformat(now_iso.replace("Z", ""))
                    hours = round((resp_dt - scraped_dt).total_seconds() / 3600, 2)
                except Exception:
                    hours = None
            cur.execute(
                f"UPDATE {self.TABLE} SET first_response_at = ?, response_time_hours = ? WHERE id = ?",
                (now_iso, hours, lead_id),
            )
            conn.commit()
            return cur.rowcount > 0

    # ── Filters ────────────────────────────────────────────────────────
    @staticmethod
    def _build_where(filters: Dict[str, Any]) -> tuple[str, list]:
        clauses: List[str] = ["1=1"]
        params: List[Any] = []

        if filters.get("status"):
            clauses.append("status = ?")
            params.append(filters["status"])
        if filters.get("source"):
            clauses.append("source = ?")
            params.append(filters["source"])
        if filters.get("grade"):
            clauses.append("grade = ?")
            params.append(filters["grade"])

        sources = filters.get("sources")
        if sources:
            if isinstance(sources, str):
                sources = [s.strip() for s in sources.split(",") if s.strip()]
            if sources:
                placeholders = ",".join(["?"] * len(sources))
                clauses.append(f"source IN ({placeholders})")
                params.extend(sources)

        if filters.get("keyword"):
            clauses.append("keyword LIKE ?")
            params.append(f"%{filters['keyword']}%")
        if filters.get("search"):
            clauses.append("(title LIKE ? OR content LIKE ?)")
            pat = f"%{filters['search']}%"
            params.extend([pat, pat])
        if filters.get("min_score"):
            clauses.append("COALESCE(score, 0) >= ?")
            params.append(filters["min_score"])

        # 날짜 범위
        date_filter = filters.get("date_filter")
        if date_filter == "오늘":
            clauses.append("DATE(scraped_at) = DATE('now', 'localtime')")
        elif date_filter == "최근 7일":
            clauses.append("scraped_at >= datetime('now', '-7 days')")
        elif date_filter == "최근 30일":
            clauses.append("scraped_at >= datetime('now', '-30 days')")

        return ("WHERE " + " AND ".join(clauses), params)

    @staticmethod
    def _build_order_by(sort: str) -> str:
        if sort == "score":
            return "ORDER BY COALESCE(score, 0) DESC, scraped_at DESC"
        if sort == "grade":
            return "ORDER BY grade ASC, COALESCE(score, 0) DESC"
        return "ORDER BY scraped_at DESC"
