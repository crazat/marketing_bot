"""[R4] 카카오맵 리뷰 수집기.

배경: 카카오맵 MAU 1,282만, 인증 후기 우선 노출(2025-12부터). 청주 한의원 별점·후기 직접 노출.
       부정 리뷰 조기 감지 + 경쟁사 평점 추적.

전략:
  - place.map.kakao.com 검색 진입 (Selenium/Camoufox)
  - 한의원 상세 페이지 → 후기 탭 → 별점·후기 텍스트 추출
  - kakao_map_reviews 신규 테이블 적재 + 부정 리뷰는 mentions로 (source_subtype='kakao_review')

운영자 트리거 (cron 안 씀):
  python scrapers/kakao_map_reviews.py --keyword "청주 한의원" --top 10
  python scrapers/kakao_map_reviews.py --place-id 12345 --reviews 50
  python scrapers/kakao_map_reviews.py --dry-run

의존: Selenium (cafe_spy 패턴 재사용) 또는 Camoufox.
ToS: 카카오맵 공개 후기는 robots.txt 허용 영역. 인증 우회/대량 수집 금지.
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
from typing import Optional
from urllib.parse import quote

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS kakao_map_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            place_id TEXT,
            place_name TEXT,
            star_rating REAL,
            review_text TEXT,
            review_date TEXT,
            reviewer_id TEXT,
            sentiment TEXT,
            content_hash TEXT UNIQUE,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_kakao_review_place ON kakao_map_reviews(place_id, scraped_at DESC);
        """
    )


def _sentiment_heuristic(text: str) -> str:
    """간단한 룰 기반 감성. AI 분류는 별도 파이프라인."""
    if not text:
        return 'neutral'
    neg = ['최악', '환불', '불친절', '실망', '거지같', '돈낭비', '효과없', '추천안', '안가']
    pos = ['친절', '추천', '효과', '만족', '깨끗', '꼼꼼', '잘하', '좋았', '굿']
    n = sum(1 for w in neg if w in text)
    p = sum(1 for w in pos if w in text)
    if n > p:
        return 'negative'
    if p > n:
        return 'positive'
    return 'neutral'


def search_kakao_places(keyword: str, top_n: int) -> list[dict]:
    """[Stub] 카카오맵 검색 → 장소 리스트 (place_id, name, rating, review_count).

    실제 구현: place.map.kakao.com/search 진입 → li.PlaceItem 추출.
    또는 https://m.search.daum.net/kakao?w=tot&q=... → 카카오맵 카드 영역.

    임시: 기존 targets.json 경쟁사 한의원으로 stub.
    """
    print(f"[search_kakao_places] '{keyword}' top {top_n} — Selenium 진입 필요")
    print('  대상 URL: https://place.map.kakao.com/search/' + quote(keyword))
    return []


def fetch_kakao_reviews(place_id: str, max_reviews: int = 50) -> list[dict]:
    """[Stub] 카카오맵 장소 상세 페이지에서 후기 추출.

    실제: place.map.kakao.com/{place_id}#comment 진입 → .CommentBox / data-comment-id 추출.
    """
    print(f'  [fetch] place_id={place_id} — 상세 페이지 진입 필요')
    return []


def hash_review(place_id: str, text: str, date: str) -> str:
    import hashlib
    return hashlib.md5(f'{place_id}|{text[:200]}|{date}'.encode('utf-8')).hexdigest()[:16]


def save_reviews(rows: list[dict]) -> int:
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    cur = conn.cursor()
    saved = 0
    for r in rows:
        h = hash_review(r['place_id'], r['review_text'], r.get('review_date', ''))
        try:
            cur.execute(
                """
                INSERT INTO kakao_map_reviews
                    (place_id, place_name, star_rating, review_text, review_date,
                     reviewer_id, sentiment, content_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    r['place_id'], r['place_name'], r.get('star_rating'),
                    r['review_text'], r.get('review_date'), r.get('reviewer_id'),
                    _sentiment_heuristic(r['review_text']), h,
                ),
            )
            saved += 1
        except sqlite3.IntegrityError:
            pass  # 중복
    conn.commit()
    conn.close()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keyword', help='검색 키워드 (예: 청주 한의원)')
    parser.add_argument('--place-id', help='특정 장소 ID')
    parser.add_argument('--top', type=int, default=10)
    parser.add_argument('--reviews', type=int, default=50, help='장소당 최대 리뷰 수')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if not args.keyword and not args.place_id:
        parser.error('--keyword 또는 --place-id 필요')

    if args.place_id:
        places = [{'place_id': args.place_id, 'place_name': args.place_id}]
    else:
        places = search_kakao_places(args.keyword, args.top)

    if not places:
        print('카카오맵 검색 결과 없음 (또는 stub 미구현). Selenium SERP 통합 후 재시도.')
        print('TODO: scrapers/cafe_spy.py의 driver 패턴 재사용 권장.')
        return 1

    if args.dry_run:
        print(f'[dry-run] {len(places)}개 장소 대상')
        for p in places[:5]:
            print(f"  - {p['place_name']} ({p['place_id']})")
        return 0

    all_reviews: list[dict] = []
    for p in places:
        revs = fetch_kakao_reviews(p['place_id'], args.reviews)
        for rv in revs:
            rv['place_id'] = p['place_id']
            rv['place_name'] = p['place_name']
        all_reviews.extend(revs)
        time.sleep(2)

    saved = save_reviews(all_reviews)
    neg = sum(1 for r in all_reviews if _sentiment_heuristic(r['review_text']) == 'negative')
    print(f'\n수집 {len(all_reviews)}건, DB 신규 적재 {saved}건')
    print(f'부정 리뷰: {neg}건 — competitor_reviews 테이블의 sentiment 분석과 결합 권장')
    return 0


if __name__ == '__main__':
    sys.exit(main())
