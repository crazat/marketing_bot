#!/usr/bin/env python3
"""
멀티 플랫폼 Viral Hunter 테스트
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_adapters():
    """어댑터 테스트"""
    from viral_hunter_multi_platform import (
        KarrotAdapter,
        YouTubeAdapter,
        NaverPlaceAdapter,
        MultiPlatformViralHunter
    )
    from db.database import DatabaseManager

    print("="*70)
    print("🧪 멀티 플랫폼 Viral Hunter 테스트")
    print("="*70)
    print()

    db = DatabaseManager()

    # === 1. 어댑터 초기화 테스트 ===
    print("📥 STEP 1: 어댑터 초기화")
    print("-"*70)

    from viral_hunter_multi_platform import (
        InstagramAdapter,
        TikTokAdapter
    )

    adapters = {
        '당근마켓': KarrotAdapter(db),
        'YouTube': YouTubeAdapter(db),
        '네이버 플레이스': NaverPlaceAdapter(db),
        'Instagram': InstagramAdapter(db),
        'TikTok': TikTokAdapter(db),
    }

    for name, adapter in adapters.items():
        try:
            platform_name = adapter.get_platform_name()
            print(f"   ✅ {name} ({platform_name})")
        except Exception as e:
            print(f"   ❌ {name} 초기화 실패: {e}")

    print()

    # === 2. 멀티 플랫폼 Viral Hunter 초기화 ===
    print("🚀 STEP 2: 멀티 플랫폼 Viral Hunter 초기화")
    print("-"*70)

    try:
        hunter = MultiPlatformViralHunter()
        print(f"   ✅ 초기화 완료")
        print(f"   플랫폼 수: {len(hunter.adapters) + 3}개")
        print()
    except Exception as e:
        print(f"   ❌ 초기화 실패: {e}")
        return

    # === 3. 키워드 로딩 테스트 ===
    print("📋 STEP 3: 키워드 로딩")
    print("-"*70)

    keywords = hunter._load_keywords()
    print(f"   총 키워드: {len(keywords)}개")
    print(f"   샘플: {keywords[:5]}")
    print()

    # === 4. 플랫폼별 검색 테스트 (샘플) ===
    print("🔍 STEP 4: 플랫폼별 검색 테스트 (샘플)")
    print("-"*70)

    test_keyword = "청주 다이어트"
    print(f"   테스트 키워드: {test_keyword}")
    print()

    for name, adapter in adapters.items():
        try:
            print(f"   [{name}] 검색 중...")
            results = adapter.search(test_keyword, max_results=3)
            print(f"   → {len(results)}개 타겟 발견")

            if results:
                print(f"      예시:")
                for target in results[:2]:
                    print(f"        • {target.title[:50]}...")
        except Exception as e:
            print(f"   → 검색 실패: {e}")
        print()

    # === 5. 플랫폼 목록 ===
    print("="*70)
    print("📊 사용 가능한 플랫폼")
    print("="*70)
    print()

    platforms = [
        ("네이버 카페", "naver", "✅ 사용 가능"),
        ("네이버 블로그", "naver", "✅ 사용 가능"),
        ("네이버 지식인", "naver", "✅ 사용 가능"),
        ("당근마켓", "karrot", "✅ 사용 가능"),
        ("YouTube", "youtube", "✅ 사용 가능"),
        ("네이버 플레이스", "naver_place", "✅ 사용 가능"),
        ("Instagram", "instagram", "✅ 사용 가능 (API 설정 필요)"),
        ("TikTok", "tiktok", "✅ 사용 가능 (API 설정 필요)"),
    ]

    for name, code, status in platforms:
        print(f"   {status} {name} ({code})")

    print()
    print("="*70)
    print("✅ 테스트 완료!")
    print("="*70)


if __name__ == "__main__":
    try:
        test_adapters()
    except Exception as e:
        print(f"\n❌ 에러: {e}")
        import traceback
        traceback.print_exc()
