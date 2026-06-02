"""[R6] AEO (Answer Engine Optimization) 모니터링 — LLM 검색에서 우리 한의원 노출 추적.

배경: 2026/02 ChatGPT 한국 MAU 1,446만 (4배↑). HubSpot 오가닉 트래픽 -27%.
       "강남 흉터 상담 기준" 같은 자연어 쿼리에서 LLM이 우리/경쟁사를 어떻게 답변하는지 = 새 KPI.

전략:
  - 핵심 20개 키워드를 Codex CLI에 자연어 질의 (Google Search grounding 사용)
  - 답변에서 우리 한의원/경쟁사 이름 등장 카운트 + 순서
  - aeo_visibility 테이블에 적재
  - 직전 대비 노출/노출 빈도 변화 보고

운영자 트리거 (cron 안 씀, 주 1회 정도 권장):
  python scripts/aeo_visibility.py                  # 기본 20개 키워드
  python scripts/aeo_visibility.py --keywords "강남 흉터 상담 기준,강남 다이어트 한약 상담 기준"
  python scripts/aeo_visibility.py --status         # 직전 결과만

비용: Codex CLI 2.5 Flash Lite + grounding ~$0.10/1M tokens. 20 쿼리 × 2k tokens = $0.0040/회.
       월 4회 = $0.02/월. Perplexity 추가 시에만 $5-10/월.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from typing import Optional

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.path.insert(0, os.path.join(ROOT_DIR, 'marketing_bot_web', 'backend'))
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
TARGETS_PATH = os.path.join(ROOT_DIR, 'config', 'targets.json')
BUSINESS_PATH = os.path.join(ROOT_DIR, 'config', 'business_profile.json')

# 기본 모니터링 키워드 (자연어 질의 형식)
DEFAULT_QUERIES = [
    "강남 흉터 상담 기준 알려줘",
    "선릉 패인 흉터 회복조건 상담",
    "강남 여드름흉터 상담 전 확인할 것",
    "박스카 흉터 새살침 접근 범위 상담",
    "롤링 흉터 회복 방향 상담",
    "아이스픽 흉터 상담 기준 강남",
    "강남 얼굴비대칭 상담 기준",
    "선릉 안면비대칭 상담 기준",
    "얼굴 비대칭과 턱관절 긴장 기록 기준",
    "강남 시술 후 예민한 피부 회복 순서",
    "흉터 상담 전 피부 준비도 확인",
    "RECOVER NOTE 흉터 상담",
    "리커버한의원 강남 어디야",
    "리커버 강남 흉터 상담 기준",
    "강남 다이어트 한약 상담 기준",
    "선릉 비만 한약 상담 기준",
    "식욕조절 상담 기준 강남",
    "체중감량 한약 상담 전 확인할 것",
    "강남 흉터 상담 포함 제외 항목",
    "선릉역 흉터 상담 기준",
    "역삼 흉터 회복 조건",
    "삼성역 얼굴비대칭 상담",
    "강남 흉터 상담 기록 확인 기준",
    "강남 흉터 상담 방식 차이",
]


def ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS aeo_visibility (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            query_keyword TEXT NOT NULL,
            llm_provider TEXT NOT NULL,
            response_text TEXT,
            our_clinic_mentioned INTEGER DEFAULT 0,
            our_clinic_position INTEGER,
            competitors_mentioned TEXT,
            citation_urls TEXT,
            tokens_used INTEGER,
            checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_aeo_query ON aeo_visibility(query_keyword, checked_at DESC);
        """
    )


def load_self_aliases() -> list[str]:
    try:
        with open(BUSINESS_PATH, 'r', encoding='utf-8') as f:
            bp = json.load(f)
        names = set()
        business = bp.get('business', {}) or {}
        for k in ('clinic_name', 'name', 'business_name'):
            v = bp.get(k)
            if v:
                names.add(v)
            v = business.get(k)
            if v:
                names.add(v)
        for k in ('short_name', 'english_name', 'blog_id'):
            v = business.get(k)
            if v:
                names.add(v)
        for v in bp.get('aliases', []) or []:
            names.add(v)
        for v in (bp.get('self_exclusion', {}) or {}).get('blog_authors', []) or []:
            names.add(v)
        for v in (bp.get('self_exclusion', {}) or {}).get('title_keywords', []) or []:
            names.add(v)
        return [n for n in names if n and len(n) >= 2]
    except (FileNotFoundError, json.JSONDecodeError):
        return ['리커버한의원 강남', '리커버 강남', 'RECOVER 강남']


def load_competitor_names() -> list[str]:
    try:
        with open(TARGETS_PATH, 'r', encoding='utf-8') as f:
            cfg = json.load(f)
        return [t['name'] for t in cfg.get('targets', []) if t.get('name')]
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def query_codex(prompt: str) -> dict:
    """Codex CLI Flash Lite + Google Search grounding으로 자연어 질의."""
    try:
        from services.ai_client import ai_generate
    except ImportError as e:
        return {'error': f'ai_client 임포트 실패: {e}'}

    enriched = (
        f'{prompt}\n\n'
        '효능 보장, 가격 유인, 전후사진, 과장 표현은 피하고 확인 기준 중심으로 답변해주세요. '
        '공개 정보로 확인되는 한의원 이름과 위치가 있다면 출처 맥락과 함께 중립적으로 언급해주세요.'
    )
    try:
        text = ai_generate(enriched, temperature=0.3, max_tokens=800)
        return {'text': text or '', 'provider': 'codex_cli'}
    except Exception as e:
        return {'error': str(e)}


