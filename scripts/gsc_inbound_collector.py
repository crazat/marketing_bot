"""[Inbound Analytics] Google Search Console → 자사 사이트 진입 검색어 수집.

GSC API에서 직전 N일(기본 28일)의 query/page/clicks/impressions/ctr/position을
inbound_search_queries 테이블에 적재. cron 자동화 없음 — 사용자 수동 트리거.

키 누락 시 graceful skip + 가이드 출력. 추가 LLM 키 필요 없음 (Gemini 정책 준수).

운영자 트리거:
  python scripts/gsc_inbound_collector.py                  # 직전 28일 수집
  python scripts/gsc_inbound_collector.py --days 7         # 직전 7일만
  python scripts/gsc_inbound_collector.py --status         # 직전 측정 결과 보기
  python scripts/gsc_inbound_collector.py --dry-run        # 실 수집 없이 미리보기

설정 (config/secrets.json, 모두 선택):
  GSC_SITE_URL                 등록된 사이트 URL (예: https://example.com/ 또는 sc-domain:example.com)
  GSC_OAUTH_CREDENTIALS_PATH   OAuth client_secrets.json 경로 (Google Cloud 발급)
                               미설정 시 ~/.gsc/credentials.json 시도
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, date
from typing import Optional, List, Dict, Any

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

try:
    from backend_utils.logger import get_logger
    logger = get_logger(__name__)
except Exception:
    import logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
    logger = logging.getLogger(__name__)


# ---------------------------------------------------------------- #
# DB schema
# ---------------------------------------------------------------- #
def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS inbound_search_queries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            query TEXT NOT NULL,
            landing_url TEXT,
            impressions INTEGER DEFAULT 0,
            clicks INTEGER DEFAULT 0,
            ctr REAL,
            position REAL,
            measured_date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(source, query, landing_url, measured_date)
        );
        CREATE INDEX IF NOT EXISTS idx_inbound_query ON inbound_search_queries(query);
        CREATE INDEX IF NOT EXISTS idx_inbound_date ON inbound_search_queries(measured_date);
        """
    )


# ---------------------------------------------------------------- #
# Secrets / config loader
# ---------------------------------------------------------------- #
def load_secrets() -> Dict[str, Any]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def resolve_credentials_path() -> Optional[str]:
    """OAuth credentials.json 경로 결정. env > secrets.json > ~/.gsc/credentials.json."""
    env_p = os.getenv('GSC_OAUTH_CREDENTIALS_PATH')
    if env_p and os.path.exists(env_p):
        return env_p

    secrets = load_secrets()
    p = secrets.get('GSC_OAUTH_CREDENTIALS_PATH') or os.getenv('GSC_OAUTH_CREDENTIALS_PATH')
    if p and os.path.exists(p):
        return p

    default = os.path.expanduser('~/.gsc/credentials.json')
    if os.path.exists(default):
        return default
    return None


def resolve_site_url() -> Optional[str]:
    return (
        os.getenv('GSC_SITE_URL')
        or load_secrets().get('GSC_SITE_URL')
    )


# ---------------------------------------------------------------- #
# GSC client (lazy import — 패키지 없어도 --status는 동작)
# ---------------------------------------------------------------- #
def build_gsc_client(creds_path: str):
    """google-searchconsole or google-api-python-client 둘 다 시도."""
    # Preferred: searchconsole 래퍼
    try:
        import searchconsole  # type: ignore
        account = searchconsole.authenticate(client_config=creds_path)
        return ('searchconsole', account)
    except ImportError:
        pass
    except Exception as e:
        logger.warning(f"searchconsole 인증 실패: {e}")

    # Fallback: google-api-python-client 직접
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google_auth_oauthlib.flow import InstalledAppFlow  # type: ignore
        from googleapiclient.discovery import build  # type: ignore

        scopes = ['https://www.googleapis.com/auth/webmasters.readonly']
        token_path = os.path.join(os.path.dirname(creds_path), 'gsc_token.json')
        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)
        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
            creds = flow.run_local_server(port=0)
            with open(token_path, 'w', encoding='utf-8') as f:
                f.write(creds.to_json())
        service = build('searchconsole', 'v1', credentials=creds, cache_discovery=False)
        return ('apiclient', service)
    except ImportError as e:
        raise RuntimeError(
            "GSC 클라이언트 미설치. 다음 중 하나 설치: "
            "pip install google-searchconsole "
            "또는 pip install google-api-python-client google-auth-oauthlib"
        ) from e


