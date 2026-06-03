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
