"""[R1] People Also Ask (PAA) 자연어 질문 수집기.

목적: 자동완성으로 못 잡는 질문형 키워드 (예: "다이어트 한약 효과 있나요?", "한약 부작용?")를
       Google PAA 박스에서 수집. AEO/Cross-User 시대의 핵심 키워드 풀.

전략:
  - 시드 키워드 (config/keywords.json::naver_place + 추가 시드) → Camoufox로 google.com/search 진입
  - PAA 박스 ("Related questions" / "사람들이 함께 묻는 질문") 텍스트 추출
  - 추출된 질문을 다음 라운드 시드로 사용 (3-depth 트리 확장)
  - keyword_insights에 source='paa' + search_intent 자동 분류 + INSERT

운영자 트리거 (cron 안 씀):
  python scripts/pathfinder_paa.py                          # 기본 시드 + depth 2
  python scripts/pathfinder_paa.py --depth 3 --max 200     # 더 깊이
  python scripts/pathfinder_paa.py --seed "청주 다이어트 한약" --depth 2
  python scripts/pathfinder_paa.py --dry-run               # 수집만, DB 적재 안 함

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
from typing import Iterable
from urllib.parse import quote

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
KEYWORDS_PATH = os.path.join(ROOT_DIR, 'config', 'keywords.json')


# 검색 의도 분류 — pathfinder_v3_complete의 _classify_intent와 동일
def classify_intent(kw: str) -> str:
    kw = (kw or '').lower()
    patterns = [
        ('red_flag',     ['부작용', '위험', '단점', '안좋', '문제', '실패', '후회', '사기']),
        ('validation',   ['진짜', '솔직', '찐', '정말', '실제로', '리얼']),
        ('comparison',   ['vs', '보다', '차이', '비교']),
        ('transactional',['가격', '비용', '할인', '예약']),
        ('commercial',   ['추천', '후기', '리뷰', '잘하는']),
        ('informational',['방법', '효과', '원인', '증상', '치료', '기간', '주의']),
        ('navigational', ['위치', '주소', '근처']),
    ]
    for intent, words in patterns:
        if any(w in kw for w in words):
            return intent
    return 'informational'  # PAA는 대부분 정보형


# Google PAA 박스 추출 — 두 가지 패턴
PAA_PATTERNS = [
    # 표준 PAA 박스 (일반 검색)
    re.compile(r'<div[^>]+role="heading"[^>]*>([^<]{5,80}\?)</div>', re.IGNORECASE),
    # related-question-pair 모듈
    re.compile(r'data-q="([^"]{5,80}\?)"'),
    # "사람들이 함께 묻는 질문" 한글 패턴
    re.compile(r'<span[^>]+>([^<]+\?)</span>'),
]


def extract_paa(html: str) -> list[str]:
    found = set()
    for pat in PAA_PATTERNS:
        for m in pat.finditer(html):
            q = m.group(1).strip()
            # 노이즈 필터: 너무 짧거나 광고성
            if 8 <= len(q) <= 80 and '구매' not in q and '광고' not in q:
                found.add(q)
    return list(found)


def load_seeds(seed_arg: str | None) -> list[str]:
    if seed_arg:
        return [seed_arg]
    try:
        with open(KEYWORDS_PATH, 'r', encoding='utf-8') as f:
            kw = json.load(f)
        seeds = list(kw.get('naver_place', []))[:10]
        seeds += list(kw.get('blog_seo', []))[:5]
        return seeds
    except FileNotFoundError:
        # 기본 시드
        return ['청주 한의원', '청주 다이어트 한약', '청주 교통사고 한의원',
                '청주 안면비대칭', '청주 추나']


def save_keywords(rows: Iterable[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec='seconds')
    saved = 0
    for r in rows:
        cur.execute(
            """
            INSERT INTO keyword_insights
                (keyword, source, search_intent, search_volume, document_count,
                 grade, category, created_at, status)
            VALUES (?, 'paa', ?, 0, 0, 'C', ?, ?, 'active')
            ON CONFLICT(keyword) DO UPDATE SET
                source=CASE WHEN keyword_insights.source IS NULL THEN 'paa' ELSE keyword_insights.source END,
                search_intent=excluded.search_intent
            """,
            (r['keyword'], r['intent'], r.get('category', '기타'), now),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', help='단일 시드 키워드')
    parser.add_argument('--depth', type=int, default=2, help='PAA 트리 깊이 (기본 2)')
    parser.add_argument('--max', type=int, default=300, help='총 수집 최대치')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    seeds = load_seeds(args.seed)
    print(f'시드 키워드 {len(seeds)}개, depth={args.depth}, max={args.max}')

    try:
        from scrapers.camoufox_engine import CamoufoxFetcher
    except ImportError as e:
        print(f'CamoufoxFetcher import 실패: {e}')
        return 1

    fetcher = CamoufoxFetcher()
    all_questions: dict[str, dict] = {}
    queue: list[tuple[str, int]] = [(s, 0) for s in seeds]
    visited: set[str] = set()

    try:
        with fetcher:
            while queue and len(all_questions) < args.max:
                kw, depth = queue.pop(0)
                if kw in visited or depth >= args.depth:
                    continue
                visited.add(kw)

                url = f'https://www.google.com/search?q={quote(kw)}&hl=ko&gl=kr'
                html = fetcher.fetch(url, timeout_ms=15000)
                if not html:
                    print(f'  [skip] {kw} — fetch 실패')
                    continue

                questions = extract_paa(html)
                print(f'  [{depth}] "{kw}" → PAA {len(questions)}개')

                for q in questions:
                    if q not in all_questions:
                        all_questions[q] = {
                            'keyword': q,
                            'intent': classify_intent(q),
                            'depth': depth,
                            'parent': kw,
                            'category': '기타',
                        }
                    if depth + 1 < args.depth and q not in visited:
                        queue.append((q, depth + 1))

                time.sleep(2)  # rate limit
    except Exception as e:
        print(f'PAA 수집 중 오류: {e}')

    print()
    print(f'총 {len(all_questions)}개 질문 수집')

    # 의도 분포
    by_intent: dict[str, int] = {}
    for q in all_questions.values():
        by_intent[q['intent']] = by_intent.get(q['intent'], 0) + 1
    print('의도 분포:')
    for intent, cnt in sorted(by_intent.items(), key=lambda x: -x[1]):
        print(f'  {intent:<14} {cnt:>4}')

    print('\n샘플 10건:')
    for q in list(all_questions.values())[:10]:
        print(f"  [{q['intent']:<13}] {q['keyword']}")

    if args.dry_run:
        print('\ndry-run: DB 적재 안 함.')
        return 0

    saved = save_keywords(all_questions.values())
    print(f'\nkeyword_insights 적재: {saved}건 (source=paa)')
    print('다음: 정상 Pathfinder 흐름이 SERP 분석 + 등급 부여 자동 진행')
    return 0


if __name__ == '__main__':
    sys.exit(main())
