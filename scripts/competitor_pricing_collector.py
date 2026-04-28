"""[R15] 경쟁사 비급여 단가 수집기 (data.go.kr 심평원 비급여 진료비 API).

배경: 2026-6-12 비급여 진료비 공개 의무 마감. 운영 중인 모든 의료기관 단가 + 고지 근거 자료
       → 심평원 누리집·앱 공개. R14 단가 일치성 게이트의 데이터 공급원.

전략:
  1. R2 hira_oasis_harvester.py로 충북 청주권 한의원 ykiho(요양기관 식별자) 확보
  2. 각 기관별 비급여 항목·단가 fetch → hira_nonpay_items 적재
  3. R14의 verify_price_consistency() 자동 활용

운영자 트리거 (cron 안 씀):
  python scripts/competitor_pricing_collector.py --status        # 적재 현황
  python scripts/competitor_pricing_collector.py                  # targets.json 경쟁사 단가 수집
  python scripts/competitor_pricing_collector.py --hospital ykiho1,ykiho2
  python scripts/competitor_pricing_collector.py --dry-run

키: DATA_GO_KR_API_KEY (.env / secrets.json 등록 완료)
API 문서: https://www.data.go.kr/data/15001699/openapi.do
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from typing import Optional

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')

NONPAY_URL = 'https://apis.data.go.kr/B551182/nonPaymentDamtInfoService/getNonPaymentItemHospList'


def get_api_key() -> Optional[str]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('DATA_GO_KR_API_KEY')
    except (FileNotFoundError, json.JSONDecodeError):
        return os.environ.get('DATA_GO_KR_API_KEY')


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hira_nonpay_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ykiho TEXT,
            hospital_name TEXT,
            item_code TEXT,
            item_name TEXT,
            min_price REAL,
            max_price REAL,
            avg_price REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ykiho, item_code)
        );
        CREATE INDEX IF NOT EXISTS idx_nonpay_item ON hira_nonpay_items(item_name);
        CREATE INDEX IF NOT EXISTS idx_nonpay_ykiho ON hira_nonpay_items(ykiho);
    """)


def fetch_nonpay_items(api_key: str, ykiho: str) -> list[dict]:
    """기관별 비급여 항목·단가."""
    out = []
    page = 1
    while page <= 10:
        params = {
            'ServiceKey': api_key,
            'pageNo': page,
            'numOfRows': 100,
            'ykiho': ykiho,
            '_type': 'json',
        }
        try:
            r = requests.get(NONPAY_URL, params=params, timeout=15)
            if r.status_code != 200:
                print(f'  [API err] status={r.status_code}')
                break
            data = r.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if not items:
                break
            if isinstance(items, dict):
                items = [items]
            for it in items:
                out.append({
                    'item_code': it.get('itemCd'),
                    'item_name': it.get('itemNm'),
                    'min_price': float(it.get('curAmtMin', 0) or 0),
                    'max_price': float(it.get('curAmtMax', 0) or 0),
                    'avg_price': float(it.get('curAmt', 0) or 0),
                })
            if len(items) < 100:
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f'  [API err] {e}')
            break
    return out


def get_target_hospitals(conn: sqlite3.Connection) -> list[dict]:
    """hira_hospitals 테이블에서 충북 청주권 + targets.json 매칭 한의원."""
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hira_hospitals'")
    if not cur.fetchone():
        return []
    rows = cur.execute(
        """
        SELECT ykiho, name FROM hira_hospitals
         WHERE sgg_name LIKE '%청주%' OR sido_name LIKE '%충%'
        """
    ).fetchall()
    return [{'ykiho': r[0], 'name': r[1]} for r in rows]


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    cur = conn.cursor()
    n_rows = cur.execute("SELECT COUNT(*) FROM hira_nonpay_items").fetchone()[0]
    n_hosp = cur.execute("SELECT COUNT(DISTINCT ykiho) FROM hira_nonpay_items").fetchone()[0]
    last = cur.execute("SELECT MAX(updated_at) FROM hira_nonpay_items").fetchone()[0]
    print('=== 비급여 단가 수집 현황 ===')
    print(f'  hira_nonpay_items 행수: {n_rows:,}')
    print(f'  수집 기관 수: {n_hosp}')
    print(f'  최종 갱신: {last or "-"}')
    if n_rows > 0:
        top = cur.execute(
            """
            SELECT item_name, COUNT(*) c, AVG(avg_price) avg
              FROM hira_nonpay_items
             WHERE item_name IS NOT NULL
             GROUP BY item_name
             ORDER BY c DESC LIMIT 10
            """
        ).fetchall()
        print('\n  Top 10 항목 (수집 빈도):')
        for n, c, avg in top:
            print(f'    {n:<30} {c}건 평균 {round(avg or 0):,}원')
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--hospital', help='쉼표 구분 ykiho 직접 지정')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.status:
        return show_status()

    api_key = get_api_key()
    if not api_key:
        print('DATA_GO_KR_API_KEY 없음. .env / secrets.json 확인.')
        return 1

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)

    if args.hospital:
        hospitals = [{'ykiho': y.strip(), 'name': y.strip()} for y in args.hospital.split(',')]
    else:
        hospitals = get_target_hospitals(conn)
        if not hospitals:
            print('hira_hospitals 데이터 없음. R2 hira_oasis_harvester.py --hira-hospitals 먼저 실행.')
            return 1

    print(f'대상 기관 {len(hospitals)}곳 비급여 단가 수집 시작')

    if args.dry_run:
        for h in hospitals[:5]:
            print(f"  - {h['name']} ({h['ykiho']})")
        print(f'  ... 외 {max(0, len(hospitals) - 5)}곳')
        return 0

    cur = conn.cursor()
    total_items = 0
    for h in hospitals:
        items = fetch_nonpay_items(api_key, h['ykiho'])
        for it in items:
            cur.execute(
                """
                INSERT INTO hira_nonpay_items
                    (ykiho, hospital_name, item_code, item_name, min_price, max_price, avg_price)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ykiho, item_code) DO UPDATE SET
                    min_price=excluded.min_price,
                    max_price=excluded.max_price,
                    avg_price=excluded.avg_price,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (h['ykiho'], h['name'], it['item_code'], it['item_name'],
                 it['min_price'], it['max_price'], it['avg_price']),
            )
            total_items += 1
        conn.commit()
        print(f'  {h["name"]:<30} {len(items)}건 적재')
        time.sleep(0.5)

    conn.close()
    print(f'\n총 {total_items}건 비급여 단가 수집 완료')
    print('이제 R14 verify_price_consistency() 자동 작동 (콘텐츠 내 가격 ±10% 이내 자동 대조)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
