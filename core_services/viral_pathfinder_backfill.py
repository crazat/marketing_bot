"""Backfill Pathfinder post-fit metrics for stored Viral Hunter targets.

The live hunter now attaches Pathfinder lineage before filtering, but older
stored rows may not have the post-level axis/lens fit metrics that the handoff
audit relies on. This module is deliberately conservative: dry-run is the
default, and apply mode only updates score_breakdown plus empty keyword
metadata fields.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE as GYULIM_KEYWORD_PROFILE
from core_services.viral_seed_builder import ViralSeedBuilder
from viral_hunter import CommentableFilter, ViralTarget


PATHFINDER_CONTEXT_KEYS = {
    "pathfinder_viral_readiness_score",
    "pathfinder_local_service_fit_score",
    "pathfinder_content_actionability_score",
    "pathfinder_medical_ad_risk_score",
    "pathfinder_community_signal",
    "pathfinder_conversion_signal",
    "pathfinder_profile_action_signal",
    "pathfinder_preferred_search_surface",
    "pathfinder_recommended_content_type",
    "pathfinder_brand_intent_type",
    "pathfinder_review_intent_type",
    "pathfinder_execution_lens",
}

PATHFINDER_FIT_KEYS = {
    "pathfinder_axis_fit_score",
    "pathfinder_axis_fit_tier",
    "pathfinder_axis_fit_signals",
    "pathfinder_axis_adjustment",
    "pathfinder_lens_fit_score",
    "pathfinder_lens_fit_tier",
    "pathfinder_lens_fit_signals",
    "pathfinder_lens_adjustment",
}

DEFAULT_STATUSES: Tuple[str, ...] = ()


@dataclass
class BackfillCandidate:
    row_id: str
    target: ViralTarget
    score_breakdown: Dict[str, Any]
    matched_keyword: str = ""


@dataclass
class BackfillUpdate:
    target_id: str
    url: str
    title: str
    context_source: str
    category: str
    execution_lens: str
    axis_fit_score: float
    axis_fit_tier: str
    lens_fit_score: float
    lens_fit_tier: str
    changed_keys: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_id": self.target_id,
            "url": self.url,
            "title": self.title,
            "context_source": self.context_source,
            "category": self.category,
            "execution_lens": self.execution_lens,
            "axis_fit_score": self.axis_fit_score,
            "axis_fit_tier": self.axis_fit_tier,
            "lens_fit_score": self.lens_fit_score,
            "lens_fit_tier": self.lens_fit_tier,
            "changed_keys": list(self.changed_keys),
        }


def default_db_path() -> str:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(root, "db", "marketing_data.db")


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


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


def _row_value(row: sqlite3.Row, key: str, default: Any = None) -> Any:
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    return row[key] if key in keys else default


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _target_from_row(row: sqlite3.Row) -> BackfillCandidate:
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
    return BackfillCandidate(
        row_id=str(_row_value(row, "id", target.id) or target.id),
        target=target,
        score_breakdown=score_breakdown,
        matched_keyword=matched_keyword,
    )


def _needs_backfill(score_breakdown: Dict[str, Any]) -> bool:
    return not all(key in score_breakdown for key in ("pathfinder_axis_fit_score", "pathfinder_lens_fit_score"))


def _seed_contexts_for_scan(builder: ViralSeedBuilder, scan_run_id: Optional[int]) -> Tuple[Dict[str, dict], List[dict]]:
    if not scan_run_id:
        return {}, []
    seeds = builder.build(scan_run_id=scan_run_id)
    contexts = [seed.to_context() for seed in seeds]
    by_keyword = {
        str(ctx.get("keyword") or ""): ctx
        for ctx in contexts
        if ctx.get("keyword")
    }
    return by_keyword, contexts


def _existing_pathfinder_context(score_breakdown: Dict[str, Any]) -> Optional[dict]:
    if any(score_breakdown.get(key) not in (None, "") for key in PATHFINDER_CONTEXT_KEYS):
        return {
            "viral_readiness_score": score_breakdown.get("pathfinder_viral_readiness_score", 0),
            "local_service_fit_score": score_breakdown.get("pathfinder_local_service_fit_score", 0),
            "content_actionability_score": score_breakdown.get("pathfinder_content_actionability_score", 0),
            "medical_ad_risk_score": score_breakdown.get("pathfinder_medical_ad_risk_score", 0),
            "community_signal": score_breakdown.get("pathfinder_community_signal", 0),
            "conversion_signal": score_breakdown.get("pathfinder_conversion_signal", 0),
            "profile_action_signal": score_breakdown.get("pathfinder_profile_action_signal", 0),
            "preferred_search_surface": score_breakdown.get("pathfinder_preferred_search_surface", ""),
            "recommended_content_type": score_breakdown.get("pathfinder_recommended_content_type", ""),
            "brand_intent_type": score_breakdown.get("pathfinder_brand_intent_type", "generic"),
            "review_intent_type": score_breakdown.get("pathfinder_review_intent_type", "none"),
            "execution_lens": score_breakdown.get("pathfinder_execution_lens", ""),
            "keyword": score_breakdown.get("pathfinder_source_keyword", ""),
            "scan_run_id": score_breakdown.get("pathfinder_scan_run_id", 0),
        }
    return None


def _resolve_context(
    *,
    candidate: BackfillCandidate,
    builder: ViralSeedBuilder,
    source_scan_run_id: Optional[int],
    scan_contexts_by_keyword: Dict[str, dict],
    scan_contexts: Sequence[dict],
) -> Tuple[Optional[dict], str]:
    existing = _existing_pathfinder_context(candidate.score_breakdown)
    if existing and existing.get("execution_lens"):
        return existing, "existing_breakdown"

    keywords = [
        keyword
        for keyword in dict.fromkeys(candidate.target.matched_keywords or [])
        if keyword
    ]
    for keyword in keywords:
        ctx = scan_contexts_by_keyword.get(keyword)
        if ctx:
            return ctx, "scan_seed_exact"

    exact_contexts = builder.keyword_context_for(keywords)
    for keyword in keywords:
        ctx = exact_contexts.get(keyword)
        if not ctx:
            continue
        ctx_scan_id = _as_int(ctx.get("scan_run_id"))
        if not source_scan_run_id or ctx_scan_id in {0, int(source_scan_run_id)}:
            return ctx, "keyword_exact"

    if len(scan_contexts) == 1:
        return dict(scan_contexts[0]), "scan_single_seed_fallback"

    return None, "no_context"


def _context_score_breakdown(ctx: dict) -> Dict[str, Any]:
    return {
        "pathfinder_viral_readiness_score": float(ctx.get("viral_readiness_score") or 0),
        "pathfinder_local_service_fit_score": float(ctx.get("local_service_fit_score") or 0),
        "pathfinder_content_actionability_score": float(ctx.get("content_actionability_score") or 0),
        "pathfinder_medical_ad_risk_score": float(ctx.get("medical_ad_risk_score") or 0),
        "pathfinder_community_signal": float(ctx.get("community_signal") or 0),
        "pathfinder_conversion_signal": float(ctx.get("conversion_signal") or 0),
        "pathfinder_profile_action_signal": float(ctx.get("profile_action_signal") or 0),
        "pathfinder_preferred_search_surface": ctx.get("preferred_search_surface") or "",
        "pathfinder_recommended_content_type": ctx.get("recommended_content_type") or "",
        "pathfinder_brand_intent_type": ctx.get("brand_intent_type") or "generic",
        "pathfinder_review_intent_type": ctx.get("review_intent_type") or "none",
        "pathfinder_execution_lens": ctx.get("execution_lens") or "",
        "pathfinder_source_keyword": ctx.get("keyword") or "",
        "pathfinder_scan_run_id": _as_int(ctx.get("scan_run_id")),
    }


def _apply_context(target: ViralTarget, ctx: dict, context_source: str) -> None:
    target.source_scan_run_id = _as_int(ctx.get("scan_run_id")) or target.source_scan_run_id
    if ctx.get("grade"):
        target.matched_keyword_grade = str(ctx.get("grade") or "")
    if ctx.get("kei") is not None:
        target.matched_keyword_kei = _as_float(ctx.get("kei"))
    if ctx.get("priority_v3") is not None:
        target.matched_keyword_priority = _as_float(ctx.get("priority_v3"))
    if ctx.get("category"):
        target.matched_keyword_category = GYULIM_KEYWORD_PROFILE.normalize_category(str(ctx.get("category") or ""))
    if (not target.category or target.category == "기타") and target.matched_keyword_category:
        target.category = target.matched_keyword_category

    merged = {
        **(target.score_breakdown or {}),
        **_context_score_breakdown(ctx),
        "pathfinder_backfill_context_source": context_source,
    }
    if context_source == "scan_single_seed_fallback":
        merged["pathfinder_backfill_single_seed_context"] = True
    target.score_breakdown = merged


def _post_fit_breakdown(target: ViralTarget) -> Dict[str, Any]:
    title = (target.title or "").lower()
    body = CommentableFilter._strip_internal_labels(target.content_preview or "").lower()
    text = f"{title} {body}"
    domain = CommentableFilter._keyword_domain(target.matched_keywords)
    axis_score, axis_tier, axis_signals = CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain=domain,
        text=text,
    )
    axis_adjustment = 0.0
    if axis_tier != "neutral":
        axis_adjustment = max(-18.0, min(12.0, (axis_score - 55.0) * 0.28))

    lens_score, lens_tier, lens_signals = CommentableFilter._pathfinder_lens_post_fit(
        target,
        platform=target.platform,
        text=text,
    )
    lens_adjustment = 0.0
    if lens_tier != "neutral":
        lens_adjustment = max(-14.0, min(12.0, (lens_score - 55.0) * 0.30))

    return {
        "pathfinder_axis_fit_score": float(axis_score),
        "pathfinder_axis_fit_tier": axis_tier,
        "pathfinder_axis_fit_signals": ",".join(axis_signals),
        "pathfinder_axis_adjustment": float(axis_adjustment),
        "pathfinder_lens_fit_score": float(lens_score),
        "pathfinder_lens_fit_tier": lens_tier,
        "pathfinder_lens_fit_signals": ",".join(lens_signals),
        "pathfinder_lens_adjustment": float(lens_adjustment),
    }


def _changed_keys(old: Dict[str, Any], new: Dict[str, Any]) -> List[str]:
    changed = []
    for key, value in new.items():
        if old.get(key) != value:
            changed.append(key)
    return changed


def _load_candidates(
    conn: sqlite3.Connection,
    *,
    source_scan_run_id: Optional[int],
    statuses: Optional[Iterable[str]],
    only_missing: bool,
    limit: Optional[int],
) -> List[BackfillCandidate]:
    if not _table_exists(conn, "viral_targets"):
        return []
    columns = _table_columns(conn, "viral_targets")
    where = ["1=1"]
    params: List[Any] = []
    if source_scan_run_id is not None and "source_scan_run_id" in columns:
        where.append("COALESCE(source_scan_run_id, 0) = ?")
        params.append(source_scan_run_id)
    status_list = [status for status in statuses if status] if statuses is not None else []
    if status_list and "comment_status" in columns:
        placeholders = ",".join("?" for _ in status_list)
        where.append(f"COALESCE(comment_status, 'pending') IN ({placeholders})")
        params.extend(status_list)
    if only_missing and "score_breakdown" in columns:
        where.append(
            """(
                score_breakdown IS NULL
                OR score_breakdown = ''
                OR score_breakdown = '{}'
                OR score_breakdown NOT LIKE '%pathfinder_axis_fit_score%'
                OR score_breakdown NOT LIKE '%pathfinder_lens_fit_score%'
            )"""
        )
    order_clause = "ORDER BY discovered_at DESC" if "discovered_at" in columns else "ORDER BY id"
    limit_clause = "LIMIT ?" if limit else ""
    if limit:
        params.append(limit)
    rows = conn.execute(
        f"""
        SELECT *
        FROM viral_targets
        WHERE {" AND ".join(where)}
        {order_clause}
        {limit_clause}
        """,
        params,
    ).fetchall()
    return [_target_from_row(row) for row in rows]


def _update_candidate(
    conn: sqlite3.Connection,
    candidate: BackfillCandidate,
    new_breakdown: Dict[str, Any],
    *,
    columns: set[str],
) -> None:
    assignments = ["score_breakdown = ?"]
    params: List[Any] = [json.dumps(new_breakdown, ensure_ascii=False)]

    def set_if_empty(column: str, value: Any) -> None:
        if column not in columns or value in (None, ""):
            return
        assignments.append(f"{column} = COALESCE(NULLIF({column}, ''), ?)")
        params.append(value)

    target = candidate.target
    set_if_empty("matched_keyword_grade", target.matched_keyword_grade)
    if "matched_keyword_kei" in columns and target.matched_keyword_kei:
        assignments.append("matched_keyword_kei = COALESCE(NULLIF(matched_keyword_kei, 0), ?)")
        params.append(float(target.matched_keyword_kei))
    if "matched_keyword_priority" in columns and target.matched_keyword_priority:
        assignments.append("matched_keyword_priority = COALESCE(NULLIF(matched_keyword_priority, 0), ?)")
        params.append(float(target.matched_keyword_priority))
    set_if_empty("matched_keyword_category", target.matched_keyword_category)
    set_if_empty("category", target.category)
    if "source_scan_run_id" in columns and target.source_scan_run_id:
        assignments.append("source_scan_run_id = COALESCE(NULLIF(source_scan_run_id, 0), ?)")
        params.append(int(target.source_scan_run_id))
    if "updated_at" in columns:
        assignments.append("updated_at = CURRENT_TIMESTAMP")

    params.append(candidate.row_id)
    conn.execute(
        f"UPDATE viral_targets SET {', '.join(assignments)} WHERE id = ?",
        params,
    )


def backfill_pathfinder_metrics(
    *,
    db_path: Optional[str] = None,
    source_scan_run_id: Optional[int] = None,
    limit: Optional[int] = None,
    apply: bool = False,
    statuses: Optional[Iterable[str]] = None,
    only_missing: bool = True,
    sample_size: int = 10,
) -> Dict[str, Any]:
    """Return a dry-run/apply report for stored Pathfinder post-fit metrics."""
    db_path = db_path or default_db_path()
    builder = ViralSeedBuilder(db_path=db_path)
    scan_contexts_by_keyword, scan_contexts = _seed_contexts_for_scan(builder, source_scan_run_id)

    report: Dict[str, Any] = {
        "db_path": db_path,
        "source_scan_run_id": source_scan_run_id,
        "apply": bool(apply),
        "only_missing": bool(only_missing),
        "candidate_count": 0,
        "would_update": 0,
        "updated": 0,
        "skipped_no_context": 0,
        "skipped_no_change": 0,
        "context_source_counts": {},
        "axis_tier_counts": {},
        "lens_tier_counts": {},
        "samples": [],
    }

    with closing(sqlite3.connect(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        candidates = _load_candidates(
            conn,
            source_scan_run_id=source_scan_run_id,
            statuses=statuses,
            only_missing=only_missing,
            limit=limit,
        )
        columns = _table_columns(conn, "viral_targets") if _table_exists(conn, "viral_targets") else set()
        report["candidate_count"] = len(candidates)

        for candidate in candidates:
            if only_missing and not _needs_backfill(candidate.score_breakdown):
                continue
            ctx, context_source = _resolve_context(
                candidate=candidate,
                builder=builder,
                source_scan_run_id=source_scan_run_id,
                scan_contexts_by_keyword=scan_contexts_by_keyword,
                scan_contexts=scan_contexts,
            )
            if not ctx:
                report["skipped_no_context"] += 1
                continue

            old_breakdown = dict(candidate.score_breakdown)
            _apply_context(candidate.target, ctx, context_source)
            fit_breakdown = _post_fit_breakdown(candidate.target)
            new_breakdown = {**candidate.target.score_breakdown, **fit_breakdown}
            changed = _changed_keys(old_breakdown, new_breakdown)
            if not changed:
                report["skipped_no_change"] += 1
                continue

            update = BackfillUpdate(
                target_id=candidate.row_id,
                url=candidate.target.url,
                title=candidate.target.title,
                context_source=context_source,
                category=candidate.target.matched_keyword_category or candidate.target.category,
                execution_lens=str(new_breakdown.get("pathfinder_execution_lens") or ""),
                axis_fit_score=float(new_breakdown.get("pathfinder_axis_fit_score") or 0.0),
                axis_fit_tier=str(new_breakdown.get("pathfinder_axis_fit_tier") or ""),
                lens_fit_score=float(new_breakdown.get("pathfinder_lens_fit_score") or 0.0),
                lens_fit_tier=str(new_breakdown.get("pathfinder_lens_fit_tier") or ""),
                changed_keys=changed,
            )
            report["would_update"] += 1
            report["context_source_counts"][context_source] = (
                report["context_source_counts"].get(context_source, 0) + 1
            )
            report["axis_tier_counts"][update.axis_fit_tier] = (
                report["axis_tier_counts"].get(update.axis_fit_tier, 0) + 1
            )
            report["lens_tier_counts"][update.lens_fit_tier] = (
                report["lens_tier_counts"].get(update.lens_fit_tier, 0) + 1
            )
            if len(report["samples"]) < sample_size:
                report["samples"].append(update.to_dict())
            if apply:
                _update_candidate(conn, candidate, new_breakdown, columns=columns)
                report["updated"] += 1

        if apply:
            conn.commit()

    return report
