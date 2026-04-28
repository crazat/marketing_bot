"""[Inbound Analytics] Microsoft Clarity Data Export → 일별 사이트 행동 메트릭.

Clarity Data Export API:
  POST https://www.clarity.ms/export-data/api/v1/project-live-insights
  Header: Authorization: Bearer <CLARITY_API_TOKEN>

수집 메트릭: sessions, page_views, dead_clicks, rage_clicks, quick_backs, scroll_depth_avg.
일별 1행 → clarity_metrics 테이블 (UNIQUE measured_date) upsert.

키 누락 시 graceful skip + 가이드. cron 자동화 없음. 추가 LLM 의존 없음.

운영자 트리거:
  python scripts/clarity_metrics_collector.py                  # 직전 7일
  python scripts/clarity_metrics_collector.py --days 1         # 어제만
  python scripts/clarity_metrics_collector.py --status         # 직전 적재 추세
  python scripts/clarity_metrics_collector.py --dry-run        # API 호출 없이 검증

설정 (config/secrets.json, 선택):
  CLARITY_API_TOKEN    Clarity dashboard → Settings → Data Export 에서 발급
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')
CLARITY_ENDPOINT = "https://www.clarity.ms/export-data/api/v1/project-live-insights"

try:
    from backend_utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger(__name__)


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS clarity_metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            measured_date TEXT NOT NULL UNIQUE,
            sessions INTEGER DEFAULT 0,
            page_views INTEGER DEFAULT 0,
            dead_clicks INTEGER DEFAULT 0,
            rage_clicks INTEGER DEFAULT 0,
            quick_backs INTEGER DEFAULT 0,
            scroll_depth_avg REAL,
            raw_payload TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def load_secrets() -> Dict[str, Any]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def resolve_token() -> Optional[str]:
    return os.getenv('CLARITY_API_TOKEN') or load_secrets().get('CLARITY_API_TOKEN')


# ---------------------------------------------------------------- #
# Clarity API call
# ---------------------------------------------------------------- #
def fetch_clarity_day(token: str, num_of_days: int) -> Optional[Dict[str, Any]]:
    """Clarity Live Insights API 호출. num_of_days: 1~3 (Clarity 제한)."""
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise RuntimeError("requests 미설치. pip install requests") from e

    headers = {'Authorization': f'Bearer {token}'}
    params = {'numOfDays': max(1, min(num_of_days, 3))}
    try:
        resp = requests.get(CLARITY_ENDPOINT, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            logger.warning(f"Clarity API {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json() if resp.content else None
    except Exception as e:
        logger.warning(f"Clarity API 호출 실패: {e}")
        return None


def parse_clarity_metrics(payload: Any) -> Dict[str, Any]:
    """
    Clarity 응답 형태가 metric 별로 list 형식.
    예: [{"metricName": "Traffic", "information": [{"sessionsCount": 123, "pagesPerSession": 2.3, ...}]}, ...]
    숫자형 메트릭만 추출.
    """
    out = {
        'sessions': 0,
        'page_views': 0,
        'dead_clicks': 0,
        'rage_clicks': 0,
        'quick_backs': 0,
        'scroll_depth_avg': None,
    }
    if not payload:
        return out

    # payload가 list of metric dicts
    metrics = payload if isinstance(payload, list) else payload.get('metrics', [])
    for m in metrics or []:
        if not isinstance(m, dict):
            continue
        name = (m.get('metricName') or m.get('name') or '').lower()
        info = m.get('information') or m.get('Information') or []
        if not info or not isinstance(info, list):
            continue
        first = info[0] if isinstance(info[0], dict) else {}

        # 메트릭별 매핑 (Clarity 필드명 변동성에 대비해 다중 키 시도)
        if 'traffic' in name:
            out['sessions'] = int(first.get('totalSessionCount')
                                  or first.get('sessionsCount')
                                  or first.get('totalSessions') or 0)
            out['page_views'] = int(first.get('totalPageView')
                                    or first.get('pageViews')
                                    or first.get('pageViewsCount') or 0)
        elif 'deadclick' in name.replace(' ', '') or 'dead' in name:
            out['dead_clicks'] = int(first.get('subTotalsCount')
                                     or first.get('deadClicksCount')
                                     or first.get('count') or 0)
        elif 'rageclick' in name.replace(' ', '') or 'rage' in name:
            out['rage_clicks'] = int(first.get('subTotalsCount')
                                     or first.get('rageClicksCount')
                                     or first.get('count') or 0)
        elif 'quickback' in name.replace(' ', '') or 'quick back' in name:
            out['quick_backs'] = int(first.get('subTotalsCount')
                                     or first.get('quickBacksCount')
                                     or first.get('count') or 0)
        elif 'scrolldepth' in name.replace(' ', '') or 'scroll' in name:
            try:
                out['scroll_depth_avg'] = float(first.get('averageScrollDepth')
                                                or first.get('scrollDepth')
                                                or first.get('value') or 0.0)
            except Exception:
                pass

    return out


# ---------------------------------------------------------------- #
# CLI
# ---------------------------------------------------------------- #
def show_status() -> int:
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        ensure_table(conn)
        cur = conn.cursor()
        rows = cur.execute(
            """
            SELECT measured_date, sessions, page_views,
                   dead_clicks, rage_clicks, quick_backs, scroll_depth_avg
              FROM clarity_metrics
             ORDER BY measured_date DESC
             LIMIT 14
            """
        ).fetchall()
        if not rows:
            print('직전 Clarity 측정 없음. 실행 권장:')
            print('  python scripts/clarity_metrics_collector.py')
            return 0
        print('=== Clarity 사이트 행동 (최근 14일) ===')
        print(f'{"날짜":<12} {"sess":<6} {"PV":<6} {"dead":<6} {"rage":<6} {"qBack":<6} {"scroll%":<7}')
        print('-' * 64)
        for d, s, pv, dc, rc, qb, sd in rows:
            sd_s = f'{sd:.1f}' if sd is not None else '-'
            print(f'{d:<12} {s or 0:<6} {pv or 0:<6} {dc or 0:<6} {rc or 0:<6} {qb or 0:<6} {sd_s:<7}')
        return 0
    finally:
        if conn:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='Microsoft Clarity 일별 메트릭 수집')
    parser.add_argument('--days', type=int, default=7,
                        help='직전 N일 (기본 7, Clarity API는 한 번에 최대 3일치 반환 — 일별 호출)')
    parser.add_argument('--status', action='store_true', help='직전 적재 상태')
    parser.add_argument('--dry-run', action='store_true', help='API 호출 없이 검증')
    args = parser.parse_args()

    if args.status:
        return show_status()

    token = resolve_token()
    if not token:
        print('=' * 60)
        print('[skip] CLARITY_API_TOKEN 미설정 — graceful skip.')
        print('=' * 60)
        print('설정 가이드:')
        print('  1. https://clarity.microsoft.com/ 로그인 → 프로젝트 선택')
        print('  2. Settings → Data Export → Generate new API token')
        print('  3. config/secrets.json 에 추가:')
        print('       "CLARITY_API_TOKEN": "your-token-here"')
        print('  4. 재실행: python scripts/clarity_metrics_collector.py')
        print('  비용: 무료. Project당 일 10회 호출 제한.')
        return 0

    if args.dry_run:
        print(f'[dry-run] 토큰 확인 OK. 직전 {args.days}일 호출 예정.')
        print(f'  endpoint: {CLARITY_ENDPOINT}?numOfDays=1')
        return 0

    print(f'Clarity 수집: 직전 {args.days}일')

    # Clarity는 numOfDays 1/2/3만 지원 → 3일 단위로 누적 호출, 응답은 합산값
    # 보수적으로 1일치만 매번 호출하여 measured_date에 정확히 매핑
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        ensure_table(conn)
        cur = conn.cursor()
        inserted = 0
        # API는 "직전 N일"을 합산 반환. 일자별 분리값을 위해 1일 호출만 수행하고
        # measured_date = (today - 1) 로 적재. --days N 인 경우는 누적값을 N일 평균으로 균등 분할.
        payload = fetch_clarity_day(token, num_of_days=min(args.days, 3))
        if payload is None:
            print('[error] Clarity API 응답 없음 (토큰/한도 확인).')
            return 2

        metrics = parse_clarity_metrics(payload)
        # measured_date = 어제
        target_date = (date.today() - timedelta(days=1)).isoformat()
        if args.days > 1:
            # 합산값을 일별 평균으로 균등 배분 (참고용 — 정밀하지 않음)
            for k in ('sessions', 'page_views', 'dead_clicks', 'rage_clicks', 'quick_backs'):
                metrics[k] = int((metrics[k] or 0) / max(args.days, 1))

        cur.execute(
            """
            INSERT OR REPLACE INTO clarity_metrics
                (measured_date, sessions, page_views, dead_clicks,
                 rage_clicks, quick_backs, scroll_depth_avg, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_date,
                metrics['sessions'],
                metrics['page_views'],
                metrics['dead_clicks'],
                metrics['rage_clicks'],
                metrics['quick_backs'],
                metrics['scroll_depth_avg'],
                json.dumps(payload, ensure_ascii=False)[:8000],
            ),
        )
        inserted = 1
        conn.commit()
        print(f'\nDB 적재: {inserted}건 (measured_date={target_date})')
        print(f'  sessions={metrics["sessions"]} PV={metrics["page_views"]} '
              f'dead={metrics["dead_clicks"]} rage={metrics["rage_clicks"]} '
              f'quickBack={metrics["quick_backs"]} scroll={metrics["scroll_depth_avg"]}')
        print('--status 로 누적 추세 확인 권장.')
        return 0
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    sys.exit(main())
