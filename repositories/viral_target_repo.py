"""ViralTargetRepository — viral_targets 테이블 전용 Repository (PoC).

database.py의 viral_targets 관련 메서드를 캡슐화한 첫 리팩토링 단위.
기존 DatabaseManager는 그대로 유지되며, 새 코드에서 이 Repository를 사용하면
- 연결 관리 자동 (try/finally 내재)
- 타입 힌트 강화
- 테스트 격리 용이 (db_path 주입)

**마이그레이션 가이드**: 새 엔드포인트·백그라운드 작업에서 DatabaseManager 대신 이
Repository를 사용. 기존 코드는 점진적 교체.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, Iterator, List, Optional


class ViralTargetRepository:
    """viral_targets 테이블 접근 전담 Repository."""

    TABLE = "viral_targets"

    def __init__(self, db_path: str):
        self.db_path = db_path

    # ── Connection management ──────────────────────────────────────────
    @contextmanager
    def _conn(self, row_factory=None) -> Iterator[sqlite3.Connection]:
        """연결을 try/finally로 감싼 컨텍스트 매니저."""
        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            if row_factory is not None:
                conn.row_factory = row_factory
            else:
                conn.row_factory = sqlite3.Row
            yield conn
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    # ── Read ───────────────────────────────────────────────────────────
    def get(self, target_id: str) -> Optional[Dict[str, Any]]:
        """id로 단건 조회."""
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT * FROM {self.TABLE} WHERE id = ?", (target_id,))
            row = cur.fetchone()
            if row is None:
                return None
            return self._row_to_dict(row)

    def count(self, filters: Optional[Dict[str, Any]] = None) -> int:
        """필터 조건에 맞는 레코드 총 개수."""
        where, params = self._build_where(filters or {})
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(*) FROM {self.TABLE} {where}", params)
            return int(cur.fetchone()[0])

    def list(
        self,
        filters: Optional[Dict[str, Any]] = None,
        sort: str = "priority",
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """필터·정렬·페이지네이션된 목록 조회."""
        where, params = self._build_where(filters or {})
        order_by = self._build_order_by(sort)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"SELECT * FROM {self.TABLE} {where} {order_by} LIMIT ? OFFSET ?",
                (*params, limit, offset),
            )
            return [self._row_to_dict(r) for r in cur.fetchall()]

    # ── Write ──────────────────────────────────────────────────────────
    def insert(self, data: Dict[str, Any]) -> bool:
        """새 viral_target 삽입 (URL 충돌 시 scan_count 증가).

        returns: 성공 여부.
        """
        keywords_json = json.dumps(data.get("matched_keywords", []), ensure_ascii=False)
        content_hash = self._content_hash(
            data.get("url", ""), data.get("title", ""), data.get("content_preview", "")
        )
        now = datetime.now().isoformat()
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"""
                    INSERT INTO {self.TABLE}
                    (id, platform, url, title, content_preview, matched_keywords,
                     category, is_commentable, comment_status, generated_comment,
                     priority_score, discovered_at, last_scanned_at, scan_count, content_hash)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        title = excluded.title,
                        matched_keywords = excluded.matched_keywords,
                        priority_score = excluded.priority_score,
                        last_scanned_at = excluded.last_scanned_at,
                        scan_count = {self.TABLE}.scan_count + 1,
                        content_hash = excluded.content_hash
                    """,
                    (
                        data.get("id"),
                        data.get("platform"),
                        data.get("url"),
                        data.get("title"),
                        data.get("content_preview", ""),
                        keywords_json,
                        data.get("category", "기타"),
                        data.get("is_commentable", True),
                        data.get("comment_status", "pending"),
                        data.get("generated_comment", ""),
                        data.get("priority_score", 0),
                        now,
                        now,
                        1,
                        content_hash,
                    ),
                )
                # matched_keywords 정규화 테이블에도 반영
                target_id = data.get("id")
                kws = data.get("matched_keywords") or []
                if target_id and isinstance(kws, list) and kws:
                    cur.executemany(
                        "INSERT OR IGNORE INTO viral_target_keywords(viral_target_id, keyword) VALUES (?, ?)",
                        [(target_id, str(k).strip()) for k in kws if k and str(k).strip()],
                    )
                conn.commit()
                return True
        except Exception:
            return False

    def update(self, target_id: str, changes: Dict[str, Any]) -> bool:
        """부분 업데이트 (화이트리스트된 컬럼만)."""
        ALLOWED = {
            "platform", "url", "title", "content_preview", "matched_keywords",
            "category", "is_commentable", "comment_status", "generated_comment",
            "priority_score", "last_scanned_at", "scan_count",
            "first_response_at", "response_time_hours", "posted_at",
        }
        safe_changes = {k: v for k, v in changes.items() if k in ALLOWED}
        if not safe_changes:
            return False
        # matched_keywords는 JSON 직렬화
        if "matched_keywords" in safe_changes and isinstance(safe_changes["matched_keywords"], list):
            safe_changes["matched_keywords"] = json.dumps(
                safe_changes["matched_keywords"], ensure_ascii=False
            )
        set_clause = ", ".join(f"{k} = ?" for k in safe_changes.keys())
        params = list(safe_changes.values()) + [target_id]
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    f"UPDATE {self.TABLE} SET {set_clause} WHERE id = ?",
                    params,
                )
                conn.commit()
                return cur.rowcount > 0
        except Exception:
            return False

    def bulk_update_status_by_filter(
        self,
        new_status: str,
        filters: Dict[str, Any],
        max_affected: int = 10000,
    ) -> Dict[str, int]:
        """필터 조건에 맞는 레코드 일괄 상태 변경."""
        # 먼저 개수 확인
        matched = self.count(filters)
        if matched > max_affected:
            raise ValueError(f"매칭 {matched}건이 max_affected({max_affected}) 초과")

        where, params = self._build_where(filters)
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(
                f"UPDATE {self.TABLE} SET comment_status = ? {where}",
                [new_status, *params],
            )
            conn.commit()
            return {"matched": matched, "updated": cur.rowcount}

    # ── Helpers ────────────────────────────────────────────────────────
    @staticmethod
    def _content_hash(url: str, title: str, content: str) -> str:
        raw = f"{url}|{title}|{content[:500]}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
        d = dict(row)
        # matched_keywords JSON 디코드 (존재 시)
        mk = d.get("matched_keywords")
        if isinstance(mk, str):
            try:
                d["matched_keywords"] = json.loads(mk)
            except Exception:
                d["matched_keywords"] = []
        return d

    @staticmethod
    def _build_where(filters: Dict[str, Any]) -> tuple[str, list]:
        """GET /targets와 동일한 필터 규칙."""
        clauses: List[str] = ["1=1"]
        params: List[Any] = []

        effective_status = filters.get("comment_status") or filters.get("status")
        if effective_status:
            clauses.append("comment_status = ?")
            params.append(effective_status)

        platforms = filters.get("platforms")
        if platforms:
            if isinstance(platforms, str):
                platforms = [p.strip() for p in platforms.split(",") if p.strip()]
            if platforms:
                placeholders = ",".join(["?"] * len(platforms))
                clauses.append(f"platform IN ({placeholders})")
                params.extend(platforms)
        elif filters.get("platform"):
            clauses.append("platform = ?")
            params.append(filters["platform"])

        if filters.get("category"):
            clauses.append("category = ?")
            params.append(filters["category"])

        scan_batch = filters.get("scan_batch")
        date_filter = filters.get("date_filter")
        if scan_batch:
            clauses.append("strftime('%Y-%m-%d %H', discovered_at) = ?")
            params.append(scan_batch)
        elif date_filter:
            if date_filter == "오늘":
                clauses.append("DATE(discovered_at) = DATE('now', 'localtime')")
            elif date_filter == "최근 7일":
                clauses.append("discovered_at >= datetime('now', '-7 days')")
            elif date_filter == "최근 30일":
                clauses.append("discovered_at >= datetime('now', '-30 days')")

        min_scan_count = filters.get("min_scan_count")
        if min_scan_count and min_scan_count > 0:
            clauses.append("scan_count >= ?")
            params.append(min_scan_count)

        search = filters.get("search")
        if search:
            clauses.append("(title LIKE ? OR content_preview LIKE ?)")
            pat = f"%{search}%"
            params.extend([pat, pat])

        return ("WHERE " + " AND ".join(clauses), params)

    @staticmethod
    def _build_order_by(sort: str) -> str:
        if sort == "date":
            return "ORDER BY discovered_at DESC"
        if sort == "scan_count":
            return "ORDER BY scan_count DESC, discovered_at DESC"
        return "ORDER BY priority_score DESC, discovered_at DESC"
