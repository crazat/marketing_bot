import json
import re
import sqlite3
from collections import Counter

from core_services.viral_seed_builder import (
    ViralSeedBuilder,
    keyword_structure_features,
    strip_transactional_suffix,
    is_qualified_viral_outcome,
    load_proven_dead_structures,
)
from db.database import DatabaseManager
from pathfinder_v3_legion import KeywordResult, PathfinderLegion, LegionCollector
from scripts.ai_ad_classify_apply import _execute_scoped_update
import viral_hunter
from core_services.viral_url_canonicalizer import canonicalize_viral_url
from viral_hunter import AICommentGenerator, ViralTarget


def _keyword(keyword: str, grade: str = "A", priority: float = 100.0) -> KeywordResult:
    return KeywordResult(
        keyword=keyword,
        search_volume=100,
        difficulty=30,
        opportunity=80,
        grade=grade,
        category="피부/여드름",
        priority_score=priority,
        source="test",
        document_count=1000,
        kei=10.0,
        kei_grade=grade,
        business_core=True,
    )


def test_pathfinder_save_counts_insert_update_and_last_seen(tmp_path):
    db_path = tmp_path / "pathfinder.db"
    legion = PathfinderLegion.__new__(PathfinderLegion)

    first = legion.save_to_db([_keyword("청주 여드름 한의원")], db_path=str(db_path), scan_run_id=1)
    second = legion.save_to_db([_keyword("청주 여드름 한의원", priority=120)], db_path=str(db_path), scan_run_id=2)

    assert first["inserted"] == 1
    assert first["updated"] == 0
    assert second["inserted"] == 0
    assert second["updated"] == 1

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT scan_run_id, last_scan_run_id, priority_v3, business_core
            FROM keyword_insights
            WHERE keyword = ?
            """,
            ("청주 여드름 한의원",),
        ).fetchone()

    assert row == (1, 2, 120.0, 1)


def test_pathfinder_save_persists_access_convenience_fields(tmp_path):
    db_path = tmp_path / "pathfinder_access.db"
    legion = PathfinderLegion.__new__(PathfinderLegion)
    result = _keyword("청주 교통사고 한의원 주차 가능 길찾기")
    result.access_convenience_score = 82.0
    result.access_convenience_type = "parking_access"
    result.access_convenience_flags = ["parking_intent", "access_high_intent"]

    save_result = legion.save_to_db([result], db_path=str(db_path), scan_run_id=3)

    assert save_result["inserted"] == 1
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT access_convenience_score, access_convenience_type, access_convenience_flags_json
            FROM keyword_insights
            WHERE keyword = ?
            """,
            (result.keyword,),
        ).fetchone()

    assert row[0] == 82.0
    assert row[1] == "parking_access"
    assert "access_high_intent" in row[2]


def test_legion_business_core_filter_matches_actual_acquisition_categories():
    collector = LegionCollector(delay=0.0, use_google=False)

    for keyword in [
        "청주 다이어트 한의원",
        "청주 교통사고 입원",
        "청주 안면비대칭",
        "청주 여드름",
        "청주 여드름흉터",
        "청주 새살침",
        "청주 체형교정",
    ]:
        category = collector._detect_category(keyword)
        assert collector.is_business_core_keyword(keyword, category)
        assert collector.is_focus_candidate(keyword, category)

    for keyword in ["청주 피부과", "청주 기미 한의원", "청주 추나"]:
        category = collector._detect_category(keyword)
        assert not collector.is_business_core_keyword(keyword, category)
        assert not collector.is_focus_candidate(keyword, category)


def test_legion_filters_low_business_value_activity_keywords():
    collector = LegionCollector(delay=0.0, use_google=False)

    leakage = "분평동 다이어트 댄스 추천"
    category = collector._detect_category(leakage)
    assert collector.low_business_value_reason(leakage, category)
    assert not collector.is_focus_candidate(leakage, category)

    service_keyword = "청주 다이어트 한의원 비용"
    service_category = collector._detect_category(service_keyword)
    assert collector.low_business_value_reason(service_keyword, service_category) is None
    assert collector.is_focus_candidate(service_keyword, service_category)


def test_legion_high_value_longtail_is_promoted_without_large_volume_bias():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_keyword_value_profile(
        "용암동 새살침 비용",
        category="피부/여드름",
        search_intent="transactional",
        search_volume=20,
        difficulty=18,
        opportunity=88,
        document_count=1200,
        source_signal_count=1,
        has_real_volume=True,
        business_core=True,
    )
    assert profile["high_value_longtail"] is True
    assert profile["longtail_score"] >= 68
    assert profile["business_value_score"] >= 65

    promoted, flags = legion._promote_grade_for_high_value_longtail(
        "B",
        profile,
        has_real_volume=True,
        search_volume=20,
        difficulty=18,
        opportunity=88,
        verification_score=70,
        quality_flags=[],
    )
    assert promoted == "A"
    assert flags == []

    longtail_priority = legion._calculate_priority(
        18,
        88,
        "용암동 새살침 비용",
        search_volume=20,
        kei=0.4,
        category="피부/여드름",
        search_intent="transactional",
        has_real_volume=True,
        business_core=True,
        longtail_score=profile["longtail_score"],
        business_value_score=profile["business_value_score"],
    )
    generic_priority = legion._calculate_priority(
        18,
        88,
        "청주 새살침",
        search_volume=20,
        kei=0.4,
        category="피부/여드름",
        search_intent="commercial",
        has_real_volume=True,
        business_core=True,
        longtail_score=0,
        business_value_score=60,
    )
    assert longtail_priority > generic_priority


def test_legion_longtail_variant_builder_balances_categories_and_contexts():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    variants = legion._build_high_value_longtail_variants(
        ["청주 다이어트 한의원", "청주 교통사고 한의원", "청주 여드름 한의원"],
        max_keywords=1200,
    )

    assert len(variants) >= 900
    assert any("복대동" in kw and "다이어트 한약" in kw and "비용" in kw for kw in variants)
    assert any("교통사고 입원" in kw and "자보" in kw for kw in variants)
    assert any("여드름흉터 한의원" in kw and "추천" in kw for kw in variants)
    assert any("패인흉터 새살침" in kw and "치료기간" in kw for kw in variants)
    assert any("수두흉터 한의원" in kw and "치료기간" in kw for kw in variants)
    assert any("다이어트 한약" in kw and "비용 얼마" in kw for kw in variants)
    assert any("직장인" in kw and "다이어트 한약" in kw for kw in variants)
    assert any("비염 한의원" in kw and "치료기간" in kw for kw in variants)
    assert any("불면증 한의원" in kw and "상담" in kw for kw in variants)


def test_legion_longtail_variant_builder_covers_customer_journey_actions():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    variants = legion._build_high_value_longtail_variants(
        ["청주 다이어트 한약", "청주 교통사고 입원"],
        max_keywords=500,
    )

    assert "청주 다이어트 한약 주차" in variants
    assert "청주 교통사고 입원 자동차보험 서류" in variants
    assert "청주 교통사고 입원 주말" in variants
    assert not any("다이어트 댄스" in kw for kw in variants)


def test_legion_ad_keyword_metrics_create_business_value_signal():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    legion._merge_ad_keyword_metrics({
        "청주다이어트한약비용": {
            "monthly_pc_clicks": 18.0,
            "monthly_mobile_clicks": 64.0,
            "monthly_pc_ctr": 0.8,
            "monthly_mobile_ctr": 2.1,
            "avg_ad_depth": 7.0,
            "competition": "높음",
        }
    })

    metrics = legion._get_ad_keyword_metrics("청주 다이어트 한약 비용")
    signal = legion._calculate_ad_value_signal(metrics)

    assert metrics["competition"] == "높음"
    assert signal >= 65


def test_legion_inbound_query_metrics_build_first_party_seeds():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    legion.inbound_query_metrics = {
        PathfinderLegion._normalize_keyword_for_history("복대동 다이어트 한약 비용"): {
            "query": "복대동 다이어트 한약 비용",
            "sources": ["gsc"],
            "impressions": 80,
            "clicks": 3,
            "ctr": 0.0375,
            "position": 9.0,
        },
        PathfinderLegion._normalize_keyword_for_history("서울 한의원"): {
            "query": "서울 한의원",
            "sources": ["gsc"],
            "impressions": 1000,
            "clicks": 10,
            "ctr": 0.01,
            "position": 4.0,
        },
    }

    seeds = legion._build_inbound_query_seeds(limit=10)
    signal = legion._calculate_inbound_value_signal(legion._get_inbound_query_metrics("복대동 다이어트 한약 비용"))

    assert "복대동 다이어트 한약 비용" in seeds
    assert "서울 한의원" not in seeds
    assert signal >= 30


def test_legion_content_cluster_key_separates_page_targets():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    price_key = legion._content_cluster_key("복대동 다이어트 한약 비용", "다이어트", "transactional")
    review_key = legion._content_cluster_key("복대동 다이어트 한약 후기", "다이어트", "validation")

    assert price_key != review_key
    assert "price" in price_key
    assert "review" in review_key


def test_legion_owned_rank_gap_seeds_prioritize_striking_distance():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    gap_norm = PathfinderLegion._normalize_keyword_for_history("복대동 다이어트 한약 비용")
    top_norm = PathfinderLegion._normalize_keyword_for_history("청주 여드름 한의원")
    legion.owned_rank_metrics = {
        gap_norm: {
            "keyword": "복대동 다이어트 한약 비용",
            "rank": 14,
            "status": "found",
            "device": "mobile",
            "rank_gap_signal": PathfinderLegion._calculate_rank_gap_signal({
                "rank": 14,
                "status": "found",
                "device": "mobile",
            }),
            "rank_status": "striking_page2",
        },
        top_norm: {
            "keyword": "청주 여드름 한의원",
            "rank": 2,
            "status": "found",
            "device": "mobile",
            "rank_gap_signal": PathfinderLegion._calculate_rank_gap_signal({
                "rank": 2,
                "status": "found",
                "device": "mobile",
            }),
            "rank_status": "owned_top3",
        },
    }

    seeds = legion._build_owned_rank_gap_seeds(limit=10)

    assert legion.owned_rank_metrics[gap_norm]["rank_gap_signal"] >= 55
    assert PathfinderLegion._rank_status_label({"rank": 2, "status": "found"}) == "owned_top3"
    assert "복대동 다이어트 한약 비용" in seeds
    assert "청주 여드름 한의원" not in seeds


def test_legion_community_signal_seeds_capture_real_question_demand():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    focus_norm = PathfinderLegion._normalize_keyword_for_history("복대동 여드름흉터 한의원 후기")
    off_scope_norm = PathfinderLegion._normalize_keyword_for_history("서울 피부과 후기")
    legion.community_keyword_metrics = {
        focus_norm: {
            "keyword": "복대동 여드름흉터 한의원 후기",
            "mentions": 5,
            "platforms": ["cafe", "kin"],
            "commentable": 3,
            "max_priority": 120.0,
            "max_conversion_fit": 78.0,
            "max_infiltration": 66.0,
        },
        off_scope_norm: {
            "keyword": "서울 피부과 후기",
            "mentions": 12,
            "platforms": ["cafe", "kin"],
            "commentable": 8,
            "max_priority": 150.0,
            "max_conversion_fit": 90.0,
            "max_infiltration": 80.0,
        },
    }
    for data in legion.community_keyword_metrics.values():
        data["community_signal"] = PathfinderLegion._calculate_community_value_signal(data)

    seeds = legion._build_community_signal_seeds(limit=10)

    assert legion.community_keyword_metrics[focus_norm]["community_signal"] >= 40
    assert "복대동 여드름흉터 한의원 후기" in seeds
    assert "서울 피부과 후기" not in seeds


def test_legion_conversion_signal_seeds_prioritize_actual_calls():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    focus_norm = PathfinderLegion._normalize_keyword_for_history("복대동 교통사고 한의원 입원")
    off_scope_norm = PathfinderLegion._normalize_keyword_for_history("서울 교통사고 병원")
    legion.conversion_keyword_metrics = {
        focus_norm: {
            "keyword": "복대동 교통사고 한의원 입원",
            "total_calls": 4,
            "naver_search_calls": 3,
            "duration_seconds": 480,
            "rows": 2,
        },
        off_scope_norm: {
            "keyword": "서울 교통사고 병원",
            "total_calls": 10,
            "naver_search_calls": 7,
            "duration_seconds": 1200,
            "rows": 4,
        },
    }
    for data in legion.conversion_keyword_metrics.values():
        data["conversion_signal"] = PathfinderLegion._calculate_conversion_value_signal(data)

    seeds = legion._build_conversion_signal_seeds(limit=10)

    assert legion.conversion_keyword_metrics[focus_norm]["conversion_signal"] >= 35
    assert "복대동 교통사고 한의원 입원" in seeds
    assert "서울 교통사고 병원" not in seeds


def test_legion_profile_action_signal_scores_directions_and_bookings():
    metrics = {
        "calls": 2,
        "directions": 5,
        "website_clicks": 3,
        "bookings": 2,
        "messages": 1,
    }

    signal = PathfinderLegion._calculate_profile_action_value_signal(metrics)

    assert signal >= 60


def test_legion_profile_action_seeds_prioritize_local_action_keywords():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    focus_norm = PathfinderLegion._normalize_keyword_for_history("복대동 교통사고 한의원 입원 예약 길찾기")
    off_scope_norm = PathfinderLegion._normalize_keyword_for_history("서울 교통사고 병원 예약")
    legion.profile_action_metrics = {
        focus_norm: {
            "keyword": "복대동 교통사고 한의원 입원 예약 길찾기",
            "calls": 2,
            "directions": 5,
            "website_clicks": 2,
            "bookings": 2,
            "messages": 1,
            "sources": ["gbp"],
        },
        off_scope_norm: {
            "keyword": "서울 교통사고 병원 예약",
            "calls": 8,
            "directions": 10,
            "website_clicks": 3,
            "bookings": 5,
            "messages": 2,
            "sources": ["gbp"],
        },
    }
    for data in legion.profile_action_metrics.values():
        data["profile_action_signal"] = PathfinderLegion._calculate_profile_action_value_signal(data)
        data["total_actions"] = (
            data["calls"] + data["directions"] + data["website_clicks"] + data["bookings"] + data["messages"]
        )

    seeds = legion._build_profile_action_seeds(limit=10)

    assert legion.profile_action_metrics[focus_norm]["profile_action_signal"] >= 60
    assert "복대동 교통사고 한의원 입원 예약 길찾기" in seeds
    assert "서울 교통사고 병원 예약" not in seeds


def test_legion_profile_action_signal_keeps_local_action_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_keyword_value_profile(
        "복대동 교통사고 한의원 입원 예약 길찾기",
        category="교통사고",
        search_intent="transactional",
        search_volume=25,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=50.0,
        local_surface_score=45.0,
        profile_action_signal=72.0,
    )

    assert profile["profile_action_signal"] >= 60
    assert profile["high_value_longtail"] is True


def test_legion_availability_profile_scores_same_day_booking_intent():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_availability_intent_profile(
        "복대동 교통사고 한의원 오늘 입원 예약 가능",
        "교통사고",
        "transactional",
        local_surface_score=68.0,
        profile_action_signal=45.0,
        service_fit_score=92.0,
    )

    assert profile["availability_intent_type"] == "same_day_booking"
    assert profile["availability_intent_score"] >= 70
    assert "availability_high_intent" in profile["flags"]


def test_legion_availability_intent_keeps_time_sensitive_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    availability = legion._calculate_availability_intent_profile(
        "청주 교통사고 한의원 주말 입원 가능",
        "교통사고",
        "transactional",
        local_surface_score=50.0,
        service_fit_score=90.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 교통사고 한의원 주말 입원 가능",
        category="교통사고",
        search_intent="transactional",
        search_volume=25,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=50.0,
        local_surface_score=50.0,
        availability_intent_score=availability["availability_intent_score"],
        availability_intent_type=availability["availability_intent_type"],
    )

    assert availability["availability_intent_score"] >= 70
    assert profile["high_value_longtail"] is True


def test_legion_availability_profile_distinguishes_hours_check():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_availability_intent_profile(
        "청주 규림한의원 진료시간 휴무",
        "한의원일반",
        "navigational",
        local_surface_score=62.0,
        service_fit_score=75.0,
    )

    assert profile["availability_intent_type"] == "hours_check"
    assert profile["availability_intent_score"] >= 55
    assert "hours_check" in profile["flags"]


def test_legion_payment_profile_scores_auto_insurance_longtail():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_payment_coverage_profile(
        "청주 교통사고 한의원 자보 입원 치료비",
        "교통사고",
        "transactional",
        service_fit_score=94.0,
        local_surface_score=68.0,
    )

    assert profile["payment_coverage_type"] == "auto_insurance"
    assert profile["payment_coverage_score"] >= 70
    assert "payment_high_intent" in profile["flags"]


def test_legion_payment_coverage_keeps_insurance_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    payment = legion._calculate_payment_coverage_profile(
        "청주 추나요법 한의원 보험 적용 비용",
        "체형교정",
        "transactional",
        service_fit_score=90.0,
        local_surface_score=50.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 추나요법 한의원 보험 적용 비용",
        category="체형교정",
        search_intent="transactional",
        search_volume=25,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=50.0,
        local_surface_score=50.0,
        payment_coverage_score=payment["payment_coverage_score"],
        payment_coverage_type=payment["payment_coverage_type"],
    )

    assert payment["payment_coverage_score"] >= 70
    assert profile["high_value_longtail"] is True


def test_legion_payment_profile_detects_claim_documents():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_payment_coverage_profile(
        "청주 한의원 실비 청구 영수증 서류",
        "한의원일반",
        "transactional",
        service_fit_score=82.0,
        local_surface_score=55.0,
    )

    assert profile["payment_coverage_type"] == "claim_documents"
    assert profile["payment_coverage_score"] >= 70
    assert "claim_document_intent" in profile["flags"]


def test_legion_access_convenience_profile_scores_parking_access():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_access_convenience_profile(
        "청주 교통사고 한의원 주차 가능 길찾기 도보",
        "교통사고",
        "transactional",
        service_fit_score=92.0,
        local_surface_score=68.0,
        availability_intent_score=70.0,
    )

    assert profile["access_convenience_type"] == "parking_access"
    assert profile["access_convenience_score"] >= 70
    assert "access_high_intent" in profile["flags"]


def test_legion_access_convenience_keeps_parking_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    access = legion._calculate_access_convenience_profile(
        "청주 교통사고 한의원 주차 가능한 곳 길찾기 도보",
        "교통사고",
        "transactional",
        service_fit_score=90.0,
        local_surface_score=50.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 교통사고 한의원 주차 가능한 곳 길찾기 도보",
        category="교통사고",
        search_intent="transactional",
        search_volume=20,
        difficulty=22,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=50.0,
        local_surface_score=50.0,
        access_convenience_score=access["access_convenience_score"],
        access_convenience_type=access["access_convenience_type"],
    )

    assert access["access_convenience_score"] >= 70
    assert profile["high_value_longtail"] is True


def test_legion_access_convenience_profile_detects_accessibility_need():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_access_convenience_profile(
        "청주 한의원 휠체어 엘리베이터 위치 길찾기",
        "한의원일반",
        "navigational",
        service_fit_score=82.0,
        local_surface_score=65.0,
    )

    assert profile["access_convenience_type"] == "accessibility_need"
    assert profile["access_convenience_score"] >= 70
    assert "accessibility_need" in profile["flags"]


def test_legion_medical_ad_risk_distinguishes_claims_from_safe_info():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    risky = legion._calculate_medical_ad_risk_profile("청주 다이어트 한약 100% 완치 보장", "transactional")
    safe_info = legion._calculate_medical_ad_risk_profile("청주 다이어트 한약 부작용 있나요", "red_flag")

    assert risky["score"] >= 70
    assert "high_risk_claim" in risky["flags"]
    assert risky["content_feasibility_score"] < safe_info["content_feasibility_score"]
    assert safe_info["score"] < 40
    assert "safe_info_possible" in safe_info["flags"]


def test_legion_service_fit_blocks_negative_intent_longtails():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    good = legion._calculate_service_fit_profile("청주 다이어트 한약 비용", "다이어트", "transactional")
    employment = legion._calculate_service_fit_profile("청주 한의원 채용", "한의원일반", "transactional")
    off_region = legion._calculate_service_fit_profile("서울 다이어트 한의원 비용", "다이어트", "transactional")
    self_care = legion._calculate_service_fit_profile("청주 여드름흉터 셀프 홈케어", "피부/여드름", "informational")

    assert good["score"] >= 85
    assert employment["score"] < 35
    assert "employment_intent" in employment["flags"]
    assert off_region["score"] < 65
    assert "non_target_region" in off_region["flags"]
    assert self_care["hard_negative"] is True


def test_legion_negative_intent_cannot_be_promoted_as_high_value_longtail():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_keyword_value_profile(
        "청주 다이어트 한의원 채용 비용",
        category="다이어트",
        search_intent="transactional",
        search_volume=50,
        difficulty=18,
        opportunity=88,
        document_count=1200,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
    )
    promoted, flags = legion._promote_grade_for_high_value_longtail(
        "B",
        profile,
        has_real_volume=True,
        search_volume=50,
        difficulty=18,
        opportunity=88,
        verification_score=80,
        quality_flags=[],
    )

    assert profile["service_fit_score"] < 65
    assert profile["hard_negative_intent"] is True
    assert profile["high_value_longtail"] is False
    assert promoted == "B"
    assert "negative_intent:employment_intent" in flags


def test_legion_content_actionability_routes_service_and_safe_faq_pages():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    service = legion._calculate_content_actionability_profile(
        "복대동 다이어트 한약 비용",
        "다이어트",
        "transactional",
        medical_ad_risk_score=0.0,
        service_fit_score=95.0,
    )
    safe_faq = legion._calculate_content_actionability_profile(
        "청주 다이어트 한약 부작용 있나요",
        "다이어트",
        "red_flag",
        medical_ad_risk_score=12.0,
        service_fit_score=90.0,
    )

    assert service["score"] >= 80
    assert service["recommended_content_type"] == "service_landing"
    assert safe_faq["score"] >= 80
    assert safe_faq["recommended_content_type"] == "faq_safety"
    assert "safe_faq_candidate" in safe_faq["flags"]


def test_legion_content_actionability_limits_proof_sensitive_claims():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    action = legion._calculate_content_actionability_profile(
        "청주 다이어트 한약 1위 추천",
        "다이어트",
        "commercial",
        medical_ad_risk_score=42.0,
        service_fit_score=95.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 다이어트 한약 1위 추천",
        category="다이어트",
        search_intent="commercial",
        search_volume=80,
        difficulty=20,
        opportunity=88,
        document_count=1200,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        medical_ad_risk_score=42.0,
        content_actionability_score=action["score"],
    )

    assert action["score"] < 60
    assert "proof_sensitive_claim" in action["flags"]
    assert profile["high_value_longtail"] is False


def test_legion_local_surface_routes_place_action_keywords():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_local_surface_profile(
        "복대동 교통사고 한의원 입원 주차 전화",
        "교통사고",
        "transactional",
        mobile_share=0.82,
        rank_gap_signal=72.0,
        conversion_signal=48.0,
        service_fit_score=94.0,
    )

    assert profile["score"] >= 70
    assert profile["preferred_search_surface"] == "profile_action"
    assert "place_action_intent" in profile["flags"]
    assert "mobile_heavy" in profile["flags"]


def test_legion_local_surface_keeps_map_heavy_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    local_surface = legion._calculate_local_surface_profile(
        "청주 교통사고 한의원 입원 주차",
        "교통사고",
        "transactional",
        mobile_share=0.8,
        rank_gap_signal=70.0,
        conversion_signal=45.0,
        service_fit_score=90.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 교통사고 한의원 입원 주차",
        category="교통사고",
        search_intent="transactional",
        search_volume=20,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=52.0,
        local_surface_score=local_surface["score"],
    )

    assert local_surface["score"] >= 70
    assert profile["local_surface_score"] >= 70
    assert profile["high_value_longtail"] is True


def test_legion_brand_intent_separates_own_brand_from_competitor_terms():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.own_brand_terms = {"규림", "규림한의원"}
    legion.competitor_brand_terms = {"자연과한의원"}

    own = legion._calculate_brand_intent_profile("청주 규림한의원 후기", "validation")
    competitor = legion._calculate_brand_intent_profile("청주 자연과한의원 다이어트 한약 후기", "commercial")

    assert own["brand_intent_type"] == "own_brand_defense"
    assert own["brand_signal_score"] >= 80
    assert competitor["brand_intent_type"] == "competitor_comparison"
    assert competitor["competitor_brand_risk_score"] >= 70
    assert "competitor_brand_high_risk" in competitor["flags"]


def test_legion_competitor_brand_terms_do_not_promote_to_high_value_longtail():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    legion.own_brand_terms = {"규림", "규림한의원"}
    legion.competitor_brand_terms = {"자연과한의원"}

    brand = legion._calculate_brand_intent_profile("청주 자연과한의원 다이어트 한약 후기", "commercial")
    profile = legion._calculate_keyword_value_profile(
        "청주 자연과한의원 다이어트 한약 후기",
        category="다이어트",
        search_intent="commercial",
        search_volume=80,
        difficulty=20,
        opportunity=88,
        document_count=1200,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=82.0,
        local_surface_score=72.0,
        brand_intent_type=brand["brand_intent_type"],
        competitor_brand_risk_score=brand["competitor_brand_risk_score"],
    )
    promoted, flags = legion._promote_grade_for_high_value_longtail(
        "B",
        profile,
        has_real_volume=True,
        search_volume=80,
        difficulty=20,
        opportunity=88,
        verification_score=82,
        quality_flags=[],
    )

    assert profile["high_value_longtail"] is False
    assert promoted == "B"
    assert "brand_intent:competitor_comparison" in flags


def test_legion_review_reputation_profile_routes_own_brand_reviews_to_defense():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    profile = legion._calculate_review_reputation_profile(
        "청주 규림한의원 후기 평점",
        "validation",
        brand_intent_type="own_brand_defense",
        community_signal=55.0,
        local_surface_score=72.0,
    )

    assert profile["review_intent_type"] == "own_review_defense"
    assert profile["review_surface_score"] >= 70
    assert profile["reputation_risk_score"] < 40
    assert "review_defense" in profile["flags"]


def test_legion_reputation_risk_blocks_review_longtail_promotion():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    review = legion._calculate_review_reputation_profile(
        "청주 다이어트 한의원 불친절 후기 환불",
        "validation",
        brand_intent_type="generic",
        local_surface_score=55.0,
        medical_ad_risk_score=42.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "청주 다이어트 한의원 불친절 후기 환불",
        category="다이어트",
        search_intent="validation",
        search_volume=30,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=82.0,
        local_surface_score=55.0,
        review_surface_score=review["review_surface_score"],
        reputation_risk_score=review["reputation_risk_score"],
        review_intent_type=review["review_intent_type"],
    )

    assert review["reputation_risk_score"] >= 70
    assert "reputation_high_risk" in review["flags"]
    assert profile["high_value_longtail"] is False


def test_legion_review_surface_keeps_generic_review_longtail_promotable():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    review = legion._calculate_review_reputation_profile(
        "복대동 여드름흉터 한의원 후기",
        "validation",
        brand_intent_type="generic",
        local_surface_score=45.0,
    )
    profile = legion._calculate_keyword_value_profile(
        "복대동 여드름흉터 한의원 후기",
        category="피부/여드름",
        search_intent="validation",
        search_volume=30,
        difficulty=20,
        opportunity=88,
        document_count=900,
        source_signal_count=2,
        has_real_volume=True,
        business_core=True,
        content_actionability_score=50.0,
        local_surface_score=45.0,
        review_surface_score=review["review_surface_score"],
        reputation_risk_score=review["reputation_risk_score"],
        review_intent_type=review["review_intent_type"],
    )

    assert review["review_surface_score"] >= 70
    assert review["reputation_risk_score"] == 0
    assert profile["high_value_longtail"] is True


def test_legion_missing_volume_high_value_longtail_recovers_to_estimated_b_grade():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)

    keyword = "복대동 직장인 다이어트 한약 비용"
    profile = legion._calculate_keyword_value_profile(
        keyword,
        category="다이어트",
        search_intent="transactional",
        search_volume=30,
        difficulty=20,
        opportunity=88,
        document_count=1200,
        source_signal_count=3,
        has_real_volume=False,
        business_core=True,
    )
    verification = legion._calculate_verification_score(
        keyword,
        search_volume=30,
        document_count=1200,
        source_signal_count=3,
        has_real_volume=False,
        business_core=True,
    )

    assert profile["high_value_longtail"] is True
    assert verification >= 55

    promoted, flags = legion._promote_grade_for_high_value_longtail(
        "C",
        profile,
        has_real_volume=False,
        search_volume=30,
        difficulty=20,
        opportunity=88,
        verification_score=verification,
        quality_flags=["missing_real_volume"],
    )

    assert promoted == "B"
    assert "missing_real_volume" in flags
    assert "estimated_high_value_longtail" in flags


def test_legion_quality_flag_sync_drops_stale_document_count_flags():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    legion.keyword_source_signals = {
        PathfinderLegion._normalize_keyword_for_history("청주 다이어트 한약 비용"): {"round1_seed"}
    }
    legion.keyword_canonical_by_norm = {}
    legion.candidate_stats = {
        "input_by_source": Counter(),
        "valid_by_source": Counter(),
        "accepted_by_source": Counter(),
        "sa_by_source": Counter(),
        "rejected_by_source": {},
    }
    legion.diversity_metrics = {}

    result = KeywordResult(
        keyword="청주 다이어트 한약 비용",
        search_volume=30,
        difficulty=20,
        opportunity=88,
        grade="A",
        category="다이어트",
        priority_score=100,
        source="round1_seed",
        search_intent="transactional",
        document_count=1000,
        business_core=True,
        quality_flags=["missing_document_count", "low_document_count"],
    )

    legion._sync_result_quality_fields(result)

    assert "missing_document_count" not in result.quality_flags
    assert "low_document_count" not in result.quality_flags


def test_legion_run_respects_max_rounds_after_fixed_rounds():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    legion.base_seeds = ["청주 다이어트 한의원"]

    analyzed_sources = []
    legion._analyze_and_add = lambda keywords, source: analyzed_sources.append(source) or 0
    legion._build_high_value_longtail_variants = lambda *args, **kwargs: set()
    legion._collect_ad_related_keywords = lambda *args, **kwargs: []
    legion._select_expansion_keywords = lambda *args, **kwargs: []
    legion._finalize = lambda: []
    legion.collector.get_autocomplete_multi = lambda seed: set()
    legion.collector.get_autocomplete = lambda keyword: []

    legion.run(target_sa=99, max_rounds=2, skip_ad_related=True)

    assert analyzed_sources == ["round1_seed", "round2_expand"]


def test_legion_round2_uses_customer_action_suffixes_not_claim_terms():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collector = LegionCollector(delay=0.0, use_google=False)
    legion.base_seeds = ["청주 다이어트 한의원"]

    analyzed = {}

    def capture_keywords(keywords, source):
        analyzed[source] = set(keywords)
        return 0

    legion._analyze_and_add = capture_keywords
    legion._build_high_value_longtail_variants = lambda *args, **kwargs: set()
    legion._collect_ad_related_keywords = lambda *args, **kwargs: []
    legion._select_expansion_keywords = lambda *args, **kwargs: ["청주 다이어트 한약"]
    legion._finalize = lambda: []
    legion.collector.get_autocomplete_multi = lambda seed: set()
    legion.collector.get_autocomplete = lambda keyword: []

    legion.run(target_sa=99, max_rounds=2, skip_ad_related=True)

    round2_keywords = analyzed["round2_expand"]
    assert "청주 다이어트 한약 예약" in round2_keywords
    assert "청주 다이어트 한약 주차" in round2_keywords
    assert "청주 다이어트 한약 주의사항" in round2_keywords
    assert "청주 다이어트 한약 전후" not in round2_keywords
    assert "청주 다이어트 한약 효과" not in round2_keywords


def test_viral_seed_builder_penalizes_revisited_keyword_history(tmp_path):
    db_path = tmp_path / "seed_builder.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                last_scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                matched_keyword TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER
            )
            """
        )
        conn.execute(
            "INSERT INTO scan_runs(id, scan_type, status, completed_at) VALUES (1, 'legion', 'completed', '2026-05-01')"
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, last_scan_run_id, business_core, status
            ) VALUES (?, 'cat', 'A', 100, 1000, 10, ?, ?, 1, 1, 'active')
            """,
            [
                ("repeat keyword", 200.0, "transactional"),
                ("fresh transactional", 180.0, "transactional"),
                ("fresh informational", 170.0, "informational"),
            ],
        )
        conn.executemany(
            """
            INSERT INTO viral_targets(id, url, matched_keyword, comment_status, generated_comment, scan_count)
            VALUES (?, ?, 'repeat keyword', 'pending', '', 2)
            """,
            [(f"seen-{i}", f"https://example.com/{i}") for i in range(30)],
        )
        conn.commit()

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=1,
        quotas={"cat": 2},
        max_per_intent_per_category=1,
    )

    assert [seed.keyword for seed in seeds] == ["fresh transactional", "fresh informational"]
    assert all(seed.historical_target_count == 0 for seed in seeds)


def test_viral_seed_builder_rewards_keywords_that_produce_qualified_worksites(tmp_path):
    db_path = tmp_path / "seed_builder_quality_feedback.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                matched_keyword TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER,
                priority_score REAL,
                score_breakdown TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (13, 'legion', 'completed', '2026-06-06');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, '다이어트', 'A', 100, 1000, 10, ?, 'transactional',
                      13, 1, 'active', 80, 80, 1)
            """,
            [
                ("청주 다이어트 한약 좋은글", 160),
                ("청주 다이어트 한약 신선", 170),
                ("청주 다이어트 한약 노이즈", 220),
            ],
        )
        high_quality_breakdown = '{"clinic_treatment_fit_score": 92, "worksite_efficiency_score": 88}'
        conn.executemany(
            """
            INSERT INTO viral_targets(
                id, url, matched_keyword, comment_status, generated_comment,
                scan_count, priority_score, score_breakdown
            ) VALUES (?, ?, '청주 다이어트 한약 좋은글', 'pending', '', 1, 132, ?)
            """,
            [(f"good-{idx}", f"https://good.example/{idx}", high_quality_breakdown) for idx in range(6)],
        )
        conn.executemany(
            """
            INSERT INTO viral_targets(
                id, url, matched_keyword, comment_status, generated_comment,
                scan_count, priority_score, score_breakdown
            ) VALUES (?, ?, '청주 다이어트 한약 노이즈', 'skipped', 'final_gate:ad', 2, 0, '{}')
            """,
            [(f"noise-{idx}", f"https://noise.example/{idx}") for idx in range(10)],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=13, quotas={"다이어트": 2})

    assert [seed.keyword for seed in seeds] == [
        "청주 다이어트 한약 좋은글",
        "청주 다이어트 한약 신선",
    ]
    assert seeds[0].historical_target_count == 6
    assert seeds[0].historical_qualified_count == 6
    assert seeds[0].historical_quality_rate == 1.0
    assert seeds[0].historical_avg_clinic_fit == 92.0
    assert seeds[0].historical_avg_worksite_efficiency == 88.0


def test_viral_seed_builder_uses_pathfinder_execution_signals_for_viral_readiness(tmp_path):
    db_path = tmp_path / "seed_builder_execution_signals.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER,
                local_service_fit_score REAL,
                content_actionability_score REAL,
                medical_ad_risk_score REAL,
                community_signal REAL,
                conversion_signal REAL,
                profile_action_signal REAL,
                local_surface_score REAL,
                review_surface_score REAL,
                reputation_risk_score REAL,
                competitor_brand_risk_score REAL,
                availability_intent_score REAL,
                payment_coverage_score REAL,
                access_convenience_score REAL,
                verification_score REAL,
                novelty_score REAL,
                preferred_search_surface TEXT,
                recommended_content_type TEXT,
                brand_intent_type TEXT,
                review_intent_type TEXT,
                quality_flags_json TEXT,
                source_signals_json TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (15, 'legion', 'completed', '2026-06-08');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail,
                local_service_fit_score, content_actionability_score, medical_ad_risk_score,
                community_signal, conversion_signal, profile_action_signal,
                local_surface_score, review_surface_score, reputation_risk_score,
                competitor_brand_risk_score, availability_intent_score, payment_coverage_score,
                access_convenience_score, verification_score, novelty_score,
                preferred_search_surface, recommended_content_type, brand_intent_type,
                review_intent_type, quality_flags_json, source_signals_json
            ) VALUES (?, '다이어트', 'A', 100, 1000, 10, ?, 'transactional',
                      15, 1, 'active', 80, 80, 1,
                      ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "청주 다이어트 한약 1위 추천",
                    230,
                    82,
                    35,
                    85,
                    0,
                    0,
                    0,
                    30,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0,
                    40,
                    20,
                    "web_content",
                    "service_landing",
                    "generic",
                    "none",
                    '["medical_ad_high_risk_content", "content_low_actionability"]',
                    "[]",
                ),
                (
                    "청주 다이어트 한약 비용 상담 후기",
                    185,
                    92,
                    88,
                    8,
                    72,
                    58,
                    66,
                    78,
                    74,
                    0,
                    0,
                    72,
                    70,
                    70,
                    84,
                    82,
                    "hybrid_local_content",
                    "service_landing",
                    "generic",
                    "recommendation_discovery",
                    "[]",
                    '["community_demand", "profile_action_conversion"]',
                ),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=15, quotas={"다이어트": 1})
    context = ViralSeedBuilder(str(db_path)).keyword_context_for(["청주 다이어트 한약 비용 상담 후기"])

    assert [seed.keyword for seed in seeds] == ["청주 다이어트 한약 비용 상담 후기"]
    assert seeds[0].viral_readiness_score >= 80
    assert seeds[0].content_actionability_score == 88.0
    assert seeds[0].medical_ad_risk_score == 8.0
    assert seeds[0].availability_intent_score == 72.0
    assert seeds[0].payment_coverage_score == 70.0
    assert seeds[0].access_convenience_score == 70.0
    assert context["청주 다이어트 한약 비용 상담 후기"]["viral_readiness_score"] >= 80
    assert context["청주 다이어트 한약 비용 상담 후기"]["preferred_search_surface"] == "hybrid_local_content"
    assert context["청주 다이어트 한약 비용 상담 후기"]["availability_intent_score"] == 72.0
    assert context["청주 다이어트 한약 비용 상담 후기"]["payment_coverage_score"] == 70.0
    assert context["청주 다이어트 한약 비용 상담 후기"]["access_convenience_score"] == 70.0
    assert (
        context["청주 다이어트 한약 비용 상담 후기"]["source_signals_json"]
        == '["community_demand", "profile_action_conversion"]'
    )


def test_viral_seed_builder_prefers_community_fit_over_pure_profile_grade(tmp_path):
    db_path = tmp_path / "seed_builder_community_fit.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER,
                local_service_fit_score REAL,
                content_actionability_score REAL,
                medical_ad_risk_score REAL,
                community_signal REAL,
                conversion_signal REAL,
                profile_action_signal REAL,
                local_surface_score REAL,
                review_surface_score REAL,
                reputation_risk_score REAL,
                competitor_brand_risk_score REAL,
                availability_intent_score REAL,
                payment_coverage_score REAL,
                access_convenience_score REAL,
                verification_score REAL,
                novelty_score REAL,
                preferred_search_surface TEXT,
                recommended_content_type TEXT,
                brand_intent_type TEXT,
                review_intent_type TEXT,
                quality_flags_json TEXT,
                source_signals_json TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (16, 'legion', 'completed', '2026-06-09');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail,
                local_service_fit_score, content_actionability_score, medical_ad_risk_score,
                community_signal, conversion_signal, profile_action_signal,
                local_surface_score, review_surface_score, reputation_risk_score,
                competitor_brand_risk_score, availability_intent_score, payment_coverage_score,
                access_convenience_score, verification_score, novelty_score,
                preferred_search_surface, recommended_content_type, brand_intent_type,
                review_intent_type, quality_flags_json, source_signals_json
            ) VALUES (?, '다이어트', ?, 100, 1000, 10, ?, 'transactional',
                      16, 1, 'active', ?, ?, 1,
                      ?, ?, 0, ?, 0, 0, ?, 0, 0, 0, 0, 0, 0, 70, 70,
                      ?, ?, 'generic', ?, '[]', ?)
            """,
            [
                (
                    "사창동 다이어트 한약 예약",
                    "A",
                    190,
                    95,
                    95,
                    95,
                    100,
                    0,
                    65,
                    "profile_action",
                    "service_landing",
                    "none",
                    "[]",
                ),
                (
                    "봉명동 다이어트",
                    "B",
                    60,
                    70,
                    70,
                    68,
                    62,
                    92,
                    74,
                    "hybrid_local_content",
                    "proof_safe_guide",
                    "none",
                    '["community_demand"]',
                ),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=16, quotas={"다이어트": 1})

    assert [seed.keyword for seed in seeds] == ["봉명동 다이어트"]


