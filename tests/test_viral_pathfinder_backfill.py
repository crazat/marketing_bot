import json
import sqlite3

from core_services.viral_pathfinder_backfill import backfill_pathfinder_metrics


def _make_db(tmp_path):
    db_path = tmp_path / "viral_pathfinder_backfill.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE keyword_insights (
            keyword TEXT,
            category TEXT,
            grade TEXT,
            search_volume INTEGER,
            document_count INTEGER,
            kei REAL,
            priority_v3 REAL,
            search_intent TEXT,
            scan_run_id INTEGER,
            last_scan_run_id INTEGER,
            business_core INTEGER,
            status TEXT,
            high_value_longtail INTEGER,
            longtail_score REAL,
            business_value_score REAL,
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
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            platform TEXT,
            url TEXT,
            title TEXT,
            content_preview TEXT,
            matched_keywords TEXT,
            matched_keyword TEXT,
            category TEXT,
            is_commentable INTEGER,
            comment_status TEXT,
            priority_score REAL,
            score_breakdown TEXT,
            source_scan_run_id INTEGER,
            matched_keyword_grade TEXT,
            matched_keyword_kei REAL,
            matched_keyword_priority REAL,
            matched_keyword_category TEXT,
            discovered_at TEXT,
            updated_at TEXT
        )
        """
    )
    return db_path, conn


def _insert_seed(conn, *, keyword, category="교통사고", scan_id=62):
    conn.execute(
        """
        INSERT INTO keyword_insights (
            keyword, category, grade, search_volume, document_count, kei, priority_v3,
            search_intent, scan_run_id, last_scan_run_id, business_core, status,
            high_value_longtail, longtail_score, business_value_score,
            local_service_fit_score, content_actionability_score, medical_ad_risk_score,
            community_signal, conversion_signal, profile_action_signal,
            local_surface_score, review_surface_score, reputation_risk_score,
            competitor_brand_risk_score, availability_intent_score, payment_coverage_score,
            access_convenience_score, verification_score, novelty_score,
            preferred_search_surface, recommended_content_type, brand_intent_type,
            review_intent_type, quality_flags_json, source_signals_json
        ) VALUES (
            ?, ?, 'B', 120, 30, 4.5, 88,
            'transactional', ?, ?, 1, 'active',
            1, 72, 80,
            86, 84, 12,
            66, 72, 44,
            75, 10, 0,
            0, 10, 92,
            20, 70, 15,
            'hybrid_local_content', 'community_answer', 'generic',
            'none', '[]', '[]'
        )
        """,
        (keyword, category, scan_id, scan_id),
    )


def _insert_target(conn, *, target_id, keyword=None, matched_keywords=None, scan_id=62, status="raw_backlog"):
    matched_keywords = matched_keywords if matched_keywords is not None else ([keyword] if keyword else [])
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, platform, url, title, content_preview, matched_keywords, matched_keyword,
            category, is_commentable, comment_status, priority_score, score_breakdown,
            source_scan_run_id, matched_keyword_grade, matched_keyword_kei,
            matched_keyword_priority, matched_keyword_category, discovered_at, updated_at
        ) VALUES (?, 'cafe', ?, ?, ?, ?, ?, '교통사고', 1, ?, 140, ?, ?, '', 0, 0, '', datetime('now'), datetime('now'))
        """,
        (
            target_id,
            f"https://example.com/{target_id}",
            "청주 교통사고 한의원 치료비 문의",
            "봉명동 청주 교통사고 한의원 치료비 비용 보험 상담이 궁금합니다",
            json.dumps(matched_keywords, ensure_ascii=False),
            keyword or "",
            status,
            json.dumps({"clinic_treatment_fit_score": 81}, ensure_ascii=False),
            scan_id,
        ),
    )


def _score_breakdown(conn, target_id):
    raw = conn.execute(
        "SELECT score_breakdown FROM viral_targets WHERE id = ?",
        (target_id,),
    ).fetchone()[0]
    return json.loads(raw)


def test_pathfinder_backfill_dry_run_reports_without_mutating(tmp_path):
    db_path, conn = _make_db(tmp_path)
    keyword = "봉명동 교통사고 한의원 치료비"
    _insert_seed(conn, keyword=keyword)
    _insert_target(conn, target_id="old-target", keyword=keyword)
    conn.commit()

    report = backfill_pathfinder_metrics(
        db_path=str(db_path),
        source_scan_run_id=62,
        apply=False,
    )

    assert report["candidate_count"] == 1
    assert report["would_update"] == 1
    assert report["updated"] == 0
    assert report["context_source_counts"] == {"scan_seed_exact": 1}
    assert "pathfinder_axis_fit_score" not in _score_breakdown(conn, "old-target")


def test_pathfinder_backfill_default_covers_filtered_rows_for_audit_parity(tmp_path):
    db_path, conn = _make_db(tmp_path)
    keyword = "봉명동 교통사고 한의원 치료비"
    _insert_seed(conn, keyword=keyword)
    _insert_target(conn, target_id="raw-target", keyword=keyword)
    _insert_target(conn, target_id="filtered-target", keyword=keyword, status="filtered_out_ad")
    conn.commit()

    report = backfill_pathfinder_metrics(
        db_path=str(db_path),
        source_scan_run_id=62,
        apply=False,
    )

    assert report["candidate_count"] == 2
    assert report["would_update"] == 2


def test_pathfinder_backfill_apply_merges_context_and_fit_metrics(tmp_path):
    db_path, conn = _make_db(tmp_path)
    keyword = "봉명동 교통사고 한의원 치료비"
    _insert_seed(conn, keyword=keyword)
    _insert_target(conn, target_id="old-target", keyword=keyword)
    conn.commit()

    report = backfill_pathfinder_metrics(
        db_path=str(db_path),
        source_scan_run_id=62,
        apply=True,
    )

    assert report["updated"] == 1
    breakdown = _score_breakdown(conn, "old-target")
    assert breakdown["clinic_treatment_fit_score"] == 81
    assert breakdown["pathfinder_execution_lens"] == "cost"
    assert breakdown["pathfinder_source_keyword"] == keyword
    assert breakdown["pathfinder_backfill_context_source"] == "scan_seed_exact"
    assert breakdown["pathfinder_axis_fit_score"] > 0
    assert breakdown["pathfinder_lens_fit_score"] >= 55

    row = conn.execute(
        """
        SELECT matched_keyword_grade, matched_keyword_category, matched_keyword_priority
        FROM viral_targets
        WHERE id = 'old-target'
        """
    ).fetchone()
    assert row[0] == "B"
    assert row[1] == "교통사고"
    assert row[2] == 88


def test_pathfinder_backfill_skips_ambiguous_multi_seed_without_keyword(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_seed(conn, keyword="봉명동 교통사고 한의원 치료비", category="교통사고")
    _insert_seed(conn, keyword="청주 다이어트 한약 비용", category="다이어트")
    _insert_target(conn, target_id="ambiguous", keyword=None, matched_keywords=[])
    conn.commit()

    report = backfill_pathfinder_metrics(
        db_path=str(db_path),
        source_scan_run_id=62,
        apply=True,
    )

    assert report["candidate_count"] == 1
    assert report["would_update"] == 0
    assert report["updated"] == 0
    assert report["skipped_no_context"] == 1
    assert "pathfinder_axis_fit_score" not in _score_breakdown(conn, "ambiguous")