def analyze_response(text: str, self_aliases: list[str], competitors: list[str]) -> dict:
    """답변에서 우리/경쟁사 노출 + 순서 분석."""
    lower = text.lower() if text else ''

    our_mentioned = 0
    our_first_pos = None
    for alias in self_aliases:
        if alias.lower() in lower:
            our_mentioned = 1
            idx = lower.index(alias.lower())
            if our_first_pos is None or idx < our_first_pos:
                our_first_pos = idx

    competitor_mentions = []
    for name in competitors:
        if name.lower() in lower:
            idx = lower.index(name.lower())
            competitor_mentions.append({'name': name, 'pos': idx})
    competitor_mentions.sort(key=lambda x: x['pos'])

    # 순서 (rank): 우리가 답변 내 등장 순서
    if our_first_pos is None:
        our_rank = None
    else:
        ranks_before = sum(1 for c in competitor_mentions if c['pos'] < our_first_pos)
        our_rank = ranks_before + 1

    return {
        'our_clinic_mentioned': our_mentioned,
        'our_clinic_position': our_rank,
        'competitors_mentioned': [c['name'] for c in competitor_mentions[:10]],
    }


def show_status() -> int:
    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    cur = conn.cursor()
    rows = cur.execute(
        """
        SELECT query_keyword,
               our_clinic_mentioned, our_clinic_position,
               competitors_mentioned, checked_at
          FROM aeo_visibility
         WHERE id IN (
             SELECT MAX(id) FROM aeo_visibility GROUP BY query_keyword
         )
         ORDER BY checked_at DESC
        """
    ).fetchall()
    if not rows:
        print('직전 측정 없음. python scripts/aeo_visibility.py 실행 후 재시도.')
        return 0
    print('=== AEO 노출 상태 (최신) ===')
    print(f"총 {len(rows)}개 쿼리 추적 중\n")
    print(f'{"쿼리":<30} {"우리 노출":<10} {"순위":<6} {"경쟁사":<6}')
    print('-' * 70)
    for q, mentioned, pos, competitors_json, checked in rows:
        comps = json.loads(competitors_json) if competitors_json else []
        ours = '✅' if mentioned else '❌'
        rank = f'{pos}위' if pos else '-'
        print(f'{q[:28]:<30} {ours:<10} {rank:<6} {len(comps)}개')
    conn.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--keywords', help='쉼표 구분 키워드 (없으면 기본 20개)')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    if args.status:
        return show_status()

    queries = (
        [k.strip() for k in args.keywords.split(',') if k.strip()]
        if args.keywords else DEFAULT_QUERIES
    )

    self_aliases = load_self_aliases()
    competitors = load_competitor_names()
    print(f'쿼리 {len(queries)}개, 자기 한의원 별칭 {len(self_aliases)}개, 경쟁사 {len(competitors)}곳')

    if args.dry_run:
        print('\n쿼리 샘플 5건:')
        for q in queries[:5]:
            print(f'  - {q}')
        return 0

    conn = sqlite3.connect(DB_PATH)
    ensure_table(conn)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec='seconds')

    mentioned_count = 0
    for q in queries:
        print(f'\n[Codex CLI] "{q}"')
        res = query_codex(q)
        if 'error' in res:
            print(f'  err: {res["error"]}')
            continue

        analysis = analyze_response(res['text'], self_aliases, competitors)
        ours = '✅ 노출' if analysis['our_clinic_mentioned'] else '❌ 미노출'
        rank = f' (순위 {analysis["our_clinic_position"]})' if analysis['our_clinic_position'] else ''
        print(f'  {ours}{rank}, 경쟁사 {len(analysis["competitors_mentioned"])}곳 언급')

        cur.execute(
            """
            INSERT INTO aeo_visibility
                (query_keyword, llm_provider, response_text,
                 our_clinic_mentioned, our_clinic_position,
                 competitors_mentioned, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                q, res['provider'], res['text'][:5000],
                analysis['our_clinic_mentioned'], analysis['our_clinic_position'],
                json.dumps(analysis['competitors_mentioned'], ensure_ascii=False),
                now,
            ),
        )
        if analysis['our_clinic_mentioned']:
            mentioned_count += 1

    conn.commit()
    conn.close()

    print()
    print('=' * 60)
    print(f'AEO 노출 측정 완료: {mentioned_count}/{len(queries)} 쿼리에서 우리 한의원 노출')
    print(f'노출률: {mentioned_count / len(queries) * 100:.1f}%')
    print('\n다음: --status로 추세 확인 권장')
    return 0


if __name__ == '__main__':
    sys.exit(main())
