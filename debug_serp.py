#!/usr/bin/env python3
"""
네이버 검색 결과 HTML 구조 디버깅
"""
import requests
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

def debug_serp(keyword):
    print(f"\n{'='*70}")
    print(f"키워드: {keyword}")
    print("=" * 70)

    url = "https://search.naver.com/search.naver"
    params = {
        "where": "blog",
        "query": keyword,
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    response = requests.get(url, params=params, headers=headers, timeout=10)
    print(f"Status: {response.status_code}")
    print(f"URL: {response.url}")

    soup = BeautifulSoup(response.text, 'html.parser')

    # HTML 저장 (디버깅용)
    with open("debug_serp.html", "w", encoding="utf-8") as f:
        f.write(response.text)
    print("HTML saved to debug_serp.html")

    # 여러 선택자 시도
    print("\n[선택자 테스트]")

    selectors = [
        ".api_txt_lines.total_tit",
        ".title_link",
        ".sh_blog_title",
        "a.title_link",
        ".lst_total li",
        ".bx",
        ".total_wrap",
        ".sp_blog",
        ".blog_txt_wrap",
        ".detail_box",
        ".title_area",
        "li.bx",
        ".list_info",
        ".view_wrap",
        ".total_area",
        ".blog_list",
        ".blog_item",
        "[class*='blog']",
        "[class*='title']",
    ]

    for sel in selectors:
        items = soup.select(sel)
        if items:
            print(f"  {sel}: {len(items)}개")
            # 첫 번째 아이템 내용 출력
            first = items[0]
            text = first.get_text(strip=True)[:100]
            print(f"    First item: {text}...")

    # 모든 링크 찾기
    print("\n[블로그 링크 찾기]")
    all_links = soup.find_all('a', href=True)
    blog_links = [a for a in all_links if 'blog.naver.com' in a.get('href', '')]
    print(f"  blog.naver.com 링크: {len(blog_links)}개")

    for i, link in enumerate(blog_links[:5], 1):
        href = link.get('href', '')
        text = link.get_text(strip=True)[:50]
        print(f"    {i}. {text}... -> {href[:60]}...")

    # section/article 찾기
    print("\n[구조 분석]")
    sections = soup.select("section, article, .area_list, .search_result")
    for sec in sections[:3]:
        class_name = sec.get('class', [])
        id_name = sec.get('id', '')
        print(f"  {sec.name}: class={class_name}, id={id_name}")


if __name__ == "__main__":
    debug_serp("청주 한의원")
