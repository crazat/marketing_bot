#!/usr/bin/env python3
"""
SERP 분석기 디버그 테스트
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import re
from bs4 import BeautifulSoup

def test_serp(keyword):
    print(f"\n{'='*60}")
    print(f"키워드: {keyword}")
    print("=" * 60)

    url = "https://search.naver.com/search.naver"
    params = {
        "where": "blog",
        "query": keyword,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")

    soup = BeautifulSoup(response.text, 'html.parser')

    # 블로그 포스트 링크 찾기
    post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')

    results = []
    seen_urls = set()

    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        match = post_pattern.search(href)

        if not match:
            continue

        if href in seen_urls:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        seen_urls.add(href)
        username = match.group(1)

        # 날짜 찾기
        pub_date = ""
        days_since = 180

        parent = link.parent
        for _ in range(10):
            if parent is None:
                break
            text = parent.get_text()

            date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
            if date_match and not pub_date:
                pub_date = date_match.group(1)

            days_match = re.search(r'(\d+)일 전', text)
            if days_match and days_since == 180:
                days_since = int(days_match.group(1))
                pub_date = f"{days_since}일 전"

            parent = parent.parent

        results.append({
            'rank': len(results) + 1,
            'title': title[:60],
            'url': href[:60],
            'blog_name': username,
            'pub_date': pub_date,
            'days_since': days_since
        })

        if len(results) >= 10:
            break

    print(f"\n블로그 결과: {len(results)}개")

    for r in results:
        print(f"\n  {r['rank']}. {r['title']}...")
        print(f"     블로그: {r['blog_name']} | 날짜: {r['pub_date']} ({r['days_since']}일 전)")

    # 난이도 계산 (간단 버전)
    if results:
        # 오래된 글이 많으면 기회 높음
        old_posts = sum(1 for r in results[:5] if r['days_since'] > 180)
        opportunity = old_posts * 20

        # 공식 블로그 체크 (한의원, 병원 키워드)
        official_blogs = sum(1 for r in results[:5]
                            if any(kw in r['blog_name'].lower() or kw in r['title'].lower()
                                   for kw in ['한의원', '병원', '의원', '클리닉']))
        difficulty = official_blogs * 20

        print(f"\n📊 분석 결과:")
        print(f"   난이도: {difficulty}/100 (공식 블로그 {official_blogs}개)")
        print(f"   기회: {opportunity}/100 (오래된 글 {old_posts}개)")

        if difficulty <= 30 and opportunity >= 60:
            grade = "S"
        elif difficulty <= 50 and opportunity >= 40:
            grade = "A"
        elif difficulty <= 70:
            grade = "B"
        else:
            grade = "C"

        print(f"   등급: {grade}급")

    return results


if __name__ == "__main__":
    keywords = [
        "청주 한의원",
        "청주 다이어트 한의원",
        "청주 교통사고 한의원",
    ]

    for kw in keywords:
        test_serp(kw)

    print("\n" + "=" * 60)
    print("테스트 완료!")
