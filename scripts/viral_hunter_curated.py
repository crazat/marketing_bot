"""Run Viral Hunter from curated seeds with bounded profile-gap coverage."""

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
    candidates = ViralSeedBuilder().build(
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Viral Hunter from curated Pathfinder seeds.")
    parser.add_argument("--seed-file", default="logs/viral_seeds_curated.json")
    parser.add_argument("--curated-only", action="store_true", help="Do not add Pathfinder-backed profile-gap seeds.")
    parser.add_argument("--min-seeds-per-category", type=int, default=2)
    parser.add_argument("--top-n-for-ai", type=int, default=500)
    parser.add_argument("--ai-parallel", type=int, default=5)
    args = parser.parse_args()

    keywords = _load_curated_keywords(args.seed_file)
    additions: list[str] = []
    if not args.curated_only:
        keywords, additions = _append_profile_gap_seeds(
            keywords,
            minimum_per_category=args.min_seeds_per_category,
        )

    print(f"=== Curated Viral Hunter — seeds {len(keywords)} ===")
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
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
