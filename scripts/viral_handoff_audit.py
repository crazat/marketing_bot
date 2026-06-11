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

from core_services.viral_handoff_audit import summarize_viral_handoff_quality


def _default_db_path() -> str:
    return str(ROOT / "db" / "marketing_data.db")


def _pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "0.0%"


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
        f"avg_axis={overall.get('avg_axis_fit', 0)}, "
        f"avg_lens={overall.get('avg_lens_fit', 0)}, "
        f"axis_coverage={_pct(overall.get('axis_coverage_rate'))}, "
        f"lens_coverage={_pct(overall.get('lens_coverage_rate'))}"
    )

    print("\nBy category")
    for category, metrics in (report.get("by_category") or {}).items():
        print(
            f"  - {category}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}, "
            f"axis={metrics.get('avg_axis_fit', 0)}, "
            f"lens={metrics.get('avg_lens_fit', 0)}, "
            f"axis_cov={_pct(metrics.get('axis_coverage_rate'))}, "
            f"lens_cov={_pct(metrics.get('lens_coverage_rate'))}, "
            f"grades={metrics.get('grade_counts', {})}"
        )

    print("\nBy grade")
    for grade, metrics in (report.get("by_grade") or {}).items():
        print(
            f"  - {grade}: total={metrics.get('total', 0)}, "
            f"survival={_pct(metrics.get('survival_rate'))}, "
            f"strict={_pct(metrics.get('strict_fit_rate'))}"
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
        if playbook.get("boost_categories"):
            cats = ", ".join(item.get("category", "") for item in playbook["boost_categories"][:5])
            print(f"  boost_categories: {cats}")
        if playbook.get("boost_lenses"):
            lenses = ", ".join(item.get("lens", "") for item in playbook["boost_lenses"][:5])
            print(f"  boost_lenses: {lenses}")
        commands = playbook.get("suggested_commands") or {}
        if commands:
            print(f"  live_scan: {commands.get('live_scan')}")
            print(f"  post_run_audit: {commands.get('post_run_audit')}")

    samples = report.get("review_samples") or {}
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
    parser.add_argument("--limit", type=int, default=None, help="Max rows to inspect.")
    parser.add_argument("--min-axis-fit", type=float, default=55.0)
    parser.add_argument("--min-lens-fit", type=float, default=55.0)
    parser.add_argument("--min-clinic-fit", type=float, default=55.0)
    parser.add_argument("--min-worksite-efficiency", type=float, default=55.0)
    parser.add_argument("--min-lane-total", type=int, default=3)
    parser.add_argument("--min-targets-per-seed", type=float, default=1.0)
    parser.add_argument("--min-strict-fit-per-seed", type=float, default=0.25)
    parser.add_argument("--sample-per-lane", type=int, default=3)
    parser.add_argument("--no-seed-baseline", action="store_true", help="Skip seed baseline comparison.")
    parser.add_argument("--json", action="store_true", help="Print full JSON report.")
    parser.add_argument("--out", default="", help="Optional JSON output path.")
    parser.add_argument("--top-weak", type=int, default=10, help="Weak lanes to print in summary.")
    args = parser.parse_args()

    report = summarize_viral_handoff_quality(
        args.db,
        source_scan_run_id=args.scan_id,
        days=args.days,
        limit=args.limit,
        min_axis_fit=args.min_axis_fit,
        min_lens_fit=args.min_lens_fit,
        min_clinic_fit=args.min_clinic_fit,
        min_worksite_efficiency=args.min_worksite_efficiency,
        min_lane_total=args.min_lane_total,
        min_targets_per_seed=args.min_targets_per_seed,
        min_strict_fit_per_seed=args.min_strict_fit_per_seed,
        sample_per_lane=args.sample_per_lane,
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
