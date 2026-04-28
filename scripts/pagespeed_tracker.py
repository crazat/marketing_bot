"""[Inbound Analytics] PageSpeed Insights API → Core Web Vitals 추적.

PSI v5: GET https://www.googleapis.com/pagespeedonline/v5/runPagespeed
입력 URL은 config/business_profile.json::sites_to_monitor (없으면 안내).
모바일/데스크탑 strategy 모두 측정 → pagespeed_history 테이블 적재.

추출: lcp, inp, cls, fcp, ttfb, performance_score. CrUX origin summary도 보존.

키 없어도 일 25k 무료 → API 키 없을 시 안내만 하고 진행 가능.
추가 LLM 키 없음. cron 없음.

운영자 트리거:
  python scripts/pagespeed_tracker.py                       # 모바일+데스크탑
  python scripts/pagespeed_tracker.py --strategy mobile     # 모바일만
  python scripts/pagespeed_tracker.py --status              # 직전 추세
  python scripts/pagespeed_tracker.py --dry-run             # 호출 없이 URL 검증

설정:
  config/business_profile.json:
    "sites_to_monitor": ["https://your-site.com/", "https://your-site.com/blog/"]

  config/secrets.json (선택):
    PAGESPEED_API_KEY    무료 일 25k 한도. 키 없으면 일 5건 정도로 제한적.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
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
PROFILE_PATH = os.path.join(ROOT_DIR, 'config', 'business_profile.json')
PSI_ENDPOINT = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"

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
        CREATE TABLE IF NOT EXISTS pagespeed_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_url TEXT NOT NULL,
            strategy TEXT NOT NULL,
            measured_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            performance_score REAL,
            lcp_ms REAL,
            inp_ms REAL,
            cls REAL,
            fcp_ms REAL,
            ttfb_ms REAL,
            crux_origin_summary TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_pagespeed_site
            ON pagespeed_history(site_url, strategy, measured_at);
        """
    )


def load_secrets() -> Dict[str, Any]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def load_profile() -> Dict[str, Any]:
    try:
        with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def resolve_api_key() -> Optional[str]:
    """env > secrets.json > setup_paths.get_api_key('pagespeed')."""
    if os.getenv('PAGESPEED_API_KEY'):
        return os.getenv('PAGESPEED_API_KEY')
    s = load_secrets()
    if s.get('PAGESPEED_API_KEY'):
        return s['PAGESPEED_API_KEY']
    try:
        from setup_paths import get_api_key  # type: ignore
        return get_api_key('pagespeed')
    except Exception:
        return None


def resolve_sites() -> List[str]:
    profile = load_profile()
    raw = profile.get('sites_to_monitor') or []
    if isinstance(raw, str):
        raw = [raw]
    urls: List[str] = []
    for item in raw:
        if isinstance(item, str):
            urls.append(item.strip())
        elif isinstance(item, dict):
            u = item.get('url')
            if u: urls.append(str(u).strip())
    site = (profile.get('business') or {}).get('website')
    if site and not urls:
        urls = [site]
    return [u for u in urls if u]


# ---------------------------------------------------------------- #
# PSI fetch
# ---------------------------------------------------------------- #
def fetch_psi(url: str, strategy: str, api_key: Optional[str]) -> Optional[Dict[str, Any]]:
    try:
        import requests  # type: ignore
    except ImportError as e:
        raise RuntimeError("requests 미설치. pip install requests") from e

    params = {
        'url': url,
        'strategy': strategy,
        'category': ['performance'],
    }
    if api_key:
        params['key'] = api_key

    try:
        resp = requests.get(PSI_ENDPOINT, params=params, timeout=60)
        if resp.status_code != 200:
            logger.warning(f"PSI {strategy} {resp.status_code}: {resp.text[:200]}")
            return None
        return resp.json()
    except Exception as e:
        logger.warning(f"PSI 호출 실패 {url}: {e}")
        return None


