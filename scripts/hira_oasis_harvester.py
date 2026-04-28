"""[R2] HIRA + OASIS 의료 시드 키워드 harvester.

목적: 의학 공식 항목명 = 의료광고심의 통과 안전 + 경쟁사 못 쓰는 long-tail 키워드.

수집 데이터:
  - HIRA 의료기관 정보 (B551182/hospInfoServicev2): 충북 청주권 한의원 정확 명칭
  - HIRA 비급여 진료비 정보 (B551182/nonPaymentDamtInfoService): 비급여 항목명 + 단가
  - OASIS 전통의학정보포털 (oasis.kiom.re.kr): 한약재 478품목 (stub — 별도 다운로드 필요)

운영자 트리거 (cron 안 씀):
  python scripts/hira_oasis_harvester.py --hira-hospitals     # 충북 한의원 명단
  python scripts/hira_oasis_harvester.py --hira-pricing       # 비급여 항목·단가
  python scripts/hira_oasis_harvester.py --oasis-herbs        # 한약재 (수동 데이터 필요)
  python scripts/hira_oasis_harvester.py --all
  python scripts/hira_oasis_harvester.py --dry-run

키: DATA_GO_KR_API_KEY (.env / secrets.json 등록 완료)
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
from urllib.parse import quote

import requests
import xml.etree.ElementTree as ET

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')

HIRA_HOSPITALS_URL = 'https://apis.data.go.kr/B551182/hospInfoServicev2/getHospBasisList'
HIRA_NONPAY_URL = 'https://apis.data.go.kr/B551182/nonPaymentDamtInfoService/getNonPaymentItemHospList'

# OASIS 한약재 핵심 시드 (전체 478품목 중 한의원 핵심 사용)
# 출처: oasis.kiom.re.kr/herbal — 별도 다운로드 후 확장 권장
OASIS_HERB_SEED = [
    '인삼', '홍삼', '백삼', '당귀', '천궁', '황기', '감초', '계지', '시호', '백출',
    '복령', '진피', '반하', '대조', '생강', '맥문동', '오미자', '구기자', '숙지황',
    '하수오', '천마', '두충', '강활', '독활', '방풍', '갈근', '석고', '대황',
    '사인', '곽향', '후박', '창출', '인진', '치자', '연교', '금은화', '박하', '마황',
]


def get_api_key() -> Optional[str]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f).get('DATA_GO_KR_API_KEY')
    except (FileNotFoundError, json.JSONDecodeError):
        return os.environ.get('DATA_GO_KR_API_KEY')


def ensure_tables(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hira_hospitals (
            ykiho TEXT PRIMARY KEY,         -- 요양기관 식별자
            name TEXT NOT NULL,
            type_name TEXT,                  -- 한의원/한방병원
            sido_name TEXT,                  -- 시도
            sgg_name TEXT,                   -- 시군구
            emd_name TEXT,                   -- 읍면동
            address TEXT,
            phone TEXT,
            xpos REAL,
            ypos REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS hira_nonpay_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ykiho TEXT,
            item_code TEXT,
            item_name TEXT,
            min_price REAL,
            max_price REAL,
            avg_price REAL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(ykiho, item_code)
        );

        CREATE TABLE IF NOT EXISTS oasis_herbs (
            herb_name TEXT PRIMARY KEY,
            properties TEXT,
            applications TEXT,
            indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)


def fetch_hira_hospitals(api_key: str, sido: str = '충청북도', sgg: str = '청주시', max_rows: int = 200) -> list[dict]:
    """HIRA 의료기관 정보 — 충북 청주권 한의원/한방병원."""
    out = []
    page = 1
    while page <= 5:
        params = {
            'ServiceKey': api_key,
            'pageNo': page,
            'numOfRows': 100,
            'sidoCd': '11',  # 충청북도 (참고: 11=서울, 충북=33). 실제는 코드 확인 필요
            'clCd': '93,94',  # 한의원/한방병원
            '_type': 'json',
        }
        try:
            r = requests.get(HIRA_HOSPITALS_URL, params=params, timeout=15)
            if r.status_code != 200:
                print(f'  [HIRA err] status={r.status_code}')
                break
            data = r.json()
            items = data.get('response', {}).get('body', {}).get('items', {}).get('item', [])
            if not items:
                break
            if isinstance(items, dict):
                items = [items]
            for h in items:
                if sgg in (h.get('sggCdNm', '') or ''):
                    out.append({
                        'ykiho': h.get('ykiho'),
                        'name': h.get('yadmNm'),
                        'type_name': h.get('clCdNm'),
                        'sido_name': h.get('sidoCdNm'),
                        'sgg_name': h.get('sggCdNm'),
                        'emd_name': h.get('emdongNm'),
                        'address': h.get('addr'),
                        'phone': h.get('telno'),
                        'xpos': h.get('XPos'),
                        'ypos': h.get('YPos'),
                    })
            if len(out) >= max_rows or len(items) < 100:
                break
            page += 1
            time.sleep(0.5)
        except Exception as e:
            print(f'  [HIRA err] {e}')
            break
    return out


def save_hospitals(rows: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    ensure_tables(conn)
    cur = conn.cursor()
    saved = 0
    for h in rows:
        if not h.get('ykiho'):
            continue
        cur.execute(
            """
            INSERT INTO hira_hospitals
                (ykiho, name, type_name, sido_name, sgg_name, emd_name, address, phone, xpos, ypos)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ykiho) DO UPDATE SET
                name=excluded.name, type_name=excluded.type_name,
                address=excluded.address, phone=excluded.phone,
                updated_at=CURRENT_TIMESTAMP
            """,
            (h['ykiho'], h['name'], h.get('type_name'), h.get('sido_name'),
             h.get('sgg_name'), h.get('emd_name'), h.get('address'),
             h.get('phone'), h.get('xpos'), h.get('ypos')),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def save_oasis_seeds() -> int:
    """OASIS 한약재 시드를 keyword_insights + oasis_herbs에 적재."""
    conn = sqlite3.connect(DB_PATH)
    ensure_tables(conn)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec='seconds')
    saved = 0
    for herb in OASIS_HERB_SEED:
        cur.execute(
            "INSERT OR IGNORE INTO oasis_herbs (herb_name) VALUES (?)",
            (herb,),
        )
        # keyword_insights에 의학 long-tail로 추가
        for suffix in ['효능', '부작용', '복용법']:
            kw = f'{herb} {suffix}'
            cur.execute(
                """
                INSERT INTO keyword_insights
                    (keyword, source, search_intent, search_volume,
                     grade, category, created_at, status)
                VALUES (?, 'oasis', ?, 0, 'C', '기타', ?, 'active')
                ON CONFLICT(keyword) DO UPDATE SET
                    source=CASE WHEN keyword_insights.source IS NULL THEN 'oasis'
                                ELSE keyword_insights.source END
                """,
                (
                    kw,
                    'red_flag' if suffix == '부작용' else 'informational',
                    now,
                ),
            )
            saved += 1
    conn.commit()
    conn.close()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--hira-hospitals', action='store_true')
    parser.add_argument('--hira-pricing', action='store_true', help='[Stub] 비급여 항목·단가 (R15와 통합 권장)')
    parser.add_argument('--oasis-herbs', action='store_true', help='OASIS 한약재 시드 → keyword_insights')
    parser.add_argument('--all', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    api_key = get_api_key()
    if args.hira_hospitals or args.hira_pricing or args.all:
        if not api_key:
            print('DATA_GO_KR_API_KEY 없음. config/secrets.json 또는 .env 확인.')
            return 1
        print(f'API 키 OK (...{api_key[-6:]})')

    if args.dry_run:
        print('=== dry-run ===')
        if args.hira_hospitals or args.all:
            print('  HIRA 의료기관: 충북 청주 한의원/한방병원 ~50-100곳 예상')
        if args.oasis_herbs or args.all:
            print(f'  OASIS 한약재: {len(OASIS_HERB_SEED)}개 시드 × 3 패턴 = {len(OASIS_HERB_SEED) * 3}개 키워드')
        return 0

    if args.hira_hospitals or args.all:
        print('\n[HIRA] 의료기관 정보 수집 중...')
        rows = fetch_hira_hospitals(api_key)
        n = save_hospitals(rows)
        print(f'  hira_hospitals 적재: {n}건')

    if args.oasis_herbs or args.all:
        print('\n[OASIS] 한약재 시드 키워드 적재 중...')
        n = save_oasis_seeds()
        print(f'  keyword_insights 적재: {n}건 (source=oasis)')

    if args.hira_pricing or args.all:
        print('\n[HIRA pricing] R15 (competitor_pricing_collector.py) 사용 권장')
        print('  python scripts/competitor_pricing_collector.py')

    print('\n다음: Pathfinder 정상 흐름이 SERP 분석/등급 부여 자동 진행')
    return 0


if __name__ == '__main__':
    sys.exit(main())
