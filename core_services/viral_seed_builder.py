"""Curated seed builder for the Pathfinder Legion -> Viral Hunter pipeline.

The Viral Hunter should not read the whole historical keyword pool by default.
It should consume a bounded, recent Legion scan with category quotas so the
comment queue stays aligned with the clinic's current focus.
"""

from __future__ import annotations

import os
import sqlite3
from collections import Counter
from contextlib import closing
from dataclasses import dataclass, asdict
from typing import Dict, Iterable, List, Optional


DEFAULT_CATEGORY_QUOTAS: Dict[str, int] = {
    "교통사고": 10,
    "피부/여드름": 12,
    "다이어트": 10,
    "안면비대칭": 6,
    "체형교정": 4,
    "리프팅/탄력": 3,
}

DEFAULT_EXCLUDE_PATTERNS = [
    "전후",
    "다이어트댄스",
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
        with closing(sqlite3.connect(self.db_path)) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM scan_runs
                WHERE status = 'completed'
                  AND scan_type = 'legion'
                ORDER BY completed_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        return int(row[0]) if row else None

    def build(
        self,
        scan_run_id: Optional[int] = None,
        quotas: Optional[Dict[str, int]] = None,
        exclude_patterns: Optional[Iterable[str]] = None,
        include_grades: Iterable[str] = ("S", "A", "B"),
        max_per_intent_per_category: int = DEFAULT_MAX_PER_INTENT_PER_CATEGORY,
    ) -> List[ViralSeed]:
        scan_id = scan_run_id or self.latest_completed_legion_scan_id()
        if not scan_id:
            return []

        quotas = quotas or DEFAULT_CATEGORY_QUOTAS
        excludes = list(exclude_patterns or DEFAULT_EXCLUDE_PATTERNS)
        grades = tuple(include_grades)

        with closing(sqlite3.connect(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in grades)
            status_clause = ""
            if self._table_has_column(conn, "keyword_insights", "status"):
                status_clause = "AND COALESCE(status, 'active') = 'active'"
            rows = conn.execute(
                f"""
                SELECT keyword, category, grade, search_volume, document_count,
                       kei, priority_v3, search_intent
                FROM keyword_insights
                WHERE last_scan_run_id = ?
                  AND grade IN ({placeholders})
                  {status_clause}
                  AND COALESCE(document_count, 0) > 0
                  AND COALESCE(business_core, 0) = 1
                ORDER BY
                  CASE grade WHEN 'S' THEN 0 WHEN 'A' THEN 1 ELSE 2 END,
                  priority_v3 DESC,
                  kei DESC,
                  search_volume DESC
                """,
                (scan_id, *grades),
            ).fetchall()

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
                    )
                )
                seen.add(keyword)

        return selected

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
    ) -> List[dict]:
        if quota <= 0 or not items:
            return []

        selected: List[dict] = []
        deferred: List[dict] = []
        intent_counts: Counter = Counter()

        for item in items:
            intent = item["row"]["search_intent"] or "unknown"
            if intent_counts[intent] < max_per_intent:
                selected.append(item)
                intent_counts[intent] += 1
            else:
                deferred.append(item)

            if len(selected) >= quota:
                return selected[:quota]

        if len(selected) < quota:
            selected.extend(deferred[: quota - len(selected)])

        return selected[:quota]

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
