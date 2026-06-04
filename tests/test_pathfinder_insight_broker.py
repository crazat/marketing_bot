import sqlite3

from core_services.pathfinder_insight_broker import PathfinderInsightBroker, load_pathfinder_prompt_context


def _create_keyword_schema(conn: sqlite3.Connection):
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
            grade TEXT,
            category TEXT,
            search_volume INTEGER,
            difficulty INTEGER,
            opportunity INTEGER,
            priority_v3 REAL,
            document_count INTEGER,
            business_core INTEGER,
            last_scan_run_id INTEGER,
            search_intent TEXT,
            trend_status TEXT,
            quality_flags_json TEXT,
            source_signals_json TEXT,
            longtail_score REAL,
            business_value_score REAL,
            high_value_longtail INTEGER,
            local_surface_score REAL,
            review_surface_score REAL,
            profile_action_signal REAL,
            availability_intent_score REAL,
            availability_intent_type TEXT,
            payment_coverage_score REAL,
            payment_coverage_type TEXT,
            access_convenience_score REAL,
            access_convenience_type TEXT,
            medical_ad_risk_score REAL,
            content_actionability_score REAL,
            competitor_brand_risk_score REAL
        );
        CREATE TABLE rank_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT,
            rank INTEGER,
            target_name TEXT,
            checked_at TEXT,
            date TEXT,
            status TEXT,
            total_results INTEGER,
            note TEXT,
            device_type TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO scan_runs(id, scan_type, status, completed_at) VALUES (1, 'legion', 'completed', '2026-06-03 10:00:00')"
    )


