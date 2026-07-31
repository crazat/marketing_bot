import json
import sqlite3

from core_services.gyulim_keyword_profile import ACTIVE_KEYWORD_PROFILE
from core_services.viral_handoff_audit import (
    ENGAGEMENT_HOOK_LENS_TERMS,
    VIRAL_ACTION_ROUTE_DEFINITIONS,
    _category_drift_detected,
    _category_subintent_buckets,
    _category_signature_terms,
    _clinic_modality_positive_terms,
    _discarded_execution_rescue_quality,
    _next_run_playbook,
    _priority_focus_categories,
    _seed_target_coverage,
    _viral_action_route_evidence,
    latest_viral_source_scan_id,
    summarize_viral_handoff_quality,
)


def _make_db(tmp_path):
    db_path = tmp_path / "viral_handoff_audit.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            url TEXT,
            title TEXT,
            content_preview TEXT,
            platform TEXT,
            category TEXT,
            matched_keyword TEXT,
            matched_keywords TEXT,
            matched_keyword_grade TEXT,
            matched_keyword_category TEXT,
            comment_status TEXT,
            priority_score REAL,
            score_breakdown TEXT,
            source_scan_run_id INTEGER,
            discovered_at TEXT
        )
        """
    )
    return db_path, conn


def _insert_target(
    conn,
    *,
    target_id,
    scan_id,
    category,
    grade,
    status,
    priority,
    breakdown,
    title=None,
    content_preview="",
    platform="kin",
    discovered_at=None,
):
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, url, title, content_preview, platform, category, matched_keyword, matched_keywords,
            matched_keyword_grade, matched_keyword_category, comment_status,
            priority_score, score_breakdown, source_scan_run_id, discovered_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, datetime('now')))
        """,
        (
            target_id,
            f"https://example.com/{target_id}",
            title or f"{category} target",
            content_preview,
            platform,
            category,
            f"{category} keyword",
            json.dumps([f"{category} keyword"], ensure_ascii=False),
            grade,
            category,
            status,
            priority,
            json.dumps(breakdown, ensure_ascii=False),
            scan_id,
            discovered_at,
        ),
    )


def _signature_terms_for(category, *, count=4):
    profile = ACTIVE_KEYWORD_PROFILE.profile_for(category)
    if not profile:
        return []
    terms = []
    for source in (
        tuple(getattr(profile, "core_tokens", ()) or ()),
        tuple(getattr(profile, "category_terms", ()) or ()),
        tuple(getattr(profile, "seed_terms", ()) or ()),
    ):
        for term in source:
            clean = str(term or "").strip()
            if clean and clean not in terms:
                terms.append(clean)
            if len(terms) >= count:
                return terms
    return terms


def _compact_for_test(text):
    return "".join(str(text or "").lower().split())


def _non_modality_signature_terms_for(category, *, count=12):
    positive_terms = [
        _compact_for_test(term)
        for term in _clinic_modality_positive_terms(category)
    ]
    selected = []
    for term in _category_signature_terms(category):
        compact = _compact_for_test(term)
        if not compact:
            continue
        if any(
            positive and (positive in compact or compact in positive)
            for positive in positive_terms
        ):
            continue
        if term not in selected:
            selected.append(term)
        if len(selected) >= count:
            break
    return selected or [str(category or "").split("/")[0]]


def _single_subintent_signature_terms_for(category, *, count=4):
    signature_compacts = {
        _compact_for_test(term)
        for term in _category_signature_terms(category)
    }
    for bucket, terms in _category_subintent_buckets(category).items():
        selected = []
        for term in terms:
            if _compact_for_test(term) not in signature_compacts:
                continue
            candidate = selected + [term]
            compact_candidate = _compact_for_test(" ".join(candidate))
            matched_buckets = {
                candidate_bucket
                for candidate_bucket, candidate_terms in _category_subintent_buckets(category).items()
                if any(
                    _compact_for_test(candidate_term)
                    and _compact_for_test(candidate_term) in compact_candidate
                    for candidate_term in candidate_terms
                )
            }
            if matched_buckets == {bucket}:
                selected = candidate
            if len(selected) >= count:
                return bucket, selected[:count]
    raise AssertionError(f"no subintent bucket with {count} signature terms for {category}")


def _diverse_subintent_signature_terms_for(category, *, bucket_count=3):
    signature_compacts = {
        _compact_for_test(term)
        for term in _category_signature_terms(category)
    }
    selected = []
    for terms in _category_subintent_buckets(category).values():
        for term in terms:
            if _compact_for_test(term) in signature_compacts:
                selected.append(term)
                break
        if len(selected) >= bucket_count:
            return selected
    return _signature_terms_for(category, count=bucket_count)


def test_viral_handoff_audit_summarizes_grade_axis_lens_and_fit_rates(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="skin-good",
        scan_id=66,
        category="피부/여드름",
        grade="S",
        status="pending",
        priority=132,
        breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost:비용",
            "pathfinder_axis_fit_score": 88,
            "pathfinder_lens_fit_score": 82,
            "clinic_treatment_fit_score": 91,
            "worksite_efficiency_score": 86,
        },
    )
    _insert_target(
        conn,
        target_id="skin-filtered",
        scan_id=66,
        category="피부/여드름",
        grade="A",
        status="filtered_out_clinic_mismatch",
        priority=30,
        breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "base",
            "pathfinder_axis_fit_score": 28,
            "pathfinder_lens_fit_score": 80,
            "clinic_treatment_fit_score": 30,
            "worksite_efficiency_score": 40,
        },
    )
    _insert_target(
        conn,
        target_id="diet-backlog-lens-weak",
        scan_id=66,
        category="다이어트",
        grade="B",
        status="raw_backlog",
        priority=98,
        breakdown={
            "pathfinder_execution_lens": "community",
            "pathfinder_query_variant": "community:추천",
            "pathfinder_axis_fit_score": 76,
            "pathfinder_lens_fit_score": 48,
            "clinic_treatment_fit_score": 80,
            "worksite_efficiency_score": 74,
        },
    )
    _insert_target(
        conn,
        target_id="old-run",
        scan_id=65,
        category="교통사고",
        grade="S",
        status="pending",
        priority=150,
        breakdown={
            "pathfinder_execution_lens": "safety",
            "pathfinder_axis_fit_score": 90,
            "pathfinder_lens_fit_score": 90,
            "clinic_treatment_fit_score": 90,
            "worksite_efficiency_score": 90,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=66,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert report["row_count"] == 3
    assert report["generated_at_utc"]
    assert report["overall"]["grade_counts"] == {"S": 1, "A": 1, "B": 1}
    assert report["overall"]["status_counts"]["raw_backlog"] == 1
    assert report["overall"]["strict_fit"] == 1
    assert report["overall"]["strict_fit_rate"] == 0.3333
    assert report["overall"]["axis_coverage_rate"] == 1.0
    assert report["overall"]["lens_coverage_rate"] == 1.0
    assert report["by_category"]["피부/여드름"]["total"] == 2
    assert report["by_category"]["피부/여드름"]["strict_fit"] == 1
    assert report["by_grade"]["B"]["survived"] == 1
    assert report["by_lens"]["community"]["strict_fit"] == 0
    assert report["by_lens"]["cost"]["query_variant_counts"]["cost:비용"] == 1
    assert report["by_query_variant"]["cost:비용"]["strict_fit"] == 1
    assert report["by_category_lens"]["피부/여드름::cost"]["total"] == 2
    assert any(
        lane["lane"] == "community" and "low_lens_fit" in lane["reasons"]
        for lane in report["weak_lanes"]
    )
    assert any(
        item["code"] == "low_lens_fit"
        and any("lens:community" == lane for lane in item["lanes"])
        for item in report["recommendations"]
    )
    weak_samples = report["review_samples"]["weak_lane_samples"]
    assert any(
        sample_group["lane"] == "community"
        and sample_group["samples"][0]["id"] == "diet-backlog-lens-weak"
        for sample_group in weak_samples
    )


def test_viral_handoff_audit_defaults_to_latest_source_scan_id(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="run10",
        scan_id=10,
        category="피부/여드름",
        grade="A",
        status="pending",
        priority=120,
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 80,
            "pathfinder_lens_fit_score": 80,
            "clinic_treatment_fit_score": 80,
            "worksite_efficiency_score": 80,
        },
    )
    _insert_target(
        conn,
        target_id="run11",
        scan_id=11,
        category="다이어트",
        grade="B",
        status="pending",
        priority=90,
        breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_axis_fit_score": 70,
            "pathfinder_lens_fit_score": 70,
            "clinic_treatment_fit_score": 70,
            "worksite_efficiency_score": 70,
        },
    )
    conn.commit()
    conn.close()

    assert latest_viral_source_scan_id(str(db_path)) == 11
    report = summarize_viral_handoff_quality(str(db_path), include_seed_baseline=False)

    assert report["source_scan_run_id"] == 11
    assert report["row_count"] == 1
    assert set(report["by_category"]) == {"다이어트"}


