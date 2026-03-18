#!/usr/bin/env python3
"""
Naver 자동완성 API 테스트
- API 호출이 정상적으로 작동하는지 확인
- 반환 데이터 구조 파악
"""
import requests
import json
import time

def test_autocomplete(keyword: str) -> dict:
    """
    Naver 자동완성 API 테스트
    """
    print(f"\n{'='*60}")
    print(f"테스트 키워드: {keyword}")
    print('='*60)

    url = "https://ac.search.naver.com/nx/ac"

    params = {
        "q": keyword,
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
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Referer": "https://www.naver.com/"
    }

    try:
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()

        print(f"✅ 상태 코드: {response.status_code}")
        print(f"✅ 응답 길이: {len(response.text)} bytes")

        data = response.json()

        # 전체 응답 출력 (디버깅용)
        print(f"\n📦 전체 응답:")
        print(json.dumps(data, ensure_ascii=False, indent=2))

        # 응답 구조 분석
        print(f"\n📦 응답 구조:")
        print(f"   - 키: {list(data.keys())}")

        if "items" in data:
            items = data["items"]
            print(f"   - items 개수: {len(items)}")

            if items and len(items) > 0:
                print(f"\n📋 자동완성 결과:")
                # items[0]이 자동완성 리스트
                autocomplete_list = items[0] if isinstance(items[0], list) else items

                for i, item in enumerate(autocomplete_list[:10], 1):
                    if isinstance(item, list):
                        keyword_text = item[0] if item else ""
                    else:
                        keyword_text = item
                    print(f"   {i}. {keyword_text}")

                return {
                    "success": True,
                    "keyword": keyword,
                    "results": autocomplete_list,
                    "count": len(autocomplete_list)
                }

        print("⚠️ 예상과 다른 응답 구조")
        print(f"   전체 응답: {json.dumps(data, ensure_ascii=False, indent=2)[:500]}")

        return {
            "success": False,
            "keyword": keyword,
            "raw_response": data
        }

    except requests.exceptions.RequestException as e:
        print(f"❌ 요청 실패: {e}")
        return {
            "success": False,
            "keyword": keyword,
            "error": str(e)
        }
    except json.JSONDecodeError as e:
        print(f"❌ JSON 파싱 실패: {e}")
        print(f"   응답 내용: {response.text[:200]}")
        return {
            "success": False,
            "keyword": keyword,
            "error": str(e)
        }


def main():
    print("=" * 60)
    print("🔍 Naver 자동완성 API 테스트")
    print("=" * 60)

    # 테스트 키워드 목록
    test_keywords = [
        "청주 한의원",
        "청주 다이어트",
        "청주 교통사고",
        "청주 탈모",
        "오창 한의원"
    ]

    results = []

    for keyword in test_keywords:
        result = test_autocomplete(keyword)
        results.append(result)
        time.sleep(0.5)  # API 부하 방지

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 테스트 결과 요약")
    print("=" * 60)

    success_count = sum(1 for r in results if r.get("success"))
    print(f"성공: {success_count}/{len(results)}")

    for r in results:
        status = "✅" if r.get("success") else "❌"
        count = r.get("count", 0)
        print(f"   {status} {r['keyword']}: {count}개 자동완성")


if __name__ == "__main__":
    main()
