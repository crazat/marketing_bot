#!/usr/bin/env python3
"""
campaigns.json 키워드를 Pathfinder에 추가
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

미검증 196개 키워드를 Pathfinder로 검증
"""

import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def extract_unverified_keywords():
    """Pathfinder에 없는 키워드 추출"""
    import sqlite3

    # campaigns.json 로드
    with open('config/campaigns.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    all_keywords = []
    for target in data['targets']:
        all_keywords.extend(target['seeds'])

    # Pathfinder DB 연결
    conn = sqlite3.connect('db/marketing_data.db')
    cursor = conn.cursor()

    unverified = []
    for kw in all_keywords:
        cursor.execute("SELECT 1 FROM keyword_insights WHERE keyword = ?", (kw,))
        if not cursor.fetchone():
            unverified.append(kw)

    conn.close()

    return unverified

def create_pathfinder_input_file(keywords):
    """Pathfinder 입력 파일 생성"""

    # config/campaigns_unverified.json 생성
    output = {
        "campaign_name": "campaigns.json 미검증 키워드 검증",
        "targets": [
            {
                "category": "campaigns_미검증",
                "seeds": keywords
            }
        ]
    }

    output_path = 'config/campaigns_unverified.json'
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    return output_path

def main():
    print("="*70)
    print("🔍 campaigns.json 미검증 키워드 → Pathfinder 추가")
    print("="*70)
    print()

    # 1. 미검증 키워드 추출
    print("📥 미검증 키워드 추출 중...")
    unverified = extract_unverified_keywords()
    print(f"   미검증 키워드: {len(unverified)}개")
    print()

    if not unverified:
        print("✅ 모든 키워드가 이미 Pathfinder에 있습니다!")
        return

    # 2. 입력 파일 생성
    print("📝 Pathfinder 입력 파일 생성 중...")
    output_path = create_pathfinder_input_file(unverified)
    print(f"   파일 생성: {output_path}")
    print()

    # 3. 실행 방법 안내
    print("="*70)
    print("🚀 다음 단계")
    print("="*70)
    print()
    print("1. Pathfinder V3 Complete로 검증:")
    print()
    print("   python pathfinder_v3_complete.py --save-db")
    print()
    print("   ※ campaigns_unverified.json의 키워드가 자동으로 포함됩니다")
    print()
    print("2. 또는 수동으로 campaigns.json에 추가:")
    print()
    print("   # config/campaigns.json 편집")
    print('   "targets": [')
    print('     ...')
    print('     {')
    print('       "category": "미검증_재수집",')
    print('       "seeds": [')
    for kw in unverified[:5]:
        print(f'         "{kw}",')
    print('         ...')
    print('       ]')
    print('     }')
    print('   ]')
    print()
    print("="*70)
    print()

    # 4. 미검증 키워드 샘플 출력
    print("📋 미검증 키워드 샘플 (상위 20개):")
    print("-"*70)
    for i, kw in enumerate(unverified[:20], 1):
        print(f"   {i:2d}. {kw}")
    if len(unverified) > 20:
        print(f"   ... (외 {len(unverified) - 20}개)")
    print()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