def test_viral_handoff_audit_counts_ai_approved_as_actionable_and_survived(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="ai-approved",
        scan_id=12,
        category="흉터/여드름흉터",
        grade="S",
        status="ai_approved",
        priority=142,
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
            "pathfinder_axis_fit_score": 91,
            "pathfinder_lens_fit_score": 88,
            "clinic_treatment_fit_score": 93,
            "worksite_efficiency_score": 89,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=12,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert report["row_count"] == 1
    assert report["overall"]["status_counts"]["ai_approved"] == 1
    assert report["overall"]["actionable"] == 1
    assert report["overall"]["survived"] == 1
    assert report["overall"]["filtered"] == 0
    assert report["by_query_variant"]["axis_scar:specific_수술흉터"]["actionable"] == 1


def test_viral_handoff_audit_uses_current_reject_over_preserved_work_status(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="legacy-posted-now-ad",
        scan_id=13,
        category="다이어트",
        grade="S",
        status="posted",
        priority=150,
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "base",
            "pathfinder_axis_fit_score": 95,
            "pathfinder_lens_fit_score": 90,
            "clinic_treatment_fit_score": 94,
            "worksite_efficiency_score": 92,
            "final_reject_reason": "advertorial",
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=13,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert report["row_count"] == 1
    assert report["overall"]["status_counts"]["filtered_out_ad"] == 1
    assert report["overall"]["actionable"] == 0
    assert report["overall"]["survived"] == 0
    assert report["overall"]["strict_fit"] == 0
    assert report["overall"]["filtered"] == 1
    assert report["overall"]["loss_reason_counts"]["ad"] == 1


def test_viral_handoff_audit_quality_bar_and_variant_families(tmp_path):
    db_path, conn = _make_db(tmp_path)
    categories_and_variants = [
        ("흉터/여드름흉터", "axis_scar:specific_수술흉터"),
        ("안면비대칭", "axis_asymmetry:턱관절비대칭추천"),
        ("피부/여드름", "patient_voice_question_kin"),
        ("다이어트", "cost_community:추천"),
        ("체형교정", "community_base"),
        ("리프팅/탄력", "review:추천"),
        ("교통사고", "base"),
    ]
    for idx, (category, variant) in enumerate(categories_and_variants, start=1):
        _insert_target(
            conn,
            target_id=f"strict-{idx}",
            scan_id=44,
            category=category,
            grade="A",
            status="pending",
            priority=140,
            title=f"청주 {category} 후기 추천",
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": variant,
                "pathfinder_axis_fit_score": 90,
                "pathfinder_lens_fit_score": 88,
                "clinic_treatment_fit_score": 91,
                "worksite_efficiency_score": 87,
                "reply_opportunity_score": 82,
                "reply_opportunity_tier": "assist_now",
                "reply_opportunity_signals": (
                    "public_reply_surface,help_request_language,decision_or_service_task,"
                    "local_actionable,unanswered_or_low_response"
                ),
                "reply_risk_penalty": 0,
                "reply_risk_flags": "",
                "manual_review": 0,
            },
        )
    journey_terms = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    local_area_terms = (
        list(getattr(ACTIVE_KEYWORD_PROFILE, "neighborhoods", ()) or ())
        + list(getattr(ACTIVE_KEYWORD_PROFILE, "cheongju_regions", ()) or ())
        + [getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "청주")]
    )
    local_area_terms = [term for term in local_area_terms if str(term or "").strip()][:8]
    journey_idx = 1
    for category in _priority_focus_categories():
        signature_terms = " ".join(dict.fromkeys(
            _signature_terms_for(category, count=4)
            + _diverse_subintent_signature_terms_for(category, bucket_count=3)
        ))
        for lens, terms in journey_terms.items():
            for copy_idx in range(2):
                variant = f"{lens}:{terms}" if copy_idx == 0 else "patient_voice_question_kin"
                local_area = local_area_terms[(journey_idx + copy_idx) % len(local_area_terms)]
                _insert_target(
                    conn,
                    target_id=f"journey-strict-{journey_idx}-{copy_idx}",
                    scan_id=44,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=135,
                    platform=("kin" if copy_idx == 0 else "cafe"),
                    content_preview=(
                        f"{local_area} journey strict distinct copy {journey_idx}-{copy_idx} "
                        f"{signature_terms}"
                    ),
                    title=f"{local_area} {category} {terms}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{local_area} {category} {terms} 독립시드 {copy_idx}"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            journey_idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=44,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    quality_bar = report["quality_bar"]
    assert quality_bar["tier"] == "world_class"
    assert quality_bar["required_gates_passed"] is True
    assert quality_bar["focus_categories"]["strict_fit_coverage_rate"] == 1.0
    assert quality_bar["patient_journey"]["strict_coverage_rate"] == 1.0
    assert quality_bar["work_queue"]["category_lens_ready_rate"] == 1.0
    assert quality_bar["opportunity_diversity"]["category_lens_diversity_ready_rate"] == 1.0
    assert quality_bar["engagement_hook"]["category_lens_hook_ready_rate"] == 1.0
    assert quality_bar["treatment_signature"]["category_lens_signature_ready_rate"] == 1.0
    assert quality_bar["treatment_signal_diversity"]["category_lens_treatment_signal_diverse_ready_rate"] == 1.0
    assert quality_bar["treatment_subintent_diversity"]["category_lens_treatment_subintent_diverse_ready_rate"] == 1.0
    assert quality_bar["clinic_modality_fit"]["category_lens_clinic_modality_fit_ready_rate"] == 1.0
    assert quality_bar["decision_window"]["category_lens_active_decision_ready_rate"] == 1.0
    assert quality_bar["seed_candidate_alignment"]["category_lens_seed_alignment_ready_rate"] == 1.0
    assert quality_bar["local_intent"]["category_lens_local_ready_rate"] == 1.0
    assert quality_bar["patient_surface_authenticity"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert quality_bar["viral_action_route"]["category_lens_route_ready_rate"] == 1.0
    assert quality_bar["reply_workability"]["category_lens_reply_workable_ready_rate"] == 1.0
    assert quality_bar["execution_readiness"]["category_lens_execution_ready_rate"] == 1.0
    assert quality_bar["execution_priority_alignment"]["category_lens_priority_alignment_rate"] == 1.0
    assert quality_bar["patient_surface"]["strict_fit_rate"] == 1.0
    assert report["by_variant_family"]["axis_specific"]["total"] == 1
    assert report["by_variant_family"]["axis_companion"]["total"] == 1
    assert report["by_variant_family"]["patient_voice"]["total"] >= 1
    assert report["by_variant_family"]["lens_community"]["total"] == 1
    assert not any(
        item["code"] == "handoff_quality_bar_not_world_class"
        for item in report["recommendations"]
    )


def test_viral_handoff_audit_flags_high_fit_unexplained_filtered_reanalysis_backlog(tmp_path):
    db_path, conn = _make_db(tmp_path)
    conn.execute("ALTER TABLE viral_targets ADD COLUMN last_scanned_at TEXT")
    _insert_target(
        conn,
        target_id="rescue-filtered",
        scan_id=145,
        category="흉터/여드름흉터",
        grade="A",
        status="filtered_out",
        priority=145,
        title="청주 여드름흉터 치료 추천 궁금해요",
        content_preview="청주에서 여드름흉터 치료 받아보신 분 추천 부탁드려요",
        discovered_at="2020-01-01 00:00:00",
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "patient_voice_question_kin",
            "pathfinder_axis_fit_score": 96,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 90,
            "worksite_efficiency_score": 88,
            "reply_opportunity_score": 93,
            "reply_opportunity_tier": "assist_now",
            "reply_opportunity_signals": "public_reply_surface,help_request_language,local_actionable",
            "reply_risk_penalty": 0,
            "reply_risk_flags": "",
            "manual_review": 0,
        },
    )
    _insert_target(
        conn,
        target_id="explicit-off-domain",
        scan_id=145,
        category="흉터/여드름흉터",
        grade="A",
        status="filtered_out",
        priority=150,
        title="청주 여드름흉터 치료 추천",
        content_preview="오프도메인",
        discovered_at="2020-01-01 00:00:00",
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_axis_fit_score": 98,
            "pathfinder_lens_fit_score": 88,
            "reply_opportunity_score": 95,
            "final_reject_reason": "off_domain",
        },
    )
    conn.execute(
        "UPDATE viral_targets SET last_scanned_at = datetime('now') WHERE source_scan_run_id = 145"
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=145,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    rescue = report["reanalysis_rescue_quality"]
    assert rescue["overall"]["candidate_count"] == 1
    assert rescue["overall"]["priority_focus_candidate_count"] == 1
    assert rescue["by_category"] == {"흉터/여드름흉터": 1}
    assert rescue["samples"][0]["id"] == "rescue-filtered"
    assert "reanalysis_rescue_backlog" in report["quality_bar"]["failed_advisory_gates"]
    assert report["quality_bar"]["reanalysis_rescue_backlog"]["candidate_count"] == 1
    assert any(item["code"] == "reanalysis_rescue_backlog" for item in report["recommendations"])
    playbook = report["next_run_playbook"]
    assert playbook["reanalysis_rescue_required"] is True
    assert playbook["reanalysis_rescue_candidate_count"] == 1
    assert playbook["reanalysis_rescue_budget"] == 60
    assert "--rescue-backlog 60" in playbook["suggested_commands"]["live_scan"]


def test_viral_handoff_audit_flags_discarded_execution_ready_false_negative(tmp_path):
    db_path, conn = _make_db(tmp_path)
    category = _priority_focus_categories()[0]
    signature_term = _signature_terms_for(category, count=1)[0]
    _insert_target(
        conn,
        target_id="discarded-ready-stale-status",
        scan_id=152,
        category=category,
        grade="A",
        status="filtered_out_ad",
        priority=145,
        platform="kin",
        title=f"청주 {signature_term} 한의원 추천 상담 어디가 좋을까요 ?",
        content_preview=(
            f"청주에서 {signature_term} 때문에 고민인데 한의원 치료 상담 가능한 곳 추천 부탁드립니다"
        ),
        breakdown={
            "pathfinder_source_keyword": f"청주 {signature_term} 추천 상담",
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "patient_voice_question_kin",
            "pathfinder_axis_fit_score": 92,
            "pathfinder_lens_fit_score": 89,
            "clinic_treatment_fit_score": 91,
            "worksite_efficiency_score": 88,
            "reply_opportunity_score": 86,
            "reply_opportunity_tier": "assist_now",
            "reply_opportunity_signals": (
                "public_reply_surface,help_request_language,decision_or_service_task,"
                "local_actionable,unanswered_or_low_response"
            ),
            "reply_risk_penalty": 0,
            "reply_risk_flags": "",
            "manual_review": 0,
        },
    )
    _insert_target(
        conn,
        target_id="discarded-current-reject-conflict",
        scan_id=152,
        category=category,
        grade="A",
        status="pending",
        priority=150,
        platform="kin",
        title=f"청주 {signature_term} 한의원 추천 상담 어디가 좋을까요 ?",
        content_preview=(
            f"청주에서 {signature_term} 때문에 고민인데 한의원 치료 상담 가능한 곳 추천 부탁드립니다"
        ),
        breakdown={
            "pathfinder_source_keyword": f"청주 {signature_term} 추천 상담",
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "patient_voice_question_kin",
            "pathfinder_axis_fit_score": 92,
            "pathfinder_lens_fit_score": 89,
            "clinic_treatment_fit_score": 91,
            "worksite_efficiency_score": 88,
            "reply_opportunity_score": 86,
            "reply_opportunity_tier": "assist_now",
            "reply_opportunity_signals": (
                "public_reply_surface,help_request_language,decision_or_service_task,"
                "local_actionable,unanswered_or_low_response"
            ),
            "reply_risk_penalty": 0,
            "reply_risk_flags": "",
            "manual_review": 0,
            "final_reject_reason": "advertorial",
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=152,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    assert report["reanalysis_rescue_quality"]["overall"]["candidate_count"] == 0
    rescue = report["discarded_execution_rescue_quality"]
    assert rescue["overall"]["candidate_count"] == 1
    assert rescue["overall"]["priority_focus_candidate_count"] == 1
    assert rescue["overall"]["auto_requeue_candidate_count"] == 1
    assert rescue["overall"]["manual_review_candidate_count"] == 0
    assert rescue["by_status"] == {"filtered_out_ad": 1}
    assert rescue["by_rescue_mode"] == {"auto_requeue": 1}
    assert rescue["by_reject_reason"] == {"(none)": 1}
    assert rescue["samples"][0]["id"] == "discarded-ready-stale-status"
    assert rescue["samples"][0]["rescue_mode"] == "auto_requeue"
    assert rescue["samples"][0]["current_reject_reason"] == ""
    assert "discarded_execution_rescue_backlog" in report["quality_bar"]["failed_advisory_gates"]
    assert report["quality_bar"]["discarded_execution_rescue_backlog"]["candidate_count"] == 1
    assert report["quality_bar"]["discarded_execution_rescue_backlog"]["auto_requeue_candidate_count"] == 1
    assert report["quality_bar"]["discarded_execution_rescue_backlog"]["manual_review_candidate_count"] == 0
    playbook = report["next_run_playbook"]
    assert playbook["discarded_execution_rescue_required"] is True
    assert playbook["discarded_execution_rescue_candidate_count"] == 1
    assert playbook["discarded_execution_auto_requeue_candidate_count"] == 1
    assert playbook["discarded_execution_manual_review_candidate_count"] == 0
    assert playbook["discarded_execution_manual_review_required"] is False
    assert playbook["discarded_execution_rescue_budget"] == 30
    assert "--rescue-backlog 30" in playbook["suggested_commands"]["live_scan"]
    assert any(
        item["code"] == "discarded_execution_rescue_backlog"
        for item in report["recommendations"]
    )


def test_discarded_execution_rescue_splits_auto_requeue_and_manual_review():
    base = {
        "metric_strict_fit": True,
        "fresh_activity": True,
        "priority": 140,
        "reply_opportunity_score": 90,
        "source_seed_lineage_present": True,
        "query_variant_lineage_present": True,
        "engagement_hook_matched": True,
        "treatment_signature_matched": True,
        "treatment_subintent_matched": True,
        "clinic_modality_matched": True,
        "decision_window_matched": True,
        "local_intent_matched": True,
        "seed_candidate_alignment_matched": True,
        "patient_surface_matched": True,
        "viral_action_route_matched": True,
        "reply_workability_matched": True,
        "patient_surface_provider_noise": False,
        "viral_action_route_mismatch": False,
        "reply_risk_blocked": False,
        "reply_risk_flags": [],
        "reply_manual_review": False,
        "reply_risk_penalty": 0,
        "category": "흉터/여드름흉터",
        "lens": "review",
        "platform": "kin",
        "title": "청주 여드름흉터 한의원 추천",
        "url": "https://example.com/rescue",
        "source_seed": "청주 여드름흉터 한의원 추천",
        "query_variant": "patient_voice_question_kin",
    }
    report = _discarded_execution_rescue_quality(
        [
            {
                **base,
                "id": "auto-filtered",
                "status": "filtered_out_ad",
                "current_reject_reason": "",
            },
            {
                **base,
                "id": "ai-rejected",
                "status": "filtered_out_ai",
                "current_reject_reason": "",
            },
            {
                **base,
                "id": "current-reject-conflict",
                "status": "filtered_out",
                "current_reject_reason": "off_domain",
            },
            {
                **base,
                "id": "manual-skipped",
                "status": "skipped",
                "current_reject_reason": "",
            },
            {
                **base,
                "id": "stale-never-requeue",
                "status": "filtered_out_stale_window",
                "current_reject_reason": "",
            },
        ],
        limit=5,
    )

    assert report["overall"]["candidate_count"] == 2
    assert report["overall"]["auto_requeue_candidate_count"] == 1
    assert report["overall"]["manual_review_candidate_count"] == 1
    assert report["overall"]["stale_window_safety_excluded_count"] == 1
    assert report["by_status"] == {"filtered_out_ad": 1, "skipped": 1}
    assert report["by_rescue_mode"] == {"auto_requeue": 1, "manual_review": 1}
    assert report["auto_requeue_samples"][0]["id"] == "auto-filtered"
    assert report["manual_review_samples"][0]["id"] == "manual-skipped"


def test_viral_handoff_audit_reports_query_variant_quality_feedback(tmp_path):
    db_path, conn = _make_db(tmp_path)
    good_variant = "axis_scar:specific_surgery_scar"
    weak_variant = "axis_skin:specific_acne"
    weak_family_variant = "colloquial:face_balance"
    weak_scale_variant = "consultation_community:thin_signal"

    for idx in range(3):
        _insert_target(
            conn,
            target_id=f"variant-good-{idx}",
            scan_id=144,
            category="scar",
            grade="A",
            status="pending",
            priority=135,
            title=f"Cheongju scar review {idx}",
            content_preview="patient review asks about scar treatment cost and consultation",
            breakdown={
                "pathfinder_source_keyword": "cheongju surgery scar review",
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": good_variant,
                "pathfinder_axis_fit_score": 91,
                "pathfinder_lens_fit_score": 88,
                "clinic_treatment_fit_score": 92,
                "worksite_efficiency_score": 86,
            },
        )

    for idx in range(20):
        _insert_target(
            conn,
            target_id=f"variant-weak-{idx}",
            scan_id=144,
            category="skin",
            grade="B",
            status="filtered_out_ai",
            priority=80,
            title=f"provider promo acne skin {idx}",
            content_preview="brand promotion without patient question",
            breakdown={
                "pathfinder_source_keyword": "skin acne blog promo",
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": weak_variant,
                "pathfinder_axis_fit_score": 24,
                "pathfinder_lens_fit_score": 18,
                "clinic_treatment_fit_score": 22,
                "worksite_efficiency_score": 12,
            },
        )

    for idx in range(60):
        _insert_target(
            conn,
            target_id=f"variant-family-weak-{idx}",
            scan_id=144,
            category="asymmetry",
            grade="B",
            status="filtered_out_ad",
            priority=70,
            title=f"ad facial balance {idx}",
            content_preview="advertising page without local patient intent",
            breakdown={
                "pathfinder_source_keyword": "face balance ad",
                "pathfinder_execution_lens": "consultation",
                "pathfinder_query_variant": weak_family_variant,
                "pathfinder_axis_fit_score": 20,
                "pathfinder_lens_fit_score": 16,
                "clinic_treatment_fit_score": 18,
                "worksite_efficiency_score": 10,
            },
        )

    for idx in range(2):
        _insert_target(
            conn,
            target_id=f"variant-weak-scale-survivor-{idx}",
            scan_id=144,
            category="consultation",
            grade="A",
            status="pending",
            priority=120,
            title=f"thin consultation survivor {idx}",
            content_preview="patient asks a local consultation question",
            breakdown={
                "pathfinder_source_keyword": "thin consultation keyword",
                "pathfinder_execution_lens": "consultation",
                "pathfinder_query_variant": weak_scale_variant,
                "pathfinder_axis_fit_score": 91,
                "pathfinder_lens_fit_score": 86,
                "clinic_treatment_fit_score": 90,
                "worksite_efficiency_score": 82,
            },
        )

    for idx in range(158):
        _insert_target(
            conn,
            target_id=f"variant-weak-scale-lost-{idx}",
            scan_id=144,
            category="consultation",
            grade="B",
            status="filtered_out",
            priority=55,
            title=f"thin consultation lost {idx}",
            content_preview="generic provider mention without workable patient context",
            breakdown={
                "pathfinder_source_keyword": "thin consultation keyword",
                "pathfinder_execution_lens": "consultation",
                "pathfinder_query_variant": weak_scale_variant,
                "pathfinder_axis_fit_score": 24,
                "pathfinder_lens_fit_score": 20,
                "clinic_treatment_fit_score": 18,
                "worksite_efficiency_score": 12,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=144,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    feedback = report["variant_quality_feedback"]
    assert feedback["counts"]["scale_variants"] >= 1
    assert feedback["scale_variants"][0]["variant"] == good_variant
    assert not any(item["variant"] == weak_scale_variant for item in feedback["scale_variants"])
    assert not any(
        item["variant"] == weak_scale_variant for item in feedback["scale_category_lens_variants"]
    )
    assert any(item["variant"] == weak_scale_variant for item in feedback["repair_variants"])
    assert any(item["variant"] == weak_variant for item in feedback["repair_variants"])
    assert any(item["variant"] == weak_variant for item in feedback["retire_variants"])
    assert any(
        item["variant"] == weak_variant and item["lens"] == "review"
        for item in feedback["repair_category_lens_variants"]
    )
    assert any(
        item["variant"] == weak_variant and item["lens"] == "review"
        for item in feedback["retire_category_lens_variants"]
    )
    assert any(item["family"] == "colloquial" for item in feedback["repair_families"])
    assert any(item["family"] == "colloquial" for item in feedback["retire_families"])

    playbook = report["next_run_playbook"]
    assert playbook["variant_quality_feedback_required"] is True
    assert any(item["variant"] == weak_variant for item in playbook["variant_actions"]["retire_or_pause"])
    assert any(
        item["variant"] == weak_variant
        for item in playbook["variant_actions"]["retire_category_lens_or_pause"]
    )
    assert any(
        item["family"] == "colloquial"
        for item in playbook["variant_actions"]["retire_family_or_pause"]
    )
    assert any(
        item["code"] == "query_variant_quality_feedback"
        for item in report["recommendations"]
    )


def test_viral_handoff_audit_uses_baseline_pathfinder_fit_scores_for_metric_coverage(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="baseline-fit-only",
        scan_id=145,
        category="scar",
        grade="A",
        status="pending",
        priority=130,
        title="Cheongju scar treatment review",
        content_preview="patient asks for local scar consultation and review",
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "base",
            "pathfinder_local_service_fit_score": 87,
            "pathfinder_content_actionability_score": 83,
            "clinic_treatment_fit_score": 91,
            "worksite_efficiency_score": 88,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=145,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert report["overall"]["axis_coverage_rate"] == 1.0
    assert report["overall"]["lens_coverage_rate"] == 1.0
    assert report["overall"]["avg_axis_fit"] == 87.0
    assert report["overall"]["avg_lens_fit"] == 83.0
    assert report["overall"]["strict_fit"] == 1


def test_viral_handoff_audit_since_filter_includes_rescanned_existing_targets(tmp_path):
    db_path, conn = _make_db(tmp_path)
    conn.execute("ALTER TABLE viral_targets ADD COLUMN last_scanned_at TEXT")
    for target_id, discovered_at, last_scanned_at in (
        ("rediscovered-current", "2026-06-01 09:00:00", "2026-06-03 10:00:00"),
        ("old-only", "2026-06-01 09:00:00", "2026-06-01 10:00:00"),
    ):
        _insert_target(
            conn,
            target_id=target_id,
            scan_id=55,
            category="흉터/여드름흉터",
            grade="A",
            status="pending",
            priority=120,
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "base",
                "pathfinder_axis_fit_score": 90,
                "pathfinder_lens_fit_score": 88,
                "clinic_treatment_fit_score": 91,
                "worksite_efficiency_score": 87,
            },
        )
        conn.execute(
            "UPDATE viral_targets SET discovered_at = ?, last_scanned_at = ? WHERE id = ?",
            (discovered_at, last_scanned_at, target_id),
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=55,
        since="2026-06-02 00:00:00",
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert report["row_count"] == 1
    assert report["filters"]["since"] == "2026-06-02 00:00:00"
    assert report["by_category"]["흉터/여드름흉터"]["total"] == 1


def test_viral_handoff_audit_reports_source_seed_level_quality(tmp_path):
    db_path, conn = _make_db(tmp_path)
    source_seed = "청주 수술흉터 새살침 상담"
    companion_seed = "청주 켈로이드 흉터 한의원 후기"
    for idx, status in enumerate(("filtered_out_ai", "filtered_out_ad", "pending"), start=1):
        _insert_target(
            conn,
            target_id=f"scar-seed-{idx}",
            scan_id=56,
            category="흉터/여드름흉터",
            grade="A",
            status=status,
            priority=130 - idx,
            breakdown={
                "pathfinder_source_keyword": source_seed,
                "pathfinder_source_keywords": [source_seed, companion_seed],
                "pathfinder_execution_lens": "consultation",
                "pathfinder_query_variant": "axis_scar:specific_수술흉터",
                "pathfinder_axis_fit_score": 90,
                "pathfinder_lens_fit_score": 50 if status != "pending" else 84,
                "clinic_treatment_fit_score": 85,
                "worksite_efficiency_score": 42 if status != "pending" else 86,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=56,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    seed_metrics = report["by_source_seed"][source_seed]
    assert seed_metrics["category"] == "흉터/여드름흉터"
    assert seed_metrics["total"] == 3
    assert seed_metrics["credit_total"] == 3
    assert seed_metrics["primary_total"] == 3
    assert seed_metrics["assist_total"] == 0
    assert seed_metrics["strict_fit"] == 1
    assert seed_metrics["query_variant_counts"] == {"axis_scar:specific_수술흉터": 3}
    companion_metrics = report["by_source_seed"][companion_seed]
    assert companion_metrics["category"] == "흉터/여드름흉터"
    assert companion_metrics["total"] == 3
    assert companion_metrics["credit_total"] == 3
    assert companion_metrics["primary_total"] == 0
    assert companion_metrics["assist_total"] == 3
    assert companion_metrics["credit_note"] == "total is source-seed credit count; row_count is not duplicated"
    assert companion_metrics["strict_fit"] == 1
    assert report["review_samples"]["priority_focus_weak_lane_samples"][0]["samples"][0]["source_seeds"] == [
        source_seed,
        companion_seed,
    ]

    weak_seed = report["weak_source_seeds"][0]
    assert weak_seed["seed"] == source_seed
    assert weak_seed["category"] == "흉터/여드름흉터"
    assert weak_seed["credit_total"] == 3
    assert weak_seed["primary_total"] == 3
    assert "low_survival_rate" in weak_seed["reasons"]

    weak_names = [item["seed"] for item in report["weak_source_seeds"][:2]]
    assert weak_names == [source_seed, companion_seed]

    feedback = report["source_seed_feedback"]
    assert feedback["counts"]["scale_candidates"] == 1
    assert feedback["counts"]["assist_only_candidates"] == 1
    scale_seed = feedback["scale_candidates"][0]
    assert scale_seed["seed"] == source_seed
    assert scale_seed["action"] == "scale_or_keep"
    assert scale_seed["strict_fit"] == 1
    assist_seed = feedback["assist_only_candidates"][0]
    assert assist_seed["seed"] == companion_seed
    assert assist_seed["action"] == "merge_or_keep_as_companion"


def test_review_samples_prioritize_gyulim_focus_lanes_over_peripheral_weak_lanes(tmp_path):
    db_path, conn = _make_db(tmp_path)
    for idx in range(4):
        _insert_target(
            conn,
            target_id=f"immune-filtered-{idx}",
            scan_id=45,
            category="면역/보약",
            grade="B",
            status="filtered_out_ai",
            priority=150,
            breakdown={
                "pathfinder_execution_lens": "availability",
                "pathfinder_query_variant": "base",
                "pathfinder_axis_fit_score": 72,
                "pathfinder_lens_fit_score": 28,
                "clinic_treatment_fit_score": 40,
                "worksite_efficiency_score": 30,
            },
        )
    for idx, category in enumerate(("흉터/여드름흉터", "안면비대칭"), start=1):
        _insert_target(
            conn,
            target_id=f"focus-filtered-{idx}",
            scan_id=45,
            category=category,
            grade="A",
            status="filtered_out_ai",
            priority=130,
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 88,
                "pathfinder_lens_fit_score": 52,
                "clinic_treatment_fit_score": 84,
                "worksite_efficiency_score": 44,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=45,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    weak_samples = report["review_samples"]["weak_lane_samples"]
    assert weak_samples[0]["lane"] == "면역/보약"

    focus_samples = report["review_samples"]["priority_focus_weak_lane_samples"]
    assert focus_samples[0]["type"] == "category"
    assert focus_samples[0]["lane"] == "흉터/여드름흉터"
    assert focus_samples[0]["focus_category"] == "흉터/여드름흉터"
    assert "면역/보약" not in {sample["focus_category"] for sample in focus_samples}
    assert report["quality_bar"]["priority_focus_weak_lanes"][0]["lane"] == "흉터/여드름흉터"


def test_weak_lane_diagnostic_samples_prefer_problem_cases_over_successes(tmp_path):
    db_path, conn = _make_db(tmp_path)
    for idx, priority in enumerate((140, 135, 130), start=1):
        _insert_target(
            conn,
            target_id=f"scar-filtered-{idx}",
            scan_id=46,
            category="흉터/여드름흉터",
            grade="A",
            status="filtered_out_ai",
            priority=priority,
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 88,
                "pathfinder_lens_fit_score": 52,
                "clinic_treatment_fit_score": 84,
                "worksite_efficiency_score": 44,
            },
        )
    _insert_target(
        conn,
        target_id="scar-strict-success",
        scan_id=46,
        category="흉터/여드름흉터",
        grade="S",
        status="pending",
        priority=200,
        breakdown={
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "axis_scar:specific_수술흉터",
            "pathfinder_axis_fit_score": 92,
            "pathfinder_lens_fit_score": 90,
            "clinic_treatment_fit_score": 90,
            "worksite_efficiency_score": 88,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=46,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_samples = report["review_samples"]["priority_focus_weak_lane_samples"]
    scar_category = next(
        sample for sample in focus_samples
        if sample["type"] == "category" and sample["lane"] == "흉터/여드름흉터"
    )
    assert scar_category["samples"][0]["status"] == "filtered_out_ai"
    assert scar_category["samples"][0]["priority"] == 140


def test_viral_handoff_audit_recategorizes_legacy_skin_scar_targets(tmp_path):
    db_path, conn = _make_db(tmp_path)
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, url, title, platform, category, matched_keyword, matched_keywords,
            matched_keyword_grade, matched_keyword_category, comment_status,
            priority_score, score_breakdown, source_scan_run_id, discovered_at
        ) VALUES (?, ?, ?, 'kin', ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            "legacy-scar",
            "https://example.com/legacy-scar",
            "청주 여드름흉터 새살침 상담",
            "피부/여드름",
            "청주 여드름흉터 새살침 상담",
            json.dumps(["청주 여드름흉터 새살침 상담"], ensure_ascii=False),
            "A",
            "피부/여드름",
            "pending",
            120,
            json.dumps(
                {
                    "pathfinder_execution_lens": "consultation",
                    "pathfinder_axis_fit_score": 86,
                    "pathfinder_lens_fit_score": 80,
                    "clinic_treatment_fit_score": 88,
                    "worksite_efficiency_score": 82,
                },
                ensure_ascii=False,
            ),
            77,
        ),
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=77,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    assert set(report["by_category"]) == {"흉터/여드름흉터"}
    assert report["by_category"]["흉터/여드름흉터"]["total"] == 1
    assert report["review_samples"]["weak_lane_samples"] == []


def test_viral_handoff_audit_flags_source_seed_category_drift(tmp_path):
    db_path, conn = _make_db(tmp_path)
    source_seed = "가경동 만성비염 한의원 치료기간"
    _insert_target(
        conn,
        target_id="skin-rhinitis-drift",
        scan_id=78,
        category="피부/여드름",
        grade="A",
        status="filtered_out_ai",
        priority=118,
        breakdown={
            "pathfinder_source_keyword": source_seed,
            "pathfinder_execution_lens": "consultation",
            "pathfinder_query_variant": "base",
            "pathfinder_axis_fit_score": 28,
            "pathfinder_lens_fit_score": 74,
            "clinic_treatment_fit_score": 40,
            "worksite_efficiency_score": 35,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=78,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    seed_metrics = report["by_source_seed"][source_seed]
    assert seed_metrics["category"] == "피부/여드름"
    assert seed_metrics["detected_category"] == "호흡기/알레르기"
    assert seed_metrics["category_drift"] is True
    assert seed_metrics["category_drift_count"] == 1
    assert seed_metrics["category_drift_rate"] == 1.0

    feedback = report["source_seed_feedback"]
    assert feedback["counts"]["recategorize_candidates"] == 1
    recategorize = feedback["recategorize_candidates"][0]
    assert recategorize["seed"] == source_seed
    assert recategorize["category"] == "피부/여드름"
    assert recategorize["detected_category"] == "호흡기/알레르기"
    assert recategorize["action"] == "recategorize_or_quarantine"
    assert "source_seed_category_drift" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["source_seed_feedback_required"] is True
    assert report["next_run_playbook"]["source_seed_actions"]["recategorize_or_quarantine"][0]["seed"] == source_seed
    assert any(
        item["code"] == "source_seed_category_drift"
        for item in report["recommendations"]
    )


def test_viral_handoff_audit_flags_missing_pathfinder_source_lineage(tmp_path):
    db_path, conn = _make_db(tmp_path)
    category = _priority_focus_categories()[0]
    source_breakdown = {
        "pathfinder_source_keyword": "cheongju scar source seed",
        "pathfinder_execution_lens": "review",
        "pathfinder_query_variant": "patient_voice_question_kin",
        "pathfinder_axis_fit_score": 90,
        "pathfinder_lens_fit_score": 88,
        "clinic_treatment_fit_score": 91,
        "worksite_efficiency_score": 87,
    }
    missing_breakdown = {
        "pathfinder_execution_lens": "review",
        "pathfinder_query_variant": "patient_voice_question_kin",
        "pathfinder_axis_fit_score": 90,
        "pathfinder_lens_fit_score": 88,
        "clinic_treatment_fit_score": 91,
        "worksite_efficiency_score": 87,
    }
    _insert_target(
        conn,
        target_id="lineage-present",
        scan_id=147,
        category=category,
        grade="A",
        status="pending",
        priority=121,
        title="Cheongju scar review with explicit lineage",
        breakdown=source_breakdown,
    )
    _insert_target(
        conn,
        target_id="lineage-missing",
        scan_id=147,
        category=category,
        grade="A",
        status="pending",
        priority=139,
        title="Cheongju scar review missing source lineage",
        breakdown=missing_breakdown,
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=147,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    lineage = report["source_lineage_quality"]
    assert lineage["overall"]["source_seed_present"] == 1
    assert lineage["overall"]["source_seed_missing"] == 1
    assert lineage["overall"]["source_seed_fallback_count"] == 1
    assert lineage["overall"]["source_seed_coverage_rate"] == 0.5
    assert lineage["overall"]["priority_focus_source_seed_coverage_rate"] == 0.5
    assert lineage["overall"]["actionable_strict_source_seed_coverage_rate"] == 0.5
    sample = lineage["missing_samples"][0]
    assert sample["id"] == "lineage-missing"
    assert "fallback_matched_keyword_used" in sample["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "source_lineage_coverage" in failed
    assert "query_variant_lineage_coverage" not in failed
    assert report["quality_bar"]["source_seed_integrity"]["source_seed_coverage_rate"] == 0.5
    assert report["next_run_playbook"]["source_lineage_repair_required"] is True
    assert report["next_run_playbook"]["source_lineage_missing_samples"][0]["id"] == "lineage-missing"
    assert any(
        item["code"] == "source_lineage_coverage_low"
        for item in report["recommendations"]
    )


def test_viral_handoff_audit_flags_content_category_mismatch(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="skin-target-diet-content",
        scan_id=79,
        category="피부/여드름",
        grade="A",
        status="pending",
        priority=125,
        title="청주 다이어트 한약 후기 궁금해요",
        content_preview="비만 때문에 감량 한약을 알아보고 있습니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름 한의원 후기",
            "pathfinder_execution_lens": "review",
            "pathfinder_query_variant": "base",
            "pathfinder_axis_fit_score": 82,
            "pathfinder_lens_fit_score": 81,
            "clinic_treatment_fit_score": 86,
            "worksite_efficiency_score": 84,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=79,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    overall = report["overall"]
    assert overall["content_category_observed"] == 1
    assert overall["content_category_mismatch"] == 1
    assert overall["content_category_mismatch_rate"] == 1.0
    assert report["by_category"]["피부/여드름"]["content_category_mismatch"] == 1
    assert report["quality_bar"]["content_coherence"]["mismatch_rate"] == 1.0
    assert "content_category_mismatch" in report["quality_bar"]["failed_advisory_gates"]
    assert any(
        item["code"] == "content_category_mismatch"
        for item in report["recommendations"]
    )
    assert report["next_run_playbook"]["content_coherence_required"] is True
    sample = report["review_samples"]["top_strict_fit"][0]
    assert sample["content_detected_category"] == "다이어트"
    assert sample["content_category_mismatch"] is True


def test_category_drift_requires_an_observed_detected_category():
    """An absent detector result is unknown, not the fallback ``기타`` bucket."""
    assert _category_drift_detected("피부/여드름", "") is False
    assert _category_drift_detected("피부/여드름", "다이어트") is True


def test_viral_handoff_audit_flags_lens_surface_mismatch_and_bridge_match(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="cost-lens-no-cost-surface",
        scan_id=80,
        category="피부/여드름",
        grade="A",
        status="pending",
        priority=126,
        title="청주 여드름 치료 궁금해요",
        content_preview="성인여드름 때문에 한의원 알아보고 있습니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름 비용",
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost:비용",
            "pathfinder_axis_fit_score": 86,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 88,
            "worksite_efficiency_score": 86,
        },
    )
    _insert_target(
        conn,
        target_id="cost-lens-no-cost-surface-2",
        scan_id=80,
        category="피부/여드름",
        grade="A",
        status="pending",
        priority=124,
        title="청주 여드름 치료 알아보고 있어요",
        content_preview="성인여드름 때문에 한의원 치료를 고민하고 있습니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름 비용",
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost:비용",
            "pathfinder_axis_fit_score": 86,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 88,
            "worksite_efficiency_score": 86,
        },
    )
    _insert_target(
        conn,
        target_id="cost-lens-community-bridge",
        scan_id=80,
        category="피부/여드름",
        grade="A",
        status="pending",
        priority=125,
        title="청주 여드름 한의원 추천 부탁드려요",
        content_preview="여드름 치료 괜찮은 곳 가보신 분 있나요?",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름 비용",
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost_community:추천",
            "pathfinder_axis_fit_score": 86,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 88,
            "worksite_efficiency_score": 86,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=80,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    overall = report["overall"]
    assert overall["lens_surface_checked"] == 3
    assert overall["lens_surface_matched"] == 1
    assert overall["lens_surface_mismatch"] == 2
    assert overall["lens_surface_mismatch_rate"] == 0.6667
    assert "lens_surface_mismatch" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["lens_surface_required"] is True
    assert any(
        item["code"] == "lens_surface_mismatch"
        for item in report["recommendations"]
    )
    samples = report["review_samples"]["top_strict_fit"]
    mismatch_sample = next(sample for sample in samples if sample["id"] == "cost-lens-no-cost-surface")
    bridge_sample = next(sample for sample in samples if sample["id"] == "cost-lens-community-bridge")
    assert mismatch_sample["lens_surface_matched"] is False
    assert bridge_sample["lens_surface_matched"] is True
    assert bridge_sample["lens_surface_bridge_terms"]
    lens_samples = report["review_samples"]["lens_surface_mismatch_samples"]
    assert lens_samples[0]["samples"][0]["id"] == "cost-lens-no-cost-surface"
    assert lens_samples[0]["mismatch_rate"] == 0.6667


def test_viral_handoff_audit_treats_community_base_as_transactional_lens_bridge(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="cost-lens-community-base-bridge",
        scan_id=180,
        category="흉터/여드름흉터",
        grade="A",
        status="pending",
        priority=125,
        title="청주 여드름흉터 새살침 추천 부탁드려요",
        content_preview="실제 경험이나 후기 있는 곳이 궁금합니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름흉터 비용",
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "community_base",
            "pathfinder_axis_fit_score": 86,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 88,
            "worksite_efficiency_score": 86,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=180,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    overall = report["overall"]
    assert overall["lens_surface_checked"] == 1
    assert overall["lens_surface_matched"] == 1
    assert overall["lens_surface_mismatch"] == 0
    sample = report["review_samples"]["top_strict_fit"][0]
    assert sample["lens_surface_matched"] is True
    assert sample["lens_surface_bridge_terms"]


def test_viral_handoff_audit_averages_clinic_and_worksite_over_observed_scores(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="observed-worksite-fit",
        scan_id=181,
        category="흉터/여드름흉터",
        grade="A",
        status="pending",
        priority=125,
        title="청주 여드름흉터 새살침 상담 궁금합니다",
        content_preview="후기 보고 치료 상담을 받아볼지 고민 중입니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름흉터 상담",
            "pathfinder_execution_lens": "consultation",
            "pathfinder_query_variant": "community_base",
            "pathfinder_axis_fit_score": 86,
            "pathfinder_lens_fit_score": 84,
            "clinic_treatment_fit_score": 88,
            "worksite_efficiency_score": 86,
        },
    )
    _insert_target(
        conn,
        target_id="early-filter-no-worksite-score",
        scan_id=181,
        category="흉터/여드름흉터",
        grade="A",
        status="filtered_out_ad",
        priority=80,
        title="청주 여드름흉터 광고 안내",
        content_preview="병원 이벤트 안내 글입니다.",
        breakdown={
            "pathfinder_source_keyword": "청주 여드름흉터 상담",
            "pathfinder_execution_lens": "consultation",
            "pathfinder_query_variant": "community_base",
            "pathfinder_axis_fit_score": 82,
            "pathfinder_lens_fit_score": 70,
        },
    )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=181,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    overall = report["overall"]
    assert overall["avg_clinic_fit"] == 88.0
    assert overall["avg_worksite_efficiency"] == 86.0
    assert overall["clinic_fit_observed"] == 1
    assert overall["worksite_efficiency_observed"] == 1
    assert overall["clinic_fit_coverage_rate"] == 0.5
    assert overall["worksite_efficiency_coverage_rate"] == 0.5
    quality_bar = report["quality_bar"]
    assert quality_bar["metric_coverage"]["minimum_rate"] == 0.5
    assert quality_bar["metric_coverage"]["clinic_fit_coverage_rate"] == 0.5
    assert quality_bar["metric_coverage"]["worksite_efficiency_coverage_rate"] == 0.5
    assert "metric_coverage" in quality_bar["failed_required_gates"]
    playbook = report["next_run_playbook"]
    assert playbook["metric_backfill_required"] is True
    assert {
        "clinic_fit_metric_coverage_low",
        "worksite_efficiency_metric_coverage_low",
    }.issubset({item["code"] for item in playbook["metric_backfill_gaps"]})
    assert any(
        item["code"] == "clinic_fit_metric_coverage_low"
        for item in report["recommendations"]
    )
    assert any(
        item["code"] == "worksite_efficiency_metric_coverage_low"
        for item in report["recommendations"]
    )
    assert all(
        "low_worksite_efficiency" not in item["reasons"]
        for item in report["weak_lanes"]
    )


def test_mismatch_playbook_prioritizes_gyulim_focus_axes(tmp_path):
    db_path, conn = _make_db(tmp_path)
    for idx in range(3):
        _insert_target(
            conn,
            target_id=f"immune-content-mismatch-{idx}",
            scan_id=81,
            category="면역/보약",
            grade="B",
            status="filtered_out_ai",
            priority=150,
            title="청주 다이어트 한약 후기 궁금해요",
            content_preview="비만 때문에 감량 한약을 알아보고 있습니다.",
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 40,
                "pathfinder_lens_fit_score": 50,
                "clinic_treatment_fit_score": 40,
                "worksite_efficiency_score": 35,
            },
        )
    for idx in range(3):
        _insert_target(
            conn,
            target_id=f"scar-content-mismatch-{idx}",
            scan_id=81,
            category="흉터/여드름흉터",
            grade="B",
            status="filtered_out_ai",
            priority=120,
            title="청주 다이어트 한약 후기 궁금해요",
            content_preview="비만 때문에 감량 한약을 알아보고 있습니다.",
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 40,
                "pathfinder_lens_fit_score": 50,
                "clinic_treatment_fit_score": 40,
                "worksite_efficiency_score": 35,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=81,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    assert report["next_run_playbook"]["content_mismatch_lanes"][0]["lane"] == "흉터/여드름흉터"
    assert report["review_samples"]["content_mismatch_samples"][0]["lane"] == "흉터/여드름흉터"
    assert report["review_samples"]["content_mismatch_samples"][0]["mismatch_rate"] == 1.0


def test_loss_analysis_prioritizes_gyulim_focus_filter_hotspots(tmp_path):
    db_path, conn = _make_db(tmp_path)
    for idx in range(3):
        _insert_target(
            conn,
            target_id=f"immune-loss-{idx}",
            scan_id=82,
            category="면역/보약",
            grade="B",
            status="filtered_out_ai",
            priority=150,
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 44,
                "pathfinder_lens_fit_score": 50,
                "clinic_treatment_fit_score": 40,
                "worksite_efficiency_score": 35,
            },
        )
    for idx in range(2):
        _insert_target(
            conn,
            target_id=f"scar-loss-{idx}",
            scan_id=82,
            category="흉터/여드름흉터",
            grade="A",
            status="filtered_out_clinic_mismatch",
            priority=120,
            breakdown={
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": "community_base",
                "pathfinder_axis_fit_score": 78,
                "pathfinder_lens_fit_score": 64,
                "clinic_treatment_fit_score": 38,
                "worksite_efficiency_score": 35,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=82,
        include_seed_baseline=False,
        min_lane_total=1,
    )

    loss = report["loss_analysis"]
    assert loss["overall"]["lost"] == 5
    assert loss["overall"]["loss_reason_counts"]["ai"] == 3
    assert loss["overall"]["loss_reason_counts"]["clinic_mismatch"] == 2
    focus_hotspot = loss["priority_focus_hotspots"][0]
    assert focus_hotspot["lane"] == "흉터/여드름흉터"
    assert focus_hotspot["dominant_loss_reason"] == "clinic_mismatch"
    assert report["next_run_playbook"]["filter_loss_required"] is True
    assert report["next_run_playbook"]["filter_loss_hotspots"][0]["lane"] == "흉터/여드름흉터"
    assert any(
        item["code"] == "priority_focus_filter_loss_hotspots"
        for item in report["recommendations"]
    )


def test_platform_surface_quality_prioritizes_gyulim_focus_axes(tmp_path):
    db_path, conn = _make_db(tmp_path)
    focus_category = _priority_focus_categories()[0]
    peripheral_category = "peripheral"

    for idx in range(4):
        _insert_target(
            conn,
            target_id=f"peripheral-blog-loss-{idx}",
            scan_id=83,
            category=peripheral_category,
            grade="B",
            status="filtered_out_ai",
            priority=170,
            platform="blog",
            breakdown={
                "pathfinder_execution_lens": "service",
                "pathfinder_query_variant": "base",
                "pathfinder_axis_fit_score": 35,
                "pathfinder_lens_fit_score": 35,
                "clinic_treatment_fit_score": 35,
                "worksite_efficiency_score": 35,
            },
        )
    for idx in range(2):
        _insert_target(
            conn,
            target_id=f"focus-blog-loss-{idx}",
            scan_id=83,
            category=focus_category,
            grade="A",
            status="filtered_out_clinic_mismatch",
            priority=130,
            platform="blog",
            breakdown={
                "pathfinder_execution_lens": "service",
                "pathfinder_query_variant": "base",
                "pathfinder_axis_fit_score": 82,
                "pathfinder_lens_fit_score": 80,
                "clinic_treatment_fit_score": 30,
                "worksite_efficiency_score": 45,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=83,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    lane = f"blog::{focus_category}"
    assert report["by_platform"]["blog"]["total"] == 6
    assert report["by_platform_category"][lane]["lost"] == 2

    quality = report["platform_surface_quality"]
    focus_hotspot = quality["priority_focus_hotspots"][0]
    assert focus_hotspot["lane"] == lane
    assert focus_hotspot["focus_category"] == focus_category
    assert "high_platform_loss" in focus_hotspot["reasons"]
    assert report["quality_bar"]["platform_surface"]["priority_focus_hotspots"] == 1
    assert "platform_surface_hotspots" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["platform_surface_required"] is True
    assert report["next_run_playbook"]["platform_surface_hotspots"][0]["lane"] == lane
    assert report["review_samples"]["platform_surface_samples"][0]["lane"] == lane
    assert any(
        item["code"] == "priority_focus_platform_surface_hotspots"
        for item in report["recommendations"]
    )


def test_patient_journey_coverage_boosts_missing_focus_lens(tmp_path):
    db_path, conn = _make_db(tmp_path)
    focus_category = _priority_focus_categories()[0]
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    for idx, (lens, terms) in enumerate(terms_by_lens.items(), start=1):
        _insert_target(
            conn,
            target_id=f"journey-present-{idx}",
            scan_id=84,
            category=focus_category,
            grade="A",
            status="pending",
            priority=140,
            title=f"청주 {focus_category} {terms}",
            breakdown={
                "pathfinder_execution_lens": lens,
                "pathfinder_query_variant": f"{lens}:{terms}",
                "pathfinder_axis_fit_score": 90,
                "pathfinder_lens_fit_score": 88,
                "clinic_treatment_fit_score": 91,
                "worksite_efficiency_score": 87,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=84,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    expected_lane = f"{focus_category}::cost"
    journey = report["patient_journey_coverage"]
    assert journey["by_category"][focus_category]["strict_lens_coverage_rate"] == 0.8333
    assert journey["priority_focus_gaps"][0]["lane"] == expected_lane
    assert journey["priority_focus_gaps"][0]["reasons"] == ["no_targets"]
    assert "patient_journey_strict_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["patient_journey_required"] is True
    assert report["next_run_playbook"]["patient_journey_gaps"][0]["lane"] == expected_lane
    assert f'--boost-category "{focus_category}"' in report["next_run_playbook"]["suggested_commands"]["live_scan"]
    assert '--boost-lens "cost"' in report["next_run_playbook"]["suggested_commands"]["live_scan"]
    assert f'--boost-category-lens "{expected_lane}"' in report["next_run_playbook"]["suggested_commands"]["live_scan"]
    assert any(
        item["code"] == "patient_journey_coverage_gaps"
        for item in report["recommendations"]
    )


def test_patient_journey_coverage_flags_backlog_only_strict_candidates(tmp_path):
    db_path, conn = _make_db(tmp_path)
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in terms_by_lens.items():
            _insert_target(
                conn,
                target_id=f"journey-backlog-{idx}",
                scan_id=85,
                category=category,
                grade="A",
                status="raw_backlog",
                priority=140,
                title=f"청주 {category} {terms}",
                breakdown={
                    "pathfinder_execution_lens": lens,
                    "pathfinder_query_variant": f"{lens}:{terms}",
                    "pathfinder_axis_fit_score": 90,
                    "pathfinder_lens_fit_score": 88,
                    "clinic_treatment_fit_score": 91,
                    "worksite_efficiency_score": 87,
                },
            )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=85,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    journey = report["patient_journey_coverage"]
    assert journey["overall"]["strict_coverage_rate"] == 1.0
    assert journey["overall"]["actionable_strict_coverage_rate"] == 0.0
    assert report["overall"]["strict_fit_rate"] == 1.0
    assert report["overall"]["actionable_strict_rate"] == 0.0
    assert "patient_journey_strict_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "patient_journey_actionable_strict_coverage" in report["quality_bar"]["failed_advisory_gates"]
    first_gap = journey["priority_focus_gaps"][0]
    assert first_gap["category"] == _priority_focus_categories()[0]
    assert "no_actionable_strict" in first_gap["reasons"]
    assert report["next_run_playbook"]["patient_journey_required"] is True
    assert "no_actionable_strict" in report["next_run_playbook"]["patient_journey_gaps"][0]["reasons"]


def test_work_queue_readiness_requires_repeatable_actionable_depth(tmp_path):
    db_path, conn = _make_db(tmp_path)
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in terms_by_lens.items():
            _insert_target(
                conn,
                target_id=f"queue-thin-{idx}",
                scan_id=86,
                category=category,
                grade="A",
                status="pending",
                priority=140,
                title=f"청주 {category} {terms}",
                breakdown={
                    "pathfinder_execution_lens": lens,
                    "pathfinder_query_variant": f"{lens}:{terms}",
                    "pathfinder_axis_fit_score": 90,
                    "pathfinder_lens_fit_score": 88,
                    "clinic_treatment_fit_score": 91,
                    "worksite_efficiency_score": 87,
                },
            )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=86,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    assert queue["overall"]["category_ready_rate"] == 1.0
    assert queue["overall"]["category_lens_ready_rate"] == 0.0
    assert queue["priority_gaps"][0]["lane"] == expected_lane
    assert queue["priority_gaps"][0]["actionable_strict"] == 1
    assert queue["priority_gaps"][0]["target"] == 2
    assert queue["priority_gaps"][0]["reasons"] == ["thin_lens_queue"]
    assert "work_queue_lens_depth" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["work_queue_required"] is True
    assert report["next_run_playbook"]["work_queue_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["work_queue_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "work_queue_depth_gaps"
        for item in report["recommendations"]
    )


def test_fresh_work_queue_readiness_flags_stale_actionable_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in terms_by_lens.items():
            for copy_idx in range(2):
                _insert_target(
                    conn,
                    target_id=f"queue-stale-{idx}-{copy_idx}",
                    scan_id=87,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    title=f"청주 {category} {terms}",
                    discovered_at="2000-01-01 00:00:00",
                    breakdown={
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": f"{lens}:{terms}",
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=87,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    assert queue["overall"]["category_lens_ready_rate"] == 1.0
    assert queue["overall"]["fresh_category_lens_ready_rate"] == 0.0
    assert queue["fresh_priority_gaps"][0]["lane"] == expected_lane
    assert queue["fresh_priority_gaps"][0]["fresh_actionable_strict"] == 0
    assert "stale_lens_inventory" in queue["fresh_priority_gaps"][0]["reasons"]
    assert "work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_work_queue_lens_depth" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["fresh_work_queue_required"] is True
    assert report["next_run_playbook"]["fresh_work_queue_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_work_queue_gap_samples"][0]["samples"][0]["fresh_activity"] is False
    assert any(
        item["code"] == "fresh_work_queue_depth_gaps"
        for item in report["recommendations"]
    )


def test_unique_work_queue_readiness_flags_duplicate_actionable_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            for copy_idx in range(2):
                _insert_target(
                    conn,
                    target_id=f"queue-duplicate-{idx}-{copy_idx}",
                    scan_id=88,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    title=f"duplicate queue {category} {lens}",
                    breakdown={
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": f"{lens}:duplicate",
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=88,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    assert queue["overall"]["category_lens_ready_rate"] == 1.0
    assert queue["overall"]["fresh_category_lens_ready_rate"] == 1.0
    assert queue["overall"]["unique_category_lens_ready_rate"] == 0.0
    assert queue["overall"]["fresh_unique_category_lens_ready_rate"] == 0.0
    assert queue["unique_priority_gaps"][0]["lane"] == expected_lane
    assert queue["unique_priority_gaps"][0]["actionable_strict"] == 2
    assert queue["unique_priority_gaps"][0]["unique_actionable_strict"] == 1
    assert queue["unique_priority_gaps"][0]["actionable_strict_duplicate_count"] == 1
    assert "duplicate_lens_inventory" in queue["unique_priority_gaps"][0]["reasons"]
    assert "work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "unique_work_queue_lens_depth" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_unique_work_queue_lens_depth" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["unique_work_queue_required"] is True
    assert report["next_run_playbook"]["fresh_unique_work_queue_required"] is True
    assert report["next_run_playbook"]["unique_work_queue_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["unique_work_queue_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_unique_work_queue_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "unique_work_queue_depth_gaps"
        for item in report["recommendations"]
    )


def test_opportunity_diversity_flags_single_surface_seed_and_query_family(tmp_path):
    db_path, conn = _make_db(tmp_path)
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in terms_by_lens.items():
            for copy_idx in range(2):
                _insert_target(
                    conn,
                    target_id=f"queue-concentrated-{idx}-{copy_idx}",
                    scan_id=89,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform="kin",
                    content_preview=f"distinct opportunity {idx}-{copy_idx}",
                    title=f"청주 {category} {terms}",
                    breakdown={
                        "pathfinder_source_keyword": f"청주 {category} {lens} 단일시드",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": f"{lens}:same-family",
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=89,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 0.0
    assert diversity["overall"]["fresh_category_lens_diversity_ready_rate"] == 0.0
    first_gap = diversity["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["platform_count"] == 1
    assert first_gap["source_seed_count"] == 1
    assert first_gap["variant_family_count"] == 1
    assert "single_platform_dependency" in first_gap["reasons"]
    assert "single_source_seed_dependency" in first_gap["reasons"]
    assert "single_query_family_dependency" in first_gap["reasons"]
    assert "unique_work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "opportunity_diversity_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_opportunity_diversity_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["opportunity_diversity_required"] is True
    assert report["next_run_playbook"]["fresh_opportunity_diversity_required"] is True
    assert report["next_run_playbook"]["opportunity_diversity_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["opportunity_diversity_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_opportunity_diversity_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "opportunity_diversity_gaps"
        for item in report["recommendations"]
    )


def test_engagement_hook_quality_flags_generic_actionable_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-no-hook-{idx}-{copy_idx}",
                    scan_id=90,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"general treatment summary {idx}-{copy_idx}",
                    title=f"{category} information packet {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=90,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 0.0
    assert hook_quality["overall"]["fresh_category_lens_hook_ready_rate"] == 0.0
    first_gap = hook_quality["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["hooked_actionable_strict"] == 0
    assert first_gap["engagement_hook_missing"] == 2
    assert "no_hooked_actionable_strict" in first_gap["reasons"]
    assert "missing_engagement_hook" in first_gap["reasons"]
    assert "unique_work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "opportunity_diversity_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "engagement_hook_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_engagement_hook_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["engagement_hook_required"] is True
    assert report["next_run_playbook"]["fresh_engagement_hook_required"] is True
    assert report["next_run_playbook"]["engagement_hook_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["engagement_hook_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_engagement_hook_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "engagement_hook_gaps"
        for item in report["recommendations"]
    )


def test_treatment_signature_quality_flags_generic_patient_intent_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    terms_by_lens = {
        "review": "후기 추천",
        "community": "추천 궁금",
        "cost": "비용 가격",
        "consultation": "상담 문의",
        "availability": "예약 주차",
        "safety": "부작용 회복",
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in terms_by_lens.items():
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-no-signature-{idx}-{copy_idx}",
                    scan_id=91,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"general local clinic question {idx}-{copy_idx}",
                    title=f"청주 {terms} 어디가 괜찮나요 {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=91,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 0.0
    assert signature_quality["overall"]["fresh_category_lens_signature_ready_rate"] == 0.0
    first_gap = signature_quality["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["signature_actionable_strict"] == 0
    assert first_gap["treatment_signature_missing"] == 2
    assert "no_treatment_signature" in first_gap["reasons"]
    assert "missing_treatment_signature" in first_gap["reasons"]
    assert "unique_work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "opportunity_diversity_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "engagement_hook_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "treatment_signature_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_treatment_signature_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["treatment_signature_required"] is True
    assert report["next_run_playbook"]["fresh_treatment_signature_required"] is True
    assert report["next_run_playbook"]["treatment_signature_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["treatment_signature_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_treatment_signature_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "treatment_signature_gaps"
        for item in report["recommendations"]
    )


def test_local_intent_quality_flags_nonlocal_patient_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            terms = " ".join(ENGAGEMENT_HOOK_LENS_TERMS[lens][:2])
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-no-local-{idx}-{copy_idx}",
                    scan_id=92,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"general nonlocal clinic question {idx}-{copy_idx}",
                    title=f"{category} {terms} patient question {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=92,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    local_quality = report["local_intent_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 0.0
    assert local_quality["overall"]["fresh_category_lens_local_ready_rate"] == 0.0
    first_gap = local_quality["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["local_actionable_strict"] == 0
    assert first_gap["local_intent_missing"] == 2
    assert "no_local_intent" in first_gap["reasons"]
    assert "missing_local_intent" in first_gap["reasons"]
    assert "unique_work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "opportunity_diversity_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "engagement_hook_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "treatment_signature_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "local_intent_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_local_intent_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["local_intent_required"] is True
    assert report["next_run_playbook"]["fresh_local_intent_required"] is True
    assert report["next_run_playbook"]["local_intent_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["local_intent_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_local_intent_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "local_intent_gaps"
        for item in report["recommendations"]
    )


def test_local_area_diversity_flags_single_area_dependency(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "청주")
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            terms = " ".join(ENGAGEMENT_HOOK_LENS_TERMS[lens][:2])
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-single-local-area-{idx}-{copy_idx}",
                    scan_id=148,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"{primary_region} patient local area dependency {idx}-{copy_idx}",
                    title=f"{primary_region} {category} {terms} patient question {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{primary_region} {category} {lens} single local area seed {idx}-{copy_idx}"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=148,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    local_quality = report["local_intent_quality"]
    area_quality = report["local_area_diversity_quality"]
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert local_quality["overall"]["fresh_category_lens_local_ready_rate"] == 1.0
    assert area_quality["overall"]["category_lens_local_area_diversity_ready_rate"] == 0.0
    assert area_quality["overall"]["fresh_category_lens_local_area_diversity_ready_rate"] == 0.0
    first_gap = next(item for item in area_quality["priority_gaps"] if item["lane"] == expected_lane)
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["local_area_actionable_strict"] == 2
    assert first_gap["local_area_count"] == 1
    assert first_gap["min_local_areas"] == 2
    assert "single_local_area_dependency" in first_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "local_intent_lens_coverage" not in failed
    assert "local_area_diversity_lens_coverage" in failed
    assert "fresh_local_area_diversity_lens_coverage" in failed
    assert report["next_run_playbook"]["local_area_diversity_required"] is True
    assert report["next_run_playbook"]["fresh_local_area_diversity_required"] is True
    assert any(
        item["lane"] == expected_lane
        for item in report["next_run_playbook"]["local_area_diversity_gaps"]
    )
    assert any(
        item["code"] == "local_area_diversity_gaps"
        for item in report["recommendations"]
    )


def test_patient_surface_quality_flags_provider_promo_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "청주")
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            terms = " ".join(ENGAGEMENT_HOOK_LENS_TERMS[lens][:2])
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-provider-surface-{idx}-{copy_idx}",
                    scan_id=93,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"provider promo surface {idx}-{copy_idx}",
                    title=(
                        f"{primary_region} {category} {terms} "
                        f"의료진소개 진료시간 오시는길 {idx}-{copy_idx}"
                    ),
                    breakdown={
                        "pathfinder_source_keyword": f"seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=93,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    local_quality = report["local_intent_quality"]
    patient_surface = report["patient_surface_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert patient_surface["overall"]["category_lens_patient_surface_ready_rate"] == 0.0
    assert patient_surface["overall"]["fresh_category_lens_patient_surface_ready_rate"] == 0.0
    first_gap = patient_surface["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["patient_surface_actionable_strict"] == 0
    assert first_gap["provider_surface_noise"] == 2
    assert first_gap["patient_surface_missing"] == 2
    assert "no_patient_surface" in first_gap["reasons"]
    assert "provider_surface_noise" in first_gap["reasons"]
    assert "unique_work_queue_lens_depth" not in report["quality_bar"]["failed_advisory_gates"]
    assert "opportunity_diversity_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "engagement_hook_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "treatment_signature_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "local_intent_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "patient_surface_authenticity_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_patient_surface_authenticity_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["patient_surface_required"] is True
    assert report["next_run_playbook"]["fresh_patient_surface_required"] is True
    assert report["next_run_playbook"]["patient_surface_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["patient_surface_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_patient_surface_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "patient_surface_authenticity_gaps"
        for item in report["recommendations"]
    )


def test_viral_action_route_quality_flags_generic_patient_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "청주")
    idx = 1
    for category in _priority_focus_categories():
        for lens in ("review", "community", "cost", "consultation", "availability", "safety"):
            for copy_idx, platform in enumerate(("kin", "cafe")):
                variant = (
                    f"axis_generic:specific_lane_{idx}"
                    if copy_idx == 0
                    else f"colloquial:lane_{idx}"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-no-route-{idx}-{copy_idx}",
                    scan_id=94,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"generic patient surface without route {idx}-{copy_idx}",
                    title=f"{primary_region} {category} 궁금해요 알려주세요? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": variant,
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=94,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    local_quality = report["local_intent_quality"]
    patient_surface = report["patient_surface_quality"]
    action_route = report["viral_action_route_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert patient_surface["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert action_route["overall"]["category_lens_route_ready_rate"] == 0.0
    assert action_route["overall"]["fresh_category_lens_route_ready_rate"] == 0.0
    first_gap = action_route["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["routed_actionable_strict"] == 0
    assert first_gap["viral_action_route_missing"] == 2
    assert "no_viral_action_route" in first_gap["reasons"]
    assert "missing_viral_action_route" in first_gap["reasons"]
    assert "patient_surface_authenticity_lens_coverage" not in report["quality_bar"]["failed_advisory_gates"]
    assert "viral_action_route_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "fresh_viral_action_route_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["viral_action_route_required"] is True
    assert report["next_run_playbook"]["fresh_viral_action_route_required"] is True
    assert report["next_run_playbook"]["viral_action_route_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["viral_action_route_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_viral_action_route_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "viral_action_route_gaps"
        for item in report["recommendations"]
    )


def test_viral_action_route_bridges_community_entry_to_conversion_lens(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="cost-community-bridge",
        scan_id=152,
        category="다이어트",
        grade="A",
        status="pending",
        priority=150,
        title="청주 다이어트한약 체중감량하려구요",
        content_preview="청주쪽으로 다이어트한약 찾아보고 있습니다. 괜찮은곳 추천해주세요",
        breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "cost_community:추천",
            "pathfinder_source_keyword": "청주 다이어트 한약 비용",
            "pathfinder_axis_fit_score": 95,
            "pathfinder_lens_fit_score": 70,
            "clinic_treatment_fit_score": 95,
            "worksite_efficiency_score": 95,
        },
    )
    _insert_target(
        conn,
        target_id="consultation-community-bridge",
        scan_id=152,
        category="교통사고",
        grade="A",
        status="pending",
        priority=150,
        title="교통사고입원실 있는 한의원 추천해주세요",
        content_preview="사창동 근처 교통사고 잘해주시는 한의원 추천주세요",
        breakdown={
            "pathfinder_execution_lens": "consultation",
            "pathfinder_query_variant": "community_base",
            "pathfinder_source_keyword": "사창동 교통사고 한의원 상담 가능한곳",
            "pathfinder_axis_fit_score": 95,
            "pathfinder_lens_fit_score": 70,
            "clinic_treatment_fit_score": 95,
            "worksite_efficiency_score": 95,
        },
    )
    _insert_target(
        conn,
        target_id="cost-generic-question",
        scan_id=152,
        category="다이어트",
        grade="A",
        status="pending",
        priority=150,
        title="청주 다이어트 궁금해요 알려주세요?",
        content_preview="generic patient surface without concrete route",
        breakdown={
            "pathfinder_execution_lens": "cost",
            "pathfinder_query_variant": "community_base",
            "pathfinder_source_keyword": "청주 다이어트 한약 비용",
            "pathfinder_axis_fit_score": 95,
            "pathfinder_lens_fit_score": 70,
            "clinic_treatment_fit_score": 95,
            "worksite_efficiency_score": 95,
        },
    )
    conn.commit()
    conn.close()

    read_conn = sqlite3.connect(db_path)
    read_conn.row_factory = sqlite3.Row
    rows = {
        row["id"]: row
        for row in read_conn.execute(
            "SELECT * FROM viral_targets WHERE source_scan_run_id = 152"
        )
    }
    read_conn.close()

    cost_route = _viral_action_route_evidence(rows["cost-community-bridge"], "cost")
    assert cost_route["matched"] is True
    assert cost_route["route_bridge"] is True
    assert cost_route["route"] == "recommendation_request"
    assert cost_route["route_mismatch"] is False

    consultation_route = _viral_action_route_evidence(
        rows["consultation-community-bridge"],
        "consultation",
    )
    assert consultation_route["matched"] is True
    assert consultation_route["route_bridge"] is True
    assert consultation_route["route"] == "recommendation_request"
    assert consultation_route["route_mismatch"] is False

    generic_route = _viral_action_route_evidence(rows["cost-generic-question"], "cost")
    assert generic_route["matched"] is False
    assert generic_route["route_bridge"] is False
    assert generic_route["route_mismatch"] is False


def test_treatment_signal_diversity_flags_single_term_collapse(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    route_terms = {}
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        terms = tuple(definition.get("terms") or ())
        if not terms:
            continue
        for lens_name in tuple(definition.get("lenses") or ()):
            route_terms.setdefault(lens_name, terms[0])
    journey_terms = {
        lens_name: route_terms[lens_name]
        for lens_name in ("review", "community", "cost", "consultation", "availability", "safety")
    }
    idx = 1
    for category in _priority_focus_categories():
        signature_term = _signature_terms_for(category, count=1)[0]
        for lens, route_term in journey_terms.items():
            for copy_idx, platform in enumerate(("kin", "cafe")):
                _insert_target(
                    conn,
                    target_id=f"queue-narrow-signal-{idx}-{copy_idx}",
                    scan_id=96,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"single signal copy {idx}-{copy_idx}",
                    title=f"{primary_region} {signature_term} {route_term} question recommend ? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"narrow-signal-seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_signal:specific_{idx}"
                            if copy_idx == 0
                            else f"colloquial:narrow_signal_{idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=96,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    signal_diversity = report["treatment_signal_diversity_quality"]
    local_quality = report["local_intent_quality"]
    patient_surface = report["patient_surface_quality"]
    action_route = report["viral_action_route_quality"]
    reply_workability = report["reply_workability_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert patient_surface["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert action_route["overall"]["category_lens_route_ready_rate"] == 1.0
    assert reply_workability["overall"]["category_lens_reply_workable_ready_rate"] == 1.0
    assert signal_diversity["overall"]["category_lens_treatment_signal_diverse_ready_rate"] < 0.35
    assert signal_diversity["overall"]["fresh_category_lens_treatment_signal_diverse_ready_rate"] < 0.30
    first_gap = signal_diversity["priority_gaps"][0]
    assert first_gap["lane"] == focus_category
    first_lens_gap = signal_diversity["category_lens_gaps"][0]
    assert first_lens_gap["category"] in _priority_focus_categories()
    assert first_lens_gap["lens"] in journey_terms
    assert first_gap["unique_actionable_strict"] == len(journey_terms) * 2
    assert first_gap["treatment_signal_actionable_strict"] == len(journey_terms) * 2
    assert first_lens_gap["unique_actionable_strict"] == 2
    assert first_lens_gap["treatment_signal_actionable_strict"] == 2
    assert first_gap["min_distinct_treatment_signal_terms"] == 4
    assert (
        first_gap["distinct_treatment_signal_terms"]
        < first_gap["min_distinct_treatment_signal_terms"]
    )
    assert first_lens_gap["distinct_treatment_signal_terms"] == 1
    assert first_lens_gap["min_distinct_treatment_signal_terms"] == 2
    assert "narrow_treatment_signal_diversity" in first_gap["reasons"]
    assert "narrow_treatment_signal_diversity" in first_lens_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "treatment_signature_lens_coverage" not in failed
    assert "treatment_signal_diversity_lens_coverage" in failed
    assert "fresh_treatment_signal_diversity_lens_coverage" in failed
    assert report["next_run_playbook"]["treatment_signal_diversity_required"] is True
    assert report["next_run_playbook"]["fresh_treatment_signal_diversity_required"] is True
    assert report["next_run_playbook"]["treatment_signal_diversity_gaps"][0]["lane"] == focus_category
    assert report["review_samples"]["treatment_signal_diversity_gap_samples"][0]["lane"] == focus_category
    assert report["review_samples"]["fresh_treatment_signal_diversity_gap_samples"][0]["lane"] == focus_category
    assert any(
        item["code"] == "treatment_signal_diversity_gaps"
        for item in report["recommendations"]
    )


def test_treatment_subintent_diversity_flags_single_subintent_collapse(tmp_path):
    db_path, conn = _make_db(tmp_path)
    route_terms = {
        "review": "추천",
        "community": "추천",
        "cost": "비용",
        "consultation": "상담",
        "availability": "예약",
        "safety": "회복 안전",
    }
    local_areas = ("청주", "흥덕구", "오창")
    idx = 1
    chosen_bucket_by_category = {}
    for category in _priority_focus_categories():
        bucket, signature_terms = _single_subintent_signature_terms_for(category, count=4)
        chosen_bucket_by_category[category] = bucket
        for lens_idx, (lens, route_term) in enumerate(route_terms.items()):
            for copy_idx, platform in enumerate(("kin", "cafe")):
                signature_term = signature_terms[
                    (lens_idx * 2 + copy_idx) % len(signature_terms)
                ]
                local_area = local_areas[(lens_idx + copy_idx) % len(local_areas)]
                target_text = (
                    f"{local_area} {signature_term} {route_term} 궁금 추천 "
                    f"어디 상담 가능 ?"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-single-subintent-{idx}-{copy_idx}",
                    scan_id=151,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"{target_text} patient question {idx}-{copy_idx}",
                    title=f"{target_text} {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{local_area} {signature_term} {route_term} 궁금 추천"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_subintent:single_bucket_{idx}"
                            if copy_idx == 0
                            else f"colloquial:single_subintent_{idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=151,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    assert report["work_queue_readiness"]["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert report["opportunity_diversity"]["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert report["engagement_hook_quality"]["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert report["treatment_signature_quality"]["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert (
        report["treatment_signal_diversity_quality"]["overall"][
            "category_lens_treatment_signal_diverse_ready_rate"
        ]
        == 1.0
    )
    assert report["clinic_modality_quality"]["overall"]["category_lens_clinic_modality_fit_ready_rate"] == 1.0
    assert report["decision_window_quality"]["overall"]["category_lens_active_decision_ready_rate"] == 1.0
    assert report["local_intent_quality"]["overall"]["category_lens_local_ready_rate"] == 1.0
    assert report["local_area_diversity_quality"]["overall"]["category_lens_local_area_diversity_ready_rate"] == 1.0
    assert report["patient_surface_quality"]["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert report["viral_action_route_quality"]["overall"]["category_lens_route_ready_rate"] == 1.0
    assert report["reply_workability_quality"]["overall"]["category_lens_reply_workable_ready_rate"] == 1.0
    subintent = report["treatment_subintent_diversity_quality"]
    assert subintent["overall"]["category_lens_treatment_subintent_diverse_ready_rate"] == 0.0
    assert subintent["overall"]["fresh_category_lens_treatment_subintent_diverse_ready_rate"] == 0.0
    category_gap = next(
        item for item in subintent["priority_gaps"]
        if item["lane"] == focus_category
    )
    lens_gap = next(
        item for item in subintent["category_lens_gaps"]
        if item["lane"] == expected_lane
    )
    assert category_gap["unique_actionable_strict"] == len(route_terms) * 2
    assert category_gap["treatment_subintent_actionable_strict"] == len(route_terms) * 2
    assert category_gap["distinct_treatment_subintent_buckets"] == 1
    assert category_gap["min_distinct_treatment_subintent_buckets"] == 3
    assert category_gap["treatment_subintent_buckets"] == [chosen_bucket_by_category[focus_category]]
    assert lens_gap["unique_actionable_strict"] == 2
    assert lens_gap["treatment_subintent_actionable_strict"] == 2
    assert lens_gap["distinct_treatment_subintent_buckets"] == 1
    assert lens_gap["min_distinct_treatment_subintent_buckets"] == 2
    assert "narrow_treatment_subintent_diversity" in category_gap["reasons"]
    assert "narrow_treatment_subintent_diversity" in lens_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "treatment_signal_diversity_lens_coverage" not in failed
    assert "treatment_subintent_diversity_lens_coverage" in failed
    assert "fresh_treatment_subintent_diversity_lens_coverage" in failed
    assert report["next_run_playbook"]["treatment_subintent_diversity_required"] is True
    assert report["next_run_playbook"]["fresh_treatment_subintent_diversity_required"] is True
    assert report["next_run_playbook"]["treatment_subintent_diversity_gaps"][0]["lane"] == focus_category
    assert report["review_samples"]["treatment_subintent_diversity_gap_samples"][0]["lane"] == focus_category
    assert (
        report["review_samples"]["fresh_treatment_subintent_diversity_gap_samples"][0]["lane"]
        == focus_category
    )
    assert any(
        item["code"] == "treatment_subintent_diversity_gaps"
        for item in report["recommendations"]
    )


def test_clinic_modality_quality_flags_offscope_modality_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    route_terms = {
        "review": "추천",
        "community": "추천",
        "cost": "비용",
        "consultation": "상담",
        "availability": "예약",
        "safety": "회복 안전",
    }
    local_areas = ("청주", "흥덕구", "오창")
    idx = 1
    for category in _priority_focus_categories():
        signature_terms = _non_modality_signature_terms_for(category, count=12)
        for lens_idx, (lens, route_term) in enumerate(route_terms.items()):
            for copy_idx, platform in enumerate(("kin", "cafe")):
                signature_term = signature_terms[
                    (lens_idx * 2 + copy_idx) % len(signature_terms)
                ]
                local_area = local_areas[(lens_idx + copy_idx) % len(local_areas)]
                target_text = (
                    f"{local_area} {signature_term} {route_term} 궁금 추천 "
                    f"피부과 레이저 위고비 마운자로 성형외과 양악 윤곽수술 ?"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-offscope-modality-{idx}-{copy_idx}",
                    scan_id=149,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"{target_text} patient question {idx}-{copy_idx}",
                    title=f"{target_text} {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{local_area} {signature_term} {route_term} "
                            f"피부과 레이저 위고비"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_generic:offscope_modality_{idx}"
                            if copy_idx == 0
                            else f"colloquial:offscope_modality_{idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=149,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    signal_diversity = report["treatment_signal_diversity_quality"]
    local_quality = report["local_intent_quality"]
    area_quality = report["local_area_diversity_quality"]
    patient_surface = report["patient_surface_quality"]
    action_route = report["viral_action_route_quality"]
    reply_workability = report["reply_workability_quality"]
    clinic_modality = report["clinic_modality_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert signal_diversity["overall"]["category_lens_treatment_signal_diverse_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert area_quality["overall"]["category_lens_local_area_diversity_ready_rate"] == 1.0
    assert patient_surface["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert action_route["overall"]["category_lens_route_ready_rate"] == 1.0
    assert reply_workability["overall"]["category_lens_reply_workable_ready_rate"] == 1.0
    assert clinic_modality["overall"]["category_lens_clinic_modality_fit_ready_rate"] == 0.0
    assert clinic_modality["overall"]["fresh_category_lens_clinic_modality_fit_ready_rate"] == 0.0
    first_gap = next(
        item for item in clinic_modality["priority_gaps"]
        if item["lane"] == expected_lane
    )
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["clinic_modality_fit_actionable_strict"] == 0
    assert first_gap["offscope_modality_noise"] == 2
    assert "offscope_modality_noise" in first_gap["reasons"]
    assert {"피부과", "레이저", "위고비"}.issubset(
        set(first_gap["clinic_modality_offscope_terms"])
    )
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "clinic_modality_lens_coverage" in failed
    assert "fresh_clinic_modality_lens_coverage" in failed
    assert report["next_run_playbook"]["clinic_modality_required"] is True
    assert report["next_run_playbook"]["fresh_clinic_modality_required"] is True
    assert any(
        item["lane"] == expected_lane
        for item in report["next_run_playbook"]["clinic_modality_gaps"]
    )
    assert any(
        item["code"] == "clinic_modality_fit_gaps"
        for item in report["recommendations"]
    )
    assert any(
        sample.get("clinic_modality_offscope_terms")
        for sample in report["review_samples"]["top_strict_fit"]
    )


def test_decision_window_quality_flags_completed_or_booked_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    route_terms = {
        "review": "추천",
        "community": "추천",
        "cost": "비용",
        "consultation": "상담",
        "availability": "예약",
        "safety": "회복 안전",
    }
    local_areas = ("청주", "흥덕구", "오창")
    idx = 1
    for category in _priority_focus_categories():
        signature_terms = _non_modality_signature_terms_for(category, count=12)
        for lens_idx, (lens, route_term) in enumerate(route_terms.items()):
            for copy_idx, platform in enumerate(("kin", "cafe")):
                signature_term = signature_terms[
                    (lens_idx * 2 + copy_idx) % len(signature_terms)
                ]
                local_area = local_areas[(lens_idx + copy_idx) % len(local_areas)]
                target_text = (
                    f"{local_area} {signature_term} {route_term} "
                    f"예약완료 다녀왔습니다 받았습니다"
                )
                _insert_target(
                    conn,
                    target_id=f"queue-completed-window-{idx}-{copy_idx}",
                    scan_id=150,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"{target_text} patient surface {idx}-{copy_idx}",
                    title=f"{target_text} {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{local_area} {signature_term} {route_term} 예약완료"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_generic:completed_window_{idx}"
                            if copy_idx == 0
                            else f"colloquial:completed_window_{idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=150,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    assert report["work_queue_readiness"]["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert report["opportunity_diversity"]["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert report["engagement_hook_quality"]["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert report["treatment_signature_quality"]["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert (
        report["treatment_signal_diversity_quality"]["overall"][
            "category_lens_treatment_signal_diverse_ready_rate"
        ]
        == 1.0
    )
    assert report["clinic_modality_quality"]["overall"]["category_lens_clinic_modality_fit_ready_rate"] == 1.0
    assert report["local_intent_quality"]["overall"]["category_lens_local_ready_rate"] == 1.0
    assert report["local_area_diversity_quality"]["overall"]["category_lens_local_area_diversity_ready_rate"] == 1.0
    assert report["patient_surface_quality"]["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert report["viral_action_route_quality"]["overall"]["category_lens_route_ready_rate"] == 1.0
    assert report["reply_workability_quality"]["overall"]["category_lens_reply_workable_ready_rate"] == 1.0
    assert report["execution_readiness_quality"]["overall"]["category_lens_execution_ready_rate"] == 1.0
    decision_window = report["decision_window_quality"]
    assert decision_window["overall"]["category_lens_active_decision_ready_rate"] == 0.0
    assert decision_window["overall"]["fresh_category_lens_active_decision_ready_rate"] == 0.0
    first_gap = next(
        item for item in decision_window["priority_gaps"]
        if item["lane"] == expected_lane
    )
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["active_decision_actionable_strict"] == 0
    assert first_gap["completed_decision_window_noise"] == 2
    assert "completed_decision_window_noise" in first_gap["reasons"]
    assert "already_committed_booking_noise" in first_gap["reasons"]
    assert "예약완료" in first_gap["decision_window_completed_terms"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "execution_readiness_lens_coverage" not in failed
    assert "decision_window_lens_coverage" in failed
    assert "fresh_decision_window_lens_coverage" in failed
    assert report["next_run_playbook"]["decision_window_required"] is True
    assert report["next_run_playbook"]["fresh_decision_window_required"] is True
    assert any(
        item["lane"] == expected_lane
        for item in report["next_run_playbook"]["decision_window_gaps"]
    )
    assert any(
        item["code"] == "decision_window_gaps"
        for item in report["recommendations"]
    )
    assert any(
        sample.get("decision_window_completed_terms")
        for sample in report["review_samples"]["top_strict_fit"]
    )


def test_reply_workability_quality_flags_risky_or_low_opportunity_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    route_terms = {}
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        terms = tuple(definition.get("terms") or ())
        if not terms:
            continue
        for lens_name in tuple(definition.get("lenses") or ()):
            route_terms.setdefault(lens_name, terms[0])
    journey_terms = {
        lens_name: route_terms[lens_name]
        for lens_name in ("review", "community", "cost", "consultation", "availability", "safety")
    }
    idx = 1
    for category in _priority_focus_categories():
        for lens, terms in journey_terms.items():
            for copy_idx, platform in enumerate(("kin", "cafe")):
                risky = copy_idx == 1
                _insert_target(
                    conn,
                    target_id=f"queue-reply-blocked-{idx}-{copy_idx}",
                    scan_id=95,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=platform,
                    content_preview=f"reply workability blocked copy {idx}-{copy_idx}",
                    title=f"{primary_region} {category} {terms} 沅곴툑?댁슂 ?뚮젮二쇱꽭?? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"reply-seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_reply:specific_{idx}"
                            if copy_idx == 0
                            else f"colloquial:reply_workability_{idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": 82 if risky else 20,
                        "reply_opportunity_tier": "assist_now" if risky else "low",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                            if risky
                            else ""
                        ),
                        "reply_risk_penalty": -60 if risky else 0,
                        "reply_risk_flags": "urgent_medical" if risky else "",
                        "manual_review": 1 if risky else 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=95,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    queue = report["work_queue_readiness"]
    diversity = report["opportunity_diversity"]
    hook_quality = report["engagement_hook_quality"]
    signature_quality = report["treatment_signature_quality"]
    local_quality = report["local_intent_quality"]
    patient_surface = report["patient_surface_quality"]
    action_route = report["viral_action_route_quality"]
    reply_workability = report["reply_workability_quality"]
    assert queue["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert diversity["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert hook_quality["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert signature_quality["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert local_quality["overall"]["category_lens_local_ready_rate"] == 1.0
    assert patient_surface["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert action_route["overall"]["category_lens_route_ready_rate"] == 1.0
    assert reply_workability["overall"]["category_lens_reply_workable_ready_rate"] == 0.0
    assert reply_workability["overall"]["fresh_category_lens_reply_workable_ready_rate"] == 0.0
    first_gap = reply_workability["priority_gaps"][0]
    assert first_gap["lane"] == expected_lane
    assert first_gap["unique_actionable_strict"] == 2
    assert first_gap["reply_workable_actionable_strict"] == 0
    assert first_gap["reply_workability_missing"] == 2
    assert first_gap["reply_risk_flagged"] == 1
    assert first_gap["reply_metric_missing"] == 0
    assert "no_reply_workable_surface" in first_gap["reasons"]
    assert "missing_reply_workability" in first_gap["reasons"]
    assert "reply_risk_flags" in first_gap["reasons"]
    assert "low_reply_opportunity_score" in first_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "viral_action_route_lens_coverage" not in failed
    assert "reply_workability_lens_coverage" in failed
    assert "fresh_reply_workability_lens_coverage" in failed
    assert report["next_run_playbook"]["reply_workability_required"] is True
    assert report["next_run_playbook"]["fresh_reply_workability_required"] is True
    assert report["next_run_playbook"]["reply_workability_gaps"][0]["lane"] == expected_lane
    assert report["review_samples"]["reply_workability_gap_samples"][0]["lane"] == expected_lane
    assert report["review_samples"]["fresh_reply_workability_gap_samples"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "reply_workability_gaps"
        for item in report["recommendations"]
    )


def test_reply_workability_derives_content_risk_flags_when_ai_flags_missing(tmp_path):
    db_path, conn = _make_db(tmp_path)
    category = _priority_focus_categories()[0]
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    signature_terms = _signature_terms_for(category, count=1)
    signature_term = signature_terms[0] if signature_terms else category
    route_term = ""
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        if "review" in tuple(definition.get("lenses") or ()):
            route_terms = tuple(definition.get("terms") or ())
            if route_terms:
                route_term = str(route_terms[0])
                break
    rows = (
        ("urgent", "emergency urgent pain question"),
        ("pregnant-medicine", "pregnant medication prescription dosage question"),
    )
    for idx, (suffix, risk_text) in enumerate(rows, start=1):
        _insert_target(
            conn,
            target_id=f"content-risk-{suffix}",
            scan_id=197,
            category=category,
            grade="A",
            status="pending",
            priority=150 - idx,
            platform="kin" if idx == 1 else "cafe",
            title=f"{primary_region} {signature_term} {route_term} {risk_text} ?",
            content_preview=f"patient asks local review but includes {risk_text}",
            breakdown={
                "pathfinder_source_keyword": f"content-risk-seed-{idx}",
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": f"axis_content_risk:specific_{idx}",
                "pathfinder_axis_fit_score": 92,
                "pathfinder_lens_fit_score": 90,
                "clinic_treatment_fit_score": 91,
                "worksite_efficiency_score": 88,
                "reply_opportunity_score": 86,
                "reply_opportunity_tier": "assist_now",
                "reply_opportunity_signals": (
                    "public_reply_surface,help_request_language,decision_or_service_task,"
                    "local_actionable,unanswered_or_low_response"
                ),
                "reply_risk_penalty": 0,
                "reply_risk_flags": "",
                "manual_review": 0,
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=197,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    expected_lane = f"{category}::review"
    reply = report["reply_workability_quality"]
    reply_gap = next(item for item in reply["category_lens_gaps"] if item["lane"] == expected_lane)
    assert reply_gap["unique_actionable_strict"] == 2
    assert reply_gap["reply_workable_actionable_strict"] == 0
    assert reply_gap["reply_risk_flagged"] == 2
    assert "reply_risk_flags" in reply_gap["reasons"]

    compliance = report["compliance_work_mode_quality"]
    compliance_gap = next(
        item for item in compliance["category_lens_gaps"] if item["lane"] == expected_lane
    )
    assert compliance_gap["auto_work_ready_actionable_strict"] == 0
    assert compliance_gap["blocked_or_escalate_actionable_strict"] == 2
    assert "urgent_medical" in compliance_gap["reply_risk_flags"]
    assert "medication_advice_request" in compliance_gap["reply_risk_flags"]
    assert "reply_workability_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert "compliance_work_mode_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["reply_workability_required"] is True
    assert report["next_run_playbook"]["compliance_work_mode_required"] is True
    sample = report["review_samples"]["top_strict_fit"][0]
    assert sample["content_risk_flags"]
    assert sample["content_risk_terms"]


def test_compliance_work_mode_splits_auto_review_and_blocked_inventory(tmp_path):
    db_path, conn = _make_db(tmp_path)
    category = _priority_focus_categories()[0]
    rows = (
        {
            "suffix": "safe",
            "risk_flags": "",
            "risk_penalty": 0,
            "manual_review": 0,
        },
        {
            "suffix": "manual",
            "risk_flags": "testimonial_sensitive",
            "risk_penalty": -10,
            "manual_review": 1,
        },
        {
            "suffix": "blocked",
            "risk_flags": "urgent_medical",
            "risk_penalty": -60,
            "manual_review": 1,
        },
    )
    for idx, row in enumerate(rows, start=1):
        _insert_target(
            conn,
            target_id=f"compliance-mode-{row['suffix']}",
            scan_id=196,
            category=category,
            grade="A",
            status="pending",
            priority=150 - idx,
            platform="kin",
            title=f"Cheongju {category} review consultation question {idx}",
            content_preview="patient asks for local consultation and recommendation",
            breakdown={
                "pathfinder_source_keyword": f"compliance-mode-seed-{idx}",
                "pathfinder_execution_lens": "review",
                "pathfinder_query_variant": f"axis_compliance:specific_{idx}",
                "pathfinder_axis_fit_score": 92,
                "pathfinder_lens_fit_score": 90,
                "clinic_treatment_fit_score": 91,
                "worksite_efficiency_score": 88,
                "reply_opportunity_score": 82,
                "reply_opportunity_tier": "assist_now",
                "reply_opportunity_signals": (
                    "public_reply_surface,help_request_language,decision_or_service_task,"
                    "local_actionable,unanswered_or_low_response"
                ),
                "reply_risk_penalty": row["risk_penalty"],
                "reply_risk_flags": row["risk_flags"],
                "manual_review": row["manual_review"],
            },
        )
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=196,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    expected_lane = f"{category}::review"
    compliance = report["compliance_work_mode_quality"]
    lens_gap = next(item for item in compliance["category_lens_gaps"] if item["lane"] == expected_lane)
    assert lens_gap["unique_actionable_strict"] == 3
    assert lens_gap["auto_work_ready_actionable_strict"] == 1
    assert lens_gap["manual_review_only_actionable_strict"] == 1
    assert lens_gap["blocked_or_escalate_actionable_strict"] == 1
    assert "testimonial_sensitive" in lens_gap["reply_risk_flags"]
    assert "urgent_medical" in lens_gap["reply_risk_flags"]
    assert "thin_auto_work_ready_inventory" in lens_gap["reasons"]
    assert "manual_review_only_inventory" in lens_gap["reasons"]
    assert "blocked_or_escalate_inventory" in lens_gap["reasons"]

    assert report["quality_bar"]["compliance_work_mode"]["work_mode_counts"]["auto_work_ready"] == 1
    assert report["quality_bar"]["compliance_work_mode"]["work_mode_counts"]["manual_review_only"] == 1
    assert report["quality_bar"]["compliance_work_mode"]["work_mode_counts"]["blocked_or_escalate"] == 1
    assert "compliance_work_mode_lens_coverage" in report["quality_bar"]["failed_advisory_gates"]
    assert report["next_run_playbook"]["compliance_work_mode_required"] is True
    assert report["next_run_playbook"]["compliance_work_mode_gaps"][0]["lane"] == expected_lane
    assert any(
        item["code"] == "compliance_work_mode_gaps"
        for item in report["recommendations"]
    )


def test_execution_readiness_flags_fragmented_component_signals(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    route_terms = {}
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        terms = tuple(definition.get("terms") or ())
        if not terms:
            continue
        for lens_name in tuple(definition.get("lenses") or ()):
            route_terms.setdefault(lens_name, terms[0])
    journey_terms = {
        lens_name: route_terms[lens_name]
        for lens_name in ("review", "community", "cost", "consultation", "availability", "safety")
    }
    idx = 1
    for category in _priority_focus_categories():
        signature_terms = _signature_terms_for(category, count=2)
        if len(signature_terms) == 1:
            signature_terms = [signature_terms[0], signature_terms[0]]
        for lens, route_term in journey_terms.items():
            rows = (
                {
                    "suffix": "missing-reply",
                    "title_terms": f"{signature_terms[0]} {route_term}",
                    "reply_score": 20,
                    "reply_tier": "low",
                    "reply_signals": "",
                    "variant": f"axis_exec:specific_{idx}",
                    "platform": "kin",
                },
                {
                    "suffix": "missing-route",
                    "title_terms": signature_terms[1],
                    "reply_score": 82,
                    "reply_tier": "assist_now",
                    "reply_signals": (
                        "public_reply_surface,help_request_language,decision_or_service_task,"
                        "local_actionable,unanswered_or_low_response"
                    ),
                    "variant": f"colloquial:exec_{idx}",
                    "platform": "cafe",
                },
                {
                    "suffix": "missing-signature",
                    "title_terms": route_term,
                    "reply_score": 82,
                    "reply_tier": "assist_now",
                    "reply_signals": (
                        "public_reply_surface,help_request_language,decision_or_service_task,"
                        "local_actionable,unanswered_or_low_response"
                    ),
                    "variant": "patient_voice_question_kin",
                    "platform": "blog",
                },
            )
            for copy_idx, row in enumerate(rows):
                _insert_target(
                    conn,
                    target_id=f"queue-exec-fragmented-{idx}-{copy_idx}",
                    scan_id=97,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140,
                    platform=row["platform"],
                    content_preview=f"execution fragmented copy {idx}-{copy_idx}",
                    title=f"{primary_region} {row['title_terms']} ? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"exec-fragmented-seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": row["variant"],
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": row["reply_score"],
                        "reply_opportunity_tier": row["reply_tier"],
                        "reply_opportunity_signals": row["reply_signals"],
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=97,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    assert report["work_queue_readiness"]["overall"]["unique_category_lens_ready_rate"] == 1.0
    assert report["opportunity_diversity"]["overall"]["category_lens_diversity_ready_rate"] == 1.0
    assert report["engagement_hook_quality"]["overall"]["category_lens_hook_ready_rate"] == 1.0
    assert report["treatment_signature_quality"]["overall"]["category_lens_signature_ready_rate"] == 1.0
    assert (
        report["treatment_signal_diversity_quality"]["overall"][
            "category_lens_treatment_signal_diverse_ready_rate"
        ]
        == 1.0
    )
    assert report["local_intent_quality"]["overall"]["category_lens_local_ready_rate"] == 1.0
    assert report["patient_surface_quality"]["overall"]["category_lens_patient_surface_ready_rate"] == 1.0
    assert report["viral_action_route_quality"]["overall"]["category_lens_route_ready_rate"] == 1.0
    assert report["reply_workability_quality"]["overall"]["category_lens_reply_workable_ready_rate"] == 1.0
    execution = report["execution_readiness_quality"]
    assert execution["overall"]["category_lens_execution_ready_rate"] == 0.0
    assert execution["overall"]["fresh_category_lens_execution_ready_rate"] == 0.0
    lens_gap = next(item for item in execution["category_lens_gaps"] if item["lane"] == expected_lane)
    assert lens_gap["unique_actionable_strict"] == 3
    assert lens_gap["execution_ready_actionable_strict"] == 0
    assert lens_gap["execution_readiness_missing"] == 3
    assert lens_gap["fragmented_execution_signals"] is True
    for component in (
        "engagement_hook",
        "treatment_signature",
        "local_intent",
        "patient_surface",
        "viral_action_route",
        "reply_workability",
    ):
        assert lens_gap["execution_readiness_component_counts"][component] >= 2
    assert "fragmented_execution_signals" in lens_gap["reasons"]
    assert "missing_treatment_signature" in lens_gap["reasons"]
    assert "missing_viral_action_route" in lens_gap["reasons"]
    assert "missing_reply_workability" in lens_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "reply_workability_lens_coverage" not in failed
    assert "execution_readiness_lens_coverage" in failed
    assert "fresh_execution_readiness_lens_coverage" in failed
    assert report["next_run_playbook"]["execution_readiness_required"] is True
    assert report["next_run_playbook"]["fresh_execution_readiness_required"] is True
    assert any(item["lane"] == expected_lane for item in report["next_run_playbook"]["execution_readiness_gaps"])
    assert any(item["lane"] == expected_lane for item in report["review_samples"]["execution_readiness_gap_samples"])
    assert any(
        item["code"] == "execution_readiness_gaps"
        for item in report["recommendations"]
    )


def test_execution_priority_alignment_flags_buried_ready_targets(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    route_terms = {}
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        terms = tuple(definition.get("terms") or ())
        if not terms:
            continue
        for lens_name in tuple(definition.get("lenses") or ()):
            route_terms.setdefault(lens_name, terms[0])
    journey_terms = {
        lens_name: route_terms[lens_name]
        for lens_name in ("review", "community", "cost", "consultation", "availability", "safety")
    }
    idx = 1
    for category in _priority_focus_categories():
        signature_terms = _signature_terms_for(category, count=2)
        if len(signature_terms) == 1:
            signature_terms = [signature_terms[0], signature_terms[0]]
        for lens, route_term in journey_terms.items():
            rows = (
                {"priority": 160, "reply_score": 20, "reply_tier": "low", "reply_signals": "", "platform": "kin"},
                {"priority": 159, "reply_score": 20, "reply_tier": "low", "reply_signals": "", "platform": "cafe"},
                {
                    "priority": 80,
                    "reply_score": 82,
                    "reply_tier": "assist_now",
                    "reply_signals": (
                        "public_reply_surface,help_request_language,decision_or_service_task,"
                        "local_actionable,unanswered_or_low_response"
                    ),
                    "platform": "blog",
                },
                {
                    "priority": 79,
                    "reply_score": 82,
                    "reply_tier": "assist_now",
                    "reply_signals": (
                        "public_reply_surface,help_request_language,decision_or_service_task,"
                        "local_actionable,unanswered_or_low_response"
                    ),
                    "platform": "naver_kin",
                },
            )
            for copy_idx, row in enumerate(rows):
                signature_term = signature_terms[copy_idx % len(signature_terms)]
                _insert_target(
                    conn,
                    target_id=f"queue-exec-priority-buried-{idx}-{copy_idx}",
                    scan_id=98,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=row["priority"],
                    platform=row["platform"],
                    content_preview=f"execution priority buried copy {idx}-{copy_idx}",
                    title=f"{primary_region} {signature_term} {route_term} ? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": f"exec-priority-seed-{idx}-{copy_idx}",
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_priority:specific_{idx}_{copy_idx}"
                            if copy_idx % 2 == 0
                            else f"colloquial:priority_{idx}_{copy_idx}"
                        ),
                        "pathfinder_axis_fit_score": 90,
                        "pathfinder_lens_fit_score": 88,
                        "clinic_treatment_fit_score": 91,
                        "worksite_efficiency_score": 87,
                        "reply_opportunity_score": row["reply_score"],
                        "reply_opportunity_tier": row["reply_tier"],
                        "reply_opportunity_signals": row["reply_signals"],
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=98,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    assert report["execution_readiness_quality"]["overall"]["category_lens_execution_ready_rate"] == 1.0
    priority_alignment = report["execution_priority_alignment_quality"]
    assert priority_alignment["overall"]["category_lens_priority_alignment_rate"] == 0.0
    assert priority_alignment["overall"]["fresh_category_lens_priority_alignment_rate"] == 0.0
    lens_gap = next(item for item in priority_alignment["category_lens_gaps"] if item["lane"] == expected_lane)
    assert lens_gap["unique_actionable_strict"] == 4
    assert lens_gap["execution_ready_actionable_strict"] == 2
    assert lens_gap["top_execution_ready_actionable_strict"] == 1
    assert lens_gap["priority_top_window"] == 3
    assert lens_gap["execution_priority_gap"] == 1
    assert "execution_ready_buried" in lens_gap["reasons"]
    assert "non_ready_priority_inversion" in lens_gap["reasons"]
    assert "top_priority_execution_gap" in lens_gap["reasons"]
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "execution_readiness_lens_coverage" not in failed
    assert "execution_priority_alignment_lens_coverage" in failed
    assert "fresh_execution_priority_alignment_lens_coverage" in failed
    assert report["next_run_playbook"]["execution_priority_alignment_required"] is True
    assert report["next_run_playbook"]["fresh_execution_priority_alignment_required"] is True
    assert any(
        item["lane"] == expected_lane
        for item in report["review_samples"]["execution_priority_alignment_gap_samples"]
    )
    assert any(
        item["code"] == "execution_priority_alignment_gaps"
        for item in report["recommendations"]
    )


def test_seed_candidate_alignment_flags_source_keyword_drift(tmp_path):
    db_path, conn = _make_db(tmp_path)
    primary_region = getattr(ACTIVE_KEYWORD_PROFILE, "primary_region", "cheongju")
    route_terms = {}
    for definition in VIRAL_ACTION_ROUTE_DEFINITIONS:
        terms = tuple(definition.get("terms") or ())
        if not terms:
            continue
        for lens_name in tuple(definition.get("lenses") or ()):
            route_terms.setdefault(lens_name, terms[0])
    journey_terms = {
        lens_name: route_terms[lens_name]
        for lens_name in ("review", "community", "cost", "consultation", "availability", "safety")
    }
    idx = 1
    for category in _priority_focus_categories():
        signature_terms = _signature_terms_for(category, count=2)
        if not signature_terms:
            signature_terms = [category]
        content_term = signature_terms[-1]
        for lens, route_term in journey_terms.items():
            for copy_idx in range(2):
                _insert_target(
                    conn,
                    target_id=f"queue-seed-candidate-drift-{idx}-{copy_idx}",
                    scan_id=99,
                    category=category,
                    grade="A",
                    status="pending",
                    priority=140 - copy_idx,
                    platform=("kin" if copy_idx == 0 else "cafe"),
                    content_preview=f"seed candidate drift copy {idx}-{copy_idx} {content_term}",
                    title=f"{primary_region} {content_term} {route_term} ? {idx}-{copy_idx}",
                    breakdown={
                        "pathfinder_source_keyword": (
                            f"{primary_region} 정밀소스키워드{idx}_{copy_idx} 심화상담"
                        ),
                        "pathfinder_execution_lens": lens,
                        "pathfinder_query_variant": (
                            f"axis_seed_alignment:specific_{idx}_{copy_idx}"
                            if copy_idx == 0
                            else f"{lens}:seed_alignment_{idx}_{copy_idx}"
                        ),
                        "pathfinder_axis_fit_score": 91,
                        "pathfinder_lens_fit_score": 89,
                        "clinic_treatment_fit_score": 92,
                        "worksite_efficiency_score": 88,
                        "reply_opportunity_score": 82,
                        "reply_opportunity_tier": "assist_now",
                        "reply_opportunity_signals": (
                            "public_reply_surface,help_request_language,decision_or_service_task,"
                            "local_actionable,unanswered_or_low_response"
                        ),
                        "reply_risk_penalty": 0,
                        "reply_risk_flags": "",
                        "manual_review": 0,
                    },
                )
            idx += 1
    conn.commit()
    conn.close()

    report = summarize_viral_handoff_quality(
        str(db_path),
        source_scan_run_id=99,
        include_seed_baseline=False,
        min_lane_total=1,
        sample_per_lane=1,
    )

    focus_category = _priority_focus_categories()[0]
    expected_lane = f"{focus_category}::review"
    assert report["work_queue_readiness"]["overall"]["category_lens_ready_rate"] == 1.0
    alignment = report["seed_candidate_alignment_quality"]
    assert alignment["overall"]["category_lens_seed_alignment_ready_rate"] == 0.0
    assert alignment["overall"]["fresh_category_lens_seed_alignment_ready_rate"] == 0.0
    lens_gap = next(item for item in alignment["category_lens_gaps"] if item["lane"] == expected_lane)
    assert lens_gap["unique_actionable_strict"] == 2
    assert lens_gap["seed_aligned_actionable_strict"] == 0
    assert lens_gap["seed_candidate_alignment_missing"] == 2
    assert "source_candidate_drift" in lens_gap["reasons"]
    assert "source_specific_term_lost" in lens_gap["reasons"]
    assert lens_gap["seed_candidate_missing_reasons"]["missing_source_specific_term"] == 2
    failed = report["quality_bar"]["failed_advisory_gates"]
    assert "seed_candidate_alignment_lens_coverage" in failed
    assert "fresh_seed_candidate_alignment_lens_coverage" in failed
    assert report["next_run_playbook"]["seed_candidate_alignment_required"] is True
    assert report["next_run_playbook"]["fresh_seed_candidate_alignment_required"] is True
    assert any(
        item["lane"] == expected_lane
        for item in report["review_samples"]["seed_candidate_alignment_gap_samples"]
    )
    assert any(
        item["code"] == "seed_candidate_alignment_gaps"
        for item in report["recommendations"]
    )


def test_seed_target_coverage_builds_next_run_playbook_for_undercovered_lanes():
    baseline = {
        "seed_count": 10,
        "seed_category_counts": {"피부/여드름": 6, "다이어트": 4},
        "seed_lens_counts": {"community": 7, "cost": 3},
    }
    category_summary = {
        "피부/여드름": {
            "total": 2,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 0.5,
            "strict_fit_rate": 0.5,
        }
    }
    lens_summary = {
        "community": {
            "total": 1,
            "survived": 1,
            "strict_fit": 0,
            "survival_rate": 1.0,
            "strict_fit_rate": 0.0,
        },
        "cost": {
            "total": 3,
            "survived": 3,
            "strict_fit": 3,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        },
    }

    coverage = _seed_target_coverage(
        baseline,
        category_summary=category_summary,
        lens_summary=lens_summary,
        min_targets_per_seed=1.0,
        min_strict_fit_per_seed=0.25,
    )
    playbook = _next_run_playbook(
        source_scan_run_id=66,
        row_count=6,
        overall={"axis_coverage_rate": 1.0, "lens_coverage_rate": 1.0},
        seed_target_coverage=coverage,
        weak_lanes=[],
        recommendations=[{"code": "undercovered_seed_categories"}],
        sample_per_lane=3,
    )

    assert coverage["by_category"]["피부/여드름"]["gap_reasons"] == ["low_target_per_seed", "low_strict_fit_per_seed"]
    assert coverage["by_category"]["다이어트"]["gap_reasons"] == ["no_targets", "low_strict_fit_per_seed"]
    assert coverage["by_lens"]["community"]["gap_reasons"] == ["low_target_per_seed", "low_strict_fit_per_seed"]
    assert playbook["rerun_required"] is True
    assert playbook["coverage_gap_required"] is True
    assert [item["category"] for item in playbook["boost_categories"]] == ["피부/여드름", "다이어트"]
    assert [item["lens"] for item in playbook["boost_lenses"]] == ["community"]
    assert "--source-scan-id 66" in playbook["suggested_commands"]["live_scan"]
    assert "--boost-category" in playbook["suggested_commands"]["live_scan"]
    assert '--boost-lens "community"' in playbook["suggested_commands"]["live_scan"]
    assert playbook["suggested_commands"]["post_run_audit"] == (
        "python scripts/viral_handoff_audit.py --scan-id 66 --days 1 --sample-per-lane 3 "
        "--out reports/viral_handoff_audit_scan66_days1.json"
    )
    assert '--since "<RUN_STARTED_AT>"' in playbook["suggested_commands"]["post_run_audit_current_run_template"]
    assert "--out reports/viral_handoff_audit_scan66_current_run.json" in (
        playbook["suggested_commands"]["post_run_audit_current_run_template"]
    )


def test_seed_target_coverage_detects_category_lens_gaps():
    baseline = {
        "seed_count": 2,
        "seed_category_counts": {"흉터/여드름흉터": 1, "다이어트": 1},
        "seed_lens_counts": {"cost": 1, "review": 1},
        "seed_category_lens_counts": {
            "흉터/여드름흉터::cost": 1,
            "다이어트::review": 1,
        },
    }
    category_summary = {
        "흉터/여드름흉터": {
            "total": 1,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        },
        "다이어트": {
            "total": 1,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        },
    }
    lens_summary = {
        "cost": {
            "total": 1,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        },
        "review": {
            "total": 1,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        },
    }
    category_lens_summary = {
        "다이어트::review": {
            "total": 1,
            "survived": 1,
            "strict_fit": 1,
            "survival_rate": 1.0,
            "strict_fit_rate": 1.0,
        }
    }

    coverage = _seed_target_coverage(
        baseline,
        category_summary=category_summary,
        lens_summary=lens_summary,
        category_lens_summary=category_lens_summary,
        min_targets_per_seed=1.0,
        min_strict_fit_per_seed=0.25,
    )
    playbook = _next_run_playbook(
        source_scan_run_id=91,
        row_count=1,
        overall={"axis_coverage_rate": 1.0, "lens_coverage_rate": 1.0},
        seed_target_coverage=coverage,
        weak_lanes=[],
        recommendations=[{"code": "undercovered_seed_category_lenses"}],
        sample_per_lane=3,
    )

    assert coverage["by_category"]["흉터/여드름흉터"]["gap_reasons"] == []
    assert coverage["by_lens"]["cost"]["gap_reasons"] == []
    assert coverage["by_category_lens"]["흉터/여드름흉터::cost"]["gap_reasons"] == [
        "no_targets",
        "low_strict_fit_per_seed",
    ]
    assert coverage["undercovered_category_lenses"] == ["흉터/여드름흉터::cost"]
    assert [item["category_lens"] for item in playbook["boost_category_lenses"]] == ["흉터/여드름흉터::cost"]
    assert '--boost-category "흉터/여드름흉터"' in playbook["suggested_commands"]["live_scan"]
    assert '--boost-lens "cost"' in playbook["suggested_commands"]["live_scan"]
    assert "--boost-category-lens" in playbook["suggested_commands"]["live_scan"]


def test_next_run_playbook_prioritizes_gyulim_signature_axes_over_peripheral_gaps():
    baseline = {
        "seed_count": 58,
        "seed_category_counts": {
            "소화/위장": 1,
            "두통/어지럼": 1,
            "흉터/여드름흉터": 18,
            "안면비대칭": 16,
            "피부/여드름": 10,
            "다이어트": 12,
        },
        "seed_lens_counts": {"review": 30, "community": 28},
    }
    # 주변축은 아예 target이 없고, 핵심축은 target은 많지만 생존율이 낮다.
    # playbook은 그래도 규림 시그니처 축을 먼저 boost해야 한다.
    category_summary = {
        category: {
            "total": 120,
            "survived": 3,
            "strict_fit": 1,
            "survival_rate": 0.025,
            "strict_fit_rate": 0.0083,
        }
        for category in ("흉터/여드름흉터", "안면비대칭", "피부/여드름", "다이어트")
    }
    lens_summary = {
        "review": {"total": 30, "survived": 1, "strict_fit": 0, "survival_rate": 0.033, "strict_fit_rate": 0.0},
        "community": {"total": 28, "survived": 1, "strict_fit": 0, "survival_rate": 0.036, "strict_fit_rate": 0.0},
    }

    coverage = _seed_target_coverage(
        baseline,
        category_summary=category_summary,
        lens_summary=lens_summary,
        min_targets_per_seed=1.0,
        min_strict_fit_per_seed=0.25,
    )
    playbook = _next_run_playbook(
        source_scan_run_id=87,
        row_count=13212,
        overall={"axis_coverage_rate": 1.0, "lens_coverage_rate": 1.0},
        seed_target_coverage=coverage,
        weak_lanes=[],
        recommendations=[{"code": "undercovered_seed_categories"}],
        sample_per_lane=2,
    )

    assert [item["category"] for item in playbook["boost_categories"][:4]] == [
        "흉터/여드름흉터",
        "안면비대칭",
        "피부/여드름",
        "다이어트",
    ]
    assert "소화/위장" not in [item["category"] for item in playbook["boost_categories"][:4]]
    live_scan = playbook["suggested_commands"]["live_scan"]
    assert '--boost-category "흉터/여드름흉터"' in live_scan
    assert '--boost-category "안면비대칭"' in live_scan
