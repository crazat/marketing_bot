"""
Schema.org JSON-LD 일괄 생성 CLI
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

config/business_profile.json + qa_repository → 두 개의 JSON-LD 파일 출력.

사용:
  python scripts/generate_site_schema.py
  python scripts/generate_site_schema.py --status
  python scripts/generate_site_schema.py --max-faq 20
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, List

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parent
_BACKEND = _ROOT / "marketing_bot_web" / "backend"
for p in (_ROOT, _BACKEND):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    from backend_utils.logger import get_logger  # type: ignore
    logger = get_logger(__name__)
except Exception:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logger = logging.getLogger("schema_gen")

DB_PATH = _ROOT / "db" / "marketing_data.db"
PROFILE_PATH = _ROOT / "config" / "business_profile.json"
OUT_DIR = _ROOT / "data" / "generated_schema"


def _load_profile() -> Dict[str, Any]:
    with open(PROFILE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_qa(limit: int) -> List[Dict[str, Any]]:
    if not DB_PATH.exists():
        return []
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='qa_repository'"
        )
        if not cur.fetchone():
            return []
        cur.execute(
            "SELECT question_pattern, standard_answer, variations, use_count "
            "FROM qa_repository "
            "ORDER BY use_count DESC, id ASC LIMIT ?",
            (limit,),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Schema.org JSON-LD 일괄 생성")
    parser.add_argument("--max-faq", type=int, default=30, help="FAQPage 항목 수 (기본 30)")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    from services.schema_generator import (  # type: ignore
        generate_medical_business_schema,
        generate_faq_page_schema,
        validate_schema,
        to_jsonld_string,
    )

    if args.status:
        out = {
            "profile_present": PROFILE_PATH.exists(),
            "qa_count_estimate": len(_load_qa(10000)),
            "output_dir": str(OUT_DIR),
            "files_present": [
                p.name for p in OUT_DIR.glob("*.jsonld") if OUT_DIR.exists()
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    profile = _load_profile()
    qa_list = _load_qa(args.max_faq)

    mb = generate_medical_business_schema(profile)
    faq = generate_faq_page_schema(qa_list)

    mb_issues = validate_schema(mb)
    faq_issues = validate_schema(faq)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    mb_path = OUT_DIR / "medical_business.jsonld"
    faq_path = OUT_DIR / "faq_page.jsonld"
    mb_path.write_text(to_jsonld_string(mb), encoding="utf-8")
    faq_path.write_text(to_jsonld_string(faq), encoding="utf-8")

    summary = {
        "medical_business": {
            "path": str(mb_path),
            "validation_issues": mb_issues,
        },
        "faq_page": {
            "path": str(faq_path),
            "qa_count": len(qa_list),
            "main_entity_count": len(faq.get("mainEntity", [])),
            "validation_issues": faq_issues,
        },
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
