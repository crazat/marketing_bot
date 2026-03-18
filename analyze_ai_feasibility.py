"""AI 적용 가능성 분석 스크립트"""
import sqlite3
import pandas as pd
import sys
import io
from collections import Counter, defaultdict

# UTF-8 출력 설정
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('db/marketing_data.db')

# 전체 키워드 분석
df = pd.read_sql('SELECT * FROM keyword_insights', conn)
print('='*60)
print('📊 실제 데이터 AI 적용 가능성 분석')
print('='*60)

print(f'\n총 키워드: {len(df)}개')
print(f'S급: {len(df[df.grade=="S"])}개')
print(f'A급: {len(df[df.grade=="A"])}개')
print(f'B급: {len(df[df.grade=="B"])}개')
print(f'C급: {len(df[df.grade=="C"])}개')

# 1. 키워드 패턴 분석 (LLM 확장용)
print('\n' + '='*60)
print('🔍 A1. LLM 키워드 확장 가능성')
print('='*60)

# 핵심 단어 추출
core_words = []
for kw in df['keyword']:
    words = str(kw).replace('청주', '').replace('제천', '').split()
    core_words.extend([w for w in words if len(w) > 1])

word_freq = Counter(core_words).most_common(30)
print('상위 핵심 단어 (확장 시드):')
for w, c in word_freq[:15]:
    print(f'   {w}: {c}회')

# 2. 유사 키워드 그룹 분석 (클러스터링용)
print('\n' + '='*60)
print('🔍 A2. 의미 클러스터링 가능성')
print('='*60)

clusters = defaultdict(list)
for kw in df['keyword']:
    kw_str = str(kw)
    core = kw_str.replace('청주', '').replace('제천', '').replace(' ', '')
    core = core.replace('가격', '').replace('비용', '').replace('추천', '').replace('후기', '')
    if len(core) > 3:
        clusters[core[:5]].append(kw_str)

big_clusters = [(k, v) for k, v in clusters.items() if len(v) >= 3]
print(f'3개 이상 키워드 클러스터: {len(big_clusters)}개')
print('\n예시 클러스터 (병합/그룹화 대상):')
for core, kws in sorted(big_clusters, key=lambda x: -len(x[1]))[:8]:
    print(f'\n   [{core}] ({len(kws)}개):')
    for k in kws[:5]:
        print(f'      - {k}')

# 3. 검색 의도 분포 분석
print('\n' + '='*60)
print('🔍 A3. 검색 의도 분류 현황')
print('='*60)

if 'search_intent' in df.columns:
    intent_dist = df['search_intent'].value_counts()
    for intent, cnt in intent_dist.items():
        pct = cnt/len(df)*100
        print(f'   {intent}: {cnt}개 ({pct:.1f}%)')

    print('\n의도별 S/A급 비율:')
    for intent in intent_dist.index:
        subset = df[df['search_intent']==intent]
        sa_cnt = len(subset[subset['grade'].isin(['S','A'])])
        sa_rate = sa_cnt / len(subset) * 100 if len(subset) > 0 else 0
        print(f'   {intent}: {sa_rate:.1f}% ({sa_cnt}/{len(subset)})')

# 4. 난이도 분포 분석 (예측 모델용)
print('\n' + '='*60)
print('🔍 A4. 난이도 예측 가능성')
print('='*60)

print(f'난이도 통계:')
print(f'   평균: {df["difficulty"].mean():.1f}')
print(f'   중앙값: {df["difficulty"].median():.1f}')
print(f'   표준편차: {df["difficulty"].std():.1f}')
print(f'   최소: {df["difficulty"].min()}')
print(f'   최대: {df["difficulty"].max()}')

# 난이도 구간별 분포
print('\n난이도 구간별 분포:')
bins = [(0, 10), (11, 20), (21, 30), (31, 50), (51, 100)]
for low, high in bins:
    cnt = len(df[(df['difficulty'] >= low) & (df['difficulty'] <= high)])
    pct = cnt/len(df)*100
    bar = '█' * int(pct/2)
    print(f'   {low:2d}-{high:3d}: {cnt:4d}개 ({pct:5.1f}%) {bar}')

# 키워드 특성과 난이도 상관관계
print('\n키워드 특성별 평균 난이도:')
# 가격/비용 포함
price_kw = df[df['keyword'].str.contains('가격|비용', na=False)]
print(f'   가격/비용 키워드: {price_kw["difficulty"].mean():.1f} ({len(price_kw)}개)')

# 추천/후기 포함
review_kw = df[df['keyword'].str.contains('추천|후기', na=False)]
print(f'   추천/후기 키워드: {review_kw["difficulty"].mean():.1f} ({len(review_kw)}개)')

# 지역명 포함
region_kw = df[df['keyword'].str.contains('청주|제천', na=False)]
print(f'   지역명 키워드: {region_kw["difficulty"].mean():.1f} ({len(region_kw)}개)')

