"""CLI for auditing Pathfinder -> Viral Hunter handoff quality.

Usage:
  python scripts/viral_handoff_audit.py
  python scripts/viral_handoff_audit.py --scan-id 66 --out reports/viral_handoff_audit_66.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="backslashreplace")

from core_services.viral_handoff_audit import summarize_viral_handoff_quality


def _default_db_path() -> str:
    return str(ROOT / "db" / "marketing_data.db")


def _pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


def _ascii_preview(value: object, limit: int = 42) -> str:
    text = str(value or "-")
    text = " ".join(text.split())
    return text[:limit]


def _format_counts(value: object, limit: int = 5) -> str:
    if not isinstance(value, dict) or not value:
        return "-"
    parts = [
        f"{key}:{value[key]}"
        for key in sorted(value, key=lambda item: (-int(value.get(item) or 0), str(item)))[:limit]
    ]
    return ",".join(parts) or "-"


def _print_summary(report: dict, *, top_weak: int) -> None:
    overall = report.get("overall") or {}
    print("Pathfinder -> Viral Hunter handoff audit")
    print(f"  db: {report.get('db_path')}")
    print(f"  source_scan_run_id: {report.get('source_scan_run_id')}")
    print(f"  rows: {report.get('row_count', 0)}")
    print(
        "  overall: "
        f"survival={_pct(overall.get('survival_rate'))}, "
        f"actionable={_pct(overall.get('actionable_rate'))}, "
        f"strict_fit={_pct(overall.get('strict_fit_rate'))}, "
        f"actionable_strict={_pct(overall.get('actionable_strict_rate'))}, "
        f"loss={_pct(overall.get('loss_rate'))}, "
        f"avg_axis={overall.get('avg_axis_fit', 0)}, "
        f"avg_lens={overall.get('avg_lens_fit', 0)}, "
        f"axis_coverage={_pct(overall.get('axis_coverage_rate'))}, "
        f"lens_coverage={_pct(overall.get('lens_coverage_rate'))}, "
        f"content_mismatch={_pct(overall.get('content_category_mismatch_rate'))}, "
        f"lens_mismatch={_pct(overall.get('lens_surface_mismatch_rate'))}"
    )

    quality_bar = report.get("quality_bar") or {}
    if quality_bar:
        failed = quality_bar.get("failed_required_gates") or []
        failed_advisory = quality_bar.get("failed_advisory_gates") or []
        failed_text = ", ".join(list(failed) + list(failed_advisory)) or "-"
        print(
            "  quality_bar: "
            f"tier={quality_bar.get('tier')}, "
            f"score={quality_bar.get('score')}, "
            f"failed={failed_text}"
        )

    print("\nBy category")
    for category, metrics in (report.get("by_category") or {}).items():
        print(
            f"  - {category}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}, "
            f"actionable_strict={_pct(metrics.get('actionable_strict_rate'))}, "
            f"axis={metrics.get('avg_axis_fit', 0)}, "
            f"lens={metrics.get('avg_lens_fit', 0)}, "
            f"axis_cov={_pct(metrics.get('axis_coverage_rate'))}, "
            f"lens_cov={_pct(metrics.get('lens_coverage_rate'))}, "
            f"content_mismatch={_pct(metrics.get('content_category_mismatch_rate'))}, "
            f"lens_mismatch={_pct(metrics.get('lens_surface_mismatch_rate'))}, "
            f"grades={metrics.get('grade_counts', {})}"
        )

    print("\nBy lens")
    for lens, metrics in (report.get("by_lens") or {}).items():
        print(
            f"  - {lens}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}, "
            f"actionable_strict={_pct(metrics.get('actionable_strict_rate'))}, "
            f"surface_checked={metrics.get('lens_surface_checked', 0)}, "
            f"lens_mismatch={_pct(metrics.get('lens_surface_mismatch_rate'))}"
        )

    print("\nBy platform")
    for platform, metrics in (report.get("by_platform") or {}).items():
        print(
            f"  - {platform}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}, "
            f"loss={_pct(metrics.get('loss_rate'))}, "
            f"dominant_loss={metrics.get('dominant_loss_reason') or '-'}"
        )

    print("\nBy grade")
    for grade, metrics in (report.get("by_grade") or {}).items():
        print(
            f"  - {grade}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}"
        )

    variant_families = report.get("by_variant_family") or {}
    if variant_families:
        print("\nBy variant family")
        for family, metrics in variant_families.items():
            print(
                f"  - {family}: total={metrics.get('total', 0)}, "
                f"survival={_pct(metrics.get('survival_rate'))}, "
                f"strict={_pct(metrics.get('strict_fit_rate'))}, "
                f"grades={metrics.get('grade_counts', {})}"
            )

    variant_feedback = report.get("variant_quality_feedback") or {}
    if variant_feedback:
        weak_variants = (
            list(variant_feedback.get("retire_category_lens_variants") or [])
            + list(variant_feedback.get("repair_category_lens_variants") or [])
            + list(variant_feedback.get("retire_variants") or [])
            + list(variant_feedback.get("repair_variants") or [])
        )
        scale_variants = (
            list(variant_feedback.get("scale_category_lens_variants") or [])
            + list(variant_feedback.get("scale_variants") or [])
        )
        if weak_variants:
            print(f"\nVariant quality actions (top {min(top_weak, len(weak_variants))})")
            for item in weak_variants[:top_weak]:
                print(
                    f"  - {item.get('action')} {item.get('variant')} "
                    f"lane={item.get('category_lens') or '-'} "
                    f"family={item.get('variant_family')} "
                    f"total={item.get('total', 0)} "
                    f"survival={_pct(item.get('survival_rate'))} "
                    f"strict={_pct(item.get('strict_fit_rate'))} "
                    f"loss={item.get('dominant_loss_reason') or '-'}"
                )
        if scale_variants:
            print(f"\nVariant scale candidates (top {min(top_weak, len(scale_variants))})")
            for item in scale_variants[:top_weak]:
                print(
                    f"  - {item.get('variant')} "
                    f"lane={item.get('category_lens') or '-'} "
                    f"family={item.get('variant_family')} "
                    f"strict={item.get('strict_fit', 0)}/{item.get('total', 0)} "
                    f"actionable_strict={item.get('actionable_strict', 0)}"
                )

    patient_journey = report.get("patient_journey_coverage") or {}
    journey_overall = patient_journey.get("overall") or {}
    if journey_overall:
        print("\nPatient journey coverage")
        print(
            "  overall: "
            f"strict_pairs={journey_overall.get('strict_pairs', 0)}/"
            f"{journey_overall.get('target_pairs', 0)}, "
            f"actionable_strict_pairs={journey_overall.get('actionable_strict_pairs', 0)}/"
            f"{journey_overall.get('target_pairs', 0)}, "
            f"strict_coverage={_pct(journey_overall.get('strict_coverage_rate'))}, "
            f"actionable_strict_coverage={_pct(journey_overall.get('actionable_strict_coverage_rate'))}, "
            f"survived_coverage={_pct(journey_overall.get('survived_coverage_rate'))}, "
            f"discovered_coverage={_pct(journey_overall.get('discovered_coverage_rate'))}"
        )
        journey_gaps = patient_journey.get("priority_focus_gaps") or patient_journey.get("gaps") or []
        if journey_gaps:
            print(f"  gaps (top {min(top_weak, len(journey_gaps))}):")
            for item in journey_gaps[:top_weak]:
                print(
                    f"    - {item.get('category')}::{item.get('lens')} "
                    f"total={item.get('total', 0)} "
                    f"survival={_pct(item.get('survival_rate'))} "
                    f"strict={_pct(item.get('strict_fit_rate'))} "
                    f"actionable_strict={_pct(item.get('actionable_strict_rate'))} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    work_queue = report.get("work_queue_readiness") or {}
    work_queue_overall = work_queue.get("overall") or {}
    if work_queue_overall:
        print("\nWork queue readiness")
        print(
            "  overall: "
            f"ready_categories={work_queue_overall.get('ready_categories', 0)}/"
            f"{work_queue_overall.get('target_categories', 0)} "
            f"({_pct(work_queue_overall.get('category_ready_rate'))}), "
            f"ready_category_lenses={work_queue_overall.get('ready_category_lenses', 0)}/"
            f"{work_queue_overall.get('target_category_lenses', 0)} "
            f"({_pct(work_queue_overall.get('category_lens_ready_rate'))}), "
            f"fresh_categories={work_queue_overall.get('fresh_ready_categories', 0)}/"
            f"{work_queue_overall.get('target_categories', 0)} "
            f"({_pct(work_queue_overall.get('fresh_category_ready_rate'))}), "
            f"fresh_category_lenses={work_queue_overall.get('fresh_ready_category_lenses', 0)}/"
            f"{work_queue_overall.get('target_category_lenses', 0)} "
            f"({_pct(work_queue_overall.get('fresh_category_lens_ready_rate'))})"
        )
        print(
            "  unique: "
            f"categories={work_queue_overall.get('unique_ready_categories', 0)}/"
            f"{work_queue_overall.get('target_categories', 0)} "
            f"({_pct(work_queue_overall.get('unique_category_ready_rate'))}), "
            f"category_lenses={work_queue_overall.get('unique_ready_category_lenses', 0)}/"
            f"{work_queue_overall.get('target_category_lenses', 0)} "
            f"({_pct(work_queue_overall.get('unique_category_lens_ready_rate'))}), "
            f"fresh_categories={work_queue_overall.get('fresh_unique_ready_categories', 0)}/"
            f"{work_queue_overall.get('target_categories', 0)} "
            f"({_pct(work_queue_overall.get('fresh_unique_category_ready_rate'))}), "
            f"fresh_category_lenses={work_queue_overall.get('fresh_unique_ready_category_lenses', 0)}/"
            f"{work_queue_overall.get('target_category_lenses', 0)} "
            f"({_pct(work_queue_overall.get('fresh_unique_category_lens_ready_rate'))})"
        )
        work_queue_gaps = work_queue.get("priority_gaps") or []
        if work_queue_gaps:
            print(f"  gaps (top {min(top_weak, len(work_queue_gaps))}):")
            for item in work_queue_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"ready={item.get('actionable_strict', 0)}/{item.get('target', 0)} "
                    f"gap={item.get('gap', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_work_queue_gaps = work_queue.get("fresh_priority_gaps") or []
        if fresh_work_queue_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_work_queue_gaps))}):")
            for item in fresh_work_queue_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh={item.get('fresh_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"gap={item.get('gap', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        unique_work_queue_gaps = work_queue.get("unique_priority_gaps") or []
        if unique_work_queue_gaps:
            print(f"  unique gaps (top {min(top_weak, len(unique_work_queue_gaps))}):")
            for item in unique_work_queue_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"unique={item.get('unique_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"raw={item.get('actionable_strict', 0)} "
                    f"dupes={item.get('actionable_strict_duplicate_count', 0)} "
                    f"gap={item.get('gap', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_unique_work_queue_gaps = work_queue.get("fresh_unique_priority_gaps") or []
        if fresh_unique_work_queue_gaps:
            print(f"  fresh unique gaps (top {min(top_weak, len(fresh_unique_work_queue_gaps))}):")
            for item in fresh_unique_work_queue_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_raw={item.get('fresh_actionable_strict', 0)} "
                    f"dupes={item.get('fresh_actionable_strict_duplicate_count', 0)} "
                    f"gap={item.get('gap', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    compliance = report.get("compliance_work_mode_quality") or {}
    compliance_overall = compliance.get("overall") or {}
    if compliance_overall:
        print("\nCompliance work mode")
        print(
            "  overall: "
            f"auto_categories={compliance_overall.get('auto_work_ready_categories', 0)}/"
            f"{compliance_overall.get('target_categories', 0)} "
            f"({_pct(compliance_overall.get('category_auto_work_ready_rate'))}), "
            f"auto_category_lenses={compliance_overall.get('auto_work_ready_category_lenses', 0)}/"
            f"{compliance_overall.get('target_category_lenses', 0)} "
            f"({_pct(compliance_overall.get('category_lens_auto_work_ready_rate'))}), "
            f"modes={_format_counts(compliance_overall.get('work_mode_counts'))}"
        )
        compliance_gaps = compliance.get("priority_gaps") or []
        if compliance_gaps:
            print(f"  gaps (top {min(top_weak, len(compliance_gaps))}):")
            for item in compliance_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"auto={item.get('auto_work_ready_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"manual={item.get('manual_review_only_actionable_strict', 0)} "
                    f"blocked={item.get('blocked_or_escalate_actionable_strict', 0)} "
                    f"flags={','.join(item.get('reply_risk_flags') or []) or '-'} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    diversity = report.get("opportunity_diversity") or {}
    diversity_overall = diversity.get("overall") or {}
    if diversity_overall:
        print("\nOpportunity diversity")
        print(
            "  overall: "
            f"categories={diversity_overall.get('diverse_categories', 0)}/"
            f"{diversity_overall.get('target_categories', 0)} "
            f"({_pct(diversity_overall.get('category_diversity_ready_rate'))}), "
            f"category_lenses={diversity_overall.get('diverse_category_lenses', 0)}/"
            f"{diversity_overall.get('target_category_lenses', 0)} "
            f"({_pct(diversity_overall.get('category_lens_diversity_ready_rate'))}), "
            f"fresh_categories={diversity_overall.get('fresh_diverse_categories', 0)}/"
            f"{diversity_overall.get('target_categories', 0)} "
            f"({_pct(diversity_overall.get('fresh_category_diversity_ready_rate'))}), "
            f"fresh_category_lenses={diversity_overall.get('fresh_diverse_category_lenses', 0)}/"
            f"{diversity_overall.get('target_category_lenses', 0)} "
            f"({_pct(diversity_overall.get('fresh_category_lens_diversity_ready_rate'))})"
        )
        diversity_gaps = diversity.get("priority_gaps") or []
        if diversity_gaps:
            print(f"  gaps (top {min(top_weak, len(diversity_gaps))}):")
            for item in diversity_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"unique={item.get('unique_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"platforms={item.get('platform_count', 0)} "
                    f"seeds={item.get('source_seed_count', 0)} "
                    f"families={item.get('variant_family_count', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_diversity_gaps = diversity.get("fresh_priority_gaps") or []
        if fresh_diversity_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_diversity_gaps))}):")
            for item in fresh_diversity_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_unique={item.get('unique_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"platforms={item.get('platform_count', 0)} "
                    f"seeds={item.get('source_seed_count', 0)} "
                    f"families={item.get('variant_family_count', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    engagement_hook = report.get("engagement_hook_quality") or {}
    engagement_hook_overall = engagement_hook.get("overall") or {}
    if engagement_hook_overall:
        print("\nEngagement hook readiness")
        print(
            "  overall: "
            f"categories={engagement_hook_overall.get('hook_ready_categories', 0)}/"
            f"{engagement_hook_overall.get('target_categories', 0)} "
            f"({_pct(engagement_hook_overall.get('category_hook_ready_rate'))}), "
            f"category_lenses={engagement_hook_overall.get('hook_ready_category_lenses', 0)}/"
            f"{engagement_hook_overall.get('target_category_lenses', 0)} "
            f"({_pct(engagement_hook_overall.get('category_lens_hook_ready_rate'))}), "
            f"fresh_categories={engagement_hook_overall.get('fresh_hook_ready_categories', 0)}/"
            f"{engagement_hook_overall.get('target_categories', 0)} "
            f"({_pct(engagement_hook_overall.get('fresh_category_hook_ready_rate'))}), "
            f"fresh_category_lenses={engagement_hook_overall.get('fresh_hook_ready_category_lenses', 0)}/"
            f"{engagement_hook_overall.get('target_category_lenses', 0)} "
            f"({_pct(engagement_hook_overall.get('fresh_category_lens_hook_ready_rate'))})"
        )
        engagement_hook_gaps = engagement_hook.get("priority_gaps") or []
        if engagement_hook_gaps:
            print(f"  gaps (top {min(top_weak, len(engagement_hook_gaps))}):")
            for item in engagement_hook_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"hooked={item.get('hooked_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('engagement_hook_missing', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_engagement_hook_gaps = engagement_hook.get("fresh_priority_gaps") or []
        if fresh_engagement_hook_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_engagement_hook_gaps))}):")
            for item in fresh_engagement_hook_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_hooked={item.get('fresh_hooked_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('engagement_hook_missing', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    treatment_signature = report.get("treatment_signature_quality") or {}
    treatment_signature_overall = treatment_signature.get("overall") or {}
    if treatment_signature_overall:
        print("\nTreatment signature readiness")
        print(
            "  overall: "
            f"categories={treatment_signature_overall.get('signature_ready_categories', 0)}/"
            f"{treatment_signature_overall.get('target_categories', 0)} "
            f"({_pct(treatment_signature_overall.get('category_signature_ready_rate'))}), "
            f"category_lenses={treatment_signature_overall.get('signature_ready_category_lenses', 0)}/"
            f"{treatment_signature_overall.get('target_category_lenses', 0)} "
            f"({_pct(treatment_signature_overall.get('category_lens_signature_ready_rate'))}), "
            f"fresh_categories={treatment_signature_overall.get('fresh_signature_ready_categories', 0)}/"
            f"{treatment_signature_overall.get('target_categories', 0)} "
            f"({_pct(treatment_signature_overall.get('fresh_category_signature_ready_rate'))}), "
            f"fresh_category_lenses={treatment_signature_overall.get('fresh_signature_ready_category_lenses', 0)}/"
            f"{treatment_signature_overall.get('target_category_lenses', 0)} "
            f"({_pct(treatment_signature_overall.get('fresh_category_lens_signature_ready_rate'))})"
        )
        treatment_signature_gaps = treatment_signature.get("priority_gaps") or []
        if treatment_signature_gaps:
            print(f"  gaps (top {min(top_weak, len(treatment_signature_gaps))}):")
            for item in treatment_signature_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"signature={item.get('signature_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('treatment_signature_missing', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('treatment_signature_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_treatment_signature_gaps = treatment_signature.get("fresh_priority_gaps") or []
        if fresh_treatment_signature_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_treatment_signature_gaps))}):")
            for item in fresh_treatment_signature_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_signature={item.get('fresh_signature_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('treatment_signature_missing', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('treatment_signature_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    treatment_signal_diversity = report.get("treatment_signal_diversity_quality") or {}
    treatment_signal_diversity_overall = treatment_signal_diversity.get("overall") or {}
    if treatment_signal_diversity_overall:
        print("\nTreatment signal diversity")
        print(
            "  overall: "
            f"categories={treatment_signal_diversity_overall.get('treatment_signal_diverse_categories', 0)}/"
            f"{treatment_signal_diversity_overall.get('target_categories', 0)} "
            f"({_pct(treatment_signal_diversity_overall.get('category_treatment_signal_diverse_ready_rate'))}), "
            f"category_lenses={treatment_signal_diversity_overall.get('treatment_signal_diverse_category_lenses', 0)}/"
            f"{treatment_signal_diversity_overall.get('target_category_lenses', 0)} "
            f"({_pct(treatment_signal_diversity_overall.get('category_lens_treatment_signal_diverse_ready_rate'))}), "
            f"fresh_categories={treatment_signal_diversity_overall.get('fresh_treatment_signal_diverse_categories', 0)}/"
            f"{treatment_signal_diversity_overall.get('target_categories', 0)} "
            f"({_pct(treatment_signal_diversity_overall.get('fresh_category_treatment_signal_diverse_ready_rate'))}), "
            f"fresh_category_lenses={treatment_signal_diversity_overall.get('fresh_treatment_signal_diverse_category_lenses', 0)}/"
            f"{treatment_signal_diversity_overall.get('target_category_lenses', 0)} "
            f"({_pct(treatment_signal_diversity_overall.get('fresh_category_lens_treatment_signal_diverse_ready_rate'))})"
        )
        treatment_signal_diversity_gaps = treatment_signal_diversity.get("priority_gaps") or []
        if treatment_signal_diversity_gaps:
            print(f"  gaps (top {min(top_weak, len(treatment_signal_diversity_gaps))}):")
            for item in treatment_signal_diversity_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"signals={item.get('treatment_signal_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"terms={item.get('distinct_treatment_signal_terms', 0)}/"
                    f"{item.get('min_distinct_treatment_signal_terms', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"observed={_ascii_preview(','.join(item.get('treatment_signal_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_treatment_signal_diversity_gaps = treatment_signal_diversity.get("fresh_priority_gaps") or []
        if fresh_treatment_signal_diversity_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_treatment_signal_diversity_gaps))}):")
            for item in fresh_treatment_signal_diversity_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_signals={item.get('fresh_treatment_signal_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"terms={item.get('distinct_treatment_signal_terms', 0)}/"
                    f"{item.get('min_distinct_treatment_signal_terms', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"observed={_ascii_preview(','.join(item.get('treatment_signal_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    seed_candidate_alignment = report.get("seed_candidate_alignment_quality") or {}
    seed_candidate_alignment_overall = seed_candidate_alignment.get("overall") or {}
    if seed_candidate_alignment_overall:
        print("\nSeed -> candidate alignment")
        print(
            "  overall: "
            f"categories={seed_candidate_alignment_overall.get('seed_aligned_categories', 0)}/"
            f"{seed_candidate_alignment_overall.get('target_categories', 0)} "
            f"({_pct(seed_candidate_alignment_overall.get('category_seed_alignment_ready_rate'))}), "
            f"category_lenses={seed_candidate_alignment_overall.get('seed_aligned_category_lenses', 0)}/"
            f"{seed_candidate_alignment_overall.get('target_category_lenses', 0)} "
            f"({_pct(seed_candidate_alignment_overall.get('category_lens_seed_alignment_ready_rate'))}), "
            f"fresh_categories={seed_candidate_alignment_overall.get('fresh_seed_aligned_categories', 0)}/"
            f"{seed_candidate_alignment_overall.get('target_categories', 0)} "
            f"({_pct(seed_candidate_alignment_overall.get('fresh_category_seed_alignment_ready_rate'))}), "
            f"fresh_category_lenses={seed_candidate_alignment_overall.get('fresh_seed_aligned_category_lenses', 0)}/"
            f"{seed_candidate_alignment_overall.get('target_category_lenses', 0)} "
            f"({_pct(seed_candidate_alignment_overall.get('fresh_category_lens_seed_alignment_ready_rate'))})"
        )
        seed_candidate_alignment_gaps = seed_candidate_alignment.get("priority_gaps") or []
        if seed_candidate_alignment_gaps:
            print(f"  gaps (top {min(top_weak, len(seed_candidate_alignment_gaps))}):")
            for item in seed_candidate_alignment_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"aligned={item.get('seed_aligned_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('seed_candidate_alignment_missing', 0)} "
                    f"overlap={item.get('avg_seed_candidate_overlap_rate', 0.0)} "
                    f"missing_terms={_ascii_preview(','.join(item.get('seed_candidate_missing_terms') or []), 42)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_seed_candidate_alignment_gaps = seed_candidate_alignment.get("fresh_priority_gaps") or []
        if fresh_seed_candidate_alignment_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_seed_candidate_alignment_gaps))}):")
            for item in fresh_seed_candidate_alignment_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_aligned={item.get('fresh_seed_aligned_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('seed_candidate_alignment_missing', 0)} "
                    f"overlap={item.get('avg_seed_candidate_overlap_rate', 0.0)} "
                    f"missing_terms={_ascii_preview(','.join(item.get('seed_candidate_missing_terms') or []), 42)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    local_intent = report.get("local_intent_quality") or {}
    local_intent_overall = local_intent.get("overall") or {}
    if local_intent_overall:
        print("\nLocal intent readiness")
        print(
            "  overall: "
            f"categories={local_intent_overall.get('local_ready_categories', 0)}/"
            f"{local_intent_overall.get('target_categories', 0)} "
            f"({_pct(local_intent_overall.get('category_local_ready_rate'))}), "
            f"category_lenses={local_intent_overall.get('local_ready_category_lenses', 0)}/"
            f"{local_intent_overall.get('target_category_lenses', 0)} "
            f"({_pct(local_intent_overall.get('category_lens_local_ready_rate'))}), "
            f"fresh_categories={local_intent_overall.get('fresh_local_ready_categories', 0)}/"
            f"{local_intent_overall.get('target_categories', 0)} "
            f"({_pct(local_intent_overall.get('fresh_category_local_ready_rate'))}), "
            f"fresh_category_lenses={local_intent_overall.get('fresh_local_ready_category_lenses', 0)}/"
            f"{local_intent_overall.get('target_category_lenses', 0)} "
            f"({_pct(local_intent_overall.get('fresh_category_lens_local_ready_rate'))})"
        )
        local_intent_gaps = local_intent.get("priority_gaps") or []
        if local_intent_gaps:
            print(f"  gaps (top {min(top_weak, len(local_intent_gaps))}):")
            for item in local_intent_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"local={item.get('local_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('local_intent_missing', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('local_intent_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_local_intent_gaps = local_intent.get("fresh_priority_gaps") or []
        if fresh_local_intent_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_local_intent_gaps))}):")
            for item in fresh_local_intent_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_local={item.get('fresh_local_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('local_intent_missing', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('local_intent_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    patient_surface = report.get("patient_surface_quality") or {}
    patient_surface_overall = patient_surface.get("overall") or {}
    if patient_surface_overall:
        print("\nPatient surface authenticity")
        print(
            "  overall: "
            f"categories={patient_surface_overall.get('patient_surface_ready_categories', 0)}/"
            f"{patient_surface_overall.get('target_categories', 0)} "
            f"({_pct(patient_surface_overall.get('category_patient_surface_ready_rate'))}), "
            f"category_lenses={patient_surface_overall.get('patient_surface_ready_category_lenses', 0)}/"
            f"{patient_surface_overall.get('target_category_lenses', 0)} "
            f"({_pct(patient_surface_overall.get('category_lens_patient_surface_ready_rate'))}), "
            f"fresh_categories={patient_surface_overall.get('fresh_patient_surface_ready_categories', 0)}/"
            f"{patient_surface_overall.get('target_categories', 0)} "
            f"({_pct(patient_surface_overall.get('fresh_category_patient_surface_ready_rate'))}), "
            f"fresh_category_lenses={patient_surface_overall.get('fresh_patient_surface_ready_category_lenses', 0)}/"
            f"{patient_surface_overall.get('target_category_lenses', 0)} "
            f"({_pct(patient_surface_overall.get('fresh_category_lens_patient_surface_ready_rate'))})"
        )
        patient_surface_gaps = patient_surface.get("priority_gaps") or []
        if patient_surface_gaps:
            print(f"  gaps (top {min(top_weak, len(patient_surface_gaps))}):")
            for item in patient_surface_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"patient={item.get('patient_surface_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('patient_surface_missing', 0)} "
                    f"provider_noise={item.get('provider_surface_noise', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('patient_surface_terms') or []), 36)} "
                    f"provider={_ascii_preview(','.join(item.get('patient_surface_provider_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_patient_surface_gaps = patient_surface.get("fresh_priority_gaps") or []
        if fresh_patient_surface_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_patient_surface_gaps))}):")
            for item in fresh_patient_surface_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_patient={item.get('fresh_patient_surface_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('patient_surface_missing', 0)} "
                    f"provider_noise={item.get('provider_surface_noise', 0)} "
                    f"terms={_ascii_preview(','.join(item.get('patient_surface_terms') or []), 36)} "
                    f"provider={_ascii_preview(','.join(item.get('patient_surface_provider_terms') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    viral_action_route = report.get("viral_action_route_quality") or {}
    viral_action_route_overall = viral_action_route.get("overall") or {}
    if viral_action_route_overall:
        print("\nViral action route readiness")
        print(
            "  overall: "
            f"categories={viral_action_route_overall.get('route_ready_categories', 0)}/"
            f"{viral_action_route_overall.get('target_categories', 0)} "
            f"({_pct(viral_action_route_overall.get('category_route_ready_rate'))}), "
            f"category_lenses={viral_action_route_overall.get('route_ready_category_lenses', 0)}/"
            f"{viral_action_route_overall.get('target_category_lenses', 0)} "
            f"({_pct(viral_action_route_overall.get('category_lens_route_ready_rate'))}), "
            f"fresh_categories={viral_action_route_overall.get('fresh_route_ready_categories', 0)}/"
            f"{viral_action_route_overall.get('target_categories', 0)} "
            f"({_pct(viral_action_route_overall.get('fresh_category_route_ready_rate'))}), "
            f"fresh_category_lenses={viral_action_route_overall.get('fresh_route_ready_category_lenses', 0)}/"
            f"{viral_action_route_overall.get('target_category_lenses', 0)} "
            f"({_pct(viral_action_route_overall.get('fresh_category_lens_route_ready_rate'))})"
        )
        viral_action_route_gaps = viral_action_route.get("priority_gaps") or []
        if viral_action_route_gaps:
            print(f"  gaps (top {min(top_weak, len(viral_action_route_gaps))}):")
            for item in viral_action_route_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"routed={item.get('routed_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('viral_action_route_missing', 0)} "
                    f"mismatch={item.get('viral_action_route_mismatch', 0)} "
                    f"routes={_ascii_preview(','.join(item.get('viral_action_routes') or []), 36)} "
                    f"expected={_ascii_preview(','.join(item.get('expected_viral_action_routes') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_viral_action_route_gaps = viral_action_route.get("fresh_priority_gaps") or []
        if fresh_viral_action_route_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_viral_action_route_gaps))}):")
            for item in fresh_viral_action_route_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_routed={item.get('fresh_routed_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('viral_action_route_missing', 0)} "
                    f"mismatch={item.get('viral_action_route_mismatch', 0)} "
                    f"routes={_ascii_preview(','.join(item.get('viral_action_routes') or []), 36)} "
                    f"expected={_ascii_preview(','.join(item.get('expected_viral_action_routes') or []), 36)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    reply_workability = report.get("reply_workability_quality") or {}
    reply_workability_overall = reply_workability.get("overall") or {}
    if reply_workability_overall:
        print("\nReply workability readiness")
        print(
            "  overall: "
            f"categories={reply_workability_overall.get('reply_workable_categories', 0)}/"
            f"{reply_workability_overall.get('target_categories', 0)} "
            f"({_pct(reply_workability_overall.get('category_reply_workable_ready_rate'))}), "
            f"category_lenses={reply_workability_overall.get('reply_workable_category_lenses', 0)}/"
            f"{reply_workability_overall.get('target_category_lenses', 0)} "
            f"({_pct(reply_workability_overall.get('category_lens_reply_workable_ready_rate'))}), "
            f"fresh_categories={reply_workability_overall.get('fresh_reply_workable_categories', 0)}/"
            f"{reply_workability_overall.get('target_categories', 0)} "
            f"({_pct(reply_workability_overall.get('fresh_category_reply_workable_ready_rate'))}), "
            f"fresh_category_lenses={reply_workability_overall.get('fresh_reply_workable_category_lenses', 0)}/"
            f"{reply_workability_overall.get('target_category_lenses', 0)} "
            f"({_pct(reply_workability_overall.get('fresh_category_lens_reply_workable_ready_rate'))})"
        )
        reply_workability_gaps = reply_workability.get("priority_gaps") or []
        if reply_workability_gaps:
            print(f"  gaps (top {min(top_weak, len(reply_workability_gaps))}):")
            for item in reply_workability_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"reply={item.get('reply_workable_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('reply_workability_missing', 0)} "
                    f"risk={item.get('reply_risk_flagged', 0)} "
                    f"metric_missing={item.get('reply_metric_missing', 0)} "
                    f"avg_score={item.get('avg_reply_opportunity_score') if item.get('avg_reply_opportunity_score') is not None else '-'} "
                    f"tiers={_ascii_preview(','.join(item.get('reply_opportunity_tiers') or []), 30)} "
                    f"risks={_ascii_preview(','.join(item.get('reply_risk_flags') or []), 30)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_reply_workability_gaps = reply_workability.get("fresh_priority_gaps") or []
        if fresh_reply_workability_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_reply_workability_gaps))}):")
            for item in fresh_reply_workability_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_reply={item.get('fresh_reply_workable_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('reply_workability_missing', 0)} "
                    f"risk={item.get('reply_risk_flagged', 0)} "
                    f"metric_missing={item.get('reply_metric_missing', 0)} "
                    f"avg_score={item.get('avg_reply_opportunity_score') if item.get('avg_reply_opportunity_score') is not None else '-'} "
                    f"tiers={_ascii_preview(','.join(item.get('reply_opportunity_tiers') or []), 30)} "
                    f"risks={_ascii_preview(','.join(item.get('reply_risk_flags') or []), 30)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    execution_readiness = report.get("execution_readiness_quality") or {}
    execution_readiness_overall = execution_readiness.get("overall") or {}
    if execution_readiness_overall:
        print("\nExecution readiness")
        print(
            "  overall: "
            f"categories={execution_readiness_overall.get('execution_ready_categories', 0)}/"
            f"{execution_readiness_overall.get('target_categories', 0)} "
            f"({_pct(execution_readiness_overall.get('category_execution_ready_rate'))}), "
            f"category_lenses={execution_readiness_overall.get('execution_ready_category_lenses', 0)}/"
            f"{execution_readiness_overall.get('target_category_lenses', 0)} "
            f"({_pct(execution_readiness_overall.get('category_lens_execution_ready_rate'))}), "
            f"fresh_categories={execution_readiness_overall.get('fresh_execution_ready_categories', 0)}/"
            f"{execution_readiness_overall.get('target_categories', 0)} "
            f"({_pct(execution_readiness_overall.get('fresh_category_execution_ready_rate'))}), "
            f"fresh_category_lenses={execution_readiness_overall.get('fresh_execution_ready_category_lenses', 0)}/"
            f"{execution_readiness_overall.get('target_category_lenses', 0)} "
            f"({_pct(execution_readiness_overall.get('fresh_category_lens_execution_ready_rate'))})"
        )
        execution_readiness_gaps = execution_readiness.get("priority_gaps") or []
        if execution_readiness_gaps:
            print(f"  gaps (top {min(top_weak, len(execution_readiness_gaps))}):")
            for item in execution_readiness_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"ready={item.get('execution_ready_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"unique={item.get('unique_actionable_strict', 0)} "
                    f"missing={item.get('execution_readiness_missing', 0)} "
                    f"fragmented={item.get('fragmented_execution_signals')} "
                    f"components={_ascii_preview(_format_counts(item.get('execution_readiness_missing_components')), 60)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_execution_readiness_gaps = execution_readiness.get("fresh_priority_gaps") or []
        if fresh_execution_readiness_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_execution_readiness_gaps))}):")
            for item in fresh_execution_readiness_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_ready={item.get('fresh_execution_ready_actionable_strict', 0)}/{item.get('target', 0)} "
                    f"fresh_unique={item.get('unique_fresh_actionable_strict', 0)} "
                    f"missing={item.get('execution_readiness_missing', 0)} "
                    f"fragmented={item.get('fragmented_execution_signals')} "
                    f"components={_ascii_preview(_format_counts(item.get('execution_readiness_missing_components')), 60)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    execution_priority = report.get("execution_priority_alignment_quality") or {}
    execution_priority_overall = execution_priority.get("overall") or {}
    if execution_priority_overall:
        print("\nExecution priority alignment")
        print(
            "  overall: "
            f"categories={execution_priority_overall.get('priority_aligned_categories', 0)}/"
            f"{execution_priority_overall.get('target_categories', 0)} "
            f"({_pct(execution_priority_overall.get('category_priority_alignment_rate'))}), "
            f"category_lenses={execution_priority_overall.get('priority_aligned_category_lenses', 0)}/"
            f"{execution_priority_overall.get('target_category_lenses', 0)} "
            f"({_pct(execution_priority_overall.get('category_lens_priority_alignment_rate'))}), "
            f"fresh_categories={execution_priority_overall.get('fresh_priority_aligned_categories', 0)}/"
            f"{execution_priority_overall.get('target_categories', 0)} "
            f"({_pct(execution_priority_overall.get('fresh_category_priority_alignment_rate'))}), "
            f"fresh_category_lenses={execution_priority_overall.get('fresh_priority_aligned_category_lenses', 0)}/"
            f"{execution_priority_overall.get('target_category_lenses', 0)} "
            f"({_pct(execution_priority_overall.get('fresh_category_lens_priority_alignment_rate'))})"
        )
        execution_priority_gaps = execution_priority.get("priority_gaps") or []
        if execution_priority_gaps:
            print(f"  gaps (top {min(top_weak, len(execution_priority_gaps))}):")
            for item in execution_priority_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"top_ready={item.get('top_execution_ready_actionable_strict', 0)}/"
                    f"{item.get('target', 0)} "
                    f"ready={item.get('execution_ready_actionable_strict', 0)} "
                    f"top_window={item.get('priority_top_window', 0)} "
                    f"first_ready_rank={item.get('highest_execution_ready_rank') or '-'} "
                    f"top_non_ready={item.get('top_non_execution_ready_actionable_strict', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )
        fresh_execution_priority_gaps = execution_priority.get("fresh_priority_gaps") or []
        if fresh_execution_priority_gaps:
            print(f"  fresh gaps (top {min(top_weak, len(fresh_execution_priority_gaps))}):")
            for item in fresh_execution_priority_gaps[:top_weak]:
                print(
                    f"    - {item.get('lane')} "
                    f"fresh_top_ready={item.get('fresh_top_execution_ready_actionable_strict', 0)}/"
                    f"{item.get('target', 0)} "
                    f"fresh_ready={item.get('fresh_execution_ready_actionable_strict', 0)} "
                    f"top_window={item.get('priority_top_window', 0)} "
                    f"first_ready_rank={item.get('highest_execution_ready_rank') or '-'} "
                    f"top_non_ready={item.get('top_non_execution_ready_actionable_strict', 0)} "
                    f"reasons={','.join(item.get('reasons') or [])}"
                )

    coverage = report.get("seed_target_coverage") or {}
    if coverage:
        print("\nSeed -> target coverage")
        for lane_type in ("by_category", "by_lens"):
            lanes = coverage.get(lane_type) or {}
            if not lanes:
                continue
            print(f"  {lane_type}:")
            for lane, metrics in lanes.items():
                gap = ",".join(metrics.get("gap_reasons") or []) or "-"
                print(
                    f"    - {lane}: seeds={metrics.get('seed_count', 0)}, "
                    f"targets={metrics.get('target_count', 0)}, "
                    f"strict={metrics.get('strict_fit', 0)}, "
                    f"target/seed={metrics.get('target_per_seed', 0)}, "
                    f"strict/seed={metrics.get('strict_fit_per_seed', 0)}, "
                    f"gap={gap}"
                )

    weak_lanes = report.get("weak_lanes") or []
    if weak_lanes:
        print(f"\nWeak lanes (top {min(top_weak, len(weak_lanes))})")
        for lane in weak_lanes[:top_weak]:
            print(
                f"  - {lane.get('type')}:{lane.get('lane')} "
                f"total={lane.get('total')} strict={_pct(lane.get('strict_fit_rate'))} "
                f"survival={_pct(lane.get('survival_rate'))} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )

    loss_analysis = report.get("loss_analysis") or {}
    loss_hotspots = loss_analysis.get("priority_focus_hotspots") or loss_analysis.get("hotspots") or []
    if loss_hotspots:
        print(f"\nFilter loss hotspots (top {min(top_weak, len(loss_hotspots))})")
        for item in loss_hotspots[:top_weak]:
            reasons = item.get("loss_reason_counts") or {}
            top_reasons = ", ".join(
                f"{name}:{count}"
                for name, count in sorted(reasons.items(), key=lambda pair: int(pair[1] or 0), reverse=True)[:3]
            )
            print(
                f"  - {item.get('type')}:{item.get('lane')} "
                f"lost={item.get('lost', 0)}/{item.get('total', 0)} "
                f"loss={_pct(item.get('loss_rate'))} "
                f"dominant={item.get('dominant_loss_reason') or '-'} "
                f"reasons={top_reasons or '-'}"
            )

    platform_surface = report.get("platform_surface_quality") or {}
    platform_hotspots = platform_surface.get("priority_focus_hotspots") or platform_surface.get("hotspots") or []
    if platform_hotspots:
        print(f"\nPlatform surface hotspots (top {min(top_weak, len(platform_hotspots))})")
        for item in platform_hotspots[:top_weak]:
            reasons = ",".join(item.get("reasons") or []) or "-"
            print(
                f"  - {item.get('type')}:{item.get('lane')} "
                f"total={item.get('total', 0)} "
                f"survival={_pct(item.get('survival_rate'))} "
                f"strict={_pct(item.get('strict_fit_rate'))} "
                f"loss={_pct(item.get('loss_rate'))} "
                f"dominant={item.get('dominant_loss_reason') or '-'} "
                f"reasons={reasons}"
            )

    weak_source_seeds = report.get("weak_source_seeds") or []
    if weak_source_seeds:
        print(f"\nWeak source seeds (top {min(top_weak, len(weak_source_seeds))})")
        for seed in weak_source_seeds[:top_weak]:
            variants = seed.get("query_variant_counts") or {}
            top_variants = ", ".join(
                f"{name}:{count}"
                for name, count in sorted(variants.items(), key=lambda item: int(item[1] or 0), reverse=True)[:3]
            )
            print(
                f"  - {seed.get('category')} | {seed.get('seed')[:58]} "
                f"credits={seed.get('credit_total', seed.get('total'))} "
                f"primary={seed.get('primary_total', 0)} assist={seed.get('assist_total', 0)} "
                f"strict={_pct(seed.get('strict_fit_rate'))} "
                f"survival={_pct(seed.get('survival_rate'))} "
                f"variants={top_variants or '-'} "
                f"reasons={','.join(seed.get('reasons') or [])}"
            )

    source_seed_feedback = report.get("source_seed_feedback") or {}
    if source_seed_feedback:
        counts = source_seed_feedback.get("counts") or {}
        print(
            "\nSource seed feedback "
            f"(recategorize={counts.get('recategorize_candidates', 0)}, "
            f"scale={counts.get('scale_candidates', 0)}, "
            f"repair={counts.get('repair_candidates', 0)}, "
            f"retire={counts.get('retire_candidates', 0)}, "
            f"assist_only={counts.get('assist_only_candidates', 0)})"
        )
        for label, bucket in (
            ("recategorize", source_seed_feedback.get("recategorize_candidates") or []),
            ("repair", source_seed_feedback.get("repair_candidates") or []),
            ("scale", source_seed_feedback.get("scale_candidates") or []),
            ("retire", source_seed_feedback.get("retire_candidates") or []),
            ("assist_only", source_seed_feedback.get("assist_only_candidates") or []),
        ):
            if not bucket:
                continue
            print(f"  {label}:")
            for seed in bucket[: min(3, top_weak)]:
                print(
                    f"    - {seed.get('category')} | {seed.get('seed')[:58]} "
                    f"detected={seed.get('detected_category') or '-'} "
                    f"primary={seed.get('primary_total', 0)} "
                    f"assist={seed.get('assist_total', 0)} "
                    f"drift={_pct(seed.get('category_drift_rate'))} "
                    f"strict={_pct(seed.get('strict_fit_rate'))} "
                    f"survival={_pct(seed.get('survival_rate'))} "
                    f"action={seed.get('action')}"
                )

    recommendations = report.get("recommendations") or []
    if recommendations:
        print(f"\nRecommendations (top {min(top_weak, len(recommendations))})")
        for item in recommendations[:top_weak]:
            lanes = item.get("lanes") or []
            suffix = f" | lanes={', '.join(lanes[:4])}" if lanes else ""
            print(
                f"  - P{item.get('priority')} {item.get('code')}: "
                f"{item.get('action')}{suffix}"
            )

    playbook = report.get("next_run_playbook") or {}
    if playbook:
        print("\nNext run playbook")
        print(f"  rerun_required: {playbook.get('rerun_required')}")
        print(f"  metric_backfill_required: {playbook.get('metric_backfill_required')}")
        print(f"  coverage_gap_required: {playbook.get('coverage_gap_required')}")
        print(f"  content_coherence_required: {playbook.get('content_coherence_required')}")
        print(f"  lens_surface_required: {playbook.get('lens_surface_required')}")
        print(f"  source_seed_feedback_required: {playbook.get('source_seed_feedback_required')}")
        print(f"  filter_loss_required: {playbook.get('filter_loss_required')}")
        print(f"  patient_journey_required: {playbook.get('patient_journey_required')}")
        print(f"  work_queue_required: {playbook.get('work_queue_required')}")
        print(f"  fresh_work_queue_required: {playbook.get('fresh_work_queue_required')}")
        print(f"  unique_work_queue_required: {playbook.get('unique_work_queue_required')}")
        print(f"  fresh_unique_work_queue_required: {playbook.get('fresh_unique_work_queue_required')}")
        print(f"  opportunity_diversity_required: {playbook.get('opportunity_diversity_required')}")
        print(f"  fresh_opportunity_diversity_required: {playbook.get('fresh_opportunity_diversity_required')}")
        print(f"  engagement_hook_required: {playbook.get('engagement_hook_required')}")
        print(f"  fresh_engagement_hook_required: {playbook.get('fresh_engagement_hook_required')}")
        print(f"  treatment_signature_required: {playbook.get('treatment_signature_required')}")
        print(f"  fresh_treatment_signature_required: {playbook.get('fresh_treatment_signature_required')}")
        print(f"  treatment_signal_diversity_required: {playbook.get('treatment_signal_diversity_required')}")
        print(
            "  fresh_treatment_signal_diversity_required: "
            f"{playbook.get('fresh_treatment_signal_diversity_required')}"
        )
        print(f"  seed_candidate_alignment_required: {playbook.get('seed_candidate_alignment_required')}")
        print(
            "  fresh_seed_candidate_alignment_required: "
            f"{playbook.get('fresh_seed_candidate_alignment_required')}"
        )
        print(f"  local_intent_required: {playbook.get('local_intent_required')}")
        print(f"  fresh_local_intent_required: {playbook.get('fresh_local_intent_required')}")
        print(f"  patient_surface_required: {playbook.get('patient_surface_required')}")
        print(f"  fresh_patient_surface_required: {playbook.get('fresh_patient_surface_required')}")
        print(f"  viral_action_route_required: {playbook.get('viral_action_route_required')}")
        print(f"  fresh_viral_action_route_required: {playbook.get('fresh_viral_action_route_required')}")
        print(f"  reply_workability_required: {playbook.get('reply_workability_required')}")
        print(f"  fresh_reply_workability_required: {playbook.get('fresh_reply_workability_required')}")
        print(f"  execution_readiness_required: {playbook.get('execution_readiness_required')}")
        print(f"  fresh_execution_readiness_required: {playbook.get('fresh_execution_readiness_required')}")
        print(f"  execution_priority_alignment_required: {playbook.get('execution_priority_alignment_required')}")
        print(
            "  fresh_execution_priority_alignment_required: "
            f"{playbook.get('fresh_execution_priority_alignment_required')}"
        )
        print(f"  platform_surface_required: {playbook.get('platform_surface_required')}")
        if playbook.get("boost_categories"):
            cats = ", ".join(item.get("category", "") for item in playbook["boost_categories"][:5])
            print(f"  boost_categories: {cats}")
        if playbook.get("boost_lenses"):
            lenses = ", ".join(item.get("lens", "") for item in playbook["boost_lenses"][:5])
            print(f"  boost_lenses: {lenses}")
        if playbook.get("content_mismatch_lanes"):
            lanes = ", ".join(
                f"{item.get('type')}:{item.get('lane')}"
                for item in playbook["content_mismatch_lanes"][:5]
            )
            print(f"  content_mismatch_lanes: {lanes}")
        if playbook.get("lens_surface_mismatch_lanes"):
            lanes = ", ".join(
                f"{item.get('type')}:{item.get('lane')}"
                for item in playbook["lens_surface_mismatch_lanes"][:5]
            )
            print(f"  lens_surface_mismatch_lanes: {lanes}")
        if playbook.get("filter_loss_hotspots"):
            lanes = ", ".join(
                f"{item.get('type')}:{item.get('lane')}:{item.get('dominant_loss_reason') or '-'}"
                for item in playbook["filter_loss_hotspots"][:5]
            )
            print(f"  filter_loss_hotspots: {lanes}")
        if playbook.get("patient_journey_gaps"):
            lanes = ", ".join(
                f"{item.get('category')}::{item.get('lens')}:{','.join(item.get('reasons') or []) or '-'}"
                for item in playbook["patient_journey_gaps"][:5]
            )
            print(f"  patient_journey_gaps: {lanes}")
        if playbook.get("work_queue_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["work_queue_gaps"][:5]
            )
            print(f"  work_queue_gaps: {lanes}")
        if playbook.get("fresh_work_queue_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_work_queue_gaps"][:5]
            )
            print(f"  fresh_work_queue_gaps: {lanes}")
        if playbook.get("unique_work_queue_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('unique_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["unique_work_queue_gaps"][:5]
            )
            print(f"  unique_work_queue_gaps: {lanes}")
        if playbook.get("fresh_unique_work_queue_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('unique_fresh_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_unique_work_queue_gaps"][:5]
            )
            print(f"  fresh_unique_work_queue_gaps: {lanes}")
        if playbook.get("opportunity_diversity_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('platform_count', 0)}p/"
                f"{item.get('source_seed_count', 0)}s/{item.get('variant_family_count', 0)}v"
                for item in playbook["opportunity_diversity_gaps"][:5]
            )
            print(f"  opportunity_diversity_gaps: {lanes}")
        if playbook.get("fresh_opportunity_diversity_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('platform_count', 0)}p/"
                f"{item.get('source_seed_count', 0)}s/{item.get('variant_family_count', 0)}v"
                for item in playbook["fresh_opportunity_diversity_gaps"][:5]
            )
            print(f"  fresh_opportunity_diversity_gaps: {lanes}")
        if playbook.get("engagement_hook_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('hooked_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["engagement_hook_gaps"][:5]
            )
            print(f"  engagement_hook_gaps: {lanes}")
        if playbook.get("fresh_engagement_hook_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_hooked_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_engagement_hook_gaps"][:5]
            )
            print(f"  fresh_engagement_hook_gaps: {lanes}")
        if playbook.get("treatment_signature_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('signature_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["treatment_signature_gaps"][:5]
            )
            print(f"  treatment_signature_gaps: {lanes}")
        if playbook.get("fresh_treatment_signature_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_signature_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_treatment_signature_gaps"][:5]
            )
            print(f"  fresh_treatment_signature_gaps: {lanes}")
        if playbook.get("treatment_signal_diversity_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('distinct_treatment_signal_terms', 0)}/"
                f"{item.get('min_distinct_treatment_signal_terms', 0)}"
                for item in playbook["treatment_signal_diversity_gaps"][:5]
            )
            print(f"  treatment_signal_diversity_gaps: {lanes}")
        if playbook.get("fresh_treatment_signal_diversity_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('distinct_treatment_signal_terms', 0)}/"
                f"{item.get('min_distinct_treatment_signal_terms', 0)}"
                for item in playbook["fresh_treatment_signal_diversity_gaps"][:5]
            )
            print(f"  fresh_treatment_signal_diversity_gaps: {lanes}")
        if playbook.get("seed_candidate_alignment_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('seed_aligned_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["seed_candidate_alignment_gaps"][:5]
            )
            print(f"  seed_candidate_alignment_gaps: {lanes}")
        if playbook.get("fresh_seed_candidate_alignment_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_seed_aligned_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_seed_candidate_alignment_gaps"][:5]
            )
            print(f"  fresh_seed_candidate_alignment_gaps: {lanes}")
        if playbook.get("local_intent_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('local_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["local_intent_gaps"][:5]
            )
            print(f"  local_intent_gaps: {lanes}")
        if playbook.get("fresh_local_intent_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_local_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_local_intent_gaps"][:5]
            )
            print(f"  fresh_local_intent_gaps: {lanes}")
        if playbook.get("patient_surface_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('patient_surface_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["patient_surface_gaps"][:5]
            )
            print(f"  patient_surface_gaps: {lanes}")
        if playbook.get("fresh_patient_surface_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_patient_surface_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_patient_surface_gaps"][:5]
            )
            print(f"  fresh_patient_surface_gaps: {lanes}")
        if playbook.get("viral_action_route_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('routed_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["viral_action_route_gaps"][:5]
            )
            print(f"  viral_action_route_gaps: {lanes}")
        if playbook.get("fresh_viral_action_route_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_routed_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_viral_action_route_gaps"][:5]
            )
            print(f"  fresh_viral_action_route_gaps: {lanes}")
        if playbook.get("reply_workability_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('reply_workable_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["reply_workability_gaps"][:5]
            )
            print(f"  reply_workability_gaps: {lanes}")
        if playbook.get("fresh_reply_workability_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_reply_workable_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_reply_workability_gaps"][:5]
            )
            print(f"  fresh_reply_workability_gaps: {lanes}")
        if playbook.get("execution_readiness_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('execution_ready_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["execution_readiness_gaps"][:5]
            )
            print(f"  execution_readiness_gaps: {lanes}")
        if playbook.get("fresh_execution_readiness_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:{item.get('fresh_execution_ready_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_execution_readiness_gaps"][:5]
            )
            print(f"  fresh_execution_readiness_gaps: {lanes}")
        if playbook.get("execution_priority_alignment_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:top{item.get('priority_top_window', 0)}="
                f"{item.get('top_execution_ready_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["execution_priority_alignment_gaps"][:5]
            )
            print(f"  execution_priority_alignment_gaps: {lanes}")
        if playbook.get("fresh_execution_priority_alignment_gaps"):
            lanes = ", ".join(
                f"{item.get('lane')}:top{item.get('priority_top_window', 0)}="
                f"{item.get('fresh_top_execution_ready_actionable_strict', 0)}/{item.get('target', 0)}"
                for item in playbook["fresh_execution_priority_alignment_gaps"][:5]
            )
            print(f"  fresh_execution_priority_alignment_gaps: {lanes}")
        if playbook.get("platform_surface_hotspots"):
            lanes = ", ".join(
                f"{item.get('platform')}::{item.get('category')}:{','.join(item.get('reasons') or []) or '-'}"
                for item in playbook["platform_surface_hotspots"][:5]
            )
            print(f"  platform_surface_hotspots: {lanes}")
        source_seed_actions = playbook.get("source_seed_actions") or {}
        for action_label in ("recategorize_or_quarantine", "repair_query_shape", "retire_or_pause"):
            action_items = source_seed_actions.get(action_label) or []
            if not action_items:
                continue
            formatted = ", ".join(
                f"{item.get('category')}->{item.get('detected_category') or '-'}:{item.get('seed')[:36]}"
                for item in action_items[:3]
            )
            print(f"  source_seed_{action_label}: {formatted}")
        commands = playbook.get("suggested_commands") or {}
        if commands:
            print(f"  live_scan: {commands.get('live_scan')}")
            print(f"  post_run_audit: {commands.get('post_run_audit')}")
            if commands.get("post_run_audit_current_run_template"):
                print(f"  post_run_audit_current_run: {commands.get('post_run_audit_current_run_template')}")

    samples = report.get("review_samples") or {}
    focus_samples = samples.get("priority_focus_weak_lane_samples") or []
    if focus_samples:
        print("\nPriority focus review samples")
        for lane in focus_samples[:min(top_weak, len(focus_samples))]:
            focus = lane.get("focus_category") or "-"
            print(
                f"  - {lane.get('type')}:{lane.get('lane')} "
                f"focus={focus} reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"axis={sample.get('axis_fit')} lens={sample.get('lens_fit')} "
                    f"{sample.get('title')[:70]}"
                )

    content_samples = samples.get("content_mismatch_samples") or []
    if content_samples:
        print("\nContent mismatch samples")
        for lane in content_samples[:min(top_weak, len(content_samples))]:
            print(
                f"  - {lane.get('type')}:{lane.get('lane')} "
                f"mismatch={_pct(lane.get('mismatch_rate'))}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('category')}->{sample.get('content_detected_category') or '-'} "
                    f"{sample.get('status')} score={sample.get('priority')} "
                    f"{sample.get('title')[:70]}"
                )

    lens_samples = samples.get("lens_surface_mismatch_samples") or []
    if lens_samples:
        print("\nLens surface mismatch samples")
        for lane in lens_samples[:min(top_weak, len(lens_samples))]:
            print(
                f"  - {lane.get('type')}:{lane.get('lane')} "
                f"mismatch={_pct(lane.get('mismatch_rate'))}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("lens_surface_terms") or sample.get("lens_surface_bridge_terms") or [])
                print(
                    f"    * lens={sample.get('lens')} matched={sample.get('lens_surface_matched')} "
                    f"terms={terms or '-'} score={sample.get('priority')} "
                    f"{sample.get('title')[:70]}"
                )

    platform_samples = samples.get("platform_surface_samples") or []
    if platform_samples:
        print("\nPlatform surface samples")
        for lane in platform_samples[:min(top_weak, len(platform_samples))]:
            print(
                f"  - {lane.get('type')}:{lane.get('lane')} "
                f"survival={_pct(lane.get('survival_rate'))} "
                f"strict={_pct(lane.get('strict_fit_rate'))} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * platform={sample.get('platform')} {sample.get('status')} "
                    f"score={sample.get('priority')} axis={sample.get('axis_fit')} "
                    f"lens={sample.get('lens_fit')} {sample.get('title')[:70]}"
                )

    journey_samples = samples.get("patient_journey_gap_samples") or []
    if journey_samples:
        print("\nPatient journey gap samples")
        for lane in journey_samples[:min(top_weak, len(journey_samples))]:
            print(
                f"  - {lane.get('category')}::{lane.get('lens')} "
                f"survival={_pct(lane.get('survival_rate'))} "
                f"strict={_pct(lane.get('strict_fit_rate'))} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"axis={sample.get('axis_fit')} lens={sample.get('lens_fit')} "
                    f"{sample.get('title')[:70]}"
                )

    queue_samples = samples.get("work_queue_gap_samples") or []
    if queue_samples:
        print("\nWork queue gap samples")
        for lane in queue_samples[:min(top_weak, len(queue_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"ready={lane.get('actionable_strict', 0)}/{lane.get('target', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"axis={sample.get('axis_fit')} lens={sample.get('lens_fit')} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_queue_samples = samples.get("fresh_work_queue_gap_samples") or []
    if fresh_queue_samples:
        print("\nFresh work queue gap samples")
        for lane in fresh_queue_samples[:min(top_weak, len(fresh_queue_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh={lane.get('fresh_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"activity={sample.get('activity_at') or '-'} score={sample.get('priority')} "
                    f"{sample.get('title')[:70]}"
                )

    unique_queue_samples = samples.get("unique_work_queue_gap_samples") or []
    if unique_queue_samples:
        print("\nUnique work queue gap samples")
        for lane in unique_queue_samples[:min(top_weak, len(unique_queue_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"unique={lane.get('unique_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"raw={lane.get('actionable_strict', 0)} "
                f"dupes={lane.get('duplicate_count', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"fingerprint={_ascii_preview(sample.get('target_fingerprint'))} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_unique_queue_samples = samples.get("fresh_unique_work_queue_gap_samples") or []
    if fresh_unique_queue_samples:
        print("\nFresh unique work queue gap samples")
        for lane in fresh_unique_queue_samples[:min(top_weak, len(fresh_unique_queue_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_raw={lane.get('fresh_actionable_strict', 0)} "
                f"dupes={lane.get('duplicate_count', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"activity={sample.get('activity_at') or '-'} "
                    f"fingerprint={_ascii_preview(sample.get('target_fingerprint'))} "
                    f"{sample.get('title')[:70]}"
                )

    diversity_samples = samples.get("opportunity_diversity_gap_samples") or []
    if diversity_samples:
        print("\nOpportunity diversity gap samples")
        for lane in diversity_samples[:min(top_weak, len(diversity_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"unique={lane.get('unique_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"platforms={lane.get('platform_count', 0)} "
                f"seeds={lane.get('source_seed_count', 0)} "
                f"families={lane.get('variant_family_count', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} platform={sample.get('platform')} "
                    f"seed={_ascii_preview(sample.get('source_seed'), 36)} "
                    f"family={sample.get('query_variant_family')} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_diversity_samples = samples.get("fresh_opportunity_diversity_gap_samples") or []
    if fresh_diversity_samples:
        print("\nFresh opportunity diversity gap samples")
        for lane in fresh_diversity_samples[:min(top_weak, len(fresh_diversity_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_unique={lane.get('unique_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"platforms={lane.get('platform_count', 0)} "
                f"seeds={lane.get('source_seed_count', 0)} "
                f"families={lane.get('variant_family_count', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"platform={sample.get('platform')} seed={_ascii_preview(sample.get('source_seed'), 36)} "
                    f"family={sample.get('query_variant_family')} "
                    f"{sample.get('title')[:70]}"
                )

    engagement_hook_samples = samples.get("engagement_hook_gap_samples") or []
    if engagement_hook_samples:
        print("\nEngagement hook gap samples")
        for lane in engagement_hook_samples[:min(top_weak, len(engagement_hook_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"hooked={lane.get('hooked_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('engagement_hook_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("engagement_hook_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} hook={sample.get('engagement_hook_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_engagement_hook_samples = samples.get("fresh_engagement_hook_gap_samples") or []
    if fresh_engagement_hook_samples:
        print("\nFresh engagement hook gap samples")
        for lane in fresh_engagement_hook_samples[:min(top_weak, len(fresh_engagement_hook_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_hooked={lane.get('fresh_hooked_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('engagement_hook_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("engagement_hook_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"hook={sample.get('engagement_hook_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    treatment_signature_samples = samples.get("treatment_signature_gap_samples") or []
    if treatment_signature_samples:
        print("\nTreatment signature gap samples")
        for lane in treatment_signature_samples[:min(top_weak, len(treatment_signature_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"signature={lane.get('signature_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('treatment_signature_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("treatment_signature_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} signature={sample.get('treatment_signature_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_treatment_signature_samples = samples.get("fresh_treatment_signature_gap_samples") or []
    if fresh_treatment_signature_samples:
        print("\nFresh treatment signature gap samples")
        for lane in fresh_treatment_signature_samples[:min(top_weak, len(fresh_treatment_signature_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_signature={lane.get('fresh_signature_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('treatment_signature_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("treatment_signature_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"signature={sample.get('treatment_signature_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    treatment_signal_diversity_samples = samples.get("treatment_signal_diversity_gap_samples") or []
    if treatment_signal_diversity_samples:
        print("\nTreatment signal diversity samples")
        for lane in treatment_signal_diversity_samples[:min(top_weak, len(treatment_signal_diversity_samples))]:
            observed = ",".join(lane.get("treatment_signal_terms") or []) or "-"
            expected = ",".join(lane.get("expected_treatment_signal_terms") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"signals={lane.get('treatment_signal_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"terms={lane.get('distinct_treatment_signal_terms', 0)}/"
                f"{lane.get('min_distinct_treatment_signal_terms', 0)} "
                f"gap={lane.get('treatment_signal_diversity_gap', 0)} "
                f"observed={_ascii_preview(observed, 34)} "
                f"expected={_ascii_preview(expected, 34)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("treatment_signature_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} signature={sample.get('treatment_signature_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_treatment_signal_diversity_samples = (
        samples.get("fresh_treatment_signal_diversity_gap_samples") or []
    )
    if fresh_treatment_signal_diversity_samples:
        print("\nFresh treatment signal diversity samples")
        for lane in fresh_treatment_signal_diversity_samples[
            :min(top_weak, len(fresh_treatment_signal_diversity_samples))
        ]:
            observed = ",".join(lane.get("treatment_signal_terms") or []) or "-"
            expected = ",".join(lane.get("expected_treatment_signal_terms") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"fresh_signals={lane.get('fresh_treatment_signal_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"terms={lane.get('distinct_treatment_signal_terms', 0)}/"
                f"{lane.get('min_distinct_treatment_signal_terms', 0)} "
                f"gap={lane.get('treatment_signal_diversity_gap', 0)} "
                f"observed={_ascii_preview(observed, 34)} "
                f"expected={_ascii_preview(expected, 34)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("treatment_signature_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"signature={sample.get('treatment_signature_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    seed_candidate_alignment_samples = samples.get("seed_candidate_alignment_gap_samples") or []
    if seed_candidate_alignment_samples:
        print("\nSeed -> candidate alignment samples")
        for lane in seed_candidate_alignment_samples[:min(top_weak, len(seed_candidate_alignment_samples))]:
            missing_terms = ",".join(lane.get("seed_candidate_missing_terms") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"aligned={lane.get('seed_aligned_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('seed_candidate_alignment_missing', 0)} "
                f"overlap={lane.get('avg_seed_candidate_overlap_rate', 0.0)} "
                f"missing_terms={_ascii_preview(missing_terms, 42)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                source_terms = ",".join(sample.get("seed_candidate_alignment_terms") or []) or "-"
                matched_terms = ",".join(sample.get("seed_candidate_alignment_matched_terms") or []) or "-"
                missing_sample_terms = ",".join(sample.get("seed_candidate_alignment_missing_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} seed_aligned={sample.get('seed_candidate_alignment_matched')} "
                    f"source={_ascii_preview(source_terms, 32)} "
                    f"matched={_ascii_preview(matched_terms, 32)} "
                    f"missing={_ascii_preview(missing_sample_terms, 32)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_seed_candidate_alignment_samples = samples.get("fresh_seed_candidate_alignment_gap_samples") or []
    if fresh_seed_candidate_alignment_samples:
        print("\nFresh seed -> candidate alignment samples")
        for lane in fresh_seed_candidate_alignment_samples[
            :min(top_weak, len(fresh_seed_candidate_alignment_samples))
        ]:
            missing_terms = ",".join(lane.get("seed_candidate_missing_terms") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"fresh_aligned={lane.get('fresh_seed_aligned_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('fresh_seed_candidate_alignment_missing', 0)} "
                f"overlap={lane.get('avg_seed_candidate_overlap_rate', 0.0)} "
                f"missing_terms={_ascii_preview(missing_terms, 42)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                source_terms = ",".join(sample.get("seed_candidate_alignment_terms") or []) or "-"
                matched_terms = ",".join(sample.get("seed_candidate_alignment_matched_terms") or []) or "-"
                missing_sample_terms = ",".join(sample.get("seed_candidate_alignment_missing_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"seed_aligned={sample.get('seed_candidate_alignment_matched')} "
                    f"source={_ascii_preview(source_terms, 32)} "
                    f"matched={_ascii_preview(matched_terms, 32)} "
                    f"missing={_ascii_preview(missing_sample_terms, 32)} "
                    f"{sample.get('title')[:70]}"
                )

    local_intent_samples = samples.get("local_intent_gap_samples") or []
    if local_intent_samples:
        print("\nLocal intent gap samples")
        for lane in local_intent_samples[:min(top_weak, len(local_intent_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"local={lane.get('local_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('local_intent_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("local_intent_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} local={sample.get('local_intent_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_local_intent_samples = samples.get("fresh_local_intent_gap_samples") or []
    if fresh_local_intent_samples:
        print("\nFresh local intent gap samples")
        for lane in fresh_local_intent_samples[:min(top_weak, len(fresh_local_intent_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_local={lane.get('fresh_local_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('local_intent_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("local_intent_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"local={sample.get('local_intent_matched')} "
                    f"terms={_ascii_preview(terms, 36)} "
                    f"{sample.get('title')[:70]}"
                )

    patient_surface_samples = samples.get("patient_surface_gap_samples") or []
    if patient_surface_samples:
        print("\nPatient surface authenticity samples")
        for lane in patient_surface_samples[:min(top_weak, len(patient_surface_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"patient={lane.get('patient_surface_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('patient_surface_missing', 0)} "
                f"provider_noise={lane.get('provider_surface_noise', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("patient_surface_terms") or []) or "-"
                provider_terms = ",".join(sample.get("patient_surface_provider_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} patient={sample.get('patient_surface_matched')} "
                    f"provider_noise={sample.get('patient_surface_provider_noise')} "
                    f"terms={_ascii_preview(terms, 30)} "
                    f"provider={_ascii_preview(provider_terms, 30)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_patient_surface_samples = samples.get("fresh_patient_surface_gap_samples") or []
    if fresh_patient_surface_samples:
        print("\nFresh patient surface authenticity samples")
        for lane in fresh_patient_surface_samples[:min(top_weak, len(fresh_patient_surface_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_patient={lane.get('fresh_patient_surface_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('patient_surface_missing', 0)} "
                f"provider_noise={lane.get('provider_surface_noise', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                terms = ",".join(sample.get("patient_surface_terms") or []) or "-"
                provider_terms = ",".join(sample.get("patient_surface_provider_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"patient={sample.get('patient_surface_matched')} "
                    f"provider_noise={sample.get('patient_surface_provider_noise')} "
                    f"terms={_ascii_preview(terms, 30)} "
                    f"provider={_ascii_preview(provider_terms, 30)} "
                    f"{sample.get('title')[:70]}"
                )

    viral_action_route_samples = samples.get("viral_action_route_gap_samples") or []
    if viral_action_route_samples:
        print("\nViral action route samples")
        for lane in viral_action_route_samples[:min(top_weak, len(viral_action_route_samples))]:
            expected = ",".join(lane.get("expected_viral_action_routes") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"routed={lane.get('routed_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('viral_action_route_missing', 0)} "
                f"mismatch={lane.get('viral_action_route_mismatch', 0)} "
                f"expected={_ascii_preview(expected, 40)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                routes = ",".join(sample.get("viral_action_route_routes") or []) or "-"
                observed = ",".join(sample.get("viral_action_route_observed_routes") or []) or "-"
                terms = ",".join(sample.get("viral_action_route_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} route={sample.get('viral_action_route_matched')} "
                    f"route_id={sample.get('viral_action_route') or '-'} "
                    f"routes={_ascii_preview(routes, 28)} "
                    f"observed={_ascii_preview(observed, 28)} "
                    f"terms={_ascii_preview(terms, 28)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_viral_action_route_samples = samples.get("fresh_viral_action_route_gap_samples") or []
    if fresh_viral_action_route_samples:
        print("\nFresh viral action route samples")
        for lane in fresh_viral_action_route_samples[:min(top_weak, len(fresh_viral_action_route_samples))]:
            expected = ",".join(lane.get("expected_viral_action_routes") or []) or "-"
            print(
                f"  - {lane.get('lane')} "
                f"fresh_routed={lane.get('fresh_routed_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('viral_action_route_missing', 0)} "
                f"mismatch={lane.get('viral_action_route_mismatch', 0)} "
                f"expected={_ascii_preview(expected, 40)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                routes = ",".join(sample.get("viral_action_route_routes") or []) or "-"
                observed = ",".join(sample.get("viral_action_route_observed_routes") or []) or "-"
                terms = ",".join(sample.get("viral_action_route_terms") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"route={sample.get('viral_action_route_matched')} "
                    f"route_id={sample.get('viral_action_route') or '-'} "
                    f"routes={_ascii_preview(routes, 28)} "
                    f"observed={_ascii_preview(observed, 28)} "
                    f"terms={_ascii_preview(terms, 28)} "
                    f"{sample.get('title')[:70]}"
                )

    reply_workability_samples = samples.get("reply_workability_gap_samples") or []
    if reply_workability_samples:
        print("\nReply workability samples")
        for lane in reply_workability_samples[:min(top_weak, len(reply_workability_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"reply={lane.get('reply_workable_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('reply_workability_missing', 0)} "
                f"risk={lane.get('reply_risk_flagged', 0)} "
                f"metric_missing={lane.get('reply_metric_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                signals = ",".join(sample.get("reply_opportunity_signals") or []) or "-"
                risks = ",".join(sample.get("reply_risk_flags") or []) or "-"
                print(
                    f"    * {sample.get('status')} reply={sample.get('reply_workability_matched')} "
                    f"score={sample.get('reply_opportunity_score') if sample.get('reply_opportunity_score') is not None else '-'} "
                    f"tier={sample.get('reply_opportunity_tier') or '-'} "
                    f"risk_blocked={sample.get('reply_risk_blocked')} "
                    f"risk_penalty={sample.get('reply_risk_penalty')} "
                    f"comments={sample.get('comment_count', 0)} views={sample.get('view_count', 0)} "
                    f"signals={_ascii_preview(signals, 34)} "
                    f"risks={_ascii_preview(risks, 28)} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_reply_workability_samples = samples.get("fresh_reply_workability_gap_samples") or []
    if fresh_reply_workability_samples:
        print("\nFresh reply workability samples")
        for lane in fresh_reply_workability_samples[:min(top_weak, len(fresh_reply_workability_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_reply={lane.get('fresh_reply_workable_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('reply_workability_missing', 0)} "
                f"risk={lane.get('reply_risk_flagged', 0)} "
                f"metric_missing={lane.get('reply_metric_missing', 0)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                signals = ",".join(sample.get("reply_opportunity_signals") or []) or "-"
                risks = ",".join(sample.get("reply_risk_flags") or []) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"reply={sample.get('reply_workability_matched')} "
                    f"score={sample.get('reply_opportunity_score') if sample.get('reply_opportunity_score') is not None else '-'} "
                    f"tier={sample.get('reply_opportunity_tier') or '-'} "
                    f"risk_blocked={sample.get('reply_risk_blocked')} "
                    f"comments={sample.get('comment_count', 0)} views={sample.get('view_count', 0)} "
                    f"signals={_ascii_preview(signals, 34)} "
                    f"risks={_ascii_preview(risks, 28)} "
                    f"{sample.get('title')[:70]}"
                )

    execution_readiness_samples = samples.get("execution_readiness_gap_samples") or []
    if execution_readiness_samples:
        print("\nExecution readiness samples")
        for lane in execution_readiness_samples[:min(top_weak, len(execution_readiness_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"ready={lane.get('execution_ready_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"unique={lane.get('unique_actionable_strict', 0)} "
                f"missing={lane.get('execution_readiness_missing', 0)} "
                f"fragmented={lane.get('fragmented_execution_signals')} "
                f"components={_ascii_preview(_format_counts(lane.get('execution_readiness_missing_components')), 60)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                missing = ",".join(
                    name
                    for name, flag in (
                        ("hook", not sample.get("engagement_hook_matched")),
                        ("signature", not sample.get("treatment_signature_matched")),
                        ("local", not sample.get("local_intent_matched")),
                        ("patient", not sample.get("patient_surface_matched")),
                        ("route", not sample.get("viral_action_route_matched")),
                        ("reply", not sample.get("reply_workability_matched")),
                    )
                    if flag
                ) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"missing={missing} "
                    f"reply={sample.get('reply_workability_matched')} "
                    f"route={sample.get('viral_action_route_matched')} "
                    f"signature={sample.get('treatment_signature_matched')} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_execution_readiness_samples = samples.get("fresh_execution_readiness_gap_samples") or []
    if fresh_execution_readiness_samples:
        print("\nFresh execution readiness samples")
        for lane in fresh_execution_readiness_samples[:min(top_weak, len(fresh_execution_readiness_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_ready={lane.get('fresh_execution_ready_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_unique={lane.get('unique_fresh_actionable_strict', 0)} "
                f"missing={lane.get('execution_readiness_missing', 0)} "
                f"fragmented={lane.get('fragmented_execution_signals')} "
                f"components={_ascii_preview(_format_counts(lane.get('execution_readiness_missing_components')), 60)} "
                f"gap={lane.get('gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                missing = ",".join(
                    name
                    for name, flag in (
                        ("hook", not sample.get("engagement_hook_matched")),
                        ("signature", not sample.get("treatment_signature_matched")),
                        ("local", not sample.get("local_intent_matched")),
                        ("patient", not sample.get("patient_surface_matched")),
                        ("route", not sample.get("viral_action_route_matched")),
                        ("reply", not sample.get("reply_workability_matched")),
                    )
                    if flag
                ) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"missing={missing} "
                    f"reply={sample.get('reply_workability_matched')} "
                    f"route={sample.get('viral_action_route_matched')} "
                    f"signature={sample.get('treatment_signature_matched')} "
                    f"{sample.get('title')[:70]}"
                )

    execution_priority_samples = samples.get("execution_priority_alignment_gap_samples") or []
    if execution_priority_samples:
        print("\nExecution priority alignment samples")
        for lane in execution_priority_samples[:min(top_weak, len(execution_priority_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"top_ready={lane.get('top_execution_ready_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"ready={lane.get('execution_ready_actionable_strict', 0)} "
                f"top_window={lane.get('priority_top_window', 0)} "
                f"first_ready_rank={lane.get('highest_execution_ready_rank') or '-'} "
                f"top_non_ready={lane.get('top_non_execution_ready_actionable_strict', 0)} "
                f"gap={lane.get('execution_priority_gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                missing = ",".join(
                    name
                    for name, flag in (
                        ("hook", not sample.get("engagement_hook_matched")),
                        ("signature", not sample.get("treatment_signature_matched")),
                        ("local", not sample.get("local_intent_matched")),
                        ("patient", not sample.get("patient_surface_matched")),
                        ("route", not sample.get("viral_action_route_matched")),
                        ("reply", not sample.get("reply_workability_matched")),
                    )
                    if flag
                ) or "-"
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"missing={missing} "
                    f"reply={sample.get('reply_workability_matched')} "
                    f"route={sample.get('viral_action_route_matched')} "
                    f"{sample.get('title')[:70]}"
                )

    fresh_execution_priority_samples = samples.get("fresh_execution_priority_alignment_gap_samples") or []
    if fresh_execution_priority_samples:
        print("\nFresh execution priority alignment samples")
        for lane in fresh_execution_priority_samples[:min(top_weak, len(fresh_execution_priority_samples))]:
            print(
                f"  - {lane.get('lane')} "
                f"fresh_top_ready={lane.get('fresh_top_execution_ready_actionable_strict', 0)}/{lane.get('target', 0)} "
                f"fresh_ready={lane.get('fresh_execution_ready_actionable_strict', 0)} "
                f"top_window={lane.get('priority_top_window', 0)} "
                f"first_ready_rank={lane.get('highest_execution_ready_rank') or '-'} "
                f"top_non_ready={lane.get('top_non_execution_ready_actionable_strict', 0)} "
                f"gap={lane.get('execution_priority_gap', 0)} "
                f"reasons={','.join(lane.get('reasons') or [])}"
            )
            for sample in (lane.get("samples") or [])[:2]:
                missing = ",".join(
                    name
                    for name, flag in (
                        ("hook", not sample.get("engagement_hook_matched")),
                        ("signature", not sample.get("treatment_signature_matched")),
                        ("local", not sample.get("local_intent_matched")),
                        ("patient", not sample.get("patient_surface_matched")),
                        ("route", not sample.get("viral_action_route_matched")),
                        ("reply", not sample.get("reply_workability_matched")),
                    )
                    if flag
                ) or "-"
                print(
                    f"    * {sample.get('status')} fresh={sample.get('fresh_activity')} "
                    f"score={sample.get('priority')} "
                    f"missing={missing} "
                    f"reply={sample.get('reply_workability_matched')} "
                    f"route={sample.get('viral_action_route_matched')} "
                    f"{sample.get('title')[:70]}"
                )

    weak_samples = samples.get("weak_lane_samples") or []
    if weak_samples:
        print("\nReview samples")
        for lane in weak_samples[:min(top_weak, len(weak_samples))]:
            print(f"  - {lane.get('type')}:{lane.get('lane')} reasons={','.join(lane.get('reasons') or [])}")
            for sample in (lane.get("samples") or [])[:2]:
                print(
                    f"    * {sample.get('status')} score={sample.get('priority')} "
                    f"axis={sample.get('axis_fit')} lens={sample.get('lens_fit')} "
                    f"{sample.get('title')[:70]}"
                )

    baseline = report.get("seed_baseline") or {}
    if baseline:
        missing_categories = baseline.get("missing_seed_categories_in_targets") or []
        missing_lenses = baseline.get("missing_seed_lenses_in_targets") or []
        print("\nSeed baseline")
        print(f"  seed_count: {baseline.get('seed_count', 0)}")
        print(f"  seed_categories: {baseline.get('seed_category_counts', {})}")
        print(f"  seed_lenses: {baseline.get('seed_lens_counts', {})}")
        if missing_categories:
            print(f"  missing target categories: {missing_categories}")
        if missing_lenses:
            print(f"  missing target lenses: {missing_lenses}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Pathfinder -> Viral Hunter target quality.")
    parser.add_argument("--db", default=_default_db_path(), help="SQLite DB path.")
    parser.add_argument("--scan-id", type=int, default=None, help="source_scan_run_id to audit. Defaults to latest.")
    parser.add_argument("--days", type=int, default=None, help="Limit to targets discovered in the last N days.")
    parser.add_argument("--since", default=None, help="Limit to targets discovered or rescanned after this timestamp.")
    parser.add_argument("--limit", type=int, default=None, help="Max rows to inspect.")
    parser.add_argument("--min-axis-fit", type=float, default=55.0)
    parser.add_argument("--min-lens-fit", type=float, default=55.0)
    parser.add_argument("--min-clinic-fit", type=float, default=55.0)
    parser.add_argument("--min-worksite-efficiency", type=float, default=55.0)
    parser.add_argument("--min-lane-total", type=int, default=3)
    parser.add_argument("--min-targets-per-seed", type=float, default=1.0)
    parser.add_argument("--min-strict-fit-per-seed", type=float, default=0.25)
    parser.add_argument("--sample-per-lane", type=int, default=3)
    parser.add_argument("--fresh-days", type=int, default=14, help="Fresh work queue window in days.")
    parser.add_argument("--no-seed-baseline", action="store_true", help="Skip seed baseline comparison.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    parser.add_argument("--top-weak", type=int, default=10, help="Weak lanes to print in summary.")
    args = parser.parse_args()

    report = summarize_viral_handoff_quality(
        args.db,
        source_scan_run_id=args.scan_id,
        days=args.days,
        since=args.since,
        limit=args.limit,
        min_axis_fit=args.min_axis_fit,
        min_lens_fit=args.min_lens_fit,
        min_clinic_fit=args.min_clinic_fit,
        min_worksite_efficiency=args.min_worksite_efficiency,
        min_lane_total=args.min_lane_total,
        min_targets_per_seed=args.min_targets_per_seed,
        min_strict_fit_per_seed=args.min_strict_fit_per_seed,
        sample_per_lane=args.sample_per_lane,
        fresh_days=args.fresh_days,
        include_seed_baseline=not args.no_seed_baseline,
    )

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"wrote {out_path}")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report, top_weak=args.top_weak)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
