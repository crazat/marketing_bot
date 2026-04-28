"""[Q3] 시간 지난 hot 카페 글 재방문 — 댓글/뷰 변화 감지.

목적: viral_targets의 99.99%가 1회 스캔 후 멈춤. 댓글이 활발히 달리며 hot 되는 시점을 놓침.
운영자가 명시적으로 트리거 (cron 안 씀):
  python scripts/rescan_hot_targets.py                            # 7일 전 priority>=100 cafe
  python scripts/rescan_hot_targets.py --age-hours 72 --top 20    # 3일 전 top 20
  python scripts/rescan_hot_targets.py --dry-run

기준:
  - platform IN ('cafe', 'naver_cafe')
  - comment_status='pending' (아직 처리 안 한 글)
  - priority_score >= --min-score
  - last_scanned_at < now - --age-hours
  - 직전 스캔보다 priority/comment 변화하면 priority_score 재계산 권장 표시

비교 metric: content_hash 변화, comment_count 증가, view_count 증가.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import hashlib
from datetime import datetime, timedelta

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--age-hours', type=int, default=168, help='이 시간 이상 된 글만 (기본 168 = 7일)')
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--min-score', type=float, default=100.0)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    cutoff = (datetime.now() - timedelta(hours=args.age_hours)).strftime('%Y-%m-%d %H:%M:%S')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, url, title, priority_score, scan_count, comment_count, view_count,
               last_scanned_at, content_hash
          FROM viral_targets
         WHERE platform IN ('cafe', 'naver_cafe')
           AND comment_status = 'pending'
           AND priority_score >= ?
           AND (last_scanned_at IS NULL OR last_scanned_at < ?)
           AND url LIKE 'http%'
         ORDER BY priority_score DESC
         LIMIT ?
        """,
        (args.min_score, cutoff, args.top),
    ).fetchall()

    if not rows:
        print(f'대상 없음 (priority>={args.min_score}, age>{args.age_hours}h)')
        return 0

    print(f'재방문 대상: {len(rows)}건')
    print(f'기준: priority>={args.min_score}, last_scanned_at < {cutoff}')
    print()
    for r in rows[:5]:
        last = r['last_scanned_at'] or '미스캔'
        print(
            f"  [{r['priority_score']:.0f}] {(r['title'] or '')[:36]:<36}  "
            f"last={last[:16]}  댓글={r['comment_count'] or 0} 뷰={r['view_count'] or 0}"
        )
    if len(rows) > 5:
        print(f"  ... 외 {len(rows) - 5}건")

    if args.dry_run:
        print('\ndry-run. 실제 fetch는 --dry-run 빼고 실행.')
        return 0

    print()
    print('Selenium driver 초기화 중...')
    try:
        from scrapers.cafe_spy import CafeSpy
    except ImportError as e:
        print(f'cafe_spy import 실패: {e}')
        return 1

    spy = CafeSpy()
    if not getattr(spy, 'driver', None):
        try:
            spy._init_driver()
        except Exception as e:
            print(f'driver 초기화 실패: {e}')
            return 1

    found_leads = [
        {'title': r['title'] or '', 'link': r['url'], 'cafe_url': r['url']}
        for r in rows
    ]

    try:
        detailed = spy._deep_read_leads(found_leads)
    except Exception as e:
        print(f'_deep_read_leads 실행 실패: {e}')
        try:
            spy.driver.quit()
        except Exception:
            pass
        return 1

    now = datetime.now().isoformat(timespec='seconds')
    by_link = {r['url']: r for r in rows}
    changed = 0
    unchanged = 0
    failed = 0

    for item in detailed:
        link = item.get('link', '')
        body = (item.get('body') or '').strip()
        original = by_link.get(link)
        if not original:
            continue
        if not body or len(body) < 50:
            failed += 1
            continue
        new_hash = hashlib.md5(body.encode('utf-8')).hexdigest()[:16]
        old_hash = original['content_hash']

        # 변화 감지: hash 다르거나, 본문 길이 크게 늘어남
        is_changed = (old_hash and new_hash != old_hash) or (
            not old_hash and len(body) > 200
        )
        if is_changed:
            changed += 1
            cur.execute(
                """
                UPDATE viral_targets
                   SET content = ?,
                       content_preview = ?,
                       content_hash = ?,
                       last_scanned_at = ?,
                       scan_count = COALESCE(scan_count, 0) + 1
                 WHERE id = ?
                """,
                (body[:5000], body[:300], new_hash, now, original['id']),
            )
            print(f"  CHANGED [{original['priority_score']:.0f}] {(original['title'] or '')[:40]}")
        else:
            unchanged += 1
            cur.execute(
                """
                UPDATE viral_targets
                   SET last_scanned_at = ?,
                       scan_count = COALESCE(scan_count, 0) + 1
                 WHERE id = ?
                """,
                (now, original['id']),
            )

    conn.commit()
    conn.close()

    try:
        spy.driver.quit()
    except Exception:
        pass

    print()
    print('=' * 60)
    print(f'재방문 완료: 변화 {changed} | 동일 {unchanged} | 실패 {failed}')
    if changed:
        print(f'\n변화한 {changed}건은 AI 분류 재실행 권장:')
        print('  python scripts/ai_ad_classify_submit.py --limit ' + str(changed))

    return 0


if __name__ == '__main__':
    sys.exit(main())