def test_pathfinder_insight_brief_builds_user_and_agent_handoff(tmp_path):
    db_path = tmp_path / "pathfinder.db"
    with sqlite3.connect(db_path) as conn:
        _create_keyword_schema(conn)
        conn.execute(
            """
            INSERT INTO keyword_insights (
                keyword, grade, category, search_volume, difficulty, opportunity, priority_v3,
                document_count, business_core, last_scan_run_id, search_intent, trend_status,
                quality_flags_json, source_signals_json, longtail_score, business_value_score,
                high_value_longtail, local_surface_score, review_surface_score, profile_action_signal,
                availability_intent_score, availability_intent_type, payment_coverage_score,
                payment_coverage_type, access_convenience_score, access_convenience_type,
                medical_ad_risk_score, content_actionability_score, competitor_brand_risk_score
            )
            VALUES (?, 'A', '교통사고', 40, 18, 91, 124,
                    900, 1, 1, 'transactional', 'rising',
                    '["access_high_intent"]', '["naver_ad", "serp"]', 82, 88,
                    1, 74, 20, 63, 30, 'none', 15,
                    'none', 86, 'parking_access', 10, 72, 0)
            """,
            ("청주 교통사고 한의원 주차 가능 길찾기",),
        )
        conn.execute(
            """
            INSERT INTO keyword_insights (
                keyword, grade, category, search_volume, difficulty, opportunity, priority_v3,
                document_count, business_core, last_scan_run_id, search_intent, trend_status,
                quality_flags_json, source_signals_json, longtail_score, business_value_score,
                high_value_longtail, local_surface_score, review_surface_score, profile_action_signal,
                availability_intent_score, availability_intent_type, payment_coverage_score,
                payment_coverage_type, access_convenience_score, access_convenience_type,
                medical_ad_risk_score, content_actionability_score, competitor_brand_risk_score
            )
            VALUES (?, 'B', '교통사고', 25, 22, 86, 101,
                    700, 1, 1, 'transactional', 'stable',
                    '["payment_high_intent"]', '["naver_ad"]', 78, 84,
                    1, 50, 30, 20, 25, 'none', 88,
                    'auto_insurance', 10, 'none', 12, 68, 0)
            """,
            ("청주 교통사고 한의원 자동차보험 서류",),
        )
        conn.executemany(
            """
            INSERT INTO rank_history (
                keyword, rank, target_name, checked_at, date, status, total_results, note, device_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "청주 교통사고 한의원 주차 가능 길찾기",
                    5,
                    "규림한의원",
                    "2026-06-02 09:00:00",
                    "2026-06-02",
                    "found",
                    30,
                    "previous mobile",
                    "mobile",
                ),
                (
                    "청주 교통사고 한의원 주차 가능 길찾기",
                    3,
                    "규림한의원",
                    "2026-06-03 09:00:00",
                    "2026-06-03",
                    "found",
                    31,
                    "latest mobile",
                    "mobile",
                ),
                (
                    "청주 교통사고 한의원 주차 가능 길찾기",
                    1,
                    "로랑한의원",
                    "2026-06-03 09:00:00",
                    "2026-06-03",
                    "found",
                    31,
                    "competitor ahead",
                    "mobile",
                ),
            ],
        )
        conn.commit()

    broker = PathfinderInsightBroker(str(db_path))
    brief = broker.build_user_brief(limit=5)
    first_handoff_id = brief["keyword_cards"][0]["handoff_id"]
    first_keyword = brief["keyword_cards"][0]["keyword"]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE pathfinder_insight_feedback (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                handoff_id TEXT NOT NULL,
                keyword TEXT,
                agent TEXT,
                feedback_type TEXT NOT NULL,
                note TEXT,
                metadata_json TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO pathfinder_insight_feedback (
                handoff_id, keyword, agent, feedback_type, note, metadata_json
            )
            VALUES (?, ?, 'blog_agent', 'accepted', 'good insight', '{}')
            """,
            (first_handoff_id, first_keyword),
        )
        conn.execute(
            """
            INSERT INTO pathfinder_insight_feedback (
                handoff_id, keyword, agent, feedback_type, note, metadata_json
            )
            VALUES (?, ?, 'shorts_studio_agent', 'needs_review', 'check claims', '{}')
            """,
            (first_handoff_id, first_keyword),
        )
        conn.commit()

    brief = broker.build_user_brief(limit=5)

    assert brief["summary"]["agent_ready"] is True
    assert brief["metrics"]["high_value_longtail_count"] == 2
    assert brief["metrics"]["access_intent_count"] == 1
    assert brief["metrics"]["payment_intent_count"] == 1
    assert brief["metrics"]["avg_confidence"] > 0.7
    assert brief["quality_gate"]["status"] in {"pass", "review"}
    assert brief["provenance"]["source_table"] == "keyword_insights"
    assert "evidence_trace" in brief["delivery_contract"]["handoff_fields"]
    assert "decision_packet" in brief["delivery_contract"]["handoff_fields"]
    assert "measurement_plan" in brief["delivery_contract"]["handoff_fields"]
    assert "data_quality" in brief["delivery_contract"]["handoff_fields"]
    assert "place_rank" in brief["delivery_contract"]["handoff_fields"]
    assert "place_rank_lift" in brief["delivery_contract"]["handoff_fields"]
    assert "place_value_loop" in brief["delivery_contract"]["handoff_fields"]
    assert "place_value_brief" in brief["delivery_contract"]["handoff_fields"]
    assert "place_lift_actions" in brief["delivery_contract"]["handoff_fields"]
    assert "place_lift_experiments" in brief["delivery_contract"]["handoff_fields"]
    assert "place_profile_audit" in brief["delivery_contract"]["handoff_fields"]
    assert brief["metrics"]["place_tracked_count"] == 1
    assert brief["metrics"]["place_visible_count"] == 1
    assert brief["metrics"]["place_top3_count"] == 1
    assert brief["metrics"]["place_competitor_gap_count"] == 1
    assert brief["place_tracking"]["tracked_count"] == 1
    assert brief["place_tracking"]["source"] == "keyword_cards"
    assert brief["place_tracking"]["latest_checked_at"] == "2026-06-03 09:00:00"
    lift = brief["place_rank_lift"]
    assert lift["status"] == "ready"
    assert lift["source"] == "keyword_cards"
    assert lift["measurement_contract"]["primary_metric"] == "rank_history.current_rank by keyword and device"
    assert lift["source_refs"][0]["url"].startswith("https://help.naver.com")
    assert lift["diagnostic_scores"]["overall_score"] > 0
    assert lift["diagnostic_scores"]["competitor_pressure_score"] == 0
    assert lift["automation_matrix"][0]["system_action"] == "keyword_relevance recovery action"
    assert len(lift["source_refs"]) >= 14
    assert any(ref["url"].endswith("25088?lang=ko") for ref in lift["source_refs"])
    assert any("content-abusing" in ref["url"] for ref in lift["source_refs"])
    assert lift["profile_audit_checklist"][0]["status"] == "urgent"
    assert lift["profile_audit_checklist"][0]["checks"]
    assert lift["handoff_actions"]
    assert lift["tracking_expansion"]["card_keyword_count"] >= 1
    assert "candidate_keywords" in lift["tracking_expansion"]
    assert any("허위 리뷰" in item for item in lift["prohibited_tactics"])
    value_loop = brief["place_value_loop"]
    assert value_loop["status"] == "ready"
    assert value_loop["pathfinder_to_place"]["representative_keyword_candidates"]
    assert len(value_loop["pathfinder_to_place"]["representative_keyword_candidates"]) <= 5
    assert value_loop["pathfinder_to_place"]["smartplace_updates"][0]["field"] == "대표키워드"
    assert value_loop["pathfinder_to_place"]["ai_longtail_readiness"]["score"] > 0
    assert value_loop["place_to_pathfinder"]["import_signals"][0]["source"] == "SmartPlace 인기 검색어/통계"
    assert value_loop["closed_loop_experiments"]
    assert any("25167" in ref["url"] for ref in value_loop["source_refs"])
    assert brief["feedback_contract"]["endpoint"] == "/pathfinder/insight-feedback"
    assert brief["feedback_summary"]["total_events"] == 2
    assert brief["feedback_summary"]["counts"]["accepted"] == 1
    assert brief["feedback_summary"]["counts"]["needs_review"] == 1
    assert brief["decision_overview"]["operator_review_count"] >= 1
    assert brief["decision_overview"]["measurement_contract"]["unit"] == "handoff_id"
    assert "blog_agent" in brief["agent_handoffs"]["packets"]
    assert "shorts_studio_agent" in brief["agent_handoffs"]["packets"]
    card = brief["keyword_cards"][0]
    assert card["handoff_id"].startswith("pf-")
    assert card["confidence_band"] in {"high", "medium"}
    assert any(item["signal"] == "access_convenience_score" for item in card["evidence_trace"])
    assert "required" in card["human_review"]
    assert card["decision_packet"]["state"] == "review"
    assert card["data_quality"]["status"] in {"fit_for_action", "fit_with_caveats"}
    assert card["measurement_plan"]["primary_metric"]
    assert card["place_rank"]["tracked"] is True
    assert card["place_rank"]["current"]["rank"] == 3
    assert card["place_rank"]["rank_delta"] == 2
    assert card["place_rank"]["trend"] == "improved"
    assert card["place_rank"]["best_competitor"]["target_name"] == "로랑한의원"
    assert card["place_rank"]["competitor_gap"] == 2
    assert card["place_lift_actions"][0]["lever"] == "information_completeness"
    assert card["place_lift_experiments"][0]["keyword"] == card["keyword"]
    assert card["place_tracking_candidates"]
    assert card["place_profile_audit"][0]["field"]
    assert card["place_value_brief"]["representative_keyword_candidate"]
    assert "키워드" in " ".join(card["place_value_brief"]["do_not"])
    assert card["feedback_snapshot"]["total_events"] == 2
    assert card["feedback_snapshot"]["learning_status"] == "review"
    action = brief["action_queue"][0]
    assert action["handoff_id"] == card["handoff_id"]
    assert action["evidence_trace"]
    assert action["decision_packet"]["state"] == "review"
    assert action["measurement_plan"]["review_after_days"] in {14, 30}
    assert action["data_quality"]["score"] > 0
    assert action["place_rank"]["current"]["rank"] == 3
    assert action["feedback_snapshot"]["counts"]["needs_review"] == 1
    assert lift["priority_actions"][0]["lever"] == "information_completeness"
    assert lift["priority_actions"][0]["keyword"] == card["keyword"]
    assert lift["priority_actions"][0]["measurement"] == "competitor_gap decreases or reaches zero for the tracked keyword"
    assert lift["experiment_queue"][0]["success_metric"] == "competitor_gap decreases or reaches zero for the tracked keyword"
    blog_task = brief["agent_handoffs"]["packets"]["blog_agent"]["tasks"][0]
    assert blog_task["primary_keyword"].startswith("청주")
    assert blog_task["handoff_id"] == card["handoff_id"]
    assert blog_task["success_criteria"]
    assert blog_task["decision_packet"]["state"] == "review"
    assert blog_task["measurement_plan"]["primary_metric"]
    assert blog_task["data_quality"]["score"] > 0
    assert blog_task["feedback_snapshot"]["learning_status"] == "review"
    assert blog_task["place_lift_actions"][0]["keyword"] == card["keyword"]
    assert blog_task["place_lift_experiments"][0]["success_metric"]
    assert blog_task["place_tracking_candidates"]
    assert blog_task["place_profile_audit"][0]["checks"]
    assert blog_task["place_value_brief"]["smartplace_field"]
    assert "SmartPlace profile value" in " ".join(blog_task["success_criteria"])
    assert "Pathfinder Insight Handoff" in brief["codex_prompt_context"]
    assert "confidence=" in brief["codex_prompt_context"]
    assert "Evidence:" in brief["codex_prompt_context"]
    assert "Decision:" in brief["codex_prompt_context"]
    assert "Data quality:" in brief["codex_prompt_context"]
    assert "Measure:" in brief["codex_prompt_context"]
    assert "Feedback:" in brief["codex_prompt_context"]
    assert "Place rank:" in brief["codex_prompt_context"]
    assert "Place lift:" in brief["codex_prompt_context"]
    assert "Place tracking candidates:" in brief["codex_prompt_context"]
    assert "Place value:" in brief["codex_prompt_context"]
    assert "SmartPlace representative keyword candidates:" in brief["codex_prompt_context"]
    legacy_context = load_pathfinder_prompt_context(str(db_path), limit=5)
    assert "Place lift:" in legacy_context
    assert "Place tracking candidates:" in legacy_context
    assert "Place value:" in legacy_context
    assert brief["codex_synthesis"]["status"] == "not_requested"
    assert brief["codex_synthesis"]["place_rank_lift"]["priority_actions"]
    assert brief["codex_synthesis"]["place_value_loop"]["representative_keyword_candidates"]
    assert brief["codex_synthesis"]["place_rank_lift"]["diagnostic_scores"]["overall_score"] > 0
    assert "청주" in brief["codex_synthesis"]["executive_summary"]
    assert any("방문 편의" in insight for insight in brief["top_insights"])


