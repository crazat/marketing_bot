"""[R5] Threads (Meta) 한국 멘션 수집기.

배경: Threads 한국 MAU 543만, 25-44세 70%, +500% 성장. 솔직 후기 문화.
       청주 한의원 잠재고객(여성 다이어트 핵심 타겟) 멘션 폭증 중.

전략:
  - https://www.threads.net/search?q=... 공개 검색 (로그인 없이 접근 가능한 영역)
  - Camoufox로 SERP 진입 (Meta 봇 탐지 회피)
  - 키워드 멘션 게시물 + 작성자 + reply count 추출
  - mentions 테이블에 source='threads', source_subtype='threads_post' 적재

운영자 트리거:
  python scrapers/threads_collector.py --keyword "청주 한의원"
  python scrapers/threads_collector.py --keyword "다이어트 한약" --top 50
  python scrapers/threads_collector.py --dry-run

ToS: Threads 공개 게시물 수집 합법(Scrapfly·ScrapeCreators 등 상업 운영). rate limit 1 req/sec, 인증 우회 금지.
의존: scrapers/camoufox_engine.py (CamoufoxFetcher).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from urllib.parse import quote

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


# Threads 게시물 패턴 — JSON-LD 또는 inline data
# Threads는 React 기반 SPA + window.__INITIAL_DATA__로 데이터 주입
THREADS_POST_PATTERNS = [
    re.compile(r'"text":"([^"]{20,500})"'),  # post text
    re.compile(r'"username":"([a-z0-9_.]+)"'),
]


def _try_extract_posts(html: str) -> list[dict]:
    """[Stub] Threads SERP HTML에서 게시물 추출.

    실제 구현: Threads SPA의 window.__INITIAL_DATA__ JSON 파싱.
    또는 https://www.threads.net/api/graphql 비공식 endpoint 사용 (ScrapeCreators 패턴 참조).

    Threads 페이지 패턴은 자주 변경됨 → 셀렉터 강건화 필요.
    """
    posts: list[dict] = []
    # 매우 단순한 휴리스틱 — 실제 운영 시 보강 필요
    text_matches = THREADS_POST_PATTERNS[0].findall(html)
    user_matches = THREADS_POST_PATTERNS[1].findall(html)
    for i, text in enumerate(text_matches[:50]):
        username = user_matches[i] if i < len(user_matches) else 'unknown'
        posts.append({
            'text': text.replace('\\n', ' ').strip(),
            'username': username,
            'url': f'https://www.threads.net/@{username}',
        })
    return posts


def _is_relevant(text: str, keyword: str) -> bool:
    if not text:
        return False
    # 키워드 부분 매칭 (공백 처리)
    kw_clean = keyword.replace(' ', '')
    text_clean = text.replace(' ', '')
    return keyword in text or kw_clean in text_clean


def save_threads_posts(posts: list[dict], keyword: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("PRAGMA table_info(mentions)")
    cols = [r[1] for r in cur.fetchall()]
    if 'source_subtype' not in cols:
        cur.execute("ALTER TABLE mentions ADD COLUMN source_subtype TEXT")
        conn.commit()

    now = datetime.now().isoformat(timespec='seconds')
    saved = 0

    for p in posts:
        if not _is_relevant(p.get('text', ''), keyword):
            continue
        cur.execute("SELECT id FROM mentions WHERE url = ?", (p['url'],))
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO mentions (
                platform, source, source_subtype, source_module,
                title, url, content, summary, author, keyword,
                category, status, created_at
            ) VALUES (?, 'threads', 'threads_post', 'threads_collector',
                      ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                'threads',
                p.get('text', '')[:200],
                p['url'],
                p.get('text', ''),
                p.get('text', '')[:300],
                p.get('username', ''),
                keyword,
                '기타',
                now,
            ),
        )
        saved += 1

    conn.commit()
    conn.close()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keyword', required=True)
    parser.add_argument('--top', type=int, default=30)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f"=== Threads 멘션 수집 — '{args.keyword}' ===")

    try:
        from scrapers.camoufox_engine import CamoufoxFetcher
    except ImportError as e:
        print(f'CamoufoxFetcher import 실패: {e}')
        return 1

    fetcher = CamoufoxFetcher()
    url = f'https://www.threads.net/search?q={quote(args.keyword)}&serp_type=default'

    try:
        with fetcher:
            print(f'fetch: {url}')
            html = fetcher.fetch(url, timeout_ms=20000,
                                 wait_selector='div[data-pressable-container]')
    except Exception as e:
        print(f'Camoufox 진입 실패: {e}')
        return 1

    if not html:
        print('HTML 비어있음. Threads 봇 탐지 또는 selector 변경. 재시도 권장.')
        return 1

    posts = _try_extract_posts(html)
    relevant = [p for p in posts if _is_relevant(p.get('text', ''), args.keyword)]
    print(f'추출 {len(posts)}건, 키워드 매칭 {len(relevant)}건')

    if args.dry_run:
        print('\n샘플 5건:')
        for p in relevant[:5]:
            print(f"  @{p['username']}: {p['text'][:60]}")
        return 0

    saved = save_threads_posts(relevant[:args.top], args.keyword)
    print(f'mentions 신규 적재: {saved}건 (source_subtype=threads_post)')
    print('다음: AI 분류 권장 — python scripts/ai_ad_classify_submit.py --limit ' + str(saved))
    return 0


if __name__ == '__main__':
    sys.exit(main())