def test_viral_seed_builder_balances_execution_lenses_within_treatment_axis(tmp_path):
    db_path = tmp_path / "seed_builder_execution_lens_balance.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER,
                local_service_fit_score REAL,
                content_actionability_score REAL,
                medical_ad_risk_score REAL,
                community_signal REAL,
                conversion_signal REAL,
                profile_action_signal REAL,
                review_surface_score REAL,
                payment_coverage_score REAL,
                verification_score REAL,
                novelty_score REAL,
                preferred_search_surface TEXT,
                recommended_content_type TEXT,
                review_intent_type TEXT,
                source_signals_json TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (18, 'legion', 'completed', '2026-06-11');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail,
                local_service_fit_score, content_actionability_score, medical_ad_risk_score,
                community_signal, conversion_signal, profile_action_signal,
                review_surface_score, payment_coverage_score, verification_score,
                novelty_score, preferred_search_surface, recommended_content_type,
                review_intent_type, source_signals_json
            ) VALUES (?, 'skin', 'A', 100, 1000, 10, ?, 'transactional',
                      18, 1, 'active', 90, 90, 1,
                      88, 86, 0, ?, ?, 0, ?, ?, 76,
                      70, ?, ?, ?, ?)
            """,
            [
                (
                    "cheongju acne scar cost",
                    240,
                    62,
                    10,
                    0,
                    90,
                    "hybrid_local_content",
                    "proof_safe_guide",
                    "none",
                    '["community_demand"]',
                ),
                (
                    "cheongju pitted scar price",
                    235,
                    62,
                    10,
                    0,
                    88,
                    "hybrid_local_content",
                    "proof_safe_guide",
                    "none",
                    '["community_demand"]',
                ),
                (
                    "cheongju acne scar reviews",
                    150,
                    78,
                    10,
                    85,
                    0,
                    "hybrid_local_content",
                    "proof_safe_guide",
                    "recommendation_discovery",
                    '["community_demand"]',
                ),
                (
                    "cheongju acne scar consultation",
                    145,
                    45,
                    78,
                    0,
                    0,
                    "hybrid_local_content",
                    "service_landing",
                    "none",
                    '["community_demand"]',
                ),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=18,
        quotas={"skin": 3},
        max_per_intent_per_category=10,
        max_per_cluster_per_category=10,
    )

    selected_lenses = [seed.execution_lens for seed in seeds]
    assert set(selected_lenses) == {"review", "cost", "consultation"}
    assert selected_lenses.count("cost") == 1
    assert "cheongju pitted scar price" not in [seed.keyword for seed in seeds]


def test_viral_seed_builder_interleaves_treatment_axes_for_partial_runs(tmp_path):
    db_path = tmp_path / "seed_builder_axis_interleave.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (19, 'legion', 'completed', '2026-06-11');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, ?, 'A', 100, 1000, 10, ?, 'transactional',
                      19, 1, 'active', 90, 90, 1)
            """,
            [
                ("skin one", "skin", 300),
                ("skin two", "skin", 290),
                ("skin three", "skin", 280),
                ("diet one", "diet", 270),
                ("diet two", "diet", 260),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=19,
        quotas={"skin": 3, "diet": 2},
        max_per_cluster_per_category=10,
    )

    assert [seed.keyword for seed in seeds] == [
        "skin one",
        "diet one",
        "skin two",
        "diet two",
        "skin three",
    ]


def test_viral_seed_builder_uses_axis_lens_feedback_to_promote_fresh_winning_lane(tmp_path):
    db_path = tmp_path / "seed_builder_axis_lens_feedback.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                matched_keyword TEXT,
                matched_keyword_category TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER,
                priority_score REAL,
                score_breakdown TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (20, 'legion', 'completed', '2026-06-11');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, 'skin', 'A', 100, 1000, 10, ?, 'transactional',
                      20, 1, 'active', 90, 90, 1)
            """,
            [
                ("cheongju acne scar reviews", 230),
                ("cheongju acne scar cost", 190),
            ],
        )
        cost_breakdown = (
            '{"pathfinder_execution_lens":"cost","pathfinder_lens_fit_score":88,'
            '"pathfinder_lens_fit_tier":"strong","clinic_treatment_fit_score":91,'
            '"worksite_efficiency_score":89}'
        )
        review_breakdown = (
            '{"pathfinder_execution_lens":"review","pathfinder_lens_fit_score":22,'
            '"pathfinder_lens_fit_tier":"mismatch","clinic_treatment_fit_score":42,'
            '"worksite_efficiency_score":38}'
        )
        conn.executemany(
            """
            INSERT INTO viral_targets(
                id, url, matched_keyword, matched_keyword_category, comment_status,
                generated_comment, scan_count, priority_score, score_breakdown
            ) VALUES (?, ?, 'older acne scar cost lane', 'skin', 'pending', '', 1, 132, ?)
            """,
            [(f"cost-lane-{idx}", f"https://cost.example/{idx}", cost_breakdown) for idx in range(6)],
        )
        conn.executemany(
            """
            INSERT INTO viral_targets(
                id, url, matched_keyword, matched_keyword_category, comment_status,
                generated_comment, scan_count, priority_score, score_breakdown
            ) VALUES (?, ?, 'older acne scar review lane', 'skin', 'filtered_out_low_opportunity', '', 1, 0, ?)
            """,
            [(f"review-lane-{idx}", f"https://review.example/{idx}", review_breakdown) for idx in range(6)],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=20,
        quotas={"skin": 1},
        max_per_cluster_per_category=10,
    )

    assert [seed.keyword for seed in seeds] == ["cheongju acne scar cost"]
    assert seeds[0].execution_lens == "cost"
    assert seeds[0].historical_target_count == 0
    assert seeds[0].historical_axis_lens_target_count == 6
    assert seeds[0].historical_axis_lens_quality_rate == 1.0
    assert seeds[0].historical_axis_lens_avg_lens_fit == 88.0


def test_viral_seed_builder_prefers_axis_recommendation_queries(tmp_path):
    db_path = tmp_path / "seed_builder_axis_recommendation.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER,
                local_service_fit_score REAL,
                content_actionability_score REAL,
                medical_ad_risk_score REAL,
                community_signal REAL,
                conversion_signal REAL,
                profile_action_signal REAL,
                local_surface_score REAL,
                review_surface_score REAL,
                reputation_risk_score REAL,
                competitor_brand_risk_score REAL,
                availability_intent_score REAL,
                payment_coverage_score REAL,
                access_convenience_score REAL,
                verification_score REAL,
                novelty_score REAL,
                preferred_search_surface TEXT,
                recommended_content_type TEXT,
                brand_intent_type TEXT,
                review_intent_type TEXT,
                quality_flags_json TEXT,
                source_signals_json TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (17, 'legion', 'completed', '2026-06-10');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail,
                local_service_fit_score, content_actionability_score, medical_ad_risk_score,
                community_signal, conversion_signal, profile_action_signal,
                local_surface_score, review_surface_score, reputation_risk_score,
                competitor_brand_risk_score, availability_intent_score, payment_coverage_score,
                access_convenience_score, verification_score, novelty_score,
                preferred_search_surface, recommended_content_type, brand_intent_type,
                review_intent_type, quality_flags_json, source_signals_json
            ) VALUES (?, ?, 'B', 100, 1000, 10, ?, 'commercial',
                      17, 1, 'active', 80, 80, 1,
                      ?, ?, 0, ?, 0, 0, ?, ?, 0, 0, 0, 0, 0, 70, 70,
                      ?, ?, 'generic', ?, '[]', ?)
            """,
            [
                (
                    "봉명동 안면비대칭",
                    "안면비대칭",
                    120,
                    68,
                    61,
                    96,
                    38,
                    0,
                    "web_content",
                    "proof_safe_guide",
                    "none",
                    '["community_demand"]',
                ),
                (
                    "청주 턱관절 한의원 추천",
                    "안면비대칭",
                    60,
                    87,
                    58,
                    0,
                    38,
                    72,
                    "web_content",
                    "proof_safe_guide",
                    "recommendation_discovery",
                    '["round1_longtail_scout"]',
                ),
                (
                    "복대동 골반교정 한의원 예약",
                    "체형교정",
                    120,
                    95,
                    100,
                    96,
                    88,
                    0,
                    "profile_action",
                    "service_landing",
                    "none",
                    '["community_demand"]',
                ),
                (
                    "청주 체형교정 한의원 추천",
                    "체형교정",
                    80,
                    87,
                    58,
                    80,
                    38,
                    72,
                    "web_content",
                    "proof_safe_guide",
                    "recommendation_discovery",
                    '["community_demand"]',
                ),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=17,
        quotas={"안면비대칭": 1, "체형교정": 1},
    )

    assert [seed.keyword for seed in seeds] == [
        "청주 턱관절 한의원 추천",
        "청주 체형교정 한의원 추천",
    ]


def test_viral_seed_builder_prefers_asymmetry_tmj_hanbang_over_face_shape(tmp_path):
    db_path = tmp_path / "seed_builder_asymmetry_tmj.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER,
                local_service_fit_score REAL,
                content_actionability_score REAL,
                medical_ad_risk_score REAL,
                community_signal REAL,
                conversion_signal REAL,
                profile_action_signal REAL,
                local_surface_score REAL,
                review_surface_score REAL,
                reputation_risk_score REAL,
                competitor_brand_risk_score REAL,
                availability_intent_score REAL,
                payment_coverage_score REAL,
                access_convenience_score REAL,
                verification_score REAL,
                novelty_score REAL,
                preferred_search_surface TEXT,
                recommended_content_type TEXT,
                brand_intent_type TEXT,
                review_intent_type TEXT,
                quality_flags_json TEXT,
                source_signals_json TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (18, 'legion', 'completed', '2026-06-10');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail,
                local_service_fit_score, content_actionability_score, medical_ad_risk_score,
                community_signal, conversion_signal, profile_action_signal,
                local_surface_score, review_surface_score, reputation_risk_score,
                competitor_brand_risk_score, availability_intent_score, payment_coverage_score,
                access_convenience_score, verification_score, novelty_score,
                preferred_search_surface, recommended_content_type, brand_intent_type,
                review_intent_type, quality_flags_json, source_signals_json
            ) VALUES (?, '안면비대칭', 'B', 100, 1000, 10, ?, 'commercial',
                      18, 1, 'active', 82, 82, 1,
                      ?, ?, 0, ?, ?, 0, ?, ?, 0, 0, 0, 0, 0, 70, 70,
                      ?, ?, 'generic', ?, '[]', ?)
            """,
            [
                (
                    "청주 얼굴형 안면비대칭 상담",
                    132,
                    72,
                    70,
                    20,
                    36,
                    54,
                    0,
                    "profile_action",
                    "service_landing",
                    "none",
                    '["community_demand"]',
                ),
                (
                    "청주 턱관절 한의원 상담",
                    92,
                    88,
                    86,
                    35,
                    42,
                    72,
                    38,
                    "web_content",
                    "proof_safe_guide",
                    "recommendation_discovery",
                    '["round1_longtail_scout"]',
                ),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=18, quotas={"안면비대칭": 1})

    assert [seed.keyword for seed in seeds] == ["청주 턱관절 한의원 상담"]


def test_viral_seed_builder_penalizes_broad_diet_activity_queries():
    broad = ViralSeedBuilder._axis_execution_query_bonus(
        {
            "category": "다이어트",
            "keyword": "사창동 다이어트",
            "preferred_search_surface": "web_content",
            "community_signal": 60,
        }
    )
    activity = ViralSeedBuilder._axis_execution_query_bonus(
        {
            "category": "다이어트",
            "keyword": "청주 다이어트 운동 추천",
            "preferred_search_surface": "web_content",
            "community_signal": 60,
        }
    )
    injection = ViralSeedBuilder._axis_execution_query_bonus(
        {
            "category": "다이어트",
            "keyword": "청주다이어트주사 예약",
            "preferred_search_surface": "web_content",
            "community_signal": 60,
        }
    )
    obesity_clinic = ViralSeedBuilder._axis_execution_query_bonus(
        {
            "category": "다이어트",
            "keyword": "청주 비만클리닉 후기",
            "preferred_search_surface": "web_content",
            "community_signal": 60,
        }
    )
    medical = ViralSeedBuilder._axis_execution_query_bonus(
        {
            "category": "다이어트",
            "keyword": "청주 다이어트한약 한의원 상담",
            "preferred_search_surface": "hybrid_local_content",
            "community_signal": 60,
        }
    )

    assert broad < 0
    assert activity <= 0
    assert injection < activity
    assert obesity_clinic < 0
    assert medical > 0
    assert medical > activity
    assert medical > injection


def test_viral_seed_builder_suppresses_non_hanbang_diet_medical_seeds(tmp_path):
    db_path = tmp_path / "seed_builder_non_hanbang_diet.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (20, 'legion', 'completed', '2026-06-12');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, '다이어트', 'A', 100, 1000, 10, ?, 'transactional',
                      20, 1, 'active', 90, 90, 1)
            """,
            [
                ("청주다이어트주사 예약", 320),
                ("청주 비만클리닉 후기", 310),
                ("청주 마운자로 처방 병원", 300),
                ("청주 다이어트한약 한의원 상담", 160),
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=20, quotas={"다이어트": 4})

    assert [seed.keyword for seed in seeds] == ["청주 다이어트한약 한의원 상담"]


def test_viral_seed_builder_suppresses_structurally_weak_execution_lenses():
    weak_feedback = {
        "total_count": 160,
        "quality_rate": 0.0,
        "lens_match_rate": 0.0,
        "avg_lens_fit": 20.0,
    }
    weak_body_cost = {
        "row": {
            "category": "체형교정",
            "keyword": "봉명동 체형교정 한의원 치료비",
            "community_signal": 4,
            "review_intent_type": "none",
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_lifting_safety = {
        "row": {
            "category": "리프팅/탄력",
            "keyword": "봉명동 한방리프팅 부작용 있나요",
            "community_signal": 5,
            "review_intent_type": "none",
        },
        "axis_lens_feedback": {**weak_feedback, "quality_rate": 0.025, "avg_lens_fit": 69.0},
    }
    weak_traffic_availability = {
        "row": {
            "category": "교통사고",
            "keyword": "분평동 교통사고 입원 예약",
            "community_signal": 8,
            "review_intent_type": "none",
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_lifting_consultation = {
        "row": {
            "category": "리프팅/탄력",
            "keyword": "봉명동 한방리프팅 상담",
            "community_signal": 12,
            "review_intent_type": "none",
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_asymmetry_community = {
        "row": {
            "category": "안면비대칭",
            "keyword": "봉명동 안면비대칭",
            "community_signal": 42,
            "review_intent_type": "none",
            "source_signals_json": '["community_demand"]',
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_scar_safety = {
        "row": {
            "category": "흉터/여드름흉터",
            "keyword": "봉명동 여드름흉터 한의원 치료기간",
            "community_signal": 8,
            "review_intent_type": "none",
            "recommended_content_type": "faq_safety",
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_skin_safety = {
        "row": {
            "category": "피부/여드름",
            "keyword": "복대동 여드름 한의원 부작용",
            "community_signal": 8,
            "review_intent_type": "none",
            "recommended_content_type": "faq_safety",
        },
        "axis_lens_feedback": weak_feedback,
    }
    weak_body_community_with_enough_signal = {
        "row": {
            "category": "체형교정",
            "keyword": "봉명동 체형교정",
            "community_signal": 45,
            "review_intent_type": "none",
            "source_signals_json": '["community_demand"]',
        },
        "axis_lens_feedback": {
            "total_count": 25,
            "quality_rate": 0.01,
            "lens_match_rate": 0.02,
            "avg_lens_fit": 44.0,
        },
    }
    rescued_body_review = {
        "row": {
            "category": "체형교정",
            "keyword": "청주 체형교정 한의원 추천",
            "community_signal": 72,
            "review_intent_type": "recommendation_discovery",
        },
        "axis_lens_feedback": weak_feedback,
    }

    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_body_cost)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_lifting_safety)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_traffic_availability)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_lifting_consultation)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_asymmetry_community)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_scar_safety)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_skin_safety)
    assert ViralSeedBuilder._should_suppress_weak_execution_lens(weak_body_community_with_enough_signal)
    assert not ViralSeedBuilder._should_suppress_weak_execution_lens(rescued_body_review)
    assert not ViralSeedBuilder._is_viable_execution_lens(weak_body_cost)


def test_viral_seed_builder_feedback_uses_normalized_keyword_variants(tmp_path):
    db_path = tmp_path / "seed_builder_normalized_feedback.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (14, 'legion', 'completed', '2026-06-07');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core, status
            ) VALUES (?, '피부/여드름', 'A', 100, 1000, 10, ?, 'transactional', 14, 1, 'active')
            """,
            [
                ("청주 여드름흉터 한의원 비용", 210),
                ("청주 수술흉터 새살침 상담", 180),
            ],
        )
        conn.executemany(
            """
            INSERT INTO viral_targets(id, matched_keyword, comment_status, generated_comment, scan_count)
            VALUES (?, '청주여드름흉터한의원비용', 'skipped', 'final_gate:ad', 2)
            """,
            [(f"variant-{idx}",) for idx in range(20)],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=14, quotas={"흉터/여드름흉터": 1})

    assert [seed.keyword for seed in seeds] == ["청주 수술흉터 새살침 상담"]


def test_viral_seed_builder_fills_undercovered_axis_with_profile_exploration(tmp_path):
    db_path = tmp_path / "seed_builder_profile_gap_fill.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (16, 'legion', 'completed', '2026-06-09');
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (
                '청주 안면비대칭 한의원 추천', '안면비대칭', 'A', 70, 900,
                12, 180, 'commercial', 16, 1, 'active', 82, 84, 1
            );
            """
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=16,
        quotas={"안면비대칭": 3},
        fill_profile_gaps=True,
    )

    assert len(seeds) == 3
    assert Counter(seed.category for seed in seeds) == Counter({"안면비대칭": 3})
    assert "청주 안면비대칭 한의원 추천" in {seed.keyword for seed in seeds}
    profile_gap_seeds = [seed for seed in seeds if seed.search_volume == 0 and seed.document_count == 0]
    assert len(profile_gap_seeds) == 2
    assert all(seed.grade == "B" for seed in profile_gap_seeds)
    assert all(seed.scan_run_id == 16 for seed in profile_gap_seeds)
    assert all(
        any(term in seed.keyword for term in ("안면비대칭", "얼굴비대칭", "턱비대칭", "턱관절"))
        for seed in profile_gap_seeds
    )
    assert len({re.sub(r"\\s+", "", seed.keyword) for seed in seeds}) == 3


def test_viral_seed_builder_feedback_credits_secondary_matched_keywords(tmp_path):
    db_path = tmp_path / "seed_builder_secondary_matched_keywords.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER,
                priority_score REAL,
                score_breakdown TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (21, 'legion', 'completed', '2026-06-11');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, 'skin', 'A', 100, 1000, 10, ?, 'transactional',
                      21, 1, 'active', 80, 80, 1)
            """,
            [
                ("primary unrewarded seed", 190),
                ("secondary rewarded seed", 170),
            ],
        )
        high_quality_breakdown = '{"clinic_treatment_fit_score": 92, "worksite_efficiency_score": 88}'
        conn.executemany(
            """
            INSERT INTO viral_targets(
                id, url, matched_keyword, matched_keywords, matched_keyword_category,
                comment_status, generated_comment, scan_count, priority_score, score_breakdown
            ) VALUES (?, ?, 'different primary keyword', ?, 'skin', 'pending', '', 1, 132, ?)
            """,
            [
                (
                    f"secondary-{idx}",
                    f"https://secondary.example/{idx}",
                    '["different primary keyword", "secondary rewarded seed"]',
                    high_quality_breakdown,
                )
                for idx in range(6)
            ],
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=21,
        quotas={"skin": 1},
        max_per_cluster_per_category=10,
    )

    assert [seed.keyword for seed in seeds] == ["secondary rewarded seed"]
    assert seeds[0].historical_target_count == 6
    assert seeds[0].historical_qualified_count == 6
    assert seeds[0].historical_quality_rate == 1.0


def test_viral_hunter_search_plan_expands_ready_community_keywords_and_limits_risk():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "community ready": {
            "viral_readiness_score": 88,
            "community_signal": 72,
            "conversion_signal": 55,
            "profile_action_signal": 62,
            "medical_ad_risk_score": 8,
            "content_actionability_score": 86,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "service_landing",
            "review_intent_type": "recommendation_discovery",
        },
        "risky claim": {
            "viral_readiness_score": 45,
            "medical_ad_risk_score": 84,
            "content_actionability_score": 34,
            "preferred_search_surface": "web_content",
            "recommended_content_type": "service_landing",
        },
    }

    ready_plan = hunter._search_plan_for_keyword("community ready", 100)
    risky_plan = hunter._search_plan_for_keyword("risky claim", 100)

    assert ready_plan["platform_limits"]["cafe"] > 100
    assert ready_plan["platform_limits"]["kin"] > 100
    assert ready_plan["include_blog"] is True
    assert risky_plan["platform_limits"]["cafe"] < 100
    assert risky_plan["platform_limits"]["kin"] < 100
    assert risky_plan["platform_limits"]["blog"] < risky_plan["platform_limits"]["cafe"]


def test_viral_hunter_search_plan_uses_execution_lens_to_reduce_blog_noise():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "review lens": {
            "viral_readiness_score": 88,
            "community_signal": 72,
            "conversion_signal": 20,
            "profile_action_signal": 10,
            "medical_ad_risk_score": 8,
            "content_actionability_score": 86,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "recommendation_discovery",
            "execution_lens": "review",
        }
    }

    plan = hunter._search_plan_for_keyword("review lens", 100)

    assert plan["execution_lens"] == "review"
    assert plan["platform_limits"]["cafe"] > 100
    assert plan["platform_limits"]["kin"] > 100
    assert plan["platform_limits"]["blog"] == 65


def test_viral_hunter_search_plan_treats_availability_lens_as_decision_surface():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 교통사고 한의원 주차 가능": {
            "category": "교통사고",
            "viral_readiness_score": 50,
            "community_signal": 10,
            "conversion_signal": 20,
            "profile_action_signal": 25,
            "availability_intent_score": 20,
            "access_convenience_score": 82,
            "medical_ad_risk_score": 8,
            "content_actionability_score": 82,
            "preferred_search_surface": "",
            "recommended_content_type": "",
            "review_intent_type": "none",
            "execution_lens": "availability",
        }
    }

    plan = hunter._search_plan_for_keyword("청주 교통사고 한의원 주차 가능", 100)

    assert plan["execution_lens"] == "availability"
    assert plan["platform_limits"]["cafe"] == 100
    assert plan["platform_limits"]["kin"] == 100
    assert plan["platform_limits"]["blog"] == 65


def test_viral_hunter_builds_lens_aware_search_query_variants():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "금천동 여드름흉터": {
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "profile_action_signal": 10,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "community",
        }
    }

    plans = hunter._search_queries_for_keyword("금천동 여드름흉터", 100)

    assert [plan["query"] for plan in plans] == [
        "금천동 여드름흉터",
        "금천동 여드름흉터 추천",
        "청주 여드름흉터 새살침 후기",
        "여드름흉터",
    ]
    assert plans[1]["source_keyword"] == "금천동 여드름흉터"
    assert plans[1]["variant"] == "community:추천"
    assert plans[2]["variant"] == "axis_scar:새살침후기"
    # 비지역 환자 질문 표면: 지역 토큰 제거 + kin 위주 한정 예산
    assert plans[3]["variant"] == "patient_voice_kin"
    assert plans[3]["platform_limits"] == {"cafe": 15, "blog": 0, "kin": 40}
    assert plans[1]["platform_limits"]["cafe"] < plans[0]["platform_limits"]["cafe"]
    assert hunter.keyword_context["금천동 여드름흉터 추천"]["pathfinder_source_keyword"] == "금천동 여드름흉터"
    assert hunter.keyword_context["청주 여드름흉터 새살침 후기"]["pathfinder_source_keyword"] == "금천동 여드름흉터"
    assert hunter.keyword_context["여드름흉터"]["pathfinder_query_variant"] == "patient_voice_kin"


def test_viral_hunter_infers_query_plan_for_manual_scar_keyword_without_context():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {}

    plans = hunter._search_queries_for_keyword("금천동 여드름흉터 비용", 100)

    assert [plan["query"] for plan in plans] == [
        "금천동 여드름흉터",
        "금천동 여드름흉터 추천",
        "청주 여드름흉터 새살침 후기",
        "여드름흉터",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["variant"] == "community_base"
    assert plans[1]["variant"] == "cost_community:추천"
    assert plans[2]["variant"] == "axis_scar:새살침후기"
    assert plans[3]["variant"] == "patient_voice_kin"
    assert hunter.keyword_context["금천동 여드름흉터 비용"]["category"] == "흉터/여드름흉터"
    assert hunter.keyword_context["금천동 여드름흉터 비용"]["execution_lens"] == "cost"


def test_viral_hunter_applies_inferred_context_when_db_context_is_missing():
    class EmptySeedBuilder:
        def keyword_context_for(self, keywords):
            return {}

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {}
    hunter.seed_builder = EmptySeedBuilder()
    target = ViralTarget(
        platform="kin",
        url="https://example.com/manual-scar",
        title="금천동 여드름흉터 새살침 상담",
        content_preview="청주에서 여드름흉터 한의원 상담 받아본 분 계신가요?",
        matched_keywords=["금천동 여드름흉터 비용"],
        category="기타",
    )

    hunter._apply_keyword_context(target)

    assert target.matched_keyword_category == "흉터/여드름흉터"
    assert target.category == "흉터/여드름흉터"
    assert target.score_breakdown["pathfinder_execution_lens"] == "cost"


def test_viral_hunter_applies_pathfinder_access_scores_to_target_breakdown():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 여드름 한의원 주차 가능": {
            "category": "피부/여드름",
            "viral_readiness_score": 68,
            "local_service_fit_score": 82,
            "content_actionability_score": 80,
            "medical_ad_risk_score": 7,
            "community_signal": 22,
            "conversion_signal": 38,
            "profile_action_signal": 55,
            "availability_intent_score": 62,
            "payment_coverage_score": 10,
            "access_convenience_score": 84,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "access_landing",
            "review_intent_type": "none",
            "execution_lens": "availability",
        }
    }
    target = ViralTarget(
        platform="kin",
        url="https://example.com/skin-access-context",
        title="청주 여드름 한의원 주차 가능한 곳",
        content_preview="차로 가기 편하고 위치 찾기 쉬운 곳이 궁금합니다.",
        matched_keywords=["청주 여드름 한의원 주차 가능"],
        category="피부/여드름",
    )

    hunter._apply_keyword_context(target)

    assert target.score_breakdown["pathfinder_execution_lens"] == "availability"
    assert target.score_breakdown["pathfinder_availability_intent_score"] == 62.0
    assert target.score_breakdown["pathfinder_access_convenience_score"] == 84.0
    assert target.score_breakdown["pathfinder_payment_coverage_score"] == 10.0


def test_viral_hunter_adds_axis_companion_query_for_scar_seed():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "금천동 여드름흉터 비용": {
            "category": "흉터/여드름흉터",
            "viral_readiness_score": 72,
            "community_signal": 35,
            "conversion_signal": 55,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("금천동 여드름흉터 비용", 100)

    assert [plan["query"] for plan in plans] == [
        "금천동 여드름흉터",
        "금천동 여드름흉터 추천",
        "청주 여드름흉터 새살침 후기",
        "여드름흉터",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["variant"] == "community_base"
    assert plans[1]["variant"] == "cost_community:추천"
    assert plans[2]["variant"] == "axis_scar:새살침후기"
    assert plans[3]["variant"] == "patient_voice_kin"
    assert plans[3]["platform_limits"] == {"cafe": 15, "blog": 0, "kin": 40}
    assert hunter.keyword_context["청주 여드름흉터 새살침 후기"]["pathfinder_source_keyword"] == "금천동 여드름흉터 비용"
    assert hunter.keyword_context["여드름흉터"]["pathfinder_source_keyword"] == "금천동 여드름흉터 비용"


def test_viral_hunter_adds_axis_companion_query_for_skin_seed_without_duplicate():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 여드름 한의원 비용": {
            "category": "피부/여드름",
            "viral_readiness_score": 66,
            "community_signal": 28,
            "conversion_signal": 58,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 78,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 비용", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 여드름 한의원",
        "청주 여드름 한의원 추천",
        "청주 피부질환 한의원 추천",
        "여드름 한의원",
    ]
    assert plans[2]["variant"] == "axis_skin:피부질환추천"
    assert plans[3]["variant"] == "patient_voice_kin"


def test_viral_hunter_preserves_specific_scar_context_in_axis_companion():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 수술흉터 새살침 상담": {
            "category": "흉터/여드름흉터",
            "viral_readiness_score": 73,
            "community_signal": 42,
            "conversion_signal": 58,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 82,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "consultation",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 수술흉터 새살침 상담", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 수술흉터 새살침",
        "청주 수술흉터 새살침 추천",
        "청주 수술흉터 새살침 후기",
        "수술흉터 새살침",
    ]
    assert plans[2]["variant"] == "axis_scar:specific_수술흉터"
    assert hunter.keyword_context["청주 수술흉터 새살침 후기"]["pathfinder_source_keyword"] == "청주 수술흉터 새살침 상담"


def test_viral_hunter_preserves_specific_skin_context_before_generic_companion():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 아토피 한의원 비용": {
            "category": "피부/여드름",
            "viral_readiness_score": 67,
            "community_signal": 35,
            "conversion_signal": 55,
            "medical_ad_risk_score": 8,
            "content_actionability_score": 78,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 아토피 한의원 비용", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 아토피 한의원",
        "청주 아토피 한의원 추천",
        "청주 아토피 한의원 후기",
        "아토피 한의원",
    ]
    assert plans[2]["variant"] == "axis_skin:specific_아토피"


def test_viral_hunter_preserves_specific_wart_skin_context_before_generic_companion():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 편평사마귀 한의원 비용": {
            "category": "피부/여드름",
            "viral_readiness_score": 69,
            "community_signal": 38,
            "conversion_signal": 56,
            "medical_ad_risk_score": 8,
            "content_actionability_score": 79,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 편평사마귀 한의원 비용", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 편평사마귀 한의원",
        "청주 편평사마귀 한의원 추천",
        "청주 편평사마귀 한의원 후기",
        "편평사마귀 한의원",
    ]
    assert plans[2]["variant"] == "axis_skin:specific_편평사마귀"


def test_viral_hunter_preserves_specific_traffic_context_in_axis_companion():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 교통사고 입원 자동차보험 서류": {
            "category": "교통사고",
            "viral_readiness_score": 71,
            "community_signal": 34,
            "conversion_signal": 57,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 82,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "service_landing",
            "review_intent_type": "none",
            "execution_lens": "consultation",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 교통사고 입원 자동차보험 서류", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 교통사고 입원 자동차보험 서류",
        "청주 교통사고 입원 자동차보험 서류 추천",
        "청주 교통사고 입원 한의원 추천",
    ]
    assert plans[2]["variant"] == "axis_traffic:specific_입원"
    assert all(plan["variant"] != "patient_voice_kin" for plan in plans)
    assert (
        hunter.keyword_context["청주 교통사고 입원 한의원 추천"]["pathfinder_source_keyword"]
        == "청주 교통사고 입원 자동차보험 서류"
    )


def test_viral_hunter_adds_axis_companion_query_for_diet_review_seed():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 다이어트한약 추천": {
            "category": "다이어트",
            "viral_readiness_score": 70,
            "community_signal": 45,
            "conversion_signal": 35,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 82,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "recommendation_discovery",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 다이어트한약 추천", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 다이어트한약 추천",
        "청주 다이어트한약 후기",
        "청주 한방다이어트 한의원 추천",
        "다이어트한약 추천",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["platform_limits"]["cafe"] >= 150
    assert plans[1]["variant"] == "axis_diet:한약후기"
    assert plans[2]["variant"] == "axis_diet:한방다이어트추천"
    assert plans[3]["variant"] == "patient_voice_kin"


def test_viral_hunter_adds_axis_companion_query_for_body_review_seed():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 체형교정 한의원 추천": {
            "category": "체형교정",
            "viral_readiness_score": 62,
            "community_signal": 45,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "recommendation_discovery",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 체형교정 한의원 추천", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 체형교정 한의원 추천",
        "청주 체형교정 추나 한의원 추천",
        "청주 골반교정 추나 한의원 추천",
        "체형교정 한의원 추천",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["platform_limits"]["cafe"] >= 150
    assert plans[1]["variant"] == "axis_body:체형추나추천"
    assert plans[2]["variant"] == "axis_body:골반교정추천"
    assert plans[3]["variant"] == "patient_voice_kin"
    assert hunter.keyword_context["청주 체형교정 추나 한의원 추천"]["pathfinder_source_keyword"] == "청주 체형교정 한의원 추천"
    assert hunter.keyword_context["청주 골반교정 추나 한의원 추천"]["pathfinder_source_keyword"] == "청주 체형교정 한의원 추천"


def test_viral_hunter_adds_axis_companion_query_for_lifting_seed_even_when_review_term_exists():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 한방리프팅 추천": {
            "category": "리프팅/탄력",
            "viral_readiness_score": 48,
            "community_signal": 25,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "recommendation_discovery",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 한방리프팅 추천", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 한방리프팅 추천",
        "청주 매선 한방리프팅 후기",
        "청주 팔자주름 한방리프팅 후기",
        "한방리프팅 추천",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[1]["variant"] == "axis_lifting:매선한방후기"
    assert plans[2]["variant"] == "axis_lifting:팔자주름후기"
    assert plans[3]["variant"] == "patient_voice_kin"


def test_viral_hunter_adds_compound_axis_companion_query_for_asymmetry_seed():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "봉명동 턱비대칭 한의원 비용": {
            "category": "안면비대칭",
            "viral_readiness_score": 47,
            "community_signal": 20,
            "conversion_signal": 60,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "service_landing",
            "review_intent_type": "none",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("봉명동 턱비대칭 한의원 비용", 100)

    # 거래형 접미사(비용)는 광고성 공급만 노출하므로 검색 면에서는 제거되고,
    # cost 렌즈는 커뮤니티 표면(추천) 동반 쿼리로 우회한다.
    assert [plan["query"] for plan in plans] == [
        "봉명동 턱비대칭 한의원",
        "봉명동 턱비대칭 한의원 추천",
        "청주 턱관절 안면비대칭 한의원 추천",
        "턱비대칭 한의원",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["variant"] == "community_base"
    assert plans[1]["variant"] == "cost_community:추천"
    assert plans[2]["variant"] == "axis_asymmetry:턱관절비대칭추천"
    assert plans[3]["variant"] == "patient_voice_kin"
    assert hunter.keyword_context["봉명동 턱비대칭 한의원"]["pathfinder_source_keyword"] == "봉명동 턱비대칭 한의원 비용"


def test_viral_hunter_redirects_cost_lens_seed_to_community_surface():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 여드름 한의원 비용": {
            "viral_readiness_score": 72,
            "community_signal": 20,
            "conversion_signal": 50,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 비용", 100)

    # 비용 접미사 쿼리는 그대로 검색하지 않고 서비스 코어 + 커뮤니티 표면으로 우회한다.
    assert [plan["query"] for plan in plans] == [
        "청주 여드름 한의원",
        "청주 여드름 한의원 추천",
        "청주 피부질환 한의원 추천",
        "여드름 한의원",
    ]
    assert plans[0]["variant"] == "community_base"
    assert plans[1]["variant"] == "cost_community:추천"
    assert plans[2]["variant"] == "axis_skin:피부질환추천"
    assert plans[3]["variant"] == "patient_voice_kin"


def test_viral_hunter_does_not_duplicate_query_variant_when_lens_term_exists():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 여드름 한의원 추천": {
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 추천", 100)

    assert [plan["query"] for plan in plans] == [
        "청주 여드름 한의원 추천",
        "청주 피부질환 한의원 추천",
        "청주 아토피 한의원 후기",
        "여드름 한의원 추천",
    ]
    assert [plan["query"] for plan in plans].count("청주 여드름 한의원 추천") == 1
    assert plans[1]["variant"] == "axis_skin:피부질환추천"
    assert plans[2]["variant"] == "axis_skin:아토피후기"
    assert plans[3]["variant"] == "patient_voice_kin"


def test_viral_hunter_shared_variant_context_keeps_stronger_source_lineage():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "금천동 여드름흉터 비용": {
            "category": "흉터/여드름흉터",
            "priority_v3": 900,
            "viral_readiness_score": 91,
            "content_actionability_score": 88,
            "local_service_fit_score": 86,
            "community_signal": 55,
            "conversion_signal": 70,
            "profile_action_signal": 62,
            "medical_ad_risk_score": 5,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "cost",
        },
        "봉명동 여드름흉터 비용": {
            "category": "흉터/여드름흉터",
            "priority_v3": 10,
            "viral_readiness_score": 35,
            "content_actionability_score": 50,
            "local_service_fit_score": 45,
            "community_signal": 10,
            "conversion_signal": 20,
            "profile_action_signal": 5,
            "medical_ad_risk_score": 5,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "cost",
        },
    }

    hunter._search_queries_for_keyword("금천동 여드름흉터 비용", 100)
    hunter._search_queries_for_keyword("봉명동 여드름흉터 비용", 100)

    shared_context = hunter.keyword_context["청주 여드름흉터 새살침 후기"]

    assert shared_context["pathfinder_source_keyword"] == "금천동 여드름흉터 비용"
    assert shared_context["pathfinder_source_keywords"] == [
        "금천동 여드름흉터 비용",
        "봉명동 여드름흉터 비용",
    ]
    assert shared_context["pathfinder_query_variants"] == ["axis_scar:새살침후기"]
    assert shared_context["pathfinder_context_collision_count"] == 2


def test_viral_hunter_apply_context_recovers_original_source_from_shared_variant():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 여드름흉터 새살침 후기": {
            "category": "흉터/여드름흉터",
            "priority_v3": 900,
            "viral_readiness_score": 91,
            "content_actionability_score": 88,
            "local_service_fit_score": 86,
            "community_signal": 55,
            "conversion_signal": 70,
            "profile_action_signal": 62,
            "medical_ad_risk_score": 5,
            "execution_lens": "review",
            "pathfinder_source_keyword": "금천동 여드름흉터 비용",
            "pathfinder_query_variant": "axis_scar:새살침후기",
        }
    }
    target = ViralTarget(
        platform="kin",
        url="https://example.com/shared-variant-only",
        title="청주 여드름흉터 새살침 후기 궁금합니다",
        content_preview="청주에서 여드름흉터 새살침 상담 받아본 분 계신가요?",
        matched_keywords=["청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
    )

    hunter._apply_keyword_context(target)

    assert target.matched_keywords[:2] == [
        "금천동 여드름흉터 비용",
        "청주 여드름흉터 새살침 후기",
    ]
    assert target.score_breakdown["pathfinder_source_keyword"] == "금천동 여드름흉터 비용"
    assert target.score_breakdown["pathfinder_context_keyword"] == "청주 여드름흉터 새살침 후기"
    assert target.score_breakdown["pathfinder_search_query"] == "청주 여드름흉터 새살침 후기"
    assert target.score_breakdown["pathfinder_query_variant"] == "axis_scar:새살침후기"


def test_viral_hunter_query_variant_keeps_original_seed_lineage():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/query-variant",
        title="금천동 여드름흉터 추천 부탁해요",
        matched_keywords=["금천동 여드름흉터 추천"],
    )

    viral_hunter.ViralHunter._attach_search_query_lineage(
        target,
        source_keyword="금천동 여드름흉터",
        search_query="금천동 여드름흉터 추천",
        query_variant="community:추천",
    )

    assert target.matched_keywords[:2] == ["금천동 여드름흉터", "금천동 여드름흉터 추천"]
    assert target.score_breakdown["pathfinder_source_keyword"] == "금천동 여드름흉터"
    assert target.score_breakdown["pathfinder_search_query"] == "금천동 여드름흉터 추천"
    assert target.score_breakdown["pathfinder_query_variant"] == "community:추천"


def test_viral_hunter_merges_duplicate_search_result_with_stronger_query_variant():
    current = ViralTarget(
        platform="kin",
        url="https://example.com/duplicate-scar-question",
        title="청주 여드름흉터 질문",
        content_preview="청주에서 흉터 상담 가능한 곳이 궁금합니다.",
        matched_keywords=["청주 여드름흉터"],
        search_rank=8,
        exposure_score=20,
        sort_appearances=["sim"],
    )
    incoming = ViralTarget(
        platform="kin",
        url="https://example.com/duplicate-scar-question",
        title="청주 여드름흉터 새살침 질문",
        content_preview="청주에서 패인흉터 새살침 상담 받아보신 분 계신가요?",
        matched_keywords=["청주 여드름흉터 새살침 후기"],
        search_rank=2,
        exposure_score=45,
        sort_appearances=["date"],
    )
    viral_hunter.ViralHunter._attach_search_query_lineage(
        current,
        source_keyword="금천동 여드름흉터 비용",
        search_query="금천동 여드름흉터",
        query_variant="community_base",
    )
    viral_hunter.ViralHunter._attach_search_query_lineage(
        incoming,
        source_keyword="금천동 여드름흉터 비용",
        search_query="청주 여드름흉터 새살침 후기",
        query_variant="axis_scar:새살침후기",
    )

    viral_hunter.ViralHunter._merge_duplicate_search_target(current, incoming)

    assert current.score_breakdown["pathfinder_query_variant"] == "axis_scar:새살침후기"
    assert current.score_breakdown["pathfinder_search_query"] == "청주 여드름흉터 새살침 후기"
    assert current.score_breakdown["pathfinder_query_variants"] == [
        "community_base",
        "axis_scar:새살침후기",
    ]
    assert current.score_breakdown["pathfinder_search_queries"] == [
        "금천동 여드름흉터",
        "청주 여드름흉터 새살침 후기",
    ]
    assert current.score_breakdown["pathfinder_duplicate_query_count"] == 2
    assert current.matched_keywords[:2] == [
        "금천동 여드름흉터 비용",
        "청주 여드름흉터 새살침 후기",
    ]
    assert current.search_rank == 2
    assert current.exposure_score == 45
    assert current.sort_appearances == ["sim", "date"]


def test_viral_hunter_duplicate_merge_prefers_specific_axis_variant_over_generic_axis_exposure():
    current = ViralTarget(
        platform="kin",
        url="https://example.com/duplicate-surgery-scar",
        title="청주 여드름흉터 새살침 후기",
        content_preview="청주에서 여드름흉터 새살침 상담 받아보신 분 계신가요?",
        matched_keywords=["청주 여드름흉터 새살침 후기"],
        search_rank=1,
        exposure_score=90,
        sort_appearances=["sim"],
    )
    incoming = ViralTarget(
        platform="kin",
        url="https://example.com/duplicate-surgery-scar",
        title="청주 수술흉터 새살침 후기",
        content_preview="수술흉터랑 켈로이드 때문에 새살침 상담 후기가 궁금합니다.",
        matched_keywords=["청주 수술흉터 새살침 후기"],
        search_rank=7,
        exposure_score=25,
        sort_appearances=["date"],
    )
    viral_hunter.ViralHunter._attach_search_query_lineage(
        current,
        source_keyword="청주 수술흉터 새살침 상담",
        search_query="청주 여드름흉터 새살침 후기",
        query_variant="axis_scar:새살침후기",
    )
    viral_hunter.ViralHunter._attach_search_query_lineage(
        incoming,
        source_keyword="청주 수술흉터 새살침 상담",
        search_query="청주 수술흉터 새살침 후기",
        query_variant="axis_scar:specific_수술흉터",
    )

    viral_hunter.ViralHunter._merge_duplicate_search_target(current, incoming)

    assert current.score_breakdown["pathfinder_query_variant"] == "axis_scar:specific_수술흉터"
    assert current.score_breakdown["pathfinder_search_query"] == "청주 수술흉터 새살침 후기"
    assert current.score_breakdown["pathfinder_query_variants"] == [
        "axis_scar:새살침후기",
        "axis_scar:specific_수술흉터",
    ]
    assert current.matched_keywords[:2] == [
        "청주 수술흉터 새살침 상담",
        "청주 수술흉터 새살침 후기",
    ]
    # Exposure remains the best observed URL-level value even when lineage prefers specific context.
    assert current.exposure_score == 90
    assert current.search_rank == 1


def test_viral_hunter_checkpoint_hash_includes_query_variants(tmp_path):
    class EmptySearcher:
        def search_all(self, *args, **kwargs):
            return []

        def get_stats(self):
            return {"requests": 0, "cache_hits": 0, "errors": 0, "error_rate": "0%"}

    class EmptyFilter:
        def filter(self, targets):
            return []

    class EmptyDb:
        def insert_viral_target(self, data):
            return True

    def make_hunter(context):
        captured_hashes = []
        hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
        hunter.keyword_context = dict(context)
        hunter.searcher = EmptySearcher()
        hunter.filter = EmptyFilter()
        hunter.db = EmptyDb()
        hunter.cfg = type("Cfg", (), {"root_dir": str(tmp_path)})()
        hunter.generator = type("Generator", (), {"last_failed_ai_batches": set()})()
        hunter._load_keyword_context = lambda keywords: None
        hunter._load_checkpoint = lambda keyword_hash: captured_hashes.append(keyword_hash) or None
        hunter._save_checkpoint = lambda *args, **kwargs: None
        hunter._clear_checkpoint = lambda: None
        return hunter, captured_hashes

    base_hunter, base_hashes = make_hunter({})
    variant_hunter, variant_hashes = make_hunter({
        "seed alpha": {
            "viral_readiness_score": 70,
            "community_signal": 65,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "execution_lens": "community",
        }
    })
    scan_hunter, scan_hashes = make_hunter({
        "seed alpha": {
            "scan_run_id": 77,
            "viral_readiness_score": 70,
        }
    })
    boost_hunter, boost_hashes = make_hunter({
        "seed alpha": {
            "category": "skin",
            "execution_lens": "cost",
            "viral_readiness_score": 70,
        }
    })

    base_hunter.hunt(keywords=["seed alpha"], max_per_platform=100, top_n_for_ai=0)
    variant_hunter.hunt(keywords=["seed alpha"], max_per_platform=100, top_n_for_ai=0)
    scan_hunter.hunt(keywords=["seed alpha"], max_per_platform=100, top_n_for_ai=0, source_scan_run_id=77)
    boost_hunter.hunt(
        keywords=["seed alpha"],
        max_per_platform=100,
        top_n_for_ai=0,
        boost_lenses=["cost"],
    )

    assert base_hashes and variant_hashes and base_hashes[0] != variant_hashes[0]
    assert scan_hashes and scan_hashes[0] != base_hashes[0]
    assert boost_hashes and boost_hashes[0] != base_hashes[0]


def test_viral_hunter_load_keywords_can_pin_pathfinder_scan_id(tmp_path):
    db_path = tmp_path / "source_scan_seed_pin.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES
                (101, 'legion', 'completed', '2026-06-10'),
                (102, 'legion', 'completed', '2026-06-11');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, '다이어트', 'A', 100, 1000, 10, ?,
                      'transactional', ?, 1, 'active', 90, 90, 1)
            """,
            [
                ("scan101 diet consultation", 100, 101),
                ("scan102 diet consultation", 300, 102),
            ],
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.seed_builder = ViralSeedBuilder(str(db_path))
    hunter.keyword_context = {}

    keywords = hunter._load_keywords(source_scan_run_id=101)

    assert keywords == ["scan101 diet consultation"]
    assert hunter.keyword_context["scan101 diet consultation"]["scan_run_id"] == 101
    assert "scan102 diet consultation" not in hunter.keyword_context


