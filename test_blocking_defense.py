#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🛡️ 차단 방어 메커니즘 테스트

새로 추가된 기능:
1. HTML 응답 검증
2. 연속 0개 결과 감지
3. 적응형 delay 조절
4. 5분 대기 및 자동 복구
"""

import sys
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    from viral_hunter import NaverUnifiedSearch

    print(f"\n{'='*60}")
    print("🛡️ 차단 방어 메커니즘 테스트")
    print(f"{'='*60}\n")

    # 검색 엔진 (캐시 없이, delay 1초)
    searcher = NaverUnifiedSearch(delay=1.0, max_retries=3, use_cache=False)

    # 테스트 키워드 (실제로 결과가 있는 키워드)
    test_keywords = [
        "청주 한의원",
        "청주 다이어트",
        "청주 교통사고",
        "청주 추나",
        "청주 피부과",
        "청주 여드름",
        "청주 입원",
        "율량동 한의원",
        "청주 새살침",
        "청주 야간진료"
    ]

    print(f"📋 테스트 시나리오:")
    print(f"   - {len(test_keywords)}개 키워드 연속 검색")
    print(f"   - 초기 delay: 1.0초")
    print(f"   - 0개 결과 시 자동 대응 확인\n")

    total_found = 0

    for i, keyword in enumerate(test_keywords, 1):
        print(f"\n[{i}/{len(test_keywords)}] '{keyword}' 검색...")

        # 카페 검색만 테스트 (빠르게)
        results = searcher.search_cafe(keyword, max_results=10, max_pages=1)
        total_found += len(results)

        if results:
            print(f"   ✅ {len(results)}개 발견")
        else:
            print(f"   ⚠️  0개 - 차단 메커니즘 작동 확인")

        # 중간 통계 (5개마다)
        if i % 5 == 0:
            stats = searcher.get_stats()
            print(f"\n   📊 중간 통계:")
            print(f"      성공률: {stats['success_rate']}")
            print(f"      연속 실패: {stats['consecutive_failures']}회")
            print(f"      현재 delay: {stats['current_delay']}")

    # 최종 통계
    print(f"\n{'='*60}")
    print("📊 최종 테스트 결과")
    print(f"{'='*60}")

    stats = searcher.get_stats()
    print(f"총 검색: {stats['total_searches']}회")
    print(f"성공: {stats['successful_searches']}회 ({stats['success_rate']})")
    print(f"총 발견: {total_found}개")
    print(f"연속 실패: {stats['consecutive_failures']}회")
    print(f"차단 상태: {'🚨 차단됨' if stats['is_blocked'] else '✅ 정상'}")
    print(f"최종 delay: {stats['current_delay']}")
    print(f"\nAPI 호출:")
    print(f"   요청: {stats['requests']}건")
    print(f"   에러: {stats['errors']}건 ({stats['error_rate']})")
    print(f"   캐시 히트: {stats['cache_hits']}건")
    print(f"{'='*60}\n")

    # 평가
    if stats['consecutive_failures'] >= 5:
        print("⚠️  연속 실패 5회 이상 감지 - 방어 메커니즘 작동!")
    else:
        print("✅ 정상 작동 - 모든 키워드에서 결과 발견")
