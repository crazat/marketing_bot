"""Quality audit for the Pathfinder -> Viral Hunter handoff.

The audit is intentionally read-only. It summarizes whether Pathfinder seeds
are turning into usable Viral Hunter targets by treatment axis, keyword grade,
and execution lens.
"""

from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional

from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE
from core_services.viral_seed_builder import canonical_category_for_keyword


ACTIONABLE_STATUSES = {"pending", "generated", "posted", "approved"}
SURVIVED_STATUSES = ACTIONABLE_STATUSES | {"raw_backlog"}
FILTERED_PREFIXES = ("filtered_out",)


@dataclass
class LaneStats:
    total: int = 0
    actionable: int = 0
    survived: int = 0
    filtered: int = 0
    strict_fit: int = 0
    axis_observed: int = 0
    lens_observed: int = 0
    priority_sum: float = 0.0
    axis_fit_sum: float = 0.0
    lens_fit_sum: float = 0.0
    clinic_fit_sum: float = 0.0
    worksite_sum: float = 0.0
    status_counts: Counter = field(default_factory=Counter)
    grade_counts: Counter = field(default_factory=Counter)
    lens_counts: Counter = field(default_factory=Counter)
    variant_counts: Counter = field(default_factory=Counter)

    def add(
        self,
        *,
        status: str,
        grade: str,
        lens: str,
        query_variant: str,
        priority: float,
        axis_fit: Optional[float],
        lens_fit: Optional[float],
        clinic_fit: Optional[float],
        worksite_efficiency: Optional[float],
        strict_fit: bool,
    ) -> None:
        self.total += 1
        self.priority_sum += priority
        self.status_counts[status] += 1
        self.grade_counts[grade] += 1
        self.lens_counts[lens] += 1
        self.variant_counts[query_variant] += 1
        if status in ACTIONABLE_STATUSES:
            self.actionable += 1
        if status in SURVIVED_STATUSES:
            self.survived += 1
        if status.startswith(FILTERED_PREFIXES) or status == "manual_review":
            self.filtered += 1
        if strict_fit:
            self.strict_fit += 1
        if axis_fit is not None:
            self.axis_observed += 1
            self.axis_fit_sum += axis_fit
        if lens_fit is not None:
            self.lens_observed += 1
            self.lens_fit_sum += lens_fit
        if clinic_fit is not None:
            self.clinic_fit_sum += clinic_fit
        if worksite_efficiency is not None:
            self.worksite_sum += worksite_efficiency

    @staticmethod
    def _rate(numerator: int, denominator: int) -> float:
        return round(numerator / denominator, 4) if denominator else 0.0

    @staticmethod
    def _avg(total: float, count: int) -> float:
        return round(total / count, 2) if count else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "total": self.total,
            "actionable": self.actionable,
            "survived": self.survived,
            "filtered": self.filtered,
            "strict_fit": self.strict_fit,
            "actionable_rate": self._rate(self.actionable, self.total),
            "survival_rate": self._rate(self.survived, self.total),
            "strict_fit_rate": self._rate(self.strict_fit, self.total),
            "avg_priority": self._avg(self.priority_sum, self.total),
            "avg_axis_fit": self._avg(self.axis_fit_sum, self.axis_observed),
            "avg_lens_fit": self._avg(self.lens_fit_sum, self.lens_observed),
            "avg_clinic_fit": self._avg(self.clinic_fit_sum, self.total),
            "avg_worksite_efficiency": self._avg(self.worksite_sum, self.total),
            "axis_observed": self.axis_observed,
            "lens_observed": self.lens_observed,
            "axis_coverage_rate": self._rate(self.axis_observed, self.total),
            "lens_coverage_rate": self._rate(self.lens_observed, self.total),
            "status_counts": dict(self.status_counts),
            "grade_counts": dict(self.grade_counts),
            "lens_counts": dict(self.lens_counts),
            "query_variant_counts": dict(self.variant_counts),
        }


def _default_db_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "db", "marketing_data.db")


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _select_expr(columns: set[str], name: str, fallback: str, alias: Optional[str] = None) -> str:
    output = alias or name
    if name in columns:
        return name if output == name else f"{name} AS {output}"
    return f"{fallback} AS {output}"


