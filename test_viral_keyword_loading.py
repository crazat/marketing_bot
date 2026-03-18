#!/usr/bin/env python3
"""
Viral Hunter 키워드 로딩 테스트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pathfinder 연동이 제대로 되는지 확인
"""

import sys
import os

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from viral_hunter import ViralHunter
from utils import logger

def test_keyword_loading():
    """키워드 로딩 테스트"""

    print("="*70)
    print("🧪 Viral Hunter 키워드 로딩 테스트")
    print("="*70)
    print()

    try:
        # Viral Hunter 초기화
        hunter = ViralHunter()

        # 키워드 로드
        print("📥 키워드 로딩 중...\n")
        keywords = hunter._load_keywords()

        print("\n" + "="*70)
        print("✅ 테스트 성공!")
        print("="*70)
        print()
        print(f"📊 총 키워드 수: {len(keywords)}개")
        print()

        # 상위 20개 키워드 출력
        print("📋 상위 20개 키워드:")
        print("-" * 70)
        for i, kw in enumerate(keywords[:20], 1):
            print(f"   {i:2d}. {kw}")

        if len(keywords) > 20:
            print(f"   ... (외 {len(keywords) - 20}개)")

        print()
        print("="*70)

        # 키워드 샘플 분석
        print("\n🔍 키워드 분석:")
        print("-" * 70)

        # Pathfinder 스타일 키워드 찾기 (검증)
        pathfinder_style = [kw for kw in keywords if '한약' in kw or '한의원' in kw]
        print(f"   • '한약/한의원' 포함: {len(pathfinder_style)}개")

        # 지역 키워드
        regions = ['청주', '세종', '충주', '제천', '대전']
        region_counts = {r: len([kw for kw in keywords if r in kw]) for r in regions}
        print(f"   • 지역별:")
        for region, count in sorted(region_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"     - {region}: {count}개")

        # 카테고리별
        categories = ['다이어트', '교통사고', '피부', '여드름', '비대칭', '탈모']
        category_counts = {c: len([kw for kw in keywords if c in kw]) for c in categories}
        print(f"   • 카테고리별:")
        for cat, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            if count > 0:
                print(f"     - {cat}: {count}개")

        print()
        print("="*70)
        print("✨ 테스트 완료!")
        print("="*70)

        return True

    except Exception as e:
        print("\n" + "="*70)
        print("❌ 테스트 실패!")
        print("="*70)
        print(f"\n에러: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_keyword_loading()
    sys.exit(0 if success else 1)
