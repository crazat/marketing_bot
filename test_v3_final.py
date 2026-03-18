#!/usr/bin/env python3
"""
Pathfinder V3 최종 테스트
- 한의원 관련 키워드만 필터링
- KEI 계산 포함
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from scrapers.naver_autocomplete import NaverAutocompleteScraper
from scrapers.naver_ad_manager import NaverAdManager

def calculate_kei(vol, supply):
    """KEI (Keyword Efficiency Index) 계산"""
    if supply == 0:
        return 0
    return (vol ** 2) / supply

def main():
    print("=" * 70)
    print("🧪 Pathfinder V3 최종 테스트 (한의원 관련만)")
    print("=" * 70)

    # 1. 간결한 시드 생성
    seeds = []
    base_region = "청주"

    category_terms = {
        "다이어트": ["다이어트", "다이어트한약", "다이어트약", "비만", "살빼기"],
        "여드름_피부": ["여드름", "피부", "모공", "피부관리", "아토피"],
        "교통사고": ["교통사고", "교통사고한의원", "자동차사고", "입원"],
        "통증": ["허리통증", "목디스크", "어깨통증", "무릎통증", "관절통증", "통증"],
        "탈모": ["탈모", "탈모치료", "탈모한의원", "두피"],
        "한의원": ["한의원", "한방병원", "침", "한약", "추나"],
        "갱년기": ["갱년기", "폐경", "여성호르몬", "산후조리"],
        "불면증": ["불면증", "수면", "수면장애"],
        "비염": ["비염", "알레르기", "축농증", "코막힘"],
        "교정": ["안면비대칭", "체형교정", "턱관절"],
    }

    intent_modifiers = ["가격", "후기", "추천", "잘하는곳", "효과", "비용"]

    for category, terms in category_terms.items():
        for term in terms:
            seeds.append(f"{base_region} {term}")
            for intent in intent_modifiers[:3]:
                seeds.append(f"{base_region} {term} {intent}")

    # 동네 시드
    dongs = ["오창", "가경동", "복대동", "율량동", "분평동", "오송", "산남동"]
    for dong in dongs:
        for term in ["한의원", "다이어트", "교통사고", "탈모", "통증"]:
            seeds.append(f"{dong} {term}")

    seeds = list(set(seeds))
    print(f"\n📦 시드: {len(seeds)}개")

    # 2. 자동완성 확장
    print("\n🔍 Naver 자동완성 확장 중...")
    scraper = NaverAutocompleteScraper(delay=0.3)

    cheongju_regions = ["청주", "오창", "오송", "복대", "가경", "율량", "분평", "상당", "서원", "흥덕", "산남"]

    expanded = scraper.expand_keywords_bfs(
        seed_keywords=seeds,
        max_depth=2,
        max_total=500,
        region_filter=cheongju_regions
    )
    print(f"✅ 자동완성 결과: {len(expanded)}개")

    # 3. 검색량 조회 (보너스 포함)
    print("\n📊 검색량 조회 중...")
    ad_mgr = NaverAdManager()
    search_vol_map = ad_mgr.get_keyword_volumes(expanded)

    all_keywords = list(search_vol_map.keys())
    print(f"✅ Ad API 총 반환: {len(all_keywords)}개 (보너스: {len(all_keywords) - len(expanded)}개)")

    # 4. 필터링
    # 경쟁사/비한의원 블랙리스트
    competitor_blacklist = [
        "피부과", "성형외과", "정형외과", "산부인과", "이비인후과",
        "내과", "정신과", "비뇨기과", "치과", "안과", "신경외과",
        "미용실", "헤어샵", "네일", "왁싱", "마사지", "에스테틱",
        "필라테스", "요가", "헬스장", "크로스핏", "복싱", "PT",
        "보톡스", "필러", "레이저제모", "울쎄라", "써마지", "인모드",
        "세차", "배터리", "공방", "가구", "블랙박스", "폐기물", "이사",
        "속눈썹", "반영구", "문신", "타투", "네일아트",
        "스노우", "미하이", "365", "비타", "포에버", "동안나라",
        "임플란트", "교정치과", "치아교정", "발치",
    ]

    # 한의원 관련 용어
    hanbang_terms = [
        "한의원", "한방", "한약", "침", "뜸", "추나", "부항", "교정",
        "공진단", "경옥고", "보약", "총명탕", "한방병원"
    ]

    # 한의원 치료 질환
    hanbang_symptoms = [
        "다이어트", "비만", "살빼", "체중", "감량",
        "여드름", "피부", "모공", "흉터", "아토피",
        "탈모", "두피",
        "통증", "디스크", "허리", "목", "어깨", "무릎", "관절",
        "교통사고", "후유증", "입원",
        "안면비대칭", "체형교정", "턱관절", "척추",
        "갱년기", "폐경", "생리", "산후",
        "불면증", "수면",
        "비염", "축농증", "알레르기",
        "두통", "어지럼", "이명",
        "소화", "위장", "역류", "담적",
    ]

    filtered = []
    filter_stats = {"competitor": 0, "not_hanbang": 0, "volume_low": 0, "no_region": 0}

    for kw in all_keywords:
        vol = search_vol_map.get(kw, 0)

        # 청주 지역 필터
        if not any(loc in kw for loc in cheongju_regions):
            filter_stats["no_region"] += 1
            continue

        # 경쟁사 필터
        if any(comp in kw for comp in competitor_blacklist):
            filter_stats["competitor"] += 1
            continue

        # 한의원 관련성 체크
        has_hanbang = any(term in kw for term in hanbang_terms)
        has_symptom = any(term in kw for term in hanbang_symptoms)

        if not (has_hanbang or has_symptom):
            filter_stats["not_hanbang"] += 1
            continue

        # 검색량 필터
        if vol < 5:
            filter_stats["volume_low"] += 1
            continue

        # KEI 계산 (가상 공급량 사용 - 실제로는 블로그 수 조회 필요)
        # 여기서는 검색량만으로 정렬
        filtered.append({
            "keyword": kw,
            "volume": vol
        })

    print(f"\n📋 필터링 결과:")
    print(f"   - 청주 외 지역: {filter_stats['no_region']}개")
    print(f"   - 경쟁사/비한의원: {filter_stats['competitor']}개")
    print(f"   - 한의원 비관련: {filter_stats['not_hanbang']}개")
    print(f"   - 검색량 부족: {filter_stats['volume_low']}개")
    print(f"   → 최종 통과: {len(filtered)}개")

    # 5. Top 키워드 출력
    filtered_sorted = sorted(filtered, key=lambda x: x['volume'], reverse=True)

    print(f"\n💎 한의원 관련 Top 50 키워드 (검색량 순):")
    for i, item in enumerate(filtered_sorted[:50], 1):
        print(f"   {i:2d}. {item['keyword']} (Vol: {item['volume']:,})")

    # 6. 카테고리 분포
    print(f"\n📁 카테고리 분포:")
    cat_count = {}
    for item in filtered:
        kw = item['keyword'].lower()
        if '한의원' in kw or '한방' in kw or '한약' in kw:
            cat = "한의원"
        elif '다이어트' in kw or '비만' in kw or '살빼' in kw:
            cat = "다이어트"
        elif '여드름' in kw or '피부' in kw or '아토피' in kw:
            cat = "피부"
        elif '교통사고' in kw:
            cat = "교통사고"
        elif '통증' in kw or '디스크' in kw or '허리' in kw or '어깨' in kw:
            cat = "통증"
        elif '탈모' in kw or '두피' in kw:
            cat = "탈모"
        elif '갱년기' in kw or '폐경' in kw or '산후' in kw:
            cat = "여성"
        elif '비염' in kw or '알레르기' in kw:
            cat = "비염"
        elif '불면' in kw or '수면' in kw:
            cat = "불면"
        else:
            cat = "기타"
        cat_count[cat] = cat_count.get(cat, 0) + 1

    for cat, cnt in sorted(cat_count.items(), key=lambda x: -x[1]):
        print(f"   {cat}: {cnt}개")

    # 7. 의도별 분류
    print(f"\n🎯 구매 의도 키워드 (가격/후기/추천/잘하는곳):")
    intent_kws = [item for item in filtered_sorted if any(sig in item['keyword'] for sig in ["가격", "비용", "후기", "추천", "잘하는"])]
    for i, item in enumerate(intent_kws[:20], 1):
        print(f"   {i:2d}. {item['keyword']} (Vol: {item['volume']:,})")

    print(f"\n✅ 총 {len(filtered)}개 한의원 관련 키워드 수집!")
    print(f"   - 구매 의도 키워드: {len(intent_kws)}개")


if __name__ == "__main__":
    main()
