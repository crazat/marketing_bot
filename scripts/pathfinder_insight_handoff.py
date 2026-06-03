"""Export Pathfinder user brief and agent handoff packets.

Usage:
    python scripts/pathfinder_insight_handoff.py --out reports_pathfinder/insight_brief_latest.json
    python scripts/pathfinder_insight_handoff.py --agent shorts --out scratch/shorts_handoff.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from db.database import DatabaseManager
    from core_services.pathfinder_insight_broker import PathfinderInsightBroker
except Exception as exc:  # pragma: no cover - import failure is surfaced by CLI.
    raise SystemExit(f"import failed: {exc}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export Pathfinder insight handoff JSON.")
    parser.add_argument("--db", default=None, help="SQLite DB path. Defaults to DatabaseManager().db_path.")
    parser.add_argument("--out", default="reports_pathfinder/insight_brief_latest.json", help="Output JSON path.")
    parser.add_argument("--limit", type=int, default=12, help="Keyword/card limit.")
    parser.add_argument("--agent", default="all", help="all, blog, shorts, viral, ads.")
    parser.add_argument("--handoff-only", action="store_true", help="Export only agent handoff packets.")
    parser.add_argument("--include-all-keywords", action="store_true", help="Do not require business_core=1.")
    parser.add_argument("--allow-stale", action="store_true", help="Do not restrict to latest completed Legion run.")
    parser.add_argument("--use-codex", action="store_true", help="Ask Codex CLI for an executive synthesis.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db_path = args.db or DatabaseManager().db_path
    broker = PathfinderInsightBroker(db_path)
    common = {
        "limit": args.limit,
        "business_core_only": not args.include_all_keywords,
        "latest_verified_only": not args.allow_stale,
    }
    if args.handoff_only:
        payload = broker.build_agent_handoffs(agent=args.agent, **common)
    else:
        payload = broker.build_user_brief(use_codex=args.use_codex, **common)

    out = Path(args.out)
    if not out.is_absolute():
        out = ROOT / out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved: {out}")
    print(f"agent_ready: {payload.get('summary', {}).get('agent_ready', bool(payload.get('packets')))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
