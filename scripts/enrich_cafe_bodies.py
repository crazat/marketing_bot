"""[Q1] viral_targets 카페 글 본문 enrichment.

문제: Naver Search API의 description은 300자에서 잘려 본문이 사실상 비어있음 (HTML strip 후 <50자 다수).
해결: priority_score 높은 cafe pending 글에 한해 Selenium으로 재방문하여 본문 복원.

운영자가 명시적으로 실행 (cron 안 씀):
  python scripts/enrich_cafe_bodies.py                      # 기본: top 30, score>=80
  python scripts/enrich_cafe_bodies.py --top 100            # top 100
  python scripts/enrich_cafe_bodies.py --min-score 100      # priority>=100 (최대 --top 건)
  python scripts/enrich_cafe_bodies.py --dry-run            # 대상만 출력

cafe_spy의 _deep_read_leads 재사용. 로그인 필요한 카페는 cafe_spy 로그인 로직 사용.
"""
from __future__ import annotations

import argparse
import os
import sys
import sqlite3
import time
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--top', type=int, default=30, help='상위 N건 (priority_score desc)')
    parser.add_argument('--min-score', type=float, default=80.0, help='최소 priority_score')
    parser.add_argument('--max-content', type=int, default=200,
                        help='이 길이 미만 content_preview만 enrich (이미 풍부한 글 재방문 안 함)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    rows = cur.execute(
        """
        SELECT id, url, title, content_preview, priority_score
          FROM viral_targets
         WHERE platform IN ('cafe', 'naver_cafe')
           AND comment_status = 'pending'
           AND priority_score >= ?
           AND (LENGTH(COALESCE(content_preview, '')) < ? OR content IS NULL OR content = '')
           AND url LIKE 'http%'
         ORDER BY priority_score DESC
         LIMIT ?
        """,
        (args.min_score, args.max_content, args.top),
    ).fetchall()

    if not rows:
        print('대상 없음 (score 미달 또는 이미 본문 풍부).')
        return 0

    print(f'대상: {len(rows)}건 (min_score={args.min_score}, content<{args.max_content}자)')
    for r in rows[:5]:
        prev_len = len(r['content_preview'] or '')
        print(f"  [{r['priority_score']:.0f}] {(r['title'] or '')[:40]:<40}  preview={prev_len}자")
    if len(rows) > 5:
        print(f"  ... 외 {len(rows) - 5}건")

    if args.dry_run:
        print('\ndry-run. 실제 fetch는 --dry-run 빼고 실행.')
        return 0

    print()
    print('Selenium driver 초기화 중... (cafe_spy CafeSpy 사용)')
    try:
        from scrapers.cafe_spy import CafeSpy
    except ImportError as e:
        print(f'cafe_spy import 실패: {e}')
        return 1

    spy = CafeSpy()
    if not getattr(spy, 'driver', None):
        # 일부 CafeSpy 구현은 lazy init
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

    updated = 0
    too_short = 0
    now = datetime.now().isoformat(timespec='seconds')
    id_by_link = {r['url']: r['id'] for r in rows}

    for item in detailed:
        body = (item.get('body') or '').strip()
        link = item.get('link', '')
        tid = id_by_link.get(link)
        if not tid:
            continue
        if len(body) < 50:
            too_short += 1
            continue
        # 새 본문이 더 풍부하면 덮어쓰기 (최대 5000자)
        cur.execute(
            """
            UPDATE viral_targets
               SET content = ?,
                   content_preview = ?,
                   last_scanned_at = ?,
                   scan_count = COALESCE(scan_count, 0) + 1
             WHERE id = ?
            """,
            (body[:5000], body[:300], now, tid),
        )
        updated += 1

    conn.commit()
    conn.close()

    try:
        spy.driver.quit()
    except Exception:
        pass

    print()
    print(f'본문 업데이트: {updated}/{len(rows)}건')
    if too_short:
        print(f'본문 너무 짧음 (<50자): {too_short}건 — 회원전용/삭제글 가능성')

    print()
    print('다음 단계: AI 분류 재실행 권장 — python scripts/ai_ad_classify_submit.py --limit 200')
    return 0


if __name__ == '__main__':
    sys.exit(main())
