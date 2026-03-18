#!/usr/bin/env python3
"""
MF-KEI 3.0 점수 계산 테스트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import math

def calculate_priority_v3(volume: int, difficulty: int, opportunity: int, keyword: str = "") -> float:
    """MF-KEI 3.0 점수 계산 (검색량 우선 + 저검색량 의도 가중치 제거)"""
    # 1. 검색량 점수 (로그 스케일 정규화)
    if volume > 0:
        volume_score = min(100, (math.log10(volume) / 4) * 100)
    else:
        volume_score = 0

    # 2. 난이도 점수
    difficulty_score = 100 - difficulty

    # 3. 기회 점수
    opportunity_score = opportunity

    # 4. 가중 평균 (검색량 50%, 기회 30%, 난이도 20%)
    base_score = (
        volume_score * 0.5 +
        opportunity_score * 0.3 +
        difficulty_score * 0.2
    )

    # 5. 의도 가중치 (검색량 100 이상만 적용)
    intent_weight = 1.0
    if volume >= 100:
        if any(w in keyword for w in ["가격", "비용"]):
            intent_weight = 1.5
        elif any(w in keyword for w in ["후기", "추천"]):
            intent_weight = 1.3

    return base_score * intent_weight


def evaluate_grade(volume: int, difficulty: int, opportunity: int) -> str:
    """등급 평가 (검색량 기준 포함)"""
    if volume >= 100 and (opportunity >= 90 or difficulty < 15):
        return 'S'
    elif volume >= 50 and (opportunity >= 80 or difficulty < 20):
        return 'A'
    elif volume < 50:
        return 'B (저검색량)'
    else:
        return 'B'


print("=" * 80)
print("🧪 MF-KEI 3.0 점수 계산 테스트")
print("=" * 80)

# 테스트 케이스
test_cases = [
    # (volume, difficulty, opportunity, keyword)
    (20, 0, 98, "충주 다이어트 카페 비용"),
    (5600, 13, 100, "청주 교통사고"),
    (1660, 8, 100, "청주 교통사고 한의원"),
    (1600, 10, 100, "청주 탈모"),
    (300, 6, 96, "청주 산후조리원 비용"),
    (70, 11, 100, "청주 산후조리원 가격"),
    (20, 15, 100, "청주 안면비대칭 교정 가격"),
]

print("\n📊 실제 키워드 점수 비교 (MF-KEI 3.0)")
print("-" * 100)
print(f"{'키워드':<35} | {'검색량':>6} | {'난이도':>4} | {'기회':>4} | {'점수':>7} | {'등급':>12}")
print("-" * 100)

results = []
for volume, diff, opp, kw in test_cases:
    score = calculate_priority_v3(volume, diff, opp, kw)
    grade = evaluate_grade(volume, diff, opp)
    results.append((kw, volume, diff, opp, score, grade))
    print(f"{kw:<35} | {volume:>6} | {diff:>4} | {opp:>4} | {score:>7.1f} | {grade:>12}")

# 점수 순 정렬
print("\n\n🏆 점수 순위 (MF-KEI 3.0)")
print("=" * 100)
results.sort(key=lambda x: x[4], reverse=True)
for rank, (kw, vol, diff, opp, score, grade) in enumerate(results, 1):
    emoji = "🔥" if grade == 'S' else "⭐" if grade == 'A' else "📌"
    print(f"{rank}. {emoji} {kw:<35} | 검색량:{vol:>6} | 점수:{score:>6.1f} | 등급:{grade}")

# 검색량 정규화 테이블
print("\n\n📈 검색량 → volume_score 정규화 테이블")
print("-" * 80)
volumes = [10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
for v in volumes:
    vs = min(100, (math.log10(v) / 4) * 100) if v > 0 else 0
    print(f"검색량 {v:>6} → volume_score {vs:>5.1f}")

print("\n✅ MF-KEI 3.0 테스트 완료")