def test_viral_hunter_limit_keywords_preserves_axis_lens_coverage(tmp_path):
    class CapturingSearcher:
        def __init__(self):
            self.calls = []

        def search_all(self, keyword, **kwargs):
            self.calls.append(keyword)
            return []

        def get_stats(self):
            return {"requests": 0, "cache_hits": 0, "errors": 0, "error_rate": "0%"}

    class EmptyFilter:
        def filter(self, targets):
            return []

    class EmptyDb:
        def insert_viral_target(self, data):
            return True

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "skin review one": {"category": "skin", "execution_lens": "review"},
        "skin review two": {"category": "skin", "execution_lens": "review"},
        "skin cost one": {"category": "skin", "execution_lens": "cost"},
        "diet review one": {"category": "diet", "execution_lens": "review"},
    }
    hunter.searcher = CapturingSearcher()
    hunter.filter = EmptyFilter()
    hunter.db = EmptyDb()
    hunter.cfg = type("Cfg", (), {"root_dir": str(tmp_path)})()
    hunter.generator = type("Generator", (), {"last_failed_ai_batches": set()})()
    hunter.seed_builder = None
    hunter._load_keyword_context = lambda keywords: None
    hunter._load_checkpoint = lambda keyword_hash: None
    hunter._save_checkpoint = lambda *args, **kwargs: None
    hunter._clear_checkpoint = lambda: None

    original_keywords = ["skin review one", "skin review two", "skin cost one", "diet review one"]
    boosted_order = hunter._order_keywords_for_handoff_coverage(
        original_keywords,
        boost_lenses=["cost"],
    )
    assert boosted_order[:3] == ["skin cost one", "skin review one", "diet review one"]

    hunter.hunt(
        keywords=original_keywords,
        limit_keywords=3,
        max_per_platform=10,
        top_n_for_ai=0,
        fresh=True,
    )

    base_calls = [keyword for keyword in hunter.searcher.calls if keyword in set(original_keywords)]
    assert base_calls == ["skin review one", "skin cost one", "diet review one"]


def test_naver_search_all_honors_platform_specific_limits():
    searcher = viral_hunter.NaverUnifiedSearch(delay=0, use_cache=False)
    calls = []

    def fake(platform):
        def _search(keyword, max_results):
            calls.append((platform, keyword, max_results))
            return [
                ViralTarget(
                    platform=platform,
                    url=f"https://example.com/{platform}",
                    title=f"{platform} result",
                    matched_keywords=[keyword],
                )
            ]
        return _search

    searcher.search_cafe = fake("cafe")
    searcher.search_blog = fake("blog")
    searcher.search_kin = fake("kin")

    results = searcher.search_all(
        "청주 다이어트 상담",
        max_per_platform=100,
        include_blog=True,
        platform_limits={"cafe": 180, "blog": 0, "kin": 140},
    )

    assert calls == [
        ("cafe", "청주 다이어트 상담", 180),
        ("kin", "청주 다이어트 상담", 140),
    ]
    assert [target.platform for target in results] == ["cafe", "kin"]


def test_viral_seed_builder_accepts_legion_mode_lineage(tmp_path):
    db_path = tmp_path / "seed_builder_mode.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                mode TEXT,
                status TEXT,
                completed_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO scan_runs(id, scan_type, mode, status, completed_at)
            VALUES (7, 'pathfinder', 'legion', 'completed', '2026-06-01')
            """
        )
        conn.commit()

    assert ViralSeedBuilder(str(db_path)).latest_completed_legion_scan_id() == 7


def test_viral_seed_builder_builds_from_scan_run_id_only_schema(tmp_path):
    db_path = tmp_path / "seed_builder_scan_run_only.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER
            );
            """
        )
        conn.execute(
            "INSERT INTO scan_runs(id, scan_type, status, completed_at) VALUES (8, 'legion', 'completed', '2026-06-01')"
        )
        conn.execute(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core, status
            ) VALUES ('scan id only keyword', 'cat', 'A', 100, 1000, 10, 150, 'transactional', 8, 1, 'active')
            """
        )
        conn.commit()

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=8, quotas={"cat": 1})

    assert len(seeds) == 1
    assert seeds[0].keyword == "scan id only keyword"
    assert seeds[0].scan_run_id == 8


def test_viral_seed_builder_handles_thin_keyword_schema(tmp_path):
    db_path = tmp_path / "seed_builder_thin.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                priority_v3 REAL,
                scan_run_id INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (9, 'legion', 'completed', '2026-06-02');
            INSERT INTO keyword_insights(keyword, category, grade, priority_v3, scan_run_id)
            VALUES ('thin schema keyword', 'cat', 'A', 77, 9);
            """
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=9, quotas={"cat": 1})

    assert len(seeds) == 1
    assert seeds[0].keyword == "thin schema keyword"
    assert seeds[0].document_count == 0
    assert seeds[0].search_intent == "unknown"


def test_viral_seed_builder_diversifies_skin_clusters_and_regions(tmp_path):
    db_path = tmp_path / "seed_builder_diversity.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (10, 'legion', 'completed', '2026-06-03');
            """
        )
        rows = [
            ("분평동 여드름흉터 한의원 비용", 200),
            ("분평동 여드름흉터 한의원 상담", 190),
            ("분평동 여드름흉터 한의원 예약", 180),
            ("산남동 여드름 한의원 비용", 100),
            ("복대동 새살침 후기", 90),
        ]
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, '피부/여드름', 'A', 100, 1000, 10, ?, 'transactional',
                      10, 1, 'active', 100, 100, 1)
            """,
            rows,
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=10,
        quotas={"흉터/여드름흉터": 3, "피부/여드름": 1},
    )

    selected = [seed.keyword for seed in seeds]
    assert "분평동 여드름흉터 한의원 비용" in selected
    assert "분평동 여드름흉터 한의원 상담" in selected
    assert "복대동 새살침 후기" in selected
    assert "산남동 여드름 한의원 비용" in selected
    assert "분평동 여드름흉터 한의원 예약" not in selected
    assert Counter(seed.category for seed in seeds) == Counter({"흉터/여드름흉터": 3, "피부/여드름": 1})


def test_viral_seed_builder_keeps_gyulim_scar_axis_separate_from_skin(tmp_path):
    db_path = tmp_path / "seed_builder_scar_alias.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (11, 'legion', 'completed', '2026-06-04');
            """
        )
        rows = [
            ("청주 수술흉터 새살침 상담", "흉터/여드름흉터", 210),
            ("청주 성인여드름 한의원 비용", "피부", 200),
        ]
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, ?, 'A', 100, 1000, 10, ?, 'transactional',
                      11, 1, 'active', 100, 100, 1)
            """,
            rows,
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=11,
        quotas={"흉터/여드름흉터": 1, "피부": 1},
    )

    assert [seed.keyword for seed in seeds] == [
        "청주 수술흉터 새살침 상담",
        "청주 성인여드름 한의원 비용",
    ]
    assert {seed.category for seed in seeds} == {"흉터/여드름흉터", "피부/여드름"}
    context = ViralSeedBuilder(str(db_path)).keyword_context_for(["청주 수술흉터 새살침 상담"])
    assert context["청주 수술흉터 새살침 상담"]["category"] == "흉터/여드름흉터"


def test_viral_seed_builder_keeps_skin_comparison_when_hanbang_anchor_present(tmp_path):
    db_path = tmp_path / "seed_builder_skin_compare.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (12, 'legion', 'completed', '2026-06-05');
            """
        )
        rows = [
            ("청주 여드름흉터 피부과 말고 한의원 상담", 220),
            ("청주 피부과 추천", 210),
        ]
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (?, '피부/여드름', 'A', 100, 1000, 10, ?, 'transactional',
                      12, 1, 'active', 100, 100, 1)
            """,
            rows,
        )

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=12, quotas={"흉터/여드름흉터": 2})

    selected = [seed.keyword for seed in seeds]
    assert "청주 여드름흉터 피부과 말고 한의원 상담" in selected
    assert "청주 피부과 추천" not in selected


def test_viral_seed_builder_gap_fill_restores_missing_profile_axis(tmp_path):
    db_path = tmp_path / "seed_builder_missing_axis_gap_fill.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT,
                longtail_score REAL,
                business_value_score REAL,
                high_value_longtail INTEGER
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (13, 'legion', 'completed', '2026-06-06');
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, scan_run_id, business_core,
                status, longtail_score, business_value_score, high_value_longtail
            ) VALUES (
                '청주 수술흉터 새살침 상담', '흉터/여드름흉터', 'A',
                100, 1000, 10, 200, 'transactional',
                13, 1, 'active', 100, 100, 1
            );
            """
        )

    seeds = ViralSeedBuilder(str(db_path)).build(
        scan_run_id=13,
        quotas={"흉터/여드름흉터": 1, "안면비대칭": 1},
        fill_profile_gaps=True,
    )

    assert len(seeds) == 2
    assert {seed.category for seed in seeds} == {"흉터/여드름흉터", "안면비대칭"}
    assert any(seed.keyword == "청주 수술흉터 새살침 상담" for seed in seeds)
    assert any(seed.scan_run_id == 13 and seed.category == "안면비대칭" for seed in seeds)


def test_viral_hunter_applies_pathfinder_context_for_custom_keyword(tmp_path):
    db_path = tmp_path / "custom_keyword_context.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                last_scan_run_id INTEGER,
                status TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, last_scan_run_id, status
            ) VALUES ('custom treatment keyword', 'custom category', 'A', 120, 900, 12.5, 88.0, 'transactional', 7, 'active')
            """
        )
        conn.commit()

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.seed_builder = ViralSeedBuilder(str(db_path))
    hunter.keyword_context = {}

    target = ViralTarget(
        platform="kin",
        url="https://example.com/custom",
        title="custom target",
        matched_keywords=["secondary keyword", "custom treatment keyword"],
        category="기타",
    )

    hunter._apply_keyword_context(target)

    assert target.source_scan_run_id == 7
    assert target.matched_keyword_grade == "A"
    assert target.matched_keyword_kei == 12.5
    assert target.matched_keyword_priority == 88.0
    assert target.matched_keyword_category == "custom category"
    assert target.category == "custom category"


def test_viral_hunter_attaches_pathfinder_execution_context_to_targets():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 수술흉터 새살침 상담": {
            "scan_run_id": 19,
            "grade": "A",
            "kei": 12.0,
            "priority_v3": 118.0,
            "category": "흉터/여드름흉터",
            "viral_readiness_score": 91.0,
            "local_service_fit_score": 88.0,
            "content_actionability_score": 86.0,
            "medical_ad_risk_score": 9.0,
            "community_signal": 74.0,
            "conversion_signal": 61.0,
            "profile_action_signal": 58.0,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "service_landing",
            "brand_intent_type": "generic",
            "review_intent_type": "recommendation_discovery",
            "execution_lens": "review",
            "source_signals_json": '["community_demand", "profile_action_conversion"]',
            "quality_flags_json": '["medical_ad_review_required"]',
        }
    }

    target = ViralTarget(
        platform="kin",
        url="https://example.com/pathfinder-context",
        title="청주 수술흉터 새살침 상담 가능한 곳",
        matched_keywords=["청주 수술흉터 새살침 상담"],
        category="기타",
    )

    hunter._apply_keyword_context(target)
    formatted = AICommentGenerator._format_unified_target(3, target)

    assert target.source_scan_run_id == 19
    assert target.matched_keyword_category == "흉터/여드름흉터"
    assert target.score_breakdown["pathfinder_viral_readiness_score"] == 91.0
    assert target.score_breakdown["pathfinder_content_actionability_score"] == 86.0
    assert target.score_breakdown["pathfinder_preferred_search_surface"] == "hybrid_local_content"
    assert target.score_breakdown["pathfinder_execution_lens"] == "review"
    assert target.score_breakdown["pathfinder_source_keyword"] == "청주 수술흉터 새살침 상담"
    assert target.score_breakdown["pathfinder_source_signals"] == [
        "community_demand",
        "profile_action_conversion",
    ]
    assert target.score_breakdown["pathfinder_quality_flags"] == ["medical_ad_review_required"]
    assert "community_demand" in target.score_breakdown["pathfinder_insight_brief"]
    assert "PATHFINDER_KEYWORD: 청주 수술흉터 새살침 상담" in formatted
    assert "PATHFINDER_EXECUTION: readiness=91.0" in formatted
    assert "PATHFINDER_SIGNALS: sources=community_demand, profile_action_conversion; flags=medical_ad_review_required" in formatted
    assert "PATHFINDER_BRIEF: axis=흉터/여드름흉터; lens=review" in formatted
    assert "lens=review" in formatted


def test_unified_target_format_includes_pathfinder_search_lineage_and_fit_scores():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/pathfinder-ai-handoff",
        title="청주 여드름흉터 새살침 후기 궁금합니다",
        content_preview="수술흉터와 여드름흉터 때문에 새살침 상담 후기가 궁금합니다.",
        matched_keywords=["금천동 여드름흉터 비용", "청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_source_keyword": "금천동 여드름흉터 비용",
            "pathfinder_context_keyword": "청주 여드름흉터 새살침 후기",
            "pathfinder_search_query": "청주 여드름흉터 새살침 후기",
            "pathfinder_query_variant": "axis_scar:새살침후기",
            "pathfinder_source_keywords": [
                "금천동 여드름흉터 비용",
                "봉명동 여드름흉터 비용",
            ],
            "pathfinder_query_variants": ["community_base", "axis_scar:새살침후기"],
            "pathfinder_context_collision_count": 2,
            "pathfinder_axis_fit_score": 84.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_axis_fit_signals": "pathfinder_axis_core_match,pathfinder_axis_specific_context_match",
            "pathfinder_lens_fit_score": 78.0,
            "pathfinder_lens_fit_tier": "strong",
            "pathfinder_lens_fit_signals": "pathfinder_lens_review_match,pathfinder_lens_surface_match",
        },
    )

    formatted = AICommentGenerator._format_unified_target(8, target)

    assert (
        "PATHFINDER_SEARCH: source=금천동 여드름흉터 비용; "
        "query=청주 여드름흉터 새살침 후기; variant=axis_scar:새살침후기"
    ) in formatted
    assert "sources=금천동 여드름흉터 비용, 봉명동 여드름흉터 비용" in formatted
    assert "variants=community_base, axis_scar:새살침후기" in formatted
    assert "collisions=2" in formatted
    assert "PATHFINDER_FIT: axis=84.0/strong; lens=78.0/strong" in formatted
    assert "axis_signals=pathfinder_axis_core_match, pathfinder_axis_specific_context_match" in formatted
    assert "lens_signals=pathfinder_lens_review_match, pathfinder_lens_surface_match" in formatted


def test_viral_filter_uses_pathfinder_execution_signals_for_post_priority():
    common = {
        "platform": "kin",
        "title": "청주 여드름흉터 새살침 한의원 추천 부탁드려요",
        "content_preview": (
            "청주에서 여드름흉터랑 패인흉터 때문에 새살침 상담 받아보려고 합니다. "
            "한의원 비용이나 예약 가능한 곳, 주말 진료 되는 곳 있으면 추천 부탁드려요. "
            "직장인이라 빨리 상담 가능하면 좋겠습니다."
        ),
        "matched_keywords": ["청주 여드름흉터 새살침 상담"],
        "category": "흉터/여드름흉터",
        "matched_keyword_category": "흉터/여드름흉터",
        "matched_keyword_grade": "A",
        "matched_keyword_priority": 115,
        "date_str": "방금 전",
        "comment_count": 0,
        "view_count": 180,
    }
    baseline = ViralTarget(url="https://example.com/pathfinder-base", **common)
    boosted = ViralTarget(
        url="https://example.com/pathfinder-boosted",
        score_breakdown={
            "pathfinder_viral_readiness_score": 92.0,
            "pathfinder_local_service_fit_score": 88.0,
            "pathfinder_content_actionability_score": 86.0,
            "pathfinder_medical_ad_risk_score": 8.0,
            "pathfinder_community_signal": 72.0,
            "pathfinder_conversion_signal": 60.0,
            "pathfinder_profile_action_signal": 58.0,
            "pathfinder_preferred_search_surface": "hybrid_local_content",
            "pathfinder_recommended_content_type": "service_landing",
            "pathfinder_review_intent_type": "recommendation_discovery",
        },
        **common,
    )

    filtered = viral_hunter.CommentableFilter().filter([baseline, boosted])
    by_url = {target.url: target for target in filtered}

    assert set(by_url) == {"https://example.com/pathfinder-base", "https://example.com/pathfinder-boosted"}
    assert by_url["https://example.com/pathfinder-boosted"].priority_score > by_url["https://example.com/pathfinder-base"].priority_score
    boosted_breakdown = by_url["https://example.com/pathfinder-boosted"].score_breakdown
    assert boosted_breakdown["pathfinder_execution_adjustment"] > 0
    assert "pathfinder_ready_keyword" in boosted_breakdown["pathfinder_execution_signals"]
    assert boosted_breakdown["pathfinder_priority_adjustment"] > 0


def test_viral_filter_prioritizes_posts_matching_pathfinder_execution_lens():
    pathfinder_context = {
        "pathfinder_viral_readiness_score": 91.0,
        "pathfinder_local_service_fit_score": 88.0,
        "pathfinder_content_actionability_score": 86.0,
        "pathfinder_medical_ad_risk_score": 8.0,
        "pathfinder_community_signal": 70.0,
        "pathfinder_conversion_signal": 58.0,
        "pathfinder_profile_action_signal": 45.0,
        "pathfinder_preferred_search_surface": "hybrid_local_content",
        "pathfinder_recommended_content_type": "proof_safe_guide",
        "pathfinder_review_intent_type": "none",
        "pathfinder_execution_lens": "cost",
    }
    common = {
        "platform": "kin",
        "matched_keywords": ["청주 여드름흉터 한의원"],
        "category": "피부/여드름",
        "matched_keyword_category": "피부/여드름",
        "matched_keyword_grade": "A",
        "matched_keyword_priority": 120,
        "date_str": "방금 전",
        "comment_count": 0,
        "view_count": 180,
    }
    cost_match = ViralTarget(
        url="https://example.com/pathfinder-lens-cost",
        title="청주 여드름흉터 한의원 비용 궁금해요",
        content_preview=(
            "청주에서 여드름흉터 치료를 알아보는 중인데 한의원 비용이랑 보험 가능 여부가 궁금합니다. "
            "상담 전에 대략적인 치료비를 알고 싶어요."
        ),
        score_breakdown=pathfinder_context.copy(),
        **common,
    )
    recommendation_mismatch = ViralTarget(
        url="https://example.com/pathfinder-lens-review",
        title="청주 여드름흉터 한의원 추천 부탁해요",
        content_preview=(
            "청주에서 여드름흉터 때문에 한의원 알아보는 중인데 어디가 괜찮은지 경험 있으신 분 추천 부탁드려요. "
            "상담도 생각하고 있습니다."
        ),
        score_breakdown=pathfinder_context.copy(),
        **common,
    )

    filtered = viral_hunter.CommentableFilter().filter([recommendation_mismatch, cost_match])
    by_url = {target.url: target for target in filtered}

    assert set(by_url) == {
        "https://example.com/pathfinder-lens-cost",
        "https://example.com/pathfinder-lens-review",
    }
    assert by_url["https://example.com/pathfinder-lens-cost"].priority_score > by_url["https://example.com/pathfinder-lens-review"].priority_score
    cost_breakdown = by_url["https://example.com/pathfinder-lens-cost"].score_breakdown
    mismatch_breakdown = by_url["https://example.com/pathfinder-lens-review"].score_breakdown
    assert cost_breakdown["pathfinder_lens_fit_score"] >= 75
    assert cost_breakdown["pathfinder_lens_fit_tier"] == "strong"
    assert "pathfinder_lens_cost_match" in cost_breakdown["pathfinder_lens_fit_signals"]
    assert mismatch_breakdown["pathfinder_lens_fit_tier"] in {"weak", "mismatch"}
    assert mismatch_breakdown["pathfinder_lens_adjustment"] < cost_breakdown["pathfinder_lens_adjustment"]


def test_viral_filter_scores_pathfinder_axis_fit_separately_from_lens():
    pathfinder_context = {
        "pathfinder_viral_readiness_score": 91.0,
        "pathfinder_local_service_fit_score": 88.0,
        "pathfinder_content_actionability_score": 86.0,
        "pathfinder_medical_ad_risk_score": 8.0,
        "pathfinder_community_signal": 70.0,
        "pathfinder_conversion_signal": 58.0,
        "pathfinder_profile_action_signal": 45.0,
        "pathfinder_preferred_search_surface": "hybrid_local_content",
        "pathfinder_recommended_content_type": "proof_safe_guide",
        "pathfinder_review_intent_type": "none",
        "pathfinder_execution_lens": "cost",
    }
    common = {
        "platform": "kin",
        "matched_keywords": ["청주 한의원 비용"],
        "category": "흉터/여드름흉터",
        "matched_keyword_category": "흉터/여드름흉터",
        "matched_keyword_grade": "A",
        "matched_keyword_priority": 120,
        "date_str": "방금 전",
        "comment_count": 0,
        "view_count": 180,
    }
    axis_match = ViralTarget(
        url="https://example.com/pathfinder-axis-skin",
        title="청주 여드름흉터 한의원 비용 궁금해요",
        content_preview=(
            "청주에서 여드름흉터랑 패인흉터 때문에 새살침 치료 상담을 알아봅니다. "
            "한의원 비용과 예약 가능한 곳이 궁금해요. 피부과 레이저 말고 한방 쪽으로도 "
            "상담 받아본 분이 있는지, 치료기간이나 주말 진료 여부도 알고 싶습니다."
        ),
        score_breakdown=pathfinder_context.copy(),
        **common,
    )
    axis_mismatch = ViralTarget(
        url="https://example.com/pathfinder-axis-diet",
        title="청주 다이어트한약 한의원 비용 궁금해요",
        content_preview=(
            "청주에서 다이어트한약 먹어보신 분 계신가요? 감량 상담이랑 비용, 한의원 후기가 궁금합니다. "
            "식욕억제나 체중 감량 때문에 알아보는 중이고 예약 가능한 곳, 처방 기간, 주말 상담이 "
            "되는지도 알고 싶어서 경험 있으신 분들 의견 부탁드립니다."
        ),
        score_breakdown=pathfinder_context.copy(),
        **common,
    )

    filtered = viral_hunter.CommentableFilter().filter([axis_mismatch, axis_match])
    by_url = {target.url: target for target in filtered}

    assert set(by_url) == {"https://example.com/pathfinder-axis-skin"}
    assert axis_mismatch.comment_status == "filtered_out"
    assert axis_mismatch.score_breakdown["final_reject_reason"] == "off_domain"
    match_breakdown = by_url["https://example.com/pathfinder-axis-skin"].score_breakdown
    mismatch_breakdown = axis_mismatch.score_breakdown
    assert match_breakdown["pathfinder_axis_fit_tier"] == "strong"
    assert mismatch_breakdown["pathfinder_axis_fit_tier"] == "mismatch"
    assert "pathfinder_axis_core_match" in match_breakdown["pathfinder_axis_fit_signals"]
    assert "pathfinder_axis_cross_axis_noise" in mismatch_breakdown["pathfinder_axis_fit_signals"]


def test_legion_history_adjustment_rewards_fresh_keywords():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    repeated_norm = PathfinderLegion._normalize_keyword_for_history("청주 다이어트")
    legion.diversity_profile = {
        "keyword_norms": {repeated_norm},
        "category_counts": Counter({"다이어트": 40, "피부/여드름": 2}),
        "intent_counts": Counter({"commercial": 40, "transactional": 2}),
        "viral_keyword_stats": {
            repeated_norm: {"total_count": 25, "revisit_rate": 0.8},
        },
    }

    repeated = legion._apply_history_novelty_adjustment(
        "청주 다이어트",
        100.0,
        "다이어트",
        "commercial",
    )
    fresh = legion._apply_history_novelty_adjustment(
        "청주 새살침 상담",
        100.0,
        "피부/여드름",
        "transactional",
    )

    assert fresh > repeated


def test_legion_expansion_keyword_selection_caps_category_bias():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    legion.collected = {}
    for i in range(5):
        keyword = f"diet {i}"
        legion.collected[keyword] = KeywordResult(
            keyword=keyword,
            search_volume=100,
            difficulty=20,
            opportunity=90,
            grade="A",
            category="diet",
            priority_score=100 - i,
            source="test",
        )
    for i in range(3):
        keyword = f"skin {i}"
        legion.collected[keyword] = KeywordResult(
            keyword=keyword,
            search_volume=100,
            difficulty=20,
            opportunity=90,
            grade="A",
            category="skin",
            priority_score=80 - i,
            source="test",
        )

    selected = legion._select_expansion_keywords({"A"}, limit=4, max_per_category=2)

    assert selected == ["diet 0", "diet 1", "skin 0", "skin 1"]


def test_legion_quality_guard_caps_low_confidence_kei_outlier():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, kei_grade, flags = legion._apply_quality_grade_guard(
        grade="S",
        kei_grade="S",
        search_volume=30,
        document_count=1,
        verification_score=45.0,
        source_signal_count=1,
        has_real_volume=True,
    )

    assert grade == "B"
    assert kei_grade == "B"
    assert "low_document_count" in flags


def test_legion_execution_fit_promotes_verified_community_longtail_to_s():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 98.0,
            "longtail_score": 96.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=94.0,
        source_signal_count=2,
        category="다이어트",
        community_signal=92.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=88.0,
        review_surface_score=0.0,
        availability_intent_score=52.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "S"
    assert "execution_fit_s_grade" in flags


def test_legion_execution_fit_promotes_booking_longtail_to_a_without_market_proof():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 95.0,
            "longtail_score": 95.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=30,
        verification_score=86.0,
        source_signal_count=1,
        category="체형교정",
        community_signal=0.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=88.0,
        review_surface_score=0.0,
        availability_intent_score=70.0,
        payment_coverage_score=60.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "A"
    assert "execution_fit_a_grade" in flags
    assert "execution_fit_s_grade" not in flags


def test_legion_execution_fit_promotes_skin_service_longtail_to_a():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 100.0,
            "longtail_score": 100.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=75.0,
        source_signal_count=1,
        category="피부/여드름",
        community_signal=0.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=74.0,
        review_surface_score=0.0,
        availability_intent_score=47.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "A"
    assert "execution_fit_a_grade" in flags


def test_legion_execution_fit_promotes_strategic_skin_booking_with_lower_verification():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 100.0,
            "longtail_score": 100.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=66.0,
        source_signal_count=1,
        category="피부/여드름",
        community_signal=0.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=74.0,
        review_surface_score=0.0,
        availability_intent_score=47.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "A"
    assert "execution_fit_a_grade" in flags
    assert "strategic_focus_axis_a_grade" in flags


