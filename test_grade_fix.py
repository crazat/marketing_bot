#!/usr/bin/env python3
"""
순환 논리 수정 테스트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

# 시뮬레이션
test_cases = [
    # (keyword, api_volume, difficulty, opportunity, serp_grade)
    ("청주 교통사고 입원 병원 가격", 0, 0, 100, "S"),  # API에 없음
    ("청주 교통사고 입원 병원 가격", 10, 0, 100, "S"),  # API 검색량 10
    ("청주 교통사고", 5600, 13, 100, "S"),  # API 검색량 5600
    ("청주 산후조리원 비용", 300, 6, 96, "S"),  # API 검색량 300
    ("충주 다이어트 카페 비용", 20, 0, 98, "S"),  # API 검색량 20
]

print("=" * 100)
print("🧪 순환 논리 수정 테스트")
print("=" * 100)
print()

print("📊 수정 전 로직 (순환 논리)")
print("-" * 100)
print(f"{'키워드':<35} | {'API검색량':>8} | {'난이도':>4} | {'기회':>4} | {'SERP등급':>6} | {'추정치':>6} | {'최종등급':>6}")
print("-" * 100)

for keyword, api_vol, diff, opp, serp_grade in test_cases:
    # 수정 전 로직
    search_volume = api_vol
    if search_volume == 0:
        # 순환 논리: SERP 등급 기반 추정치
        search_volume = 100 if serp_grade in ['S', 'A'] else 30

    # 재평가
    grade = serp_grade
    if search_volume >= 100 and (opp >= 90 or diff < 15):
        grade = 'S'
    elif search_volume >= 50 and (opp >= 80 or diff < 20):
        grade = 'A'
    elif search_volume < 50 and grade in ['S', 'A']:
        grade = 'B'

    emoji = "🔥" if grade == 'S' else "⭐" if grade == 'A' else "📌"
    print(f"{keyword:<35} | {api_vol:>8} | {diff:>4} | {opp:>4} | {serp_grade:>6} | {search_volume:>6} | {emoji} {grade:>5}")

print("\n\n📊 수정 후 로직 (순환 논리 제거)")
print("-" * 100)
print(f"{'키워드':<35} | {'API검색량':>8} | {'난이도':>4} | {'기회':>4} | {'SERP등급':>6} | {'추정치':>6} | {'최종등급':>6}")
print("-" * 100)

for keyword, api_vol, diff, opp, serp_grade in test_cases:
    # 수정 후 로직
    search_volume = api_vol
    has_real_volume = search_volume > 0

    # 재평가: 실제 검색량 있을 때만 S/A급 가능
    grade = serp_grade
    if has_real_volume:
        if search_volume >= 100 and (opp >= 90 or diff < 15):
            grade = 'S'
        elif search_volume >= 50 and (opp >= 80 or diff < 20):
            grade = 'A'
        elif search_volume < 50:
            grade = 'B'
    else:
        # 검색량 없으면 무조건 B급
        if grade in ['S', 'A']:
            grade = 'B'
        search_volume = 30  # 추정치 (점수 계산용)

    emoji = "🔥" if grade == 'S' else "⭐" if grade == 'A' else "📌"
    print(f"{keyword:<35} | {api_vol:>8} | {diff:>4} | {opp:>4} | {serp_grade:>6} | {search_volume:>6} | {emoji} {grade:>5}")

print("\n\n✅ 핵심 개선:")
print("1. API 검색량이 없으면 → 무조건 B급 이하")
print("2. API 검색량이 50 미만이면 → B급")
print("3. API 검색량이 100 이상이고 기회/난이도 조건 만족 → S급")
print()
print("⚠️ 순환 논리 완전 제거: 추정치가 등급에 영향을 주지 않음")
