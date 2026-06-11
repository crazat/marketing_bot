import json
import sqlite3
from collections import Counter

from core_services.viral_seed_builder import ViralSeedBuilder
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
    assert context["청주 다이어트 한약 비용 상담 후기"]["viral_readiness_score"] >= 80
    assert context["청주 다이어트 한약 비용 상담 후기"]["preferred_search_surface"] == "hybrid_local_content"


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

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=14, quotas={"피부/여드름": 1})

    assert [seed.keyword for seed in seeds] == ["청주 수술흉터 새살침 상담"]


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

    assert [plan["query"] for plan in plans] == ["금천동 여드름흉터", "금천동 여드름흉터 추천"]
    assert plans[1]["source_keyword"] == "금천동 여드름흉터"
    assert plans[1]["variant"] == "community:추천"
    assert plans[1]["platform_limits"]["cafe"] < plans[0]["platform_limits"]["cafe"]
    assert hunter.keyword_context["금천동 여드름흉터 추천"]["pathfinder_source_keyword"] == "금천동 여드름흉터"


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
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[0]["platform_limits"]["cafe"] >= 150
    assert plans[1]["variant"] == "axis_body:체형추나추천"
    assert plans[2]["variant"] == "axis_body:골반교정추천"
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
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[1]["variant"] == "axis_lifting:매선한방후기"
    assert plans[2]["variant"] == "axis_lifting:팔자주름후기"


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

    assert [plan["query"] for plan in plans] == [
        "봉명동 턱비대칭 한의원 비용",
        "청주 턱관절 안면비대칭 한의원 추천",
        "청주 안면비대칭 교정 한의원 추천",
    ]
    assert plans[0]["platform_limits"]["blog"] == 35
    assert plans[1]["variant"] == "axis_asymmetry:턱관절비대칭추천"
    assert plans[2]["variant"] == "axis_asymmetry:교정추천"


def test_viral_hunter_does_not_duplicate_query_variant_when_lens_term_exists():
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

    assert [plan["query"] for plan in plans] == ["청주 여드름 한의원 비용"]


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
        quotas={"피부/여드름": 4},
    )

    selected = [seed.keyword for seed in seeds]
    assert selected == [
        "분평동 여드름흉터 한의원 비용",
        "분평동 여드름흉터 한의원 상담",
        "복대동 새살침 후기",
        "산남동 여드름 한의원 비용",
    ]
    assert "분평동 여드름흉터 한의원 예약" not in selected


def test_viral_seed_builder_merges_gyulim_scar_alias_quota_into_skin_axis(tmp_path):
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
            ("청주 여드름흉터 한의원 비용", "피부", 200),
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
        "청주 여드름흉터 한의원 비용",
    ]
    assert {seed.category for seed in seeds} == {"피부/여드름"}
    context = ViralSeedBuilder(str(db_path)).keyword_context_for(["청주 수술흉터 새살침 상담"])
    assert context["청주 수술흉터 새살침 상담"]["category"] == "피부/여드름"


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

    seeds = ViralSeedBuilder(str(db_path)).build(scan_run_id=12, quotas={"피부/여드름": 2})

    selected = [seed.keyword for seed in seeds]
    assert "청주 여드름흉터 피부과 말고 한의원 상담" in selected
    assert "청주 피부과 추천" not in selected


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
            "category": "피부/여드름",
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
    assert target.matched_keyword_category == "피부/여드름"
    assert target.score_breakdown["pathfinder_viral_readiness_score"] == 91.0
    assert target.score_breakdown["pathfinder_content_actionability_score"] == 86.0
    assert target.score_breakdown["pathfinder_preferred_search_surface"] == "hybrid_local_content"
    assert target.score_breakdown["pathfinder_execution_lens"] == "review"
    assert "PATHFINDER_KEYWORD: 청주 수술흉터 새살침 상담" in formatted
    assert "PATHFINDER_EXECUTION: readiness=91.0" in formatted
    assert "lens=review" in formatted


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
        "category": "피부/여드름",
        "matched_keyword_category": "피부/여드름",
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
        "category": "피부/여드름",
        "matched_keyword_category": "피부/여드름",
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

    assert set(by_url) == {
        "https://example.com/pathfinder-axis-skin",
        "https://example.com/pathfinder-axis-diet",
    }
    assert by_url["https://example.com/pathfinder-axis-skin"].priority_score > by_url["https://example.com/pathfinder-axis-diet"].priority_score
    match_breakdown = by_url["https://example.com/pathfinder-axis-skin"].score_breakdown
    mismatch_breakdown = by_url["https://example.com/pathfinder-axis-diet"].score_breakdown
    assert match_breakdown["pathfinder_axis_fit_tier"] == "strong"
    assert mismatch_breakdown["pathfinder_axis_fit_tier"] == "mismatch"
    assert "pathfinder_axis_core_match" in match_breakdown["pathfinder_axis_fit_signals"]
    assert "pathfinder_axis_cross_axis_noise" in mismatch_breakdown["pathfinder_axis_fit_signals"]
    assert mismatch_breakdown["pathfinder_axis_adjustment"] < 0


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

    assert by_category["피부/여드름"] >= 10
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
    assert selected_categories.count("피부/여드름") == 6
    assert selected_categories.count("다이어트") == 4
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


def test_viral_final_gate_rejects_asymmetry_seed_without_axis_anchor():
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

    assert viral_hunter.CommentableFilter.final_reject_reason(target) == "domain_mismatch"


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
