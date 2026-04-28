"""[Q9] 네이버 광고 키워드 데이터 수동 갱신 — 사용자 트리거.

목적: naver_ad_keyword_data 테이블의 검색량/경쟁 강도가 40일 이상 묵으면
      Pathfinder 등급 산정의 search_volume=0 garbage가 늘어남.
      운영자가 명시적으로 갱신.

웹 UI에서 트리거 가능:
  POST http://localhost:8000/api/hud/mission/naver_ad_keywords

CLI에서 직접 트리거:
  python scripts/refresh_ad_data.py            # 기본 키워드 풀
  python scripts/refresh_ad_data.py --status   # 마지막 갱신 일자만 확인

cron으로 돌리지 말 것 (사용자 정책).
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sqlite3
import sys
from datetime import datetime

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    row = cur.execute(
        "SELECT COUNT(*), MAX(created_at) FROM naver_ad_keyword_data"
    ).fetchone()
    total, last = row if row else (0, None)
    print('=== 네이버 광고 데이터 상태 ===')
    print(f'총 행수: {total:,}')
    print(f'최종 갱신: {last or "(없음)"}')
    if last:
        try:
            last_dt = datetime.fromisoformat(last.replace('Z', ''))
            age_days = (datetime.now() - last_dt).days
            stale = ' (40일 이상)' if age_days >= 40 else ''
            print(f'경과: {age_days}일{stale}')
        except Exception:
            pass
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true', help='상태만 출력')
    args = parser.parse_args()

    if args.status:
        return show_status()

    print('네이버 광고 키워드 데이터 갱신 시작...')
    print('대상 스크립트: scrapers/naver_ad_keyword_collector.py')
    print()

    cmd = [sys.executable, 'scrapers/naver_ad_keyword_collector.py']
    proc = subprocess.run(cmd, cwd=ROOT_DIR)

    if proc.returncode != 0:
        print(f'갱신 실패 (exit code: {proc.returncode})')
        return proc.returncode

    print()
    show_status()
    return 0


if __name__ == '__main__':
    sys.exit(main())
