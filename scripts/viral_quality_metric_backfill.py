"""CLI for backfilling Viral Hunter quality metrics on stored targets.

Usage:
  python scripts/viral_quality_metric_backfill.py --scan-id 104
  python scripts/viral_quality_metric_backfill.py --scan-id 104 --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core_services.viral_quality_metric_backfill import backfill_quality_metrics, default_db_path


def _print_summary(report: dict) -> None:
    mode = "apply" if report.get("apply") else "dry-run"
    print("Viral quality metric backfill")
    print(f"  mode: {mode}")
    print(f"  db: {report.get('db_path')}")
    print(f"  source_scan_run_id: {report.get('source_scan_run_id')}")
    print(f"  candidates: {report.get('candidate_count', 0)}")
    print(f"  would_update: {report.get('would_update', 0)}")
    print(f"  updated: {report.get('updated', 0)}")
    print(f"  skipped_no_change: {report.get('skipped_no_change', 0)}")
    print(f"  coverage_before: {report.get('coverage_before', {})}")
    print(f"  coverage_after: {report.get('coverage_after', {})}")
    print(f"  statuses: {report.get('status_counts', {})}")
    print(f"  clinic_tiers: {report.get('clinic_tier_counts', {})}")
    print(f"  worksite_tiers: {report.get('worksite_tier_counts', {})}")

    samples = report.get("samples") or []
    if samples:
        print("\nSamples")
        for sample in samples[:10]:
            print(
                f"  - {sample.get('target_id')} "
                f"status={sample.get('status')} "
                f"clinic={sample.get('clinic_score')}:{sample.get('clinic_tier')} "
                f"worksite={sample.get('worksite_score')}:{sample.get('worksite_tier')} "
                f"title={sample.get('title')}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill Viral Hunter quality metrics for stored targets.")
    parser.add_argument("--db", default=default_db_path(), help="SQLite DB path")
    parser.add_argument("--scan-id", type=int, default=None, help="source_scan_run_id to backfill")
    parser.add_argument("--limit", type=int, default=None, help="Max candidates to inspect")
    parser.add_argument("--apply", action="store_true", help="Persist updates. Omit for dry-run.")
    parser.add_argument("--include-all", action="store_true", help="Recompute even if quality metrics already exist")
    parser.add_argument("--status", action="append", default=None, help="Comment status to include; repeatable")
    parser.add_argument("--sample-size", type=int, default=10, help="Number of sample updates to print")
    parser.add_argument("--json", action="store_true", help="Print the full JSON report")
    args = parser.parse_args()

    report = backfill_quality_metrics(
        db_path=args.db,
        source_scan_run_id=args.scan_id,
        limit=args.limit,
        apply=args.apply,
        statuses=args.status,
        only_missing=not args.include_all,
        sample_size=args.sample_size,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_summary(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
