"""[External Signals R3-8] SERP 변동성 자체 계산 (top10 turnover rate).

배경: 외부 SERP 변동 모니터링 서비스(Mozcast, Cognitive SEO) 비용 회피.
       자체 rank_history 데이터로 키워드별 일별 top 10 도메인/업체 다양성·턴오버를 직접 측정.
       알고리즘 변화·경쟁사 대량 최적화 시점 = volatility_score 급등으로 감지.

로직:
  - 키워드 × device_type (mobile/desktop) × date 별로 rank 1-10 target_name 집합 추출
  - 직전 날짜와 비교 → new_entrants / dropouts / turnover_rate 계산
  - turnover_rate = |symmetric_diff| / 10
  - volatility_score = turnover_rate * 0.7 + (rank 변동량 평균 / 10) * 0.3

운영자 트리거 (cron 안 씀):
  python scripts/serp_volatility.py --status
  python scripts/serp_volatility.py
  python scripts/serp_volatility.py --days 14
  python scripts/serp_volatility.py --dry-run

테이블: serp_volatility (db_init에서 자동 생성)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def fetch_top10_per_day(conn: sqlite3.Connection, days: int) -> Dict[Tuple[str, str, str], List[Tuple[int, str]]]:
    """rank_history → (keyword, device_type, date) → [(rank, target_name)]."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    cur = conn.cursor()
    cur.execute(
        """
        SELECT keyword, device_type,
               COALESCE(date, substr(checked_at, 1, 10)) as d,
               rank, target_name
          FROM rank_history
         WHERE rank IS NOT NULL
           AND rank BETWEEN 1 AND 10
           AND status = 'found'
           AND COALESCE(date, substr(checked_at, 1, 10)) >= ?
           AND target_name IS NOT NULL
           AND target_name != ''
        """,
        (since,),
    )
    bucket: Dict[Tuple[str, str, str], List[Tuple[int, str]]] = defaultdict(list)
    for kw, dev, d, rank, tname in cur.fetchall():
        if not kw or not d:
            continue
        bucket[(kw, dev or 'mobile', d)].append((rank, tname))
    return bucket


def compute_volatility(top10s: Dict[Tuple[str, str, str], List[Tuple[int, str]]]) -> List[Dict[str, Any]]:
    """직전 날짜와 비교하여 turnover/volatility 계산."""
    # group by (keyword, device_type)
    by_pair: Dict[Tuple[str, str], List[Tuple[str, List[Tuple[int, str]]]]] = defaultdict(list)
    for (kw, dev, d), entries in top10s.items():
        # rank 정렬 + dedup
        seen: Set[str] = set()
        clean: List[Tuple[int, str]] = []
        for r, t in sorted(entries):
            if t in seen:
                continue
            seen.add(t)
            clean.append((r, t))
        by_pair[(kw, dev)].append((d, clean))

    results: List[Dict[str, Any]] = []
    for (kw, dev), days_list in by_pair.items():
        days_list.sort(key=lambda x: x[0])
        prev_set: Optional[Set[str]] = None
        prev_rank_map: Dict[str, int] = {}
        for d, entries in days_list:
            cur_set = {t for _, t in entries}
            cur_rank_map = {t: r for r, t in entries}
            if prev_set is None:
                prev_set = cur_set
                prev_rank_map = cur_rank_map
                continue
            new_entrants = cur_set - prev_set
            dropouts = prev_set - cur_set
            sym = new_entrants | dropouts
            turnover_rate = len(sym) / max(20, len(cur_set | prev_set)) * 2.0  # normalized 0-1
            turnover_rate = min(1.0, turnover_rate)

            # 동일 target rank 변화량
            common = cur_set & prev_set
            rank_deltas = [
                abs(cur_rank_map[t] - prev_rank_map[t])
                for t in common
                if t in prev_rank_map and t in cur_rank_map
            ]
            avg_delta = sum(rank_deltas) / len(rank_deltas) if rank_deltas else 0.0

            volatility_score = round(turnover_rate * 0.7 + min(avg_delta / 10.0, 1.0) * 0.3, 3)

            results.append({
                'keyword': kw,
                'device_type': dev,
                'measured_date': d,
                'top10_turnover_rate': round(turnover_rate, 3),
                'new_entrants': sorted(list(new_entrants)),
                'dropouts': sorted(list(dropouts)),
                'volatility_score': volatility_score,
            })
            prev_set = cur_set
            prev_rank_map = cur_rank_map
    return results