def _parse_json(value: object, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default
    return default


def _number(value: object, default: Optional[float] = 0.0) -> Optional[float]:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _grade(value: object) -> str:
    text = str(value or "").strip().upper()
    return text if text in {"S", "A", "B", "C", "D"} else "unknown"


def _status(value: object) -> str:
    return str(value or "pending").strip() or "pending"


def _row_value(row: sqlite3.Row, name: str, default: object = "") -> object:
    try:
        return row[name]
    except (IndexError, KeyError, TypeError):
        return default


def _matched_keyword_candidates(row: sqlite3.Row) -> List[str]:
    candidates: List[str] = []

    def add(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in candidates:
            candidates.append(text)

    add(_row_value(row, "matched_keyword"))
    parsed = _parse_json(_row_value(row, "matched_keywords"), [])
    if isinstance(parsed, list):
        for item in parsed:
            add(item)
    elif isinstance(parsed, str):
        add(parsed)
    return candidates


def _category(row: sqlite3.Row) -> str:
    raw = _row_value(row, "matched_keyword_category") or _row_value(row, "category") or "기타"
    normalized = ACTIVE_KEYWORD_PROFILE.normalize_category(str(raw))
    for keyword in _matched_keyword_candidates(row):
        candidate = canonical_category_for_keyword(keyword, normalized)
        if ACTIVE_KEYWORD_PROFILE.profile_for(candidate):
            return candidate
    return normalized


def _lens(score_breakdown: Dict[str, Any]) -> str:
    text = str(score_breakdown.get("pathfinder_execution_lens") or "").strip().lower()
    return text or "unknown"


def _variant(score_breakdown: Dict[str, Any]) -> str:
    text = str(score_breakdown.get("pathfinder_query_variant") or "").strip()
    return text or "base"


def _score_from_breakdown(score_breakdown: Dict[str, Any], key: str) -> Optional[float]:
    return _number(score_breakdown.get(key), None)


def _row_sample(
    row: sqlite3.Row,
    *,
    category: str,
    grade: str,
    status: str,
    lens: str,
    query_variant: str,
    priority: float,
    axis_fit: Optional[float],
    lens_fit: Optional[float],
    clinic_fit: Optional[float],
    worksite_efficiency: Optional[float],
    strict_fit: bool,
) -> Dict[str, Any]:
    return {
        "id": row["id"] or "",
        "url": row["url"] or "",
        "title": row["title"] or "",
        "platform": row["platform"] or "",
        "category": category,
        "grade": grade,
        "status": status,
        "lens": lens,
        "query_variant": query_variant,
        "priority": round(priority, 2),
        "axis_fit": axis_fit,
        "lens_fit": lens_fit,
        "clinic_fit": clinic_fit,
        "worksite_efficiency": worksite_efficiency,
        "strict_fit": strict_fit,
        "matched_keyword": row["matched_keyword"] or "",
    }


def _sample_for_lane(records: List[Dict[str, Any]], lane_type: str, lane: str, limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return []
    if lane_type == "category":
        matched = [record for record in records if record["category"] == lane]
    elif lane_type == "grade":
        matched = [record for record in records if record["grade"] == lane]
    elif lane_type == "lens":
        matched = [record for record in records if record["lens"] == lane]
    elif lane_type == "category_lens":
        category, _, lens = lane.partition("::")
        matched = [
            record for record in records
            if record["category"] == category and record["lens"] == lens
        ]
    else:
        matched = []
    matched.sort(
        key=lambda record: (
            bool(record.get("strict_fit")),
            float(record.get("priority") or 0.0),
        ),
        reverse=True,
    )
    return matched[:limit]


def _review_samples(
    records: List[Dict[str, Any]],
    weak_lanes: List[Dict[str, Any]],
    *,
    sample_per_lane: int,
) -> Dict[str, Any]:
    strict = [record for record in records if record.get("strict_fit")]
    actionable = [record for record in records if record.get("status") in ACTIONABLE_STATUSES]
    filtered = [
        record for record in records
        if str(record.get("status") or "").startswith(FILTERED_PREFIXES)
        or record.get("status") == "manual_review"
    ]
    sort_key = lambda record: float(record.get("priority") or 0.0)
    strict.sort(key=sort_key, reverse=True)
    actionable.sort(key=sort_key, reverse=True)
    filtered.sort(key=sort_key, reverse=True)

    weak_samples = []
    for lane in weak_lanes[:10]:
        samples = _sample_for_lane(
            records,
            str(lane.get("type") or ""),
            str(lane.get("lane") or ""),
            sample_per_lane,
        )
        if samples:
            weak_samples.append({
                "type": lane.get("type"),
                "lane": lane.get("lane"),
                "reasons": lane.get("reasons") or [],
                "samples": samples,
            })

    return {
        "top_strict_fit": strict[:sample_per_lane],
        "top_actionable": actionable[:sample_per_lane],
        "top_filtered": filtered[:sample_per_lane],
        "weak_lane_samples": weak_samples,
    }


def latest_viral_source_scan_id(db_path: Optional[str] = None) -> Optional[int]:
    path = db_path or _default_db_path()
    if not os.path.exists(path):
        return None
    with sqlite3.connect(path) as conn:
        if not _table_exists(conn, "viral_targets"):
            return None
        columns = _columns(conn, "viral_targets")
        if "source_scan_run_id" not in columns:
            return None
        row = conn.execute(
            """
            SELECT MAX(source_scan_run_id)
            FROM viral_targets
            WHERE COALESCE(source_scan_run_id, 0) > 0
            """
        ).fetchone()
        scan_id = row[0] if row else None
        return int(scan_id) if scan_id else None


def _fetch_rows(
    conn: sqlite3.Connection,
    *,
    source_scan_run_id: Optional[int],
    days: Optional[int],
    limit: Optional[int],
) -> List[sqlite3.Row]:
    columns = _columns(conn, "viral_targets")
    if not columns:
        return []

    select_cols = [
        _select_expr(columns, "id", "''"),
        _select_expr(columns, "url", "''"),
        _select_expr(columns, "title", "''"),
        _select_expr(columns, "platform", "''"),
        _select_expr(columns, "category", "'기타'"),
        _select_expr(columns, "matched_keyword", "''"),
        _select_expr(columns, "matched_keywords", "'[]'"),
        _select_expr(columns, "matched_keyword_grade", "''"),
        _select_expr(columns, "matched_keyword_category", "''"),
        _select_expr(columns, "comment_status", "'pending'"),
        _select_expr(columns, "priority_score", "0"),
        _select_expr(columns, "score_breakdown", "'{}'"),
        _select_expr(columns, "source_scan_run_id", "0"),
        _select_expr(columns, "discovered_at", "''"),
    ]
    where: List[str] = []
    params: List[Any] = []
    if source_scan_run_id is not None and "source_scan_run_id" in columns:
        where.append("COALESCE(source_scan_run_id, 0) = ?")
        params.append(int(source_scan_run_id))
    if days is not None and "discovered_at" in columns:
        where.append("discovered_at >= datetime('now', ?)")
        params.append(f"-{int(days)} day")
    where_sql = "WHERE " + " AND ".join(where) if where else ""
    limit_sql = ""
    if limit is not None and int(limit) > 0:
        limit_sql = f" LIMIT {int(limit)}"

    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT {", ".join(select_cols)}
        FROM viral_targets
        {where_sql}
        ORDER BY COALESCE(priority_score, 0) DESC, discovered_at DESC
        {limit_sql}
        """,
        params,
    ).fetchall()


def _is_strict_fit(
    *,
    status: str,
    lens: str,
    axis_fit: Optional[float],
    lens_fit: Optional[float],
    clinic_fit: Optional[float],
    worksite_efficiency: Optional[float],
    min_axis_fit: float,
    min_lens_fit: float,
    min_clinic_fit: float,
    min_worksite_efficiency: float,
) -> bool:
    if status not in SURVIVED_STATUSES:
        return False
    axis_ok = (axis_fit if axis_fit is not None else clinic_fit or 0.0) >= min_axis_fit
    clinic_ok = (clinic_fit or 0.0) >= min_clinic_fit
    worksite_ok = (worksite_efficiency or 0.0) >= min_worksite_efficiency
    if lens in {"", "unknown", "service"}:
        lens_ok = True
    else:
        lens_ok = (lens_fit if lens_fit is not None else 0.0) >= min_lens_fit
    return bool(axis_ok and lens_ok and clinic_ok and worksite_ok)


def _weak_lane_reasons(metrics: Dict[str, Any], *, min_lane_total: int) -> List[str]:
    if int(metrics.get("total") or 0) < min_lane_total:
        return []
    reasons: List[str] = []
    if float(metrics.get("axis_coverage_rate") or 0.0) < 0.50:
        reasons.append("missing_axis_fit_metrics")
    if float(metrics.get("lens_coverage_rate") or 0.0) < 0.50 and set(metrics.get("lens_counts") or {}) - {"unknown", "service"}:
        reasons.append("missing_lens_fit_metrics")
    if float(metrics.get("survival_rate") or 0.0) < 0.35:
        reasons.append("low_survival_rate")
    if float(metrics.get("strict_fit_rate") or 0.0) < 0.25:
        reasons.append("low_strict_fit_rate")
    if metrics.get("axis_observed") and float(metrics.get("avg_axis_fit") or 0.0) < 55.0:
        reasons.append("low_axis_fit")
    if metrics.get("lens_observed") and float(metrics.get("avg_lens_fit") or 0.0) < 55.0:
        reasons.append("low_lens_fit")
    if float(metrics.get("avg_worksite_efficiency") or 0.0) < 55.0:
        reasons.append("low_worksite_efficiency")
    return reasons


def _action_for_reason(reason: str) -> str:
    actions = {
        "missing_axis_fit_metrics": "rerun Viral Hunter with current scoring or rescore stored targets to populate pathfinder_axis_fit_*",
        "missing_lens_fit_metrics": "rerun Viral Hunter with current scoring or rescore stored targets to populate pathfinder_lens_fit_*",
        "low_survival_rate": "inspect filtered statuses and tune search surfaces before increasing volume",
        "low_strict_fit_rate": "tighten seed-to-post fit gates for this lane before scaling outreach",
        "low_axis_fit": "tighten treatment-axis query anchors and negative terms for this lane",
        "low_lens_fit": "adjust lens-specific query variants and post-fit terms for this lane",
        "low_worksite_efficiency": "prefer higher-workability surfaces, recency, unanswered threads, and cafe/kin depth for this lane",
    }
    return actions.get(reason, "review this lane manually before scaling")


def _lane_seed_coverage(
    seed_counts: Dict[str, int],
    lane_summary: Dict[str, Dict[str, Any]],
    *,
    min_targets_per_seed: float,
    min_strict_fit_per_seed: float,
) -> Dict[str, Dict[str, Any]]:
    coverage: Dict[str, Dict[str, Any]] = {}
    for lane, raw_seed_count in sorted((seed_counts or {}).items()):
        seed_count = int(raw_seed_count or 0)
        if seed_count <= 0:
            continue
        metrics = lane_summary.get(lane) or {}
        target_count = int(metrics.get("total") or 0)
        survived = int(metrics.get("survived") or 0)
        strict_fit = int(metrics.get("strict_fit") or 0)
        target_per_seed = round(target_count / seed_count, 4)
        survived_per_seed = round(survived / seed_count, 4)
        strict_fit_per_seed = round(strict_fit / seed_count, 4)
        gap_reasons: List[str] = []
        if target_count == 0:
            gap_reasons.append("no_targets")
        elif target_per_seed < min_targets_per_seed:
            gap_reasons.append("low_target_per_seed")
        if strict_fit_per_seed < min_strict_fit_per_seed:
            gap_reasons.append("low_strict_fit_per_seed")
        if metrics and float(metrics.get("survival_rate") or 0.0) < 0.35:
            gap_reasons.append("low_survival_rate")
        coverage[lane] = {
            "seed_count": seed_count,
            "target_count": target_count,
            "survived": survived,
            "strict_fit": strict_fit,
            "target_per_seed": target_per_seed,
            "survived_per_seed": survived_per_seed,
            "strict_fit_per_seed": strict_fit_per_seed,
            "survival_rate": float(metrics.get("survival_rate") or 0.0),
            "strict_fit_rate": float(metrics.get("strict_fit_rate") or 0.0),
            "gap_reasons": list(dict.fromkeys(gap_reasons)),
        }
    return coverage


def _seed_target_coverage(
    baseline: Dict[str, Any],
    *,
    category_summary: Dict[str, Dict[str, Any]],
    lens_summary: Dict[str, Dict[str, Any]],
    min_targets_per_seed: float,
    min_strict_fit_per_seed: float,
) -> Dict[str, Any]:
    if not baseline:
        return {}
    by_category = _lane_seed_coverage(
        baseline.get("seed_category_counts") or {},
        category_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    by_lens = _lane_seed_coverage(
        baseline.get("seed_lens_counts") or {},
        lens_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    return {
        "by_category": by_category,
        "by_lens": by_lens,
        "undercovered_categories": [
            lane for lane, metrics in by_category.items()
            if metrics.get("gap_reasons")
        ],
        "undercovered_lenses": [
            lane for lane, metrics in by_lens.items()
            if metrics.get("gap_reasons")
        ],
    }


def _next_run_playbook(
    *,
    source_scan_run_id: Optional[int],
    row_count: int,
    overall: Dict[str, Any],
    seed_target_coverage: Dict[str, Any],
    weak_lanes: List[Dict[str, Any]],
    recommendations: List[Dict[str, Any]],
    sample_per_lane: int,
) -> Dict[str, Any]:
    metric_backfill_required = bool(
        row_count
        and (
            float(overall.get("axis_coverage_rate") or 0.0) < 0.80
            or float(overall.get("lens_coverage_rate") or 0.0) < 0.80
        )
    )
    boost_categories = [
        {
            "category": lane,
            **metrics,
        }
        for lane, metrics in (seed_target_coverage.get("by_category") or {}).items()
        if metrics.get("gap_reasons")
    ]
    boost_lenses = [
        {
            "lens": lane,
            **metrics,
        }
        for lane, metrics in (seed_target_coverage.get("by_lens") or {}).items()
        if metrics.get("gap_reasons")
    ]
    boost_categories.sort(key=lambda item: (item["target_per_seed"], item["strict_fit_per_seed"], -item["seed_count"]))
    boost_lenses.sort(key=lambda item: (item["target_per_seed"], item["strict_fit_per_seed"], -item["seed_count"]))
    coverage_gap_required = bool(boost_categories or boost_lenses)

    review_before_scaling = [
        lane for lane in weak_lanes
        if any(
            reason in set(lane.get("reasons") or [])
            for reason in ("low_axis_fit", "low_lens_fit", "low_strict_fit_rate", "low_worksite_efficiency")
        )
    ][:10]

    def quote_cli(value: object) -> str:
        text = str(value or "").replace('"', '\\"')
        return f'"{text}"'

    boost_args: List[str] = []
    for item in boost_categories[:5]:
        category = item.get("category")
        if category:
            boost_args.append(f"--boost-category {quote_cli(category)}")
    for item in boost_lenses[:5]:
        lens = item.get("lens")
        if lens:
            boost_args.append(f"--boost-lens {quote_cli(lens)}")

    scan_command = "python viral_hunter.py --scan --fresh --top-n-for-ai 300 --ai-parallel 5"
    if source_scan_run_id:
        scan_command += f" --source-scan-id {int(source_scan_run_id)}"
    if boost_args:
        scan_command += " " + " ".join(boost_args)
    audit_command = "python scripts/viral_handoff_audit.py"
    if source_scan_run_id:
        audit_command += f" --scan-id {source_scan_run_id}"
    audit_command += f" --sample-per-lane {max(1, int(sample_per_lane or 1))}"

    return {
        "rerun_required": bool(row_count == 0 or metric_backfill_required or coverage_gap_required),
        "metric_backfill_required": metric_backfill_required,
        "coverage_gap_required": coverage_gap_required,
        "boost_categories": boost_categories[:10],
        "boost_lenses": boost_lenses[:10],
        "review_before_scaling": review_before_scaling,
        "top_recommendation_codes": [item.get("code") for item in recommendations[:5]],
        "suggested_commands": {
            "live_scan": scan_command,
            "post_run_audit": audit_command,
        },
    }


def _recommendations(
    *,
    row_count: int,
    overall: Dict[str, Any],
    weak_lanes: List[Dict[str, Any]],
    baseline: Dict[str, Any],
    seed_target_coverage: Dict[str, Any],
    top_n: int = 12,
) -> List[Dict[str, Any]]:
    recommendations: List[Dict[str, Any]] = []

    def add(priority: int, code: str, message: str, action: str, lanes: Optional[List[str]] = None) -> None:
        recommendations.append({
            "priority": priority,
            "code": code,
            "message": message,
            "action": action,
            "lanes": lanes or [],
        })

    seed_count = int(baseline.get("seed_count") or 0)
    if seed_count and row_count == 0:
        add(
            100,
            "no_viral_targets_for_seed_scan",
            f"Pathfinder has {seed_count} seeds but Viral Hunter has no stored targets for this scan.",
            "run Viral Hunter live for this Pathfinder scan, then rerun this audit",
        )

    missing_categories = baseline.get("missing_seed_categories_in_targets") or []
    if missing_categories:
        add(
            92,
            "missing_seed_categories_in_targets",
            "Some Pathfinder treatment axes produced no Viral Hunter targets.",
            "increase or verify search execution for the missing treatment axes",
            [f"category:{category}" for category in missing_categories],
        )

    missing_lenses = baseline.get("missing_seed_lenses_in_targets") or []
    if missing_lenses:
        add(
            88,
            "missing_seed_lenses_in_targets",
            "Some Pathfinder execution lenses produced no Viral Hunter targets.",
            "check lens query variants and checkpoint freshness for the missing lenses",
            [f"lens:{lens}" for lens in missing_lenses],
        )

    for lane_type, code, priority in (
        ("by_category", "undercovered_seed_categories", 86),
        ("by_lens", "undercovered_seed_lenses", 82),
    ):
        undercovered = [
            f"{lane_type.removeprefix('by_')}:{lane}"
            for lane, metrics in (seed_target_coverage.get(lane_type) or {}).items()
            if metrics.get("gap_reasons")
        ]
        if undercovered:
            add(
                priority,
                code,
                "Some Pathfinder seed lanes are producing too few usable Viral Hunter targets.",
                "boost these lanes in the next Viral Hunter run and inspect their weak-lane samples",
                undercovered[:8],
            )

    if row_count and float(overall.get("axis_coverage_rate") or 0.0) < 0.80:
        add(
            84,
            "axis_fit_metric_coverage_low",
            "Most stored targets do not have pathfinder_axis_fit_* metrics.",
            "rerun with the current build or backfill scoring before judging fit quality",
        )
    if row_count and float(overall.get("lens_coverage_rate") or 0.0) < 0.80:
        add(
            78,
            "lens_fit_metric_coverage_low",
            "Most stored targets do not have pathfinder_lens_fit_* metrics.",
            "rerun with the current build or backfill scoring before judging lens quality",
        )
    if row_count and float(overall.get("strict_fit_rate") or 0.0) < 0.30:
        add(
            72,
            "strict_fit_rate_low",
            "Too few targets satisfy axis, lens, clinic-fit, and worksite-fit thresholds.",
            "prioritize weak lanes and inspect sample targets before increasing run volume",
        )

    grouped_reasons: Dict[str, List[str]] = defaultdict(list)
    for lane in weak_lanes:
        lane_name = f"{lane.get('type')}:{lane.get('lane')}"
        for reason in lane.get("reasons") or []:
            grouped_reasons[reason].append(lane_name)

    for reason, lanes in grouped_reasons.items():
        priority = {
            "missing_axis_fit_metrics": 70,
            "missing_lens_fit_metrics": 66,
            "low_survival_rate": 62,
            "low_strict_fit_rate": 60,
            "low_axis_fit": 58,
            "low_lens_fit": 56,
            "low_worksite_efficiency": 54,
        }.get(reason, 50)
        add(
            priority,
            reason,
            f"{len(lanes)} lane(s) flagged for {reason}.",
            _action_for_reason(reason),
            lanes[:8],
        )

    recommendations.sort(key=lambda item: int(item.get("priority") or 0), reverse=True)
    return recommendations[:top_n]


def _seed_baseline(db_path: str, source_scan_run_id: Optional[int]) -> Dict[str, Any]:
    if source_scan_run_id is None:
        return {}
    try:
        from core_services.viral_seed_builder import ViralSeedBuilder

        seeds = ViralSeedBuilder(db_path).build(scan_run_id=source_scan_run_id)
    except Exception:
        return {}
    if not seeds:
        return {}
    return {
        "seed_count": len(seeds),
        "seed_category_counts": dict(Counter(seed.category for seed in seeds)),
        "seed_grade_counts": dict(Counter(seed.grade for seed in seeds)),
        "seed_lens_counts": dict(Counter(seed.execution_lens or "service" for seed in seeds)),
    }


def summarize_viral_handoff_quality(
    db_path: Optional[str] = None,
    *,
    source_scan_run_id: Optional[int] = None,
    days: Optional[int] = None,
    limit: Optional[int] = None,
    min_axis_fit: float = 55.0,
    min_lens_fit: float = 55.0,
    min_clinic_fit: float = 55.0,
    min_worksite_efficiency: float = 55.0,
    min_lane_total: int = 3,
    min_targets_per_seed: float = 1.0,
    min_strict_fit_per_seed: float = 0.25,
    sample_per_lane: int = 3,
    include_seed_baseline: bool = True,
) -> Dict[str, Any]:
    """Return a read-only quality report for stored Viral Hunter targets."""
    path = db_path or _default_db_path()
    if source_scan_run_id is None:
        source_scan_run_id = latest_viral_source_scan_id(path)

    if not os.path.exists(path):
        return {
            "db_path": path,
            "source_scan_run_id": source_scan_run_id,
            "row_count": 0,
            "error": "db_not_found",
        }

    overall = LaneStats()
    by_category: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_grade: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_lens: Dict[str, LaneStats] = defaultdict(LaneStats)
    by_category_lens: Dict[str, LaneStats] = defaultdict(LaneStats)
    records: List[Dict[str, Any]] = []

    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = _fetch_rows(
            conn,
            source_scan_run_id=source_scan_run_id,
            days=days,
            limit=limit,
        )

    for row in rows:
        score_breakdown = _parse_json(row["score_breakdown"], {})
        category = _category(row)
        grade = _grade(row["matched_keyword_grade"])
        status = _status(row["comment_status"])
        lens = _lens(score_breakdown)
        query_variant = _variant(score_breakdown)
        priority = _number(row["priority_score"], 0.0) or 0.0
        clinic_fit = _score_from_breakdown(score_breakdown, "clinic_treatment_fit_score")
        worksite_efficiency = _score_from_breakdown(score_breakdown, "worksite_efficiency_score")
        axis_fit = _score_from_breakdown(score_breakdown, "pathfinder_axis_fit_score")
        lens_fit = _score_from_breakdown(score_breakdown, "pathfinder_lens_fit_score")
        strict_fit = _is_strict_fit(
            status=status,
            lens=lens,
            axis_fit=axis_fit,
            lens_fit=lens_fit,
            clinic_fit=clinic_fit,
            worksite_efficiency=worksite_efficiency,
            min_axis_fit=min_axis_fit,
            min_lens_fit=min_lens_fit,
            min_clinic_fit=min_clinic_fit,
            min_worksite_efficiency=min_worksite_efficiency,
        )
        add_kwargs = {
            "status": status,
            "grade": grade,
            "lens": lens,
            "query_variant": query_variant,
            "priority": priority,
            "axis_fit": axis_fit,
            "lens_fit": lens_fit,
            "clinic_fit": clinic_fit,
            "worksite_efficiency": worksite_efficiency,
            "strict_fit": strict_fit,
        }
        overall.add(**add_kwargs)
        by_category[category].add(**add_kwargs)
        by_grade[grade].add(**add_kwargs)
        by_lens[lens].add(**add_kwargs)
        by_category_lens[f"{category}::{lens}"].add(**add_kwargs)
        records.append(
            _row_sample(
                row,
                category=category,
                grade=grade,
                status=status,
                lens=lens,
                query_variant=query_variant,
                priority=priority,
                axis_fit=axis_fit,
                lens_fit=lens_fit,
                clinic_fit=clinic_fit,
                worksite_efficiency=worksite_efficiency,
                strict_fit=strict_fit,
            )
        )

    category_summary = {key: stats.to_dict() for key, stats in sorted(by_category.items())}
    grade_summary = {key: stats.to_dict() for key, stats in sorted(by_grade.items())}
    lens_summary = {key: stats.to_dict() for key, stats in sorted(by_lens.items())}
    category_lens_summary = {
        key: stats.to_dict()
        for key, stats in sorted(by_category_lens.items())
    }

    weak_lanes = []
    for lane_type, summary in (
        ("category", category_summary),
        ("grade", grade_summary),
        ("lens", lens_summary),
        ("category_lens", category_lens_summary),
    ):
        for lane, metrics in summary.items():
            reasons = _weak_lane_reasons(metrics, min_lane_total=min_lane_total)
            if reasons:
                weak_lanes.append({
                    "type": lane_type,
                    "lane": lane,
                    "total": metrics["total"],
                    "survival_rate": metrics["survival_rate"],
                    "strict_fit_rate": metrics["strict_fit_rate"],
                    "avg_axis_fit": metrics["avg_axis_fit"],
                    "avg_lens_fit": metrics["avg_lens_fit"],
                    "reasons": reasons,
                })
    weak_lanes.sort(key=lambda item: (item["strict_fit_rate"], item["survival_rate"], -item["total"]))

    baseline = _seed_baseline(path, source_scan_run_id) if include_seed_baseline else {}
    if baseline:
        discovered_categories = set(category_summary)
        discovered_lenses = set(lens_summary)
        baseline["missing_seed_categories_in_targets"] = sorted(
            set(baseline.get("seed_category_counts", {})) - discovered_categories
        )
        baseline["missing_seed_lenses_in_targets"] = sorted(
            set(baseline.get("seed_lens_counts", {})) - discovered_lenses
        )

    overall_summary = overall.to_dict()
    seed_target_coverage = _seed_target_coverage(
        baseline,
        category_summary=category_summary,
        lens_summary=lens_summary,
        min_targets_per_seed=min_targets_per_seed,
        min_strict_fit_per_seed=min_strict_fit_per_seed,
    )
    recommendations = _recommendations(
        row_count=len(rows),
        overall=overall_summary,
        weak_lanes=weak_lanes,
        baseline=baseline,
        seed_target_coverage=seed_target_coverage,
    )
    next_run_playbook = _next_run_playbook(
        source_scan_run_id=source_scan_run_id,
        row_count=len(rows),
        overall=overall_summary,
        seed_target_coverage=seed_target_coverage,
        weak_lanes=weak_lanes,
        recommendations=recommendations,
        sample_per_lane=sample_per_lane,
    )

    return {
        "db_path": path,
        "source_scan_run_id": source_scan_run_id,
        "row_count": len(rows),
        "thresholds": {
            "min_axis_fit": min_axis_fit,
            "min_lens_fit": min_lens_fit,
            "min_clinic_fit": min_clinic_fit,
            "min_worksite_efficiency": min_worksite_efficiency,
            "min_lane_total": min_lane_total,
            "min_targets_per_seed": min_targets_per_seed,
            "min_strict_fit_per_seed": min_strict_fit_per_seed,
            "sample_per_lane": sample_per_lane,
        },
        "overall": overall_summary,
        "by_category": category_summary,
        "by_grade": grade_summary,
        "by_lens": lens_summary,
        "by_category_lens": category_lens_summary,
        "seed_target_coverage": seed_target_coverage,
        "weak_lanes": weak_lanes,
        "recommendations": recommendations,
        "next_run_playbook": next_run_playbook,
        "review_samples": _review_samples(
            records,
            weak_lanes,
            sample_per_lane=max(0, int(sample_per_lane or 0)),
        ),
        "seed_baseline": baseline,
    }
