"""Run Viral Hunter from a specific Pathfinder scan with optional manual seeds."""

import argparse
import json
import os
import sys
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core_services.viral_seed_builder import ViralSeedBuilder, canonical_category_for_keyword
from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE as GYULIM_KEYWORD_PROFILE
from viral_hunter import ViralHunter


def _load_curated_keywords(path: str) -> list[str]:
    with open(path, encoding="utf-8") as handle:
        values = json.load(handle)
    return list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def _append_profile_gap_seeds(
    keywords: list[str],
    *,
    builder: ViralSeedBuilder,
    source_scan_id: int,
    minimum_per_category: int,
) -> tuple[list[str], list[str]]:
    """Add only enough Pathfinder-backed seeds to cover missing care axes."""
    minimum = max(0, int(minimum_per_category or 0))
    if minimum == 0:
        return keywords, []

    focus_categories = [
        GYULIM_KEYWORD_PROFILE.normalize_category(category)
        for category in getattr(GYULIM_KEYWORD_PROFILE, "focus_categories", ())
    ]
    focus_categories = list(dict.fromkeys(category for category in focus_categories if category))
    category_counts = Counter(
        canonical_category_for_keyword(keyword)
        for keyword in keywords
    )
    quotas = {category: minimum for category in focus_categories}
    candidates = builder.build(
        scan_run_id=source_scan_id,
        quotas=quotas,
        include_grades=("S", "A"),
        fill_profile_gaps=True,
    )

    additions: list[str] = []
    seen = set(keywords)
    for seed in candidates:
        category = GYULIM_KEYWORD_PROFILE.normalize_category(seed.category)
        if category_counts[category] >= minimum or seed.keyword in seen:
            continue
        keywords.append(seed.keyword)
        seen.add(seed.keyword)
        category_counts[category] += 1
        additions.append(seed.keyword)
    return keywords, additions


def _scan_keywords(
    builder: ViralSeedBuilder,
    *,
    source_scan_id: int,
    limit: int | None,
    include_b: bool,
) -> list[str]:
    """Return the ranked seed cohort from the exact triggering Legion scan.

    B-grade seeds are kept only for care axes with no S/A representative by
    default.  This preserves coverage while preventing lower-confidence B
    inventory from crowding out the demonstrably stronger S/A cohort.
    """
    seeds = builder.build(
        scan_run_id=source_scan_id,
        include_grades=("S", "A", "B"),
        fill_profile_gaps=True,
    )
    if not include_b:
        sa_categories = {
            GYULIM_KEYWORD_PROFILE.normalize_category(seed.category)
            for seed in seeds
            if str(seed.grade or "").upper() in {"S", "A"}
        }
        seeds = [
            seed
            for seed in seeds
            if str(seed.grade or "").upper() != "B"
            or GYULIM_KEYWORD_PROFILE.normalize_category(seed.category) not in sa_categories
        ]
    keywords = list(dict.fromkeys(seed.keyword for seed in seeds if seed.keyword))
    if limit is not None:
        keywords = keywords[: max(0, int(limit))]
    return keywords


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Viral Hunter from curated Pathfinder seeds.")
    parser.add_argument(
        "--source-scan-id",
        type=int,
        default=None,
        help="Completed Pathfinder/Legion scan to consume (default: latest completed Legion scan).",
    )
    parser.add_argument(
        "--seed-file",
        default=None,
        help="Optional JSON seed list to append after scan-backed Pathfinder seeds.",
    )
    parser.add_argument(
        "--curated-only",
        action="store_true",
        help="Use only --seed-file; intended for an explicit legacy/manual run.",
    )
    parser.add_argument(
        "--scan-seed-limit",
        type=int,
        default=None,
        help="Optional cap on Pathfinder-backed seeds after ranking.",
    )
    parser.add_argument(
        "--include-b",
        action="store_true",
        help="Include every B-grade Pathfinder seed instead of using B only as category coverage fallback.",
    )
    parser.add_argument("--min-seeds-per-category", type=int, default=2)
    parser.add_argument("--top-n-for-ai", type=int, default=500)
    parser.add_argument("--ai-parallel", type=int, default=5)
    args = parser.parse_args()

    if args.curated_only and not args.seed_file:
        parser.error("--curated-only requires --seed-file")

    builder = ViralSeedBuilder()
    source_scan_id = args.source_scan_id or builder.latest_completed_legion_scan_id()
    if not source_scan_id:
        parser.error("No completed Pathfinder/Legion scan is available")

    scan_keywords = [] if args.curated_only else _scan_keywords(
        builder,
        source_scan_id=source_scan_id,
        limit=args.scan_seed_limit,
        include_b=args.include_b,
    )
    curated_keywords = _load_curated_keywords(args.seed_file) if args.seed_file else []
    keywords = list(dict.fromkeys(scan_keywords + curated_keywords))
    additions: list[str] = []
    if not args.curated_only:
        keywords, additions = _append_profile_gap_seeds(
            keywords,
            builder=builder,
            source_scan_id=source_scan_id,
            minimum_per_category=args.min_seeds_per_category,
        )

    print(f"=== Curated Viral Hunter — seeds {len(keywords)} ===")
    if not keywords:
        parser.error("No seeds were selected for Viral Hunter")

    print(f"    Source Pathfinder scan: {source_scan_id}")
    print(f"    Pathfinder-backed: {len(scan_keywords)}")
    if curated_keywords:
        print(f"    Manual curated supplement: {len(curated_keywords)}")
    if additions:
        print(f"    Profile-gap seeds added: {len(additions)}")
    for keyword in keywords:
        print(f"  - {keyword}")
    print()

    hunter = ViralHunter()
    hunter.hunt(
        keywords=keywords,
        fresh=True,
        checkpoint_every=5,
        top_n_for_ai=args.top_n_for_ai,
        ai_parallel=args.ai_parallel,
        source_scan_run_id=source_scan_id,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
