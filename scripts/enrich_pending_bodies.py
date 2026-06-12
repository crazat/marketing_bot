"""pending 큐의 KIN/blog/공개 cafe 글 본문 enrichment + 최종 게이트 재검사.

문제: Naver Search API snippet(~150자)만으로 게이트/AI가 판정해, 본문이 광고인
blog 글과 답변 상태를 알 수 없는 KIN 질문이 pending 큐에 남는다.
해결: 공개 표면(KIN/blog)을 HTTP로 재방문해 본문을 복원하고,
  - 게이트 재탈락 행은 filtered_* 상태로 영속화 (KIN은 질문 세그먼트만 게이트)
  - 생존 행은 보강된 본문을 content_preview에 저장 (댓글 생성 품질 개선)

운영자가 명시적으로 실행 (cron 안 씀):
  python scripts/enrich_pending_bodies.py --dry-run     # 대상만 출력
  python scripts/enrich_pending_bodies.py               # 기본: 14일 내 pending, 최대 200건
  python scripts/enrich_pending_bodies.py --days 30 --limit 400

cafe는 공개 카페만 article API로 취득(멤버 전용 401 → skip).
로그인 필요한 카페는 scripts/enrich_cafe_bodies.py(Selenium) 사용.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def backup_db(db_path: str) -> str:
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_path = os.path.join(
        os.path.dirname(db_path), 'backups', f'marketing_data.db.backup_pre_enrich_{stamp}'
    )
    os.makedirs(os.path.dirname(backup_path), exist_ok=True)
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(backup_path)
    with dst:
        src.backup(dst)
    src.close()
    dst.close()
    return backup_path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--days', type=int, default=14, help='discovered_at 윈도우 (기본 14일)')
    parser.add_argument('--limit', type=int, default=200, help='최대 fetch 수 (기본 200)')
    parser.add_argument('--min-preview', type=int, default=300,
                        help='이 길이 미만 content_preview만 대상 (기본 300)')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--no-backup', action='store_true', help='백업 생략 (재실행 시)')
    args = parser.parse_args()

    import viral_hunter
    from viral_hunter import ViralTarget

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT platform, url, title, content_preview, category, matched_keywords,
               score_breakdown
          FROM viral_targets
         WHERE comment_status = 'pending'
           AND platform IN ('kin', 'blog', 'cafe', 'naver_cafe')
           AND discovered_at >= datetime('now', ?)
           AND LENGTH(COALESCE(content_preview, '')) < ?
           AND url LIKE 'http%'
         ORDER BY priority_score DESC
         LIMIT ?
        """,
        (f'-{int(args.days)} days', int(args.min_preview), int(args.limit)),
    ).fetchall()
    conn.close()

    if not rows:
        print('대상 없음 (pending KIN/blog 중 snippet-only 행이 없습니다).')
        return 0

    print(f'대상: {len(rows)}건 (days={args.days}, preview<{args.min_preview}자)')
    if args.dry_run:
        for r in rows[:10]:
            print(f"  [{r['platform']}] {(r['title'] or '')[:50]}")
        if len(rows) > 10:
            print(f'  ... 외 {len(rows) - 10}건')
        print('\ndry-run. 실제 실행은 --dry-run 빼고.')
        return 0

    if not args.no_backup:
        backup_path = backup_db(DB_PATH)
        print(f'백업 생성: {backup_path}')

    # 게이트는 pathfinder 축/렌즈 lineage(score_breakdown)를 사용한다 — 누락하면
    # 약화된 컨텍스트로 평가되고, reject 영속화가 원본 lineage를 덮어쓴다.
    targets = []
    for r in rows:
        target = ViralTarget(
            platform=r['platform'],
            url=r['url'],
            title=r['title'] or '',
            content_preview=r['content_preview'] or '',
            category=r['category'] or '기타',
            matched_keywords=json.loads(r['matched_keywords'] or '[]'),
        )
        try:
            target.score_breakdown = json.loads(r['score_breakdown'] or '{}') or {}
        except (TypeError, ValueError):
            target.score_breakdown = {}
        targets.append(target)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    from db.database import DatabaseManager
    hunter.db = DatabaseManager()

    kept, stats = hunter._enrich_and_regate_ai_targets(
        targets,
        max_fetch=int(args.limit),
        time_budget_sec=600.0,
    )
    print(
        f"fetch {stats['fetched']}건 → 보강 {stats['enriched']}건, "
        f"게이트 재탈락 {stats['regate_rejected']}건"
    )

    # 생존 + 보강된 행은 본문을 직접 UPDATE (scan_count 등 재발견 부수효과 없이)
    conn = sqlite3.connect(DB_PATH)
    updated = 0
    for target in kept:
        breakdown = target.score_breakdown or {}
        if not breakdown.get('body_enriched'):
            continue
        cur = conn.execute(
            """
            UPDATE viral_targets
               SET content_preview = ?,
                   score_breakdown = ?
             WHERE url = ? AND comment_status = 'pending'
            """,
            (
                target.content_preview,
                json.dumps(breakdown, ensure_ascii=False),
                target.url,
            ),
        )
        updated += cur.rowcount
    conn.commit()
    conn.close()
    print(f'생존 행 본문 저장: {updated}건')

    print('\n완료. 직원 큐에서 light한 snippet 대신 실제 본문이 보입니다.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
