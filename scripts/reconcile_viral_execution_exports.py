"""Rebuild legacy Viral Hunter CSV exports from the authoritative DB state.

Older exports could retain an in-memory ``pending`` status after the database
correctly preserved a stricter status such as ``filtered_out_ad``.  This tool
keeps the original reports as an audit trail and writes ``_reconciled`` copies
whose rows are reconstructed from the final persisted records.
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core_services.viral_url_canonicalizer import canonicalize_viral_url
from viral_hunter import ViralHunter, ViralTarget


REPORTS = ROOT / "reports"
DB_PATH = ROOT / "db" / "marketing_data.db"

CSV_HEADERS = [
    "rank", "execution_bucket", "comment_status", "platform", "title", "priority_score",
    "exposure_score", "workability_score", "conversion_fit_score",
    "execution_data_quality_score", "execution_data_quality_tier",
    "execution_data_quality_missing", "execution_auto_ready", "viral_need_score",
    "execution_quality_contract", "execution_priority_cap", "viral_need_tier",
    "viral_need_signals", "reply_opportunity_score", "reply_opportunity_tier",
    "reply_opportunity_signals", "timing_window_score", "timing_window_tier",
    "timing_window_signals", "journey_fit_score", "journey_stage", "journey_signals",
    "qualification_fit_score", "qualification_tier", "qualification_signals", "manual_review",
    "reply_risk_flags", "search_sort", "search_rank", "keyword", "url",
]


def source_paths(timestamp: str) -> list[Path]:
    return [
        REPORTS / f"viral_targets_{timestamp}.csv",
        REPORTS / f"viral_targets_manual_review_{timestamp}.csv",
        REPORTS / f"viral_targets_needs_enrichment_{timestamp}.csv",
    ]


def read_source_urls(paths: Iterable[Path]) -> tuple[list[str], list[str]]:
    urls: list[str] = []
    missing_files: list[str] = []
    seen: set[str] = set()
    for path in paths:
        if not path.exists():
            missing_files.append(path.name)
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                url = (row.get("url") or "").strip()
                identity = canonicalize_viral_url(url) or url
                if url and identity not in seen:
                    seen.add(identity)
                    urls.append(url)
    return urls, missing_files


def load_target(conn: sqlite3.Connection, url: str):
    canonical_url = canonicalize_viral_url(url)
    return conn.execute(
        """
        SELECT * FROM viral_targets
         WHERE url = ? OR canonical_url = ? OR url = ? OR canonical_url = ?
         ORDER BY last_scanned_at DESC, discovered_at DESC
         LIMIT 1
        """,
        (url, url, canonical_url, canonical_url),
    ).fetchone()


def export_row(rank: int, bucket: str, target: ViralTarget) -> list[object]:
    breakdown = target.score_breakdown or {}
    return [
        rank, bucket, target.comment_status, target.platform, target.title, target.priority_score,
        target.exposure_score, target.workability_score, target.conversion_fit_score,
        breakdown.get("execution_data_quality_score", 0),
        breakdown.get("execution_data_quality_tier", ""),
        breakdown.get("execution_data_quality_missing", ""),
        breakdown.get("execution_auto_ready", False),
        breakdown.get("viral_need_score", 0),
        breakdown.get("execution_quality_contract", ""),
        breakdown.get("execution_priority_cap", 0),
        breakdown.get("viral_need_tier", ""),
        breakdown.get("viral_need_signals", ""),
        breakdown.get("reply_opportunity_score", 0),
        breakdown.get("reply_opportunity_tier", ""),
        breakdown.get("reply_opportunity_signals", ""),
        breakdown.get("timing_window_score", 0),
        breakdown.get("timing_window_tier", ""),
        breakdown.get("timing_window_signals", ""),
        breakdown.get("journey_fit_score", 0),
        breakdown.get("journey_stage", ""),
        breakdown.get("journey_signals", ""),
        breakdown.get("qualification_fit_score", 0),
        breakdown.get("qualification_tier", ""),
        breakdown.get("qualification_signals", ""),
        breakdown.get("manual_review", 0),
        breakdown.get("reply_risk_flags", ""),
        target.search_sort, target.search_rank,
        ", ".join(target.matched_keywords[:3]) if target.matched_keywords else "", target.url,
    ]


def write_export(path: Path, rows: list[ViralTarget], bucket: str) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_HEADERS)
        for rank, target in enumerate(rows, 1):
            writer.writerow(export_row(rank, bucket, target))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timestamp", required=True, help="원본 CSV timestamp (예: 20260712_143245)")
    args = parser.parse_args()

    source_urls, missing_files = read_source_urls(source_paths(args.timestamp))
    if not source_urls:
        raise SystemExit("원본 CSV에서 URL을 찾지 못했습니다.")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    buckets: dict[str, list[ViralTarget]] = {
        "auto_ready": [], "manual_review": [], "needs_enrichment": [],
    }
    dropped_statuses: Counter[str] = Counter()
    missing_targets: list[str] = []
    duplicate_targets = 0
    seen_ids: set[str] = set()

    for url in source_urls:
        row = load_target(conn, url)
        if row is None:
            missing_targets.append(url)
            continue
        target = ViralHunter._viral_target_from_db_row(row)
        if target.id in seen_ids:
            duplicate_targets += 1
            continue
        seen_ids.add(target.id)

        status = str(target.comment_status or "pending").strip().lower()
        if (
            status not in ViralHunter.EXECUTION_ACTIONABLE_STATUSES
            and not ViralHunter._is_manual_review_target(target)
        ):
            dropped_statuses[status or "unknown"] += 1
            continue
        ViralHunter._sync_execution_quality(target)
        buckets[ViralHunter._execution_export_bucket(target)].append(target)
    conn.close()

    suffix = f"{args.timestamp}_reconciled"
    outputs = {
        "auto_ready": REPORTS / f"viral_targets_{suffix}.csv",
        "manual_review": REPORTS / f"viral_targets_manual_review_{suffix}.csv",
        "needs_enrichment": REPORTS / f"viral_targets_needs_enrichment_{suffix}.csv",
    }
    for bucket, path in outputs.items():
        write_export(path, buckets[bucket], bucket)

    summary = {
        "source_timestamp": args.timestamp,
        "source_rows": len(source_urls),
        "missing_source_files": missing_files,
        "kept_by_bucket": {bucket: len(rows) for bucket, rows in buckets.items()},
        "dropped_by_authoritative_status": dict(dropped_statuses),
        "missing_db_targets": len(missing_targets),
        "missing_db_target_urls": missing_targets,
        "duplicate_db_targets": duplicate_targets,
        "outputs": {bucket: str(path.relative_to(ROOT)) for bucket, path in outputs.items()},
    }
    summary_path = REPORTS / f"viral_execution_export_reconciliation_{args.timestamp}.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