def fetch_gsc_rows(client_tuple, site_url: str, start_date: str, end_date: str,
                   row_limit: int = 25000) -> List[Dict[str, Any]]:
    kind, client = client_tuple
    if kind == 'searchconsole':
        webproperty = client[site_url]
        report = (webproperty.query
                  .range(start_date, end_date)
                  .dimension('query', 'page', 'date')
                  .limit(row_limit)
                  .get())
        out = []
        for r in report.rows:
            keys = list(r.keys)
            out.append({
                'query': keys[0] if len(keys) > 0 else '',
                'page': keys[1] if len(keys) > 1 else '',
                'date': keys[2] if len(keys) > 2 else end_date,
                'clicks': r.clicks,
                'impressions': r.impressions,
                'ctr': r.ctr,
                'position': r.position,
            })
        return out

    # apiclient
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['query', 'page', 'date'],
        'rowLimit': row_limit,
        'searchType': 'web',
    }
    resp = client.searchanalytics().query(siteUrl=site_url, body=body).execute()
    out = []
    for r in resp.get('rows', []):
        keys = r.get('keys', [])
        out.append({
            'query': keys[0] if len(keys) > 0 else '',
            'page': keys[1] if len(keys) > 1 else '',
            'date': keys[2] if len(keys) > 2 else end_date,
            'clicks': r.get('clicks', 0),
            'impressions': r.get('impressions', 0),
            'ctr': r.get('ctr', 0.0),
            'position': r.get('position', 0.0),
        })
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
            SELECT measured_date,
                   COUNT(DISTINCT query) AS uniq_q,
                   SUM(impressions) AS imps,
                   SUM(clicks) AS clk,
                   AVG(position) AS avg_pos
              FROM inbound_search_queries
             WHERE source='gsc'
             GROUP BY measured_date
             ORDER BY measured_date DESC
             LIMIT 14
            """
        ).fetchall()
        if not rows:
            print('직전 GSC 측정 없음. 다음 실행 권장:')
            print('  python scripts/gsc_inbound_collector.py')
            return 0
        print('=== GSC 진입 검색어 (최근 14일) ===')
        print(f'{"날짜":<12} {"유니크 query":<14} {"노출":<10} {"클릭":<8} {"평균 순위":<8}')
        print('-' * 60)
        for d, uq, imps, clk, ap in rows:
            print(f'{d:<12} {uq:<14} {imps or 0:<10} {clk or 0:<8} {ap or 0:<8.2f}')

        # 최근 측정일 top 검색어
        latest = rows[0][0]
        top = cur.execute(
            """
            SELECT query, SUM(clicks), SUM(impressions), AVG(position)
              FROM inbound_search_queries
             WHERE source='gsc' AND measured_date=?
             GROUP BY query
             ORDER BY SUM(clicks) DESC
             LIMIT 10
            """, (latest,)
        ).fetchall()
        if top:
            print(f'\n--- {latest} top 10 by clicks ---')
            for q, c, i, p in top:
                print(f'  {q[:40]:<42} 클릭{c or 0} 노출{i or 0} 순위{p or 0:.1f}')
        return 0
    finally:
        if conn:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='GSC 진입 검색어 수집')
    parser.add_argument('--days', type=int, default=28, help='직전 N일 (기본 28)')
    parser.add_argument('--status', action='store_true', help='직전 결과만 표시')
    parser.add_argument('--dry-run', action='store_true', help='실 수집 없이 검증만')
    args = parser.parse_args()

    if args.status:
        return show_status()

    site_url = resolve_site_url()
    creds_path = resolve_credentials_path()

    if not site_url or not creds_path:
        print('=' * 60)
        print('[skip] GSC 자격증명 미설정 — graceful skip.')
        print('=' * 60)
        print('설정 가이드:')
        print('  1. Google Cloud Console에서 OAuth 2.0 client_secrets.json 다운로드')
        print('  2. config/secrets.json 또는 환경변수에 등록:')
        print('       GSC_SITE_URL                  = https://your-site.com/')
        print('                                       또는 sc-domain:your-site.com')
        print('       GSC_OAUTH_CREDENTIALS_PATH    = C:\\path\\to\\client_secrets.json')
        print('  3. 패키지 설치: pip install google-api-python-client google-auth-oauthlib')
        print('  4. 재실행: python scripts/gsc_inbound_collector.py')
        if not site_url:
            print('\n현재 누락: GSC_SITE_URL')
        if not creds_path:
            print('현재 누락: GSC_OAUTH_CREDENTIALS_PATH')
        return 0

    end = date.today() - timedelta(days=2)  # GSC는 보통 2일 lag
    start = end - timedelta(days=max(args.days - 1, 0))
    start_s, end_s = start.isoformat(), end.isoformat()

    print(f'GSC 수집 범위: {start_s} → {end_s} ({args.days}일)')
    print(f'사이트: {site_url}')
    print(f'자격증명: {creds_path}')

    if args.dry_run:
        print('\n[dry-run] 실 API 호출 없이 종료. --dry-run 빼고 다시 실행.')
        return 0

    try:
        client_tuple = build_gsc_client(creds_path)
    except RuntimeError as e:
        print(f'[error] {e}')
        return 2

    try:
        rows = fetch_gsc_rows(client_tuple, site_url, start_s, end_s)
    except Exception as e:
        print(f'[error] GSC API 호출 실패: {e}')
        return 2

    print(f'GSC 응답 row 수: {len(rows)}')

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        ensure_table(conn)
        cur = conn.cursor()
        inserted = 0
        for r in rows:
            try:
                cur.execute(
                    """
                    INSERT OR REPLACE INTO inbound_search_queries
                        (source, query, landing_url, impressions, clicks,
                         ctr, position, measured_date)
                    VALUES ('gsc', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (r.get('query') or '').strip(),
                        (r.get('page') or '').strip(),
                        int(r.get('impressions') or 0),
                        int(r.get('clicks') or 0),
                        float(r.get('ctr') or 0.0),
                        float(r.get('position') or 0.0),
                        r.get('date') or end_s,
                    ),
                )
                inserted += 1
            except Exception as e:
                logger.debug(f'row 적재 실패: {e}')
        conn.commit()
        print(f'\nDB 적재: {inserted}/{len(rows)}건')
        print('--status 로 누적 추세 확인 권장.')
    finally:
        if conn:
            conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
