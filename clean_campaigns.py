#!/usr/bin/env python3
"""
campaigns.json에서 불필요한 지역 및 경쟁사 키워드 제거
"""
import json

# 제거할 지역명 (오창, 오송은 청주시 청원구에 속하므로 유지)
REMOVE_REGIONS = ["세종", "진천", "증평", "괴산", "보은"]

# 제거할 경쟁사/비한의원 키워드
REMOVE_COMPETITORS = [
    # 다른 의료 업종
    "피부과", "성형외과", "정형외과", "산부인과", "이비인후과",
    # 피부과 장비/시술 (한의원 아님)
    "울쎄라", "인모드", "슈링크", "써마지", "레이저",
    # 성형외과 시술
    "광대축소", "윤곽", "지방흡입", "보톡스",
]

def clean_campaigns():
    # campaigns.json 읽기
    with open('config/campaigns.json', 'r', encoding='utf-8') as f:
        data = json.load(f)

    original_count = 0
    removed_count = 0

    # 각 카테고리의 시드 클리닝
    for target in data['targets']:
        category = target['category']
        original_seeds = target['seeds']
        original_count += len(original_seeds)

        cleaned_seeds = []
        for seed in original_seeds:
            # 제거할 지역명 체크
            has_bad_region = any(region in seed for region in REMOVE_REGIONS)

            # 경쟁사 키워드 체크
            has_competitor = any(comp in seed for comp in REMOVE_COMPETITORS)

            if has_bad_region:
                print(f"  ❌ [{category}] {seed} (타지역)")
                removed_count += 1
            elif has_competitor:
                print(f"  ❌ [{category}] {seed} (경쟁사)")
                removed_count += 1
            else:
                cleaned_seeds.append(seed)

        target['seeds'] = cleaned_seeds
        print(f"✅ [{category}] {len(original_seeds)} → {len(cleaned_seeds)} ({len(original_seeds) - len(cleaned_seeds)} 제거)")

    # 백업 생성
    with open('config/campaigns.json.backup', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)
    print(f"\n💾 백업 저장: config/campaigns.json.backup")

    # 클리닝된 파일 저장
    with open('config/campaigns.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"\n📊 클리닝 완료:")
    print(f"  - 원래 시드: {original_count}개")
    print(f"  - 제거된 시드: {removed_count}개")
    print(f"  - 남은 시드: {original_count - removed_count}개")
    print(f"\n✅ config/campaigns.json 업데이트 완료!")

if __name__ == "__main__":
    clean_campaigns()
