"""Curated seed builder for the Pathfinder Legion -> Viral Hunter pipeline.

The Viral Hunter should not read the whole historical keyword pool by default.
It should consume a bounded, recent Legion scan with category quotas so the
comment queue stays aligned with the clinic's current focus.
"""

from __future__ import annotations

import os
import sqlite3
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
        with sqlite3.connect(self.db_path) as conn:
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
    ) -> List[ViralSeed]:
        scan_id = scan_run_id or self.latest_completed_legion_scan_id()
        if not scan_id:
            return []

        quotas = quotas or DEFAULT_CATEGORY_QUOTAS
        excludes = list(exclude_patterns or DEFAULT_EXCLUDE_PATTERNS)
        grades = tuple(include_grades)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            placeholders = ",".join("?" for _ in grades)
            rows = conn.execute(
                f"""
                SELECT keyword, category, grade, search_volume, document_count,
                       kei, priority_v3, search_intent
                FROM keyword_insights
                WHERE last_scan_run_id = ?
                  AND grade IN ({placeholders})
                  AND status = 'active'
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
            feedback_penalty = min(20.0, final_gate_count * 2.0) + min(15.0, skip_rate * 15.0)
            adjusted_priority = float(row["priority_v3"] or 0) - feedback_penalty
            scored_rows.append((adjusted_priority, row))

        scored_rows.sort(
            key=lambda item: (
                {"S": 0, "A": 1, "B": 2}.get(item[1]["grade"], 3),
                -item[0],
                -float(item[1]["kei"] or 0),
                -int(item[1]["search_volume"] or 0),
            )
        )

        by_category: Dict[str, List[sqlite3.Row]] = {}
        for _, row in scored_rows:
            by_category.setdefault(row["category"] or "기타", []).append(row)

        selected: List[ViralSeed] = []
        seen = set()
        for category, quota in quotas.items():
            for row in by_category.get(category, [])[:quota]:
                keyword = row["keyword"]
                if keyword in seen:
                    continue
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
                    )
                )
                seen.add(keyword)

        return selected

    def _load_keyword_feedback(self) -> Dict[str, dict]:
        """Summarize Viral Hunter outcomes by matched keyword for seed ranking."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    """
                    SELECT matched_keyword,
                           COUNT(*) AS total_count,
                           SUM(CASE WHEN comment_status = 'skipped' THEN 1 ELSE 0 END) AS skipped_count,
                           SUM(CASE WHEN generated_comment LIKE 'final_gate:%' THEN 1 ELSE 0 END) AS final_gate_count
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
            }
        return feedback