# 5. 콘텐츠 생성 가능성
print('\n' + '='*60)
print('🔍 B1-B4. 콘텐츠 생성 가능성')
print('='*60)

sa_keywords = df[df['grade'].isin(['S','A'])]
print(f'콘텐츠 대상 S/A급: {len(sa_keywords)}개')

if 'category' in df.columns:
    print('\n카테고리별 S/A급 (콘텐츠 주제):')
    cat_sa = sa_keywords['category'].value_counts()
    for cat, cnt in cat_sa.items():
        pct = cnt/len(sa_keywords)*100
        print(f'   {cat}: {cnt}개 ({pct:.1f}%)')

# S급 키워드 샘플 (블로그 제목 생성 대상)
print('\nS급 키워드 샘플 (블로그 제목 생성 대상):')
s_keywords = df[df['grade']=='S'].nsmallest(10, 'difficulty')
for _, row in s_keywords.iterrows():
    print(f'   - {row["keyword"]} [검색량:{row["search_volume"]:,}]')

# 6. 트렌드 데이터 분석
print('\n' + '='*60)
print('🔍 C1. 트렌드 예측 가능성')
print('='*60)

if 'trend_status' in df.columns:
    trend_dist = df['trend_status'].value_counts()
    print('트렌드 상태 분포:')
    for trend, cnt in trend_dist.items():
        pct = cnt/len(df)*100
        print(f'   {trend}: {cnt}개 ({pct:.1f}%)')

    # 상승 트렌드 키워드
    rising = df[df['trend_status'] == '상승']
    if len(rising) > 0:
        print(f'\n📈 상승 트렌드 키워드 ({len(rising)}개):')
        for _, row in rising.head(10).iterrows():
            print(f'   - {row["keyword"]}')

# 7. 자동 카테고리 분류 분석
print('\n' + '='*60)
print('🔍 D1. 자동 카테고리 분류 가능성')
print('='*60)

if 'category' in df.columns:
    cat_dist = df['category'].value_counts()
    print('현재 카테고리 분포:')
    for cat, cnt in cat_dist.items():
        pct = cnt/len(df)*100
        print(f'   {cat}: {cnt}개 ({pct:.1f}%)')

    # 기타 카테고리 분석
    etc = df[df['category'] == '기타']
    if len(etc) > 0:
        print(f'\n미분류(기타) 키워드 샘플 ({len(etc)}개):')
        for kw in etc['keyword'].head(10):
            print(f'   - {kw}')

# 8. 종합 평가
print('\n' + '='*60)
print('📋 AI 적용 우선순위 평가')
print('='*60)

evaluations = []

# A1 평가
unique_cores = len(set([str(kw).split()[0] if str(kw).split() else '' for kw in df['keyword']]))
evaluations.append(('A1 LLM 키워드 확장', '높음' if unique_cores < 50 else '중간',
                   f'핵심 단어 {len(word_freq)}개로 {len(df)}개 키워드 생성 가능'))

# A2 평가
evaluations.append(('A2 의미 클러스터링', '높음' if len(big_clusters) > 30 else '중간',
                   f'{len(big_clusters)}개 클러스터, 평균 {sum(len(v) for _,v in big_clusters)/max(1,len(big_clusters)):.1f}개/클러스터'))

# A3 평가
if 'search_intent' in df.columns:
    unknown = len(df[df['search_intent'] == 'unknown'])
    evaluations.append(('A3 검색 의도 고도화', '높음' if unknown > len(df)*0.1 else '낮음',
                       f'미분류 {unknown}개 ({unknown/len(df)*100:.1f}%)'))

# A4 평가
diff_std = df['difficulty'].std()
evaluations.append(('A4 난이도 예측', '중간' if diff_std > 20 else '높음',
                   f'난이도 표준편차 {diff_std:.1f}, 패턴 학습 가능'))

# B1 평가
evaluations.append(('B1 블로그 제목 생성', '높음',
                   f'S/A급 {len(sa_keywords)}개 → 즉시 콘텐츠 생성 가능'))

# C1 평가
if 'trend_status' in df.columns:
    rising_cnt = len(df[df['trend_status'] == '상승'])
    evaluations.append(('C1 트렌드 예측', '중간' if rising_cnt > 5 else '낮음',
                       f'상승 트렌드 {rising_cnt}개, 데이터 누적 필요'))

# D1 평가
if 'category' in df.columns:
    etc_cnt = len(df[df['category'] == '기타'])
    evaluations.append(('D1 자동 카테고리 분류', '높음' if etc_cnt > 20 else '낮음',
                       f'미분류 {etc_cnt}개 ({etc_cnt/len(df)*100:.1f}%)'))

print('\n| 기능 | 우선순위 | 근거 |')
print('|------|---------|------|')
for name, priority, reason in evaluations:
    emoji = '🔴' if priority == '높음' else ('🟡' if priority == '중간' else '🟢')
    print(f'| {name} | {emoji} {priority} | {reason} |')

conn.close()
print('\n✅ 분석 완료')
