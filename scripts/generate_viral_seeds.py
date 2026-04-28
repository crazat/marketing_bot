"""[2026-04-28] Pathfinder S+A → viral_hunter 시드 자동 생성.

매번 사람이 18개씩 손으로 골라 미용 카테고리 누락하던 문제 해결.
business_profile.json::categories.main 기반 균형 추출.

조건:
  - grade IN ('S', 'A')
  - 청주 권역 (region 매칭 또는 keyword에 청주/지역동명 포함)
  - 미용 주력 카테고리 우선
  - search_volume >= 50
  - 자기 한의원(규림) 제외
  - 카테고리별 quota로 균형

출력:
  - logs/viral_seeds_curated.json (덮어쓰기, 백업 자동)
  - 콘솔에 카테고리별 시드 목록 출력
"""
from __future__ import annotations
import json
import sqlite3
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

DB_PATH = 'db/marketing_data.db'
SEEDS_PATH = Path('logs/viral_seeds_curated.json')

# 청주 권역 region/keyword 매칭
CHEONGJU_REGIONS = ('청주', '오창', '오송', '흥덕구', '상당구', '서원구', '청원구')
CHEONGJU_DONGS = (
    '가경', '복대', '용암', '분평', '금천', '사천', '내덕', '봉명', '율량', '사창',
    '운천', '서원', '용정', '월오', '강서', '오근장', '미평', '수곡', '사직', '성안길',
    '지웰시티',
)

# 카테고리별 quota (business_profile.json::categories.main 우선순위 반영)
# 미용 주력 (LP 페이지 5/6) → 큰 quota
# pathfinder category 텍스트 → 표준 카테고리 매핑
CATEGORY_QUOTAS = {
    '다이어트': 7,
    '피부':     7,   # 피부/여드름, 여드름/피부, 알레르기/아토피, 리프팅 등
    '탈모':     5,
    '비대칭':   5,   # 안면비대칭, 안면비대칭_교정 등
    '교정':     3,   # 체형교정 (별도)
    '교통사고': 5,
    '통증':     4,   # 통증, 통증/디스크
    '추나':     3,
    '두통':     2,
    '소화':     2,
    '호흡':     2,   # 비염 등
}

# 카테고리 매핑 (pathfinder category 텍스트 → quota 키)
def category_bucket(raw_cat: str | None, keyword: str) -> str | None:
    """pathfinder category + keyword 텍스트로 quota 버킷 결정."""
    cat = (raw_cat or '').lower()
    kw = keyword.lower()

    # 1. category 명시 매칭
    if any(t in cat for t in ('다이어트', '비만')):
        return '다이어트'
    if any(t in cat for t in ('탈모', '모발')):
        return '탈모'
    if any(t in cat for t in ('안면비대칭', '비대칭')):
        return '비대칭'
    if '체형교정' in cat or '교정' == cat:
        return '교정'
    if '교통사고' in cat:
        return '교통사고'
    if any(t in cat for t in ('피부', '여드름', '아토피', '리프팅', '알레르기')):
        return '피부'
    if '추나' in cat:
        return '추나'
    if any(t in cat for t in ('통증', '디스크')):
        return '통증'
    if '두통' in cat or '어지럼' in cat:
        return '두통'
    if '소화' in cat or '위장' in cat:
        return '소화'
    if '비염' in cat or '호흡' in cat:
        return '호흡'

    # 2. keyword 텍스트 폴백
    if any(t in kw for t in ('다이어트', '비만', '살빼', '감비')):
        return '다이어트'
    if any(t in kw for t in ('여드름', '피부', '아토피', '리프팅')):
        return '피부'
    if '탈모' in kw:
        return '탈모'
    if '비대칭' in kw or '안면교정' in kw:
        return '비대칭'
    if '체형교정' in kw or '척추교정' in kw or '자세교정' in kw or '골반교정' in kw:
        return '교정'
    if '교통사고' in kw:
        return '교통사고'
    if '추나' in kw:
        return '추나'
    if '거북목' in kw or '일자목' in kw:
        return '통증'
    if '디스크' in kw or '허리' in kw or '어깨' in kw:
        return '통증'
    if '두통' in kw or '편두통' in kw or '어지럼' in kw:
        return '두통'
    if '소화' in kw or '위장' in kw:
        return '소화'
    if '비염' in kw or '천식' in kw:
        return '호흡'

    return None


def is_cheongju(region: str | None, keyword: str) -> bool:
    if region and any(r in region for r in CHEONGJU_REGIONS):
        return True
    if any(r in keyword for r in CHEONGJU_REGIONS):
        return True
    if any(d in keyword for d in CHEONGJU_DONGS):
        return True
    return False


def is_self_clinic(keyword: str) -> bool:
    """규림한의원 자체 키워드 제외."""
    kw = keyword.lower()
    return '규림' in kw or 'kyurim' in kw


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # S+A 청주 권역 + vol>=50, 카테고리 매칭되는 것만
    rows = c.execute("""
        SELECT keyword, grade, category, region, search_volume, document_count
        FROM keyword_insights
        WHERE grade IN ('S', 'A')
          AND search_volume >= 50
        ORDER BY search_volume DESC
    """).fetchall()

    # 버킷별 분류
    buckets: dict[str, list[dict]] = {k: [] for k in CATEGORY_QUOTAS}
    rejected = {'self': 0, 'non_cheongju': 0, 'no_bucket': 0}

    for r in rows:
        kw = r['keyword']
        if is_self_clinic(kw):
            rejected['self'] += 1
            continue
        if not is_cheongju(r['region'], kw):
            rejected['non_cheongju'] += 1
            continue
        bucket = category_bucket(r['category'], kw)
        if not bucket or bucket not in buckets:
            rejected['no_bucket'] += 1
            continue
        if len(buckets[bucket]) >= CATEGORY_QUOTAS[bucket]:
            continue  # quota 초과
        buckets[bucket].append({
            'keyword': kw,
            'grade': r['grade'],
            'category': r['category'],
            'volume': r['search_volume'],
        })

    conn.close()

    # 결과 출력
    print('=' * 72)
    print(f'pathfinder S+A → viral_hunter 시드 자동 생성 — {datetime.now():%Y-%m-%d %H:%M}')
    print('=' * 72)
    total = sum(len(v) for v in buckets.values())
    print(f'\n총 {total}개 시드 추출\n')

    seeds = []
    for bucket, items in buckets.items():
        if not items:
            continue
        print(f'[{bucket}] {len(items)}/{CATEGORY_QUOTAS[bucket]}개')
        for it in items:
            print(f"  - [{it['grade']}] {it['keyword']:<35} (vol {it['volume']}, cat={it['category']})")
            seeds.append(it['keyword'])
        print()

    print('필터 통계:')
    print(f"  자기 한의원 제외: {rejected['self']}건")
    print(f"  청주 외 제외:     {rejected['non_cheongju']}건")
    print(f"  카테고리 매칭 X:   {rejected['no_bucket']}건")

    # 백업 + 저장
    if SEEDS_PATH.exists():
        backup = SEEDS_PATH.with_name(f'{SEEDS_PATH.stem}.bak_{datetime.now():%Y%m%d_%H%M%S}.json')
        shutil.copy(SEEDS_PATH, backup)
        print(f'\n기존 시드 백업: {backup}')

    SEEDS_PATH.write_text(
        json.dumps(seeds, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f'새 시드 저장: {SEEDS_PATH} ({len(seeds)}개)')


if __name__ == '__main__':
    main()
