"""CompetitorRepository — 경쟁사 관련 3개 테이블 전담 Repository.

테이블:
- competitor_reviews: 리뷰 수집 (sentiment, keywords)
- competitor_weaknesses: 약점 분석 결과
- competitor_rankings: 경쟁사 키워드별 순위 추적
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Optional


class CompetitorRepository:
    """경쟁사 데이터 접근 전담."""

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

    # ── Reviews ────────────────────────────────────────────────────────
    def list_reviews(
        self,
        competitor_name: Optional[str] = None,
        sentiment: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        where = ["1=1"]
        params: List[Any] = []
        if competitor_name:
            where.append("competitor_name = ?")
            params.append(competitor_name)
        if sentiment:
            where.append("sentiment = ?")
            params.append(sentiment)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM competitor_reviews WHERE {' AND '.join(where)} "
                f"ORDER BY scraped_at DESC LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    def count_reviews(
        self,
        competitor_name: Optional[str] = None,
        sentiment: Optional[str] = None,
    ) -> int:
        where = ["1=1"]
        params: List[Any] = []
        if competitor_name:
            where.append("competitor_name = ?")
            params.append(competitor_name)
        if sentiment:
            where.append("sentiment = ?")
            params.append(sentiment)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT COUNT(*) FROM competitor_reviews WHERE {' AND '.join(where)}",
                params,
            )
            return int(cur.fetchone()[0])

    def sentiment_breakdown(self, competitor_name: Optional[str] = None) -> Dict[str, int]:
        where = ["1=1"]
        params: List[Any] = []
        if competitor_name:
            where.append("competitor_name = ?")
            params.append(competitor_name)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT sentiment, COUNT(*) FROM competitor_reviews WHERE "
                f"{' AND '.join(where)} GROUP BY sentiment",
                params,
            )
            return {r[0] or "unknown": r[1] for r in cur.fetchall()}

    # ── Weaknesses ─────────────────────────────────────────────────────
    def list_weaknesses(
        self,
        competitor_name: Optional[str] = None,
        min_severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        where = ["1=1"]
        params: List[Any] = []
        if competitor_name:
            where.append("competitor_name = ?")
            params.append(competitor_name)
        if min_severity:
            # severity 순서: Low < Medium < High
            order = {"Low": 0, "Medium": 1, "High": 2}
            min_v = order.get(min_severity, 0)
            # SQLite에서 순서 처리는 CASE 사용
            where.append(
                "CASE severity WHEN 'Low' THEN 0 WHEN 'Medium' THEN 1 WHEN 'High' THEN 2 ELSE 0 END >= ?"
            )
            params.append(min_v)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM competitor_weaknesses WHERE {' AND '.join(where)} "
                f"ORDER BY created_at DESC",
                params,
            )
            return [dict(r) for r in cur.fetchall()]

    def insert_weakness(
        self,
        competitor_name: str,
        weakness_type: str,
        description: str,
        severity: str = "Medium",
        source_url: Optional[str] = None,
        opportunity_keywords: Optional[str] = None,
    ) -> bool:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO competitor_weaknesses
                (competitor_name, weakness_type, description, severity, source_url, opportunity_keywords)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (competitor_name, weakness_type, description, severity, source_url, opportunity_keywords),
            )
            conn.commit()
            return True

    # ── Rankings ───────────────────────────────────────────────────────
    def upsert_ranking(
        self,
        competitor_name: str,
        keyword: str,
        rank: int,
        scanned_date: Optional[str] = None,
        note: Optional[str] = None,
    ) -> bool:
        """경쟁사 키워드 순위 기록 (날짜별 upsert)."""
        with self._conn() as conn:
            cur = conn.cursor()
            if scanned_date:
                cur.execute(
                    """
                    INSERT INTO competitor_rankings(competitor_name, keyword, rank, scanned_date, note)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(competitor_name, keyword, scanned_date) DO UPDATE
                    SET rank = excluded.rank, note = excluded.note
                    """,
                    (competitor_name, keyword, rank, scanned_date, note),
                )
            else:
                cur.execute(
                    """
                    INSERT INTO competitor_rankings(competitor_name, keyword, rank, note)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(competitor_name, keyword, scanned_date) DO UPDATE
                    SET rank = excluded.rank, note = excluded.note
                    """,
                    (competitor_name, keyword, rank, note),
                )
            conn.commit()
            return True

    def latest_rank(self, competitor_name: str, keyword: str) -> Optional[int]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT rank FROM competitor_rankings
                WHERE competitor_name = ? AND keyword = ?
                ORDER BY scanned_date DESC LIMIT 1
                """,
                (competitor_name, keyword),
            )
            row = cur.fetchone()
            return int(row[0]) if row else None

    def rank_history(
        self,
        competitor_name: str,
        keyword: str,
        days: int = 30,
    ) -> List[Dict[str, Any]]:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"""
                SELECT rank, scanned_date, note FROM competitor_rankings
                WHERE competitor_name = ? AND keyword = ?
                  AND scanned_date >= DATE('now', '-{int(days)} days')
                ORDER BY scanned_date ASC
                """,
                (competitor_name, keyword),
            )
            return [dict(r) for r in cur.fetchall()]
