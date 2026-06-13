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

from core_services.viral_url_canonicalizer import canonicalize_viral_url


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
        with self._conn() as conn:
            where, params = self._build_where(filters or {}, self._columns_for_conn(conn))
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
        with self._conn() as conn:
            columns = self._columns_for_conn(conn)
            order_by = self._build_order_by(sort, columns)
            where, params = self._build_where(filters or {}, columns)
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
        score_breakdown_json = json.dumps(data.get("score_breakdown") or {}, ensure_ascii=False)
        sort_appearances_json = json.dumps(data.get("sort_appearances") or [], ensure_ascii=False)
        url = data.get("url", "")
        canonical_url = data.get("canonical_url") or canonicalize_viral_url(url)
        content_hash = self._content_hash(
            canonical_url or url, data.get("title", ""), data.get("content_preview", "")
        )
        now = datetime.now().isoformat()
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                table_columns = self._columns_for_conn(conn)
                existing_id = None
                storage_url = url
                if canonical_url:
                    cur.execute(
                        f"""
                        SELECT id, url
                        FROM {self.TABLE}
                        WHERE url = ? OR canonical_url = ?
                        ORDER BY CASE WHEN url = ? THEN 0 ELSE 1 END, discovered_at ASC
                        LIMIT 1
                        """,
                        (url, canonical_url, url),
                    )
                    row = cur.fetchone()
                    if row is not None:
                        existing_id = row["id"]
                        storage_url = row["url"] or url
                matched_keywords = data.get("matched_keywords") or []
                matched_keyword = (
                    data.get("matched_keyword")
                    or (matched_keywords[0] if isinstance(matched_keywords, list) and matched_keywords else None)
                )
                insert_values: Dict[str, Any] = {
                    "id": data.get("id"),
                    "platform": data.get("platform"),
                    "url": storage_url,
                    "canonical_url": canonical_url,
                    "title": data.get("title"),
                    "content_preview": data.get("content_preview", ""),
                    "matched_keywords": keywords_json,
                    "category": data.get("category", "기타"),
                    "is_commentable": data.get("is_commentable", True),
                    "comment_status": data.get("comment_status", "pending"),
                    "generated_comment": data.get("generated_comment", ""),
                    "priority_score": data.get("priority_score", 0),
                    "discovered_at": now,
                    "last_scanned_at": now,
                    "scan_count": 1,
                    "content_hash": content_hash,
                    "matched_keyword": matched_keyword,
                    "source_scan_run_id": data.get("source_scan_run_id", 0),
                    "matched_keyword_grade": data.get("matched_keyword_grade"),
                    "matched_keyword_kei": data.get("matched_keyword_kei", 0),
                    "matched_keyword_priority": data.get("matched_keyword_priority", 0),
                    "matched_keyword_category": data.get("matched_keyword_category"),
                    "author": data.get("author"),
                    "posted_at": data.get("posted_at") or data.get("date_str"),
                    "like_count": data.get("like_count", 0),
                    "comment_count": data.get("comment_count", 0),
                    "view_count": data.get("view_count", 0),
                    "exposure_score": data.get("exposure_score", 0),
                    "workability_score": data.get("workability_score", 0),
                    "conversion_fit_score": data.get("conversion_fit_score", 0),
                    "score_breakdown": score_breakdown_json,
                    "search_sort": data.get("search_sort"),
                    "search_rank": data.get("search_rank", 0),
                    "search_start": data.get("search_start", 0),
                    "search_total": data.get("search_total", 0),
                    "sort_appearances": sort_appearances_json,
                    "ai_reviewed": 1 if data.get("ai_reviewed") else 0,
                    "ai_infiltration_score": data.get("ai_infiltration_score", 0),
                    "ai_post_type": data.get("ai_post_type"),
                    "ai_competitor": 1 if data.get("ai_competitor") else 0,
                    "ai_competitor_name": data.get("ai_competitor_name"),
                }
                insert_columns = [
                    column for column in insert_values
                    if column in table_columns
                ]
                placeholders = ", ".join("?" for _ in insert_columns)
                updates = [
                    f"canonical_url = COALESCE(NULLIF(excluded.canonical_url, ''), {self.TABLE}.canonical_url)",
                    "title = excluded.title",
                    "matched_keywords = excluded.matched_keywords",
                    "priority_score = excluded.priority_score",
                    "last_scanned_at = excluded.last_scanned_at",
                    f"scan_count = COALESCE({self.TABLE}.scan_count, 0) + 1",
                    "content_hash = excluded.content_hash",
                ]
                optional_updates = {
                    "matched_keyword": f"matched_keyword = COALESCE(excluded.matched_keyword, {self.TABLE}.matched_keyword)",
                    "source_scan_run_id": f"source_scan_run_id = COALESCE(NULLIF(excluded.source_scan_run_id, 0), {self.TABLE}.source_scan_run_id)",
                    "matched_keyword_grade": f"matched_keyword_grade = COALESCE(excluded.matched_keyword_grade, {self.TABLE}.matched_keyword_grade)",
                    "matched_keyword_kei": f"matched_keyword_kei = COALESCE(NULLIF(excluded.matched_keyword_kei, 0), {self.TABLE}.matched_keyword_kei)",
                    "matched_keyword_priority": f"matched_keyword_priority = COALESCE(NULLIF(excluded.matched_keyword_priority, 0), {self.TABLE}.matched_keyword_priority)",
                    "matched_keyword_category": f"matched_keyword_category = COALESCE(excluded.matched_keyword_category, {self.TABLE}.matched_keyword_category)",
                    "author": f"author = COALESCE(excluded.author, {self.TABLE}.author)",
                    "posted_at": f"posted_at = COALESCE(excluded.posted_at, {self.TABLE}.posted_at)",
                    "like_count": f"like_count = MAX(COALESCE({self.TABLE}.like_count, 0), COALESCE(excluded.like_count, 0))",
                    "comment_count": f"comment_count = MAX(COALESCE({self.TABLE}.comment_count, 0), COALESCE(excluded.comment_count, 0))",
                    "view_count": f"view_count = MAX(COALESCE({self.TABLE}.view_count, 0), COALESCE(excluded.view_count, 0))",
                    "exposure_score": f"exposure_score = MAX(COALESCE({self.TABLE}.exposure_score, 0), COALESCE(excluded.exposure_score, 0))",
                    "workability_score": f"workability_score = COALESCE(NULLIF(excluded.workability_score, 0), {self.TABLE}.workability_score)",
                    "conversion_fit_score": f"conversion_fit_score = COALESCE(NULLIF(excluded.conversion_fit_score, 0), {self.TABLE}.conversion_fit_score)",
                    "score_breakdown": f"score_breakdown = COALESCE(NULLIF(excluded.score_breakdown, '{{}}'), {self.TABLE}.score_breakdown)",
                    "search_sort": f"search_sort = COALESCE(NULLIF(excluded.search_sort, ''), {self.TABLE}.search_sort)",
                    "search_rank": (
                        "search_rank = CASE "
                        "WHEN COALESCE(excluded.search_rank, 0) > 0 "
                        f"AND (COALESCE({self.TABLE}.search_rank, 0) = 0 OR excluded.search_rank < {self.TABLE}.search_rank) "
                        f"THEN excluded.search_rank ELSE {self.TABLE}.search_rank END"
                    ),
                    "search_start": f"search_start = COALESCE(NULLIF(excluded.search_start, 0), {self.TABLE}.search_start)",
                    "search_total": f"search_total = MAX(COALESCE({self.TABLE}.search_total, 0), COALESCE(excluded.search_total, 0))",
                    "sort_appearances": f"sort_appearances = COALESCE(NULLIF(excluded.sort_appearances, '[]'), {self.TABLE}.sort_appearances)",
                    "ai_reviewed": f"ai_reviewed = MAX(COALESCE({self.TABLE}.ai_reviewed, 0), COALESCE(excluded.ai_reviewed, 0))",
                    "ai_infiltration_score": f"ai_infiltration_score = MAX(COALESCE({self.TABLE}.ai_infiltration_score, 0), COALESCE(excluded.ai_infiltration_score, 0))",
                    "ai_post_type": f"ai_post_type = COALESCE(NULLIF(excluded.ai_post_type, ''), {self.TABLE}.ai_post_type)",
                    "ai_competitor": f"ai_competitor = MAX(COALESCE({self.TABLE}.ai_competitor, 0), COALESCE(excluded.ai_competitor, 0))",
                    "ai_competitor_name": f"ai_competitor_name = COALESCE(NULLIF(excluded.ai_competitor_name, ''), {self.TABLE}.ai_competitor_name)",
                }
                updates.extend(
                    update_sql for column, update_sql in optional_updates.items()
                    if column in table_columns
                )
                cur.execute(
                    f"""
                    INSERT INTO {self.TABLE}
                    ({", ".join(insert_columns)})
                    VALUES ({placeholders})
                    ON CONFLICT(url) DO UPDATE SET
                        {", ".join(updates)}
                    """,
                    tuple(insert_values[column] for column in insert_columns),
                )
                # matched_keywords 정규화 테이블에도 반영
                target_id = existing_id or data.get("id")
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
            "platform", "url", "canonical_url", "title", "content_preview", "matched_keywords",
            "category", "is_commentable", "comment_status", "generated_comment",
            "priority_score", "last_scanned_at", "scan_count",
            "matched_keyword", "source_scan_run_id", "matched_keyword_grade",
            "matched_keyword_kei", "matched_keyword_priority", "matched_keyword_category",
            "first_response_at", "response_time_hours", "posted_at",
            "exposure_score", "workability_score", "conversion_fit_score",
            "score_breakdown", "search_sort", "search_rank", "search_start",
            "search_total", "sort_appearances", "ai_reviewed",
            "ai_infiltration_score", "ai_post_type", "ai_competitor",
            "ai_competitor_name",
        }
        safe_changes = {k: v for k, v in changes.items() if k in ALLOWED}
        # matched_keywords는 JSON 직렬화
        if "matched_keywords" in safe_changes and isinstance(safe_changes["matched_keywords"], list):
            safe_changes["matched_keywords"] = json.dumps(
                safe_changes["matched_keywords"], ensure_ascii=False
            )
        if "score_breakdown" in safe_changes and isinstance(safe_changes["score_breakdown"], (dict, list)):
            safe_changes["score_breakdown"] = json.dumps(
                safe_changes["score_breakdown"], ensure_ascii=False
            )
        if "sort_appearances" in safe_changes and isinstance(safe_changes["sort_appearances"], list):
            safe_changes["sort_appearances"] = json.dumps(
                safe_changes["sort_appearances"], ensure_ascii=False
            )
        try:
            with self._conn() as conn:
                table_columns = self._columns_for_conn(conn)
                safe_changes = {
                    key: value for key, value in safe_changes.items()
                    if key in table_columns
                }
                if not safe_changes:
                    return False
                set_clause = ", ".join(f"{k} = ?" for k in safe_changes.keys())
                params = list(safe_changes.values()) + [target_id]
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

        with self._conn() as conn:
            where, params = self._build_where(filters, self._columns_for_conn(conn))
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
    def _columns_for_conn(conn: sqlite3.Connection) -> set[str]:
        try:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({ViralTargetRepository.TABLE})").fetchall()}
        except sqlite3.Error:
            return set()

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
        for json_field, fallback in (("score_breakdown", {}), ("sort_appearances", [])):
            value = d.get(json_field)
            if isinstance(value, str):
                try:
                    d[json_field] = json.loads(value)
                except Exception:
                    d[json_field] = fallback
        return d

    @staticmethod
    def _category_columns(table_columns: Optional[set[str]]) -> List[str]:
        columns = ["category"]
        if table_columns and "matched_keyword_category" in table_columns:
            columns.append("matched_keyword_category")
        return columns

    @staticmethod
    def _append_category_in_clause(
        clauses: List[str],
        params: List[Any],
        categories: List[str],
        table_columns: Optional[set[str]],
    ) -> None:
        if not categories:
            return
        placeholders = ",".join(["?"] * len(categories))
        category_columns = ViralTargetRepository._category_columns(table_columns)
        clauses.append(
            "(" + " OR ".join(f"{column} IN ({placeholders})" for column in category_columns) + ")"
        )
        for _ in category_columns:
            params.extend(categories)

    @staticmethod
    def _append_category_not_in_clause(
        clauses: List[str],
        params: List[Any],
        categories: List[str],
        table_columns: Optional[set[str]],
    ) -> None:
        if not categories:
            return
        placeholders = ",".join(["?"] * len(categories))
        category_columns = ViralTargetRepository._category_columns(table_columns)
        clauses.append(
            " AND ".join(
                f"COALESCE({column}, '') NOT IN ({placeholders})" for column in category_columns
            )
        )
        for _ in category_columns:
            params.extend(categories)

    @staticmethod
    def _build_where(filters: Dict[str, Any], table_columns: Optional[set[str]] = None) -> tuple[str, list]:
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

        category = filters.get("category")
        if category:
            # 콤마 구분 다중값 지원 (골든큐: 다이어트,피부,비대칭/교정,교통사고,통증/디스크)
            if isinstance(category, str) and "," in category:
                cats = [c.strip() for c in category.split(",") if c.strip()]
            else:
                cats = [str(category).strip()]
            ViralTargetRepository._append_category_in_clause(clauses, params, cats, table_columns)

        include_categories = filters.get("include_categories")
        if include_categories and not category:
            if isinstance(include_categories, str):
                include_categories = [c.strip() for c in include_categories.split(",") if c.strip()]
            if include_categories:
                ViralTargetRepository._append_category_in_clause(
                    clauses,
                    params,
                    [str(c).strip() for c in include_categories if str(c).strip()],
                    table_columns,
                )

        exclude_categories = filters.get("exclude_categories")
        if exclude_categories:
            if isinstance(exclude_categories, str):
                exclude_categories = [c.strip() for c in exclude_categories.split(",") if c.strip()]
            if exclude_categories:
                ViralTargetRepository._append_category_not_in_clause(
                    clauses,
                    params,
                    [str(c).strip() for c in exclude_categories if str(c).strip()],
                    table_columns,
                )

        source_scan_run_id = filters.get("source_scan_run_id")
        if source_scan_run_id is not None:
            try:
                clauses.append("source_scan_run_id = ?")
                params.append(int(source_scan_run_id))
            except (TypeError, ValueError):
                pass

        min_score = filters.get("min_score")
        if min_score is not None:
            try:
                clauses.append("COALESCE(priority_score, 0) >= ?")
                params.append(float(min_score))
            except (TypeError, ValueError):
                pass

        min_exposure = filters.get("min_exposure")
        if min_exposure is not None and not hasattr(min_exposure, "default"):
            try:
                clauses.append("COALESCE(exposure_score, 0) >= ?")
                params.append(float(min_exposure))
            except (TypeError, ValueError):
                pass

        min_clinic_fit = filters.get("min_clinic_fit")
        if min_clinic_fit is not None and not hasattr(min_clinic_fit, "default"):
            try:
                clauses.append(f"{ViralTargetRepository._score_breakdown_number_expr('clinic_treatment_fit_score')} >= ?")
                params.append(float(min_clinic_fit))
            except (TypeError, ValueError):
                pass

        min_worksite_efficiency = filters.get("min_worksite_efficiency")
        if min_worksite_efficiency is not None and not hasattr(min_worksite_efficiency, "default"):
            try:
                clauses.append(f"{ViralTargetRepository._score_breakdown_number_expr('worksite_efficiency_score')} >= ?")
                params.append(float(min_worksite_efficiency))
            except (TypeError, ValueError):
                pass

        commentable_only = filters.get("commentable_only")
        if isinstance(commentable_only, str):
            commentable_only = commentable_only.strip().lower() in {"1", "true", "yes", "y", "on"}
        if commentable_only:
            clauses.append("COALESCE(is_commentable, 0) = 1")

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
        else:
            exclude_revisited = filters.get("exclude_revisited")
            if isinstance(exclude_revisited, str):
                exclude_revisited = exclude_revisited.strip().lower() in {"1", "true", "yes", "y", "on"}
            if exclude_revisited:
                clauses.append("COALESCE(scan_count, 1) <= 1")

        search = filters.get("search")
        if search:
            clauses.append("(title LIKE ? OR content_preview LIKE ?)")
            pat = f"%{search}%"
            params.extend([pat, pat])

        # AI 분류 필터 (2026-04-27 추가)
        ai_label = filters.get("ai_ad_label")
        if ai_label:
            if isinstance(ai_label, str) and "," in ai_label:
                labels = [l.strip() for l in ai_label.split(",") if l.strip()]
                placeholders = ",".join(["?"] * len(labels))
                clauses.append(f"ai_ad_label IN ({placeholders})")
                params.extend(labels)
            else:
                clauses.append("ai_ad_label = ?")
                params.append(ai_label)

        min_conf = filters.get("min_confidence")
        if min_conf is not None:
            try:
                clauses.append("ai_ad_confidence >= ?")
                params.append(float(min_conf))
            except (ValueError, TypeError):
                pass

        specialty = filters.get("specialty_match")
        if specialty:
            if isinstance(specialty, str) and "," in specialty:
                tiers = [t.strip() for t in specialty.split(",") if t.strip()]
                placeholders = ",".join(["?"] * len(tiers))
                clauses.append(f"specialty_match IN ({placeholders})")
                params.extend(tiers)
            else:
                clauses.append("specialty_match = ?")
                params.append(specialty)

        post_region = filters.get("post_region")
        if post_region:
            if isinstance(post_region, str) and "," in post_region:
                regions = [r.strip() for r in post_region.split(",") if r.strip()]
                placeholders = ",".join(["?"] * len(regions))
                clauses.append(f"post_region IN ({placeholders})")
                params.extend(regions)
            else:
                clauses.append("post_region = ?")
                params.append(post_region)

        return ("WHERE " + " AND ".join(clauses), params)

    @staticmethod
    def _build_order_by(sort: str, columns: Optional[set] = None) -> str:
        # columns가 주어지면 score_breakdown/특정 컬럼 의존 정렬을 컬럼 존재 여부로 가드
        # (구 스키마/최소 테이블에서 'no such column' 회피). None이면 전부 있다고 가정.
        has_breakdown = columns is None or "score_breakdown" in columns

        def _bd(key: str) -> str:
            return ViralTargetRepository._score_breakdown_number_expr(key)

        if sort == "date":
            return "ORDER BY discovered_at DESC"
        if sort == "scan_count":
            return "ORDER BY scan_count DESC, discovered_at DESC"
        if sort == "exposure":
            return "ORDER BY exposure_score DESC, priority_score DESC, discovered_at DESC"
        if sort == "workability":
            return "ORDER BY workability_score DESC, priority_score DESC, discovered_at DESC"
        if sort == "clinic_fit" and has_breakdown:
            return f"ORDER BY {_bd('clinic_treatment_fit_score')} DESC, priority_score DESC, discovered_at DESC"
        if sort == "worksite_efficiency" and has_breakdown:
            return f"ORDER BY {_bd('worksite_efficiency_score')} DESC, priority_score DESC, discovered_at DESC"
        if sort == "specialty" and (columns is None or "specialty_match" in columns):
            # 미용 특화 우선: high > medium > low > NULL, 그 안에서 신뢰도 → 우선순위
            return ("ORDER BY CASE specialty_match "
                    "WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END, "
                    "ai_ad_confidence DESC, priority_score DESC")
        if sort == "ai_confidence" and (columns is None or "ai_ad_confidence" in columns):
            return "ORDER BY ai_ad_confidence DESC, priority_score DESC"
        # 기본(priority) 정렬: priority_score는 150에서 캡되어 큐 상단(54건+ 동점)에서
        # 변별력을 잃는다 — 동점 묶음이 recency로만 깨지면 고볼륨 commodity 축(다이어트,
        # clinic_fit 34.8)이 시그니처 축(흉터/안면비대칭, clinic_fit 82~89)을 큐 상단에서
        # 밀어낸다. todays-queue(골든큐)와 동일한 전략 신호(worksite→clinic_fit)로 동점을
        # 깨서 두 화면의 순서를 일치시킨다. priority는 여전히 1차 키라 HOT LEAD 임계는 보존.
        if has_breakdown:
            return (
                f"ORDER BY priority_score DESC, {_bd('worksite_efficiency_score')} DESC, "
                f"{_bd('clinic_treatment_fit_score')} DESC, discovered_at DESC"
            )
        return "ORDER BY priority_score DESC, discovered_at DESC"

    @staticmethod
    def _score_breakdown_number_expr(key: str) -> str:
        safe_key = "".join(ch for ch in key if ch.isalnum() or ch == "_")
        return (
            "COALESCE("
            "CASE WHEN json_valid(score_breakdown) "
            f"THEN CAST(json_extract(score_breakdown, '$.{safe_key}') AS REAL) "
            "ELSE 0 END, 0)"
        )
