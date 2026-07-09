"""Backfill Viral Hunter quality metrics for stored targets.

Older rows can miss clinic/worksite metrics when they were rejected before the
late filter stages that attach those scores. The handoff audit treats that as
metric coverage loss, so this backfill computes the same local quality metrics
from stored title/content without changing target status.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple

from viral_hunter import CommentableFilter, ViralTarget


COVERAGE_KEYS = ("clinic_treatment_fit_score", "worksite_efficiency_score")
QUALITY_METRIC_KEYS = (
    "viral_need_score",
    "viral_need_tier",
    "viral_need_signals",
    "reply_opportunity_score",
    "reply_opportunity_tier",
    "reply_opportunity_signals",
    "timing_window_score",
    "timing_window_tier",
    "timing_window_signals",
    "journey_fit_score",
    "journey_stage",
    "journey_signals",
    "qualification_fit_score",
    "qualification_tier",
    "qualification_signals",
    "reply_risk_penalty",
    "reply_risk_flags",
    "metric_backfill_human_only",
    "clinic_treatment_fit_score",
    "clinic_treatment_fit_tier",
    "clinic_treatment_fit_signals",
    "worksite_efficiency_score",
    "worksite_efficiency_tier",
    "worksite_efficiency_signals",
)


@dataclass
class MetricBackfillCandidate:
    row_id: str
    target: ViralTarget
    score_breakdown: Dict[str, Any]


@dataclass
class MetricBackfillUpdate:
    target_id: str
    status: str
    title: str
    clinic_score: float
    clinic_tier: str
    worksite_score: float
    worksite_tier: str
    changed_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "status": self.status,
            "title": self.title,
            "clinic_score": self.clinic_score,
            "clinic_tier": self.clinic_tier,
            "worksite_score": self.worksite_score,
            "worksite_tier": self.worksite_tier,
            "changed_keys": list(self.changed_keys),
        }


def default_db_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "db", "marketing_data.db")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    return row[key] if key in keys else default


def _parse_json_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _parse_json_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    if not value:
        return []
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return [value] if value.strip() else []
        if isinstance(parsed, list):
            return [str(item) for item in parsed if item]
        if isinstance(parsed, str) and parsed.strip():
            return [parsed]
    return []


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _csv_terms(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _existing_float(breakdown: Dict[str, Any], key: str, computed: float) -> float:
    if key in breakdown and breakdown.get(key) not in (None, ""):
        return _as_float(breakdown.get(key))
    return float(computed)


def _existing_text(breakdown: Dict[str, Any], key: str, computed: str) -> str:
    if key in breakdown and breakdown.get(key) not in (None, ""):
        return str(breakdown.get(key) or "")
    return str(computed or "")


def _existing_terms(breakdown: Dict[str, Any], key: str, computed: Iterable[str]) -> List[str]:
    if key in breakdown and breakdown.get(key) not in (None, ""):
        return _csv_terms(breakdown.get(key))
    return [str(item) for item in computed if item]


def _target_from_row(row: sqlite3.Row) -> MetricBackfillCandidate:
    score_breakdown = _parse_json_dict(_row_value(row, "score_breakdown", "{}"))
    matched_keywords = _parse_json_list(_row_value(row, "matched_keywords", "[]"))
    matched_keyword = str(_row_value(row, "matched_keyword", "") or "").strip()
    if matched_keyword:
        matched_keywords = [matched_keyword, *matched_keywords]
    source_keyword = str(score_breakdown.get("pathfinder_source_keyword") or "").strip()
    if source_keyword:
        matched_keywords = [source_keyword, *matched_keywords]
    matched_keywords = [keyword for keyword in dict.fromkeys(matched_keywords) if keyword]

    target = ViralTarget(
        platform=str(_row_value(row, "platform", "") or ""),
        url=str(_row_value(row, "url", "") or ""),
        title=str(_row_value(row, "title", "") or ""),
        content_preview=str(_row_value(row, "content_preview", "") or ""),
        matched_keywords=matched_keywords,
        category=str(_row_value(row, "category", "") or ""),
        is_commentable=bool(_row_value(row, "is_commentable", 1)),
        generated_comment=str(_row_value(row, "generated_comment", "") or ""),
        priority_score=_as_float(_row_value(row, "priority_score", 0.0)),
        author=str(_row_value(row, "author", "") or ""),
        date_str=str(_row_value(row, "posted_at", "") or ""),
        comment_status=str(_row_value(row, "comment_status", "pending") or "pending"),
        discovered_at=str(_row_value(row, "discovered_at", "") or ""),
        first_seen_at=str(_row_value(row, "first_seen_at", "") or ""),
        last_scanned_at=str(_row_value(row, "last_scanned_at", "") or ""),
        scan_count=_as_int(_row_value(row, "scan_count", 0)),
        source_scan_run_id=_as_int(_row_value(row, "source_scan_run_id", 0)),
        matched_keyword_grade=str(_row_value(row, "matched_keyword_grade", "") or ""),
        matched_keyword_kei=_as_float(_row_value(row, "matched_keyword_kei", 0.0)),
        matched_keyword_priority=_as_float(_row_value(row, "matched_keyword_priority", 0.0)),
        matched_keyword_category=str(_row_value(row, "matched_keyword_category", "") or ""),
        like_count=_as_int(_row_value(row, "like_count", 0)),
        comment_count=_as_int(_row_value(row, "comment_count", 0)),
        view_count=_as_int(_row_value(row, "view_count", 0)),
        exposure_score=_as_float(_row_value(row, "exposure_score", 0.0)),
        workability_score=_as_float(_row_value(row, "workability_score", 0.0)),
        conversion_fit_score=_as_float(_row_value(row, "conversion_fit_score", 0.0)),
        score_breakdown=score_breakdown,
        search_sort=str(_row_value(row, "search_sort", "") or ""),
        search_rank=_as_int(_row_value(row, "search_rank", 0)),
        search_start=_as_int(_row_value(row, "search_start", 0)),
        search_total=_as_int(_row_value(row, "search_total", 0)),
        sort_appearances=_parse_json_list(_row_value(row, "sort_appearances", "[]")),
        ai_reviewed=bool(_row_value(row, "ai_reviewed", 0)),
        ai_infiltration_score=_as_float(_row_value(row, "ai_infiltration_score", 0.0)),
        ai_post_type=str(_row_value(row, "ai_post_type", "") or ""),
        ai_competitor=bool(_row_value(row, "ai_competitor", 0)),
        ai_competitor_name=str(_row_value(row, "ai_competitor_name", "") or ""),
        canonical_url=str(_row_value(row, "canonical_url", "") or ""),
    )
    return MetricBackfillCandidate(
        row_id=str(_row_value(row, "id", target.id) or target.id),
        target=target,
        score_breakdown=score_breakdown,
    )


def _needs_backfill(score_breakdown: Dict[str, Any]) -> bool:
    return not all(key in score_breakdown for key in COVERAGE_KEYS)


def _quality_metric_breakdown(candidate: MetricBackfillCandidate) -> Dict[str, Any]:
    target = candidate.target
    breakdown = dict(candidate.score_breakdown or {})
    target.score_breakdown = breakdown
    text = f"{target.title or ''} {target.content_preview or ''}".lower()
    domain = CommentableFilter._target_domain(target)
    is_inquiry = any(pattern in text for pattern in CommentableFilter.REAL_INQUIRY_PATTERNS)
    is_health = any(keyword in text for keyword in CommentableFilter.HEALTH_KEYWORDS)

    viral_score, viral_tier, viral_signals = CommentableFilter._assess_viral_need(
        target, domain, is_inquiry, is_health
    )
    viral_score = int(_existing_float(breakdown, "viral_need_score", viral_score))
    viral_tier = _existing_text(breakdown, "viral_need_tier", viral_tier)
    viral_signals = _existing_terms(breakdown, "viral_need_signals", viral_signals)

    reply_score, reply_tier, reply_signals = CommentableFilter._assess_reply_opportunity(
        target, domain, is_inquiry, is_health, viral_score, viral_signals
    )
    reply_score = int(_existing_float(breakdown, "reply_opportunity_score", reply_score))
    reply_tier = _existing_text(breakdown, "reply_opportunity_tier", reply_tier)
    reply_signals = _existing_terms(breakdown, "reply_opportunity_signals", reply_signals)

    timing_score, timing_tier, timing_signals = CommentableFilter._assess_timing_window(
        target, viral_signals, reply_signals
    )
    timing_score = int(_existing_float(breakdown, "timing_window_score", timing_score))
    timing_tier = _existing_text(breakdown, "timing_window_tier", timing_tier)
    timing_signals = _existing_terms(breakdown, "timing_window_signals", timing_signals)

    journey_score, journey_stage, journey_signals = CommentableFilter._assess_journey_fit(
        target, domain, is_inquiry, viral_signals, reply_signals, timing_score
    )
    journey_score = int(_existing_float(breakdown, "journey_fit_score", journey_score))
    journey_stage = _existing_text(breakdown, "journey_stage", journey_stage)
    journey_signals = _existing_terms(breakdown, "journey_signals", journey_signals)

    qualification_score, qualification_tier, qualification_signals = (
        CommentableFilter._assess_qualification_fit(
            target,
            domain,
            is_health,
            viral_signals,
            reply_signals,
            timing_score,
            journey_score,
            journey_stage,
        )
    )
    qualification_score = int(_existing_float(breakdown, "qualification_fit_score", qualification_score))
    qualification_tier = _existing_text(breakdown, "qualification_tier", qualification_tier)
    qualification_signals = _existing_terms(breakdown, "qualification_signals", qualification_signals)

    risk_penalty, risk_flags, human_only = CommentableFilter._assess_reply_risk(text, target)
    risk_penalty = _existing_float(breakdown, "reply_risk_penalty", risk_penalty)
    risk_flags = _existing_terms(breakdown, "reply_risk_flags", risk_flags)

    clinic_score, clinic_tier, clinic_signals = CommentableFilter._assess_clinic_treatment_fit(
        target, domain, text, is_health
    )
    clinic_score = int(_existing_float(breakdown, "clinic_treatment_fit_score", clinic_score))
    clinic_tier = _existing_text(breakdown, "clinic_treatment_fit_tier", clinic_tier)
    clinic_signals = _existing_terms(breakdown, "clinic_treatment_fit_signals", clinic_signals)

    worksite_score, worksite_tier, worksite_signals = CommentableFilter._assess_worksite_efficiency(
        target,
        clinic_score,
        viral_score,
        viral_signals,
        reply_score,
        reply_signals,
        timing_score,
        timing_signals,
        journey_score,
        journey_stage,
        qualification_score,
        risk_flags,
    )

    return {
        "viral_need_score": float(viral_score),
        "viral_need_tier": viral_tier,
        "viral_need_signals": ",".join(viral_signals),
        "reply_opportunity_score": float(reply_score),
        "reply_opportunity_tier": reply_tier,
        "reply_opportunity_signals": ",".join(reply_signals),
        "timing_window_score": float(timing_score),
        "timing_window_tier": timing_tier,
        "timing_window_signals": ",".join(timing_signals),
        "journey_fit_score": float(journey_score),
        "journey_stage": journey_stage,
        "journey_signals": ",".join(journey_signals),
        "qualification_fit_score": float(qualification_score),
        "qualification_tier": qualification_tier,
        "qualification_signals": ",".join(qualification_signals),
        "reply_risk_penalty": float(risk_penalty),
        "reply_risk_flags": ",".join(risk_flags),
        "metric_backfill_human_only": 1.0 if human_only else 0.0,
        "clinic_treatment_fit_score": float(clinic_score),
        "clinic_treatment_fit_tier": clinic_tier,
        "clinic_treatment_fit_signals": ",".join(clinic_signals),
        "worksite_efficiency_score": float(worksite_score),
        "worksite_efficiency_tier": worksite_tier,
        "worksite_efficiency_signals": ",".join(worksite_signals),
        "quality_metric_backfilled": True,
    }


def _changed_keys(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    return [key for key, value in new.items() if old.get(key) != value]


def _merge_metrics(
    old: Dict[str, Any],
    computed: Dict[str, Any],
    *,
    only_missing: bool,
) -> Dict[str, Any]:
    merged = dict(old)
    for key, value in computed.items():
        if only_missing and key in QUALITY_METRIC_KEYS and key in merged and merged.get(key) not in (None, ""):
            continue
        merged[key] = value
    return merged


def _coverage(conn: sqlite3.Connection, where_sql: str, params: List[Any]) -> Dict[str, Any]:
    row = conn.execute(
        f"""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE WHEN json_valid(COALESCE(score_breakdown, '{{}}'))
                       AND json_type(score_breakdown, '$.clinic_treatment_fit_score') IS NOT NULL
                     THEN 1 ELSE 0 END
            ) AS clinic_observed,
            SUM(
                CASE WHEN json_valid(COALESCE(score_breakdown, '{{}}'))
                       AND json_type(score_breakdown, '$.worksite_efficiency_score') IS NOT NULL
                     THEN 1 ELSE 0 END
            ) AS worksite_observed
        FROM viral_targets
        WHERE {where_sql}
        """,
        params,
    ).fetchone()
    total = int(row["total"] or 0)
    clinic = int(row["clinic_observed"] or 0)
    worksite = int(row["worksite_observed"] or 0)
    return {
        "total": total,
        "clinic_observed": clinic,
        "worksite_observed": worksite,
        "clinic_coverage_rate": round((clinic / total) if total else 0.0, 4),
        "worksite_coverage_rate": round((worksite / total) if total else 0.0, 4),
    }


def _load_candidates(
    conn: sqlite3.Connection,
    *,
    source_scan_run_id: Optional[int],
    statuses: Optional[Iterable[str]],
    only_missing: bool,
    limit: Optional[int],
) -> Tuple[List[MetricBackfillCandidate], str, List[Any]]:
    if not _table_exists(conn, "viral_targets"):
        return [], "1=0", []
    columns = _table_columns(conn, "viral_targets")
    scope_where = ["1=1"]
    params: List[Any] = []
    if source_scan_run_id is not None and "source_scan_run_id" in columns:
        scope_where.append("COALESCE(source_scan_run_id, 0) = ?")
        params.append(source_scan_run_id)
    status_list = [status for status in (statuses or ()) if status]
    if status_list and "comment_status" in columns:
        placeholders = ",".join("?" for _ in status_list)
        scope_where.append(f"COALESCE(comment_status, 'pending') IN ({placeholders})")
        params.extend(status_list)
    candidate_where = list(scope_where)
    if only_missing and "score_breakdown" in columns:
        candidate_where.append(
            """(
                score_breakdown IS NULL
                OR score_breakdown = ''
                OR score_breakdown = '{}'
                OR score_breakdown NOT LIKE '%clinic_treatment_fit_score%'
                OR score_breakdown NOT LIKE '%worksite_efficiency_score%'
            )"""
        )
    order_clause = "ORDER BY discovered_at DESC" if "discovered_at" in columns else "ORDER BY id"
    limit_clause = "LIMIT ?" if limit else ""
    query_params = list(params)
    if limit:
        query_params.append(limit)
    scope_where_sql = " AND ".join(scope_where)
    candidate_where_sql = " AND ".join(candidate_where)
    rows = conn.execute(
        f"""
        SELECT *
        FROM viral_targets
        WHERE {candidate_where_sql}
        {order_clause}
        {limit_clause}
        """,
        query_params,
    ).fetchall()
    return [_target_from_row(row) for row in rows], scope_where_sql, params


def _update_candidate(
    conn: sqlite3.Connection,
    candidate: MetricBackfillCandidate,
    new_breakdown: Dict[str, Any],
    *,
    columns: set[str],
) -> None:
    assignments = ["score_breakdown = ?"]
    params: List[Any] = [json.dumps(new_breakdown, ensure_ascii=False, sort_keys=True)]
    if "updated_at" in columns:
        assignments.append("updated_at = CURRENT_TIMESTAMP")
    params.append(candidate.row_id)
    conn.execute(
        f"UPDATE viral_targets SET {', '.join(assignments)} WHERE id = ?",
        params,
    )


def backfill_quality_metrics(
    *,
    db_path: Optional[str] = None,
    source_scan_run_id: Optional[int] = None,
    limit: Optional[int] = None,
    apply: bool = False,
    statuses: Optional[Iterable[str]] = None,
    only_missing: bool = True,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """Return a dry-run/apply report for stored Viral Hunter quality metrics."""
    db_path = db_path or default_db_path()
    report: Dict[str, Any] = {
        "db_path": db_path,
        "source_scan_run_id": source_scan_run_id,
        "apply": bool(apply),
        "only_missing": bool(only_missing),
        "candidate_count": 0,
        "would_update": 0,
        "updated": 0,
        "skipped_no_change": 0,
        "status_counts": {},
        "clinic_tier_counts": {},
        "worksite_tier_counts": {},
        "coverage_before": {},
        "coverage_after": {},
        "samples": [],
    }

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        candidates, where_sql, params = _load_candidates(
            conn,
            source_scan_run_id=source_scan_run_id,
            statuses=statuses,
            only_missing=only_missing,
            limit=limit,
        )
        columns = _table_columns(conn, "viral_targets") if _table_exists(conn, "viral_targets") else set()
        report["candidate_count"] = len(candidates)
        report["coverage_before"] = _coverage(conn, where_sql, params)

        for candidate in candidates:
            if only_missing and not _needs_backfill(candidate.score_breakdown):
                continue
            old_breakdown = dict(candidate.score_breakdown)
            computed = _quality_metric_breakdown(candidate)
            new_breakdown = _merge_metrics(old_breakdown, computed, only_missing=only_missing)
            changed = _changed_keys(old_breakdown, new_breakdown)
            if not changed:
                report["skipped_no_change"] += 1
                continue

            update = MetricBackfillUpdate(
                target_id=candidate.row_id,
                status=candidate.target.comment_status,
                title=candidate.target.title,
                clinic_score=float(new_breakdown.get("clinic_treatment_fit_score") or 0.0),
                clinic_tier=str(new_breakdown.get("clinic_treatment_fit_tier") or ""),
                worksite_score=float(new_breakdown.get("worksite_efficiency_score") or 0.0),
                worksite_tier=str(new_breakdown.get("worksite_efficiency_tier") or ""),
                changed_keys=changed,
            )
            report["would_update"] += 1
            report["status_counts"][update.status] = report["status_counts"].get(update.status, 0) + 1
            report["clinic_tier_counts"][update.clinic_tier] = (
                report["clinic_tier_counts"].get(update.clinic_tier, 0) + 1
            )
            report["worksite_tier_counts"][update.worksite_tier] = (
                report["worksite_tier_counts"].get(update.worksite_tier, 0) + 1
            )
            if len(report["samples"]) < sample_size:
                report["samples"].append(update.to_dict())
            if apply:
                _update_candidate(conn, candidate, new_breakdown, columns=columns)
                report["updated"] += 1

        if apply:
            conn.commit()
        report["coverage_after"] = _coverage(conn, where_sql, params)

    return report
