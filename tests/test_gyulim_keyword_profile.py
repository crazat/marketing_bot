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


def test_legion_collector_focus_matches_gyulim_treatments():
    collector = LegionCollector(delay=0.0, use_google=False)

    expected = {
        "청주 여드름흉터 한의원 비용": "피부/여드름",
        "청주 피부관리 한의원 상담": "피부/여드름",
        "청주 안면비대칭 교정 후기": "안면비대칭",
        "청주 다이어트 한약 비용": "다이어트",
        "청주 허리통증 한의원 비용": "통증/디스크",
        "청주 목디스크 추나요법": "통증/디스크",
        "청주 교통사고 입원 자보": "교통사고",
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

    assert not collector._is_valid_keyword("서울 허리통증 한의원")


def test_quality_filter_uses_profile_for_pain_and_skin_relevance():
    quality_filter = KeywordQualityFilter()

    pain = quality_filter.validate("청주 허리통증 한의원 비용")
    scar = quality_filter.validate("청주 패인흉터 새살침 상담")

    assert pain.is_valid
    assert pain.relevance_score >= 0.8
    assert scar.is_valid
    assert scar.relevance_score >= 0.8


def test_legion_longtail_templates_include_pain_category():
    assert "통증/디스크" in PathfinderLegion.CATEGORY_CANONICAL_SERVICES
    assert "통증/디스크" in PathfinderLegion.HIGH_VALUE_LONGTAIL_SUFFIXES
    assert "통증/디스크" in PathfinderLegion.CATEGORY_SEARCH_JOURNEY_SUFFIXES

