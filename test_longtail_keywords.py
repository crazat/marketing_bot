#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
롱테일 키워드 테스트 (검색 결과가 적거나 없는 키워드)
"""

import sys
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    from viral_hunter import NaverUnifiedSearch

    print(f"\n{'='*60}")
    print("🔍 롱테일 키워드 테스트 (검증 로직 완화)")
    print(f"{'='*60}\n")

    # 검색 엔진 (캐시 없이)
    searcher = NaverUnifiedSearch(delay=2.0, max_retries=3, use_cache=False)

    # 사용자가 실행한 롱테일 키워드
    longtail_keywords = [
        "복대동 다이어트",
        "청주 아토피 피부",
        "청주 생리통",
        "청주 손땀"
    ]

    # 비교용: 일반 키워드
    common_keywords = [
        "청주 한의원",
        "청주 다이어트"
    ]

    print("📋 롱테일 키워드 (검색 결과 적을 것으로 예상):")
    total_longtail = 0
    for i, keyword in enumerate(longtail_keywords, 1):
        print(f"\n[{i}/4] '{keyword}' 검색...")
        results = searcher.search_all(keyword, max_per_platform=10)
        total_longtail += len(results)

        if results:
            print(f"   ✅ {len(results)}개 발견")
        else:
            print(f"   ℹ️  0개 (정상 - 검색 결과 없음)")

    print(f"\n{'='*60}")
    print("📋 일반 키워드 (검색 결과 많을 것으로 예상):")
    total_common = 0
    for i, keyword in enumerate(common_keywords, 1):
        print(f"\n[{i}/2] '{keyword}' 검색...")
        results = searcher.search_all(keyword, max_per_platform=10)
        total_common += len(results)

        if results:
            print(f"   ✅ {len(results)}개 발견")
        else:
            print(f"   ⚠️  0개 (이상함 - 결과가 있어야 함)")

    # 최종 통계
    print(f"\n{'='*60}")
    print("📊 최종 결과")
    print(f"{'='*60}")

    stats = searcher.get_stats()
    print(f"롱테일 키워드 결과: {total_longtail}개")
    print(f"일반 키워드 결과: {total_common}개")
    print(f"\n통계:")
    print(f"   총 검색: {stats['total_searches']}회")
    print(f"   성공: {stats['successful_searches']}회 ({stats['success_rate']})")
    print(f"   연속 실패: {stats['consecutive_failures']}회")
    print(f"   차단 상태: {'🚨 차단됨' if stats['is_blocked'] else '✅ 정상'}")
    print(f"   최종 delay: {stats['current_delay']}")
    print(f"\nAPI 호출:")
    print(f"   요청: {stats['requests']}건")
    print(f"   에러: {stats['errors']}건 ({stats['error_rate']})")
    print(f"{'='*60}\n")

    # 평가
    if total_common == 0:
        print("❌ 일반 키워드에서도 0개 - 여전히 문제 있음")
    elif stats['consecutive_failures'] >= 10:
        print("⚠️  차단 감지 메커니즘 작동 (5분 대기)")
    else:
        print("✅ 정상 작동 - 롱테일 키워드는 결과가 적을 수 있음")
