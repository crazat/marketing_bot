#!/usr/bin/env python3
"""
Naver 자동완성 API 테스트 V2
- 여러 API 엔드포인트 시도
- 다양한 파라미터 조합 테스트
"""
import requests
import json
import time
import urllib.parse

def test_method_1(keyword: str) -> dict:
    """
    방법 1: suggest API
    """
    print(f"\n--- 방법 1: suggest API ---")

    url = "https://ac.search.naver.com/nx/ac"
    params = {
        "q": keyword,
        "q_enc": "UTF-8",
        "st": 100,
        "frm": "nv",
        "r_format": "json",
        "r_enc": "UTF-8",
        "r_unicode": 0,
        "t_koreng": 1,
        "ans": 2,
        "run": 2,
        "rev": 4,
        "con": 1
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.naver.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"   URL: {response.url}")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:300]}")
        return {"method": 1, "success": response.status_code == 200, "data": response.json()}
    except Exception as e:
        print(f"   Error: {e}")
        return {"method": 1, "success": False, "error": str(e)}


def test_method_2(keyword: str) -> dict:
    """
    방법 2: 모바일 자동완성 API
    """
    print(f"\n--- 방법 2: 모바일 API ---")

    url = "https://mac.search.naver.com/mobile/ac"
    params = {
        "q": keyword,
        "q_enc": "UTF-8",
        "st": 100,
        "r_format": "json",
        "r_enc": "UTF-8",
        "r_unicode": 0,
        "t_koreng": 1
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
        "Referer": "https://m.naver.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"   URL: {response.url}")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:300]}")
        return {"method": 2, "success": response.status_code == 200, "data": response.json() if response.status_code == 200 else None}
    except Exception as e:
        print(f"   Error: {e}")
        return {"method": 2, "success": False, "error": str(e)}


def test_method_3(keyword: str) -> dict:
    """
    방법 3: 통합검색 자동완성
    """
    print(f"\n--- 방법 3: 통합검색 API ---")

    # 공백 없이 테스트
    keyword_no_space = keyword.replace(" ", "")

    url = "https://ac.search.naver.com/nx/ac"
    params = {
        "q": keyword_no_space,
        "con": 1,
        "frm": "nv",
        "ans": 2,
        "r_format": "json",
        "r_enc": "UTF-8",
        "r_unicode": 0,
        "t_koreng": 1,
        "run": 2,
        "rev": 4,
        "q_enc": "UTF-8"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.naver.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"   키워드 (공백제거): {keyword_no_space}")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:500]}")
        return {"method": 3, "success": response.status_code == 200, "data": response.json() if response.status_code == 200 else None}
    except Exception as e:
        print(f"   Error: {e}")
        return {"method": 3, "success": False, "error": str(e)}


def test_method_4(keyword: str) -> dict:
    """
    방법 4: 짧은 키워드로 테스트 (공백 전까지만)
    """
    print(f"\n--- 방법 4: 짧은 키워드 ---")

    # 첫 단어만 사용
    short_keyword = keyword.split()[0] if " " in keyword else keyword

    url = "https://ac.search.naver.com/nx/ac"
    params = {
        "q": short_keyword,
        "con": 1,
        "frm": "nv",
        "ans": 2,
        "r_format": "json",
        "r_enc": "UTF-8",
        "r_unicode": 0,
        "t_koreng": 1,
        "run": 2,
        "rev": 4,
        "q_enc": "UTF-8"
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.naver.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"   키워드: {short_keyword}")
        print(f"   Status: {response.status_code}")
        data = response.json()
        print(f"   Response: {json.dumps(data, ensure_ascii=False)[:500]}")

        # items 분석
        if "items" in data and data["items"]:
            items = data["items"][0] if data["items"] else []
            print(f"   자동완성 개수: {len(items)}")
            if items:
                print(f"   샘플 (처음 5개):")
                for i, item in enumerate(items[:5]):
                    text = item[0] if isinstance(item, list) else item
                    print(f"      {i+1}. {text}")

        return {"method": 4, "success": response.status_code == 200, "data": data}
    except Exception as e:
        print(f"   Error: {e}")
        return {"method": 4, "success": False, "error": str(e)}


def test_method_5(keyword: str) -> dict:
    """
    방법 5: 네이버 검색 페이지에서 연관검색어 직접 크롤링
    """
    print(f"\n--- 방법 5: 검색 페이지 크롤링 ---")

    url = f"https://search.naver.com/search.naver"
    params = {
        "where": "nexearch",
        "query": keyword
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        print(f"   Status: {response.status_code}")
        print(f"   Response 길이: {len(response.text)} bytes")

        # 연관검색어 추출 시도
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(response.text, 'html.parser')

        # 연관검색어 영역 찾기
        related_keywords = []

        # 방법 5-1: 연관검색어 클래스로 찾기
        related_area = soup.select('.related_srch .keyword')
        if related_area:
            for item in related_area:
                related_keywords.append(item.get_text(strip=True))

        # 방법 5-2: 다른 선택자 시도
        if not related_keywords:
            related_area = soup.select('[class*="relate"] a')
            for item in related_area:
                text = item.get_text(strip=True)
                if text and text != keyword:
                    related_keywords.append(text)

        # 방법 5-3: data-area="rel" 속성으로 찾기
        if not related_keywords:
            related_area = soup.select('[data-area="rel"] a')
            for item in related_area:
                text = item.get_text(strip=True)
                if text:
                    related_keywords.append(text)

        print(f"   연관검색어 개수: {len(related_keywords)}")
        if related_keywords:
            print(f"   연관검색어:")
            for i, kw in enumerate(related_keywords[:10], 1):
                print(f"      {i}. {kw}")

        return {"method": 5, "success": len(related_keywords) > 0, "keywords": related_keywords}

    except ImportError:
        print("   ⚠️ BeautifulSoup 필요: pip install beautifulsoup4")
        return {"method": 5, "success": False, "error": "BeautifulSoup not installed"}
    except Exception as e:
        print(f"   Error: {e}")
        return {"method": 5, "success": False, "error": str(e)}


def main():
    print("=" * 60)
    print("🔍 Naver 자동완성 API 테스트 V2")
    print("   다양한 방법 시도")
    print("=" * 60)

    test_keyword = "청주 한의원"

    print(f"\n테스트 키워드: {test_keyword}")

    # 모든 방법 테스트
    results = []

    results.append(test_method_1(test_keyword))
    time.sleep(0.5)

    results.append(test_method_2(test_keyword))
    time.sleep(0.5)

    results.append(test_method_3(test_keyword))
    time.sleep(0.5)

    results.append(test_method_4(test_keyword))
    time.sleep(0.5)

    results.append(test_method_5(test_keyword))

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)

    for r in results:
        status = "✅" if r.get("success") else "❌"
        method = r.get("method", "?")
        print(f"   방법 {method}: {status}")


if __name__ == "__main__":
    main()
