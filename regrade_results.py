#!/usr/bin/env python3
"""
기존 CSV 결과를 MF-KEI 3.0으로 재평가
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import math

def calculate_priority_v3(volume: int, difficulty: int, opportunity: int, keyword: str = "") -> float:
    """MF-KEI 3.0 점수 계산"""
    if volume > 0:
        volume_score = min(100, (math.log10(volume) / 4) * 100)
    else:
        volume_score = 0

    difficulty_score = 100 - difficulty
    opportunity_score = opportunity

    base_score = (
        volume_score * 0.5 +
        opportunity_score * 0.3 +
        difficulty_score * 0.2
    )

    # 의도 가중치 (검색량 100 이상만)
    intent_weight = 1.0
    if volume >= 100:
        if any(w in keyword for w in ["가격", "비용"]):
            intent_weight = 1.5
        elif any(w in keyword for w in ["후기", "추천"]):
            intent_weight = 1.3

    return base_score * intent_weight


def evaluate_grade(volume: int, difficulty: int, opportunity: int) -> str:
    """등급 재평가"""
    if volume >= 100 and (opportunity >= 90 or difficulty < 15):
        return 'S'
    elif volume >= 50 and (opportunity >= 80 or difficulty < 20):
        return 'A'
    else:
        return 'B'


# CSV 로드
df = pd.read_csv('legion_v3_results.csv', encoding='utf-8-sig')

print("=" * 80)
print("🔄 MF-KEI 3.0 재평가 시작")
print("=" * 80)

# 재평가
df['new_priority'] = df.apply(
    lambda row: calculate_priority_v3(
        row['search_volume'], row['difficulty'], row['opportunity'], row['keyword']
    ), axis=1
)
df['new_grade'] = df.apply(
    lambda row: evaluate_grade(
        row['search_volume'], row['difficulty'], row['opportunity']
    ), axis=1
)

# 등급 변화 분석
print("\n📊 등급 변화 분석")
print("-" * 80)

grade_changes = df[df['grade'] != df['new_grade']]
print(f"등급 변경: {len(grade_changes)}개 / {len(df)}개 ({len(grade_changes)/len(df)*100:.1f}%)")

# S → B 강등
s_to_b = grade_changes[(grade_changes['grade'] == 'S') & (grade_changes['new_grade'] == 'B')]
print(f"  S → B 강등: {len(s_to_b)}개 (저검색량)")

# A → B 강등
a_to_b = grade_changes[(grade_changes['grade'] == 'A') & (grade_changes['new_grade'] == 'B')]
print(f"  A → B 강등: {len(a_to_b)}개 (저검색량)")

# B → S/A 승급
b_to_s = grade_changes[(grade_changes['grade'] == 'B') & (grade_changes['new_grade'] == 'S')]
b_to_a = grade_changes[(grade_changes['grade'] == 'B') & (grade_changes['new_grade'] == 'A')]
print(f"  B → S 승급: {len(b_to_s)}개 (고검색량 + 고기회)")
print(f"  B → A 승급: {len(b_to_a)}개 (중검색량 + 고기회)")

# 새 등급별 분포
print("\n📈 새 등급 분포")
print("-" * 80)
new_s = df[df['new_grade'] == 'S']
new_a = df[df['new_grade'] == 'A']
new_b = df[df['new_grade'] == 'B']
new_c = df[df['new_grade'] == 'C']

print(f"🔥 S급: {len(new_s)}개 (기존: {len(df[df.grade == 'S'])}개)")
print(f"⭐ A급: {len(new_a)}개 (기존: {len(df[df.grade == 'A'])}개)")
print(f"📌 B급: {len(new_b)}개 (기존: {len(df[df.grade == 'B'])}개)")
print(f"⚪ C급: {len(new_c)}개 (기존: {len(df[df.grade == 'C'])}개)")
print(f"\nS/A급 비율: {(len(new_s) + len(new_a))/len(df)*100:.1f}% (기존: {(len(df[df.grade.isin(['S', 'A'])]))/len(df)*100:.1f}%)")

# 상위 20개 비교
print("\n\n🏆 상위 20개 키워드 (MF-KEI 3.0)")
print("=" * 80)

df_sorted = df.sort_values('new_priority', ascending=False)
top20 = df_sorted.head(20)

for idx, row in top20.iterrows():
    old_grade = row['grade']
    new_grade = row['new_grade']
    grade_change = "" if old_grade == new_grade else f" ({old_grade}→{new_grade})"

    emoji = "🔥" if new_grade == 'S' else "⭐" if new_grade == 'A' else "📌"
    print(f"{emoji} {row['keyword']:<35} | 검색량:{row['search_volume']:>6} | "
          f"점수:{row['new_priority']:>6.1f} | {new_grade}{grade_change}")

# 평균 검색량 비교
print("\n\n📊 등급별 평균 검색량")
print("=" * 80)
print(f"S급: {new_s['search_volume'].mean():.0f}회/월 (중앙값: {new_s['search_volume'].median():.0f})")
print(f"A급: {new_a['search_volume'].mean():.0f}회/월 (중앙값: {new_a['search_volume'].median():.0f})")
print(f"B급: {new_b['search_volume'].mean():.0f}회/월 (중앙값: {new_b['search_volume'].median():.0f})")

# 저장
df['priority_score'] = df['new_priority']
df['grade'] = df['new_grade']
df.drop(['new_priority', 'new_grade'], axis=1, inplace=True)
df.to_csv('legion_v3_results_v3.csv', index=False, encoding='utf-8-sig')

print("\n\n✅ 재평가 완료: legion_v3_results_v3.csv 저장됨")