def test_pathfinder_place_tracking_candidates_remove_nested_location_tokens(tmp_path):
    broker = PathfinderInsightBroker(str(tmp_path / "empty.db"))
    card = {
        "keyword": "분평동 분평동교통사고입원자보방법 교통사고 한의원 비용",
        "category": "교통사고",
        "metrics": {
            "business_value_score": 100,
            "payment_coverage_score": 90,
            "access_convenience_score": 0,
            "availability_intent_score": 0,
            "review_surface_score": 0,
        },
        "handoff_id": "pf-test",
    }

    locations = broker._place_location_terms(card["keyword"])
    services = broker._place_service_terms(card, locations)
    plan = broker._place_tracking_expansion_plan(
        [card],
        {"cards": [], "source": "none"},
        [],
    )
    keywords = [item["keyword"] for item in plan["candidate_keywords"]]

    assert locations == ["분평동"]
    assert "분평동교통사고입원자보방법" not in services
    assert not any("분평동 분평동교통사고" in keyword for keyword in keywords)
    assert "분평동 교통사고 한의원 비용" in keywords
    assert all(item["quality"]["status"] == "clean" for item in plan["candidate_keywords"])


def test_pathfinder_brief_surfaces_recent_place_tracking_when_keyword_cards_do_not_match(tmp_path):
    db_path = tmp_path / "place_fallback.db"
    with sqlite3.connect(db_path) as conn:
        _create_keyword_schema(conn)
        conn.execute(
            """
            INSERT INTO keyword_insights (
                keyword, grade, category, search_volume, difficulty, opportunity, priority_v3,
                document_count, business_core, last_scan_run_id, search_intent, trend_status,
                quality_flags_json, source_signals_json, longtail_score, business_value_score,
                high_value_longtail
            )
            VALUES ('청주 다이어트 한약 비용', 'A', '다이어트', 100, 20, 90, 120,
                    1000, 1, 1, 'transactional', 'stable', '[]', '["naver_ad"]', 80, 88, 1)
            """
        )
        conn.executemany(
            """
            INSERT INTO rank_history (
                keyword, rank, target_name, checked_at, date, status, total_results, note, device_type
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("청주 안면비대칭", 6, "규림한의원", "2026-06-02 09:00:00", "2026-06-02", "found", 20, "", "mobile"),
                ("청주 안면비대칭", 4, "규림한의원", "2026-06-03 09:00:00", "2026-06-03", "found", 20, "", "mobile"),
            ],
        )
        conn.commit()

    broker = PathfinderInsightBroker(str(db_path))
    brief = broker.build_user_brief(limit=3)

    assert brief["metrics"]["place_tracked_count"] == 0
    assert brief["place_tracking"]["source"] == "rank_history_recent"
    assert brief["place_tracking"]["tracked_count"] == 1
    assert brief["place_tracking"]["cards"][0]["keyword"] == "청주 안면비대칭"
    assert brief["place_tracking"]["cards"][0]["current_rank"] == 4
    assert brief["place_rank_lift"]["source"] == "rank_history_recent"
    assert brief["place_rank_lift"]["priority_actions"][0]["lever"] == "local_content_alignment"
    assert brief["place_rank_lift"]["priority_actions"][0]["keyword"] == "청주 안면비대칭"
    assert brief["place_rank_lift"]["experiment_queue"][0]["keyword"] == "청주 안면비대칭"
    assert brief["place_rank_lift"]["diagnostic_scores"]["visibility_score"] > 0
    assert brief["keyword_cards"][0]["place_lift_actions"]
    assert brief["keyword_cards"][0]["place_lift_experiments"]
    assert any(
        item["keyword"] == "청주 다이어트 한약 비용"
        for item in brief["place_rank_lift"]["tracking_expansion"]["candidate_keywords"]
    )
    assert any(
        item["keyword"] == "청주 다이어트 한약 비용"
        for item in brief["keyword_cards"][0]["place_tracking_candidates"]
    )
    assert "플레이스 추적 결과 1개" in " ".join(brief["top_insights"])
    assert "최신 플레이스 추적 요약" in brief["summary"]["next_best_action"]


def test_pathfinder_handoff_agent_filter_returns_only_requested(tmp_path):
    db_path = tmp_path / "pathfinder.db"
    with sqlite3.connect(db_path) as conn:
        _create_keyword_schema(conn)
        conn.execute(
            """
            INSERT INTO keyword_insights (
                keyword, grade, category, search_volume, difficulty, opportunity, priority_v3,
                document_count, business_core, last_scan_run_id, search_intent, quality_flags_json,
                source_signals_json, business_value_score, high_value_longtail,
                access_convenience_score, access_convenience_type
            )
            VALUES ('청주 한의원 휠체어 엘리베이터 위치', 'A', '한의원일반', 35, 20, 90, 118,
                    600, 1, 1, 'navigational', '[]', '["serp"]', 86, 1, 90, 'accessibility_need')
            """
        )
        conn.commit()

    broker = PathfinderInsightBroker(str(db_path))
    handoff = broker.build_agent_handoffs(agent="shorts", limit=3)

    assert set(handoff["packets"].keys()) == {"shorts_studio_agent"}
    task = handoff["packets"]["shorts_studio_agent"]["tasks"][0]
    assert task["primary_keyword"] == "청주 한의원 휠체어 엘리베이터 위치"
    assert task["handoff_id"].startswith("pf-")
    assert task["confidence"] > 0
    assert task["evidence_trace"]
    assert task["success_criteria"]
    assert task["decision_packet"]["state"] in {"go", "review"}
    assert task["measurement_plan"]["primary_metric"]
    assert task["data_quality"]["score"] > 0
    assert task["place_lift_actions"]
    assert task["place_tracking_candidates"]
    assert task["place_value_brief"]
    assert "keeps place_tracking_candidates" in " ".join(task["success_criteria"])
    assert "SmartPlace profile value" in " ".join(task["success_criteria"])
    assert "주차" in task["hook"] or "방문" in task["hook"]


def test_pathfinder_broker_handles_minimal_schema(tmp_path):
    db_path = tmp_path / "minimal.db"
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE keyword_insights (
                keyword TEXT PRIMARY KEY,
                grade TEXT,
                search_volume INTEGER
            );
            INSERT INTO keyword_insights(keyword, grade, search_volume)
            VALUES ('청주 한의원 추천', 'B', 120);
            """
        )

    broker = PathfinderInsightBroker(str(db_path))
    brief = broker.build_user_brief(limit=3, business_core_only=False, latest_verified_only=False)
    context = load_pathfinder_prompt_context(str(db_path), agent="blog_agent", topic="청주 한의원 추천")

    assert brief["keyword_cards"][0]["keyword"] == "청주 한의원 추천"
    assert brief["keyword_cards"][0]["handoff_id"].startswith("pf-")
    assert brief["keyword_cards"][0]["decision_packet"]["state"] == "hold"
    assert brief["keyword_cards"][0]["data_quality"]["status"] == "thin"
    assert brief["decision_overview"]["operator_review_count"] == 1
    assert brief["quality_gate"]["status"] == "review"
    assert brief["summary"]["agent_ready"] is True
    assert "confidence=" in context
    assert "청주 한의원 추천" in context


