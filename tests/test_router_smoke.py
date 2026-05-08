"""라우터 레벨 스모크 테스트.

FastAPI TestClient로 viral/leads 주요 GET 엔드포인트의 import·응답 구조를 검증.
실제 DB는 테스트 격리용 임시 파일 사용.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "marketing_bot_web", "backend")
for p in (ROOT, BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

# auth 비활성 환경
os.environ.setdefault("DISABLE_API_AUTH", "true")
os.environ.setdefault("MARKETING_BOT_API_KEY", "test-key")


@pytest.fixture
def tmp_db_path(monkeypatch):
    """임시 DB를 만들고 viral_targets + mentions 최소 스키마 초기화."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY, platform TEXT, url TEXT UNIQUE, title TEXT,
            content_preview TEXT, matched_keywords TEXT, category TEXT,
            is_commentable BOOLEAN, comment_status TEXT, generated_comment TEXT,
            priority_score REAL, discovered_at TIMESTAMP, last_scanned_at TIMESTAMP,
            scan_count INTEGER DEFAULT 1, content_hash TEXT, author TEXT
        );
        CREATE TABLE viral_target_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viral_target_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            UNIQUE(viral_target_id, keyword)
        );
        CREATE TABLE mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_name TEXT, keyword TEXT, source TEXT, title TEXT, content TEXT,
            url TEXT, scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending', score INTEGER, grade TEXT
        );
        """
    )
    # 샘플 데이터
    conn.execute(
        "INSERT INTO viral_targets(id, platform, url, title, comment_status, priority_score, discovered_at) "
        "VALUES ('t1', 'cafe', 'http://x/1', 'title 1', 'pending', 90, datetime('now'))"
    )
    conn.execute(
        "INSERT INTO viral_targets(id, platform, url, title, comment_status, priority_score, discovered_at) "
        "VALUES ('t2', 'blog', 'http://x/2', 'title 2', 'pending', 50, datetime('now'))"
    )
    conn.commit()
    conn.close()
    monkeypatch.setenv("MARKETING_BOT_DB_PATH", path)
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_repositories_direct_instantiation(tmp_db_path):
    """Repository가 DatabaseManager 초기화 없이 독립 사용 가능."""
    from repositories import (
        ViralTargetRepository,
        LeadRepository,
        CompetitorRepository,
        KeywordRepository,
    )
    # 모두 db_path만으로 동작
    ViralTargetRepository(tmp_db_path)
    LeadRepository(tmp_db_path)
    # Competitor/Keyword는 테이블이 없을 수 있으므로 count는 생략
    # 단순 인스턴스 확인만
    CompetitorRepository(tmp_db_path)
    KeywordRepository(tmp_db_path)


def test_viral_target_repo_filter(tmp_db_path):
    from repositories import ViralTargetRepository
    repo = ViralTargetRepository(tmp_db_path)
    assert repo.count({"status": "pending"}) == 2
    rows = repo.list({"status": "pending"}, sort="priority")
    assert len(rows) == 2
    assert rows[0]["priority_score"] >= rows[1]["priority_score"]


def test_smart_recommendations_hide_revisited_from_visible_staff_counts(tmp_db_path, monkeypatch):
    from routers import viral as viral_router

    monkeypatch.setattr(viral_router, "get_db_path", lambda: tmp_db_path)
    core_category = viral_router.VIRAL_CORE_CATEGORIES[0]

    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO viral_targets(
                id, platform, url, title, matched_keywords, category,
                is_commentable, comment_status, priority_score, discovered_at, scan_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            """,
            (
                "fresh-core",
                "cafe",
                "http://x/fresh-core",
                "fresh core",
                '["core"]',
                core_category,
                1,
                "pending",
                90,
                1,
            ),
        )
        conn.execute(
            """
            INSERT INTO viral_targets(
                id, platform, url, title, matched_keywords, category,
                is_commentable, comment_status, priority_score, discovered_at, scan_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            """,
            (
                "revisited-core",
                "blog",
                "http://x/revisited-core",
                "revisited core",
                '["core"]',
                core_category,
                1,
                "pending",
                120,
                2,
            ),
        )
        conn.commit()

    result = asyncio.run(
        viral_router.get_smart_recommendations(work_scope="core", exclude_revisited=None)
    )
    quick = {item["id"]: item for item in result["quick_filters"]}

    assert quick["high_priority"]["count"] == 1
    assert quick["high_priority"]["filter"] == {"status": "pending", "min_score": 80, "sort": "priority"}
    assert quick["recurring"]["count"] == 1
    assert quick["recurring"]["filter"] == {"status": "pending", "min_scan_count": 2, "sort": "scan_count"}
    assert quick["commentable"]["filter"] == {"status": "pending", "commentable_only": True, "sort": "priority"}
    assert [target["id"] for target in result["today_focus"]] == ["fresh-core"]
    assert result["platform_priorities"] == [{"platform": "cafe", "count": 1, "avg_score": 90.0}]


