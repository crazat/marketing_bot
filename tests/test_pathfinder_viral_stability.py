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
    assert any("다이어트 한약" in kw and "비용 얼마" in kw for kw in variants)
    assert any("직장인" in kw and "다이어트 한약" in kw for kw in variants)


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
    assert selected_categories.count(asymmetry) == 3
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
                   matched_keyword, matched_keyword_category
            FROM viral_targets
            WHERE url = ?
            """,
            ("https://example.com/seen",),
        ).fetchone()

    assert row == (2, 10, "posted", "청주 여드름", "피부/여드름")


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
