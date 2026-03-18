"""해시태그 품질 분석"""
import sqlite3
import pandas as pd
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

conn = sqlite3.connect('db/marketing_data.db')
df = pd.read_sql('SELECT * FROM keyword_insights', conn)

print('='*60)
print('🔍 키워드 품질 및 해시태그 적합성 분석')
print('='*60)

# 1. 문제 키워드 패턴 찾기
print('\n[1] 문제 키워드 패턴')
problems = []

# 반복 단어 (가격 가격, 비용 비용)
for kw in df['keyword']:
    kw_str = str(kw)
    words = kw_str.split()
    # 연속 중복 체크
    for i in range(len(words)-1):
        if words[i] == words[i+1]:
            problems.append(('연속중복', kw_str))
            break

# 의미없는 조합
nonsense_patterns = ['가격 가격', '비용 비용', '추천 추천', '후기 후기',
                     '전후 전후', '기간 기간', '효과 효과']
for kw in df['keyword']:
    kw_str = str(kw)
    for p in nonsense_patterns:
        if p in kw_str:
            if ('연속중복', kw_str) not in problems:
                problems.append(('의미없는조합', kw_str))

print(f'   ⚠️ 문제 키워드: {len(problems)}개')
if problems:
    print('   예시:')
    shown = set()
    for ptype, kw in problems[:15]:
        if kw not in shown:
            print(f'      [{ptype}] {kw}')
            shown.add(kw)

# 2. 너무 긴 키워드
print('\n[2] 키워드 길이 분석')
df['kw_len'] = df['keyword'].str.len()
print(f'   평균 길이: {df["kw_len"].mean():.1f}자')
print(f'   10자 이하: {len(df[df["kw_len"] <= 10])}개 ({len(df[df["kw_len"] <= 10])/len(df)*100:.1f}%)')
print(f'   11-20자: {len(df[(df["kw_len"] > 10) & (df["kw_len"] <= 20)])}개')
print(f'   20자 초과: {len(df[df["kw_len"] > 20])}개 ({len(df[df["kw_len"] > 20])/len(df)*100:.1f}%)')

long_kw = df[df['kw_len'] > 25]
if len(long_kw) > 0:
    print('\n   ⚠️ 25자 초과 키워드 (블로그 해시태그 부적합):')
    for kw in long_kw['keyword'].head(10):
        print(f'      {kw} ({len(kw)}자)')

# 3. 띄어쓰기 분석
print('\n[3] 띄어쓰기 분석')
no_space = df[~df['keyword'].str.contains(' ', na=False)]
with_space = df[df['keyword'].str.contains(' ', na=False)]
print(f'   띄어쓰기 없음: {len(no_space)}개 ({len(no_space)/len(df)*100:.1f}%) ← 해시태그 즉시 사용')
print(f'   띄어쓰기 있음: {len(with_space)}개 ({len(with_space)/len(df)*100:.1f}%) ← 공백 제거 필요')

# 4. 해시태그 적합성 점수
print('\n[4] 해시태그 적합성 등급')

def hashtag_score(kw):
    kw = str(kw)
    score = 100

    # 길이 감점
    if len(kw) > 20:
        score -= 30
    elif len(kw) > 15:
        score -= 10

    # 띄어쓰기 감점 (네이버 블로그는 공백 허용 안함)
    if ' ' in kw:
        score -= 5  # 제거하면 되므로 소폭 감점

    # 특수문자 감점
    if any(c in kw for c in ['/', '(', ')', '-', ',', '.']):
        score -= 20

    # 중복 단어 감점
    words = kw.split()
    for i in range(len(words)-1):
        if words[i] == words[i+1]:
            score -= 40
            break

    return max(0, score)

df['hashtag_score'] = df['keyword'].apply(hashtag_score)

excellent = df[df['hashtag_score'] >= 90]
good = df[(df['hashtag_score'] >= 70) & (df['hashtag_score'] < 90)]
poor = df[df['hashtag_score'] < 70]

print(f'   🟢 우수 (90+): {len(excellent)}개 ({len(excellent)/len(df)*100:.1f}%)')
print(f'   🟡 양호 (70-89): {len(good)}개 ({len(good)/len(df)*100:.1f}%)')
print(f'   🔴 부적합 (<70): {len(poor)}개 ({len(poor)/len(df)*100:.1f}%)')

# 5. S/A급 해시태그 추천
print('\n[5] S/A급 해시태그 추천 TOP 30')
sa = df[df['grade'].isin(['S', 'A'])]
sa_good = sa[sa['hashtag_score'] >= 80].nsmallest(30, 'difficulty')

print('\n   💰 거래형 (가격/예약 관련):')
trans = sa_good[sa_good['search_intent'] == 'transactional'].head(10)
for _, row in trans.iterrows():
    tag = row['keyword'].replace(' ', '')
    print(f'      #{tag}')

print('\n   🔍 상업형 (추천/후기 관련):')
comm = sa_good[sa_good['search_intent'] == 'commercial'].head(10)
for _, row in comm.iterrows():
    tag = row['keyword'].replace(' ', '')
    print(f'      #{tag}')

print('\n   📚 정보형 (효과/방법 관련):')
info = sa_good[sa_good['search_intent'] == 'informational'].head(10)
for _, row in info.iterrows():
    tag = row['keyword'].replace(' ', '')
    print(f'      #{tag}')

# 6. 실용성 평가
print('\n' + '='*60)
print('📋 블로그 해시태그 실용성 평가')
print('='*60)

sa_excellent = sa[sa['hashtag_score'] >= 90]
print(f'''
✅ 결론: 실용적 사용 가능

총 키워드: {len(df)}개
S/A급: {len(sa)}개
해시태그 우수 S/A급: {len(sa_excellent)}개 ({len(sa_excellent)/len(sa)*100:.1f}%)

권장 사항:
1. 띄어쓰기 제거 후 해시태그 사용 (예: "청주 탈모" → #청주탈모)
2. 20자 이하 키워드 우선 사용
3. 중복 단어 키워드 제외 (예: "청주 가격 가격" 제외)
4. 의도별로 3-5개씩 조합 사용 권장

⚠️ 주의 키워드: {len(problems)}개 (중복/의미없는 조합)
''')

conn.close()
print('✅ 분석 완료')
