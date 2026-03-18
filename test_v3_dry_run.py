#!/usr/bin/env python3
"""
Pathfinder V3 Dry Run 테스트
- DB 저장 없이 메모리에서 결과 확인
- 필터 효과 분석
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapers.naver_autocomplete import NaverAutocompleteScraper
from scrapers.naver_ad_manager import NaverAdManager
from scrapers.keyword_harvester import KeywordHarvester

def main():
    print("=" * 70)
    print("🧪 Pathfinder V3 Dry Run 테스트")
    print("=" * 70)

    # 1. 간결한 시드 생성
    seeds = []
    base_region = "청주"

    category_terms = {
        "다이어트": ["다이어트", "다이어트한약", "비만"],
        "여드름_피부": ["여드름", "피부", "모공"],
        "교통사고": ["교통사고", "자동차사고"],
        "통증": ["허리통증", "목디스크", "어깨통증"],
        "탈모": ["탈모", "탈모치료"],
        "한의원": ["한의원", "한방병원"],
    }

    intent_modifiers = ["가격", "후기", "추천"]

    for category, terms in category_terms.items():
        for term in terms:
            seeds.append(f"{base_region} {term}")
            for intent in intent_modifiers[:2]:
                seeds.append(f"{base_region} {term} {intent}")

    # 동네 시드
    dongs = ["오창", "가경동", "복대동"]
    for dong in dongs:
        for term in ["한의원", "다이어트"]:
            seeds.append(f"{dong} {term}")

    seeds = list(set(seeds))
    print(f"\n📦 시드: {len(seeds)}개")
    print(f"   샘플: {seeds[:5]}")

    # 2. 자동완성 확장
    print("\n🔍 Naver 자동완성 확장 중...")
    scraper = NaverAutocompleteScraper(delay=0.3)

    cheongju_regions = ["청주", "오창", "오송", "복대", "가경", "율량", "분평"]

    expanded = scraper.expand_keywords_bfs(
        seed_keywords=seeds,
        max_depth=2,
        max_total=300,
        region_filter=cheongju_regions
    )

    print(f"✅ 자동완성 결과: {len(expanded)}개")

    # 3. 검색량 조회
    print("\n📊 검색량 조회 중...")
    ad_mgr = NaverAdManager()
    search_vol_map = ad_mgr.get_keyword_volumes(expanded)
    print(f"✅ 검색량 데이터: {len(search_vol_map)}개")

    # 4. 검색량 분포 분석
    print("\n📈 검색량 분포 분석:")
    vol_0 = sum(1 for kw in expanded if search_vol_map.get(kw, 0) == 0)
    vol_1_9 = sum(1 for kw in expanded if 1 <= search_vol_map.get(kw, 0) < 10)
    vol_10_49 = sum(1 for kw in expanded if 10 <= search_vol_map.get(kw, 0) < 50)
    vol_50_99 = sum(1 for kw in expanded if 50 <= search_vol_map.get(kw, 0) < 100)
    vol_100_plus = sum(1 for kw in expanded if search_vol_map.get(kw, 0) >= 100)

    print(f"   Vol = 0:      {vol_0}개 ({vol_0/len(expanded)*100:.1f}%)")
    print(f"   Vol 1-9:      {vol_1_9}개 ({vol_1_9/len(expanded)*100:.1f}%)")
    print(f"   Vol 10-49:    {vol_10_49}개 ({vol_10_49/len(expanded)*100:.1f}%)")
    print(f"   Vol 50-99:    {vol_50_99}개 ({vol_50_99/len(expanded)*100:.1f}%)")
    print(f"   Vol 100+:     {vol_100_plus}개 ({vol_100_plus/len(expanded)*100:.1f}%)")

    # 5. 필터 시뮬레이션 (검색량 >= 5 로 완화)
    print("\n🔬 필터 시뮬레이션 (Vol >= 5):")

    competitor_blacklist = [
        "피부과", "성형외과", "정형외과", "내과", "미용실", "헤어샵",
        "필라테스", "요가", "헬스장", "마사지", "에스테틱"
    ]

    filtered = []
    for kw in expanded:
        vol = search_vol_map.get(kw, 0)

        # 경쟁사 필터
        if any(comp in kw for comp in competitor_blacklist):
            continue

        # 검색량 필터 (완화: 5 이상)
        if vol < 5:
            continue

        filtered.append({
            "keyword": kw,
            "volume": vol
        })

    print(f"   필터 통과: {len(filtered)}개")

    # 6. Top 30 키워드 출력 (검색량 순)
    print("\n💎 Top 30 키워드 (검색량 순):")
    filtered_sorted = sorted(filtered, key=lambda x: x['volume'], reverse=True)

    for i, item in enumerate(filtered_sorted[:30], 1):
        print(f"   {i:2d}. {item['keyword']} (Vol: {item['volume']:,})")

    # 7. 카테고리 분포
    print("\n📁 카테고리 추정 분포:")
    category_count = {}
    for item in filtered:
        kw = item['keyword'].lower()
        if '다이어트' in kw or '비만' in kw:
            cat = "다이어트"
        elif '여드름' in kw or '피부' in kw or '모공' in kw:
            cat = "여드름_피부"
        elif '교통사고' in kw:
            cat = "교통사고"
        elif '통증' in kw or '디스크' in kw or '허리' in kw:
            cat = "통증"
        elif '탈모' in kw:
            cat = "탈모"
        elif '한의원' in kw or '한방' in kw:
            cat = "한의원"
        else:
            cat = "기타"

        category_count[cat] = category_count.get(cat, 0) + 1

    for cat, cnt in sorted(category_count.items(), key=lambda x: -x[1]):
        print(f"   {cat}: {cnt}개")


if __name__ == "__main__":
    main()
