#!/usr/bin/env python3
"""
campaigns.json 키워드 품질 분석
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 300개 키워드의:
1. Pathfinder DB와 매칭 여부
2. 검색량 확인
3. 중복 키워드 체크
4. 품질 등급 분석
"""

import sys
import os
import json
import sqlite3
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def load_campaigns_keywords():
    """campaigns.json에서 키워드 로드"""
    with open('config/campaigns.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    keywords = []
    for target in data['targets']:
        category = target['category']
        for seed in target['seeds']:
            keywords.append({
                'keyword': seed,
                'category': category
            })

    return keywords

def analyze_with_pathfinder(campaigns_keywords):
    """Pathfinder DB와 비교 분석"""

    conn = sqlite3.connect('db/marketing_data.db')
    cursor = conn.cursor()

    results = {
        'in_pathfinder': [],
        'not_in_pathfinder': [],
        'grade_stats': Counter(),
        'volume_stats': {
            'high': [],      # 1000+
            'medium': [],    # 100-999
            'low': [],       # 1-99
            'zero': []       # 0
        }
    }

    for item in campaigns_keywords:
        kw = item['keyword']
        category = item['category']

        # Pathfinder DB 조회
        cursor.execute("""
            SELECT grade, search_volume, difficulty, opportunity, priority_v3
            FROM keyword_insights
            WHERE keyword = ?
        """, (kw,))

        row = cursor.fetchone()

        if row:
            grade, volume, difficulty, opportunity, priority = row

            results['in_pathfinder'].append({
                'keyword': kw,
                'category': category,
                'grade': grade,
                'volume': volume,
                'difficulty': difficulty,
                'opportunity': opportunity,
                'priority': priority
            })

            results['grade_stats'][grade] += 1

            # 검색량별 분류
            if volume >= 1000:
                results['volume_stats']['high'].append((kw, volume))
            elif volume >= 100:
                results['volume_stats']['medium'].append((kw, volume))
            elif volume > 0:
                results['volume_stats']['low'].append((kw, volume))
            else:
                results['volume_stats']['zero'].append((kw, volume))
        else:
            results['not_in_pathfinder'].append({
                'keyword': kw,
                'category': category
            })

    conn.close()
    return results

def check_duplicates(keywords_list):
    """중복 키워드 체크"""
    keyword_counts = Counter([k['keyword'] for k in keywords_list])
    duplicates = {kw: count for kw, count in keyword_counts.items() if count > 1}
    return duplicates

def main():
    print("="*70)
    print("🔍 campaigns.json 키워드 품질 분석")
    print("="*70)
    print()

    # === 1. 키워드 로드 ===
    print("📥 STEP 1: 키워드 로드")
    print("-"*70)

    campaigns_kw = load_campaigns_keywords()
    print(f"   총 키워드: {len(campaigns_kw)}개")

    # 카테고리별 통계
    category_stats = Counter([k['category'] for k in campaigns_kw])
    print(f"   카테고리 수: {len(category_stats)}개")
    print()

    # === 2. 중복 체크 ===
    print("📋 STEP 2: 중복 키워드 체크")
    print("-"*70)

    duplicates = check_duplicates(campaigns_kw)
    if duplicates:
        print(f"   ⚠️ 중복 발견: {len(duplicates)}개")
        for kw, count in sorted(duplicates.items(), key=lambda x: -x[1])[:10]:
            print(f"      • {kw}: {count}번 중복")
    else:
        print("   ✅ 중복 없음")
    print()

    # === 3. Pathfinder와 비교 ===
    print("🔍 STEP 3: Pathfinder DB와 비교")
    print("-"*70)

    analysis = analyze_with_pathfinder(campaigns_kw)

    in_pf = len(analysis['in_pathfinder'])
    not_in_pf = len(analysis['not_in_pathfinder'])

    print(f"   Pathfinder에 있음: {in_pf}개 ({in_pf/len(campaigns_kw)*100:.1f}%)")
    print(f"   Pathfinder에 없음: {not_in_pf}개 ({not_in_pf/len(campaigns_kw)*100:.1f}%)")
    print()

    # === 4. 등급 분석 (Pathfinder에 있는 것만) ===
    if in_pf > 0:
        print("📊 STEP 4: 등급 분석 (Pathfinder에 있는 키워드)")
        print("-"*70)

        for grade in ['S', 'A', 'B', 'C']:
            count = analysis['grade_stats'][grade]
            if count > 0:
                print(f"   {grade}급: {count}개 ({count/in_pf*100:.1f}%)")
        print()

    # === 5. 검색량 분석 ===
    print("📈 STEP 5: 검색량 분석 (Pathfinder에 있는 키워드)")
    print("-"*70)

    vol_stats = analysis['volume_stats']
    print(f"   🔥 High (1000+):   {len(vol_stats['high'])}개")
    print(f"   🟢 Medium (100-999): {len(vol_stats['medium'])}개")
    print(f"   🟡 Low (1-99):      {len(vol_stats['low'])}개")
    print(f"   ⚪ Zero (0):        {len(vol_stats['zero'])}개")
    print()

    # 상위 검색량 키워드
    if vol_stats['high']:
        print("   상위 검색량 키워드 (Top 10):")
        for kw, vol in sorted(vol_stats['high'], key=lambda x: -x[1])[:10]:
            print(f"      • {kw:30s} {vol:>6,}")
        print()

    # === 6. Pathfinder에 없는 키워드 분석 ===
    if not_in_pf > 0:
        print("🔍 STEP 6: Pathfinder에 없는 키워드 분석")
        print("-"*70)

        # 카테고리별
        not_in_pf_by_cat = defaultdict(list)
        for item in analysis['not_in_pathfinder']:
            not_in_pf_by_cat[item['category']].append(item['keyword'])

        print(f"   총 {not_in_pf}개 키워드가 Pathfinder에 없습니다")
        print()
        print("   카테고리별:")
        for cat, kws in sorted(not_in_pf_by_cat.items(), key=lambda x: -len(x[1]))[:5]:
            print(f"      • {cat}: {len(kws)}개")
            for kw in kws[:3]:
                print(f"        - {kw}")
        print()

    # === 7. 품질 요약 ===
    print("="*70)
    print("📊 품질 요약")
    print("="*70)
    print()

    # Pathfinder 검증 비율
    verified = in_pf / len(campaigns_kw) * 100
    print(f"✅ Pathfinder 검증률: {verified:.1f}%")

    if in_pf > 0:
        # S/A급 비율
        sa_count = analysis['grade_stats']['S'] + analysis['grade_stats']['A']
        sa_ratio = sa_count / in_pf * 100
        print(f"✅ S/A급 비율: {sa_ratio:.1f}% ({sa_count}/{in_pf}개)")

        # 검색량 있는 비율
        has_volume = len(vol_stats['high']) + len(vol_stats['medium']) + len(vol_stats['low'])
        volume_ratio = has_volume / in_pf * 100
        print(f"✅ 검색량 있음: {volume_ratio:.1f}% ({has_volume}/{in_pf}개)")

    print()

    # === 8. 권장 사항 ===
    print("="*70)
    print("💡 권장 사항")
    print("="*70)
    print()

    if not_in_pf > 50:
        print("⚠️ 1. Pathfinder로 키워드 재수집 권장")
        print("   - 미검증 키워드가 많습니다")
        print("   - python pathfinder_v3_legion.py --target 500")
        print()

    if analysis['grade_stats']['C'] > analysis['grade_stats']['S'] + analysis['grade_stats']['A']:
        print("⚠️ 2. C급 키워드 정리 권장")
        print("   - campaigns.json에서 C급 키워드 제거 고려")
        print()

    if duplicates:
        print("⚠️ 3. 중복 키워드 제거 권장")
        print(f"   - {len(duplicates)}개 중복 발견")
        print()

    if not_in_pf == 0 and sa_ratio > 80:
        print("✅ 키워드 품질이 우수합니다!")
        print("   - 모두 Pathfinder 검증 완료")
        print("   - S/A급 비율 80% 이상")
        print()

    print("="*70)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
