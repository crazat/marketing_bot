#!/usr/bin/env python3
"""
SERP 분석기 최종 테스트
- Phase 2 기능 검증
- 난이도/기회 점수 계산
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import requests
import re
from bs4 import BeautifulSoup
from datetime import datetime
from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class BlogResult:
    rank: int
    title: str
    url: str
    blog_name: str
    days_since_publish: int
    is_official: bool

def parse_date(date_str: str) -> int:
    """날짜 문자열에서 경과일 계산"""
    now = datetime.now()

    # "X일 전" 패턴
    match = re.search(r"(\d+)일 전", date_str)
    if match:
        return int(match.group(1))

    # "X시간 전", "X분 전" 패턴
    if "시간 전" in date_str or "분 전" in date_str:
        return 0

    # "YYYY.MM.DD" 패턴
    match = re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})", date_str)
    if match:
        try:
            pub_date = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            days = (now - pub_date).days
            return max(0, days) if days >= 0 else 30
        except:
            pass

    return 90  # 기본값

def detect_official(blog_name: str, title: str) -> bool:
    """공식 블로그 여부 감지"""
    text = (blog_name + " " + title).lower()
    official_keywords = ["한의원", "병원", "의원", "클리닉", "센터", "공식"]
    return any(kw in text for kw in official_keywords)

def analyze_serp(keyword: str) -> Tuple[List[BlogResult], int, int, str]:
    """
    SERP 분석

    Returns:
        (블로그 결과 리스트, 난이도, 기회점수, 등급)
    """
    url = "https://search.naver.com/search.naver"
    params = {"where": "blog", "query": keyword}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, 'html.parser')

    # 블로그 포스트 링크 파싱
    post_pattern = re.compile(r'blog\.naver\.com/(\w+)/(\d+)')
    results = []
    seen_urls = set()

    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        match = post_pattern.search(href)

        if not match or href in seen_urls:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 5:
            continue

        seen_urls.add(href)
        username = match.group(1)

        # 날짜 찾기
        days_since = 90
        parent = link.parent
        for _ in range(10):
            if parent is None:
                break
            text = parent.get_text()

            # YYYY.MM.DD 패턴
            date_match = re.search(r'(\d{4}\.\d{1,2}\.\d{1,2})', text)
            if date_match:
                days_since = parse_date(date_match.group(1))
                break

            # X일 전 패턴
            days_match = re.search(r'(\d+)일 전', text)
            if days_match:
                days_since = int(days_match.group(1))
                break

            parent = parent.parent

        is_official = detect_official(username, title)

        results.append(BlogResult(
            rank=len(results) + 1,
            title=title,
            url=href,
            blog_name=username,
            days_since_publish=days_since,
            is_official=is_official
        ))

        if len(results) >= 10:
            break

    # 난이도 계산 (0-100)
    difficulty = 0
    for blog in results[:5]:
        if blog.is_official:
            difficulty += 15
        if blog.days_since_publish <= 30:
            difficulty += 10
        elif blog.days_since_publish <= 90:
            difficulty += 5

    # 기회 점수 계산 (0-100)
    opportunity = 0
    for i, blog in enumerate(results[:5]):
        weight = (5 - i)  # 상위일수록 가중치

        if blog.days_since_publish > 180:
            opportunity += 10 * weight
        elif blog.days_since_publish > 90:
            opportunity += 5 * weight

        if not blog.is_official:
            opportunity += 8 * weight

    opportunity = min(opportunity, 100)

    # 등급 결정
    if difficulty <= 30 and opportunity >= 60:
        grade = "S"
    elif difficulty <= 50 and opportunity >= 40:
        grade = "A"
    elif difficulty <= 70:
        grade = "B"
    else:
        grade = "C"

    return results, difficulty, opportunity, grade


def main():
    print("=" * 70)
    print("Phase 2: SERP 분석기 테스트")
    print("=" * 70)

    test_keywords = [
        "청주 한의원",
        "청주 다이어트 한의원",
        "청주 교통사고 한의원",
        "청주 탈모 치료",
        "오창 한의원",
        "청주 한의원 추천",
        "청주 비염 한의원",
        "가경동 한의원",
    ]

    all_results = []

    for kw in test_keywords:
        print(f"\n{'='*60}")
        print(f"키워드: {kw}")
        print("-" * 60)

        try:
            blogs, difficulty, opportunity, grade = analyze_serp(kw)

            print(f"블로그 결과: {len(blogs)}개")
            print(f"난이도: {difficulty}/100 ({'낮음' if difficulty <= 30 else '보통' if difficulty <= 60 else '높음'})")
            print(f"기회 점수: {opportunity}/100 ({'좋음' if opportunity >= 60 else '보통' if opportunity >= 30 else '낮음'})")
            print(f"등급: {grade}급")

            print(f"\n상위 5개 블로그:")
            for blog in blogs[:5]:
                official = " [공식]" if blog.is_official else ""
                print(f"  {blog.rank}. {blog.title[:45]}...{official}")
                print(f"     {blog.blog_name} | {blog.days_since_publish}일 전")

            all_results.append({
                'keyword': kw,
                'difficulty': difficulty,
                'opportunity': opportunity,
                'grade': grade,
                'blog_count': len(blogs)
            })

        except Exception as e:
            print(f"오류: {e}")

        import time
        time.sleep(1)  # Rate limiting

    # 결과 요약
    print("\n" + "=" * 70)
    print("결과 요약")
    print("=" * 70)

    s_grade = [r for r in all_results if r['grade'] == 'S']
    a_grade = [r for r in all_results if r['grade'] == 'A']
    b_grade = [r for r in all_results if r['grade'] == 'B']
    c_grade = [r for r in all_results if r['grade'] == 'C']

    print(f"\nS급 (즉시 공략): {len(s_grade)}개")
    for r in s_grade:
        print(f"  - {r['keyword']} (난이도: {r['difficulty']}, 기회: {r['opportunity']})")

    print(f"\nA급 (적극 공략): {len(a_grade)}개")
    for r in a_grade:
        print(f"  - {r['keyword']} (난이도: {r['difficulty']}, 기회: {r['opportunity']})")

    print(f"\nB급 (보조 공략): {len(b_grade)}개")
    for r in b_grade:
        print(f"  - {r['keyword']}")

    print(f"\nC급 (장기 전략): {len(c_grade)}개")
    for r in c_grade:
        print(f"  - {r['keyword']}")

    print("\n" + "=" * 70)
    print("테스트 완료!")


if __name__ == "__main__":
    main()
