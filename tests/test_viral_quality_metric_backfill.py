import json
import sqlite3

from core_services.viral_quality_metric_backfill import backfill_quality_metrics


def _make_db(tmp_path):
    db_path = tmp_path / "viral_quality_metric_backfill.db"
    conn = sqlite3.connect(db_path)
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
            posted_at TEXT,
            discovered_at TEXT,
            updated_at TEXT,
            comment_count INTEGER,
            view_count INTEGER
        )
        """
    )
    return db_path, conn


def _insert_target(
    conn,
    *,
    target_id,
    status="filtered_out",
    category="교통사고",
    breakdown=None,
):
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, platform, url, title, content_preview, matched_keywords, matched_keyword,
            category, is_commentable, comment_status, priority_score, score_breakdown,
            source_scan_run_id, matched_keyword_grade, matched_keyword_kei,
            matched_keyword_priority, matched_keyword_category, posted_at,
            discovered_at, updated_at, comment_count, view_count
        ) VALUES (
            ?, 'cafe', ?, '청주 교통사고 한의원 치료비 문의',
            '봉명동 청주 교통사고 한의원 치료비 비용 보험 상담 가능한 곳 추천 부탁드립니다',
            ?, '봉명동 교통사고 한의원 치료비', ?, 1, ?, 120, ?,
            104, 'A', 4.0, 95, ?, datetime('now'), datetime('now'), datetime('now'), 0, 180
        )
        """,
        (
            target_id,
            f"https://example.com/{target_id}",
            json.dumps(["봉명동 교통사고 한의원 치료비"], ensure_ascii=False),
            category,
            status,
            json.dumps(breakdown or {}, ensure_ascii=False),
            category,
        ),
    )


def _breakdown(conn, target_id):
    raw = conn.execute(
        "SELECT score_breakdown FROM viral_targets WHERE id = ?",
        (target_id,),
    ).fetchone()[0]
    return json.loads(raw)


def test_quality_metric_backfill_dry_run_does_not_mutate(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(conn, target_id="missing")
    conn.commit()

    report = backfill_quality_metrics(
        db_path=str(db_path),
        source_scan_run_id=104,
        apply=False,
    )

    assert report["candidate_count"] == 1
    assert report["would_update"] == 1
    assert report["updated"] == 0
    assert "clinic_treatment_fit_score" not in _breakdown(conn, "missing")


def test_quality_metric_backfill_apply_covers_filtered_rows(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(conn, target_id="filtered", status="filtered_out")
    _insert_target(conn, target_id="skipped", status="skipped")
    conn.commit()

    report = backfill_quality_metrics(
        db_path=str(db_path),
        source_scan_run_id=104,
        apply=True,
    )

    assert report["candidate_count"] == 2
    assert report["updated"] == 2
    assert report["coverage_before"]["clinic_coverage_rate"] == 0.0
    assert report["coverage_after"]["clinic_coverage_rate"] == 1.0

    breakdown = _breakdown(conn, "filtered")
    assert breakdown["clinic_treatment_fit_score"] >= 55
    assert breakdown["worksite_efficiency_score"] >= 55
    assert breakdown["quality_metric_backfilled"] is True


def test_quality_metric_backfill_default_skips_existing_metrics(tmp_path):
    db_path, conn = _make_db(tmp_path)
    _insert_target(
        conn,
        target_id="existing",
        breakdown={"clinic_treatment_fit_score": 91, "worksite_efficiency_score": 88},
    )
    conn.commit()

    report = backfill_quality_metrics(
        db_path=str(db_path),
        source_scan_run_id=104,
        apply=True,
    )

    assert report["candidate_count"] == 0
    assert report["updated"] == 0
    breakdown = _breakdown(conn, "existing")
    assert breakdown["clinic_treatment_fit_score"] == 91
    assert breakdown["worksite_efficiency_score"] == 88
