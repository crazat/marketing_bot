import sqlite3

from db.database import DatabaseManager
from pathfinder_v3_legion import KeywordResult, PathfinderLegion, LegionCollector
from scripts.ai_ad_classify_apply import _execute_scoped_update
import viral_hunter
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