def parse_metrics(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Lighthouse audits + loadingExperience(CrUX origin) 추출."""
    out = {
        'performance_score': None,
        'lcp_ms': None,
        'inp_ms': None,
        'cls': None,
        'fcp_ms': None,
        'ttfb_ms': None,
        'crux_origin_summary': None,
    }
    if not isinstance(payload, dict):
        return out

    # 1) Lighthouse score
    lr = payload.get('lighthouseResult') or {}
    cats = lr.get('categories') or {}
    perf = cats.get('performance') or {}
    if perf.get('score') is not None:
        try:
            out['performance_score'] = float(perf['score']) * 100
        except Exception:
            pass

    # 2) Lighthouse audits — lab data
    audits = lr.get('audits') or {}

    def _num(audit_id: str, key: str = 'numericValue') -> Optional[float]:
        a = audits.get(audit_id) or {}
        v = a.get(key)
        try:
            return float(v) if v is not None else None
        except Exception:
            return None

    out['lcp_ms'] = _num('largest-contentful-paint')
    out['fcp_ms'] = _num('first-contentful-paint')
    out['cls'] = _num('cumulative-layout-shift')
    out['ttfb_ms'] = _num('server-response-time')
    # INP는 lab에선 없을 수 있음 — interaction-to-next-paint, total-blocking-time 폴백
    out['inp_ms'] = _num('interaction-to-next-paint') or _num('total-blocking-time')

    # 3) CrUX origin (실측 데이터)
    le = payload.get('originLoadingExperience') or payload.get('loadingExperience') or {}
    metrics = le.get('metrics') or {}
    crux_summary = {}
    for k_field, k_payload in [
        ('lcp_ms', 'LARGEST_CONTENTFUL_PAINT_MS'),
        ('inp_ms', 'INTERACTION_TO_NEXT_PAINT'),
        ('cls', 'CUMULATIVE_LAYOUT_SHIFT_SCORE'),
        ('fcp_ms', 'FIRST_CONTENTFUL_PAINT_MS'),
        ('ttfb_ms', 'EXPERIMENTAL_TIME_TO_FIRST_BYTE'),
    ]:
        m = metrics.get(k_payload)
        if isinstance(m, dict) and m.get('percentile') is not None:
            try:
                val = float(m['percentile'])
                if k_field == 'cls':
                    val = val / 100.0  # CLS는 *100 단위로 옴
                crux_summary[k_field] = val
                # CrUX 값을 우선 — Lighthouse lab보다 실측이 우월
                if out[k_field] is None:
                    out[k_field] = val
            except Exception:
                pass
    if crux_summary:
        out['crux_origin_summary'] = json.dumps(crux_summary, ensure_ascii=False)

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
            SELECT site_url, strategy,
                   ROUND(AVG(performance_score),1),
                   ROUND(AVG(lcp_ms),0),
                   ROUND(AVG(inp_ms),0),
                   ROUND(AVG(cls),3),
                   COUNT(*),
                   MAX(measured_at)
              FROM pagespeed_history
             WHERE measured_at >= datetime('now', '-30 days')
             GROUP BY site_url, strategy
             ORDER BY MAX(measured_at) DESC
             LIMIT 30
            """
        ).fetchall()
        if not rows:
            print('직전 PageSpeed 측정 없음. 실행 권장:')
            print('  python scripts/pagespeed_tracker.py')
            return 0
        print('=== PageSpeed Core Web Vitals (30일 평균) ===')
        print(f'{"URL":<40} {"strat":<8} {"perf":<5} {"LCP ms":<7} {"INP ms":<7} {"CLS":<6} {"N":<3} {"최근":<19}')
        print('-' * 105)
        for u, s, perf, lcp, inp, cls, n, ts in rows:
            print(f'{(u or "")[:38]:<40} {s or "":<8} {perf or 0:<5} {int(lcp or 0):<7} '
                  f'{int(inp or 0):<7} {(cls or 0):<6.3f} {n:<3} {(ts or "")[:19]:<19}')
        return 0
    finally:
        if conn:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='PageSpeed Insights / Core Web Vitals 추적')
    parser.add_argument('--strategy', choices=['mobile', 'desktop', 'both'],
                        default='both', help='측정 strategy')
    parser.add_argument('--status', action='store_true', help='직전 추세 보기')
    parser.add_argument('--dry-run', action='store_true', help='URL 확인만, API 호출 없이')
    args = parser.parse_args()

    if args.status:
        return show_status()

    sites = resolve_sites()
    if not sites:
        print('=' * 60)
        print('[skip] 측정 대상 URL 미설정.')
        print('=' * 60)
        print('config/business_profile.json 에 다음 추가:')
        print('  "sites_to_monitor": ["https://your-site.com/",')
        print('                        "https://your-site.com/blog/"]')
        print('  또는 "business.website" 필드만 채워도 자동 사용.')
        return 0

    api_key = resolve_api_key()
    strategies = ['mobile', 'desktop'] if args.strategy == 'both' else [args.strategy]

    print(f'PageSpeed 측정: {len(sites)}개 URL × {len(strategies)} strategy')
    if not api_key:
        print('  [warn] PAGESPEED_API_KEY 없음 — 무료 한도(일 5~25 요청)로만 동작.')
        print('         과한 요청 시 429. 키 등록: config/secrets.json::PAGESPEED_API_KEY')

    for u in sites:
        print(f'  - {u}')
    for s in strategies:
        print(f'  strategy: {s}')

    if args.dry_run:
        print('\n[dry-run] 종료.')
        return 0

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        ensure_table(conn)
        cur = conn.cursor()
        inserted = 0
        for url in sites:
            for strategy in strategies:
                print(f'\n[PSI] {strategy} | {url}')
                payload = fetch_psi(url, strategy, api_key)
                if payload is None:
                    print('  [skip] 응답 없음')
                    continue
                metrics = parse_metrics(payload)
                cur.execute(
                    """
                    INSERT INTO pagespeed_history
                        (site_url, strategy, performance_score, lcp_ms, inp_ms,
                         cls, fcp_ms, ttfb_ms, crux_origin_summary)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        url, strategy,
                        metrics['performance_score'], metrics['lcp_ms'], metrics['inp_ms'],
                        metrics['cls'], metrics['fcp_ms'], metrics['ttfb_ms'],
                        metrics['crux_origin_summary'],
                    ),
                )
                inserted += 1
                print(f'  perf={metrics["performance_score"]} LCP={metrics["lcp_ms"]} '
                      f'INP={metrics["inp_ms"]} CLS={metrics["cls"]}')
                # rate limit 보호
                time.sleep(1.0)
        conn.commit()
        print(f'\nDB 적재: {inserted}건')
        print('--status 로 30일 평균 확인 권장.')
        return 0
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    sys.exit(main())
