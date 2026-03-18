#!/usr/bin/env python3
"""
Pathfinder V3 + Ad API 보너스 키워드 테스트
- Naver Ad API가 반환하는 관련 키워드 모두 활용
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapers.naver_autocomplete import NaverAutocompleteScraper
from scrapers.naver_ad_manager import NaverAdManager

def main():
    print("=" * 70)
    print("🧪 V3 + Ad API 보너스 키워드 테스트")
    print("=" * 70)

    # 1. 간결한 시드 생성 (더 많이)
    seeds = []
    base_region = "청주"

    # 더 많은 카테고리와 용어
    category_terms = {
        "다이어트": ["다이어트", "다이어트한약", "다이어트약", "비만", "살빼기", "체중감량"],
        "여드름_피부": ["여드름", "피부", "모공", "피부관리", "여드름치료"],
        "교통사고": ["교통사고", "교통사고한의원", "자동차사고", "입원"],
        "통증": ["허리통증", "목디스크", "어깨통증", "무릎통증", "관절통증", "디스크"],
        "탈모": ["탈모", "탈모치료", "탈모한의원", "두피"],
        "한의원": ["한의원", "한방병원", "침", "한약"],
        "갱년기": ["갱년기", "폐경", "여성호르몬"],
        "불면증": ["불면증", "수면", "수면장애"],
        "비염": ["비염", "알레르기", "축농증", "코막힘"],
    }

    intent_modifiers = ["가격", "후기", "추천", "잘하는곳", "효과"]

    for category, terms in category_terms.items():
        for term in terms:
            seeds.append(f"{base_region} {term}")
            for intent in intent_modifiers[:3]:
                seeds.append(f"{base_region} {term} {intent}")

    # 동네 시드
    dongs = ["오창", "가경동", "복대동", "율량동", "분평동", "오송"]
    for dong in dongs:
        for term in ["한의원", "다이어트", "교통사고", "탈모"]:
            seeds.append(f"{dong} {term}")

    seeds = list(set(seeds))
    print(f"\n📦 시드: {len(seeds)}개")

    # 2. 자동완성 확장
    print("\n🔍 Naver 자동완성 확장 중...")
    scraper = NaverAutocompleteScraper(delay=0.3)

    cheongju_regions = ["청주", "오창", "오송", "복대", "가경", "율량", "분평", "상당", "서원", "흥덕"]

    expanded = scraper.expand_keywords_bfs(
        seed_keywords=seeds,
        max_depth=2,
        max_total=500,
        region_filter=cheongju_regions
    )

    print(f"✅ 자동완성 결과: {len(expanded)}개")

    # 3. 검색량 조회 (Ad API가 보너스 키워드도 반환)
    print("\n📊 검색량 조회 중 (Ad API 보너스 포함)...")
    ad_mgr = NaverAdManager()
    search_vol_map = ad_mgr.get_keyword_volumes(expanded)

    total_keywords = list(search_vol_map.keys())
    print(f"✅ Ad API 총 반환: {len(total_keywords)}개 (보너스: {len(total_keywords) - len(expanded)}개)")

    # 4. 청주 관련 키워드만 필터
    cheongju_keywords = []
    for kw in total_keywords:
        vol = search_vol_map.get(kw, 0)

        # 청주 지역 필터
        if not any(loc in kw for loc in cheongju_regions):
            continue

        cheongju_keywords.append({
            "keyword": kw,
            "volume": vol
        })

    print(f"✅ 청주 관련: {len(cheongju_keywords)}개")

    # 5. 경쟁사 필터 + 검색량 필터
    competitor_blacklist = [
        "피부과", "성형외과", "정형외과", "내과", "미용실", "헤어샵",
        "필라테스", "요가", "헬스장", "마사지", "에스테틱", "비타",
        "스노우", "미하이", "365"
    ]

    filtered = []
    for item in cheongju_keywords:
        kw = item['keyword']
        vol = item['volume']

        # 경쟁사 필터
        if any(comp in kw for comp in competitor_blacklist):
            continue

        # 검색량 필터 (완화: 5 이상)
        if vol < 5:
            continue

        filtered.append(item)

    print(f"✅ 필터 후: {len(filtered)}개")

    # 6. 검색량 분포
    print("\n📈 검색량 분포 (필터 후):")
    vol_5_19 = sum(1 for item in filtered if 5 <= item['volume'] < 20)
    vol_20_49 = sum(1 for item in filtered if 20 <= item['volume'] < 50)
    vol_50_99 = sum(1 for item in filtered if 50 <= item['volume'] < 100)
    vol_100_499 = sum(1 for item in filtered if 100 <= item['volume'] < 500)
    vol_500_plus = sum(1 for item in filtered if item['volume'] >= 500)

    print(f"   Vol 5-19:     {vol_5_19}개")
    print(f"   Vol 20-49:    {vol_20_49}개")
    print(f"   Vol 50-99:    {vol_50_99}개")
    print(f"   Vol 100-499:  {vol_100_499}개")
    print(f"   Vol 500+:     {vol_500_plus}개")

    # 7. Top 50 키워드 (검색량 순)
    filtered_sorted = sorted(filtered, key=lambda x: x['volume'], reverse=True)

    print(f"\n💎 Top 50 키워드 (검색량 순):")
    for i, item in enumerate(filtered_sorted[:50], 1):
        print(f"   {i:2d}. {item['keyword']} (Vol: {item['volume']:,})")

    # 8. 의도별 분류
    print(f"\n📁 구매 의도 키워드:")
    intent_kws = [item for item in filtered_sorted if any(sig in item['keyword'] for sig in ["가격", "비용", "후기", "추천", "잘하는"])]
    for i, item in enumerate(intent_kws[:20], 1):
        print(f"   {i:2d}. {item['keyword']} (Vol: {item['volume']:,})")

    print(f"\n✅ 총 {len(filtered)}개 고품질 키워드 수집 완료!")


if __name__ == "__main__":
    main()
