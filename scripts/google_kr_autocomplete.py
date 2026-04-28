"""[External Signals R3-9] Google 한국어 자동완성 시드 키워드 발굴.

배경: Google 한국어 시장 점유율 약 35% (2026), 네이버와 다른 검색 의도 노출.
       suggestqueries.google.com (firefox client, hl=ko, gl=kr) 무료, 인증 X.

운영자 트리거 (cron 안 씀):
  python scripts/google_kr_autocomplete.py
  python scripts/google_kr_autocomplete.py --seeds "청주 한의원,청주 다이어트"
  python scripts/google_kr_autocomplete.py --top 30 --dry-run

적재 위치: keyword_insights (source='google_kr_autocomplete', grade='C')
시드 기본값: config/keywords.json::naver_place + blog_seo
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from typing import List, Optional

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
KEYWORDS_PATH = os.path.join(ROOT_DIR, 'config', 'keywords.json')

GOOGLE_AUTOCOMPLETE_URL = "https://suggestqueries.google.com/complete/search"


def load_seed_keywords() -> List[str]:
    seeds: List[str] = []
    try:
        with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for cat in ('naver_place', 'blog_seo'):
            for kw in data.get(cat, []):
                if kw and kw not in seeds:
                    seeds.append(kw)
    except Exception as e:
        print(f'  [warn] keywords.json 로드 실패: {e}')
    return seeds


def fetch_suggestions(keyword: str, top: int = 20) -> List[str]:
    """Google 자동완성 (firefox client, JSON 응답)."""
    params = {
        'client': 'firefox',
        'q': keyword,
        'hl': 'ko',
        'gl': 'kr',
    }
    suggestions: List[str] = []
    try:
        r = requests.get(GOOGLE_AUTOCOMPLETE_URL, params=params, timeout=10,
                         headers={'User-Agent': 'Mozilla/5.0'})
        if r.status_code != 200:
            print(f'  [HTTP {r.status_code}] {keyword}')
            return suggestions
        # firefox client 응답: ["query", ["sug1", "sug2", ...]]
        try:
            data = r.json()
            if isinstance(data, list) and len(data) >= 2 and isinstance(data[1], list):
                for s in data[1]:
                    if isinstance(s, str) and s != keyword and s not in suggestions:
                        suggestions.append(s)
                    if len(suggestions) >= top:
                        break
        except (json.JSONDecodeError, ValueError):
            # 파싱 실패 시 간단 정규식 폴백
            matches = re.findall(r'"([^"]{2,80})"', r.text)
            for m in matches:
                if m and m != keyword and m not in suggestions:
                    suggestions.append(m)
                if len(suggestions) >= top:
                    break
    except Exception as e:
        print(f'  [err] {keyword}: {e}')
    return suggestions[:top]


def upsert_keyword(conn: sqlite3.Connection, kw: str, parent: str) -> bool:
    cur = conn.cursor()
    # UNIQUE(keyword, source) — seed_government_keywords의 인덱스가 있으면 활용
    try:
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_keyword_insights_keyword_source
            ON keyword_insights(keyword, source)
        """)
    except Exception:
        pass
    try:
        cur.execute(
            """
            INSERT INTO keyword_insights
                (keyword, source, grade, search_intent, region, category, memo, created_at)
            VALUES (?, 'google_kr_autocomplete', 'C', 'unknown', '청주', 'google_자동완성', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(keyword, source) DO NOTHING
            """,
            (kw, f'parent={parent}'),
        )
        return cur.rowcount > 0
    except sqlite3.IntegrityError:
        return False
    except Exception as e:
        print(f'  [upsert err] {kw}: {e}')
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', help='쉼표 구분 시드 키워드 직접 지정 (없으면 keywords.json 사용)')
    parser.add_argument('--top', type=int, default=20)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.seeds:
        seeds = [s.strip() for s in args.seeds.split(',') if s.strip()]
    else:
        seeds = load_seed_keywords()

    if not seeds:
        print('시드 키워드 없음. --seeds 또는 config/keywords.json 확인.')
        return 1

    print(f'[google-autocomplete] 시드 {len(seeds)}개, top={args.top}')

    conn = sqlite3.connect(DB_PATH) if not args.dry_run else None
    try:
        all_suggestions: List[tuple[str, str]] = []  # (kw, parent)
        for seed in seeds:
            sugs = fetch_suggestions(seed, top=args.top)
            for s in sugs:
                all_suggestions.append((s, seed))
            print(f'  {seed:<25} → {len(sugs)}건')

        # dedup
        seen = set()
        unique = []
        for kw, parent in all_suggestions:
            if kw in seen:
                continue
            seen.add(kw)
            unique.append((kw, parent))

        print(f'\n  총 발굴 {len(unique)}건 (중복 제거 후)')
        if args.dry_run:
            for kw, parent in unique[:20]:
                print(f'  - {kw}   (← {parent})')
            if len(unique) > 20:
                print(f'  ... 외 {len(unique) - 20}건')
            print('\n  [dry-run] 적재 X')
            return 0

        new_kw = 0
        for kw, parent in unique:
            if upsert_keyword(conn, kw, parent):
                new_kw += 1
        conn.commit()
        print(f'\n  신규 적재: {new_kw}건 (source=google_kr_autocomplete)')
    finally:
        if conn is not None:
            conn.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
