#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
순수 검색 기능만 테스트 (DB 없이)
"""

import sys
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')
sys.stdout.reconfigure(encoding='utf-8')

if __name__ == "__main__":
    from viral_hunter import NaverUnifiedSearch

    # 검색 엔진 (캐시 없이)
    searcher = NaverUnifiedSearch(delay=1.0, max_retries=3, use_cache=False)

    # 테스트 키워드 (사용자 로그의 첫 10개)
    test_keywords = [
        "복대동 다이어트",
        "청주 한의원",
        "청주 다이어트",
        "청주 새살침 효과",
        "청주 교통사고",
        "청주 추나",
        "청주 피부과",
        "청주 여드름",
        "청주 입원",
        "율량동 한의원"
    ]

    print(f"\n{'='*60}")
    print(f"🔍 순수 검색 테스트 (DB 없이)")
    print(f"   키워드: {len(test_keywords)}개")
    print(f"{'='*60}\n")

    total_found = 0
    keyword_results = {}

    for i, keyword in enumerate(test_keywords, 1):
        print(f"[{i}/{len(test_keywords)}] '{keyword}' 검색 중...")

        try:
            results = searcher.search_all(keyword, max_per_platform=10)
            total_found += len(results)
            keyword_results[keyword] = len(results)

            if results:
                print(f"   ✅ {len(results)}개 발견")
            else:
                print(f"   ⚠️  0개")

        except Exception as e:
            print(f"   ❌ 에러: {e}")
            keyword_results[keyword] = -1

    print(f"\n{'='*60}")
    print(f"📊 테스트 결과 요약")
    print(f"{'='*60}")
    print(f"총 발견: {total_found}개")
    print(f"\n키워드별 결과:")

    for kw, count in keyword_results.items():
        if count == -1:
            status = "❌ 에러"
        elif count == 0:
            status = "⚠️  0개"
        else:
            status = f"✅ {count}개"
        print(f"  {status} | {kw}")

    # 통계
    stats = searcher.get_stats()
    print(f"\n{'='*60}")
    print(f"📈 API 호출 통계:")
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print(f"{'='*60}\n")

    # 결론
    if total_found == 0:
        print("⚠️  모든 키워드에서 0개 반환 - 원래 문제가 재현됨")
    elif total_found < len(test_keywords) * 5:
        print("⚠️  일부 키워드에서만 결과 발견 - 부분적 문제")
    else:
        print("✅ 대부분의 키워드에서 결과 발견 - 정상 작동")
