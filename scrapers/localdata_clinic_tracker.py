"""[External Signals R3-1] localdata.go.kr 한의원 인허가 추적 (행정안전부 LOCALDATA)

배경: 청주시 한의원 신규 개원·폐업·이전·간판 변경을 행정안전부 공공데이터로 즉시 감지.
       기존 `competitor_change_detector.py`가 못 잡는 "이름 다른 신규 한의원 개원" 신호 보강.
       2026-04 시점 청주시 한의원 약 250-280곳, 월 평균 신규 개원 1-2건 + 폐업 1-2건.

API: http://www.localdata.go.kr/devcenter/apiGuide.do
  - 데이터: localdata.go.kr open API (행정안전부 LOCALDATA)
  - 인증: authKey (별도 발급, secrets.json::LOCALDATA_AUTH_KEY 또는 DATA_GO_KR_API_KEY 폴백)
  - 한의원 opnSvcId: 01_03_03_P (한의원·한방의원 — 보건의료시설 카테고리)

운영자 트리거 (cron 안 씀):
  python scrapers/localdata_clinic_tracker.py --status
  python scrapers/localdata_clinic_tracker.py --region "청주" --service-type 한의원
  python scrapers/localdata_clinic_tracker.py --dry-run
  python scrapers/localdata_clinic_tracker.py --since 2026-04-01

테이블: clinic_lifecycle_events (db_init.py에서 자동 생성)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

try:
    from backend_utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')
    logger = logging.getLogger(__name__)

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')

# LOCALDATA OpenAPI base
LOCALDATA_URL = "http://www.localdata.go.kr/platform/rest/TO0/openDataApi"
# 한의원 (보건의료) 서비스 ID
SERVICE_TYPE_MAP = {
    '한의원': '01_03_03_P',
    '한방병원': '01_03_03_P',  # 동일 카테고리
    '의원': '01_03_02_P',
    '약국': '01_03_05_P',
}


def _load_secret(key: str) -> Optional[str]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get(key)
    except Exception:
        return os.environ.get(key)


def _get_auth_key() -> Optional[str]:
    """LOCALDATA_AUTH_KEY 우선, 없으면 DATA_GO_KR_API_KEY 폴백."""
    return _load_secret('LOCALDATA_AUTH_KEY') or _load_secret('DATA_GO_KR_API_KEY')


def fetch_localdata_changes(
    auth_key: str,
    opn_svc_id: str = '01_03_03_P',
    since_date: Optional[str] = None,
    region_keyword: str = '청주',
    page: int = 1,
    rows: int = 200,
) -> List[Dict[str, Any]]:
    """LOCALDATA에서 일별 변동분 수집.

    pageIndex, pageSize, lastModTsBgn~lastModTsEnd 로 일별 조회.
    """
    if not since_date:
        since_date = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d')
    end_date = datetime.now().strftime('%Y%m%d')

    params = {
        'authKey': auth_key,
        'opnSvcId': opn_svc_id,
        'lastModTsBgn': since_date.replace('-', ''),
        'lastModTsEnd': end_date,
        'pageIndex': str(page),
        'pageSize': str(rows),
        'resultType': 'xml',
    }
    items: List[Dict[str, Any]] = []
    try:
        r = requests.get(LOCALDATA_URL, params=params, timeout=20)
        if r.status_code != 200:
            logger.warning(f"[localdata] HTTP {r.status_code}: {r.text[:200]}")
            return items
        root = ET.fromstring(r.text)
        for row in root.findall('.//row'):
            name = (row.findtext('bplcNm') or '').strip()
            biz_no = (row.findtext('mgtNo') or '').strip() or None
            addr = (row.findtext('rdnWhlAddr') or row.findtext('siteWhlAddr') or '').strip()
            status_nm = (row.findtext('trdStateNm') or '').strip()
            apv_dt = (row.findtext('apvPermYmd') or '').strip()
            close_dt = (row.findtext('clgStdt') or row.findtext('dcbYmd') or '').strip()
            update_dt = (row.findtext('lastModTs') or '').strip()
            # 지역 필터
            if region_keyword and region_keyword not in addr:
                continue
            items.append({
                'name': name,
                'biz_no': biz_no,
                'address': addr,
                'status': status_nm,
                'approve_date': apv_dt,
                'close_date': close_dt,
                'updated': update_dt,
                'raw': {k: v for k, v in {
                    el.tag: el.text for el in row
                }.items() if v},
            })
    except ET.ParseError as e:
        logger.warning(f"[localdata] XML parse error: {e}")
    except Exception as e:
        logger.warning(f"[localdata] fetch error: {e}")
    return items


def classify_event(item: Dict[str, Any]) -> Optional[str]:
    """row → event_type 분류."""
    status = item.get('status', '')
    close_dt = item.get('close_date', '')
    apv_dt = item.get('approve_date', '')
    today = datetime.now().strftime('%Y%m%d')
    seven_days_ago = (datetime.now() - timedelta(days=14)).strftime('%Y%m%d')

    if '폐업' in status or '말소' in status or close_dt:
        return 'closed'
    if '휴업' in status:
        return 'closed'  # 휴업도 closed로 묶음
    if apv_dt and apv_dt >= seven_days_ago and apv_dt <= today:
        return 'opened'
    # 영업 상태 + 최근 변경 → renamed/relocated 추정
    if '영업' in status:
        return 'renamed'  # 정확한 분류는 hashing 필요 — 우선 보고
    return None


def upsert_event(conn: sqlite3.Connection, item: Dict[str, Any], event_type: str) -> bool:
    """clinic_lifecycle_events 적재. 중복은 UNIQUE(biz_no, event_type, event_date)로 차단."""
    cur = conn.cursor()
    event_date = item.get('approve_date') or item.get('close_date') or item.get('updated', '')[:8]
    if event_date and len(event_date) == 8:
        event_date = f"{event_date[:4]}-{event_date[4:6]}-{event_date[6:8]}"
    try:
        cur.execute(
            """
            INSERT INTO clinic_lifecycle_events
                (clinic_name, biz_no, event_type, event_date, address, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(biz_no, event_type, event_date) DO NOTHING
            """,
            (
                item.get('name'),
                item.get('biz_no'),
                event_type,
                event_date or None,
                item.get('address'),
                json.dumps(item.get('raw', {}), ensure_ascii=False),
            ),
        )
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.cursor()
        try:
            n_total = cur.execute("SELECT COUNT(*) FROM clinic_lifecycle_events").fetchone()[0]
        except sqlite3.OperationalError:
            print("clinic_lifecycle_events 테이블 없음. 서버 시작 또는 db_init.py 실행 필요.")
            return 1
        last = cur.execute("SELECT MAX(detected_at) FROM clinic_lifecycle_events").fetchone()[0]
        recent = cur.execute(
            "SELECT event_type, COUNT(*) FROM clinic_lifecycle_events "
            "WHERE detected_at >= datetime('now', '-30 days') GROUP BY event_type"
        ).fetchall()
        print('=== 한의원 인허가 추적 현황 ===')
        print(f'  전체 이벤트: {n_total}건')
        print(f'  마지막 수집: {last or "-"}')
        print('  최근 30일 이벤트별:')
        for ev, cnt in recent:
            print(f'    {ev:<12} {cnt}건')
    finally:
        conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--region', default='청주', help='주소 필터 (기본 청주)')
    parser.add_argument('--service-type', default='한의원', choices=list(SERVICE_TYPE_MAP.keys()))
    parser.add_argument('--since', help='YYYY-MM-DD (기본: 7일 전)')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.status:
        return show_status()

    auth_key = _get_auth_key()
    if not auth_key:
        print('LOCALDATA_AUTH_KEY 또는 DATA_GO_KR_API_KEY 없음. config/secrets.json 등록 필요.')
        return 1

    opn_svc_id = SERVICE_TYPE_MAP[args.service_type]
    since = args.since or (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

    print(f'[localdata] 수집 시작: {args.region} {args.service_type} since={since}')
    items = fetch_localdata_changes(
        auth_key=auth_key,
        opn_svc_id=opn_svc_id,
        since_date=since,
        region_keyword=args.region,
    )
    print(f'  수집 row: {len(items)}건')

    if args.dry_run:
        for it in items[:10]:
            print(f"  - {it.get('name'):<25} {it.get('status'):<10} {it.get('address')}")
        print(f'  ... 외 {max(0, len(items) - 10)}건')
        return 0

    conn = sqlite3.connect(DB_PATH)
    try:
        new_events = 0
        events_by_type: Dict[str, int] = {}
        for it in items:
            ev_type = classify_event(it)
            if not ev_type:
                continue
            if upsert_event(conn, it, ev_type):
                new_events += 1
                events_by_type[ev_type] = events_by_type.get(ev_type, 0) + 1
        conn.commit()
        print(f'\n신규 이벤트 {new_events}건 적재')
        for ev, cnt in events_by_type.items():
            print(f'  {ev:<10} {cnt}건')
        if new_events > 0:
            print('\n→ scrapers/competitor_change_detector.py 또는 web UI에서 후속 처리 (운영자 검토)')
    finally:
        conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
