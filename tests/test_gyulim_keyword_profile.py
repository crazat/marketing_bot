from core_services.gyulim_keyword_profile import GYULIM_KEYWORD_PROFILE
from core_services.keyword_filter import KeywordQualityFilter
from pathfinder_v3_legion import LegionCollector, PathfinderLegion


def test_gyulim_profile_seed_coverage_has_all_focus_categories():
    seeds = GYULIM_KEYWORD_PROFILE.build_seed_keywords(
        max_terms_per_category=8,
        max_suffixes_per_category=3,
        max_neighborhoods_per_category=4,
        include_contexts=True,
    )
    audit = GYULIM_KEYWORD_PROFILE.coverage_audit(seeds, min_per_category=6)

    assert audit["missing"] == []
    assert audit["undercovered"] == {}
    assert any("청주 여드름흉터" in seed for seed in seeds)
    assert any("청주 안면비대칭" in seed for seed in seeds)
    assert any("청주 허리통증" in seed for seed in seeds)
    assert any("청주 다이어트 한약" in seed for seed in seeds)


def test_gyulim_profile_exploration_seeds_cover_patient_journey_and_secondary_axes():
    seeds = GYULIM_KEYWORD_PROFILE.build_exploration_seed_keywords(
        max_terms_per_category=8,
        max_suffixes_per_category=10,
        max_contexts_per_category=4,
        max_neighborhoods_per_category=4,
    )

    assert any("복대동 허리통증 한의원 야간" in seed for seed in seeds)
    assert any("청주 여드름흉터 부작용" in seed for seed in seeds)
    assert any("청주 수두흉터 치료기간" in seed for seed in seeds)
    assert any("청주 수술흉터" in seed for seed in seeds)
    assert any("청주 비염 한의원 비용" in seed for seed in seeds)
    assert any("청주 불면증 한의원 상담" in seed for seed in seeds)
    assert any("청주 보약 한의원 가격" in seed for seed in seeds)


def test_gyulim_profile_keeps_scar_axis_separate_from_skin_axis():
    # 2026-06-12 taxonomy: 흉터/여드름흉터는 피부/여드름에서 분리된 독립 축이다.
    assert GYULIM_KEYWORD_PROFILE.normalize_category("흉터/여드름흉터") == "흉터/여드름흉터"
    assert GYULIM_KEYWORD_PROFILE.normalize_category("수술흉터") == "흉터/여드름흉터"
    assert GYULIM_KEYWORD_PROFILE.detect_category("청주 수술흉터 새살침 상담") == "흉터/여드름흉터"
    assert GYULIM_KEYWORD_PROFILE.is_focus_candidate("청주 수술흉터 새살침 상담", "흉터/여드름흉터")
    assert GYULIM_KEYWORD_PROFILE.is_focus_candidate("청주 상처흉터 한의원 치료기간", "흉터/여드름흉터")
    # scar 키워드는 더 이상 피부 축 후보가 아니고, 피부과 추천 의도는 어느 축에서도 제외.
    assert not GYULIM_KEYWORD_PROFILE.is_focus_candidate("청주 상처흉터 한의원 치료기간", "피부/여드름")
    assert not GYULIM_KEYWORD_PROFILE.is_focus_candidate("청주 수술흉터 피부과 추천", "흉터/여드름흉터")
    assert not GYULIM_KEYWORD_PROFILE.is_focus_candidate("청주 수술흉터 피부과 추천", "피부/여드름")


def test_legion_collector_focus_matches_gyulim_treatments():
    collector = LegionCollector(delay=0.0, use_google=False)

    expected = {
        "청주 여드름흉터 한의원 비용": "흉터/여드름흉터",
        "청주 수두흉터 새살침 상담": "흉터/여드름흉터",
        "청주 피부관리 한의원 상담": "피부/여드름",
        "청주 안면비대칭 교정 후기": "안면비대칭",
        "청주 다이어트 한약 비용": "다이어트",
        "청주 허리통증 한의원 비용": "통증/디스크",
        "청주 목디스크 추나요법": "통증/디스크",
        "청주 교통사고 입원 자보": "교통사고",
        "청주 비염 한의원 비용": "호흡기/알레르기",
        "청주 불면증 한의원 상담": "수면/피로",
        "청주 탈모 한의원 비용": "탈모/두피",
        "청주 보약 한의원 가격": "면역/보약",
    }

    for keyword, category in expected.items():
        detected = collector._detect_category(keyword)
        assert detected == category
        assert collector._is_valid_keyword(keyword)
        assert collector.is_business_core_keyword(keyword, detected)
        assert collector.is_focus_candidate(keyword, detected)


def test_legion_collector_keeps_low_value_leakage_out():
    collector = LegionCollector(delay=0.0, use_google=False)

    bare_technique = "청주 추나"
    bare_category = collector._detect_category(bare_technique)
    assert bare_category == "통증/디스크"
    assert not collector.is_business_core_keyword(bare_technique, bare_category)
    assert not collector.is_focus_candidate(bare_technique, bare_category)

    leakage = "분평동 다이어트 댄스 추천"
    leakage_category = collector._detect_category(leakage)
    assert collector.low_business_value_reason(leakage, leakage_category)
    assert not collector.is_focus_candidate(leakage, leakage_category)

    product_leakage = "청주 탈모 샴푸 추천"
    product_category = collector._detect_category(product_leakage)
    assert collector.low_business_value_reason(product_leakage, product_category)
    assert not collector.is_focus_candidate(product_leakage, product_category)

    assert not collector._is_valid_keyword("서울 허리통증 한의원")


def test_quality_filter_uses_profile_for_pain_and_skin_relevance():
    quality_filter = KeywordQualityFilter()

    pain = quality_filter.validate("청주 허리통증 한의원 비용")
    scar = quality_filter.validate("청주 패인흉터 새살침 상담")
    surgery_scar = quality_filter.validate("청주 수술흉터 새살침 상담")

    assert pain.is_valid
    assert pain.relevance_score >= 0.8
    assert scar.is_valid
    assert scar.relevance_score >= 0.8
    assert surgery_scar.is_valid
    assert surgery_scar.relevance_score >= 0.8


def test_legion_longtail_templates_include_pain_category():
    assert "통증/디스크" in PathfinderLegion.CATEGORY_CANONICAL_SERVICES
    assert "통증/디스크" in PathfinderLegion.HIGH_VALUE_LONGTAIL_SUFFIXES
    assert "통증/디스크" in PathfinderLegion.CATEGORY_SEARCH_JOURNEY_SUFFIXES
    assert "호흡기/알레르기" in PathfinderLegion.CATEGORY_CANONICAL_SERVICES
    assert "수면/피로" in PathfinderLegion.CATEGORY_SEARCH_JOURNEY_SUFFIXES