def upsert_volatility(conn: sqlite3.Connection, rows: List[Dict[str, Any]]) -> int:
    cur = conn.cursor()
    n_new = 0
    for r in rows:
        try:
            cur.execute(
                """
                INSERT INTO serp_volatility
                    (keyword, measured_date, device_type, top10_turnover_rate,
                     new_entrants, dropouts, volatility_score)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(keyword, measured_date, device_type) DO UPDATE SET
                    top10_turnover_rate=excluded.top10_turnover_rate,
                    new_entrants=excluded.new_entrants,
                    dropouts=excluded.dropouts,
                    volatility_score=excluded.volatility_score
                """,
                (
                    r['keyword'], r['measured_date'], r['device_type'],
                    r['top10_turnover_rate'],
                    json.dumps(r['new_entrants'], ensure_ascii=False),
                    json.dumps(r['dropouts'], ensure_ascii=False),
                    r['volatility_score'],
                ),
            )
            if cur.rowcount > 0:
                n_new += 1
        except sqlite3.OperationalError as e:
            print(f'  [warn] upsert 실패 {r["keyword"]}: {e}')
    conn.commit()
    return n_new


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            n_total = cur.execute("SELECT COUNT(*) FROM serp_volatility").fetchone()[0]
        except sqlite3.OperationalError:
            print("serp_volatility 테이블 없음. 서버 시작 또는 db_init.py 실행 필요.")
            return 1
        last = cur.execute("SELECT MAX(measured_date) FROM serp_volatility").fetchone()[0]
        n_kw = cur.execute("SELECT COUNT(DISTINCT keyword) FROM serp_volatility").fetchone()[0]
        print('=== SERP 변동성 현황 ===')
        print(f'  전체 행: {n_total}')
        print(f'  대상 키워드: {n_kw}')
        print(f'  최근 측정일: {last or "-"}')
        if n_total > 0:
            top_vol = cur.execute(
                """
                SELECT keyword, device_type, measured_date, volatility_score
                  FROM serp_volatility
                 WHERE measured_date >= date('now', '-14 days')
                 ORDER BY volatility_score DESC LIMIT 10
                """
            ).fetchall()
            print('\n  변동성 top 10 (최근 14일):')
            for kw, dev, d, vs in top_vol:
                print(f'    {kw:<25} [{dev:<7}] {d}  vol={vs:.2f}')
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=14)
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.status:
        return show_status()

    print(f'[serp-volatility] 분석 범위 days={args.days}')
    conn = sqlite3.connect(DB_PATH)
    try:
        top10s = fetch_top10_per_day(conn, days=args.days)
        print(f'  rank_history 기반 (key, device, date) 조합: {len(top10s)}건')
        results = compute_volatility(top10s)
        print(f'  계산된 volatility row: {len(results)}건')

        if args.dry_run:
            top = sorted(results, key=lambda r: r['volatility_score'], reverse=True)[:10]
            for r in top:
                print(f"  - {r['keyword']:<25} [{r['device_type']:<7}] "
                      f"{r['measured_date']} vol={r['volatility_score']:.2f}  "
                      f"(+{len(r['new_entrants'])}/-{len(r['dropouts'])})")
            print(f'\n  [dry-run] 적재 X')
            return 0

        n = upsert_volatility(conn, results)
        print(f'\n  적재(신규/갱신): {n}건')
        if n > 0:
            print('  → web UI에서 변동성 top 키워드 확인 가능 (또는 query 스킬)')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
