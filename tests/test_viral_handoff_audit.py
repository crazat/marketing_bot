import json
import sqlite3

from core_services.viral_handoff_audit import (
    _next_run_playbook,
    _seed_target_coverage,
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


def _insert_target(conn, *, target_id, scan_id, category, grade, status, priority, breakdown):
    conn.execute(
        """
        INSERT INTO viral_targets (
            id, url, title, platform, category, matched_keyword, matched_keywords,
            matched_keyword_grade, matched_keyword_category, comment_status,
            priority_score, score_breakdown, source_scan_run_id, discovered_at
        ) VALUES (?, ?, ?, 'kin', ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (
            target_id,
            f"https://example.com/{target_id}",
            f"{category} target",
            category,
            f"{category} keyword",
            json.dumps([f"{category} keyword"], ensure_ascii=False),
            grade,
            category,
            status,
            priority,
            json.dumps(breakdown, ensure_ascii=False),
            scan_id,
        ),
    )


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
    assert [item["category"] for item in playbook["boost_categories"]] == ["다이어트", "피부/여드름"]
    assert [item["lens"] for item in playbook["boost_lenses"]] == ["community"]
    assert "--source-scan-id 66" in playbook["suggested_commands"]["live_scan"]
    assert "--boost-category" in playbook["suggested_commands"]["live_scan"]
    assert '--boost-lens "community"' in playbook["suggested_commands"]["live_scan"]
    assert playbook["suggested_commands"]["post_run_audit"] == "python scripts/viral_handoff_audit.py --scan-id 66 --sample-per-lane 3"
