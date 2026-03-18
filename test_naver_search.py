#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
네이버 검색 HTML 구조 디버깅 스크립트
- 실제 네이버 검색 페이지를 크롤링해서 HTML 구조 확인
- 어떤 선택자를 사용해야 하는지 파악
"""

import requests
from bs4 import BeautifulSoup
import sys

# Windows 인코딩 문제 해결
sys.stdout.reconfigure(encoding='utf-8')

def test_naver_cafe_search(keyword: str):
    """네이버 카페 검색 HTML 구조 분석"""
    print(f"\n{'='*60}")
    print(f"🔍 네이버 카페 검색: '{keyword}'")
    print(f"{'='*60}\n")

    url = "https://search.naver.com/search.naver"
    params = {
        "where": "article",
        "query": keyword,
        "start": 1,
        "nso": "so:r,p:all"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.naver.com/",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        print(f"✅ HTTP {response.status_code}")
        print(f"📄 Content-Length: {len(response.text):,} bytes\n")

        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 전체 <a> 태그 수
        all_links = soup.find_all('a', href=True)
        print(f"🔗 전체 링크 수: {len(all_links)}개")

        # 2. cafe.naver.com이 포함된 링크 수
        cafe_links = [link for link in all_links if 'cafe.naver.com' in link.get('href', '')]
        print(f"☕ cafe.naver.com 링크: {len(cafe_links)}개")

        if cafe_links:
            print("\n📋 발견된 카페 링크 (처음 5개):")
            for i, link in enumerate(cafe_links[:5], 1):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                print(f"   {i}. [{text[:50]}...] -> {href[:80]}...")

        # 3. 주요 선택자 후보 확인
        print("\n🎯 주요 HTML 구조 분석:")

        selectors = [
            (".lst_total", "검색 결과 리스트 (구버전)"),
            (".api_subject_bx", "검색 결과 박스 (API)"),
            (".total_wrap", "검색 결과 래퍼"),
            (".total_area", "검색 결과 영역"),
            (".main_pack", "메인 검색 결과"),
            (".view_wrap", "VIEW 검색 결과"),
            (".bx", "검색 결과 박스"),
            ("#main_pack", "메인 팩 (ID)"),
        ]

        for selector, desc in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"   ✅ {selector}: {len(elements)}개 ({desc})")
                # 해당 영역 내 카페 링크 수
                cafe_in_area = []
                for elem in elements:
                    cafe_in_area.extend([link for link in elem.find_all('a', href=True)
                                        if 'cafe.naver.com' in link.get('href', '')])
                if cafe_in_area:
                    print(f"      → 카페 링크: {len(cafe_in_area)}개")
            else:
                print(f"   ❌ {selector}: 없음")

        # 4. HTML 샘플 저장 (디버깅용)
        sample_file = "/mnt/c/Projects/marketing_bot/debug_naver_cafe.html"
        with open(sample_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n💾 HTML 샘플 저장: {sample_file}")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")


def test_naver_blog_search(keyword: str):
    """네이버 블로그 검색 HTML 구조 분석"""
    print(f"\n{'='*60}")
    print(f"🔍 네이버 블로그 검색: '{keyword}'")
    print(f"{'='*60}\n")

    url = "https://search.naver.com/search.naver"
    params = {
        "where": "blog",
        "query": keyword,
        "start": 1,
        "nso": "so:r,p:all"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.naver.com/",
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        print(f"✅ HTTP {response.status_code}")
        print(f"📄 Content-Length: {len(response.text):,} bytes\n")

        soup = BeautifulSoup(response.text, 'html.parser')

        # 1. 전체 <a> 태그 수
        all_links = soup.find_all('a', href=True)
        print(f"🔗 전체 링크 수: {len(all_links)}개")

        # 2. blog.naver.com이 포함된 링크 수
        blog_links = [link for link in all_links if 'blog.naver.com' in link.get('href', '')]
        print(f"📝 blog.naver.com 링크: {len(blog_links)}개")

        if blog_links:
            print("\n📋 발견된 블로그 링크 (처음 5개):")
            for i, link in enumerate(blog_links[:5], 1):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                print(f"   {i}. [{text[:50]}...] -> {href[:80]}...")

        # 3. 주요 선택자 후보 확인
        print("\n🎯 주요 HTML 구조 분석:")

        selectors = [
            (".lst_total", "검색 결과 리스트 (구버전)"),
            (".api_subject_bx", "검색 결과 박스 (API)"),
            (".total_wrap", "검색 결과 래퍼"),
            (".total_area", "검색 결과 영역"),
            (".main_pack", "메인 검색 결과"),
            (".view_wrap", "VIEW 검색 결과"),
            (".bx", "검색 결과 박스"),
            ("#main_pack", "메인 팩 (ID)"),
        ]

        for selector, desc in selectors:
            elements = soup.select(selector)
            if elements:
                print(f"   ✅ {selector}: {len(elements)}개 ({desc})")
                # 해당 영역 내 블로그 링크 수
                blog_in_area = []
                for elem in elements:
                    blog_in_area.extend([link for link in elem.find_all('a', href=True)
                                        if 'blog.naver.com' in link.get('href', '')])
                if blog_in_area:
                    print(f"      → 블로그 링크: {len(blog_in_area)}개")
            else:
                print(f"   ❌ {selector}: 없음")

        # 4. HTML 샘플 저장 (디버깅용)
        sample_file = "/mnt/c/Projects/marketing_bot/debug_naver_blog.html"
        with open(sample_file, 'w', encoding='utf-8') as f:
            f.write(response.text)
        print(f"\n💾 HTML 샘플 저장: {sample_file}")

    except Exception as e:
        print(f"❌ 에러 발생: {e}")


if __name__ == "__main__":
    # 테스트 키워드
    test_keyword = "청주 한의원"

    # 카페 검색 테스트
    test_naver_cafe_search(test_keyword)

    # 블로그 검색 테스트
    test_naver_blog_search(test_keyword)

    print(f"\n{'='*60}")
    print("✅ 디버깅 완료")
    print("   다음 단계: HTML 파일을 열어서 실제 검색 결과 링크의 구조를 확인하세요.")
    print(f"{'='*60}\n")
