"""pending 큐 TTL 만료 정리 — 댓글 적시성 윈도우가 지난 행을 만료 상태로 전환.

문제: pending에는 TTL이 없어 직원이 처리하지 않은 행이 영구 잔류한다.
라이브 감사(2026-06-13): pending 4,002건 중 3,484건(87%)이 31~90일 적체,
그중 2,510건은 2026-04 분류 개선 이전의 '기타' 레거시. 댓글 윈도우가 지난
글에 작업하면 직원 시간 낭비 + 뒷북 댓글로 스팸처럼 보이는 리스크만 남는다.

해결: viral_hunter.expire_stale_pending_targets() — 플랫폼별 TTL(cafe 30d /
blog·kin 45d) 초과 pending을 filtered_out_stale_window로 만료. lineage는
score_breakdown에 보존, rescue 레인(raw_backlog만 소비)과 루프 없음.

운영자가 명시적으로 실행 (cron 안 씀):
  python scripts/expire_stale_pending.py --dry-run   # 집계만 출력
  python scripts/expire_stale_pending.py             # 백업 후 실제 만료
"""
from __future__ import annotations

import argparse
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
        os.path.dirname(db_path), 'backups',
        f'marketing_data.db.backup_pre_pending_expiry_{stamp}'
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
    parser.add_argument('--dry-run', action='store_true', help='만료 없이 집계만 출력')
    parser.add_argument('--no-backup', action='store_true', help='백업 생략 (재실행 시)')
    args = parser.parse_args()

    from viral_hunter import (
        expire_stale_pending_targets,
        PENDING_TTL_DAYS,
        PENDING_TTL_DEFAULT_DAYS,
        PENDING_POST_AGE_TTL_DAYS,
    )

    ttl_desc = ", ".join(f"{p} {d}d" for p, d in sorted(PENDING_TTL_DAYS.items()))
    print(f'queue-dwell TTL: {ttl_desc} (기본 {PENDING_TTL_DEFAULT_DAYS}d) | post-age TTL: {PENDING_POST_AGE_TTL_DAYS}d')

    if not args.dry_run and not args.no_backup:
        backup_path = backup_db(DB_PATH)
        print(f'백업 생성: {backup_path}')

    stats = expire_stale_pending_targets(DB_PATH, dry_run=args.dry_run)
    mode = '[dry-run] ' if args.dry_run else ''
    print(
        f"{mode}검사 {stats['checked']}건 → 만료 {stats['expired']}건 "
        f"(체류초과 {stats['expired_dwell']}, 게시물노후 {stats['expired_post_age']})"
    )
    if stats['by_platform']:
        print('  플랫폼별:', ', '.join(f'{p} {n}' for p, n in sorted(stats['by_platform'].items())))
    if stats['by_category']:
        top = sorted(stats['by_category'].items(), key=lambda kv: -kv[1])[:10]
        print('  카테고리 top:', ', '.join(f'{c} {n}' for c, n in top))
    if args.dry_run:
        print('\ndry-run. 실제 실행은 --dry-run 빼고.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
