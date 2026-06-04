"""Curated seed builder for the Pathfinder Legion -> Viral Hunter pipeline.

The Viral Hunter should not read the whole historical keyword pool by default.
It should consume a bounded, recent Legion scan with category quotas so the
comment queue stays aligned with the clinic's current focus.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional

from core_services.gyulim_keyword_profile import GYULIM_KEYWORD_PROFILE


DEFAULT_CATEGORY_QUOTAS: Dict[str, int] = {
    "피부/여드름": 14,
    "다이어트": 12,
    "교통사고": 8,
    "안면비대칭": 8,
    "체형교정": 5,
    "리프팅/탄력": 3,
}

DEFAULT_EXCLUDE_PATTERNS = [
    "전후",
    "다이어트댄스",
    "다이어트 댄스",
    "줌바",
    "댄스학원",
    "엔도",
    "내과",
    "자보 다이어트",
    "실비 다이어트",
    "보험 다이어트",
    "피부과",
    "프락셀",
    "치아교정",
    "임플란트",
    "골프",
]

DEFAULT_MAX_PER_INTENT_PER_CATEGORY = 4
DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY = 2
DEFAULT_MAX_PER_REGION_PER_CATEGORY = 4


@dataclass(frozen=True)
class ViralSeed:
    keyword: str
    scan_run_id: int
    category: str
    grade: str
    search_volume: int
    document_count: int
    kei: float
    priority_v3: float
    search_intent: str
    novelty_score: float = 0.0
    historical_target_count: int = 0
    historical_revisit_rate: float = 0.0
    longtail_score: float = 0.0
    business_value_score: float = 0.0
    high_value_longtail: bool = False

    def to_context(self) -> dict:
        return asdict(self)


class ViralSeedBuilder:
    """Builds a stable, explainable seed list from the latest Legion scan."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            db_path = os.path.join(root, "db", "marketing_data.db")
        self.db_path = db_path

    def latest_completed_legion_scan_id(self) -> Optional[int]:
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                if not self._table_exists(conn, "scan_runs"):
                    return None
                columns = self._table_columns(conn, "scan_runs")
                lineage_filters = []
                if "scan_type" in columns:
                    lineage_filters.append("scan_type = 'legion'")
                if "mode" in columns:
                    lineage_filters.append("mode LIKE '%legion%'")
                if not lineage_filters:
                    return None
                completed_order = "completed_at DESC, id DESC" if "completed_at" in columns else "id DESC"
                row = conn.execute(
                    f"""
                    SELECT id
                    FROM scan_runs
                    WHERE status = 'completed'
                      AND ({" OR ".join(lineage_filters)})
                    ORDER BY {completed_order}
                    LIMIT 1
                    """
                ).fetchone()
        except sqlite3.Error:
            return None
        return int(row[0]) if row else None

    def build(
        self,
        scan_run_id: Optional[int] = None,
        quotas: Optional[Dict[str, int]] = None,
        exclude_patterns: Optional[Iterable[str]] = None,
        include_grades: Iterable[str] = ("S", "A", "B"),
        max_per_intent_per_category: int = DEFAULT_MAX_PER_INTENT_PER_CATEGORY,
        max_per_cluster_per_category: int = DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY,
        max_per_region_per_category: int = DEFAULT_MAX_PER_REGION_PER_CATEGORY,
    ) -> List[ViralSeed]:
        scan_id = scan_run_id or self.latest_completed_legion_scan_id()
        if not scan_id:
            return []

        quotas = quotas or DEFAULT_CATEGORY_QUOTAS
        excludes = list(exclude_patterns or DEFAULT_EXCLUDE_PATTERNS)
        grades = tuple(include_grades)

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, "keyword_insights"):
                    return []
                columns = self._table_columns(conn, "keyword_insights")
                placeholders = ",".join("?" for _ in grades)
                grade_clause = f"AND grade IN ({placeholders})" if "grade" in columns else ""
                grade_params = list(grades) if "grade" in columns else []
                status_clause = "AND COALESCE(status, 'active') = 'active'" if "status" in columns else ""
                document_clause = "AND COALESCE(document_count, 0) > 0" if "document_count" in columns else ""
                business_core_clause = "AND COALESCE(business_core, 0) = 1" if "business_core" in columns else ""
                scan_filter = "1=1"
                scan_params: List[int] = []
                if "last_scan_run_id" in columns and "scan_run_id" in columns:
                    scan_filter = "COALESCE(last_scan_run_id, scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                elif "last_scan_run_id" in columns:
                    scan_filter = "COALESCE(last_scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                elif "scan_run_id" in columns:
                    scan_filter = "COALESCE(scan_run_id, 0) = ?"
                    scan_params.append(scan_id)
                select_cols = [
                    self._select_expr(columns, "keyword", "''"),
                    self._select_expr(columns, "category", "'기타'"),
                    self._select_expr(columns, "grade", "'C'"),
                    self._select_expr(columns, "search_volume", "0"),
                    self._select_expr(columns, "document_count", "0"),
                    self._select_expr(columns, "kei", "0"),
                    self._select_expr(columns, "priority_v3", "0"),
                    self._select_expr(columns, "search_intent", "'unknown'"),
                ]
                high_value_expr = self._select_expr(columns, "high_value_longtail", "0")
                longtail_expr = self._select_expr(columns, "longtail_score", "0")
                business_value_expr = self._select_expr(columns, "business_value_score", "0")
                order_terms = []
                if "grade" in columns:
                    order_terms.append("CASE grade WHEN 'S' THEN 0 WHEN 'A' THEN 1 WHEN 'B' THEN 2 ELSE 3 END")
                for column in ("priority_v3", "kei", "search_volume"):
                    if column in columns:
                        order_terms.append(f"COALESCE({column}, 0) DESC")
                order_clause = ", ".join(order_terms) or "keyword ASC"
                rows = conn.execute(
                    f"""
                    SELECT {", ".join(select_cols)},
                           {high_value_expr},
                           {longtail_expr},
                           {business_value_expr}
                    FROM keyword_insights
                    WHERE {scan_filter}
                      {grade_clause}
                      {status_clause}
                      {document_clause}
                      {business_core_clause}
                    ORDER BY {order_clause}
                    """,
                    (*scan_params, *grade_params),
                ).fetchall()
        except sqlite3.Error:
            return []

        feedback = self._load_keyword_feedback()
        scored_rows = []
        for row in rows:
            keyword = row["keyword"] or ""
            if any(pattern in keyword for pattern in excludes):
                continue
            fb = feedback.get(keyword, {})
            final_gate_count = fb.get("final_gate_count", 0)
            skip_rate = fb.get("skip_rate", 0.0)
            total_count = fb.get("total_count", 0)
            revisit_rate = fb.get("revisit_rate", 0.0)
            feedback_penalty = min(20.0, final_gate_count * 2.0) + min(15.0, skip_rate * 15.0)
            history_penalty = min(40.0, total_count * 1.2) + min(30.0, revisit_rate * 30.0)
            adjusted_priority = float(row["priority_v3"] or 0) - feedback_penalty - history_penalty
            novelty_score = max(
                0.0,
                100.0
                - min(60.0, total_count * 2.0)
                - min(30.0, revisit_rate * 30.0)
                - min(20.0, skip_rate * 20.0),
            )
            scored_rows.append({
                "adjusted_priority": adjusted_priority,
                "novelty_score": novelty_score,
                "feedback": fb,
                "row": row,
            })

        scored_rows.sort(
            key=lambda item: (
                {"S": 0, "A": 1, "B": 2}.get(item["row"]["grade"], 3),
                -int(item["row"]["high_value_longtail"] or 0),
                -float(item["row"]["business_value_score"] or 0),
                -float(item["row"]["longtail_score"] or 0),
                -item["adjusted_priority"],
                -item["novelty_score"],
                -float(item["row"]["kei"] or 0),
                -int(item["row"]["search_volume"] or 0),
            )
        )

        by_category: Dict[str, List[dict]] = {}
        for item in scored_rows:
            row = item["row"]
            by_category.setdefault(row["category"] or "기타", []).append(item)

        selected: List[ViralSeed] = []
        seen = set()
        for category, quota in quotas.items():
            category_rows = self._select_diverse_rows(
                by_category.get(category, []),
                quota,
                max_per_intent_per_category,
                max_per_cluster_per_category,
                max_per_region_per_category,
            )
            for item in category_rows:
                row = item["row"]
                keyword = row["keyword"]
                if keyword in seen:
                    continue
                fb = item["feedback"]
                selected.append(
                    ViralSeed(
                        keyword=keyword,
                        scan_run_id=scan_id,
                        category=row["category"] or "기타",
                        grade=row["grade"] or "C",
                        search_volume=int(row["search_volume"] or 0),
                        document_count=int(row["document_count"] or 0),
                        kei=float(row["kei"] or 0),
                        priority_v3=float(row["priority_v3"] or 0),
                        search_intent=row["search_intent"] or "unknown",
                        novelty_score=float(item["novelty_score"] or 0),
                        historical_target_count=int(fb.get("total_count", 0) or 0),
                        historical_revisit_rate=float(fb.get("revisit_rate", 0.0) or 0.0),
                        longtail_score=float(row["longtail_score"] or 0),
                        business_value_score=float(row["business_value_score"] or 0),
                        high_value_longtail=bool(row["high_value_longtail"] or 0),
                    )
                )
                seen.add(keyword)

        return selected

    def keyword_context_for(self, keywords: Iterable[str]) -> Dict[str, dict]:
        """Return Pathfinder lineage context for exact keywords.

        This is used when Viral Hunter runs with legacy or custom keywords. The
        default curated seed path already carries context, but the fallback path
        still needs scan id, grade, KEI and category attached to discovered
        targets so the queue remains traceable.
        """
        unique_keywords = [
            keyword
            for keyword in dict.fromkeys(str(item).strip() for item in keywords if item)
            if keyword
        ]
        if not unique_keywords:
            return {}

        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                if not self._table_exists(conn, "keyword_insights"):
                    return {}
                columns = self._table_columns(conn, "keyword_insights")
                status_clause = "AND COALESCE(status, 'active') != 'archived'" if "status" in columns else ""
                scan_expr = self._scan_id_expr(columns)
                select_cols = [
                    self._select_expr(columns, "keyword", "''"),
                    self._select_expr(columns, "category", "'기타'"),
                    self._select_expr(columns, "grade", "'C'"),
                    self._select_expr(columns, "search_volume", "0"),
                    self._select_expr(columns, "document_count", "0"),
                    self._select_expr(columns, "kei", "0"),
                    self._select_expr(columns, "priority_v3", "0"),
                    self._select_expr(columns, "search_intent", "'unknown'"),
                    self._select_expr(columns, "longtail_score", "0"),
                    self._select_expr(columns, "business_value_score", "0"),
                    self._select_expr(columns, "high_value_longtail", "0"),
                    scan_expr,
                ]

                rows: List[sqlite3.Row] = []
                for start in range(0, len(unique_keywords), 500):
                    chunk = unique_keywords[start:start + 500]
                    placeholders = ",".join("?" for _ in chunk)
                    rows.extend(
                        conn.execute(
                            f"""
                            SELECT {", ".join(select_cols)}
                            FROM keyword_insights
                            WHERE keyword IN ({placeholders})
                              {status_clause}
                            """,
                            chunk,
                        ).fetchall()
                    )
        except sqlite3.Error:
            return {}

        context: Dict[str, dict] = {}
        for row in rows:
            keyword = row["keyword"]
            if not keyword:
                continue
            context[keyword] = ViralSeed(
                keyword=keyword,
                scan_run_id=int(row["scan_run_id"] or 0),
                category=row["category"] or "기타",
                grade=row["grade"] or "C",
                search_volume=int(row["search_volume"] or 0),
                document_count=int(row["document_count"] or 0),
                kei=float(row["kei"] or 0),
                priority_v3=float(row["priority_v3"] or 0),
                search_intent=row["search_intent"] or "unknown",
                longtail_score=float(row["longtail_score"] or 0),
                business_value_score=float(row["business_value_score"] or 0),
                high_value_longtail=bool(row["high_value_longtail"] or 0),
            ).to_context()
        return context

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (table_name,),
            ).fetchone()
        except sqlite3.Error:
            return False
        return row is not None

    @staticmethod
    def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        try:
            return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
        except sqlite3.Error:
            return set()

    @staticmethod
    def _select_expr(columns: set[str], column_name: str, default_sql: str, alias: Optional[str] = None) -> str:
        output_name = alias or column_name
        if column_name in columns:
            return f"COALESCE({column_name}, {default_sql}) AS {output_name}"
        return f"{default_sql} AS {output_name}"

    @staticmethod
    def _scan_id_expr(columns: set[str]) -> str:
        if "last_scan_run_id" in columns and "scan_run_id" in columns:
            return "COALESCE(last_scan_run_id, scan_run_id, 0) AS scan_run_id"
        if "last_scan_run_id" in columns:
            return "COALESCE(last_scan_run_id, 0) AS scan_run_id"
        if "scan_run_id" in columns:
            return "COALESCE(scan_run_id, 0) AS scan_run_id"
        return "0 AS scan_run_id"

    @staticmethod
    def _table_has_column(conn: sqlite3.Connection, table_name: str, column_name: str) -> bool:
        try:
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        except sqlite3.Error:
            return False
        return any(row[1] == column_name for row in rows)

    @staticmethod
    def _select_diverse_rows(
        items: List[dict],
        quota: int,
        max_per_intent: int,
        max_per_cluster: int = DEFAULT_MAX_PER_CLUSTER_PER_CATEGORY,
        max_per_region: int = DEFAULT_MAX_PER_REGION_PER_CATEGORY,
    ) -> List[dict]:
        if quota <= 0 or not items:
            return []

        selected: List[dict] = []
        deferred: List[dict] = []
        intent_counts: Counter = Counter()
        cluster_counts: Counter = Counter()
        region_counts: Counter = Counter()

        for item in items:
            intent = item["row"]["search_intent"] or "unknown"
            keyword = item["row"]["keyword"] or ""
            category = item["row"]["category"] or "기타"
            cluster = ViralSeedBuilder._keyword_cluster_key(keyword, category)
            region = ViralSeedBuilder._keyword_region_key(keyword)

            within_intent_cap = intent_counts[intent] < max_per_intent
            within_cluster_cap = cluster_counts[cluster] < max_per_cluster
            within_region_cap = region == "unknown" or region_counts[region] < max_per_region

            if within_intent_cap and within_cluster_cap and within_region_cap:
                selected.append(item)
                intent_counts[intent] += 1
                cluster_counts[cluster] += 1
                if region != "unknown":
                    region_counts[region] += 1
            else:
                deferred.append(item)

            if len(selected) >= quota:
                return selected[:quota]

        if len(selected) < quota:
            selected.extend(deferred[: quota - len(selected)])

        return selected[:quota]

    @staticmethod
    def _keyword_region_key(keyword: str) -> str:
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        for region in sorted(
            GYULIM_KEYWORD_PROFILE.neighborhoods + GYULIM_KEYWORD_PROFILE.cheongju_regions,
            key=len,
            reverse=True,
        ):
            region_key = re.sub(r"\s+", "", region.lower())
            if region_key and region_key in compact:
                return region
        return "unknown"

    @staticmethod
    def _keyword_cluster_key(keyword: str, category: str = "") -> str:
        compact = re.sub(r"\s+", "", (keyword or "").lower())
        normalized_category = GYULIM_KEYWORD_PROFILE.normalize_category(category)
        profile = GYULIM_KEYWORD_PROFILE.profile_for(normalized_category)
        core = "generic"
        if profile:
            for term in sorted(profile.core_tokens + profile.category_terms, key=len, reverse=True):
                token = re.sub(r"\s+", "", term.lower())
                if token and token in compact:
                    core = term
                    break

        journey = "general"
        if any(term in compact for term in ("주차", "야간", "주말", "진료시간")):
            journey = "access"
        elif any(term in compact for term in ("부작용", "주의사항", "재발", "치료기간", "기간")):
            journey = "safety"
        elif any(term in compact for term in ("후기", "추천", "괜찮은곳", "잘하는곳")):
            journey = "validation"
        elif any(term in compact for term in ("비용", "가격", "상담", "예약")):
            journey = "decision"

        return f"{normalized_category}:{core}:{journey}"

    def _load_keyword_feedback(self) -> Dict[str, dict]:
        """Summarize Viral Hunter outcomes by matched keyword for seed ranking."""
        try:
            with closing(sqlite3.connect(self.db_path)) as conn:
                conn.row_factory = sqlite3.Row
                scan_count_expr = "COALESCE(scan_count, 1)"
                if not self._table_has_column(conn, "viral_targets", "scan_count"):
                    scan_count_expr = "1"
                generated_expr = "generated_comment"
                if not self._table_has_column(conn, "viral_targets", "generated_comment"):
                    generated_expr = "''"
                rows = conn.execute(
                    f"""
                    SELECT matched_keyword,
                           COUNT(*) AS total_count,
                           SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) AS skipped_count,
                           SUM(CASE WHEN {generated_expr} LIKE 'final_gate:%' THEN 1 ELSE 0 END) AS final_gate_count,
                           SUM(CASE WHEN {scan_count_expr} > 1 THEN 1 ELSE 0 END) AS revisited_count,
                           AVG({scan_count_expr}) AS avg_scan_count
                    FROM viral_targets
                    WHERE matched_keyword IS NOT NULL
                    GROUP BY matched_keyword
                    """
                ).fetchall()
        except sqlite3.Error:
            return {}

        feedback: Dict[str, dict] = {}
        for row in rows:
            total = int(row["total_count"] or 0)
            skipped = int(row["skipped_count"] or 0)
            feedback[row["matched_keyword"]] = {
                "total_count": total,
                "skipped_count": skipped,
                "final_gate_count": int(row["final_gate_count"] or 0),
                "skip_rate": (skipped / total) if total else 0.0,
                "revisited_count": int(row["revisited_count"] or 0),
                "revisit_rate": (int(row["revisited_count"] or 0) / total) if total else 0.0,
                "avg_scan_count": float(row["avg_scan_count"] or 1.0),
            }
        return feedback
