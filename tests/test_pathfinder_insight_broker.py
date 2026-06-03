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
    assert card["feedback_snapshot"]["total_events"] == 2
    assert card["feedback_snapshot"]["learning_status"] == "review"
    action = brief["action_queue"][0]
    assert action["handoff_id"] == card["handoff_id"]
    assert action["evidence_trace"]
    assert action["decision_packet"]["state"] == "review"
    assert action["measurement_plan"]["review_after_days"] in {14, 30}
    assert action["data_quality"]["score"] > 0
    assert action["feedback_snapshot"]["counts"]["needs_review"] == 1
    blog_task = brief["agent_handoffs"]["packets"]["blog_agent"]["tasks"][0]
    assert blog_task["primary_keyword"].startswith("청주")
    assert blog_task["handoff_id"] == card["handoff_id"]
    assert blog_task["success_criteria"]
    assert blog_task["decision_packet"]["state"] == "review"
    assert blog_task["measurement_plan"]["primary_metric"]
    assert blog_task["data_quality"]["score"] > 0
    assert blog_task["feedback_snapshot"]["learning_status"] == "review"
    assert "Pathfinder Insight Handoff" in brief["codex_prompt_context"]
    assert "confidence=" in brief["codex_prompt_context"]
    assert "Evidence:" in brief["codex_prompt_context"]
    assert "Decision:" in brief["codex_prompt_context"]
    assert "Data quality:" in brief["codex_prompt_context"]
    assert "Measure:" in brief["codex_prompt_context"]
    assert "Feedback:" in brief["codex_prompt_context"]
    assert brief["codex_synthesis"]["status"] == "not_requested"
    assert "청주" in brief["codex_synthesis"]["executive_summary"]
    assert any("방문 편의" in insight for insight in brief["top_insights"])


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
