"""Backfill keyword_insights.business_core for Pathfinder Legion focus categories.

This keeps S/A/B/C grades intact and adds a separate business-core signal for
the clinic's real acquisition categories.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = PROJECT_ROOT / "db" / "marketing_data.db"

CORE_CATEGORY_VARIANTS = (
    "다이어트",
    "다이어트/비만",
    "비만",
    "교통사고",
    "교통사고_입원",
    "교통사고입원",
    "안면비대칭",
    "안면비대칭_교정",
    "안면비대칭교정",
    "체형교정",
)
SKIN_CATEGORY_VARIANTS = (
    "피부/여드름",
    "여드름/피부",
    "여드름_피부",
    "여드름",
    "피부",
)
CORE_SKIN_TOKENS = (
    "여드름",
    "여드름흉터",
    "여드름자국",
    "새살침",
    "흉터",
    "패인흉터",
    "모공흉터",
    "흉터치료",
)


def ensure_column(conn: sqlite3.Connection) -> None:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(keyword_insights)")}
    if "business_core" not in cols:
        conn.execute("ALTER TABLE keyword_insights ADD COLUMN business_core INTEGER DEFAULT 0")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_keyword_insights_business_core "
        "ON keyword_insights(business_core)"
    )


def backfill(conn: sqlite3.Connection) -> tuple[int, int]:
    ensure_column(conn)

    conn.execute("UPDATE keyword_insights SET business_core = 0")

    cat_placeholders = ",".join("?" for _ in CORE_CATEGORY_VARIANTS)
    cur = conn.execute(
        f"""
        UPDATE keyword_insights
        SET business_core = 1
        WHERE category IN ({cat_placeholders})
        """,
        CORE_CATEGORY_VARIANTS,
    )
    category_rows = cur.rowcount

    skin_category_placeholders = ",".join("?" for _ in SKIN_CATEGORY_VARIANTS)
    skin_conditions = " OR ".join("keyword LIKE ?" for _ in CORE_SKIN_TOKENS)
    skin_params = tuple(f"%{token}%" for token in CORE_SKIN_TOKENS)
    cur = conn.execute(
        f"""
        UPDATE keyword_insights
        SET business_core = 1
        WHERE category IN ({skin_category_placeholders})
          AND ({skin_conditions})
        """,
        (*SKIN_CATEGORY_VARIANTS, *skin_params),
    )
    skin_rows = cur.rowcount
    conn.commit()
    return category_rows, skin_rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(DEFAULT_DB), help="SQLite DB path")
    args = parser.parse_args()

    with sqlite3.connect(args.db) as conn:
        category_rows, skin_rows = backfill(conn)
        total = conn.execute(
            "SELECT COUNT(*) FROM keyword_insights WHERE COALESCE(business_core, 0) = 1"
        ).fetchone()[0]

    print(f"business_core backfilled: category_rows={category_rows}, skin_rows={skin_rows}, total={total}")


if __name__ == "__main__":
    main()
