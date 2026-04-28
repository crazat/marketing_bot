"""[Inbound Analytics] Naver Search Advisor → 자사 사이트 진입 검색어 수집.

공식 API 없음 → Camoufox 로그인 후 검색어 통계 페이지에서 CSV 자동 다운로드.
다운받은 CSV를 inbound_search_queries 테이블 (source='naver_advisor')로 적재.

키 누락 시 graceful skip + 가이드 출력. 추가 LLM 키 없음 (Gemini-only 정책 유지).

운영자 트리거:
  python scripts/naver_advisor_scraper.py                  # 직전 90일 수집
  python scripts/naver_advisor_scraper.py --days 30        # 직전 30일
  python scripts/naver_advisor_scraper.py --status         # 직전 적재 상태
  python scripts/naver_advisor_scraper.py --dry-run        # 로그인까지만 검증

설정 (config/secrets.json, 둘 중 하나만 있어도 됨):
  NAVER_ADVISOR_ID / NAVER_ADVISOR_PW         네이버 계정 (2FA 미사용 권장)
  NAVER_ADVISOR_COOKIES_PATH                  로그인된 쿠키 JSON (Camoufox 수동 export)
  NAVER_ADVISOR_SITE_URL                      등록된 사이트 URL
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
import sqlite3
import sys
import time
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
DOWNLOAD_DIR = os.path.join(ROOT_DIR, 'db', 'naver_advisor_csv')

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


def load_secrets() -> Dict[str, Any]:
    try:
        with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def resolve_advisor_creds() -> Dict[str, Optional[str]]:
    s = load_secrets()
    return {
        'id': os.getenv('NAVER_ADVISOR_ID') or s.get('NAVER_ADVISOR_ID'),
        'pw': os.getenv('NAVER_ADVISOR_PW') or s.get('NAVER_ADVISOR_PW'),
        'cookies_path': os.getenv('NAVER_ADVISOR_COOKIES_PATH') or s.get('NAVER_ADVISOR_COOKIES_PATH'),
        'site_url': os.getenv('NAVER_ADVISOR_SITE_URL') or s.get('NAVER_ADVISOR_SITE_URL'),
    }


# ---------------------------------------------------------------- #
# Camoufox 로그인 & CSV 다운로드
# ---------------------------------------------------------------- #
def fetch_advisor_csv(creds: Dict[str, Optional[str]], days: int,
                      dry_run: bool = False) -> List[Dict[str, Any]]:
    """
    Camoufox로 Naver Search Advisor 로그인 후 검색어 CSV 다운로드.
    공식 API 없음 → 사이트 구조 변경 시 selector 재조정 필요.
    """
    try:
        from camoufox.sync_api import Camoufox  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "camoufox not installed. pip install camoufox && python -m camoufox fetch"
        ) from e

    os.makedirs(DOWNLOAD_DIR, exist_ok=True)

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=max(days - 1, 0))

    rows: List[Dict[str, Any]] = []

    with Camoufox(
        headless=False,  # 로그인은 사용자 확인 필요할 수 있음
        humanize=True,
        locale=['ko-KR', 'ko'],
        i_know_what_im_doing=True,
    ) as browser:
        page = browser.new_page()

        # 1) 쿠키 로드 (있을 경우)
        cookies_loaded = False
        if creds.get('cookies_path') and os.path.exists(creds['cookies_path']):
            try:
                with open(creds['cookies_path'], 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                browser.contexts[0].add_cookies(cookies)
                cookies_loaded = True
                logger.info(f"쿠키 로드 완료: {creds['cookies_path']}")
            except Exception as e:
                logger.warning(f"쿠키 로드 실패: {e}")

        # 2) ID/PW 로그인
        if not cookies_loaded and creds.get('id') and creds.get('pw'):
            page.goto('https://nid.naver.com/nidlogin.login', timeout=20000,
                      wait_until='domcontentloaded')
            time.sleep(1.0)
            try:
                page.fill('input[name="id"]', creds['id'])
                time.sleep(0.4)
                page.fill('input[name="pw"]', creds['pw'])
                time.sleep(0.3)
                page.click('button[type="submit"]')
                time.sleep(3.5)
            except Exception as e:
                logger.warning(f"로그인 폼 입력 실패 (CAPTCHA 가능): {e}")

        # 3) Search Advisor 검색어 통계 페이지 이동
        site = creds.get('site_url') or ''
        # 사이트 토큰 URL은 환경별 다름 — 메인 진입 → 사용자 사이트 선택
        page.goto('https://searchadvisor.naver.com/console/board', timeout=20000,
                  wait_until='domcontentloaded')
        time.sleep(2.5)

        if dry_run:
            logger.info("[dry-run] 로그인까지만 검증 — 페이지 도달 여부 확인")
            current_url = page.url
            print(f'  현재 URL: {current_url}')
            print('  로그인 성공 시 /console/board 또는 /console/site/* 형태')
            return []

        # 4) 검색어 분석 → 검색어 통계 → 기간 설정 → CSV 다운로드
        # 페이지 구조 변경 시 사용자가 수동 export 한 CSV를 DOWNLOAD_DIR에 넣고
        # parse_advisor_csv_dir() 로 처리하도록 fallback.
        logger.warning(
            "[NOTE] Naver Search Advisor 페이지 구조는 자주 변경됨. "
            "자동 CSV 다운로드 실패 시 수동 export 한 CSV를 "
            f"{DOWNLOAD_DIR} 폴더에 두고 재실행하세요."
        )

        try:
            # 검색어 통계 메뉴 클릭 시도
            page.click('text=검색어', timeout=5000)
            time.sleep(2)
            # CSV/엑셀 다운로드 버튼 추정 selector 모음
            for sel in ['button:has-text("다운로드")',
                        'button:has-text("엑셀")',
                        'a:has-text("CSV")']:
                try:
                    with page.expect_download(timeout=10000) as dl_info:
                        page.click(sel)
                    download = dl_info.value
                    target = os.path.join(
                        DOWNLOAD_DIR,
                        f'naver_advisor_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
                    )
                    download.save_as(target)
                    logger.info(f"CSV 저장: {target}")
                    rows.extend(parse_advisor_csv(target, start.isoformat(), end.isoformat()))
                    break
                except Exception:
                    continue
        except Exception as e:
            logger.warning(f"메뉴 자동 클릭 실패: {e}")

    # 다운로드 폴더의 모든 CSV 처리 (수동 export 포함)
    if not rows:
        rows = parse_advisor_csv_dir(DOWNLOAD_DIR, start.isoformat(), end.isoformat())

    return rows


def parse_advisor_csv(csv_path: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """
    검색어 / 노출수 / 클릭수 / 클릭률 / 평균순위 형태 CSV 파싱.
    네이버는 EUC-KR/UTF-8-BOM 둘 다 사용. 양쪽 시도.
    """
    out = []
    encodings = ['utf-8-sig', 'cp949', 'utf-8']
    text = None
    for enc in encodings:
        try:
            with open(csv_path, 'r', encoding=enc) as f:
                text = f.read()
            break
        except UnicodeDecodeError:
            continue
    if not text:
        logger.warning(f"CSV 인코딩 판독 실패: {csv_path}")
        return []

    reader = csv.reader(io.StringIO(text))
    header_keys = ['검색어', 'query', '키워드']
    rows_iter = list(reader)
    if not rows_iter:
        return []
    header = rows_iter[0]
    # 컬럼 인덱스 추정
    try:
        q_i = next(i for i, h in enumerate(header) if any(k in h for k in header_keys))
    except StopIteration:
        q_i = 0
    imp_i = next((i for i, h in enumerate(header) if '노출' in h or 'impression' in h.lower()), 1)
    clk_i = next((i for i, h in enumerate(header) if '클릭' in h or 'click' in h.lower()), 2)
    pos_i = next((i for i, h in enumerate(header) if '순위' in h or 'position' in h.lower()), -1)

    for r in rows_iter[1:]:
        if len(r) <= q_i:
            continue
        q = (r[q_i] or '').strip()
        if not q:
            continue
        try:
            imp = int(str(r[imp_i]).replace(',', '')) if imp_i < len(r) else 0
        except Exception:
            imp = 0
        try:
            clk = int(str(r[clk_i]).replace(',', '')) if clk_i < len(r) else 0
        except Exception:
            clk = 0
        try:
            pos = float(str(r[pos_i]).replace(',', '')) if 0 <= pos_i < len(r) else 0.0
        except Exception:
            pos = 0.0
        ctr = (clk / imp) if imp > 0 else 0.0
        out.append({
            'query': q,
            'page': '',
            'date': end_date,  # CSV는 합산값 — measured_date에 end_date 사용
            'impressions': imp,
            'clicks': clk,
            'ctr': ctr,
            'position': pos,
        })
    return out


def parse_advisor_csv_dir(csv_dir: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    if not os.path.isdir(csv_dir):
        return []
    out = []
    for fn in os.listdir(csv_dir):
        if fn.lower().endswith('.csv'):
            path = os.path.join(csv_dir, fn)
            try:
                out.extend(parse_advisor_csv(path, start_date, end_date))
            except Exception as e:
                logger.warning(f"CSV 파싱 실패 {fn}: {e}")
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
             WHERE source='naver_advisor'
             GROUP BY measured_date
             ORDER BY measured_date DESC
             LIMIT 14
            """
        ).fetchall()
        if not rows:
            print('직전 Naver Advisor 측정 없음. 다음 실행 권장:')
            print('  python scripts/naver_advisor_scraper.py')
            return 0
        print('=== Naver Advisor 진입 검색어 (최근 측정 14건) ===')
        print(f'{"측정날짜":<12} {"유니크 query":<14} {"노출":<10} {"클릭":<8} {"평균 순위":<8}')
        print('-' * 60)
        for d, uq, imps, clk, ap in rows:
            print(f'{d:<12} {uq:<14} {imps or 0:<10} {clk or 0:<8} {(ap or 0):<8.2f}')
        return 0
    finally:
        if conn:
            conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description='Naver Search Advisor 진입 검색어 수집')
    parser.add_argument('--days', type=int, default=90, help='직전 N일 (기본 90)')
    parser.add_argument('--status', action='store_true', help='직전 적재 상태 보기')
    parser.add_argument('--dry-run', action='store_true', help='로그인 검증만, CSV 다운로드 없이')
    args = parser.parse_args()

    if args.status:
        return show_status()

    creds = resolve_advisor_creds()
    has_login = bool(creds.get('id') and creds.get('pw'))
    has_cookies = bool(creds.get('cookies_path') and os.path.exists(creds.get('cookies_path') or ''))

    if not (has_login or has_cookies):
        print('=' * 60)
        print('[skip] Naver Advisor 자격증명 미설정 — graceful skip.')
        print('=' * 60)
        print('설정 가이드 (config/secrets.json 또는 환경변수):')
        print('  방법 A) ID/PW 로그인 (2FA 미사용 계정 권장)')
        print('       NAVER_ADVISOR_ID = "your-naver-id"')
        print('       NAVER_ADVISOR_PW = "your-naver-pw"')
        print('  방법 B) 쿠키 export (보안상 권장)')
        print('       NAVER_ADVISOR_COOKIES_PATH = "C:\\path\\to\\naver_cookies.json"')
        print('       (Camoufox로 수동 로그인 후 context.cookies() export)')
        print('  공통)  NAVER_ADVISOR_SITE_URL = "https://your-site.com/"')
        print('')
        print('대안: Search Advisor 콘솔에서 직접 CSV 다운로드 후')
        print(f'       {DOWNLOAD_DIR} 폴더에 두고 다시 실행하면 적재만 시도함.')
        # 폴더에 수동 CSV가 있으면 그것만이라도 적재
        manual_rows = parse_advisor_csv_dir(DOWNLOAD_DIR,
                                            (date.today() - timedelta(days=args.days)).isoformat(),
                                            date.today().isoformat())
        if manual_rows:
            print(f'\n수동 CSV 발견: {len(manual_rows)}행 — 적재 진행')
            return _persist(manual_rows)
        return 0

    print(f'Naver Advisor 수집 시도 (days={args.days}, dry_run={args.dry_run})')
    try:
        rows = fetch_advisor_csv(creds, args.days, dry_run=args.dry_run)
    except RuntimeError as e:
        print(f'[error] {e}')
        return 2

    if args.dry_run:
        print('\n[dry-run] 종료.')
        return 0

    if not rows:
        print('[warn] CSV에서 행을 찾지 못함. 사이트 구조 변경 가능성.')
        print(f'       {DOWNLOAD_DIR} 폴더에 수동 export CSV를 두고 재실행하세요.')
        return 0

    return _persist(rows)


def _persist(rows: List[Dict[str, Any]]) -> int:
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
                    VALUES ('naver_advisor', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        (r.get('query') or '').strip(),
                        (r.get('page') or '').strip(),
                        int(r.get('impressions') or 0),
                        int(r.get('clicks') or 0),
                        float(r.get('ctr') or 0.0),
                        float(r.get('position') or 0.0),
                        r.get('date') or date.today().isoformat(),
                    ),
                )
                inserted += 1
            except Exception as e:
                logger.debug(f'row 적재 실패: {e}')
        conn.commit()
        print(f'\nDB 적재: {inserted}/{len(rows)}건')
        print('--status 로 누적 추세 확인 권장.')
        return 0
    finally:
        if conn:
            conn.close()


if __name__ == '__main__':
    sys.exit(main())