def test_legion_execution_fit_promotes_strategic_diet_booking_longtail_to_a():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 100.0,
            "longtail_score": 100.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=30,
        verification_score=71.0,
        source_signal_count=1,
        category="다이어트",
        community_signal=0.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=88.0,
        review_surface_score=0.0,
        availability_intent_score=52.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "A"
    assert "strategic_focus_axis_a_grade" in flags


def test_legion_execution_fit_promotes_strategic_asymmetry_consultation_to_a():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 99.0,
            "longtail_score": 100.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=75.0,
        source_signal_count=1,
        category="안면비대칭",
        community_signal=0.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=81.0,
        content_actionability_score=86.5,
        local_surface_score=74.0,
        review_surface_score=0.0,
        availability_intent_score=47.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "A"
    assert "strategic_focus_axis_a_grade" in flags


def test_legion_execution_fit_keeps_broad_diet_community_keyword_below_a():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 83.4,
            "longtail_score": 75.5,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=240,
        verification_score=92.9,
        source_signal_count=1,
        category="다이어트",
        community_signal=79.6,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=68.0,
        content_actionability_score=61.4,
        local_surface_score=50.0,
        review_surface_score=0.0,
        availability_intent_score=0.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "B"
    assert "execution_fit_a_grade" not in flags


def test_legion_high_value_variants_frontload_strategic_focus_axes():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    variants = legion._build_high_value_longtail_variants(
        [
            "청주 여드름흉터",
            "청주 다이어트 한의원",
            "청주 안면비대칭",
        ],
        max_keywords=90,
    )

    by_category = Counter(legion.collector._detect_category(keyword) for keyword in variants)

    assert by_category["흉터/여드름흉터"] >= 10
    assert by_category["다이어트"] >= 10
    assert by_category["안면비대칭"] >= 10
    assert any("여드름흉터 한의원" in keyword and "비용" in keyword for keyword in variants)
    assert any("다이어트 한의원" in keyword and "상담" in keyword for keyword in variants)
    assert any("안면비대칭" in keyword and "예약" in keyword for keyword in variants)


def test_legion_execution_fit_does_not_promote_medical_ad_risk():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 98.0,
            "longtail_score": 96.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=94.0,
        source_signal_count=2,
        category="피부/여드름",
        community_signal=92.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=88.0,
        review_surface_score=0.0,
        availability_intent_score=52.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=45.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=[],
    )

    assert grade == "B"
    assert flags == []


def test_legion_execution_fit_keeps_safe_faq_below_s():
    legion = PathfinderLegion.__new__(PathfinderLegion)

    grade, flags = legion._promote_grade_for_execution_fit(
        "B",
        {
            "high_value_longtail": True,
            "business_value_score": 98.0,
            "longtail_score": 96.0,
            "hard_negative_intent": False,
        },
        has_real_volume=True,
        search_volume=20,
        verification_score=94.0,
        source_signal_count=2,
        category="교통사고",
        community_signal=92.0,
        conversion_signal=0.0,
        profile_action_signal=0.0,
        local_service_fit_score=95.0,
        content_actionability_score=100.0,
        local_surface_score=88.0,
        review_surface_score=0.0,
        availability_intent_score=0.0,
        payment_coverage_score=0.0,
        access_convenience_score=0.0,
        medical_ad_risk_score=0.0,
        reputation_risk_score=0.0,
        brand_intent_type="generic",
        quality_flags=["content_action:safe_faq_candidate"],
    )

    assert grade == "A"
    assert "execution_fit_s_grade" not in flags
    assert "execution_fit_a_grade" in flags


def test_legion_diversity_metrics_counts_actual_four_plus_longtails():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    results = [
        KeywordResult(
            keyword="청주 다이어트",
            search_volume=100,
            difficulty=20,
            opportunity=80,
            grade="B",
            category="다이어트",
            priority_score=80,
            source="test",
        ),
        KeywordResult(
            keyword="청주 다이어트 한약 비용",
            search_volume=80,
            difficulty=20,
            opportunity=80,
            grade="A",
            category="다이어트",
            priority_score=90,
            source="test",
        ),
        KeywordResult(
            keyword="청주 교통사고 입원 자동차보험 서류",
            search_volume=60,
            difficulty=20,
            opportunity=80,
            grade="A",
            category="교통사고",
            priority_score=95,
            source="test",
        ),
    ]

    metrics = legion._calculate_diversity_metrics(results)

    assert metrics["longtail_4plus_count"] == 2
    assert metrics["longtail_4plus_rate"] == round(2 / 3, 4)


def test_legion_diversity_rerank_promotes_underrepresented_aspect():
    legion = PathfinderLegion.__new__(PathfinderLegion)
    results = [
        KeywordResult(
            keyword=f"diet keyword {i}",
            search_volume=100,
            difficulty=20,
            opportunity=80,
            grade="B",
            category="diet",
            priority_score=100 - i,
            source="round4_intent",
            search_intent="commercial",
            verification_score=70,
        )
        for i in range(6)
    ]
    results.append(
        KeywordResult(
            keyword="scar keyword",
            search_volume=80,
            difficulty=25,
            opportunity=75,
            grade="B",
            category="skin",
            priority_score=92,
            source="round8_ai",
            search_intent="informational",
            verification_score=70,
        )
    )

    reranked = legion._rerank_for_diversity(results)
    top_four_categories = [result.category for result in reranked[:4]]

    assert "skin" in top_four_categories
    assert reranked[0].diversity_rank == 1


def test_ai_target_split_reserves_minority_category_floor():
    skin = "\ud53c\ubd80"
    asymmetry = "\ube44\ub300\uce6d/\uad50\uc815"

    targets = [
        ViralTarget(
            platform="kin",
            url=f"https://example.com/skin/{i}",
            title=f"skin {i}",
            category=skin,
            priority_score=1000 - i,
        )
        for i in range(12)
    ]
    targets += [
        ViralTarget(
            platform="kin",
            url=f"https://example.com/asymmetry/{i}",
            title=f"asymmetry {i}",
            category=asymmetry,
            priority_score=100 - i,
        )
        for i in range(5)
    ]
    targets.sort(key=lambda target: target.priority_score, reverse=True)

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(
        targets,
        top_n=10,
        category_min_quotas={asymmetry: 3},
    )

    selected_categories = [
        viral_hunter._ai_quota_category(target)
        for target in selected
    ]
    selected_urls = {target.url for target in selected}
    rest_urls = {target.url for target in rest}

    assert len(selected) == 10
    assert selected_categories.count("안면비대칭") == 3
    assert selected_urls.isdisjoint(rest_urls)


def test_ai_target_split_prefers_pathfinder_matched_category_for_body_axis():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/body-axis",
        title="강서동쪽 도수치료 잘하는곳 있나요",
        category="통증/디스크",
        matched_keyword_category="체형교정",
        priority_score=150,
    )

    assert viral_hunter._ai_quota_category(target) == "체형교정"
    assert viral_hunter._canonical_ai_category("통증/디스크") == "체형교정"


def test_viral_filter_domain_falls_back_to_pathfinder_category():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/scar-domain",
        title="청주 여드름흉터 상담 궁금합니다",
        matched_keywords=["청주 한의원 비용"],
        category="기타",
        matched_keyword_category="흉터/여드름흉터",
    )

    assert viral_hunter.CommentableFilter._keyword_domain(["청주 한의원 비용"]) == "general"
    assert viral_hunter.CommentableFilter._target_domain(target) == "scar_skin"


def test_ai_target_split_caps_dominant_skin_floor_and_uses_matched_category():
    targets = [
        ViralTarget(
            platform="kin",
            url=f"https://example.com/skin/{i}",
            title=f"skin {i}",
            category="기타",
            matched_keyword_category="흉터/여드름흉터",
            priority_score=1000 - i,
        )
        for i in range(12)
    ]
    targets += [
        ViralTarget(
            platform="kin",
            url=f"https://example.com/diet/{i}",
            title=f"diet {i}",
            category="다이어트",
            priority_score=100 - i,
        )
        for i in range(5)
    ]
    targets.sort(key=lambda target: target.priority_score, reverse=True)

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(targets, top_n=10)
    selected_categories = [viral_hunter._ai_quota_category(target) for target in selected]
    selected_urls = {target.url for target in selected}
    rest_urls = {target.url for target in rest}

    assert len(selected) == 10
    assert selected_categories.count("흉터/여드름흉터") == 6
    assert selected_categories.count("다이어트") == 4
    assert selected_urls.isdisjoint(rest_urls)


def test_ai_target_split_prefers_pathfinder_fit_inside_category_floor():
    weak_high_priority = ViralTarget(
        platform="kin",
        url="https://example.com/scar/weak-high-priority",
        title="scar weak high priority",
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=150,
        score_breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 42,
            "pathfinder_lens_fit_score": 40,
            "clinic_treatment_fit_score": 45,
            "worksite_efficiency_score": 45,
            "pathfinder_viral_readiness_score": 50,
            "pathfinder_content_actionability_score": 50,
        },
    )
    strong_lower_priority = ViralTarget(
        platform="kin",
        url="https://example.com/scar/strong-lower-priority",
        title="scar strong lower priority",
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=140,
        score_breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 92,
            "pathfinder_lens_fit_score": 88,
            "clinic_treatment_fit_score": 90,
            "worksite_efficiency_score": 86,
            "pathfinder_viral_readiness_score": 88,
            "pathfinder_content_actionability_score": 90,
        },
    )

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(
        [weak_high_priority, strong_lower_priority],
        top_n=1,
        category_min_quotas={"흉터/여드름흉터": 1},
    )

    assert selected == [strong_lower_priority]
    assert rest == [weak_high_priority]
    assert (
        viral_hunter._ai_target_selection_score(strong_lower_priority)
        > viral_hunter._ai_target_selection_score(weak_high_priority)
    )


def test_ai_target_split_uses_pathfinder_fit_for_global_fill_slots():
    high_priority_weak = ViralTarget(
        platform="kin",
        url="https://example.com/general/weak-high",
        title="weak high",
        category="기타",
        priority_score=130,
        score_breakdown={
            "pathfinder_axis_fit_score": 35,
            "pathfinder_lens_fit_score": 35,
            "clinic_treatment_fit_score": 35,
            "worksite_efficiency_score": 35,
        },
    )
    lower_priority_strong = ViralTarget(
        platform="kin",
        url="https://example.com/general/strong-low",
        title="strong low",
        category="기타",
        priority_score=120,
        score_breakdown={
            "pathfinder_axis_fit_score": 94,
            "pathfinder_lens_fit_score": 91,
            "clinic_treatment_fit_score": 89,
            "worksite_efficiency_score": 88,
            "pathfinder_viral_readiness_score": 90,
            "pathfinder_content_actionability_score": 90,
        },
    )

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(
        [high_priority_weak, lower_priority_strong],
        top_n=1,
        category_min_quotas={},
    )

    assert selected == [lower_priority_strong]
    assert rest == [high_priority_weak]


def test_ai_target_split_guarantees_available_signature_axes_before_large_floors():
    targets = []
    for category, prefix, base_score in (
        ("흉터/여드름흉터", "scar", 1000),
        ("피부/여드름", "skin", 950),
        ("교통사고", "traffic", 900),
    ):
        targets.extend(
            ViralTarget(
                platform="kin",
                url=f"https://example.com/{prefix}/{i}",
                title=f"{prefix} {i}",
                category=category,
                matched_keyword_category=category,
                priority_score=base_score - i,
                score_breakdown={"pathfinder_execution_lens": "review"},
            )
            for i in range(6)
        )
    targets.extend(
        [
            ViralTarget(
                platform="kin",
                url="https://example.com/asymmetry/rare",
                title="asymmetry rare",
                category="안면비대칭",
                matched_keyword_category="안면비대칭",
                priority_score=120,
                score_breakdown={"pathfinder_execution_lens": "review"},
            ),
            ViralTarget(
                platform="kin",
                url="https://example.com/diet/rare",
                title="diet rare",
                category="다이어트",
                matched_keyword_category="다이어트",
                priority_score=110,
                score_breakdown={"pathfinder_execution_lens": "review"},
            ),
        ]
    )
    targets.sort(key=lambda target: target.priority_score, reverse=True)

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(targets, top_n=6)
    selected_categories = [viral_hunter._ai_quota_category(target) for target in selected]
    selected_urls = {target.url for target in selected}
    rest_urls = {target.url for target in rest}

    assert "안면비대칭" in selected_categories
    assert "다이어트" in selected_categories
    assert selected_urls.isdisjoint(rest_urls)


def test_ai_target_split_preserves_pathfinder_lens_diversity_inside_category_floor():
    targets = [
        ViralTarget(
            platform="kin",
            url=f"https://example.com/scar/review/{i}",
            title=f"scar review {i}",
            category="흉터/여드름흉터",
            matched_keyword_category="흉터/여드름흉터",
            priority_score=1000 - i,
            score_breakdown={"pathfinder_execution_lens": "review"},
        )
        for i in range(8)
    ]
    targets += [
        ViralTarget(
            platform="kin",
            url="https://example.com/scar/cost",
            title="scar cost",
            category="흉터/여드름흉터",
            matched_keyword_category="흉터/여드름흉터",
            priority_score=120,
            score_breakdown={"pathfinder_execution_lens": "cost"},
        ),
        ViralTarget(
            platform="kin",
            url="https://example.com/scar/consultation",
            title="scar consultation",
            category="흉터/여드름흉터",
            matched_keyword_category="흉터/여드름흉터",
            priority_score=110,
            score_breakdown={"pathfinder_execution_lens": "consultation"},
        ),
        ViralTarget(
            platform="kin",
            url="https://example.com/diet/review",
            title="diet review",
            category="다이어트",
            priority_score=105,
            score_breakdown={"pathfinder_execution_lens": "review"},
        ),
    ]
    targets.sort(key=lambda target: target.priority_score, reverse=True)

    selected, rest = viral_hunter.split_ai_targets_with_category_floor(
        targets,
        top_n=5,
        category_min_quotas={"흉터/여드름흉터": 4},
    )

    scar_lenses = {
        viral_hunter._ai_target_execution_lens(target)
        for target in selected
        if viral_hunter._ai_quota_category(target) == "흉터/여드름흉터"
    }
    selected_urls = {target.url for target in selected}
    rest_urls = {target.url for target in rest}

    assert len(selected) == 5
    assert scar_lenses >= {"review", "cost", "consultation"}
    assert "https://example.com/scar/cost" in selected_urls
    assert "https://example.com/scar/consultation" in selected_urls
    assert selected_urls.isdisjoint(rest_urls)


def test_naver_multi_sort_collect_tracks_exposure_metadata():
    searcher = viral_hunter.NaverUnifiedSearch(delay=0, use_cache=False)

    def fake_fetch(platform, keyword, display=100, start=1, sort="date"):
        if start > 1:
            return []
        if sort == "sim":
            return [
                {
                    "link": "https://example.com/shared",
                    "title": "Shared top result",
                    "description": "청주 상담 질문 본문",
                    "postdate": "20260511",
                    "cafename": "test cafe",
                },
                {
                    "link": "https://example.com/sim-only",
                    "title": "Similarity only result",
                    "description": "청주 추천 질문 본문",
                    "postdate": "20260510",
                    "cafename": "test cafe",
                },
            ]
        if sort == "date":
            return [
                {
                    "link": "https://example.com/shared",
                    "title": "Shared recent result",
                    "description": "청주 상담 질문 최신 본문",
                    "postdate": "20260511",
                    "cafename": "test cafe",
                }
            ]
        return []

    searcher._api_fetch = fake_fetch
    targets = searcher._api_collect_multi_sort("cafe", "청주 상담", 10)
    by_url = {target.url: target for target in targets}

    assert set(by_url) == {"https://example.com/shared", "https://example.com/sim-only"}
    shared = by_url["https://example.com/shared"]
    assert shared.search_rank == 1
    assert shared.search_sort == "sim"
    assert shared.exposure_score > 0
    assert shared.sort_appearances == ["sim", "date"]


def test_viral_filter_scores_gyulim_skin_scar_worksite_fit():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/scar-fit",
        title="청주 여드름흉터 새살침 한의원 추천 부탁드려요",
        content_preview=(
            "청주에서 여드름흉터랑 패인흉터 때문에 새살침 상담 받아보려고 합니다. "
            "한의원 비용이나 예약 가능한 곳 아시는 분 추천 부탁드려요. "
            "직장인이라 주말 진료도 궁금합니다."
        ),
        matched_keywords=["청주 여드름흉터 한의원 추천"],
        category="피부",
        matched_keyword_grade="A",
        matched_keyword_priority=115,
        date_str="방금 전",
        comment_count=0,
        view_count=180,
    )

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert len(filtered) == 1
    breakdown = filtered[0].score_breakdown
    assert breakdown["clinic_treatment_fit_score"] >= 90
    assert breakdown["worksite_efficiency_score"] >= 90
    assert "gyulim_profile_match" in breakdown["clinic_treatment_fit_signals"]
    assert "unanswered_thread" in breakdown["worksite_efficiency_signals"]
    assert filtered[0].priority_score >= 120


def test_viral_filter_routes_sensitive_medication_advice_to_manual_review():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/pregnancy-diet-medication-advice",
        title="청주 임신 중 다이어트한약 복용해도 되나요",
        content_preview=(
            "임신 초기인데 체중이 너무 늘어서 청주에서 다이어트한약 상담을 알아보고 있습니다. "
            "한약을 복용해도 되는지, 계속 먹어도 되는지 궁금합니다. "
            "비용이나 예약 가능한 한의원보다 안전하게 상담받을 수 있는 곳을 찾고 있습니다."
        ),
        matched_keywords=["청주 다이어트한약 상담"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
        date_str="방금 전",
        comment_count=0,
        view_count=120,
    )

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert filtered == []
    assert target.comment_status == "manual_review"
    assert target.score_breakdown["manual_review"] == 1.0
    assert "medication_advice_request" in target.score_breakdown["reply_risk_flags"]


