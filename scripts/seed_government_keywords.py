"""[External Signals R3-6] 정부 시드 키워드 자동 등록.

배경:
  - 어르신 한의 주치의 사업: 2026 본격 시행, 노인 한약 보험 적용 확대
  - 첩약 건강보험 2단계 6개 질환 (2026-04 시행): 월경통/안면마비/뇌혈관후유증/알러지비염/
    기능성소화불량/요추디스크
  → 이들 키워드는 의료보험 정책 변화로 검색 수요 급증 예상. 미리 등록해두고 ranking 추적.

운영자 트리거 (cron 안 씀):
  python scripts/seed_government_keywords.py --status
  python scripts/seed_government_keywords.py
  python scripts/seed_government_keywords.py --dry-run

적재 위치: keyword_insights (grade='B', source='government_seed', search_intent='informational')
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from typing import List, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')

# 정부 정책 시드 키워드
GOVERNMENT_SEEDS: List[Tuple[str, str]] = [
    # (keyword, category)
    # 어르신 한의 주치의 (2026 본격 시행)
    ("한의 주치의", "어르신주치의"),
    ("어르신 한의 주치의", "어르신주치의"),
    ("노인 한약 보험", "어르신주치의"),
    ("어르신 한방 진료", "어르신주치의"),
    # 첩약 건강보험 2단계 6개 질환 (2026-04 시행)
    ("월경통 한약", "첩약보험"),
    ("안면마비 한약", "첩약보험"),
    ("뇌혈관후유증 한약", "첩약보험"),
    ("알러지비염 한약", "첩약보험"),
    ("기능성소화불량 한약", "첩약보험"),
    ("요추디스크 한약", "첩약보험"),
    ("추간판탈출 한약", "첩약보험"),
]


def ensure_unique_constraint(conn: sqlite3.Connection) -> None:
    """source별 keyword UNIQUE를 보장하기 위해 partial index 생성."""
    cur = conn.cursor()
    cur.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_insights_keyword_source
        ON keyword_insights(keyword, source)
    """)
    conn.commit()


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='keyword_insights'")
        if not cur.fetchone():
            print("keyword_insights 테이블 없음.")
            return 1
        rows = cur.execute(
            """
            SELECT category, COUNT(*) c FROM keyword_insights
             WHERE source='government_seed'
             GROUP BY category
            """
        ).fetchall()
        n_total = cur.execute(
            "SELECT COUNT(*) FROM keyword_insights WHERE source='government_seed'"
        ).fetchone()[0]
        print('=== 정부 시드 키워드 현황 ===')
        print(f'  source=government_seed 행수: {n_total}')
        for cat, c in rows:
            print(f'    {cat:<15} {c}건')
        if n_total > 0:
            sample = cur.execute(
                "SELECT keyword, grade FROM keyword_insights "
                "WHERE source='government_seed' ORDER BY created_at DESC LIMIT 5"
            ).fetchall()
            print('\n  최근 적재 sample:')
            for kw, g in sample:
                print(f'    [{g}] {kw}')
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.status:
        return show_status()

    print(f'[gov-seed] 시드 키워드 {len(GOVERNMENT_SEEDS)}개 등록 시작')

    if args.dry_run:
        for kw, cat in GOVERNMENT_SEEDS:
            print(f'  - [{cat:<10}] {kw}')
        print('\n  [dry-run] 적재 X')
        return 0

    conn = sqlite3.connect(DB_PATH)
    try:
        ensure_unique_constraint(conn)
        cur = conn.cursor()
        new_kw = 0
        skipped = 0
        for kw, cat in GOVERNMENT_SEEDS:
            try:
                cur.execute(
                    """
                    INSERT INTO keyword_insights
                        (keyword, source, grade, search_intent, region, category,
                         memo, created_at)
                    VALUES (?, 'government_seed', 'B', 'informational', '청주', ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(keyword, source) DO NOTHING
                    """,
                    (kw, cat, '정부 정책 시드 — 2026 검색 수요 급증 예상'),
                )
                if cur.rowcount > 0:
                    new_kw += 1
                else:
                    skipped += 1
            except sqlite3.IntegrityError:
                skipped += 1
        conn.commit()
        print(f'\n  신규 적재: {new_kw}건, 기존: {skipped}건')
        if new_kw > 0:
            print('  → Pathfinder/순위 스캔에서 자동 추적 대상')
            print('  → battle 키워드 등록은 web UI(/battle)에서 수동 결정')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
