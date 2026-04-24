"""KeywordRepository 단위 테스트."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from repositories.keyword_repo import KeywordRepository


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE keyword_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT, volume INTEGER, search_volume INTEGER,
            category TEXT, grade TEXT, priority_v3 REAL,
            status TEXT DEFAULT 'active',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE rank_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT, rank INTEGER, target_name TEXT,
            checked_at TIMESTAMP, date TEXT, status TEXT,
            device_type TEXT, note TEXT
        );
        """
    )
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def _insert_kw(path, keyword, grade="B", priority=50.0, search_volume=100):
    conn = sqlite3.connect(path)
    conn.execute(
        "INSERT INTO keyword_insights(keyword, grade, priority_v3, search_volume) VALUES (?,?,?,?)",
        (keyword, grade, priority, search_volume),
    )
    conn.commit()
    conn.close()


def test_count_and_grade_filter(tmp_db):
    for g, n in [("S", 2), ("A", 3), ("B", 10), ("C", 5)]:
        for i in range(n):
            _insert_kw(tmp_db, f"{g}-kw{i}", grade=g, priority=n * 10)
    repo = KeywordRepository(tmp_db)
    assert repo.count() == 20
    assert repo.count({"grade": "S"}) == 2
    assert repo.count({"grades": ["S", "A"]}) == 5
    assert repo.count({"min_search_volume": 50}) == 20


def test_list_sort(tmp_db):
    _insert_kw(tmp_db, "low", priority=10)
    _insert_kw(tmp_db, "mid", priority=50)
    _insert_kw(tmp_db, "top", priority=100)
    repo = KeywordRepository(tmp_db)
    rows = repo.list(sort="priority_v3", limit=5)
    assert rows[0]["keyword"] == "top"
    assert rows[-1]["keyword"] == "low"


def test_group_by_grade(tmp_db):
    _insert_kw(tmp_db, "a1", grade="A")
    _insert_kw(tmp_db, "a2", grade="A")
    _insert_kw(tmp_db, "b1", grade="B")
    repo = KeywordRepository(tmp_db)
    g = repo.group_by_grade()
    assert g["A"] == 2
    assert g["B"] == 1


def test_rank_history(tmp_db):
    repo = KeywordRepository(tmp_db)
    repo.record_rank("청주 한의원", 5, target_name="우리", device_type="mobile")
    repo.record_rank("청주 한의원", 3, target_name="우리", device_type="mobile")
    latest = repo.latest_rank("청주 한의원", device_type="mobile")
    assert latest["rank"] == 3
    hist = repo.rank_history("청주 한의원", days=1, device_type="mobile")
    assert len(hist) == 2


def test_sort_whitelist_injection_defense(tmp_db):
    _insert_kw(tmp_db, "x", priority=10)
    repo = KeywordRepository(tmp_db)
    # 화이트리스트에 없는 sort 키는 기본값(priority_v3)으로 대체
    rows = repo.list(sort="evil; DROP TABLE keyword_insights")
    assert len(rows) >= 1