def test_all_backlog_staff_queries_hide_revisited_by_default(tmp_db_path, monkeypatch):
    from routers import viral as viral_router

    monkeypatch.setattr(viral_router, "get_db_path", lambda: tmp_db_path)

    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO viral_targets(
                id, platform, url, title, comment_status, priority_score,
                discovered_at, scan_count
            )
            VALUES (?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), ?)
            """,
            (
                "revisited-backlog",
                "blog",
                "http://x/revisited-backlog",
                "revisited backlog",
                "pending",
                95,
                2,
            ),
        )
        conn.commit()

    default_count = asyncio.run(
        viral_router.count_viral_targets(
            work_scope="all_backlog",
            exclude_revisited=None,
            min_confidence=None,
            min_score=None,
            commentable_only=None,
        )
    )
    explicit_all_count = asyncio.run(
        viral_router.count_viral_targets(
            work_scope="all_backlog",
            exclude_revisited=False,
            min_confidence=None,
            min_score=None,
            commentable_only=None,
        )
    )
    recurring_count = asyncio.run(
        viral_router.count_viral_targets(
            work_scope="all_backlog",
            min_scan_count=2,
            min_confidence=None,
            min_score=None,
            commentable_only=None,
        )
    )

    assert default_count == {"total": 2}
    assert explicit_all_count == {"total": 3}
    assert recurring_count == {"total": 1}


def test_invalid_work_scope_falls_back_to_staff_default(tmp_db_path, monkeypatch):
    from routers import viral as viral_router

    monkeypatch.setattr(viral_router, "get_db_path", lambda: tmp_db_path)
    core_category = viral_router.VIRAL_CORE_CATEGORIES[0]

    with sqlite3.connect(tmp_db_path) as conn:
        conn.execute(
            """
            INSERT INTO viral_targets(
                id, platform, url, title, category, comment_status,
                priority_score, discovered_at, scan_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), 1)
            """,
            (
                "valid-core-scope",
                "cafe",
                "http://x/valid-core-scope",
                "valid core scope",
                core_category,
                "pending",
                90,
            ),
        )
        conn.execute(
            """
            INSERT INTO viral_targets(
                id, platform, url, title, category, comment_status,
                priority_score, discovered_at, scan_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now', 'localtime'), 1)
            """,
            (
                "off-scope",
                "blog",
                "http://x/off-scope",
                "off scope",
                "legacy",
                "pending",
                95,
            ),
        )
        conn.commit()

    result = asyncio.run(
        viral_router.count_viral_targets(
            work_scope="not-a-real-scope",
            exclude_revisited=None,
            min_confidence=None,
            min_score=None,
            commentable_only=None,
        )
    )

    assert result == {"total": 1}


def test_viral_service_compute_penalty_import():
    """services.viral_service import 및 기본 동작."""
    from services.viral_service import compute_penalty_score
    assert compute_penalty_score(0, "domain") == 0
    assert compute_penalty_score(100, "domain") == 30  # 캡


def test_lead_service_extract_tokens_import():
    from services.lead_service import extract_tokens
    tokens = extract_tokens("청주 다이어트 한약")
    assert "다이어트" in tokens
