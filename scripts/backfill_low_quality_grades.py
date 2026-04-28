"""
[Q7] keyword_insights 품질 게이트 백필 스크립트.

신규 발굴은 pathfinder_v3_complete.py / pathfinder_v3_legion.py에서 강화된 게이트가 적용되지만,
기존에 쌓인 garbage S/A 키워드(search_volume=0이거나 KEI=0)는 그대로 남아있음.
이 스크립트로 일회성 정리.

두 단계 게이트:
  --mode=conservative (기본): search_volume < 50 OR search_volume IS NULL -> C
                              (명백한 garbage만, ~989건 예상)
  --mode=strict: 위 + (difficulty=0 OR priority_v3<1) AND search_volume<100 -> C
                 (SERP 미분석 의심 포함, 3000+건)

운영자가 명시적으로 실행 (cron 안 씀):
  python scripts/backfill_low_quality_grades.py                          # 보수 dry-run
  python scripts/backfill_low_quality_grades.py --mode=strict            # 공격 dry-run
  python scripts/backfill_low_quality_grades.py --apply                  # 보수 적용
  python scripts/backfill_low_quality_grades.py --mode=strict --apply    # 공격 적용
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import io
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "db" / "marketing_data.db"


CONSERVATIVE_WHERE = """
    grade IN ('S', 'A', 'B')
    AND (search_volume IS NULL OR search_volume < 50)
"""

STRICT_WHERE = """
    grade IN ('S', 'A', 'B')
    AND (
        search_volume IS NULL
        OR search_volume < 50
        OR (
            (difficulty IS NULL OR difficulty = 0 OR priority_v3 IS NULL OR priority_v3 < 1)
            AND (search_volume IS NULL OR search_volume < 100)
        )
    )
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["conservative", "strict"],
        default="conservative",
        help="conservative: search_volume<50만. strict: SERP 미분석 의심도 포함",
    )
    parser.add_argument("--apply", action="store_true", help="실제 UPDATE 실행 (없으면 dry-run)")
    args = parser.parse_args()

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    if not DB_PATH.exists():
        print(f"DB not found: {DB_PATH}")
        return 1

    where_clause = CONSERVATIVE_WHERE if args.mode == "conservative" else STRICT_WHERE

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        f"""
        SELECT id, keyword, grade, search_volume, difficulty, priority_v3
        FROM keyword_insights
        WHERE {where_clause}
        """
    ).fetchall()

    by_grade = {"S": 0, "A": 0, "B": 0}
    for r in rows:
        by_grade[r["grade"]] = by_grade.get(r["grade"], 0) + 1

    print("=" * 70)
    print(f"Q7 백필 - 저품질 키워드 등급 강등 [mode={args.mode}]")
    print("=" * 70)
    print(f"영향 대상: {len(rows)}건")
    print(f"  S -> C: {by_grade['S']}")
    print(f"  A -> C: {by_grade['A']}")
    print(f"  B -> C: {by_grade['B']}")
    print()

    print("샘플 10건:")
    for r in rows[:10]:
        print(
            f"  [{r['grade']}] {r['keyword']:<30} "
            f"vol={r['search_volume']!s:>6} diff={r['difficulty']!s:>4} "
            f"prio={r['priority_v3']!s:>6}"
        )

    if not args.apply:
        print()
        print("dry-run 모드. 실제 적용은 --apply.")
        return 0

    print()
    print(f"{len(rows)}건 강등 중...")
    cur.execute(
        f"""
        UPDATE keyword_insights
           SET grade = 'C'
         WHERE {where_clause}
        """
    )
    affected = cur.rowcount
    conn.commit()
    print(f"강등 완료: {affected}건")

    return 0


if __name__ == "__main__":
    sys.exit(main())
