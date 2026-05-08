"""ViralTargetRepository 단위 테스트 (PoC)."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

# 루트 경로 추가
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from repositories import ViralTargetRepository


@pytest.fixture
def tmp_db():
    """임시 DB를 만들고 viral_targets 스키마만 초기화."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE viral_targets (
            id TEXT PRIMARY KEY,
            platform TEXT,
            url TEXT UNIQUE,
            title TEXT,
            content_preview TEXT,
            matched_keywords TEXT,
            category TEXT,
            is_commentable BOOLEAN,
            comment_status TEXT,
            generated_comment TEXT,
            priority_score REAL,
            discovered_at TIMESTAMP,
            last_scanned_at TIMESTAMP,
            scan_count INTEGER DEFAULT 1,
            content_hash TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE viral_target_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            viral_target_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            UNIQUE(viral_target_id, keyword)
        )
        """
    )
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_insert_and_get(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    assert repo.count() == 0

    sample = {
        "id": "t1",
        "platform": "cafe",
        "url": "https://cafe.naver.com/x/1",
        "title": "청주 다이어트",
        "content_preview": "본문 미리보기 100자 이상으로 충분한 길이가 되도록 채워 테스트용 데이터",
        "matched_keywords": ["청주 다이어트", "한의원"],
        "priority_score": 85,
        "category": "기타",
    }
    assert repo.insert(sample) is True

    got = repo.get("t1")
    assert got is not None
    assert got["title"] == "청주 다이어트"
    assert got["matched_keywords"] == ["청주 다이어트", "한의원"]


def test_list_and_count_filtered(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    for i in range(5):
        repo.insert({
            "id": f"t{i}",
            "platform": "cafe" if i % 2 == 0 else "blog",
            "url": f"https://x/{i}",
            "title": f"title {i}",
            "priority_score": i * 10,
            "comment_status": "pending" if i < 3 else "posted",
            "matched_keywords": [],
        })

    assert repo.count() == 5
    assert repo.count({"platform": "cafe"}) == 3
    assert repo.count({"status": "pending"}) == 3

    rows = repo.list({"platform": "cafe"}, limit=10)
    assert len(rows) == 3
    # priority DESC 정렬
    assert rows[0]["priority_score"] >= rows[-1]["priority_score"]


def test_score_and_commentable_filters_match_smart_quick_filters(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    repo.insert({
        "id": "hot-commentable",
        "platform": "cafe",
        "url": "https://x/hot-commentable",
        "title": "hot commentable",
        "comment_status": "pending",
        "priority_score": 90,
        "is_commentable": True,
        "matched_keywords": [],
    })
    repo.insert({
        "id": "hot-closed",
        "platform": "blog",
        "url": "https://x/hot-closed",
        "title": "hot closed",
        "comment_status": "pending",
        "priority_score": 85,
        "is_commentable": False,
        "matched_keywords": [],
    })
    repo.insert({
        "id": "cold-commentable",
        "platform": "kin",
        "url": "https://x/cold-commentable",
        "title": "cold commentable",
        "comment_status": "pending",
        "priority_score": 40,
        "is_commentable": True,
        "matched_keywords": [],
    })

    assert repo.count({"status": "pending", "min_score": 80}) == 2

    rows = repo.list(
        {"status": "pending", "min_score": "80", "commentable_only": "true"},
        limit=10,
    )
    assert [row["url"] for row in rows] == ["https://x/hot-commentable"]


def test_exclude_revisited_hides_duplicate_scan_targets(tmp_db):
    repo = ViralTargetRepository(tmp_db)

    repo.insert({
        "id": "fresh",
        "platform": "kin",
        "url": "https://x/fresh",
        "title": "fresh target",
        "comment_status": "pending",
        "priority_score": 90,
        "matched_keywords": [],
    })
    repo.insert({
        "id": "dup-1",
        "platform": "cafe",
        "url": "https://x/duplicate",
        "title": "duplicate target",
        "comment_status": "pending",
        "priority_score": 80,
        "matched_keywords": [],
    })
    repo.insert({
        "id": "dup-2",
        "platform": "cafe",
        "url": "https://x/duplicate",
        "title": "duplicate target rediscovered",
        "comment_status": "pending",
        "priority_score": 85,
        "matched_keywords": [],
    })

    assert repo.count({"status": "pending"}) == 2
    assert repo.count({"status": "pending", "exclude_revisited": True}) == 1

    rows = repo.list({"status": "pending", "exclude_revisited": True}, limit=10)
    assert [row["url"] for row in rows] == ["https://x/fresh"]

    rediscovered = repo.list(
        {"status": "pending", "exclude_revisited": True, "min_scan_count": 2},
        limit=10,
    )
    assert [row["url"] for row in rediscovered] == ["https://x/duplicate"]


def test_insert_conflict_recovers_null_scan_count(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    sample = {
        "id": "legacy",
        "platform": "cafe",
        "url": "https://x/legacy",
        "title": "legacy",
        "comment_status": "pending",
        "priority_score": 50,
        "matched_keywords": [],
    }
    assert repo.insert(sample)

    with sqlite3.connect(tmp_db) as conn:
        conn.execute("UPDATE viral_targets SET scan_count = NULL WHERE url = ?", (sample["url"],))
        conn.commit()

    assert repo.insert({**sample, "id": "legacy-again", "priority_score": 55})

    row = repo.get("legacy")
    assert row is not None
    assert row["scan_count"] == 1
    assert row["priority_score"] == 55


def test_update(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    repo.insert({"id": "t1", "platform": "cafe", "url": "https://x/1", "title": "A", "priority_score": 50})
    assert repo.update("t1", {"comment_status": "approved", "priority_score": 100}) is True
    got = repo.get("t1")
    assert got["comment_status"] == "approved"
    assert got["priority_score"] == 100
    # 화이트리스트 외 필드는 무시
    assert repo.update("t1", {"arbitrary_evil": "DROP TABLE"}) is False


def test_bulk_update_status_max_affected(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    for i in range(3):
        repo.insert({
            "id": f"t{i}", "platform": "cafe", "url": f"https://x/{i}",
            "title": f"t{i}", "comment_status": "pending", "priority_score": 0,
        })
    with pytest.raises(ValueError):
        repo.bulk_update_status_by_filter("skipped", {"status": "pending"}, max_affected=1)
    r = repo.bulk_update_status_by_filter("skipped", {"status": "pending"}, max_affected=100)
    assert r["matched"] == 3
    assert r["updated"] == 3
    assert repo.count({"status": "skipped"}) == 3
