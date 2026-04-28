"""[R9] 네이버 클립 댓글 lead 수집기.

배경: 네이버 클립이 의료 콘텐츠 게이트웨이로 부상 (2026년 크리에이터 1만→2만, AI 에디터 출시).
       검색 결과 상단 노출. 클립 영상 댓글 영역에 자연 질문 lead 발생.

전략:
  1. 키워드로 클립 검색 (m.search.naver.com/p/csearch + clip 탭)
  2. 상위 N개 클립 영상 페이지 진입
  3. 댓글 영역에서 자연 질문 패턴 추출
  4. mentions 테이블에 source='naver_clip', source_subtype='clip_comment' 적재

운영자 트리거:
  python scrapers/naver_clip_collector.py --keyword "청주 한의원" --top 20
  python scrapers/naver_clip_collector.py --keyword "다이어트 한약" --top 10 --dry-run

cron 안 씀. 사용자 수동 트리거.
의존: Camoufox (이미 설치됨, scrapers/camoufox_engine.py 활용 가능).
"""
from __future__ import annotations

import argparse
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
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')

# 자연 질문 패턴 (CommentableFilter.INQUIRY_PATTERNS와 정합)
QUESTION_PATTERNS = re.compile(
    r'(추천|어디|궁금|있을까요|있나요|알려주세요|좋은[곳데가]|잘하는|괜찮은|어떤가요|어때요|'
    r'고민|상담|문의|받을\s*수|되는곳|되나요|가능한|어디서|어떻게)'
)


def search_clips(keyword: str, top_n: int) -> list[dict]:
    """[Stub] 키워드로 네이버 클립 검색 → 영상 URL/제목/작성자 리스트.

    실제 구현은 Camoufox로 https://m.search.naver.com/search.naver?where=video&query=... 진입 후
    클립 카드 (data-video-type=clip) 추출. 본 함수는 골격만 제공.
    """
    print(f"[search_clips] '{keyword}' top {top_n} — Camoufox SERP 진입 필요")
    print("  TODO: scrapers/camoufox_engine.py의 SERP 메서드 재사용해 클립 카드 추출")
    print("  대상 URL: https://m.search.naver.com/search.naver?where=video&query=" + quote(keyword))
    return []


def fetch_clip_comments(clip_url: str) -> list[dict]:
    """[Stub] 클립 영상 페이지에서 댓글 추출.

    실제 구현은 Camoufox/Playwright로 영상 페이지 → 댓글 영역 스크롤 → 텍스트 추출.
    네이버 클립 댓글 영역 selector는 m.naver.com 기준 .CommentBox_comment / [data-comment] 류.
    """
    return []


def is_natural_question(text: str) -> bool:
    if not text or len(text) < 8:
        return False
    return bool(QUESTION_PATTERNS.search(text))


def save_comments(rows: Iterable[dict], keyword: str) -> int:
    """mentions 테이블에 클립 댓글 lead 적재."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # mentions 테이블 컬럼 확인 (source_subtype 보장)
    cur.execute("PRAGMA table_info(mentions)")
    cols = [r[1] for r in cur.fetchall()]
    if 'source_subtype' not in cols:
        cur.execute("ALTER TABLE mentions ADD COLUMN source_subtype TEXT")
        conn.commit()

    now = datetime.now().isoformat(timespec='seconds')
    saved = 0

    for r in rows:
        if not is_natural_question(r.get('content', '')):
            continue
        cur.execute("SELECT id FROM mentions WHERE url = ?", (r['url'],))
        if cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO mentions (
                platform, source, source_subtype, source_module,
                title, url, content, summary, author, keyword,
                category, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (
                'naver',
                'naver_clip',
                'clip_comment',
                'clip_collector',
                r.get('clip_title', ''),
                r['url'],
                r.get('content', ''),
                (r.get('content', '') or '')[:300],
                r.get('author', ''),
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
    parser.add_argument('--top', type=int, default=10, help='상위 N개 클립 영상')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    print(f"=== 네이버 클립 댓글 수집 — '{args.keyword}' ===")

    clips = search_clips(args.keyword, args.top)
    if not clips:
        print('클립 검색 결과 0개 (또는 stub 미구현). Camoufox SERP 통합 후 재시도.')
        return 1

    if args.dry_run:
        print(f'\n[dry-run] {len(clips)}개 클립 발견. 댓글 수집 안 함.')
        for c in clips[:5]:
            print(f"  - {c.get('title', '')[:50]} ({c.get('author', '')})")
        return 0

    all_comments: list[dict] = []
    for clip in clips:
        comments = fetch_clip_comments(clip['url'])
        for c in comments:
            c['clip_title'] = clip.get('title', '')
        all_comments.extend(comments)
        time.sleep(2)  # rate limit

    print(f'\n총 댓글 {len(all_comments)}개 추출, 자연 질문 필터링 중...')
    saved = save_comments(all_comments, args.keyword)
    print(f'mentions 테이블 적재: {saved}건 (source_subtype=clip_comment)')

    return 0


if __name__ == '__main__':
    sys.exit(main())
