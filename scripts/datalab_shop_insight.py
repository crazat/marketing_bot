"""[R3] 네이버 DataLab 쇼핑 인사이트 — 카테고리·인구통계 결합 키워드 발굴.

목적: 단순 한약 키워드 → 인구통계 + 상황 결합 ("20대 다이어트 유산균", "임산부 한약 안전")
       DataLab Shopping Insight API (헬스케어 카테고리)로 검색 트렌드 + 연령/성별 분포 수집.

전략:
  - 우리 타겟 키워드 (config/keywords.json) × 인구통계 변형 → DataLab Shopping API 호출
  - 카테고리별 클릭 추이 + 연령/성별 분포 결합
  - keyword_insights에 source='shop_insight' + search_intent + 메타 적재

운영자 트리거:
  python scripts/datalab_shop_insight.py                # 기본 시드 + 8개 변형
  python scripts/datalab_shop_insight.py --dry-run      # API 안 호출, 변형만 출력

API 인증: NAVER_DATALAB_KEYS (이미 .env에 있음, 5개 키 로테이션)
참조: https://developers.naver.com/docs/serviceapi/datalab/shopping/shopping.md

카테고리 ID (네이버 쇼핑 헬스케어):
  50000008 — 건강식품
  50005617 — 다이어트식품
  50000146 — 건강관리용품
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from typing import Optional

import requests

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(THIS_DIR)
sys.path.insert(0, ROOT_DIR)
sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = os.path.join(ROOT_DIR, 'db', 'marketing_data.db')
SECRETS_PATH = os.path.join(ROOT_DIR, 'config', 'secrets.json')

CATEGORIES = {
    '50000008': '건강식품',
    '50005617': '다이어트식품',
    '50000146': '건강관리용품',
}

# 인구통계 변형 — Cross-User 모델로 상황 결합
DEMOGRAPHIC_VARIATIONS = [
    '20대', '30대', '40대',
    '여성', '남성',
    '임산부', '산후',
    '직장인', '학생',
]


def load_datalab_keys() -> list[tuple[str, str]]:
    with open(SECRETS_PATH, 'r', encoding='utf-8') as f:
        s = json.load(f)
    keys = s.get('NAVER_DATALAB_KEYS') or []
    if isinstance(keys, list):
        return [(k.get('client_id'), k.get('client_secret')) for k in keys if k.get('client_id')]
    # 폴백: 단일 NAVER_CLIENT_ID/SECRET
    return [(s['NAVER_CLIENT_ID'], s['NAVER_CLIENT_SECRET'])]


def datalab_shopping_keywords(
    category_id: str,
    keywords: list[str],
    start_date: str,
    end_date: str,
    client_id: str,
    client_secret: str,
) -> Optional[dict]:
    """카테고리 내 키워드 클릭 추이 조회."""
    url = 'https://openapi.naver.com/v1/datalab/shopping/category/keywords'
    headers = {
        'X-Naver-Client-Id': client_id,
        'X-Naver-Client-Secret': client_secret,
        'Content-Type': 'application/json',
    }
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'timeUnit': 'month',
        'category': category_id,
        'keyword': [{'name': kw, 'param': [kw]} for kw in keywords[:5]],  # API 최대 5개
        'device': '',
        'gender': '',
        'ages': [],
    }
    try:
        r = requests.post(url, headers=headers, json=body, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f'  [API err] status={r.status_code} body={r.text[:200]}')
    except Exception as e:
        print(f'  [API err] {e}')
    return None


def expand_seeds(seeds: list[str]) -> list[dict]:
    """시드 × 인구통계 변형 — 8N개 키워드 후보 생성."""
    out = []
    for s in seeds:
        for d in DEMOGRAPHIC_VARIATIONS:
            kw = f'{d} {s}'.strip()
            out.append({'keyword': kw, 'parent': s, 'demo': d})
    return out


def save_keywords(rows: list[dict], category_name: str) -> int:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    now = datetime.now().isoformat(timespec='seconds')
    saved = 0
    for r in rows:
        # ratio가 일정 이상이면 적재 (낮은 트렌드는 노이즈)
        if r.get('ratio', 0) < 5:
            continue
        cur.execute(
            """
            INSERT INTO keyword_insights
                (keyword, source, search_intent, search_volume,
                 grade, category, created_at, status)
            VALUES (?, 'shop_insight', 'commercial', 0,
                    'C', ?, ?, 'active')
            ON CONFLICT(keyword) DO UPDATE SET
                source=CASE WHEN keyword_insights.source IS NULL THEN 'shop_insight'
                            ELSE keyword_insights.source END,
                category=excluded.category
            """,
            (r['keyword'], category_name, now),
        )
        saved += 1
    conn.commit()
    conn.close()
    return saved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--seeds', nargs='*', help='시드 키워드 (없으면 기본)')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()

    seeds = args.seeds or ['다이어트', '한약', '면역', '체질', '비염']
    expanded = expand_seeds(seeds)
    print(f'시드 {len(seeds)}개 × 변형 {len(DEMOGRAPHIC_VARIATIONS)}개 = {len(expanded)} 후보')

    if args.dry_run:
        print('\n변형 샘플:')
        for r in expanded[:15]:
            print(f"  {r['keyword']}")
        return 0

    keys = load_datalab_keys()
    if not keys:
        print('NAVER_DATALAB_KEYS 없음. secrets.json 확인.')
        return 1

    end = datetime.now().date()
    start = end - timedelta(days=180)
    sd = start.strftime('%Y-%m-%d')
    ed = end.strftime('%Y-%m-%d')

    all_results: list[dict] = []
    for cat_id, cat_name in CATEGORIES.items():
        print(f'\n=== {cat_name} ({cat_id}) ===')
        # 변형을 5개씩 청크
        for i in range(0, len(expanded), 5):
            chunk = expanded[i:i+5]
            kws = [r['keyword'] for r in chunk]
            cid, csec = keys[i % len(keys)]  # 키 로테이션
            res = datalab_shopping_keywords(cat_id, kws, sd, ed, cid, csec)
            if not res:
                continue
            for j, item in enumerate(res.get('results', [])):
                # ratio 산정: 최근 6개월 평균
                data_points = item.get('data', [])
                if data_points:
                    avg_ratio = sum(p.get('ratio', 0) for p in data_points) / len(data_points)
                else:
                    avg_ratio = 0
                chunk[j]['ratio'] = round(avg_ratio, 2)
                chunk[j]['category'] = cat_name
            all_results.extend(chunk)
            time.sleep(0.5)

    print()
    print(f'총 {len(all_results)}건 트렌드 데이터 수집')
    high_ratio = [r for r in all_results if r.get('ratio', 0) >= 5]
    print(f'유효 키워드 (ratio>=5): {len(high_ratio)}')

    if high_ratio:
        print('\n샘플 top 10 (ratio 순):')
        for r in sorted(high_ratio, key=lambda x: -x.get('ratio', 0))[:10]:
            print(f"  [{r['category']:<10}] {r['keyword']:<28} ratio={r['ratio']}")

    saved = save_keywords(all_results, '기타')
    print(f'\nkeyword_insights 적재: {saved}건 (source=shop_insight)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