def test_viral_reply_risk_routes_drug_combination_and_acute_side_effect_to_human_only():
    F = viral_hunter.CommentableFilter
    target = ViralTarget(
        platform="kin",
        url="https://example.com/skin-drug-combination",
        title="청주 여드름 한약 항생제 같이 복용해도 되나요",
        content_preview=(
            "피부과 항생제를 먹고 있는데 청주 여드름 한의원 한약을 같이 복용해도 되는지 "
            "궁금합니다. 상담 전에 비슷한 경험 있으신 분 이야기를 듣고 싶습니다."
        ),
        matched_keywords=["청주 여드름 한의원 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )
    combo_text = f"{target.title} {target.content_preview}".lower()

    penalty, flags, human_only = F._assess_reply_risk(combo_text, target)

    assert human_only is True
    assert penalty <= -60
    assert "sensitive_medical" in flags
    assert "medication_advice_request" in flags

    side_effect = ViralTarget(
        platform="kin",
        url="https://example.com/diet-acute-side-effect",
        title="청주 다이어트한약 부작용 심장 두근거림",
        content_preview=(
            "다이어트한약을 먹고 심장 두근거림과 어지럼이 있는데 계속 먹어도 될까요? "
            "청주에서 어디에 상담해야 할지 궁금합니다."
        ),
        matched_keywords=["청주 다이어트한약 상담"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )
    acute_text = f"{side_effect.title} {side_effect.content_preview}".lower()

    _, acute_flags, acute_human_only = F._assess_reply_risk(acute_text, side_effect)

    assert acute_human_only is True
    assert "acute_side_effect" in acute_flags


def test_viral_reply_risk_keeps_general_side_effect_experience_as_non_human_only():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/diet-side-effect-experience",
        title="청주 다이어트한약 부작용 경험 궁금해요",
        content_preview=(
            "청주에서 다이어트한약 상담 받아보신 분들 중 부작용 경험이나 주의사항이 "
            "어땠는지 궁금합니다. 비용과 상담 후기도 같이 알고 싶습니다."
        ),
        matched_keywords=["청주 다이어트한약 후기"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    _, flags, human_only = viral_hunter.CommentableFilter._assess_reply_risk(
        f"{target.title} {target.content_preview}".lower(),
        target,
    )

    assert human_only is False
    assert "sensitive_medical" in flags
    assert "medication_advice_request" not in flags


def test_viral_filter_keeps_surgery_scar_when_new_skin_care_context_is_hanbang():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/surgery-scar-fit",
        title="청주 수술흉터 새살침 한의원 상담 가능한 곳 있나요",
        content_preview=(
            "피부과 레이저 말고 한의원에서 수술흉터랑 켈로이드 새살침 상담을 받아보고 싶어요. "
            "비용과 치료기간이 궁금하고, 청주에서 주말 상담 가능한 곳이 있을까요?"
        ),
        matched_keywords=["청주 수술흉터 새살침 상담"],
        category="피부",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="A",
        matched_keyword_priority=120,
        date_str="방금 전",
        comment_count=0,
        view_count=160,
    )

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert len(filtered) == 1
    breakdown = filtered[0].score_breakdown
    assert breakdown["clinic_treatment_fit_score"] >= 80
    assert "gyulim_profile_match" in breakdown["clinic_treatment_fit_signals"]
    assert filtered[0].comment_status == "pending"


def test_pathfinder_lens_fit_accepts_cost_seed_community_bridge_variant():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/cost-community-bridge",
        title="청주 여드름흉터 새살침 추천 부탁드려요",
        content_preview="금액 언급은 없지만 실제 경험이나 후기 있는 곳이 궁금합니다.",
        matched_keywords=["금천동 여드름흉터 비용", "금천동 여드름흉터 추천"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost_community:추천",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_lens_post_fit(
        target,
        platform=target.platform,
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert score >= 55
    assert tier in {"acceptable", "strong"}
    assert "pathfinder_lens_cost_community_bridge" in signals


def test_pathfinder_lens_fit_keeps_plain_cost_seed_mismatch_without_bridge_or_cost_term():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/cost-plain-mismatch",
        title="청주 여드름흉터 새살침 추천 부탁드려요",
        content_preview="실제 경험이나 후기 있는 곳이 궁금합니다.",
        matched_keywords=["금천동 여드름흉터 비용"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "community_base",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_lens_post_fit(
        target,
        platform=target.platform,
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert score < 50
    assert tier == "mismatch"
    assert "pathfinder_lens_cost_mismatch" in signals


def test_pathfinder_lens_fit_accepts_access_convenience_terms_as_availability():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/access-availability-fit",
        title="청주 여드름 한의원 주차 가능한 곳",
        content_preview=(
            "차로 가야 해서 주차랑 길찾기가 편한지 궁금합니다. "
            "엘리베이터도 있으면 좋겠어요."
        ),
        matched_keywords=["청주 여드름 한의원 주차 가능"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        score_breakdown={
            "pathfinder_execution_lens": "availability",
            "pathfinder_availability_intent_score": 62.0,
            "pathfinder_access_convenience_score": 84.0,
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_lens_post_fit(
        target,
        platform=target.platform,
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert score >= 75
    assert tier == "strong"
    assert "pathfinder_lens_availability_match" in signals


def test_pathfinder_axis_fit_rewards_source_specific_scar_context():
    source_keyword = "청주 수술흉터 새살침 상담"
    matching_target = ViralTarget(
        platform="kin",
        url="https://example.com/surgery-scar-specific",
        title="청주 수술흉터 새살침 후기 궁금합니다",
        content_preview="수술 흉터와 켈로이드 때문에 한의원 새살침 상담을 알아보고 있습니다.",
        matched_keywords=[source_keyword, "청주 수술흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
        },
    )
    broad_target = ViralTarget(
        platform="kin",
        url="https://example.com/general-acne-scar",
        title="청주 여드름흉터 새살침 후기 궁금합니다",
        content_preview="패인 여드름흉터와 여드름자국 때문에 한의원 상담을 알아보고 있습니다.",
        matched_keywords=[source_keyword, "청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
        },
    )

    matching_score, _, matching_signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        matching_target,
        domain="scar_skin",
        text=f"{matching_target.title} {matching_target.content_preview}".lower(),
    )
    broad_score, _, broad_signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        broad_target,
        domain="scar_skin",
        text=f"{broad_target.title} {broad_target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in matching_signals
    assert "pathfinder_axis_specific_context_missing" in broad_signals
    assert matching_score >= broad_score + 20


def test_pathfinder_axis_fit_matches_scar_source_specific_aliases():
    source_keyword = "청주 여드름자국 새살침 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/acne-mark-alias",
        title="청주 붉은자국 색소침착 새살침 상담 궁금합니다",
        content_preview=(
            "여드름 이후 붉은자국과 색소침착이 남아서 새살침으로 상담 가능한 "
            "한의원을 알아보고 있습니다."
        ),
        matched_keywords=[source_keyword, "청주 붉은자국 새살침 상담"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_scar:specific_여드름자국",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="scar_skin",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in signals
    assert "pathfinder_axis_specific_context_missing" not in signals
    assert score >= 70
    assert tier in {"acceptable", "strong"}


def test_pathfinder_axis_fit_matches_skin_wart_source_specific_aliases():
    source_keyword = "청주 편평사마귀 한의원 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/flat-wart-alias",
        title="청주 편평 사마귀 한의원 상담 궁금합니다",
        content_preview=(
            "얼굴에 편평 사마귀가 반복돼서 한방 치료나 한의원 상담 후기가 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 편평 사마귀 한의원 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_skin:specific_편평사마귀",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="scar_skin",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in signals
    assert "pathfinder_axis_specific_context_missing" not in signals
    assert score >= 70
    assert tier in {"acceptable", "strong"}


def test_pathfinder_axis_fit_matches_asymmetry_source_specific_aliases():
    cases = [
        (
            "청주 광대비대칭 한의원 상담",
            "청주 광대 좌우 차이 한의원 상담 궁금합니다",
            "광대 좌우 차이와 얼굴형 비대칭 때문에 한방 교정 상담을 알아보고 있습니다.",
        ),
        (
            "청주 좌우비대칭 한의원 상담",
            "청주 얼굴 좌우 차이 한의원 상담 궁금합니다",
            "얼굴 좌우 차이가 보여서 안면 교정이나 한의원 상담 후기가 궁금합니다.",
        ),
        (
            "청주 두상비대칭 한의원 상담",
            "청주 머리 비대칭 한의원 상담 궁금합니다",
            "머리 비대칭과 얼굴 균형 문제로 한방 교정 상담을 받아볼지 고민입니다.",
        ),
    ]

    for source_keyword, title, content_preview in cases:
        target = ViralTarget(
            platform="kin",
            url=f"https://example.com/asymmetry-source-alias-{len(source_keyword)}",
            title=title,
            content_preview=content_preview,
            matched_keywords=[source_keyword, title],
            category="안면비대칭",
            matched_keyword_category="안면비대칭",
            score_breakdown={
                "pathfinder_source_keyword": source_keyword,
                "pathfinder_query_variant": "axis_asymmetry:specific",
            },
        )

        score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
            target,
            domain="asymmetry",
            text=f"{target.title} {target.content_preview}".lower(),
        )

        assert "pathfinder_axis_specific_context_match" in signals
        assert "pathfinder_axis_specific_context_missing" not in signals
        assert "pathfinder_axis_specific_context_strict_gap" not in signals
        assert score >= 70
        assert tier in {"acceptable", "strong"}


def test_pathfinder_axis_fit_does_not_treat_generic_wart_as_flat_wart_source_context():
    source_keyword = "청주 편평사마귀 한의원 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/generic-wart-not-flat-wart",
        title="청주 사마귀 치료 한의원 상담 궁금합니다",
        content_preview=(
            "손에 난 사마귀 치료 때문에 한방 치료나 한의원 상담 후기가 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 사마귀 치료 한의원 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_skin:specific_편평사마귀",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="scar_skin",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_missing" in signals
    assert "pathfinder_axis_specific_context_strict_gap" in signals
    assert "pathfinder_axis_specific_context_match" not in signals
    assert score < 75
    assert tier in {"weak", "acceptable", "mismatch"}


def test_pathfinder_axis_fit_ignores_negated_scar_source_specific_context():
    source_keyword = "청주 수술흉터 새살침 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/negated-surgery-scar-context",
        title="청주 여드름흉터 새살침 상담 궁금합니다",
        content_preview=(
            "수술흉터는 아니고 패인 여드름흉터와 여드름자국 때문에 "
            "새살침 한의원 상담 후기가 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 여드름흉터 새살침 상담"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="scar_skin",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_missing" in signals
    assert "pathfinder_axis_specific_context_strict_gap" in signals
    assert "pathfinder_axis_specific_context_match" not in signals
    assert score < 75
    assert tier in {"weak", "acceptable", "mismatch"}


def test_pathfinder_axis_fit_distinguishes_partial_multi_intent_traffic_context():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    full_target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-admission-insurance",
        title="청주 교통사고 입원 자동차보험 한의원 추천",
        content_preview="교통사고 후 입원 치료와 자동차보험 서류 상담 가능한 한의원이 궁금합니다.",
        matched_keywords=[source_keyword, "청주 교통사고 입원 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )
    partial_target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-admission-only",
        title="청주 교통사고 입원 한의원 추천",
        content_preview="교통사고 후 입원 가능한 한방병원이 있는지 궁금합니다.",
        matched_keywords=[source_keyword, "청주 교통사고 입원 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    full_score, _, full_signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        full_target,
        domain="traffic",
        text=f"{full_target.title} {full_target.content_preview}".lower(),
    )
    partial_score, _, partial_signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        partial_target,
        domain="traffic",
        text=f"{partial_target.title} {partial_target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in full_signals
    assert "pathfinder_axis_specific_context_complete" in full_signals
    assert "pathfinder_axis_specific_context_partial" in partial_signals
    assert "pathfinder_axis_specific_context_match" not in partial_signals
    assert full_score > partial_score


def test_pathfinder_axis_fit_matches_traffic_source_specific_aliases():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-insurance-alias",
        title="청주 교통사고 입원 자보 처리 한의원 추천",
        content_preview=(
            "교통사고 입원 치료를 알아보는 중이고 자보 처리와 보험 접수, "
            "서류 상담까지 가능한 곳이 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 입원 자보 처리"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in signals
    assert "pathfinder_axis_specific_context_complete" in signals
    assert "pathfinder_axis_specific_context_partial" not in signals
    assert score >= 75
    assert tier == "strong"


def test_pathfinder_axis_fit_ignores_labeled_kin_answer_source_specific_context():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/kin-answer-only-traffic-source-context",
        title="청주 교통사고 통증 한의원 추천 부탁드립니다",
        content_preview=(
            "교통사고 후 목 통증 때문에 청주에서 한의원 치료 가능한 곳이 궁금합니다. "
            "[기존답변1] 입원 치료와 자동차보험 서류 접수까지 가능한 한방병원을 확인해보세요."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 통증 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
    )
    reject_reason = viral_hunter.CommentableFilter._pathfinder_fit_reject_reason(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
        axis_fit_score=score,
        axis_fit_tier=tier,
        lens_fit_score=80.0,
        lens_fit_tier="strong",
    )

    assert "pathfinder_axis_specific_context_strict_gap" in signals
    assert "pathfinder_axis_specific_context_match" not in signals
    assert score < 75
    assert reject_reason == "source_context_mismatch"


def test_pathfinder_axis_fit_ignores_leading_labeled_kin_answer_source_context():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/kin-leading-answer-only-source-context",
        title="청주 교통사고 통증 한의원 추천 부탁드립니다",
        content_preview=(
            "[기존답변1] 입원 치료와 자동차보험 서류 접수까지 가능한 "
            "한방병원을 확인해보세요."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 통증 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    user_text = viral_hunter.CommentableFilter._user_need_text(target)
    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "입원" not in user_text
    assert "자동차보험" not in user_text
    assert "pathfinder_axis_specific_context_strict_gap" in signals
    assert "pathfinder_axis_specific_context_match" not in signals
    assert score < 75
    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_pathfinder_axis_fit_keeps_labeled_kin_question_source_specific_context():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/kin-question-traffic-source-context",
        title="청주 교통사고 입원 자동차보험 서류 한의원 추천",
        content_preview=(
            "교통사고 입원 치료를 알아보고 있고 자동차보험 서류 접수 가능한 "
            "청주 한의원이 궁금합니다. "
            "[기존답변1] 통원 치료 위주로도 상담 가능합니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 입원 자동차보험 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_match" in signals
    assert "pathfinder_axis_specific_context_complete" in signals
    assert "pathfinder_axis_specific_context_strict_gap" not in signals
    assert score >= 75
    assert tier == "strong"


def test_pathfinder_axis_fit_penalizes_strict_traffic_source_context_gap():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-admission-without-insurance-context",
        title="청주 교통사고 입원 한의원 추천",
        content_preview=(
            "교통사고 후 입원 가능한 한방병원이 있는지 궁금합니다. "
            "목과 어깨 통증 치료를 받아보고 싶습니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 입원 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_query_variant": "axis_traffic:specific_입원",
        },
    )

    score, tier, signals = viral_hunter.CommentableFilter._pathfinder_axis_post_fit(
        target,
        domain="traffic",
        text=f"{target.title} {target.content_preview}".lower(),
    )

    assert "pathfinder_axis_specific_context_partial" in signals
    assert "pathfinder_axis_specific_context_strict_gap" in signals
    assert "pathfinder_axis_specific_context_match" not in signals
    assert score < 75
    assert tier in {"weak", "acceptable", "mismatch"}


def test_viral_final_gate_rejects_strict_traffic_source_context_gap():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/traffic-source-context-gap",
        title="청주 교통사고 입원 한의원 추천 부탁드려요",
        content_preview=(
            "교통사고 후 입원 가능한 곳을 찾고 있습니다. "
            "목 통증 치료를 받아보고 싶은데 추천 부탁드립니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 입원 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 68.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 76.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_keeps_strict_traffic_source_context_alias_match():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/traffic-source-context-alias-match",
        title="청주 교통사고 입원 자보 처리 한의원 추천 부탁드려요",
        content_preview=(
            "교통사고 입원 치료를 알아보는 중이고 자보 처리와 보험 접수, "
            "서류 상담까지 가능한 곳이 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 입원 자보 처리"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 88.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_strict_scar_source_context_gap():
    source_keyword = "청주 수술흉터 새살침 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/surgery-scar-source-context-gap",
        title="청주 여드름흉터 새살침 상담 궁금합니다",
        content_preview=(
            "패인 여드름흉터와 여드름자국 때문에 새살침 상담을 알아보고 있습니다. "
            "얼굴에 남은 여드름 자국 위주로 후기가 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 여드름흉터 새살침 상담"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 66.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_rejects_negated_scar_source_context():
    source_keyword = "청주 수술흉터 새살침 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/negated-surgery-scar-final-gate",
        title="청주 여드름흉터 새살침 상담 궁금합니다",
        content_preview=(
            "수술흉터는 아니고 패인 여드름흉터와 여드름자국 때문에 "
            "청주 한의원 새살침 상담 후기를 찾고 있습니다."
        ),
        matched_keywords=[source_keyword, "청주 여드름흉터 새살침 상담"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 74.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_rejects_strict_skin_wart_source_context_gap():
    source_keyword = "청주 편평사마귀 한의원 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/flat-wart-source-context-gap",
        title="청주 여드름흉터 새살침 상담 궁금합니다",
        content_preview=(
            "패인 여드름흉터와 여드름자국 때문에 새살침 상담을 알아보고 있습니다. "
            "한의원 후기가 궁금합니다."
        ),
        matched_keywords=[source_keyword, "청주 여드름흉터 새살침 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 70.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 78.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_rejects_generic_wart_for_flat_wart_source_context():
    source_keyword = "청주 편평사마귀 한의원 상담"
    target = ViralTarget(
        platform="kin",
        url="https://example.com/generic-wart-flat-wart-source-gap",
        title="청주 사마귀 치료 한의원 상담 궁금합니다",
        content_preview=(
            "손에 난 사마귀 치료 때문에 청주 한의원 상담 후기가 궁금합니다. "
            "편평하게 번지는 얼굴 사마귀는 아닙니다."
        ),
        matched_keywords=[source_keyword, "청주 사마귀 치료 한의원 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 72.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 78.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_rejects_negated_traffic_source_context():
    source_keyword = "청주 교통사고 입원 자동차보험 서류"
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/negated-traffic-admission-final-gate",
        title="청주 교통사고 통원 자보 한의원 추천 부탁드려요",
        content_preview=(
            "교통사고 후 입원은 안 하고 통원 치료를 알아보고 있습니다. "
            "자보 처리와 보험 접수 가능한 한의원 추천 부탁드립니다."
        ),
        matched_keywords=[source_keyword, "청주 교통사고 통원 자보 한의원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_source_keyword": source_keyword,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_axis_fit_score": 72.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 78.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "source_context_mismatch"


def test_viral_final_gate_rejects_scar_seed_when_post_is_only_active_acne():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/scar-seed-active-acne-only",
        title="청주 여드름 한의원 추천 부탁드려요",
        content_preview=(
            "성인여드름이 계속 올라와서 한약이나 약침 상담 가능한 한의원을 찾고 있습니다. "
            "현재 올라오는 여드름 치료와 재발 관리 후기가 궁금합니다."
        ),
        matched_keywords=["금천동 여드름흉터 비용", "청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_query_variant": "axis_scar:새살침후기",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 44.0,
            "pathfinder_axis_fit_tier": "mismatch",
            "pathfinder_lens_fit_score": 72.0,
            "pathfinder_lens_fit_tier": "acceptable",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_scar_seed_with_user_scar_anchor():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/scar-seed-real-scar-question",
        title="청주 여드름흉터 새살침 상담 받아보신 분",
        content_preview=(
            "패인흉터랑 여드름자국 때문에 청주에서 새살침 한의원 상담을 알아보고 있습니다. "
            "비용이나 치료기간 후기가 궁금해서 경험 있으신 분 추천 부탁드려요."
        ),
        matched_keywords=["금천동 여드름흉터 비용", "청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_query_variant": "axis_scar:새살침후기",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 82.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 76.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_skin_companion_without_skin_anchor():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/skin-companion-general-clinic",
        title="청주 한의원 추천 부탁드립니다",
        content_preview=(
            "청주에서 야간진료 가능한 한의원 추천 부탁드립니다. "
            "감기랑 피로 상담을 받아보고 싶습니다."
        ),
        matched_keywords=["청주 여드름 한의원 비용", "청주 피부질환 한의원 추천"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_skin:피부질환추천",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 40.0,
            "pathfinder_axis_fit_tier": "mismatch",
            "pathfinder_lens_fit_score": 74.0,
            "pathfinder_lens_fit_tier": "acceptable",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_filter_rejects_kin_question_with_ad_answer_snippet():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/kin-answer-ad",
        title="청주교통사고한의원 어깨통증 치료 될까요??",
        content_preview=(
            "청주에서 사고가 난 뒤 어깨통증이 심해서 한의원 치료가 되는지 궁금합니다. "
            "방치하면 만성이 되기 쉬우니 초기에 한의원에서 추나나 약침 치료를 받으시는 게 좋습니다. "
            "청주 성안길 쪽 규림한의원이 교통사고 진료도 꼼꼼하고 친절하게 잘 봐주시는 편이니 "
            "비용 부담 없이 자동차보험으로 상담 한번 받아보세요."
        ),
        matched_keywords=["청주 교통사고 한의원"],
        category="교통사고",
        matched_keyword_grade="A",
        matched_keyword_priority=100,
        date_str="방금 전",
        comment_count=0,
        view_count=150,
    )

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert filtered == []
    assert target.comment_status == "filtered_out_ad"
    assert target.score_breakdown["ad_signal_score"] >= 4
    assert "answer_snippet_ad" in target.score_breakdown["ad_signals"]


def test_viral_final_gate_does_not_reject_plain_user_question():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/plain-question",
        title="청주 교통사고 한의원 치료 받고 싶어요",
        content_preview=(
            "저는 청주에서 교통사고가 난 뒤 목이랑 어깨 통증이 계속 있어서 "
            "한의원 치료를 받고 싶어요. 자동차보험 적용되는지랑 입원 가능한 곳이 있는지 "
            "아시는 분 알려주세요."
        ),
        matched_keywords=["청주 교통사고 한의원"],
        category="교통사고",
        matched_keyword_grade="A",
        matched_keyword_priority=100,
        date_str="방금 전",
        comment_count=0,
        view_count=120,
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_distant_region_title():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/distant-region",
        title="대전안면비대칭교정 제대로 알고 시작하자",
        content_preview=(
            "대전 유성에서 안면비대칭 교정 상담 가능한 곳을 찾고 있습니다. "
            "턱관절이랑 얼굴비대칭 때문에 한의원 치료 후기가 궁금합니다."
        ),
        matched_keywords=["봉명동 안면비대칭"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_local_venue_anchor_detection():
    """청주 로컬 카페명은 지역 앵커, 인접/타지역/빈값/블로그는 아님."""
    F = viral_hunter.CommentableFilter

    def cafe(name):
        return ViralTarget(platform="cafe", url="x", title="t", author=name)

    assert F._has_local_venue_anchor(cafe("청주맘스캠프 (충북맘,청주맘카페)")) is True
    assert F._has_local_venue_anchor(cafe("러브인오송")) is True
    assert F._has_local_venue_anchor(cafe("오창맘들 모여라")) is True
    assert F._has_local_venue_anchor(cafe("복대동 사는 사람들")) is True
    assert F._has_local_venue_anchor(cafe("세종맘카페")) is False     # 인접이나 청주 본권 아님
    assert F._has_local_venue_anchor(cafe("강남언니")) is False
    assert F._has_local_venue_anchor(cafe("")) is False
    # 블로그 bloggername은 업체 SEO 비중이 높아 앵커로 쓰지 않는다
    assert F._has_local_venue_anchor(
        ViralTarget(platform="blog", url="x", title="t", author="청주맘일기")
    ) is False


def test_distant_local_target_respects_local_venue():
    """로컬 카페 글은 본문의 우연한 타지역 언급으로 false-kill 되지 않는다.
    단, 제목이 명시적으로 타지역을 타겟하면 카페가 로컬이어도 킬 유지."""
    F = viral_hunter.CommentableFilter
    # 로컬 카페 + 본문 우연 타지역 → keep
    assert F._is_distant_local_target(
        "여드름흉터 고민", "여드름흉터 고민 강남언니 앱에서 봤는데", local_venue=True
    ) is False
    # 로컬 카페여도 제목이 명시적 타지역 타겟 → kill
    assert F._is_distant_local_target("강남 성형외과 추천", "강남 성형외과 추천", local_venue=True) is True
    # 비로컬 카페 + 본문 타지역 → kill (회귀 방지)
    assert F._is_distant_local_target(
        "여드름흉터 고민", "여드름흉터 고민 강남 압구정 피부과", local_venue=False
    ) is True


def test_region_fit_signal_credits_local_venue_without_double_count():
    """카페 로컬 앵커는 본문에 지역이 없을 때만 가산(중복 가산 방지)."""
    F = viral_hunter.CommentableFilter
    base, _ = F._region_fit_signal("여드름 흉터 자국 고민이에요", local_venue=False)
    boosted, signals = F._region_fit_signal("여드름 흉터 자국 고민이에요", local_venue=True)
    assert boosted > base
    assert "local_venue_anchor" in signals
    # 텍스트에 이미 청주가 있으면 venue 가산을 중복으로 더하지 않는다
    with_text, _ = F._region_fit_signal("청주 여드름 흉터 고민", local_venue=False)
    with_both, _ = F._region_fit_signal("청주 여드름 흉터 고민", local_venue=True)
    assert with_text == with_both


def test_region_gate_ignores_ambiguous_cheongju_stem_false_positive():
    F = viral_hunter.CommentableFilter
    text = (
        "국민청원에 올리고 싶을 정도로 여드름흉터가 고민입니다. "
        "상당히 오래된 패인흉터라 한의원 새살침 후기와 비용이 궁금해요."
    )

    assert F._contains_region_terms(text, F.REGION_KEYWORDS) is False
    assert F._has_ambiguous_region_false_positive(text) is True

    target = ViralTarget(
        platform="kin",
        url="https://example.com/petition-not-cheongju",
        title="여드름흉터 새살침 후기 궁금합니다",
        content_preview=text,
        matched_keywords=["청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    assert F.final_reject_reason(target) == "region_mismatch"


def test_region_gate_keeps_unambiguous_cheongju_district_context():
    F = viral_hunter.CommentableFilter
    valid_text = "청주 상당구에서 수술흉터 새살침 상담 받아보신 분 후기 궁금합니다."
    shorthand_text = "청주 서원 여드름흉터 한의원 비용 궁금합니다."

    assert F._contains_region_terms(valid_text, F.REGION_KEYWORDS) is True
    assert F._contains_region_terms(shorthand_text, F.REGION_KEYWORDS) is True

    target = ViralTarget(
        platform="kin",
        url="https://example.com/cheongju-district-scar",
        title="청주 상당구 수술흉터 새살침 후기 궁금합니다",
        content_preview=valid_text,
        matched_keywords=["청주 수술흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    assert F.final_reject_reason(target) is None


def test_viral_final_gate_keeps_local_cafe_with_incidental_distant_mention():
    """청주 로컬 카페 글이 본문에 우연히 타지역을 언급해도 region_mismatch로 죽지 않고,
    동일 글이 비로컬 카페면 타지역 언급으로 죽는다(카페 정체성이 지역 앵커)."""
    F = viral_hunter.CommentableFilter

    def asymmetry_post(author):
        return ViralTarget(
            platform="cafe", url="https://cafe.naver.com/x/1",
            title="턱이 자꾸 돌아가고 얼굴비대칭이 심해서 한의원 추천 받고싶어요",
            content_preview=(
                "얼굴 비뚤어진게 너무 스트레스에요. 친구는 강남까지 다닌다는데 "
                "저는 가까운 데서 받고싶어요 후기 궁금해요"
            ),
            author=author, category="안면비대칭",
            matched_keyword_category="안면비대칭", matched_keyword_grade="B",
        )

    assert F.final_reject_reason(asymmetry_post("청주맘스캠프 (충북맘,청주맘카페)")) != "region_mismatch"
    assert F.final_reject_reason(asymmetry_post("전국여성수다카페")) == "region_mismatch"


def test_viral_final_gate_rejects_more_distant_skin_region_title():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/distant-skin-region",
        title="평택 여드름흉터 한의원 장안동 소중한 내몸",
        content_preview=(
            "평택 장안동에서 여드름흉터 한의원 상담 가능한 곳을 찾고 있습니다. "
            "패인흉터와 새살침 치료 후기가 궁금합니다."
        ),
        matched_keywords=["금천동 여드름흉터"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_viral_final_gate_rejects_cheonan_asan_micro_region_titles():
    for title in [
        "탕정면 자동차보험한의원 지겨웠다면",
        "쌍용동 교통사고치료 조기에",
        "신불당동 교통사고보험한의원 나를",
    ]:
        target = ViralTarget(
            platform="cafe",
            url=f"https://example.com/{title}",
            title=title,
            content_preview=(
                "교통사고 후유증과 자동차보험 한의원 치료를 안내하는 글입니다. "
                "청주 권역 후보로 저장되면 안 되는 천안/아산권 지역 글입니다."
            ),
            matched_keywords=["봉명동 교통사고 한의원 치료비"],
            category="교통사고",
            matched_keyword_category="교통사고",
            matched_keyword_grade="A",
        )

        assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_viral_final_gate_rejects_off_area_asymmetry_title():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/off-area-asymmetry",
        title="아산 눈떨림 어떻게",
        content_preview=(
            "아산에서 눈떨림과 얼굴비대칭 때문에 한의원 상담을 알아보고 있습니다. "
            "턱관절이랑 안면비대칭 교정 후기가 궁금합니다."
        ),
        matched_keywords=["봉명동 안면비대칭"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_viral_final_gate_rejects_ambiguous_neighborhood_from_distant_city():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/distant-ambiguous-neighborhood",
        title="봉명동 다이어트 어디서?",
        content_preview=(
            "천안 사시는 분 중에 다이어트 관리 받을 곳 아시면 추천좀요. "
            "봉명동 쪽에 사는데 비만클리닉이나 한의원 같은 곳이 있을까요?"
        ),
        matched_keywords=["봉명동 다이어트"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_viral_final_gate_rejects_cosmetic_procedure_for_asymmetry_axis():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-cosmetic",
        title="청주 안면비대칭 쥬베룩볼륨 상담",
        content_preview=(
            "청주에서 얼굴 볼륨과 안면비대칭이 고민이라 쥬베룩이나 필러 시술 "
            "잘하는 피부과를 알아보고 있습니다."
        ),
        matched_keywords=["청주 안면비대칭"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_asymmetry_brow_esthetic_and_dental_noise():
    brow = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-brow-tattoo",
        title="청주눈썹문신 추천좀",
        content_preview=(
            "얼굴 비대칭 때문에 눈썹문신이나 반영구 잘하는 뷰티샵을 알아보고 있어요. "
            "자연스럽게 맞춰주는 곳 추천 부탁드립니다."
        ),
        matched_keywords=["청주 얼굴형 안면비대칭 상담"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )
    esthetic = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-esthetic",
        title="청주 윤곽관리 받고 얼굴형 정리해보신분",
        content_preview=(
            "에스테틱에서 윤곽관리나 경락으로 작은얼굴 관리 받아본 분 후기 궁금합니다. "
            "한의원 치료 상담은 아직 생각 안 하고 있어요."
        ),
        matched_keywords=["청주 턱비대칭 예약"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )
    dental = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-dental",
        title="청주교정추천 반듯한 배열을 지키기 위해",
        content_preview=(
            "치아 배열이랑 치열교정 때문에 교정치과를 찾고 있습니다. "
            "인비절라인 상담받아보신 분 계신가요?"
        ),
        matched_keywords=["청주 턱비대칭 예약"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(brow) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(esthetic) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(dental) == "off_domain"


def test_viral_final_gate_keeps_asymmetry_tmj_hanbang_question():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-tmj-hanbang",
        title="청주 턱관절 안면비대칭 한의원 추천",
        content_preview=(
            "턱관절 통증이랑 얼굴비대칭 때문에 추나 상담을 받아보고 싶습니다. "
            "청주에서 안면비대칭 교정 상담 괜찮았던 한의원 추천 부탁드려요."
        ),
        matched_keywords=["청주 턱관절 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_keeps_asymmetry_patient_expression_aliases():
    cases = [
        (
            "청주 광대 좌우 차이 한의원 상담 궁금합니다",
            "광대 좌우 차이와 얼굴형 비대칭 때문에 한방 교정 상담 받아보신 분 계신가요?",
            "청주 광대비대칭 한의원 상담",
        ),
        (
            "청주 얼굴 좌우 차이 한의원 상담 궁금합니다",
            "얼굴 좌우 차이가 보여서 안면 교정이나 한의원 상담 후기가 궁금합니다.",
            "청주 좌우비대칭 한의원 상담",
        ),
        (
            "청주 머리 비대칭 한의원 상담 궁금합니다",
            "머리 비대칭과 얼굴 균형 문제로 한방 교정 상담 받아보신 분 계신가요?",
            "청주 두상비대칭 한의원 상담",
        ),
    ]

    for index, (title, content_preview, source_keyword) in enumerate(cases):
        target = ViralTarget(
            platform="cafe",
            url=f"https://example.com/asymmetry-patient-expression-{index}",
            title=title,
            content_preview=content_preview,
            matched_keywords=[source_keyword],
            category="안면비대칭",
            matched_keyword_category="안면비대칭",
            matched_keyword_grade="B",
        )

        assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_cross_axis_redeems_diet_question_from_asymmetry_seed():
    # 2026-06-12 교차축 구제: 비대칭 시드가 찾은 글이라도 글 자체가 다른 핵심
    # 진료축(다이어트)의 유효한 사용자 질문이면 cafe/kin에서는 살린다.
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-seed-broad-clinic",
        title="청주다이어트한약 먹으면서 감량 성공하신 분?",
        content_preview=(
            "청주에서 다이어트한약을 먹고 감량 상담을 받아본 분들의 "
            "한의원 후기가 궁금합니다."
        ),
        matched_keywords=["청주 턱관절 한의원 상담 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None

    # 같은 글이 blog로 들어오면 교차축 구제가 없다 (업체 SEO 위험).
    blog_variant = ViralTarget(
        platform="blog",
        url="https://example.com/asymmetry-seed-broad-clinic-blog",
        title="청주다이어트한약 먹으면서 감량 성공하신 분?",
        content_preview=(
            "청주에서 다이어트한약을 먹고 감량 상담을 받아본 분들의 "
            "한의원 후기가 궁금합니다."
        ),
        matched_keywords=["청주 턱관절 한의원 상담 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(blog_variant) == "domain_mismatch"


def test_viral_final_gate_rejects_asymmetry_conversion_lens_when_axis_fit_is_low():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/asymmetry-low-axis-availability",
        title="청주 한의원 예약 가능한 곳",
        content_preview=(
            "청주에서 야간진료나 당일 예약 가능한 한의원 상담을 알아보고 있습니다. "
            "어디가 괜찮은지 경험 있으신 분 알려주세요."
        ),
        matched_keywords=["청주 턱비대칭 예약"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_execution_lens": "availability",
            "pathfinder_axis_fit_score": 42.0,
            "pathfinder_axis_fit_tier": "mismatch",
            "pathfinder_lens_fit_score": 84.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "domain_mismatch"


def test_viral_final_gate_rejects_asymmetry_companion_without_user_axis_anchor():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/asymmetry-companion-broad-clinic",
        title="충북 음성 근처 한의원 추천",
        content_preview=(
            "충북 음성 근처에서 일반 한의원 추천을 찾고 있습니다. "
            "피로와 한약 상담이 가능한 곳을 알아보고 있어 해당 진료축 상담은 아닙니다."
        ),
        matched_keywords=["봉명동 턱비대칭 한의원 비용", "청주 턱관절 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_asymmetry:턱관절추천",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 84.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_asymmetry_companion_when_axis_appears_only_in_answer_snippet():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/asymmetry-companion-answer-snippet-noise",
        title="청주에 담적치료 병원이나 한의원 추천해주세요",
        content_preview=(
            "담적치료를 잘하는 한의원이나 병원 추천 부탁드립니다. "
            "소화계통 상담을 알아보는 글이고 식사 후 더부룩함과 명치 답답함이 고민입니다. "
            "평소 속이 자주 불편해서 생활관리와 약 상담 경험을 듣고 싶은 상황입니다. "
            "위장 관련 검사를 어디서 받아야 할지와 한약 상담 후기를 중심으로 묻는 글입니다. "
            "최근 식사량이 줄고 트림이 잦아져서 가까운 곳을 찾고 있습니다. "
            "답변 스니펫 뒤쪽에 턱관절이나 얼굴 비대칭 표현이 섞여 있습니다."
        ),
        matched_keywords=["봉명동 턱비대칭 한의원 비용", "청주 턱관절 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_asymmetry:턱관절추천",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 72.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_asymmetry_kin_answer_axis_near_snippet_start():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/asymmetry-companion-kin-answer-axis-near-start",
        title="청주에 담적치료 병원이나 한의원 추천해주세요",
        content_preview=(
            "담적치료를 잘하는 한의원이나 병원 추천 부탁드립니다. "
            "소화계통은 자율신경의 통제하에 확장과 수축이 정상으로 움직이지 않으면 불편합니다. "
            "답변에는 턱관절, 얼굴 비대칭 표현이 섞여 있지만 사용자의 질문은 위장 담적 상담입니다."
        ),
        matched_keywords=["봉명동 턱비대칭 한의원 비용", "청주 턱관절 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_asymmetry:턱관절추천",
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 72.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 80.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_kin_labeled_answer_is_not_used_as_user_axis_anchor():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/asymmetry-labeled-answer-axis-only",
        title="청주에 담적치료 한의원 추천해주세요",
        content_preview=(
            "담적치료를 잘하는 한의원 추천 부탁드립니다. "
            "소화가 안 되고 명치가 답답해서 한약 상담 경험을 듣고 싶습니다. "
            "[기존답변1] 턱관절 안면비대칭 교정은 한의원 추나와 교정 상담으로 접근할 수 있습니다. "
            "청주 안면비대칭 비용과 예약도 확인하세요."
        ),
        matched_keywords=["청주 턱관절 안면비대칭 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_asymmetry:턱관절비대칭추천",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 80.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 78.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    user_text = viral_hunter.CommentableFilter._user_need_text(target)

    assert "[기존답변1]" not in user_text
    assert "턱관절" not in user_text
    assert viral_hunter.CommentableFilter._has_user_axis_anchor(
        target,
        domain="asymmetry",
        category="안면비대칭",
    ) is False
    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_conversion_lens_mismatch():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/diet-lens-mismatch",
        title="청주 다이어트한약 복용 루틴 정리",
        content_preview=(
            "다이어트한약을 먹을 때 식단관리와 운동 루틴을 어떻게 잡는지 정리해보려 합니다. "
            "감량 기록과 생활관리 중심으로 찾아보고 있습니다."
        ),
        matched_keywords=["청주 다이어트 한약 비용"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 82.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 33.0,
            "pathfinder_lens_fit_tier": "weak",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "lens_mismatch"


def test_viral_final_gate_rejects_diet_injection_clinic_without_hanbang_intent():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/diet-injection-clinic-noise",
        title="청주다이어트 미하이 비만클리닉 어때요?",
        content_preview=(
            "지방분해주사, 클라투, 바디톡신 같은 관리로 다이어트에 시너지 효과를 "
            "보고 싶어서 예약 가능한 비만클리닉을 찾고 있습니다."
        ),
        matched_keywords=["청주다이어트주사 예약"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_diet_hanbang_question_after_injection_attempts():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/diet-hanbang-after-injections",
        title="청주 다이어트한약 상담 받아보신 분",
        content_preview=(
            "식단도 해보고 다이어트 주사도 맞아봤지만 체중이 잘 안 빠져서 "
            "청주에서 한의원 다이어트한약 상담을 받아보려고 합니다. "
            "한약 비용이나 부작용 경험 있으신 분 추천 부탁드려요."
        ),
        matched_keywords=["청주다이어트주사 예약"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_kin_multibranch_footer_region_noise():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/kin-footer-region-noise",
        title="여드름 비용질문(한의원)",
        content_preview=(
            "여드름한의원을 선택해야 될 때 치료비용, 병원의 위치, 치료 프로그램 등 "
            "고려해야 되는 점이 많아 병원 선택에 어려움이 있습니다. "
            "강남, 노원, 신림, 수원, 안양, 일산, 부천, 인천, 대전, 청주, 천안, "
            "광주, 대구, 부산, 울산, 포항, 진주, 제주, 창원, 춘천, 구미, 전주, 원주 "
            "23지점 의 피부 네트워크를 가진 한의원입니다."
        ),
        matched_keywords=["청주 여드름 한의원 비용"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "region_mismatch"


def test_viral_final_gate_rejects_provider_info_posts_without_user_ask():
    price_sheet = ViralTarget(
        platform="cafe",
        url="https://example.com/provider-price-sheet",
        title="청주 여드름치료비용 - 수향",
        content_preview=(
            "청주 수향한의원에 여드름 치료비용입니다. "
            "한약 1개월 30만원 여드름흉터 10회치료 70만원 약초침은 3회 50만원입니다."
        ),
        matched_keywords=["청주 여드름 한의원 비용"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )
    guide_post = ViralTarget(
        platform="blog",
        url="https://example.com/provider-guide-post",
        title="다이어트 한약 가격 차이 정리해봤습니다",
        content_preview=(
            "가격은 약재의 종류와 처방 기간, 그리고 한의원의 운영 방식에 따라 갈립니다. "
            "차이의 상당 부분은 상담과 관리, 브랜드 비용입니다."
        ),
        matched_keywords=["복대동다이어트한의원상담 가격"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )
    treatment_guide = ViralTarget(
        platform="cafe",
        url="https://example.com/provider-body-guide",
        title="청주체형교정 추나요법이란",
        content_preview=(
            "만약 아래와 같은 증상들이 발견된다면 사랑인한의원 청주점에 오셔서 "
            "청주체형교정 치료를 진행해보시길 바랍니다. 대표적인 한방 프로그램으로는 추나요법이 있습니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )
    chuna_situation_guide = ViralTarget(
        platform="cafe",
        url="https://example.com/provider-chuna-situation-guide",
        title="청주추나요법 어떤 상황에서 필요할까?",
        content_preview=(
            "것을 추천해 드리고 싶습니다. 본 한의원의 의료진들은 수년간의 "
            "풍부한 임상경험을 가지고 있기 때문에 안심하시고 받으실 수 있습니다."
        ),
        matched_keywords=["청주 턱관절 안면비대칭 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(price_sheet) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(guide_post) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(treatment_guide) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(chuna_situation_guide) == "advertorial"


def test_viral_final_gate_rejects_question_like_blog_provider_cta_body():
    target = ViralTarget(
        platform="blog",
        url="https://example.com/provider-question-like-scar-guide",
        title="청주 수술흉터 새살침 후기 궁금하다면",
        content_preview=(
            "본원에서는 수술흉터 피부 상태에 맞춘 맞춤 진료를 진행합니다. "
            "네이버 예약 또는 카카오톡 상담으로 문의주세요. "
            "오시는 길과 진료시간은 아래에서 확인 가능합니다."
        ),
        matched_keywords=["청주 수술흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    text = f"{target.title} {target.content_preview}".lower()
    is_advertorial, signals, score = viral_hunter.CommentableFilter._detect_advertorial(target, text)

    assert is_advertorial is True
    assert score >= 5
    assert "provider_cta_body" in signals
    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "advertorial"


def test_viral_final_gate_keeps_cafe_user_question_with_provider_terms_but_no_cta_body():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-scar-real-user-question",
        title="청주 수술흉터 새살침 후기 궁금해요",
        content_preview=(
            "수술흉터 때문에 한의원 상담 받아보신 분 계신가요? "
            "비용이나 치료기간 후기가 궁금합니다. "
            "광고 말고 직접 경험 있으신 분 부탁드려요."
        ),
        matched_keywords=["청주 수술흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter._provider_cta_body_signal(target, "") == (False, [])
    assert viral_hunter.CommentableFilter._is_response_restricted_surface(target) is False
    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_response_restricted_user_surface():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-scar-response-restricted",
        title="청주 수술흉터 새살침 후기 궁금해요",
        content_preview=(
            "수술흉터와 켈로이드 때문에 한의원 새살침 상담을 알아보고 있습니다. "
            "비용, 치료기간, 주말 상담 가능 여부가 궁금해서 실제 경험담을 찾습니다. "
            "업체 사절 홍보 금지 댓글 사절입니다."
        ),
        matched_keywords=["청주 수술흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
        date_str="방금 전",
        comment_count=0,
        view_count=120,
    )

    assert viral_hunter.CommentableFilter._is_response_restricted_surface(target) is True
    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "response_restricted"

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert filtered == []
    assert target.is_commentable is False
    assert target.comment_status == "filtered_out"
    assert target.score_breakdown["final_reject_reason"] == "response_restricted"


def test_viral_final_gate_rejects_self_owned_blog_and_brand_title():
    owned_blog = ViralTarget(
        platform="blog",
        url="https://blog.naver.com/sangshan1/223456789012",
        title="청주 여드름흉터 새살침 후기 정리",
        content_preview="청주에서 여드름흉터와 새살침 상담을 알아보는 분들을 위한 글입니다.",
        matched_keywords=["청주 여드름흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )
    brand_title = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-brand-title-question",
        title="청주 규림한의원 여드름흉터 상담 받아보신 분 있나요",
        content_preview=(
            "여드름흉터랑 새살침 비용이 궁금해서 실제 상담 후기 찾고 있습니다. "
            "광고 말고 경험 있으신 분 계실까요?"
        ),
        matched_keywords=["청주 여드름흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(owned_blog) == "self_target"
    assert viral_hunter.CommentableFilter.final_reject_reason(brand_title) == "self_target"

    assert viral_hunter.CommentableFilter.apply_final_reject(owned_blog) == "self_target"
    assert owned_blog.is_commentable is False
    assert owned_blog.comment_status == "filtered_out"
    assert owned_blog.score_breakdown["final_reject_reason"] == "self_target"


def test_viral_filter_marks_self_target_status_for_audit():
    target = ViralTarget(
        platform="blog",
        url="https://blog.naver.com/cozypark5959/223456789013",
        title="청주 수술흉터 새살침 후기",
        content_preview="수술흉터와 켈로이드 치료 상담 정보를 정리한 글입니다.",
        matched_keywords=["청주 수술흉터 새살침"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        matched_keyword_grade="B",
    )

    filtered = viral_hunter.CommentableFilter().filter([target])

    assert filtered == []
    assert target.is_commentable is False
    assert target.comment_status == "filtered_out"
    assert target.score_breakdown["final_reject_reason"] == "self_target"


def test_viral_final_gate_rejects_body_seed_without_body_anchor():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/body-seed-broad-clinic",
        title="청주 한의원 추천 부탁드립니다",
        content_preview=(
            "청주에서 야간진료 가능한 한의원 추천 부탁드립니다. "
            "감기랑 피로 상담을 받아보고 싶습니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_body_review_question_with_clear_axis_anchor():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/body-review-axis-rescue",
        title="일자목인거 같은데 한의원 추천좀요",
        content_preview=(
            "평소 컴퓨터를 많이 써서 어깨가 무겁고 일자목 교정도 받고 싶습니다. "
            "청주에서 추나요법이나 체형교정 잘하는 한의원 추천 부탁드려요."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 31.6,
            "pathfinder_axis_fit_tier": "mismatch",
            "pathfinder_lens_fit_score": 84.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_body_fitness_provider_ad():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/body-fitness-provider-ad",
        title="닥터짐가경점 체형교정 프로그램 안내",
        content_preview=(
            "청주 가경동 운동센터에서 체형교정과 바디라인 관리를 도와드립니다. "
            "센터 회원권과 스피닝 수업은 카카오톡 문의로 확인 가능합니다."
        ),
        matched_keywords=["청주 체형교정"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_body_dosu_user_question():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/body-dosu-question",
        title="강서동쪽 도수치료 잘하는곳 있나요",
        content_preview=(
            "청주 강서동 근처에서 목디스크랑 자세 때문에 도수치료 받을 곳을 찾고 있습니다. "
            "정형외과나 한의원 추나요법 받아보신 분 추천 부탁드려요."
        ),
        matched_keywords=["청주 체형교정 추나 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_anti_hanbang_asymmetry_request():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/asymmetry-anti-hanbang",
        title="청주 턱관절 염증 잘보는 병원 추천해주세요",
        content_preview=(
            "턱관절이 아파서 청주에서 진료받을 병원을 찾고 있습니다. "
            "한의원은 추천안받을께요. 정형외과나 구강내과 쪽으로 알려주세요."
        ),
        matched_keywords=["청주 턱관절 안면비대칭 한의원 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_body_companion_when_user_text_is_other_condition():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/body-companion-adhd-noise",
        title="청주ADHD 한의원 추천부탁드려요~",
        content_preview=(
            "청주ADHD 병원을 찾아보니 정신의학과, 한의원, 상담센터 등 참 많습니다. "
            "답변 스니펫에는 침치료와 추나치료 같은 표현이 섞여 있지만 사용자의 질문은 체형교정이 아닙니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천", "청주 체형교정 추나 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_body:체형추나추천",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 88.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 86.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_body_companion_without_user_axis_anchor():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/body-companion-broad-hanbang-noise",
        title="36개월 한의원 추천 부탁드려요",
        content_preview=(
            "청주에 이사온지 얼마 안되서 어린이 한약 잘하는 곳을 찾고 있습니다. "
            "교통사고 추나 다이어트 위주의 한의원 말고 아이 한약 상담 가능한 곳이 궁금합니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천", "청주 체형교정 추나 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_body:체형추나추천",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 82.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 84.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_body_companion_foot_or_traffic_noise():
    foot = ViralTarget(
        platform="kin",
        url="https://example.com/body-companion-foot-noise",
        title="청주 족지간신경종",
        content_preview=(
            "발가락 쪽 통증 때문에 병원 추천을 찾고 있습니다. "
            "검색 답변에는 추나요법이나 허리 문제가 섞였지만 체형교정 질문은 아닙니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천", "청주 체형교정 추나 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_body:체형추나추천",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 80.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 84.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )
    traffic = ViralTarget(
        platform="cafe",
        url="https://example.com/body-companion-traffic-noise",
        title="청주한방병원 교통사고 치료받으려해요",
        content_preview=(
            "교통사고 후 입원과 자동차보험 적용 가능한 한방병원을 찾고 있습니다. "
            "체형교정이나 골반교정 문의가 아닙니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천", "청주 체형교정 추나 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "axis_body:체형추나추천",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 76.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 84.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(foot) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(traffic) == "off_domain"


def test_viral_final_gate_rejects_lifting_seed_without_lifting_anchor():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/lifting-seed-traffic-noise",
        title="청주 교통사고 한방치료 방법",
        content_preview=(
            "청주에서 교통사고 후유증 때문에 한방치료나 입원 가능한 곳을 "
            "알아보고 있습니다. 자동차보험 적용도 궁금합니다."
        ),
        matched_keywords=["청주 한방리프팅 추천"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_lifting_base_result_without_user_lifting_anchor():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-base-food-noise",
        title="홈플러스 강정 브랜드 솥솥 론칭제 2의 당당치킨으로 성장 목표",
        content_preview="식품 브랜드 출시와 매장 성장 목표를 다룬 글입니다.",
        matched_keywords=["청주 한방리프팅 추천"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "base",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 74.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 76.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_incidental_lifting_commerce_spam():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-incidental-commerce-spam",
        title="홈플러스 강정 브랜드 솥솥 론칭제 2의 당당치킨으로 성장 목표",
        content_preview=(
            "식품 브랜드 출시와 매장 성장 목표를 다룬 글입니다. "
            "젠틀몬스터 안경과 얼굴 리프팅 이벤트 키워드도 함께 노출됩니다."
        ),
        matched_keywords=["청주 한방리프팅 추천"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_query_variant": "base",
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 76.0,
            "pathfinder_axis_fit_tier": "acceptable",
            "pathfinder_lens_fit_score": 74.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_lifting_low_axis_fit_even_with_lifting_anchor():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-low-axis-fit",
        title="청주 리프팅 상담 예약 가능한 한의원",
        content_preview=(
            "청주에서 피부탄력과 팔자주름 때문에 리프팅 상담을 예약하려고 합니다. "
            "다만 Pathfinder 축 적합도가 낮게 들어온 후보는 저장하지 않아야 합니다."
        ),
        matched_keywords=["청주 한방리프팅 예약"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_execution_lens": "availability",
            "pathfinder_axis_fit_score": 42.0,
            "pathfinder_axis_fit_tier": "mismatch",
            "pathfinder_lens_fit_score": 82.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "domain_mismatch"


def test_viral_final_gate_keeps_lifting_hanbang_user_question():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-hanbang-question",
        title="청주 한방리프팅 팔자주름 상담 받아보신 분",
        content_preview=(
            "팔자주름과 피부탄력 때문에 한방리프팅이나 매선 상담을 고민 중입니다. "
            "청주에서 실제로 받아보신 분 후기나 추천 부탁드려요."
        ),
        matched_keywords=["청주 한방리프팅 추천"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 78.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 76.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_lifting_injectable_noise():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-injectable-noise",
        title="청주 팔자주름 엘란쎄 어떨까요",
        content_preview=(
            "팔자주름 때문에 리프팅이나 엘란쎄 시술을 알아보고 있습니다. "
            "피부과 필러 쪽으로 상담 받아보신 분 계신가요?"
        ),
        matched_keywords=["청주 한방리프팅 예약"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_lifting_device_context_without_hanbang_service():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/lifting-device-no-hanbang-service",
        title="청주 울쎄라 리프팅 추천받아요",
        content_preview=(
            "피부과에서 써마지랑 울쎄라 중에 어떤 리프팅이 나은지 궁금합니다. "
            "결정사 한방언니 후기 글도 봤는데 실제로 받아보신 분 계실까요?"
        ),
        matched_keywords=["청주 한방리프팅 추천"],
        category="리프팅/탄력",
        matched_keyword_category="리프팅/탄력",
        matched_keyword_grade="B",
        score_breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 78.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 76.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_skin_homecare_or_salon_posts():
    homecare = ViralTarget(
        platform="cafe",
        url="https://example.com/skin-homecare",
        title="강소라 led 마스크",
        content_preview=(
            "청주에서 여드름흉터 때문에 led 마스크랑 홈케어 제품 추천이 궁금합니다. "
            "한의원 치료보다는 집에서 관리할 제품을 찾고 있어요."
        ),
        matched_keywords=["금천동 여드름흉터"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )
    salon = ViralTarget(
        platform="cafe",
        url="https://example.com/skin-salon",
        title="피부관리실 추천이요",
        content_preview=(
            "청주 금천동 근처 피부관리실이나 에스테틱 추천받고 싶어요. "
            "한의원 상담이나 치료를 찾는 건 아닙니다."
        ),
        matched_keywords=["금천동 여드름흉터"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(homecare) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(salon) == "off_domain"


def test_viral_final_gate_rejects_skin_salon_and_incidental_legal_posts():
    spa = ViralTarget(
        platform="kin",
        url="https://example.com/skin-spa-noise",
        title="청주에 피부 스케일링",
        content_preview=(
            "얼굴에 좁쌀여드름이 있는데 분평동 학스킨스파에서 상담 받아보라는 "
            "추천을 들었습니다. 제품 구입이나 피부관리 쪽도 궁금합니다."
        ),
        matched_keywords=["분평동 여드름"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )
    legal = ViralTarget(
        platform="kin",
        url="https://example.com/skin-incidental-legal",
        title="학폭피해학생부모입니다",
        content_preview=(
            "피해학생에게 여드름괴물이라고 비아냥거린 학교폭력 사건입니다. "
            "청주에서 학폭 상담받을 변호사나 법률 조언이 필요합니다."
        ),
        matched_keywords=["산남동 여드름"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(spa) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(legal) == "off_domain"


def test_viral_final_gate_rejects_skin_western_rx_prescription_request():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/skin-isotretinoin-prescription",
        title="청주에 미성년자한테도 이소티논 주는 병원",
        content_preview=(
            "여드름 때문에 스트레스가 심한데 제가 간 병원은 안 준대요. "
            "사창동 쪽이면 더 좋고 미성년자한테도 이소티논 처방해주는 병원 알려주세요."
        ),
        matched_keywords=["사창동 여드름"],
        category="피부",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_skin_hanbang_question_after_rx_attempts():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/skin-hanbang-after-isotretinoin",
        title="이소티논 먹어도 여드름이 반복돼서 한의원 상담 궁금해요",
        content_preview=(
            "피부과약을 먹어도 자꾸 재발해서 청주 여드름 한의원에서 "
            "한약이나 약침 치료 상담 받아보신 분 후기 부탁드립니다."
        ),
        matched_keywords=["청주 여드름 한의원 상담"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_diet_activity_venue_noise():
    sports_center = ViralTarget(
        platform="kin",
        url="https://example.com/diet-sports-center",
        title="청주 현대스포랜드에 다니려고하는데요",
        content_preview=(
            "다이어트를 하려고 피트니스 센터를 알아보는데 현대스포랜드 시설이나 "
            "한달 가격이 어떤지 궁금합니다."
        ),
        matched_keywords=["사창동 다이어트"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )
    dance = ViralTarget(
        platform="kin",
        url="https://example.com/diet-dance-class",
        title="청주 봉명동에 있는 째즈댄스 학원좀 알려주세요",
        content_preview=(
            "다이어트 시간에는 땀이 많이 나서 째즈댄스 학원을 다녀보려고 합니다. "
            "봉명동 근처 위치와 시간을 알고 싶습니다."
        ),
        matched_keywords=["봉명동 다이어트"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )
    zumba = ViralTarget(
        platform="kin",
        url="https://example.com/diet-zumba-class",
        title="청주 서원구 줌바댄스 하는 곳",
        content_preview=(
            "수곡동이나 산남동 근처에서 다이어트 댄스처럼 할 수 있는 "
            "줌바댄스 수업 위치와 시간을 알고 싶습니다."
        ),
        matched_keywords=["산남동 다이어트"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(sports_center) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(dance) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(zumba) == "off_domain"


def test_viral_final_gate_keeps_diet_medical_treatment_question():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/diet-injection-question",
        title="야식 때문에 살이 쪄서 다이어트 주사 고민이에요",
        content_preview=(
            "사창동 근처에서 다이어트 주사나 한약 상담 받아보신 분 계실까요? "
            "비용과 처방 기간이 궁금합니다."
        ),
        matched_keywords=["사창동 다이어트"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_diet_testimonial_promo():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/diet-testimonial-promo",
        title="복대동다이어트한약 한의원 내돈내산 10키로 성공후기♥",
        content_preview=(
            "복대동 다이어트한약 한의원에서 상담받고 비움탕으로 10키로 감량 성공한 "
            "내돈내산 후기입니다. 자세한 처방과 비용 후기를 남겨요."
        ),
        matched_keywords=["복대동 다이어트 한의원 상담"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "advertorial"


def test_viral_final_gate_rejects_homework_with_incidental_accident_context():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/homework-accident-noise",
        title="영어작문 부탁드립니다 내공50드리겠습니다.",
        content_preview=(
            "입원한 병원은 금천동에 위치한 정형외과입니다. "
            "1학기 때 교통사고로 치료했다는 내용을 영어작문으로 옮겨주세요."
        ),
        matched_keywords=["금천동 교통사고"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "non_relevant"


def test_viral_final_gate_rejects_traffic_vehicle_repair_or_settlement_noise():
    repair = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-repair-compensation",
        title="상대방 과실 교통사고시 광택 코팅비용 보상받을수 있나요",
        content_preview=(
            "차량 광택과 코팅 수리비를 보험사에서 보상받을 수 있는지 궁금합니다. "
            "과실비율과 대물보상 기준을 알고 싶습니다."
        ),
        matched_keywords=["용암동 교통사고"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="B",
    )
    settlement = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-settlement-only",
        title="교통사고 합의금 과실비율 질문",
        content_preview=(
            "손해보험사와 합의금 이야기를 해야 하는데 휴업손해와 위자료 계산이 "
            "어떻게 되는지 법률 조언이 필요합니다."
        ),
        matched_keywords=["가경동 교통사고 입원 보험"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(repair) == "off_domain"
    assert viral_hunter.CommentableFilter.final_reject_reason(settlement) == "off_domain"


def test_viral_final_gate_rejects_traffic_insurance_surcharge_noise():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-insurance-surcharge",
        title="보험료할증에 관한 질문드립니다",
        content_preview=(
            "교통사고 후 자동차보험 보험료할증이 얼마나 붙는지 궁금합니다. "
            "대인 대물 접수 뒤 다음 갱신 보험료 계산 기준을 알고 싶습니다."
        ),
        matched_keywords=["봉명동 교통사고 한의원 치료비"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="A",
        score_breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 86.0,
            "pathfinder_axis_fit_tier": "strong",
            "pathfinder_lens_fit_score": 82.0,
            "pathfinder_lens_fit_tier": "strong",
        },
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_rejects_traffic_animal_hospital_noise():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/traffic-vet-animal-noise",
        title="회원님들중 수의사분이나 지인분들중 계시면 도움좀 부탁드립니다",
        content_preview=(
            "충북 청주 산남동에서 닥스훈트를 키우고 있는데 오늘 교통사고를 당했습니다. "
            "사직동 24시 종합 동물병원에 입원중인데 수의사 선생님 의견이 궁금합니다."
        ),
        matched_keywords=["산남동 교통사고 입원"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="S",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "off_domain"


def test_viral_final_gate_keeps_traffic_medical_admission_question():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/traffic-medical-admission",
        title="교통사고났는데 가경동 입원가능한곳 알려주세요",
        content_preview=(
            "출근길에 사고가 나서 목이랑 어깨 통증이 심합니다. "
            "보험 접수는 됐고 가경동 근처 입원 가능한 한의원이나 병원 추천 부탁드려요."
        ),
        matched_keywords=["가경동 교통사고 입원 추천"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="A",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_final_gate_rejects_traffic_chain_provider_seo():
    target = ViralTarget(
        platform="kin",
        url="https://example.com/traffic-chain-seo",
        title="자동차사고후유증 차앤차한의원",
        content_preview=(
            "자동차보험치료, 교통사고후물리치료, 자보한의원입니다. "
            "차앤차는 전국 지점이 위치하며 교통사고후유증 치료를 안내합니다."
        ),
        matched_keywords=["가경동 교통사고 입원 보험"],
        category="교통사고",
        matched_keyword_category="교통사고",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "advertorial"


def test_viral_final_gate_rejects_medical_price_event_promo():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/skin-price-event-promo",
        title="청주편평사마귀치료 무제한 제거 성지에서 27만원 이벤트로 새 피부 얻은 이야기",
        content_preview=(
            "청주 편평사마귀 치료를 무제한 제거 이벤트로 27만원에 받았다는 "
            "홍보성 후기입니다. 피부 치료 가격 혜택과 이벤트 내용을 안내합니다."
        ),
        matched_keywords=["청주 여드름 한의원 비용"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "advertorial"


def test_viral_final_gate_rejects_local_clinic_availability_promo_title():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/local-clinic-availability-promo",
        title="청주한의원추천 화요일 야간진료 예약가능해요!",
        content_preview=(
            "청주 체형교정 한의원에서 추나요법과 자세교정 상담을 받을 수 있고 "
            "야간진료 예약 가능하다는 안내 글입니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "advertorial"


def test_viral_final_gate_rejects_blog_medical_seo_titles():
    asymmetry = ViralTarget(
        platform="blog",
        url="https://example.com/blog-asymmetry-seo",
        title="청주가경동한의원 안면비대칭, 단순 미용 문제가 아닌 이유",
        content_preview=(
            "청주 가경동 한의원에서 안면비대칭과 턱관절 문제를 어떻게 봐야 하는지 "
            "설명하는 병원형 정보 글입니다."
        ),
        matched_keywords=["청주 안면비대칭 교정 추천"],
        category="안면비대칭",
        matched_keyword_category="안면비대칭",
        matched_keyword_grade="B",
    )
    body = ViralTarget(
        platform="blog",
        url="https://example.com/blog-body-seo",
        title="청주한의원 몸과 마음의 균형을 되찾는 체형교정",
        content_preview=(
            "청주 한의원에서 체형교정과 추나요법, 자세교정 관리 방향을 안내하는 "
            "홍보성 블로그 글입니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(asymmetry) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(body) == "advertorial"


def test_viral_final_gate_rejects_blog_local_provider_service_titles():
    traffic_body = ViralTarget(
        platform="blog",
        url="https://example.com/blog-body-provider-title-traffic",
        title="체형교정 청주한의원 교통사고 후유증 초기 중요",
        content_preview=(
            "청주 한의원에서 교통사고 후유증과 체형교정, 추나요법 관리 방향을 "
            "설명하는 로컬 병원 블로그 글입니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )
    rehab_body = ViralTarget(
        platform="blog",
        url="https://example.com/blog-body-provider-title-rehab",
        title="청주한의원 재활운동 체형교정",
        content_preview=(
            "청주 한의원에서 재활운동과 체형교정 진료를 안내하는 병원형 "
            "콘텐츠입니다."
        ),
        matched_keywords=["청주 체형교정 한의원 추천"],
        category="체형교정",
        matched_keyword_category="체형교정",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(traffic_body) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(rehab_body) == "advertorial"


def test_viral_final_gate_rejects_cafe_local_provider_service_titles():
    skin = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-skin-provider-title",
        title="청주여드름흉터치료 ㅎ한의원",
        content_preview=(
            "청주 한의원에서 여드름흉터와 패인흉터 치료 방법을 안내하는 "
            "카페형 병원 홍보 글입니다."
        ),
        matched_keywords=["가경동 여드름흉터"],
        category="피부/여드름",
        matched_keyword_category="피부/여드름",
        matched_keyword_grade="B",
    )
    diet = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-diet-seo-title",
        title="청주다이어트한약 40대다이어트 결정적인 실수5",
        content_preview=(
            "청주 다이어트한약과 비만 관리 방향을 설명하며 상담을 유도하는 "
            "카페형 정보 글입니다."
        ),
        matched_keywords=["청주다이어트한약"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )
    famous = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-diet-famous-title",
        title="청주다이어트한약 유명한곳이 여기죠???",
        content_preview=(
            "청주 다이어트한약과 비만 관리 상담을 유도하는 카페형 홍보 "
            "콘텐츠입니다."
        ),
        matched_keywords=["청주다이어트한약"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(skin) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(diet) == "advertorial"
    assert viral_hunter.CommentableFilter.final_reject_reason(famous) == "advertorial"


def test_viral_final_gate_keeps_cafe_diet_user_question_title():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/cafe-diet-user-question",
        title="청주다이어트한약 먹으면서 감량 성공하신 분?",
        content_preview=(
            "청주에서 다이어트한약 먹어보신 분 계신가요? 광고 말고 실제로 "
            "상담 받아본 후기나 비용이 궁금합니다."
        ),
        matched_keywords=["청주다이어트한약"],
        category="다이어트",
        matched_keyword_category="다이어트",
        matched_keyword_grade="B",
    )

    assert viral_hunter.CommentableFilter.final_reject_reason(target) is None


def test_viral_clinic_fit_drops_non_service_skin_beauty_posts():
    target = ViralTarget(
        platform="cafe",
        url="https://example.com/non-service-skin",
        title="청주 여드름 화장품 추천",
        content_preview=(
            "청주에서 여드름 때문에 올리브영 화장품이랑 폼클렌징 추천 받고 싶어요. "
            "피부과 레이저는 부담이라 홈케어 제품 위주로 알아보고 있습니다. "
            "한의원 상담이나 치료를 찾는 건 아니고 화장품 후기 궁금합니다."
        ),
        matched_keywords=["청주 여드름"],
        category="피부",
    )
    text = f"{target.title} {target.content_preview}".lower()

    score, tier, signals = viral_hunter.CommentableFilter._assess_clinic_treatment_fit(
        target,
        "scar_skin",
        text,
        is_health=True,
    )

    assert score < viral_hunter.CommentableFilter.MIN_CLINIC_TREATMENT_FIT_SCORE
    assert tier == "weak"
    assert "non_service_request" in signals


def test_zero_result_streak_does_not_sleep_without_api_errors(monkeypatch):
    searcher = viral_hunter.NaverUnifiedSearch(delay=0, use_cache=False)

    def fail_if_called(seconds):
        raise AssertionError(f"unexpected sleep: {seconds}")

    monkeypatch.setattr(viral_hunter.time, "sleep", fail_if_called)

    for _ in range(10):
        searcher._check_blocking_status(0)

    assert searcher._consecutive_empty_results == 0
    assert searcher._is_blocked is False


def test_viral_duplicate_upsert_updates_scan_metadata_without_table_scan(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral.db"))

    target = {
        "id": "a",
        "platform": "kin",
        "url": "https://example.com/q/1",
        "title": "청주 다이어트 질문",
        "content_preview": "상담 가능한 곳 있나요?",
        "matched_keywords": ["청주 다이어트"],
        "category": "다이어트",
        "comment_status": "pending",
        "source_scan_run_id": 1,
    }
    assert db.insert_viral_target(target)
    assert db.insert_viral_target({**target, "id": "b", "source_scan_run_id": 2})

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT scan_count, source_scan_run_id, comment_status FROM viral_targets WHERE url = ?",
            (target["url"],),
        ).fetchone()

    assert row == (2, 2, "pending")
    assert db.get_existing_viral_urls([target["url"], "https://example.com/new"]) == {target["url"]}


def test_database_get_viral_targets_uses_recent_scan_filters(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_list_filters.db"))

    rows = [
        ("run75-pending", "https://example.com/run75-pending", "pending", 95, 75, "2026-06-01 10:00:00", "2026-06-15 16:12:00"),
        ("run75-posted", "https://example.com/run75-posted", "posted", 99, 75, "2026-06-01 10:00:00", "2026-06-15 16:13:00"),
        ("run74-pending", "https://example.com/run74-pending", "pending", 100, 74, "2026-06-01 10:00:00", "2026-06-14 16:09:00"),
        ("today-rescanned", "https://example.com/today-rescanned", "pending", 80, 76, "2026-06-01 10:00:00", None),
    ]
    for row_id, url, status, score, scan_id, discovered_at, last_scanned_at in rows:
        assert db.insert_viral_target({
            "id": row_id,
            "platform": "cafe",
            "url": url,
            "title": row_id,
            "matched_keywords": ["keyword"],
            "comment_status": status,
            "priority_score": score,
            "source_scan_run_id": scan_id,
        })
        with sqlite3.connect(db.db_path) as conn:
            if last_scanned_at is None:
                conn.execute(
                    "UPDATE viral_targets SET discovered_at = ?, last_scanned_at = datetime('now', 'localtime') WHERE id = ?",
                    (discovered_at, row_id),
                )
            else:
                conn.execute(
                    "UPDATE viral_targets SET discovered_at = ?, last_scanned_at = ? WHERE id = ?",
                    (discovered_at, last_scanned_at, row_id),
                )
            conn.commit()

    run_rows = db.get_viral_targets(status="pending", scan_batch="run:75", sort="date")
    hour_rows = db.get_viral_targets(status="pending", scan_batch="2026-06-15 16", sort="date")
    today_rows = db.get_viral_targets(status="pending", date_filter="오늘", sort="date")

    assert [row["id"] for row in run_rows] == ["run75-pending"]
    assert [row["id"] for row in hour_rows] == ["run75-pending"]
    assert "today-rescanned" in {row["id"] for row in today_rows}


def test_viral_url_canonicalizer_uses_naver_post_identity():
    assert (
        canonicalize_viral_url(
            "https://kin.naver.com/qna/detail.naver?d1id=7&docId=346459027&qb=old"
        )
        == "https://kin.naver.com/qna/detail.naver?docId=346459027"
    )
    assert (
        canonicalize_viral_url(
            "https://blog.naver.com/PostView.naver?blogId=ClinicA&logNo=223456&from=search"
        )
        == "https://blog.naver.com/clinica/223456"
    )
    assert (
        canonicalize_viral_url("https://m.blog.naver.com/ClinicA/223456?trackingCode=rss")
        == "https://blog.naver.com/clinica/223456"
    )
    assert (
        canonicalize_viral_url("https://cafe.naver.com/ClinicCafe/98765?boardtype=L")
        == "https://cafe.naver.com/cliniccafe/98765"
    )


def test_viral_canonical_upsert_prevents_kin_query_param_duplicates(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_canonical.db"))
    first_url = "https://kin.naver.com/qna/detail.naver?d1id=7&docId=346459027&qb=old"
    second_url = "https://kin.naver.com/qna/detail.naver?d1id=7&docId=346459027&qb=new"

    assert db.insert_viral_target({
        "id": "first",
        "platform": "kin",
        "url": first_url,
        "title": "same doc",
        "matched_keywords": ["keyword"],
        "comment_status": "pending",
        "source_scan_run_id": 1,
    })
    assert db.insert_viral_target({
        "id": "second",
        "platform": "kin",
        "url": second_url,
        "title": "same doc refreshed",
        "matched_keywords": ["keyword"],
        "comment_status": "pending",
        "source_scan_run_id": 2,
    })

    with sqlite3.connect(db.db_path) as conn:
        rows = conn.execute(
            """
            SELECT url, canonical_url, scan_count, source_scan_run_id
            FROM viral_targets
            """
        ).fetchall()

    assert rows == [(
        first_url,
        "https://kin.naver.com/qna/detail.naver?docId=346459027",
        2,
        2,
    )]
    assert db.get_existing_viral_urls([second_url]) == {second_url}


def test_existing_url_refresh_uses_blog_cafe_canonical_paths(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_canonical_refresh.db"))
    blog_postview = (
        "https://blog.naver.com/PostView.naver?blogId=ClinicA&logNo=223456&from=search"
    )
    blog_path = "https://m.blog.naver.com/ClinicA/223456?trackingCode=rss"
    cafe_url = "https://cafe.naver.com/ClinicCafe/98765?boardtype=L"
    cafe_url_with_query = "https://cafe.naver.com/ClinicCafe/98765?iframe_url=/ArticleRead.nhn"

    assert db.insert_viral_target({
        "id": "blog-old",
        "platform": "blog",
        "url": blog_postview,
        "title": "old blog",
        "matched_keywords": ["keyword"],
        "comment_status": "posted",
        "source_scan_run_id": 1,
    })
    assert db.insert_viral_target({
        "id": "cafe-old",
        "platform": "cafe",
        "url": cafe_url,
        "title": "old cafe",
        "matched_keywords": ["keyword"],
        "comment_status": "posted",
        "source_scan_run_id": 1,
    })

    assert db.get_existing_viral_urls([blog_path, cafe_url_with_query]) == {
        blog_path,
        cafe_url_with_query,
    }

    refreshed = db.refresh_existing_viral_targets([
        {
            "id": "blog-new",
            "platform": "blog",
            "url": blog_path,
            "title": "new blog",
            "matched_keywords": ["keyword"],
            "source_scan_run_id": 10,
        },
        {
            "id": "cafe-new",
            "platform": "cafe",
            "url": cafe_url_with_query,
            "title": "new cafe",
            "matched_keywords": ["keyword"],
            "source_scan_run_id": 10,
        },
    ])

    assert refreshed == 2
    with sqlite3.connect(db.db_path) as conn:
        rows = conn.execute(
            """
            SELECT platform, scan_count, source_scan_run_id, comment_status
            FROM viral_targets
            ORDER BY platform
            """
        ).fetchall()

    assert rows == [
        ("blog", 2, 10, "posted"),
        ("cafe", 2, 10, "posted"),
    ]


def test_viral_target_insert_persists_exposure_and_ai_metadata(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_quality.db"))

    target = {
        "id": "quality",
        "platform": "cafe",
        "url": "https://example.com/quality",
        "title": "quality target",
        "matched_keywords": ["청주 상담"],
        "comment_status": "pending",
        "priority_score": 101,
        "exposure_score": 120,
        "workability_score": 95,
        "conversion_fit_score": 88,
        "score_breakdown": {"exposure": 120, "workability": 95},
        "search_sort": "sim",
        "search_rank": 3,
        "search_start": 1,
        "sort_appearances": ["sim", "date"],
        "ai_reviewed": True,
        "ai_infiltration_score": 91,
        "ai_post_type": "consultation",
        "ai_competitor": True,
        "ai_competitor_name": "competitor clinic",
    }
    assert db.insert_viral_target(target)

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            """
            SELECT exposure_score, workability_score, conversion_fit_score,
                   search_sort, search_rank, ai_reviewed, ai_infiltration_score,
                   ai_post_type, ai_competitor, ai_competitor_name
            FROM viral_targets
            WHERE url = ?
            """,
            (target["url"],),
        ).fetchone()

    assert row == (120.0, 95.0, 88.0, "sim", 3, 1, 91.0, "consultation", 1, "competitor clinic")


def test_duplicate_upsert_handles_legacy_null_scan_count_and_preserves_scores(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_null_scan.db"))

    target = {
        "id": "legacy",
        "platform": "kin",
        "url": "https://example.com/legacy",
        "title": "청주 교통사고 질문",
        "matched_keywords": ["청주 교통사고"],
        "category": "교통사고",
        "comment_status": "pending",
        "priority_score": 95,
        "matched_keyword_kei": 100.0,
        "matched_keyword_priority": 80.0,
        "source_scan_run_id": 1,
    }
    assert db.insert_viral_target(target)
    with sqlite3.connect(db.db_path) as conn:
        conn.execute(
            "UPDATE viral_targets SET scan_count = NULL WHERE url = ?",
            (target["url"],),
        )
        conn.commit()

    assert db.insert_viral_target({
        **target,
        "id": "legacy-again",
        "priority_score": 0,
        "matched_keyword_kei": 0,
        "matched_keyword_priority": 0,
        "source_scan_run_id": 2,
    })

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            """
            SELECT scan_count, priority_score, matched_keyword_kei,
                   matched_keyword_priority, source_scan_run_id
            FROM viral_targets
            WHERE url = ?
            """,
            (target["url"],),
        ).fetchone()

    assert row == (1, 95.0, 100.0, 80.0, 2)


def test_viral_hunter_excludes_existing_urls_before_ai_but_refreshes_metadata(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_before_ai.db"))
    existing = {
        "id": "old",
        "platform": "kin",
        "url": "https://example.com/seen",
        "title": "old title",
        "matched_keywords": ["old"],
        "comment_status": "posted",
        "source_scan_run_id": 1,
        "score_breakdown": {
            "clinic_treatment_fit_score": 81,
            "legacy_quality_note": "keep",
        },
    }
    assert db.insert_viral_target(existing)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = db
    targets = [
        ViralTarget(
            platform="kin",
            url="https://example.com/seen",
            title="new title",
            matched_keywords=["청주 여드름"],
            source_scan_run_id=10,
            matched_keyword_grade="B",
            matched_keyword_kei=3.2,
            matched_keyword_priority=71.0,
            matched_keyword_category="피부/여드름",
            score_breakdown={
                "pathfinder_execution_lens": "cost",
                "pathfinder_query_variant": "cost:비용",
                "pathfinder_axis_fit_score": 77,
            },
        ),
        ViralTarget(
            platform="kin",
            url="https://example.com/fresh",
            title="fresh title",
            matched_keywords=["청주 여드름"],
            source_scan_run_id=10,
        ),
    ]

    fresh_targets, duplicate_count = hunter._exclude_existing_targets_before_ai(targets)

    assert duplicate_count == 1
    assert [target.url for target in fresh_targets] == ["https://example.com/fresh"]

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            """
            SELECT scan_count, source_scan_run_id, comment_status,
                   matched_keyword, matched_keyword_category, score_breakdown
            FROM viral_targets
            WHERE url = ?
            """,
            ("https://example.com/seen",),
        ).fetchone()

    merged_breakdown = json.loads(row[5])
    assert row[:5] == (2, 10, "posted", "청주 여드름", "피부/여드름")
    assert merged_breakdown["clinic_treatment_fit_score"] == 81
    assert merged_breakdown["legacy_quality_note"] == "keep"
    assert merged_breakdown["pathfinder_execution_lens"] == "cost"
    assert merged_breakdown["pathfinder_query_variant"] == "cost:비용"
    assert merged_breakdown["pathfinder_axis_fit_score"] == 77


def test_existing_url_refresh_is_deduped_and_does_not_zero_out_priority(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_refresh.db"))
    existing = {
        "id": "seen",
        "platform": "kin",
        "url": "https://example.com/seen-once",
        "title": "old title",
        "matched_keywords": ["청주 다이어트"],
        "category": "다이어트",
        "comment_status": "posted",
        "priority_score": 88,
        "source_scan_run_id": 1,
    }
    assert db.insert_viral_target(existing)

    refreshed = db.refresh_existing_viral_targets([
        {
            **existing,
            "title": "new zero score",
            "priority_score": 0,
            "source_scan_run_id": 10,
            "matched_keywords": ["청주 다이어트약"],
        },
        {
            **existing,
            "title": "duplicate same run",
            "priority_score": 0,
            "source_scan_run_id": 10,
            "matched_keywords": ["청주 다이어트약"],
        },
    ])

    assert refreshed == 1
    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            """
            SELECT scan_count, priority_score, source_scan_run_id, matched_keyword
            FROM viral_targets
            WHERE url = ?
            """,
            (existing["url"],),
        ).fetchone()

    assert row == (2, 88.0, 10, "청주 다이어트약")


def test_unified_ai_bonus_keeps_hot_lead_score_above_tier_threshold():
    generator = AICommentGenerator()
    target = ViralTarget(
        platform="kin",
        url="https://example.com/hot",
        title="청주 교통사고 입원 질문",
        content_preview="청주에서 교통사고 입원 상담 가능한 곳 찾습니다.",
        matched_keywords=["청주 교통사고"],
        category="교통사고",
        priority_score=130,
    )

    suitable, unsuitable_count, competitor_count = generator._parse_unified_results(
        [target],
        """
        ---
        POST_ID: 1
        SUITABLE: true
        SCORE: 95
        TYPE: consultation
        COMPETITOR: false
        COUNTER_SCORE: 0
        REASON: 상담 요청
        ---
        """,
    )

    assert unsuitable_count == 0
    assert competitor_count == 0
    assert suitable[0].priority_score == 149
    assert suitable[0].priority_score >= 120


def test_competitor_reference_uses_curated_list_with_criticals():
    """프롬프트 경쟁사 참조는 큐레이트된 config(로랑/데이릴 critical)에서 온다."""
    note = AICommentGenerator._competitor_reference_note()
    assert "로랑한의원" in note and "데이릴한의원" in note
    # 자기 업체 제외 지시 포함
    assert "규림" in note and "COMPETITOR=false" in note
    # 빌더가 프롬프트에 주입
    prompt = AICommentGenerator.__new__(AICommentGenerator)._build_unified_prompt(
        "분석:\n{posts_formatted}\n경쟁사:\n{competitor_reference}", "POST_ID: 1"
    )
    assert "로랑한의원" in prompt and "데이릴한의원" in prompt
    # competitor_reference 플레이스홀더 없는 구버전 템플릿도 안전하게 append
    legacy = AICommentGenerator.__new__(AICommentGenerator)._build_unified_prompt(
        "분석:\n{posts_formatted}", "POST_ID: 1"
    )
    assert "로랑한의원" in legacy


def test_classify_competitor_name_self_critical_known_unknown():
    f = AICommentGenerator._classify_competitor_name
    assert f("로랑한의원") == "critical"
    assert f("데이릴한의원 (간접 언급)") == "critical"
    assert f("자연과한의원 청주점") == "critical"
    assert f("규림한의원 청주점") == "self"      # 자기 업체
    assert f("kyurim clinic") == "self"
    assert f("이름없는동네한의원") == "unknown"
    assert f("N/A") == "unknown"
    assert f("") == "unknown"


def test_parse_unified_self_recommendation_not_counterattack():
    """답변이 우리 한의원(규림)을 추천한 글은 역공략 대상이 아니다."""
    generator = AICommentGenerator()
    target = ViralTarget(
        platform="kin", url="https://example.com/self-rec",
        title="청주 안면비대칭 어디가 잘해요",
        content_preview="청주 안면비대칭 잘하는 곳 추천해주세요",
        matched_keywords=["청주 안면비대칭"], category="안면비대칭", priority_score=80,
    )
    suitable, _unsuit, competitor_count = generator._parse_unified_results(
        [target],
        """
        ---
        POST_ID: 1
        SUITABLE: true
        SCORE: 80
        TYPE: recommendation_request
        COMPETITOR: true
        COMPETITOR_NAME: 규림한의원 청주점
        COUNTER_SCORE: 70
        REASON: 우리 한의원 추천됨
        ---
        """,
    )
    assert competitor_count == 0                       # 자기 추천 → 역공략 카운트 안 함
    assert suitable[0].ai_competitor is False
    assert suitable[0].category != "경쟁사_역공략"        # 경쟁사_역공략으로 바뀌지 않음


def test_parse_unified_critical_competitor_gets_priority_boost():
    """critical 경쟁사(로랑) 가로채기는 일반 경쟁사보다 우선순위 부스트를 더 받는다."""
    generator = AICommentGenerator()

    def run(comp_name):
        t = ViralTarget(
            platform="kin", url=f"https://example.com/{comp_name}",
            title="청주 안면비대칭 추천", content_preview="청주 안면비대칭 어디가 좋아요?",
            matched_keywords=["청주 안면비대칭"], category="안면비대칭", priority_score=80,
        )
        generator._parse_unified_results(
            [t],
            f"""
            ---
            POST_ID: 1
            SUITABLE: true
            SCORE: 80
            TYPE: recommendation_request
            COMPETITOR: true
            COMPETITOR_NAME: {comp_name}
            COUNTER_SCORE: 80
            REASON: 경쟁사 추천됨
            ---
            """,
        )
        return t

    critical = run("로랑한의원")
    generic = run("이름없는동네한의원")
    assert critical.category == "경쟁사_역공략" and generic.category == "경쟁사_역공략"
    assert (critical.score_breakdown or {}).get("competitor_class") == "critical"
    assert (critical.score_breakdown or {}).get("competitor_critical_boost") == 10.0
    assert "competitor_critical_boost" not in (generic.score_breakdown or {})
    assert critical.priority_score > generic.priority_score   # critical 부스트로 더 높음


def test_raw_backlog_can_be_promoted_to_pending_on_later_ai_success(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_promote.db"))
    raw = {
        "id": "raw",
        "platform": "cafe",
        "url": "https://example.com/post/1",
        "title": "청주 교통사고 상담",
        "matched_keywords": ["청주 교통사고"],
        "comment_status": "raw_backlog",
        "source_scan_run_id": 3,
    }
    assert db.insert_viral_target(raw)
    assert db.insert_viral_target({**raw, "id": "raw2", "comment_status": "pending", "source_scan_run_id": 4})

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT comment_status, source_scan_run_id, scan_count FROM viral_targets WHERE url = ?",
            (raw["url"],),
        ).fetchone()

    assert row == ("pending", 4, 2)


def test_needs_ai_retry_is_not_demoted_to_raw_backlog(tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_retry.db"))
    retry = {
        "id": "retry",
        "platform": "kin",
        "url": "https://example.com/retry/1",
        "title": "청주 피부 질문",
        "comment_status": "needs_ai_retry",
        "source_scan_run_id": 5,
    }
    assert db.insert_viral_target(retry)
    assert db.insert_viral_target({**retry, "id": "retry2", "comment_status": "raw_backlog", "source_scan_run_id": 6})

    with sqlite3.connect(db.db_path) as conn:
        row = conn.execute(
            "SELECT comment_status, source_scan_run_id, scan_count FROM viral_targets WHERE url = ?",
            (retry["url"],),
        ).fetchone()

    assert row == ("needs_ai_retry", 6, 2)


def test_unified_ai_failure_is_saved_for_retry_not_returned_as_pending(monkeypatch, tmp_path):
    db = DatabaseManager(str(tmp_path / "viral_ai.db"))
    generator = AICommentGenerator()
    monkeypatch.setattr(
        generator,
        "_load_prompts",
        lambda: {"unified_analysis": {"template": "{posts_formatted}", "batch_size": 2}},
    )

    def fail_ai(*args, **kwargs):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(viral_hunter, "ai_generate", fail_ai)
    targets = [
        ViralTarget(platform="kin", url="https://example.com/1", title="청주 여드름 질문"),
        ViralTarget(platform="kin", url="https://example.com/2", title="청주 다이어트 질문"),
    ]

    result = generator.unified_analysis_parallel(targets, max_workers=1, db=db)

    assert result == []
    assert generator.last_failed_ai_batches == {1}
    with sqlite3.connect(db.db_path) as conn:
        rows = conn.execute(
            "SELECT comment_status, COUNT(*) FROM viral_targets GROUP BY comment_status"
        ).fetchall()
    assert rows == [("needs_ai_retry", 2)]


def test_unified_parser_missing_suitable_is_not_fail_open():
    generator = AICommentGenerator()
    target = ViralTarget(platform="kin", url="https://example.com/3", title="청주 질문")

    suitable, unsuitable, competitors = generator._parse_unified_results(
        [target],
        "POST_ID: 1\nSCORE: 90\nTYPE: recommendation_request\n---",
    )

    assert suitable == []
    assert unsuitable == 1
    assert competitors == 0


def test_ad_classify_apply_scopes_updates_by_source_scan_run_id():
    conn = sqlite3.connect(":memory:")
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            source_scan_run_id INTEGER,
            comment_status TEXT,
            ai_ad_reason TEXT,
            ai_classified_at TEXT
        )
        """
    )
    cur.executemany(
        "INSERT INTO viral_targets(id, source_scan_run_id, comment_status) VALUES (?, ?, ?)",
        [("run9", 9, "pending"), ("run8", 8, "pending")],
    )

    updated = _execute_scoped_update(
        cur,
        "ai_ad_reason=?, ai_classified_at=?, comment_status=?",
        ["parse_failed", "now", "needs_ai_retry"],
        "run9",
        9,
    )
    skipped = _execute_scoped_update(
        cur,
        "ai_ad_reason=?, ai_classified_at=?, comment_status=?",
        ["parse_failed", "now", "needs_ai_retry"],
        "run8",
        9,
    )

    assert updated == 1
    assert skipped == 0
    assert cur.execute("SELECT comment_status FROM viral_targets WHERE id='run9'").fetchone()[0] == "needs_ai_retry"
    assert cur.execute("SELECT comment_status FROM viral_targets WHERE id='run8'").fetchone()[0] == "pending"


def test_strip_transactional_suffix_keeps_service_core():
    assert strip_transactional_suffix("복대동 턱비대칭 한의원 비용") == "복대동 턱비대칭 한의원"
    assert strip_transactional_suffix("사창동 매선침 상담 가능한곳") == "사창동 매선침"
    assert strip_transactional_suffix("봉명동 교통사고 한의원 입원 가능") == "봉명동 교통사고 한의원 입원"
    assert strip_transactional_suffix("분평동 안면홍조 한의원 야간 예약") == "분평동 안면홍조 한의원"
    # 접미사가 없으면 그대로 유지
    assert strip_transactional_suffix("청주 여드름 한의원") == "청주 여드름 한의원"
    assert strip_transactional_suffix("청주 체형교정 한의원 추천") == "청주 체형교정 한의원 추천"
    # 서비스 토큰이 남지 않으면 원본 유지 (동네명 단독 검색 방지)
    assert strip_transactional_suffix("봉명동 상담") == "봉명동 상담"


def test_keyword_structure_features_buckets():
    suffix_neigh = keyword_structure_features("복대동 턱비대칭 한의원 비용", "안면비대칭")
    assert suffix_neigh["has_transactional_suffix"] is True
    assert suffix_neigh["has_neighborhood_token"] is True
    assert suffix_neigh["structure_key"] == "structure:안면비대칭:suffix:neigh"

    plain_city = keyword_structure_features("청주 여드름 한의원", "피부/여드름")
    assert plain_city["has_transactional_suffix"] is False
    assert plain_city["has_neighborhood_token"] is False
    assert plain_city["structure_key"] == "structure:피부/여드름:plain:city"


def test_seed_builder_structure_yield_adjustment_uses_evidence():
    # 증거 부족(80건 미만)은 중립
    assert ViralSeedBuilder._structure_yield_adjustment({"total_count": 40, "quality_rate": 0.0}) == 0.0
    # 대량 증거 + 수율 1% 미만이면 강한 패널티
    bad = ViralSeedBuilder._structure_yield_adjustment({"total_count": 1600, "quality_rate": 0.005})
    assert bad == -30.0
    # 같은 수율이라도 증거가 적으면 패널티가 비례 축소
    smaller = ViralSeedBuilder._structure_yield_adjustment({"total_count": 160, "quality_rate": 0.005})
    assert -30.0 < smaller < 0.0
    # 건강한 구조(수율 5%+)는 보너스
    good = ViralSeedBuilder._structure_yield_adjustment({"total_count": 800, "quality_rate": 0.10})
    assert good > 0.0


def test_structure_proven_zero_yield_blocks_only_dead_derivatives():
    """제로수율 파생 구조(동네/접미사)는 하드블록, 기본 plain:city 레인은 보존."""
    block = ViralSeedBuilder._structure_proven_zero_yield
    neigh = {"has_neighborhood_token": True, "has_transactional_suffix": False}
    suffix = {"has_neighborhood_token": False, "has_transactional_suffix": True}
    base = {"has_neighborhood_token": False, "has_transactional_suffix": False}

    # 파생 구조 + 압도적 제로수율 증거 → 차단
    assert block(neigh, {"total_count": 535, "qualified_count": 0, "quality_rate": 0.0}) is True
    assert block(suffix, {"total_count": 400, "qualified_count": 1, "quality_rate": 0.0025}) is True
    # 기본 plain:city 레인은 제로수율이어도 절대 차단 안 함 (진료축 기본 탐사 보존)
    assert block(base, {"total_count": 1000, "qualified_count": 0, "quality_rate": 0.0}) is False
    # 증거 부족(thin signature axis)은 차단 안 함 — 랭킹 패널티만
    assert block(neigh, {"total_count": 80, "qualified_count": 0, "quality_rate": 0.0}) is False
    # 파생 구조라도 수율이 살아있으면 보존
    assert block(neigh, {"total_count": 500, "qualified_count": 21, "quality_rate": 0.042}) is False


def test_is_qualified_viral_outcome_single_definition():
    """단일 workable 판정 — 시드빌더 quality_rate와 Legion 등급게이트가 같은 규칙을 공유."""
    assert is_qualified_viral_outcome("posted", 0.0, 0.0, 0.0) is True
    assert is_qualified_viral_outcome("ai_approved", 0.0, 0.0, 0.0) is True
    # 게시상태 아니어도 임상적합+작업효율 동시 충족이면 workable
    assert is_qualified_viral_outcome("pending", 80.0, 72.0, 0.0) is True
    # 우선순위 120+ & 적합 60+ 도 workable
    assert is_qualified_viral_outcome("pending", 60.0, 60.0, 121.0) is True
    # 저적합 pending은 workable 아님
    assert is_qualified_viral_outcome("pending", 10.0, 10.0, 10.0) is False
    # 한쪽 점수만 높은 부분 충족은 workable 아님
    assert is_qualified_viral_outcome("filtered_out_ad", 80.0, 50.0, 0.0) is False


def _create_dead_structure_viral_targets(conn):
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            matched_keyword TEXT,
            comment_status TEXT,
            score_breakdown TEXT,
            priority_score REAL,
            matched_keyword_category TEXT,
            category TEXT
        )
        """
    )


def _insert_dead_struct_row(conn, idx, keyword, category, status, sb, priority):
    conn.execute(
        "INSERT INTO viral_targets VALUES (?,?,?,?,?,?,?)",
        (
            f"{keyword}-{idx}",
            keyword,
            status,
            json.dumps({"pathfinder_source_keyword": keyword, **sb}, ensure_ascii=False),
            priority,
            category,
            category,
        ),
    )


def test_load_proven_dead_structures_mirrors_structure_block(tmp_path):
    """바이럴 viral_targets에서 제로수율 파생 구조만 dead로 — Legion 등급게이트 단일원천."""
    db_path = tmp_path / "dead_structures.db"
    dead_kw = "봉명동 비염 한의원 예약"            # 호흡기 suffix:neigh (제로수율)
    alive_kw = "복대동 여드름흉터 한의원 상담"      # 흉터 suffix:neigh (수율 살아있음)
    base_kw = "청주 비염 한의원"                    # 호흡기 plain:city (base 레인 — 절대 차단 X)
    thin_kw = "가경동 매선리프팅 한의원 예약"        # 리프팅 suffix:neigh (증거 부족)

    dead_key = keyword_structure_features(dead_kw, "호흡기/알레르기")["structure_key"]
    alive_key = keyword_structure_features(alive_kw, "흉터/여드름흉터")["structure_key"]
    base_key = keyword_structure_features(base_kw, "호흡기/알레르기")["structure_key"]
    thin_key = keyword_structure_features(thin_kw, "리프팅/탄력")["structure_key"]

    with sqlite3.connect(db_path) as conn:
        _create_dead_structure_viral_targets(conn)
        # dead: 파생 + 160건 + qualified 0 → 차단
        for idx in range(160):
            _insert_dead_struct_row(conn, idx, dead_kw, "호흡기/알레르기", "pending", {}, 40.0)
        # alive: 파생 + 200건 중 20건 posted(=qualified) → 보존
        for idx in range(180):
            _insert_dead_struct_row(conn, idx, alive_kw, "흉터/여드름흉터", "pending", {}, 40.0)
        for idx in range(180, 200):
            _insert_dead_struct_row(conn, idx, alive_kw, "흉터/여드름흉터", "posted", {}, 40.0)
        # base plain:city: 200건 제로수율이어도 derivative 아니라 절대 차단 X
        for idx in range(200):
            _insert_dead_struct_row(conn, idx, base_kw, "호흡기/알레르기", "pending", {}, 40.0)
        # thin: 파생이지만 80건뿐 → 증거 부족, 차단 X
        for idx in range(80):
            _insert_dead_struct_row(conn, idx, thin_kw, "리프팅/탄력", "pending", {}, 40.0)
        conn.commit()
        dead = load_proven_dead_structures(conn)

    assert dead_key in dead
    assert alive_key not in dead     # 수율 살아있는 파생 구조는 보존
    assert base_key not in dead      # 기본 plain:city 레인은 절대 차단 안 됨
    assert thin_key not in dead      # 증거 부족 파생은 차단 안 됨 (자동 회복 여지)


def test_load_proven_dead_structures_failsoft_without_table(tmp_path):
    """viral_targets 테이블/증거 없으면 빈 set — 등급 무변경(라이브 누적 전 no-op)."""
    db_path = tmp_path / "empty.db"
    with sqlite3.connect(db_path) as conn:
        assert load_proven_dead_structures(conn) == set()
        conn.execute(
            "CREATE TABLE viral_targets (id TEXT, matched_keyword TEXT, comment_status TEXT)"
        )
        conn.commit()
        assert load_proven_dead_structures(conn) == set()


def test_best_learned_quality_rate_prefers_granular_evidence():
    """가장 granular하고 증거 충분한 버킷의 workable 수율을 채택, 없으면 (0,0)."""
    pick = ViralSeedBuilder._best_learned_quality_rate
    kw = {"total_count": 10, "quality_rate": 0.20}
    axis = {"total_count": 50, "quality_rate": 0.08}
    struct = {"total_count": 400, "quality_rate": 0.03}
    # 키워드 버킷 증거 충분 → 키워드 수율 우선
    assert pick(kw, axis, struct) == (0.20, 10)
    # 키워드 얇음 → axis_lens로
    assert pick({"total_count": 3}, axis, struct) == (0.08, 50)
    # 둘 다 얇음 → structure로
    assert pick({"total_count": 3}, {"total_count": 2}, struct) == (0.03, 400)
    # 전부 증거 부족 → (0,0) no-op
    assert pick({"total_count": 3}, {"total_count": 2}, {"total_count": 5}) == (0.0, 0)


def _fit_row(grade="B", kei=0.1, category="흉터/여드름흉터", keyword="청주 여드름흉터 한의원 후기"):
    return {
        "keyword": keyword, "category": category, "grade": grade, "kei": kei,
        "community_signal": 30.0, "conversion_signal": 10.0, "profile_action_signal": 10.0,
        "local_service_fit_score": 70.0, "content_actionability_score": 65.0,
        "preferred_search_surface": "web_content", "recommended_content_type": "proof_safe_guide",
        "review_intent_type": "none",
    }


def test_viral_seed_fit_score_grade_no_longer_rewards_anti_predictive_tier():
    """역방향 grade bonus 제거 — 동일 신호라면 A가 B보다 높게 점수받지 않음(라이브: A<B)."""
    fit = ViralSeedBuilder._viral_seed_fit_score
    common = dict(adjusted_priority=50.0, viral_readiness_score=40.0, execution_risk_penalty=0.0)
    score_a = fit(_fit_row(grade="A", kei=0.1), **common)
    score_b = fit(_fit_row(grade="B", kei=0.1), **common)
    # 동일 KEI/신호 → 등급만으로 A가 B를 못 이긴다 (예전엔 A=+5 > B=+2)
    assert score_a == score_b
    # 진짜 KEI 수요는 여전히 소폭 보상 (인플레가 아닌 실수요)
    score_kei = fit(_fit_row(grade="A", kei=600.0), **common)
    assert score_kei > score_b


def test_viral_seed_fit_score_rewards_learned_workable_yield():
    """학습된 workable 수율(예측 신호)이 점수를 끌어올린다 — 증거 없으면 no-op."""
    fit = ViralSeedBuilder._viral_seed_fit_score
    common = dict(adjusted_priority=50.0, viral_readiness_score=40.0, execution_risk_penalty=0.0)
    base = fit(_fit_row(), learned_quality_rate=0.0, learned_evidence=0, **common)
    high = fit(_fit_row(), learned_quality_rate=0.15, learned_evidence=40, **common)
    assert high > base
    # 증거(evidence=0)면 수율값이 있어도 무시 (no-op)
    no_evi = fit(_fit_row(), learned_quality_rate=0.15, learned_evidence=0, **common)
    assert no_evi == base


def test_category_demand_factor_rules():
    """Rule A(증거 충분+저acceptance) / Rule B(공급有 제로전환) / 저표본 보존."""
    f = ViralSeedBuilder._category_demand_factor
    # Rule B: 공급 충분(>=150) + 한 번도 작업 안 됨(posted==0) → 프로브 플로어.
    # decided 표본이 얇아도(=4) 트립한다 — gap-fill 제로수요 축을 잡는 핵심.
    factor, reason = f({"total_count": 700, "staff_positive_count": 0,
                        "staff_reviewed_count": 4, "staff_accept_rate": 0.0})
    assert factor == 0.2 and "zero_conversion" in reason
    # Rule A: 표본 충분 + acceptance 구간별 매핑
    assert f({"total_count": 4000, "staff_positive_count": 2,
              "staff_reviewed_count": 299, "staff_accept_rate": 0.007})[0] == 0.25
    assert f({"total_count": 800, "staff_positive_count": 3,
              "staff_reviewed_count": 88, "staff_accept_rate": 0.034})[0] == 0.4
    assert f({"total_count": 3900, "staff_positive_count": 40,
              "staff_reviewed_count": 600, "staff_accept_rate": 0.067})[0] == 0.6
    # acceptance 충분(>=12%) → 게이트 안 함
    assert f({"total_count": 19000, "staff_positive_count": 446,
              "staff_reviewed_count": 3249, "staff_accept_rate": 0.137})[0] == 1.0
    # 저표본 + 공급도 적음(total<150) → 보존(탐사 유지). 어느 룰도 미발동.
    assert f({"total_count": 60, "staff_positive_count": 0,
              "staff_reviewed_count": 5, "staff_accept_rate": 0.0})[0] == 1.0


def test_apply_category_demand_gate_protects_and_redistributes():
    """저수요 축은 프로브 플로어로 축소, 보호 축은 불변, 절감분은 시그니처 축으로."""
    builder = ViralSeedBuilder(db_path="unused.db")  # __init__는 연결하지 않음
    quotas = {
        "흉터/여드름흉터": 12,   # protected signature (boost 대상)
        "안면비대칭": 10,        # protected signature (boost 대상)
        "교통사고": 8,           # protected (고LTV) — 저acceptance여도 절대 게이트 안 됨
        "다이어트": 12,          # protected
        "통증/디스크": 6,        # gate (Rule A)
        "호흡기/알레르기": 3,     # gate (Rule A, 저acceptance)
    }
    feedback = {
        "axis:흉터/여드름흉터": {"total_count": 8000, "staff_positive_count": 80,
                            "staff_reviewed_count": 1000, "staff_accept_rate": 0.08},
        "axis:안면비대칭": {"total_count": 7000, "staff_positive_count": 84,
                        "staff_reviewed_count": 900, "staff_accept_rate": 0.093},
        "axis:교통사고": {"total_count": 15000, "staff_positive_count": 42,
                      "staff_reviewed_count": 1655, "staff_accept_rate": 0.025},
        "axis:다이어트": {"total_count": 19000, "staff_positive_count": 446,
                      "staff_reviewed_count": 3249, "staff_accept_rate": 0.137},
        "axis:통증/디스크": {"total_count": 4000, "staff_positive_count": 2,
                        "staff_reviewed_count": 299, "staff_accept_rate": 0.007},
        "axis:호흡기/알레르기": {"total_count": 700, "staff_positive_count": 1,
                           "staff_reviewed_count": 30, "staff_accept_rate": 0.033},
    }
    adjusted = builder._apply_category_demand_gate(quotas, feedback)

    # 보호 축은 저acceptance여도 불변 (교통사고 = 사용자 명시 보호)
    assert adjusted["교통사고"] == 8
    assert adjusted["다이어트"] == 12
    # 통증/디스크: 0.7% → 0.25 → round(6*0.25)=2
    assert adjusted["통증/디스크"] == 2
    assert builder._category_demand_adjustments["통증/디스크"]["factor"] == 0.25
    # 호흡기: 3.3% → Rule A 0.4 → round(3*0.4)=1 (프로브 플로어 이상)
    assert adjusted["호흡기/알레르기"] == 1
    # freed = (6-2)+(3-1)=6 → 시그니처 축당 max(1, 6//2)=3 재투입
    assert adjusted["흉터/여드름흉터"] == 15
    assert adjusted["안면비대칭"] == 13
    assert builder._category_demand_boosts == {"흉터/여드름흉터": 3, "안면비대칭": 3}
    # 게이트된 어떤 축도 0으로 떨어지지 않음 (자동 회복 가능한 프로브)
    assert all(v >= 1 for v in adjusted.values())

    # 증거(feedback) 없으면 no-op — 라이브 누적 전까지 계획 불변 (다른 게이트와 동일)
    untouched = builder._apply_category_demand_gate({"통증/디스크": 6}, {})
    assert untouched == {"통증/디스크": 6}
    assert builder._category_demand_adjustments == {}


def test_seed_builder_feedback_aggregates_structure_buckets(tmp_path):
    db_path = tmp_path / "structure_feedback.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                matched_keyword TEXT,
                matched_keywords TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER,
                score_breakdown TEXT,
                priority_score REAL,
                matched_keyword_category TEXT,
                category TEXT
            )
            """
        )
        rows = []
        for idx in range(5):
            rows.append(
                (
                    f"suffix-{idx}",
                    "복대동 턱비대칭 한의원 비용",
                    json.dumps(["복대동 턱비대칭 한의원 비용"], ensure_ascii=False),
                    "filtered_out_ad",
                    "",
                    1,
                    json.dumps(
                        {"pathfinder_source_keyword": "복대동 턱비대칭 한의원 비용"},
                        ensure_ascii=False,
                    ),
                    40.0,
                    "안면비대칭",
                    "안면비대칭",
                )
            )
        rows.append(
            (
                "plain-1",
                "청주 안면비대칭",
                json.dumps(["청주 안면비대칭"], ensure_ascii=False),
                "posted",
                "good comment",
                1,
                json.dumps({"pathfinder_source_keyword": "청주 안면비대칭"}, ensure_ascii=False),
                130.0,
                "안면비대칭",
                "안면비대칭",
            )
        )
        conn.executemany(
            "INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    builder = ViralSeedBuilder(db_path=str(db_path))
    feedback = builder._load_keyword_feedback()

    suffix_bucket = feedback["structure:안면비대칭:suffix:neigh"]
    assert suffix_bucket["total_count"] == 5
    assert suffix_bucket["qualified_count"] == 0

    plain_bucket = feedback["structure:안면비대칭:plain:city"]
    assert plain_bucket["total_count"] == 1
    assert plain_bucket["qualified_count"] == 1


def test_viral_hunter_persists_discovery_audit(tmp_path):
    db_path = tmp_path / "audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT
            )
            """
        )
        rows = []
        for idx in range(30):
            rows.append(
                (
                    f"zero-{idx}",
                    "리프팅/탄력",
                    "filtered_out_ad",
                    "봉명동 한방리프팅 비용",
                    json.dumps(["봉명동 한방리프팅 비용"], ensure_ascii=False),
                    "리프팅/탄력",
                    json.dumps(
                        {
                            "pathfinder_source_keyword": "봉명동 한방리프팅 비용",
                            "pathfinder_query_variant": "base",
                            "pathfinder_execution_lens": "cost",
                        },
                        ensure_ascii=False,
                    ),
                    "2026-06-12T10:00:00",
                )
            )
        for idx in range(2):
            rows.append(
                (
                    f"good-{idx}",
                    "피부/여드름",
                    "pending",
                    "청주 여드름 한의원",
                    json.dumps(["청주 여드름 한의원"], ensure_ascii=False),
                    "피부/여드름",
                    json.dumps(
                        {
                            "pathfinder_source_keyword": "청주 여드름 한의원",
                            "pathfinder_query_variant": "community:추천",
                            "pathfinder_execution_lens": "review",
                        },
                        ensure_ascii=False,
                    ),
                    "2026-06-12 10:05:00",
                )
            )
        # 런 시작 이전에 발견된 행은 감사에 포함되지 않아야 한다.
        rows.append(
            (
                "old-1",
                "다이어트",
                "pending",
                "청주 다이어트",
                json.dumps(["청주 다이어트"], ensure_ascii=False),
                "다이어트",
                "{}",
                "2026-06-11 09:00:00",
            )
        )
        conn.executemany("INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=67,
        keyword_count=2,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["summary"]["discovered"] == 32
    assert audit["summary"]["fresh_discovered"] == 32
    assert audit["summary"]["pending"] == 2
    assert audit["summary"]["fresh_pending"] == 2
    assert audit["summary"]["open_pending"] == 2
    assert audit["summary"]["ai_filtered"] == 0
    assert audit["summary"]["post_ai_survival_rate"] == 1.0
    assert audit["summary"]["fresh_pending_rate"] == 2 / 32
    assert audit["summary"]["ad_filtered"] == 30
    assert audit["zero_yield_seeds"][0]["seed"] == "봉명동 한방리프팅 비용"
    assert audit["per_category"]["피부/여드름"]["fresh_pending"] == 2
    assert audit["per_structure"]["structure:리프팅/탄력:suffix:neigh"]["ad_filtered"] == 30
    assert audit["per_query_variant"]["community:추천"]["pending"] == 2
    assert audit["per_query_variant"]["community:추천"]["fresh_pending"] == 2
    assert audit["per_category_lens"]["리프팅/탄력::cost"]["ad_filtered"] == 30
    assert audit["per_category_lens"]["피부/여드름::review"]["pending"] == 2
    assert audit["per_category_lens_query_variant"]["피부/여드름::review::community:추천"]["pending"] == 2

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT source_scan_run_id, keyword_count, discovered_count,
                   pending_count, ad_filtered_count, audit_json
            FROM viral_scan_audits
            """
        ).fetchone()
    assert row[0] == 67
    assert row[1] == 2
    assert row[2] == 32
    assert row[3] == 2
    assert row[4] == 30
    persisted = json.loads(row[5])
    assert persisted["summary"]["pending"] == 2
    assert persisted["summary"]["fresh_pending"] == 2
    assert persisted["summary"]["open_pending"] == 2
    assert persisted["per_category_lens_query_variant"]["피부/여드름::review::community:추천"]["pending"] == 2


def test_viral_hunter_discovery_audit_counts_actionable_statuses_as_yield(tmp_path):
    db_path = tmp_path / "audit_actionable.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT
            )
            """
        )
        rows = []
        for status in ("generated", "posted", "ai_approved"):
            rows.append(
                (
                    f"target-{status}",
                    "흉터/여드름흉터",
                    status,
                    "청주 수술흉터 새살침 후기",
                    json.dumps(["청주 수술흉터 새살침 후기"], ensure_ascii=False),
                    "흉터/여드름흉터",
                    json.dumps(
                        {
                            "pathfinder_source_keyword": "청주 수술흉터 새살침 상담",
                            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
                            "pathfinder_execution_lens": "consultation",
                        },
                        ensure_ascii=False,
                    ),
                    "2026-06-12 10:05:00",
                )
            )
        conn.executemany("INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=68,
        keyword_count=1,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["summary"]["pending"] == 3
    assert audit["summary"]["open_pending"] == 0
    assert audit["summary"]["post_ai_survival_rate"] == 1.0
    assert audit["per_query_variant"]["axis_scar:specific_수술흉터"]["pending"] == 3
    assert audit["per_category_lens"]["흉터/여드름흉터::consultation"]["pending"] == 3


def test_viral_hunter_discovery_audit_splits_open_pending_and_ai_filtered(tmp_path):
    db_path = tmp_path / "audit_post_ai_split.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT
            )
            """
        )
        rows = []
        for status in ("pending", "generated", "filtered_out_ai", "raw_backlog"):
            rows.append(
                (
                    f"target-{status}",
                    "안면비대칭",
                    status,
                    "청주 안면비대칭 한의원 추천",
                    json.dumps(["청주 안면비대칭 한의원 추천"], ensure_ascii=False),
                    "안면비대칭",
                    json.dumps(
                        {
                            "pathfinder_source_keyword": "청주 안면비대칭 한의원 추천",
                            "pathfinder_query_variant": "axis_asymmetry:교정추천",
                            "pathfinder_execution_lens": "review",
                        },
                        ensure_ascii=False,
                    ),
                    "2026-06-12 10:05:00",
                )
            )
        conn.executemany("INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=69,
        keyword_count=1,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["summary"]["discovered"] == 4
    assert audit["summary"]["pending"] == 2
    assert audit["summary"]["open_pending"] == 1
    assert audit["summary"]["ai_filtered"] == 1
    assert audit["summary"]["raw_backlog"] == 1
    assert audit["summary"]["post_ai_survival_rate"] == 2 / 3
    assert audit["per_category"]["안면비대칭"]["open_pending"] == 1
    assert audit["per_category"]["안면비대칭"]["ai_filtered"] == 1
    assert audit["per_query_variant"]["axis_asymmetry:교정추천"]["raw_backlog"] == 1


def test_viral_hunter_discovery_audit_filters_by_source_scan_and_reports_focus_axis_coverage(tmp_path):
    db_path = tmp_path / "audit_scan_scope_focus_axis.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT,
                source_scan_run_id INTEGER
            )
            """
        )
        rows = [
            (
                "scan-70-scar",
                "흉터/여드름흉터",
                "pending",
                "청주 여드름흉터 새살침 상담",
                json.dumps(["청주 여드름흉터 새살침 상담"], ensure_ascii=False),
                "흉터/여드름흉터",
                json.dumps(
                    {
                        "pathfinder_source_keyword": "청주 여드름흉터 새살침 상담",
                        "pathfinder_query_variant": "axis_scar:새살침상담",
                        "pathfinder_execution_lens": "consultation",
                    },
                    ensure_ascii=False,
                ),
                "2026-06-12 10:05:00",
                70,
            ),
            (
                "scan-71-diet",
                "다이어트",
                "pending",
                "청주 다이어트 한약 후기",
                json.dumps(["청주 다이어트 한약 후기"], ensure_ascii=False),
                "다이어트",
                json.dumps(
                    {
                        "pathfinder_source_keyword": "청주 다이어트 한약 후기",
                        "pathfinder_query_variant": "axis_diet:한약후기",
                        "pathfinder_execution_lens": "review",
                    },
                    ensure_ascii=False,
                ),
                "2026-06-12 10:06:00",
                71,
            ),
        ]
        conn.executemany("INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=70,
        keyword_count=1,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["summary"]["discovered"] == 1
    assert set(audit["per_category"]) == {"흉터/여드름흉터"}
    focus = audit["focus_axis_coverage"]
    assert focus["by_category"]["흉터/여드름흉터"]["discovered"] == 1
    assert focus["by_category"]["흉터/여드름흉터"]["open_pending"] == 1
    assert "다이어트" in focus["missing_discovery_categories"]
    assert "다이어트" in focus["missing_actionable_categories"]
    assert "흉터/여드름흉터" not in focus["missing_actionable_categories"]
    assert "흉터/여드름흉터" in focus["priority_focus_categories"]


def test_viral_hunter_discovery_audit_canonicalizes_legacy_scar_category(tmp_path):
    db_path = tmp_path / "scar_audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "scar-1",
                "피부/여드름",
                "pending",
                "청주 여드름흉터 새살침 상담",
                json.dumps(["청주 여드름흉터 새살침 상담"], ensure_ascii=False),
                "피부/여드름",
                json.dumps(
                    {
                        "pathfinder_source_keyword": "청주 여드름흉터 새살침 상담",
                        "pathfinder_query_variant": "consultation:상담",
                    },
                    ensure_ascii=False,
                ),
                "2026-06-12 10:05:00",
            ),
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=67,
        keyword_count=1,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["per_category"]["흉터/여드름흉터"]["discovered"] == 1
    assert "피부/여드름" not in audit["per_category"]
    assert any(
        key.startswith("structure:흉터/여드름흉터:")
        for key in audit["per_structure"]
    )


def test_viral_hunter_discovery_audit_counts_current_run_rediscoveries(tmp_path):
    db_path = tmp_path / "rediscovery_audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                category TEXT,
                comment_status TEXT,
                matched_keyword TEXT,
                matched_keywords TEXT,
                matched_keyword_category TEXT,
                score_breakdown TEXT,
                discovered_at TEXT,
                last_scanned_at TEXT
            )
            """
        )
        rows = [
            (
                "rediscovered-1",
                "흉터/여드름흉터",
                "pending",
                "청주 여드름흉터 새살침 후기",
                json.dumps(["청주 여드름흉터 새살침 후기"], ensure_ascii=False),
                "흉터/여드름흉터",
                json.dumps(
                    {
                        "pathfinder_source_keyword": "청주 여드름흉터 새살침 후기",
                        "pathfinder_query_variant": "axis_scar:새살침후기",
                    },
                    ensure_ascii=False,
                ),
                "2026-06-01 09:00:00",
                "2026-06-12T10:05:00",
            ),
            (
                "new-1",
                "다이어트",
                "filtered_out_ad",
                "청주 다이어트한약 후기",
                json.dumps(["청주 다이어트한약 후기"], ensure_ascii=False),
                "다이어트",
                json.dumps(
                    {
                        "pathfinder_source_keyword": "청주 다이어트한약 후기",
                        "pathfinder_query_variant": "axis_diet:한약후기",
                    },
                    ensure_ascii=False,
                ),
                "2026-06-12 10:06:00",
                "2026-06-12 10:06:00",
            ),
            (
                "old-untouched",
                "피부/여드름",
                "pending",
                "청주 여드름 한의원",
                json.dumps(["청주 여드름 한의원"], ensure_ascii=False),
                "피부/여드름",
                "{}",
                "2026-06-01 09:00:00",
                "2026-06-11 09:00:00",
            ),
        ]
        conn.executemany("INSERT INTO viral_targets VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    audit = hunter._persist_viral_discovery_audit(
        "2026-06-12 00:00:00",
        source_scan_run_id=68,
        keyword_count=2,
        db_path=str(db_path),
    )

    assert audit is not None
    assert audit["summary"]["discovered"] == 2
    assert audit["summary"]["fresh_discovered"] == 1
    assert audit["summary"]["rediscovered"] == 1
    assert audit["summary"]["rediscovered_pending"] == 1
    assert audit["summary"]["fresh_pending"] == 0
    assert audit["per_category"]["흉터/여드름흉터"]["discovered"] == 1
    assert audit["per_category"]["흉터/여드름흉터"]["fresh_discovered"] == 0
    assert audit["per_category"]["흉터/여드름흉터"]["rediscovered"] == 1
    assert audit["per_category"]["흉터/여드름흉터"]["rediscovered_pending"] == 1
    assert audit["per_query_variant"]["axis_scar:새살침후기"]["rediscovered"] == 1
    assert audit["per_query_variant"]["axis_scar:새살침후기"]["fresh_pending"] == 0
    assert "피부/여드름" not in audit["per_category"]



def test_staff_outcome_adjustment_thresholds():
    adjust = ViralSeedBuilder._staff_outcome_adjustment

    assert adjust({}) == 0.0
    assert adjust({"staff_reviewed_count": 7, "staff_accept_rate": 0.0}) == 0.0
    assert adjust({"staff_reviewed_count": 40, "staff_accept_rate": 0.04}) == -14.0
    assert adjust({"staff_reviewed_count": 40, "staff_accept_rate": 0.08}) == -8.0
    assert adjust({"staff_reviewed_count": 40, "staff_accept_rate": 0.15}) == 0.0
    assert adjust({"staff_reviewed_count": 40, "staff_accept_rate": 0.22}) == 5.0
    assert adjust({"staff_reviewed_count": 40, "staff_accept_rate": 0.40}) > 5.0

    # 증거가 얇으면 같은 승인율이라도 감점 폭이 줄어든다.
    thin = adjust({"staff_reviewed_count": 8, "staff_accept_rate": 0.0})
    assert -14.0 < thin < 0.0


def test_viral_seed_builder_uses_staff_outcomes_to_reorder_lanes(tmp_path):
    db_path = tmp_path / "seed_builder_staff_outcomes.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY,
                scan_type TEXT,
                status TEXT,
                completed_at TEXT
            );
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                category TEXT,
                grade TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                kei REAL,
                priority_v3 REAL,
                search_intent TEXT,
                last_scan_run_id INTEGER,
                business_core INTEGER,
                status TEXT
            );
            CREATE TABLE viral_targets (
                id TEXT PRIMARY KEY,
                url TEXT UNIQUE,
                matched_keyword TEXT,
                comment_status TEXT,
                generated_comment TEXT,
                scan_count INTEGER
            );
            CREATE TABLE viral_target_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                rating TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (1, 'legion', 'completed', '2026-06-12');
            """
        )
        conn.executemany(
            """
            INSERT INTO keyword_insights(
                keyword, category, grade, search_volume, document_count,
                kei, priority_v3, search_intent, last_scan_run_id, business_core, status
            ) VALUES (?, 'cat', 'A', 100, 1000, 10, 200.0, ?, 1, 1, 'active')
            """,
            [
                ("alpha lane keyword", "transactional"),
                ("beta lane keyword", "informational"),
                ("gamma lane keyword", "commercial"),
            ],
        )
        # alpha: 직원이 20개 전부 skip — 발견시점 점수와 무관하게 강등돼야 한다.
        conn.executemany(
            "INSERT INTO viral_targets VALUES (?, ?, 'alpha lane keyword', 'skipped', '', 1)",
            [(f"alpha-{i}", f"https://example.com/alpha/{i}") for i in range(20)],
        )
        # beta: 20개 중 8개 posted — 승인율 40%로 보너스 구간.
        conn.executemany(
            "INSERT INTO viral_targets VALUES (?, ?, 'beta lane keyword', ?, '', 1)",
            [
                (f"beta-{i}", f"https://example.com/beta/{i}", "posted" if i < 8 else "skipped")
                for i in range(20)
            ],
        )
        # gamma: 상태는 pending이지만 직원 rating 'good' 10개 — 명시 피드백도 양성 신호.
        conn.executemany(
            "INSERT INTO viral_targets VALUES (?, ?, 'gamma lane keyword', 'pending', '', 1)",
            [(f"gamma-{i}", f"https://example.com/gamma/{i}") for i in range(10)],
        )
        conn.executemany(
            "INSERT INTO viral_target_feedback(target_id, rating) VALUES (?, 'good')",
            [(f"gamma-{i}",) for i in range(10)],
        )
        conn.commit()

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=1, quotas={"cat": 3})
    by_keyword = {seed.keyword: seed for seed in seeds}

    assert set(by_keyword) == {"alpha lane keyword", "beta lane keyword", "gamma lane keyword"}

    alpha = by_keyword["alpha lane keyword"]
    beta = by_keyword["beta lane keyword"]
    gamma = by_keyword["gamma lane keyword"]

    assert alpha.historical_staff_reviewed_count == 20
    assert alpha.historical_staff_accept_rate == 0.0
    assert alpha.staff_outcome_adjustment < 0

    assert beta.historical_staff_reviewed_count == 20
    assert beta.historical_staff_accept_rate == 0.4
    assert beta.staff_outcome_adjustment > 0

    assert gamma.historical_staff_reviewed_count == 10
    assert gamma.historical_staff_accept_rate == 1.0
    assert gamma.staff_outcome_adjustment > 0

    keywords_in_order = [seed.keyword for seed in seeds]
    assert keywords_in_order.index("beta lane keyword") < keywords_in_order.index("alpha lane keyword")
    assert keywords_in_order.index("gamma lane keyword") < keywords_in_order.index("alpha lane keyword")


def _create_rescue_viral_targets_table(conn):
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            platform TEXT,
            url TEXT UNIQUE,
            title TEXT,
            content_preview TEXT,
            matched_keywords TEXT,
            matched_keyword TEXT,
            category TEXT,
            is_commentable INTEGER,
            generated_comment TEXT,
            priority_score REAL,
            author TEXT,
            posted_at TEXT,
            comment_status TEXT,
            discovered_at TEXT,
            source_scan_run_id INTEGER,
            matched_keyword_grade TEXT,
            matched_keyword_kei REAL,
            matched_keyword_priority REAL,
            matched_keyword_category TEXT
        )
        """
    )


def _insert_rescue_target(conn, target_id, url, category, status, priority, discovered_at):
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, platform, url, title, content_preview, matched_keywords, matched_keyword,
            category, is_commentable, generated_comment, priority_score, author, posted_at,
            comment_status, discovered_at, source_scan_run_id, matched_keyword_grade,
            matched_keyword_kei, matched_keyword_priority, matched_keyword_category
        ) VALUES (?, 'cafe', ?, '청주 후기 질문글', '실제 사용자 질문 본문', '["청주 키워드"]', '청주 키워드',
                  ?, 1, '', ?, 'user', '', ?, ?, 60, 'A', 10.0, 100.0, ?)
        """,
        (target_id, url, category, priority, status, discovered_at, category),
    )


def test_viral_hunter_loads_backlog_rescue_targets(tmp_path):
    from datetime import datetime
    from types import SimpleNamespace

    db_path = tmp_path / "rescue.db"
    now = datetime.now().isoformat()
    with sqlite3.connect(db_path) as conn:
        _create_rescue_viral_targets_table(conn)
        _insert_rescue_target(conn, "pibu-90", "https://cafe.naver.com/t/90", "피부", "raw_backlog", 90, now)
        _insert_rescue_target(conn, "pibu-80", "https://cafe.naver.com/t/80", "피부", "raw_backlog", 80, now)
        _insert_rescue_target(conn, "pibu-70", "https://cafe.naver.com/t/70", "피부", "raw_backlog", 70, now)
        _insert_rescue_target(conn, "asym-10", "https://cafe.naver.com/t/asym", "안면비대칭", "needs_ai_retry", 10, now)
        # 레스큐 대상이 아니어야 하는 행들
        _insert_rescue_target(conn, "pending-99", "https://cafe.naver.com/t/pending", "피부", "pending", 99, now)
        _insert_rescue_target(conn, "old-95", "https://cafe.naver.com/t/old", "피부", "raw_backlog", 95, "2020-01-01T00:00:00")
        _insert_rescue_target(conn, "dup-97", "https://cafe.naver.com/t/dup", "피부", "raw_backlog", 97, now)
        conn.commit()

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))

    exclude = {canonicalize_viral_url("https://cafe.naver.com/t/dup") or "https://cafe.naver.com/t/dup"}
    rescued = hunter._load_backlog_rescue_targets(3, exclude_urls=exclude)

    rescued_urls = {target.url for target in rescued}

    assert len(rescued) == 3
    # 카테고리 floor 덕분에 저점수 비대칭 needs_ai_retry도 포함된다.
    assert "https://cafe.naver.com/t/asym" in rescued_urls
    assert "https://cafe.naver.com/t/90" in rescued_urls
    assert "https://cafe.naver.com/t/80" in rescued_urls
    # pending/오래된 행/제외 URL은 레스큐되지 않는다.
    assert "https://cafe.naver.com/t/pending" not in rescued_urls
    assert "https://cafe.naver.com/t/old" not in rescued_urls
    assert "https://cafe.naver.com/t/dup" not in rescued_urls


def test_unified_analysis_parallel_persists_ai_unsuitable(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.saved = []

        def insert_viral_target(self, data):
            self.saved.append(data)
            return True

    monkeypatch.setattr(
        AICommentGenerator,
        "_load_prompts",
        lambda self: {"unified_analysis": {"template": "{posts_formatted}", "batch_size": 25}},
    )
    monkeypatch.setattr(
        viral_hunter,
        "ai_generate",
        lambda *args, **kwargs: (
            "POST_ID: 1\nSUITABLE: true\nSCORE: 80\nTYPE: consultation\n"
            "COMPETITOR: false\n---\n"
            "POST_ID: 2\nSUITABLE: false\nSCORE: 10\nTYPE: unknown\n---"
        ),
    )

    suitable_target = ViralTarget(
        platform="cafe",
        url="https://cafe.naver.com/suit/1",
        title="다이어트 한약 후기 궁금해요",
        content_preview="요즘 살이 너무 쪄서 고민이에요. 효과 있을까요?",
        matched_keywords=["청주 다이어트"],
        category="다이어트",
    )
    unsuitable_target = ViralTarget(
        platform="blog",
        url="https://blog.naver.com/unsuit/2",
        title="오늘의 일상 기록",
        content_preview="그냥 일기입니다.",
        matched_keywords=["청주 다이어트"],
        category="다이어트",
    )

    generator = AICommentGenerator.__new__(AICommentGenerator)
    fake_db = FakeDB()
    results = generator.unified_analysis_parallel(
        [suitable_target, unsuitable_target],
        batch_size=25,
        max_workers=1,
        db=fake_db,
    )

    result_urls = {target.url for target in results}
    assert "https://cafe.naver.com/suit/1" in result_urls
    assert "https://blog.naver.com/unsuit/2" not in result_urls

    # AI 부적합 판정은 침묵 폐기가 아니라 filtered_out_ai로 영속화돼야 한다.
    unsuitable_saved = [
        row for row in fake_db.saved if row.get("url") == "https://blog.naver.com/unsuit/2"
    ]
    assert unsuitable_saved
    assert unsuitable_saved[-1]["comment_status"] == "filtered_out_ai"
    assert unsuitable_target.ai_reviewed is True
    assert unsuitable_target.is_commentable is False
    assert (unsuitable_target.score_breakdown or {}).get("ai_verdict") == "unsuitable"



def test_strip_region_tokens_removes_local_anchors_only():
    from core_services.viral_seed_builder import strip_region_tokens

    assert strip_region_tokens("청주 여드름흉터 한의원") == "여드름흉터 한의원"
    assert strip_region_tokens("복대동 다이어트 한약") == "다이어트 한약"
    assert strip_region_tokens("청주시 오창 안면비대칭 교정") == "안면비대칭 교정"
    # 지역 토큰만 남으면 빈 문자열 — 호출자는 이 시드를 건너뛰어야 한다.
    assert strip_region_tokens("율량동") == ""
    # 지역 토큰이 없으면 원문 유지
    assert strip_region_tokens("다이어트 한약 효과") == "다이어트 한약 효과"


def test_viral_hunter_skips_patient_voice_for_non_user_surface_axis():
    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.keyword_context = {
        "청주 교통사고 한의원": {
            "category": "교통사고",
            "viral_readiness_score": 70,
            "community_signal": 45,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "review_intent_type": "none",
            "execution_lens": "community",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 교통사고 한의원", 100)

    # 교통사고는 사용자-표면 중심 축이 아니므로 비지역 변형을 보내지 않는다.
    assert [plan["query"] for plan in plans] == [
        "청주 교통사고 한의원",
        "청주 교통사고 한의원 추천",
        "청주 교통사고 후유증 한의원 추천",
    ]
    assert plans[2]["variant"] == "axis_traffic:후유증추천"
    assert all(plan["variant"] != "patient_voice_kin" for plan in plans)


def test_variant_proven_zero_yield_thresholds():
    proven = viral_hunter.ViralHunter._variant_proven_zero_yield

    assert proven({"discovered": 60, "pending": 0}) is True
    assert proven({"discovered": 59, "pending": 0}) is False
    assert proven({"discovered": 60, "pending": 1}) is False
    assert proven({"discovered": 300, "pending": 1}) is True  # 0.33% < 0.4%
    assert proven({"discovered": 300, "pending": 2}) is False
    assert proven({}) is False


def test_viral_hunter_variant_yield_gate_drops_proven_zero_yield_companions(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "variant_yield.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        audit_json = json.dumps(
            {
                "per_query_variant": {
                    "axis_skin:아토피후기": {"discovered": 80, "pending": 0, "ad_filtered": 30},
                    "axis_skin:피부질환추천": {"discovered": 80, "pending": 6, "ad_filtered": 10},
                }
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-12 09:00:00", "2026-06-12 10:00:00", audit_json),
        )
        conn.commit()

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter.keyword_context = {
        "청주 여드름 한의원 추천": {
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 추천", 100)
    variants = [plan["variant"] for plan in plans]

    # 제로수율이 증명된 동반 변형만 차단되고, 기준/건강 변형은 유지된다.
    assert "axis_skin:아토피후기" not in variants
    assert "axis_skin:피부질환추천" in variants
    assert variants[0] == "base"
    assert "patient_voice_kin" in variants
    assert hunter._variant_drop_counts == {"axis_skin:아토피후기": 1}


def test_viral_hunter_variant_yield_gate_prefers_category_lens_specific_evidence(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "variant_lane_yield.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        audit_json = json.dumps(
            {
                "per_query_variant": {
                    "axis_skin:아토피후기": {"discovered": 100, "pending": 0, "ad_filtered": 70},
                },
                "per_category_lens_query_variant": {
                    "피부/여드름::review::axis_skin:아토피후기": {
                        "discovered": 8,
                        "pending": 1,
                        "ad_filtered": 2,
                    },
                },
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-12 09:00:00", "2026-06-12 10:00:00", audit_json),
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter.keyword_context = {
        "청주 여드름 한의원 추천": {
            "category": "피부/여드름",
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 추천", 100)
    variants = [plan["variant"] for plan in plans]

    assert "axis_skin:아토피후기" in variants
    assert getattr(hunter, "_variant_drop_counts", {}) == {}


def test_viral_hunter_variant_yield_gate_drops_category_lens_zero_yield_even_when_global_survives(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "variant_lane_zero.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        audit_json = json.dumps(
            {
                "per_query_variant": {
                    "axis_skin:아토피후기": {"discovered": 100, "pending": 8, "ad_filtered": 20},
                },
                "per_category_lens_query_variant": {
                    "피부/여드름::review::axis_skin:아토피후기": {
                        "discovered": 70,
                        "pending": 0,
                        "ad_filtered": 60,
                    },
                },
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-12 09:00:00", "2026-06-12 10:00:00", audit_json),
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter.keyword_context = {
        "청주 여드름 한의원 추천": {
            "category": "피부/여드름",
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 추천", 100)
    variants = [plan["variant"] for plan in plans]

    assert "axis_skin:아토피후기" not in variants
    assert hunter._variant_drop_counts == {"axis_skin:아토피후기": 1}


def test_viral_hunter_variant_yield_gate_uses_fresh_yield_over_rediscovered_pending(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "variant_fresh_yield.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        audit_json = json.dumps(
            {
                "per_query_variant": {
                    "axis_skin:아토피후기": {
                        "discovered": 180,
                        "fresh_discovered": 80,
                        "pending": 25,
                        "fresh_pending": 0,
                        "rediscovered": 100,
                        "rediscovered_pending": 25,
                        "ad_filtered": 50,
                    },
                },
                "per_category_lens_query_variant": {
                    "피부/여드름::review::axis_skin:아토피후기": {
                        "discovered": 180,
                        "fresh_discovered": 80,
                        "pending": 25,
                        "fresh_pending": 0,
                        "rediscovered": 100,
                        "rediscovered_pending": 25,
                        "ad_filtered": 50,
                    },
                },
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-14 09:00:00", "2026-06-14 10:00:00", audit_json),
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter.keyword_context = {
        "청주 여드름 한의원 추천": {
            "category": "피부/여드름",
            "viral_readiness_score": 72,
            "community_signal": 64,
            "conversion_signal": 20,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "review",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름 한의원 추천", 100)
    variants = [plan["variant"] for plan in plans]

    assert "axis_skin:아토피후기" not in variants
    assert hunter._variant_drop_counts == {"axis_skin:아토피후기": 1}


def test_viral_hunter_variant_yield_gate_does_not_drop_patient_voice_from_global_only_evidence(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "patient_voice_global_only.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        audit_json = json.dumps(
            {
                "per_query_variant": {
                    "patient_voice_kin": {"discovered": 90, "pending": 0, "ad_filtered": 60},
                }
            },
            ensure_ascii=False,
        )
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-12 09:00:00", "2026-06-12 10:00:00", audit_json),
        )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter.keyword_context = {
        "청주 여드름흉터 비용": {
            "category": "흉터/여드름흉터",
            "viral_readiness_score": 72,
            "community_signal": 35,
            "conversion_signal": 55,
            "medical_ad_risk_score": 5,
            "content_actionability_score": 80,
            "preferred_search_surface": "hybrid_local_content",
            "recommended_content_type": "proof_safe_guide",
            "execution_lens": "cost",
        }
    }

    plans = hunter._search_queries_for_keyword("청주 여드름흉터 비용", 100)
    variants = [plan["variant"] for plan in plans]

    assert "patient_voice_kin" in variants
    assert getattr(hunter, "_variant_drop_counts", {}) == {}


def test_viral_hunter_specific_axis_variant_needs_two_bad_runs_before_drop(tmp_path):
    from types import SimpleNamespace

    db_path = tmp_path / "specific_variant_cold_start.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE viral_scan_audits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_started_at TEXT,
                created_at TEXT,
                audit_json TEXT
            )
            """
        )
        one_bad_run = {
            "per_category_lens_query_variant": {
                "흉터/여드름흉터::consultation::axis_scar:specific_수술흉터": {
                    "discovered": 80,
                    "pending": 0,
                    "ad_filtered": 45,
                }
            }
        }
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-12 09:00:00", "2026-06-12 10:00:00", json.dumps(one_bad_run, ensure_ascii=False)),
        )

    def make_hunter():
        hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
        hunter.db = SimpleNamespace(db_path=str(db_path))
        hunter.keyword_context = {
            "청주 수술흉터 새살침 상담": {
                "category": "흉터/여드름흉터",
                "viral_readiness_score": 73,
                "community_signal": 42,
                "conversion_signal": 58,
                "medical_ad_risk_score": 5,
                "content_actionability_score": 82,
                "preferred_search_surface": "hybrid_local_content",
                "recommended_content_type": "proof_safe_guide",
                "execution_lens": "consultation",
            }
        }
        return hunter

    first_hunter = make_hunter()
    first_variants = [
        plan["variant"]
        for plan in first_hunter._search_queries_for_keyword("청주 수술흉터 새살침 상담", 100)
    ]

    assert "axis_scar:specific_수술흉터" in first_variants
    assert getattr(first_hunter, "_variant_drop_counts", {}) == {}

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO viral_scan_audits (run_started_at, created_at, audit_json) VALUES (?, ?, ?)",
            ("2026-06-13 09:00:00", "2026-06-13 10:00:00", json.dumps(one_bad_run, ensure_ascii=False)),
        )

    second_hunter = make_hunter()
    second_variants = [
        plan["variant"]
        for plan in second_hunter._search_queries_for_keyword("청주 수술흉터 새살침 상담", 100)
    ]

    assert "axis_scar:specific_수술흉터" not in second_variants
    assert second_hunter._variant_drop_counts == {"axis_scar:specific_수술흉터": 1}



def test_blog_postview_url_conversion():
    convert = viral_hunter.blog_postview_url

    assert convert("https://blog.naver.com/risk4wu/224301094763") == (
        "https://blog.naver.com/PostView.naver?blogId=risk4wu&logNo=224301094763"
    )
    already = "https://blog.naver.com/PostView.naver?blogId=abc&logNo=224301094763"
    assert convert(already) == already
    assert convert("https://cafe.naver.com/somecafe/123") is None
    assert convert("") is None


def test_extract_kin_body_includes_question_and_answers():
    html = (
        '<html><body>'
        '<div class="questionDetail">청주에서 여드름흉터 <b>새살침</b> 받아본 분 계신가요? 효과 궁금합니다.</div>'
        '<div class="answerDetail">안녕하세요, 상담한의사입니다. 병원 위치 | 진료 예약 | 문의 전화 주세요.</div>'
        '<div class="answerDetail">저는 그냥 시간이 지나니 옅어졌어요.</div>'
        '<div class="answerDetail">세 번째 답변은 잘려야 합니다.</div>'
        '</body></html>'
    )

    body = viral_hunter.extract_kin_body_from_html(html, max_answers=2)

    assert "여드름흉터" in body and "새살침" in body
    assert "[기존답변1]" in body and "진료 예약" in body
    assert "[기존답변2]" in body and "옅어졌어요" in body
    assert "세 번째" not in body


def test_extract_blog_body_from_html_supports_both_editors():
    smart = '<div class="se-main-container">추나치료 <span>청주한의원</span> 소개해 드릴게요.</div>'
    legacy = '<div id="postViewArea">구버전 에디터 본문입니다.</div>'

    assert "추나치료" in viral_hunter.extract_blog_body_from_html(smart)
    assert "구버전 에디터" in viral_hunter.extract_blog_body_from_html(legacy)
    assert viral_hunter.extract_blog_body_from_html("") == ""


def test_viral_hunter_enriches_and_regates_ai_targets(monkeypatch):
    from types import SimpleNamespace

    class FakeDB:
        def __init__(self):
            self.saved = []

        def insert_viral_target(self, data):
            self.saved.append(data)
            return True

    kin_html = (
        '<div class="questionDetail">턱관절 비대칭 때문에 고민이 많아요. 청주에 잘하는 곳 있을까요? '
        '두통도 같이 와서 일상생활이 힘듭니다. 교정으로 좋아질 수 있는지 궁금해요.</div>'
        '<div class="answerDetail">저도 비슷했는데 꾸준히 치료받고 나아졌어요.</div>'
    )
    # planted 질문: 광고 신호가 질문 세그먼트 자체에 있다 → 로컬 게이트 재탈락 대상.
    promo_kin_html = (
        '<div class="questionDetail">PROMO 지금 바로 예약하세요 특별 할인!</div>'
        '<div class="answerDetail">광고 같네요.</div>'
    )
    # 자연 질문 + 광고성 답변: 게이트는 질문만 보고 통과시키고 AI가 전체를 판단한다.
    answer_promo_kin_html = (
        '<div class="questionDetail">다이어트 한약 먹어도 되나요? 부작용 걱정돼요.</div>'
        '<div class="answerDetail">PROMO 저희 한의원으로 예약 주세요!</div>'
    )

    cafe_article_json = json.dumps({
        "result": {
            "article": {
                "contentHtml": "<p>주성 율량 주변에 교통사고로 입원할 수 있는 한방병원 있을까요? 추천 부탁드려요.</p>"
            }
        }
    }, ensure_ascii=False)

    def fake_fetcher(url):
        if "promo-question" in url:
            return promo_kin_html
        if "promo-answer" in url:
            return answer_promo_kin_html
        if "cjpublic" in url:
            return cafe_article_json
        if "cafe-articleapi" in url:
            return ""  # 멤버 전용 카페 401 시뮬레이션
        return kin_html

    # 게이트 내부 규칙에 결합하지 않도록, 재검사 자체는 마커 기반으로 검증한다.
    monkeypatch.setattr(
        viral_hunter.CommentableFilter,
        "apply_final_reject",
        staticmethod(
            lambda t: "ad_detected"
            if "PROMO" in (t.content_preview or "").split("[기존답변", 1)[0]
            else None
        ),
    )

    enrich_me = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=1",
        title="턱관절 비대칭 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 안면비대칭"],
        category="안면비대칭",
    )
    promo_revealed = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=promo-question",
        title="다이어트 한약 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 다이어트"],
        category="다이어트",
    )
    answer_promo_survives = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=promo-answer",
        title="다이어트 한약 부작용 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 다이어트"],
        category="다이어트",
    )
    cafe_member_only = ViralTarget(
        platform="cafe",
        url="https://cafe.naver.com/memberonly/123456",
        title="멤버 전용 카페 글",
        content_preview="짧은 snippet",
        matched_keywords=["청주 다이어트"],
        category="다이어트",
    )
    cafe_public = ViralTarget(
        platform="cafe",
        url="https://cafe.naver.com/cjpublic/12345",
        title="공개 카페 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 교통사고"],
        category="교통사고",
    )
    already_rich = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=2",
        title="이미 풍부한 글",
        content_preview="가" * 400,
        matched_keywords=["청주 피부"],
        category="피부/여드름",
    )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = FakeDB()

    kept, stats = hunter._enrich_and_regate_ai_targets(
        [enrich_me, promo_revealed, answer_promo_survives, cafe_member_only, cafe_public, already_rich],
        fetcher=fake_fetcher,
    )

    # 보강: kin 3건 + cafe 2건 fetch. 멤버 전용 cafe(빈 응답)와 이미 풍부한 글은 그대로.
    assert stats["fetched"] == 5
    assert stats["enriched"] == 4
    assert len(enrich_me.content_preview) > 100
    assert "[기존답변1]" in enrich_me.content_preview
    assert (enrich_me.score_breakdown or {}).get("body_enriched") == "kin"
    assert cafe_member_only.content_preview == "짧은 snippet"
    assert "교통사고로 입원" in cafe_public.content_preview
    assert (cafe_public.score_breakdown or {}).get("body_enriched") == "cafe"
    assert len(already_rich.content_preview) == 400

    # planted 질문(질문 세그먼트에 광고 신호)은 AI 예산 소모 전에 재탈락 + 영속화.
    assert stats["regate_rejected"] == 1
    kept_urls = {t.url for t in kept}
    assert promo_revealed.url not in kept_urls
    assert enrich_me.url in kept_urls
    assert cafe_member_only.url in kept_urls
    assert cafe_public.url in kept_urls
    assert hunter.db.saved and hunter.db.saved[0]["url"] == promo_revealed.url

    # 자연 질문 + 광고성 '답변'은 로컬 게이트가 죽이지 않는다 — AI가 전체 본문으로
    # planted 여부/경쟁사 역공략 기회를 판단한다. (답변 텍스트는 preview에 유지)
    assert answer_promo_survives.url in kept_urls
    assert "[기존답변1]" in answer_promo_survives.content_preview
    assert "PROMO" in answer_promo_survives.content_preview


def test_viral_hunter_refills_ai_budget_after_enrichment_reject(monkeypatch):
    class FakeDB:
        def __init__(self):
            self.saved = []

        def insert_viral_target(self, data):
            self.saved.append(data)
            return True

    def fake_fetcher(url):
        if "reject" in url:
            return '<div class="questionDetail">PROMO 광고성 질문입니다.</div>'
        return '<div class="questionDetail">청주 여드름흉터 새살침 후기 궁금합니다. 추천 부탁드려요.</div>'

    monkeypatch.setattr(
        viral_hunter.CommentableFilter,
        "apply_final_reject",
        staticmethod(lambda t: "ad_detected" if "PROMO" in (t.content_preview or "") else None),
    )

    rejected_ai = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=reject",
        title="reject",
        content_preview="짧은 snippet",
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=150,
        score_breakdown={"pathfinder_axis_fit_score": 80, "pathfinder_lens_fit_score": 80},
    )
    already_kept = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=kept",
        title="kept",
        content_preview="가" * 400,
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=120,
        score_breakdown={"pathfinder_axis_fit_score": 85, "pathfinder_lens_fit_score": 80},
    )
    refill_best = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=refill-best",
        title="refill best",
        content_preview="짧은 snippet",
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=118,
        score_breakdown={"pathfinder_axis_fit_score": 95, "pathfinder_lens_fit_score": 92},
    )
    refill_weaker = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=refill-weak",
        title="refill weak",
        content_preview="짧은 snippet",
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        priority_score=119,
        score_breakdown={"pathfinder_axis_fit_score": 40, "pathfinder_lens_fit_score": 40},
    )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = FakeDB()

    enriched, enrich_stats = hunter._enrich_and_regate_ai_targets(
        [rejected_ai, already_kept],
        max_fetch=3,
        fetcher=fake_fetcher,
    )
    ai_targets, rest_targets, refill_stats = hunter._refill_ai_targets_after_enrichment(
        enriched,
        [refill_weaker, refill_best],
        target_count=2,
        max_fetch=3 - enrich_stats["fetched"],
        fetcher=fake_fetcher,
    )

    assert rejected_ai.url not in {target.url for target in ai_targets}
    assert refill_best.url in {target.url for target in ai_targets}
    assert refill_weaker.url in {target.url for target in rest_targets}
    assert refill_stats["attempted"] == 1
    assert refill_stats["kept"] == 1
    assert refill_stats["rejected"] == 0
    assert hunter.db.saved and hunter.db.saved[0]["url"] == rejected_ai.url


def test_cafe_article_api_url_conversion():
    convert = viral_hunter.cafe_article_api_url

    assert convert("http://cafe.naver.com/cjcjmom/3298659") == (
        "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/cjcjmom/articles/3298659?useCafeId=false"
    )
    legacy = "https://cafe.naver.com/ArticleRead.nhn?clubid=11569471&articleid=3298659"
    assert convert(legacy) == (
        "https://apis.naver.com/cafe-web/cafe-articleapi/v2.1/cafes/11569471/articles/3298659?useCafeId=true"
    )
    assert convert("https://cafe.naver.com/somecafe") is None
    assert convert("https://blog.naver.com/abc/123456") is None


def test_extract_cafe_body_from_json():
    valid = json.dumps({
        "result": {"article": {"contentHtml": "<p>청주 다이어트 한약 <b>후기</b> 궁금해요</p>"}}
    }, ensure_ascii=False)

    body = viral_hunter.extract_cafe_body_from_json(valid)
    assert "다이어트 한약" in body and "후기" in body

    assert viral_hunter.extract_cafe_body_from_json("not-json") == ""
    assert viral_hunter.extract_cafe_body_from_json(json.dumps({"result": {}})) == ""
    assert viral_hunter.extract_cafe_body_from_json("") == ""


def test_extract_post_dates_from_surfaces():
    """KIN/blog/cafe 공개 표면에서 게시일을 YYYYMMDD로 복원 (라이브 마크업 기준)."""
    kin_html = (
        '<div class="questionInfo"><span class="infoItem">조회수 46</span>'
        '<span class="infoItem"><span class="blind">작성일</span>2026.05.25</span></div>'
        '<div class="questionDetail">청주 다이어트 한약 질문이에요</div>'
    )
    assert viral_hunter.extract_kin_post_date_from_html(kin_html) == "20260525"
    assert viral_hunter.extract_kin_view_count_from_html(kin_html) == 46

    blog_html = '<div><span class="se_publishDate pcol2">2026. 6. 10. 2:49</span></div>'
    assert viral_hunter.extract_blog_post_date_from_html(blog_html) == "20260610"

    # writeDate epoch ms — 정오(UTC)로 잡아 KST(+9) day-boundary flakiness 회피.
    cafe_json = json.dumps({
        "result": {"article": {"writeDate": 1710504000000, "commentCount": 3, "readCount": 594}}
    })
    assert viral_hunter.extract_cafe_post_date_from_json(cafe_json) == "20240315"

    # 게시일 마크업이 없으면 빈 문자열로 fail-soft.
    assert viral_hunter.extract_kin_post_date_from_html("<div>no date</div>") == ""
    assert viral_hunter.extract_blog_post_date_from_html("") == ""
    assert viral_hunter.extract_cafe_post_date_from_json(json.dumps({"result": {}})) == ""
    # 잘못된 날짜(13월)는 거부.
    assert viral_hunter.extract_blog_post_date_from_html('<span class="date">2026.13.40</span>') == ""


def test_fetch_naver_post_detail_collects_date_body_and_metrics():
    """fetch_naver_post_detail은 한 번의 fetch로 본문+게시일+참여 지표를 모은다."""
    kin_html = (
        '<div class="questionInfo"><span class="infoItem"><span class="blind">작성일</span>'
        '2015.01.08</span></div>'
        '<div class="questionDetail">추나요법으로 허리치료 되는지 궁금합니다.</div>'
        '<div class="answerDetail">답변1</div><div class="answerDetail">답변2</div>'
    )

    detail = viral_hunter.fetch_naver_post_detail(
        "https://kin.naver.com/qna/detail.naver?docId=214897865",
        "kin",
        fetcher=lambda url: kin_html,
    )
    assert detail["posted_date"] == "20150108"
    assert "허리치료" in detail["body"]
    assert detail["comment_count"] == 2

    cafe_json = json.dumps({
        "result": {"article": {
            "contentHtml": "<p>교통사고 입원 한방병원 추천해주세요</p>",
            "writeDate": 1710504000000, "commentCount": 5, "readCount": 800,
        }}
    })
    cafe_detail = viral_hunter.fetch_naver_post_detail(
        "https://cafe.naver.com/cjpublic/12345", "cafe", fetcher=lambda url: cafe_json,
    )
    assert cafe_detail["posted_date"] == "20240315"
    assert cafe_detail["comment_count"] == 5
    assert cafe_detail["view_count"] == 800
    assert "교통사고 입원" in cafe_detail["body"]


def test_enrichment_regate_expires_stale_dated_post():
    """검색 API가 날짜를 안 줘 '신선'으로 통과한 글이, 게시일 복원 후 타이밍 만료된다."""
    from datetime import datetime

    class FakeDB:
        def __init__(self):
            self.saved = []

        def insert_viral_target(self, data):
            self.saved.append(data)
            return True

    # 본문은 충분히 길어 본문 재fetch 대상은 아니지만(>=300), snippet<300이라 fetch는 됨.
    # 핵심: 게시일이 2015년으로 밝혀지면 타이밍 윈도우 점수가 만료 임계 아래로 떨어진다.
    old_kin_html = (
        '<div class="questionInfo"><span class="infoItem"><span class="blind">작성일</span>'
        '2015.01.08</span></div>'
        '<div class="questionDetail">추나요법으로 허리치료 되는지 궁금합니다. 청주에서 잘하는 곳 알려주세요.</div>'
        '<div class="answerDetail">답1</div><div class="answerDetail">답2</div>'
        '<div class="answerDetail">답3</div><div class="answerDetail">답4</div>'
    )
    fresh_kin_html = (
        '<div class="questionInfo"><span class="infoItem"><span class="blind">작성일</span>'
        + datetime.now().strftime("%Y.%m.%d")
        + '</span></div>'
        '<div class="questionDetail">청주 디스크 한의원 추천 부탁드려요. 어제부터 허리가 너무 아픕니다.</div>'
    )

    def fetcher(url):
        return old_kin_html if "old" in url else fresh_kin_html

    stale_target = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=old",
        title="추나요법 허리치료 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 추나"],
        category="통증/디스크",
        discovered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    fresh_target = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=fresh",
        title="청주 디스크 한의원 추천 질문",
        content_preview="짧은 snippet",
        matched_keywords=["청주 디스크 한의원"],
        category="통증/디스크",
        discovered_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = FakeDB()
    kept, stats = hunter._enrich_and_regate_ai_targets(
        [stale_target, fresh_target], fetcher=fetcher,
    )

    assert stats["dated"] == 2
    assert stats["stale_rejected"] == 1
    kept_urls = {t.url for t in kept}
    assert stale_target.url not in kept_urls
    assert fresh_target.url in kept_urls
    assert stale_target.comment_status == "filtered_out_stale_window"
    assert (stale_target.score_breakdown or {}).get("post_date_enriched") == "20150108"
    assert hunter.db.saved and hunter.db.saved[0]["url"] == stale_target.url


def test_timing_parser_handles_naver_relative_and_spaced_date_formats():
    from datetime import datetime

    now = datetime(2026, 6, 17, 17, 30, 0)
    parse = viral_hunter.CommentableFilter._parse_datetime

    assert parse("오늘", now) == datetime(2026, 6, 17, 0, 0, 0)
    assert parse("그제 작성", now) == datetime(2026, 6, 15, 17, 30, 0)
    assert parse("오후 3:20", now) == datetime(2026, 6, 17, 15, 20, 0)
    assert parse("어제 오전 9:05", now) == datetime(2026, 6, 16, 9, 5, 0)
    assert parse("2026. 6. 10. 오후 3:20", now) == datetime(2026, 6, 10, 15, 20, 0)


def test_timing_window_uses_spaced_naver_date_as_real_post_age_penalty():
    from datetime import datetime

    now = datetime(2026, 6, 17, 17, 30, 0)
    old_target = ViralTarget(
        platform="kin",
        url="https://example.com/spaced-date-old",
        title="청주 여드름흉터 새살침 후기 궁금합니다",
        content_preview="청주 여드름흉터 새살침 상담 받아보신 분 후기와 비용이 궁금합니다.",
        matched_keywords=["청주 여드름흉터 새살침 후기"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
        date_str="2026. 5. 1. 오후 3:20",
        discovered_at="2026-06-17 16:30:00",
        comment_count=0,
        view_count=150,
    )

    score, tier, signals = viral_hunter.CommentableFilter._assess_timing_window(
        old_target,
        viral_need_signals=["recommendation_request", "ready_to_act"],
        reply_opportunity_signals=["clear_question_shape"],
        now=now,
    )
    no_date_target = ViralTarget(
        platform=old_target.platform,
        url="https://example.com/spaced-date-unknown",
        title=old_target.title,
        content_preview=old_target.content_preview,
        matched_keywords=old_target.matched_keywords,
        category=old_target.category,
        matched_keyword_category=old_target.matched_keyword_category,
        date_str="",
        discovered_at=old_target.discovered_at,
        comment_count=old_target.comment_count,
        view_count=old_target.view_count,
    )
    no_date_score, _, no_date_signals = viral_hunter.CommentableFilter._assess_timing_window(
        no_date_target,
        viral_need_signals=["recommendation_request", "ready_to_act"],
        reply_opportunity_signals=["clear_question_shape"],
        now=now,
    )

    assert "posted_over_30d" in signals
    assert "freshly_discovered" in signals
    assert "no_post_date" not in signals
    assert "no_post_date" in no_date_signals
    assert score <= no_date_score - 25
    assert tier in {"aging", "stale"}


def _create_pending_ttl_table(conn):
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY, platform TEXT, url TEXT UNIQUE, category TEXT,
            comment_status TEXT, is_commentable INTEGER, discovered_at TEXT,
            first_seen_at TEXT, posted_at TEXT, score_breakdown TEXT, updated_at TEXT
        )
        """
    )


def test_expire_stale_pending_targets(tmp_path):
    """플랫폼별 TTL을 넘긴 pending만 만료되고, 다른 상태/신선한 행은 보존."""
    from datetime import datetime, timedelta

    db_path = tmp_path / "ttl.db"
    now = datetime.now()

    def days_ago(n):
        return (now - timedelta(days=n)).strftime("%Y-%m-%d %H:%M:%S")

    rows = [
        # (id, platform, status, discovered_days_ago) — TTL: cafe 30, blog/kin 45
        ("cafe-old", "cafe", "pending", 40),       # 만료 (>30)
        ("cafe-fresh", "cafe", "pending", 20),     # 보존 (<=30)
        ("kin-old", "kin", "pending", 60),         # 만료 (>45)
        ("kin-edge", "kin", "pending", 40),        # 보존 (<=45)
        ("blog-old", "blog", "pending", 50),       # 만료 (>45)
        ("raw-old", "cafe", "raw_backlog", 90),    # pending 아님 → 무시
        ("posted-old", "kin", "posted", 90),       # pending 아님 → 무시
    ]
    with sqlite3.connect(db_path) as conn:
        _create_pending_ttl_table(conn)
        for tid, plat, status, age in rows:
            conn.execute(
                "INSERT INTO viral_targets (id, platform, url, category, comment_status, "
                "is_commentable, discovered_at, score_breakdown) VALUES (?,?,?,?,?,1,?,'{}')",
                (tid, plat, f"https://x/{tid}", "통증/디스크", status, days_ago(age)),
            )
        conn.commit()

    stats = viral_hunter.expire_stale_pending_targets(str(db_path))
    assert stats["expired"] == 3

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        statuses = {
            r["id"]: r["comment_status"]
            for r in conn.execute("SELECT id, comment_status FROM viral_targets")
        }
        breakdown = conn.execute(
            "SELECT score_breakdown FROM viral_targets WHERE id='cafe-old'"
        ).fetchone()[0]

    assert statuses["cafe-old"] == "filtered_out_stale_window"
    assert statuses["kin-old"] == "filtered_out_stale_window"
    assert statuses["blog-old"] == "filtered_out_stale_window"
    assert statuses["cafe-fresh"] == "pending"
    assert statuses["kin-edge"] == "pending"
    assert statuses["raw-old"] == "raw_backlog"
    assert statuses["posted-old"] == "posted"
    assert "pending_ttl" in breakdown and "pending_age_days" in breakdown

    # dry-run은 상태를 바꾸지 않는다.
    dry = viral_hunter.expire_stale_pending_targets(str(db_path), dry_run=True)
    assert dry["expired"] == 0  # 이미 만료된 행 외 남은 pending은 신선


def test_expire_stale_pending_targets_post_age(tmp_path):
    """발견은 최근이어도 게시물 자체가 오래되면(post-age) 만료된다."""
    from datetime import datetime, timedelta

    db_path = tmp_path / "ttl_postage.db"
    now = datetime.now()
    recent = (now - timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")  # 큐 체류는 신선

    rows = [
        # (id, posted_at YYYYMMDD, 기대)
        ("kin-ancient", "20150108", True),    # 11년 전 글 → post-age 만료
        ("kin-1yr", (now - timedelta(days=300)).strftime("%Y%m%d"), True),   # 300일 > 270 만료
        ("kin-recent-post", (now - timedelta(days=20)).strftime("%Y%m%d"), False),  # 20일 글 보존
        ("kin-no-date", "", False),           # 게시일 모름 → post-age 미적용, 체류 신선 → 보존
    ]
    with sqlite3.connect(db_path) as conn:
        _create_pending_ttl_table(conn)
        for tid, posted, _ in rows:
            conn.execute(
                "INSERT INTO viral_targets (id, platform, url, category, comment_status, "
                "is_commentable, discovered_at, posted_at, score_breakdown) "
                "VALUES (?,?,?,?,'pending',1,?,?,'{}')",
                (tid, "kin", f"https://x/{tid}", "통증/디스크", recent, posted),
            )
        conn.commit()

    stats = viral_hunter.expire_stale_pending_targets(str(db_path))
    assert stats["expired"] == 2
    assert stats["expired_post_age"] == 2
    assert stats["expired_dwell"] == 0

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        statuses = {
            r["id"]: r["comment_status"]
            for r in conn.execute("SELECT id, comment_status FROM viral_targets")
        }
        breakdown = conn.execute(
            "SELECT score_breakdown FROM viral_targets WHERE id='kin-ancient'"
        ).fetchone()[0]

    assert statuses["kin-ancient"] == "filtered_out_stale_window"
    assert statuses["kin-1yr"] == "filtered_out_stale_window"
    assert statuses["kin-recent-post"] == "pending"
    assert statuses["kin-no-date"] == "pending"
    assert "pending_post_age" in breakdown and "post_age_days" in breakdown


def test_platform_yield_acceptance_to_factor():
    """수용률 → 발견 예산 가중치 매핑 (바닥 0.2, 상한 1.0)."""
    f = viral_hunter.ViralHunter._acceptance_to_yield_factor
    assert f(0.20) == 1.0      # kin 19.7%급
    assert f(0.15) == 1.0
    assert f(0.10) == 0.85
    assert f(0.069) == 0.6     # cafe 6.9%급
    assert f(0.02) == 0.35
    assert f(0.004) == 0.2     # blog 0.4%급 → 바닥
    assert f(0.0) == 0.2


def test_platform_yield_factors_and_budget_application(tmp_path):
    """staff 수용률에서 플랫폼 가중치를 학습하고 발견 예산에 적용 (바닥 보장)."""
    from types import SimpleNamespace

    db_path = tmp_path / "platyield.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE viral_targets (id TEXT PRIMARY KEY, platform TEXT, comment_status TEXT)"
        )

        def seed(platform, good, skipped):
            n = 0
            for _ in range(good):
                conn.execute("INSERT INTO viral_targets VALUES (?,?,?)",
                             (f"{platform}-g{n}", platform, "posted")); n += 1
            for _ in range(skipped):
                conn.execute("INSERT INTO viral_targets VALUES (?,?,?)",
                             (f"{platform}-s{n}", platform, "skipped")); n += 1

        seed("blog", 2, 498)    # 0.4% → 바닥 0.2
        seed("cafe", 35, 465)   # 7.0% → 0.6
        seed("kin", 100, 400)   # 20%  → 1.0
        seed("instagram", 0, 10)  # 표본<40 → 미개입(dict 제외)
        conn.commit()

    hunter = viral_hunter.ViralHunter.__new__(viral_hunter.ViralHunter)
    hunter.db = SimpleNamespace(db_path=str(db_path))
    hunter._platform_yield_cache = None
    hunter._platform_drop_counts = {}

    factors = hunter._load_platform_yield_factors()
    assert factors.get("blog") == 0.2
    assert factors.get("cafe") == 0.6
    assert "kin" not in factors          # 1.0은 dict에서 제외(미개입)
    assert "instagram" not in factors    # 표본 부족

    limits = hunter._apply_platform_yield_factors({"cafe": 100, "blog": 100, "kin": 100})
    assert limits["kin"] == 100          # 고수율 플랫폼 그대로
    assert limits["cafe"] == 60          # 0.6배
    assert limits["blog"] == 20          # 0.2배
    # 바닥 limit: 작은 예산도 완전히 0이 되지 않는다.
    floored = hunter._apply_platform_yield_factors({"blog": 30})
    assert floored["blog"] == viral_hunter.ViralHunter.PLATFORM_YIELD_FLOOR_LIMIT
    # 차단량 집계.
    assert hunter._platform_drop_counts.get("blog", 0) > 0


def test_scar_patient_exploration_rescues_comparison_question():
    """흉터 환자의 탐색 질문은 본문에 시술 단어(레이저)가 있어도 살아남는다."""
    target = ViralTarget(
        platform="cafe",
        url="https://cafe.naver.com/scar-rescue/123456",
        title="여드름 흉터 병원 가야 할지 고민이에요ㅠ",
        content_preview=(
            "여드름 흉터 때문에 진짜 스트레스예요ㅠㅠ 거울 볼 때마다 패인 부분이 너무 신경 쓰여서 "
            "사람 만나기도 자신감이 없어지더라고요. 여드름 흉터 병원에 가봐야 하나 싶어서 "
            "이것저것 찾아보는데 레이저 종류도 많고..."
        ),
        matched_keywords=["금천동 여드름흉터"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
    )

    assert viral_hunter.CommentableFilter.apply_final_reject(target) is None

    # 제목 자체가 시술/피부과 주제면 구제하지 않는다 (주제 고착 글).
    committed = ViralTarget(
        platform="cafe",
        url="https://cafe.naver.com/scar-committed/123457",
        title="여드름 흉터 프락셀 어떤지 궁금해요",
        content_preview="여드름 흉터 프락셀 받아보신 분 후기 좀요. 프락셀 알아보는 중이에요.",
        matched_keywords=["금천동 여드름흉터"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
    )

    assert viral_hunter.CommentableFilter.apply_final_reject(committed) == "off_domain"


def test_seoul_neighborhood_titles_hit_region_gate():
    """닥톡류 '(서울동네 카테고리)' 템플릿 질문은 동네명만으로 지역 게이트에 걸린다."""
    target = ViralTarget(
        platform="kin",
        url="https://kin.naver.com/qna/detail.naver?docId=jamsil1",
        title="여드름흉터제거 어떤 치료가 좋을까요?(잠실 여드름흉터)",
        content_preview="잠실 30대 초반/남 여드름흉터 패인 여드름흉터는 몇 년이 지나도 그대로인 것 같아요. 치료 추천해주세요.",
        matched_keywords=["여드름흉터"],
        category="흉터/여드름흉터",
        matched_keyword_category="흉터/여드름흉터",
    )

    assert viral_hunter.CommentableFilter.apply_final_reject(target) == "region_mismatch"


def _final_gate_target(platform, title, preview, mk_cat, cat, url_suffix):
    return ViralTarget(
        platform=platform,
        url=f"https://example.test/final-gate/{url_suffix}",
        title=title,
        content_preview=preview,
        matched_keywords=["청주 다이어트 한약"],
        category=cat,
        matched_keyword_category=mk_cat,
    )


def test_cross_axis_discovery_rescued_on_user_question_surfaces_only():
    """다이어트 시드가 찾은 추나/자세 질문은 cafe/kin에서만 교차축으로 구제된다."""
    question = (
        "청주 30대 후반/남 추나치료 평소 오래 앉아 있는 편인데 허리랑 골반이 "
        "한쪽으로 틀어진 느낌이 있습니다. 추나치료가 도움이 되는지 궁금합니다."
    )
    kin = _final_gate_target("kin", "추나치료 자세 불균형에도 도움이 될까요?", question, "다이어트", "통증/디스크", "ca-kin")
    assert viral_hunter.CommentableFilter.apply_final_reject(kin) is None

    blog = _final_gate_target("blog", "추나치료 자세 불균형에도 도움이 될까요?", question, "다이어트", "통증/디스크", "ca-blog")
    assert viral_hunter.CommentableFilter.apply_final_reject(blog) == "domain_mismatch"

    # detect_category 우발 매칭(성형 글의 체형 단어)은 user-axis 앵커 요구로 차단.
    junk = _final_gate_target(
        "cafe",
        "보형물로도 처진가슴 잘 잡히죠?",
        "윗가슴부터 가득 찼음 좋겠는데 보형물로도 처진가슴 잘 잡히죠? 수술 고민이에요",
        "다이어트", "체형교정", "ca-junk",
    )
    assert viral_hunter.CommentableFilter.apply_final_reject(junk) == "domain_mismatch"


def test_kin_answer_segment_isolated_in_final_gate_everywhere():
    """[기존답변] 분리는 게이트 본체에 있다 — 어떤 호출 경로든 답변 광고가 질문을 오살하지 않는다."""
    question = (
        "청주 30대 후반/남 추나치료 평소 오래 앉아 있는 편인데 허리랑 골반이 "
        "한쪽으로 틀어진 느낌이 있습니다. 추나치료가 도움이 되는지 궁금합니다."
    )
    promo_answer = (
        " [기존답변1] # 병원 위치 | 진료 예약 | 문의 전화 안녕하세요, "
        "닥톡-네이버 지식iN 상담한의사입니다. 상담 한번 받아보세요."
    )
    labeled = _final_gate_target("kin", "추나치료 자세 불균형에도 도움이 될까요?", question + promo_answer, "체형교정", "체형교정", "seg-labeled")
    assert viral_hunter.CommentableFilter.apply_final_reject(labeled) is None
    # 게이트 통과 후에도 preview 원본(답변 포함)은 보존돼 AI가 전체를 본다.
    assert "[기존답변1]" in labeled.content_preview

    # 라벨 없는 snippet 연결(미보강)은 기존 광고 판정 규칙이 그대로 적용된다.
    unlabeled = _final_gate_target(
        "kin", "추나치료 자세 불균형에도 도움이 될까요?",
        question + " # 병원 위치 | 진료 예약 | 문의 전화 안녕하세요, 닥톡-네이버 지식iN "
        "상담한의사입니다. 상담 한번 받아보세요. 비용 부담 없이 진료받으세요",
        "체형교정", "체형교정", "seg-unlabeled",
    )
    assert viral_hunter.CommentableFilter.apply_final_reject(unlabeled) == "advertorial"


def test_asymmetry_patient_vocab_passes_anchor_gate():
    """키워드 용어 없이 증상을 서술하는 턱 틀어짐 환자 질문이 앵커 게이트를 통과한다."""
    jaw = _final_gate_target(
        "kin",
        "스트레스를 받으면 돌아가는 턱..ㅠ",
        "안녕하세요? 저는 22세 여자인데요, 스트레스를 받으면 아래턱이 오른쪽으로 "
        "움직이는 증상이 일어납니다. 누가 봐도 심할 만큼 아래턱이 돌아가 있습니다. 어떻게 해야 할까요?",
        "안면비대칭", "안면비대칭", "jaw-vocab",
    )
    assert viral_hunter.CommentableFilter.apply_final_reject(jaw) is None