def test_pathfinder_broker_latest_filter_uses_scan_run_id_when_last_scan_missing(tmp_path):
    db_path = tmp_path / "scan_run_only.db"
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
                grade TEXT,
                category TEXT,
                search_volume INTEGER,
                document_count INTEGER,
                business_core INTEGER,
                scan_run_id INTEGER
            );
            INSERT INTO scan_runs(id, scan_type, status, completed_at)
            VALUES (8, 'legion', 'completed', '2026-06-01');
            INSERT INTO keyword_insights(
                keyword, grade, category, search_volume, document_count, business_core, scan_run_id
            ) VALUES
                ('latest scan keyword', 'A', '교통사고', 100, 1000, 1, 8),
                ('older scan keyword', 'A', '교통사고', 100, 1000, 1, 7);
            """
        )

    broker = PathfinderInsightBroker(str(db_path))
    brief = broker.build_user_brief(limit=5)

    keywords = [card["keyword"] for card in brief["keyword_cards"]]
    assert keywords == ["latest scan keyword"]
    assert brief["keyword_cards"][0]["metrics"]["last_scan_run_id"] == 8


def test_pathfinder_codex_synthesis_falls_back_when_ai_unavailable(tmp_path, monkeypatch):
    db_path = tmp_path / "pathfinder.db"
    with sqlite3.connect(db_path) as conn:
        _create_keyword_schema(conn)
        conn.execute(
            """
            INSERT INTO keyword_insights (
                keyword, grade, category, search_volume, difficulty, opportunity, priority_v3,
                document_count, business_core, last_scan_run_id, search_intent, quality_flags_json,
                source_signals_json, business_value_score, high_value_longtail,
                access_convenience_score, access_convenience_type
            )
            VALUES ('청주 한의원 주차 편한 곳', 'A', '한의원일반', 35, 20, 90, 118,
                    600, 1, 1, 'transactional', '[]', '["serp"]', 86, 1, 90, 'parking_access')
            """
        )
        conn.commit()

    monkeypatch.setenv("MARKETING_BOT_DISABLE_AI", "true")
    broker = PathfinderInsightBroker(str(db_path))
    brief = broker.build_user_brief(limit=3, use_codex=True)

    assert brief["codex_synthesis"]["status"] == "fallback"
    assert brief["codex_synthesis"]["model"] == "deterministic_fallback"
    assert "청주 한의원 주차 편한 곳" in brief["codex_synthesis"]["executive_summary"]
