#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
특정 키워드로 viral_hunter.py 로직 테스트
사용자가 실행했던 키워드 중 하나로 직접 테스트
"""

import sys
import os

# 프로젝트 루트 경로 추가
sys.path.insert(0, '/mnt/c/Projects/marketing_bot')

# Windows 인코딩
sys.stdout.reconfigure(encoding='utf-8')

def test_viral_hunter_single_keyword():
    """viral_hunter.py의 실제 로직으로 단일 키워드 테스트"""
    from viral_hunter import NaverUnifiedSearch

    # 사용자 로그에 나온 첫 번째 키워드
    test_keywords = [
        "복대동 다이어트",
        "청주 한의원",
        "청주 다이어트",
        "청주 새살침 효과"  # 로그에 파싱 에러가 났던 키워드
    ]

    # NaverUnifiedSearch 초기화
    searcher = NaverUnifiedSearch(delay=1.0, max_retries=3, use_cache=False)

    for keyword in test_keywords:
        print(f"\n{'='*60}")
        print(f"🎯 테스트 키워드: '{keyword}'")
        print(f"{'='*60}\n")

        # 카페 검색
        print("☕ 카페 검색...")
        try:
            cafe_results = searcher.search_cafe(keyword, max_results=10, max_pages=1)
            print(f"   결과: {len(cafe_results)}개")
            if cafe_results:
                print(f"   예시:")
                for i, target in enumerate(cafe_results[:3], 1):
                    print(f"      {i}. {target.title[:60]}")
                    print(f"         URL: {target.url[:80]}")
        except Exception as e:
            print(f"   ❌ 에러: {e}")

        # 블로그 검색
        print("\n📝 블로그 검색...")
        try:
            blog_results = searcher.search_blog(keyword, max_results=10, max_pages=1)
            print(f"   결과: {len(blog_results)}개")
            if blog_results:
                print(f"   예시:")
                for i, target in enumerate(blog_results[:3], 1):
                    print(f"      {i}. {target.title[:60]}")
                    print(f"         URL: {target.url[:80]}")
        except Exception as e:
            print(f"   ❌ 에러: {e}")

        # 지식인 검색
        print("\n❓ 지식인 검색...")
        try:
            kin_results = searcher.search_kin(keyword, max_results=10, max_pages=1)
            print(f"   결과: {len(kin_results)}개")
            if kin_results:
                print(f"   예시:")
                for i, target in enumerate(kin_results[:3], 1):
                    print(f"      {i}. {target.title[:60]}")
                    print(f"         URL: {target.url[:80]}")
        except Exception as e:
            print(f"   ❌ 에러: {e}")

    # 통계 출력
    print(f"\n{'='*60}")
    print("📊 API 호출 통계:")
    stats = searcher.get_stats()
    for key, value in stats.items():
        print(f"   {key}: {value}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    test_viral_hunter_single_keyword()
