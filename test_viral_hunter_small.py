#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viral_hunter 소규모 테스트 (5개 키워드만)
"""

import sys
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    from viral_hunter import ViralHunter

    hunter = ViralHunter()

    # 테스트 키워드 (사용자 로그에 나온 것들)
    test_keywords = [
        "복대동 다이어트",
        "청주 한의원",
        "청주 다이어트",
        "청주 새살침 효과",
        "청주 교통사고"
    ]

    print(f"\n{'='*60}")
    print(f"🎯 Viral Hunter 소규모 테스트")
    print(f"   키워드: {len(test_keywords)}개")
    print(f"{'='*60}\n")

    # hunt() 실행
    results = hunter.hunt(
        keywords=test_keywords,
        limit_keywords=None,
        max_per_platform=10
    )

    print(f"\n{'='*60}")
    print(f"✅ 테스트 완료!")
    print(f"   총 발견: {len(results)}개")
    print(f"{'='*60}\n")

    if results:
        print("📋 발견된 타겟 (처음 10개):")
        for i, target in enumerate(results[:10], 1):
            platform_icon = {"cafe": "☕", "blog": "📝", "kin": "❓"}.get(target.platform, "📌")
            print(f"{i}. {platform_icon} [{target.platform.upper()}] {target.title[:60]}")
            print(f"   점수: {target.priority_score:.0f} | URL: {target.url[:70]}...")
    else:
        print("❌ 결과 없음 - 문제가 여전히 존재합니다.")
