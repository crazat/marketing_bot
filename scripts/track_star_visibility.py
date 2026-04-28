"""[R8] 경쟁사 네이버 플레이스 별점·비공개 전환 추적.

2026-4-6 별점 부활 + 점주 비공개 옵션 도입. 비공개 전환 시점 자체가 신호:
  - 별점이 보이다가 갑자기 비공개로 전환 = 평점 낮음 추정
  - 별점 신규 공개 = 자신감 있는 점수

운영자가 명시적으로 트리거 (cron 안 씀):
  python scripts/track_star_visibility.py --status         # 직전 스냅샷
  python scripts/track_star_visibility.py                  # 모든 경쟁사 1회 체크
  python scripts/track_star_visibility.py --diff-only      # 직전 대비 변화만 보고

스캔: scrapers/scraper_naver_place.py를 단발성으로 호출하거나, place_id로 직접 SERP 진입.
이 스크립트는 competitor_star_history에 스냅샷을 적재 + 직전 대비 변화를 출력.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime
from typing import Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
TARGETS_PATH = os.path.join(ROOT_DIR, 'config', 'targets.json')


def load_competitors() -> list[dict]:
    with open(TARGETS_PATH, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    return [t for t in cfg.get('targets', []) if t.get('priority') in ('Critical', 'High', 'Medium')]


def latest_snapshot(cur, name: str) -> Optional[tuple]:
    row = cur.execute(
        """
        SELECT star_rating, star_visible, review_count, checked_at
          FROM competitor_star_history
         WHERE competitor_name = ?
         ORDER BY checked_at DESC LIMIT 1
        """,
        (name,),
    ).fetchone()
    return row


def detect_transition(prev: Optional[tuple], curr: dict) -> Optional[str]:
    """직전 → 현재 전환 이벤트 판정."""
    if prev is None:
        return 'first_seen'
    prev_rating, prev_visible, *_ = prev
    if prev_visible == 1 and not curr['star_visible']:
        return 'visibility_lost'  # 비공개 전환 — 평점 낮음 의심
    if prev_visible == 0 and curr['star_visible']:
        return 'visibility_gained'
    if prev_rating is not None and curr.get('star_rating') is not None:
        diff = curr['star_rating'] - prev_rating
        if abs(diff) >= 0.5:
            return f'rating_drop_{diff:+.1f}' if diff < 0 else f'rating_rise_{diff:+.1f}'
    return None


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT competitor_name,
               (SELECT star_rating FROM competitor_star_history sub
                 WHERE sub.competitor_name = csh.competitor_name
                 ORDER BY checked_at DESC LIMIT 1) latest_rating,
               (SELECT star_visible FROM competitor_star_history sub
                 WHERE sub.competitor_name = csh.competitor_name
                 ORDER BY checked_at DESC LIMIT 1) latest_visible,
               (SELECT checked_at FROM competitor_star_history sub
                 WHERE sub.competitor_name = csh.competitor_name
                 ORDER BY checked_at DESC LIMIT 1) latest_checked
          FROM competitor_star_history csh
         GROUP BY competitor_name
        """
    ).fetchall()
    print('=== 별점 가시성 상태 (최신) ===')
    if not rows:
        print('스냅샷 없음. python scripts/track_star_visibility.py 로 첫 수집.')
        return 0
    for name, rating, visible, checked in rows:
        rate_str = f'{rating:.1f}점' if rating is not None else '-'
        vis_str = '공개' if visible else '비공개'
        print(f'  {name:<28} {rate_str:>6}  ({vis_str})  {checked}')
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true', help='최신 스냅샷만 출력')
    parser.add_argument('--diff-only', action='store_true', help='변화 발생 항목만')
    args = parser.parse_args()

    if args.status:
        return show_status()

    competitors = load_competitors()
    if not competitors:
        print('targets.json에 priority High/Critical/Medium 경쟁사가 없음.')
        return 0

    print(f'경쟁사 {len(competitors)}곳 별점·가시성 체크 중...')
    print('실제 SERP 수집은 scraper_naver_place.py 분리 실행 필요. 이 스크립트는 결과 적재만 담당.')
    print()
    print('--- 통합 흐름 권장 ---')
    print('1. python scrapers/scraper_naver_place.py --skip-reviews   (모바일/데스크탑 순위·별점 갱신)')
    print('2. python scripts/track_star_visibility.py --status        (현재 상태 확인)')
    print('3. competitor_star_history 테이블이 자동 채워지도록 scraper_naver_place.py에서 INSERT 필요')
    print()
    print('수동 적재 모드: 이 스크립트가 직접 데이터 입력 받음.')

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec='seconds')
    transitions = []

    for c in competitors:
        # rank_history에서 직전 별점/리뷰수 가져오기 (이미 라운드 2 C4에서 추가)
        recent = cur.execute(
            """
            SELECT star_rating, review_count
              FROM rank_history
             WHERE keyword LIKE ?
               AND star_rating IS NOT NULL
             ORDER BY COALESCE(date, checked_at) DESC LIMIT 1
            """,
            (f"%{c['name'][:6]}%",),
        ).fetchone()

        if recent is None:
            curr_rating, curr_reviews = None, None
        else:
            curr_rating, curr_reviews = recent

        curr = {
            'star_rating': curr_rating,
            'star_visible': 1 if curr_rating is not None else 0,
            'review_count': curr_reviews,
        }
        prev = latest_snapshot(cur, c['name'])
        event = detect_transition(prev, curr)

        cur.execute(
            """
            INSERT OR IGNORE INTO competitor_star_history
                (competitor_name, star_rating, star_visible, review_count, checked_at, transition_event)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (c['name'], curr['star_rating'], curr['star_visible'], curr['review_count'], now, event),
        )
        if event and event != 'first_seen':
            transitions.append((c['name'], event, curr_rating))

    conn.commit()
    conn.close()

    print()
    if transitions:
        print(f'!! 변화 감지: {len(transitions)}건')
        for name, event, rating in transitions:
            print(f'  - {name}: {event} (현재 {rating})')
    else:
        if not args.diff_only:
            print('변화 없음.')

    return 0


if __name__ == '__main__':
    sys.exit(main())
