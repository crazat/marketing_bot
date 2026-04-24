"""LeadRepository 단위 테스트."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from repositories.lead_repo import LeadRepository


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE mentions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_name TEXT,
            keyword TEXT,
            source TEXT,
            title TEXT,
            content TEXT,
            url TEXT,
            date_posted TEXT,
            scraped_at TIMESTAMP,
            status TEXT DEFAULT 'pending',
            score INTEGER,
            grade TEXT,
            first_response_at TEXT,
            response_time_hours REAL
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


def _insert(conn_path, **kw):
    conn = sqlite3.connect(conn_path)
    cur = conn.cursor()
    cols = list(kw.keys())
    placeholders = ",".join(["?"] * len(cols))
    cur.execute(
        f"INSERT INTO mentions ({','.join(cols)}) VALUES ({placeholders})",
        list(kw.values()),
    )
    conn.commit()
    lead_id = cur.lastrowid
    conn.close()
    return lead_id


def test_count_and_filter(tmp_db):
    for i in range(5):
        _insert(
            tmp_db,
            keyword=f"kw{i}",
            source="naver" if i % 2 == 0 else "kin",
            title=f"title {i}",
            content="body",
            scraped_at=datetime.now().isoformat(),
            status="pending" if i < 3 else "approved",
            score=i * 20,
        )
    repo = LeadRepository(tmp_db)
    assert repo.count() == 5
    assert repo.count({"status": "pending"}) == 3
    assert repo.count({"source": "naver"}) == 3
    assert repo.count({"min_score": 40}) == 3


def test_list_sort(tmp_db):
    for i in range(3):
        _insert(tmp_db, source="naver", title=f"t{i}", scraped_at=datetime.now().isoformat(), score=i * 10)
    repo = LeadRepository(tmp_db)
    rows = repo.list(sort="score", limit=5)
    assert rows[0]["score"] >= rows[-1]["score"]


def test_update_and_whitelist(tmp_db):
    lid = _insert(tmp_db, source="naver", title="x", scraped_at=datetime.now().isoformat(), status="pending")
    repo = LeadRepository(tmp_db)
    assert repo.update(lid, {"status": "approved", "score": 80}) is True
    got = repo.get(lid)
    assert got["status"] == "approved"
    assert got["score"] == 80
    # 허용 안 된 컬럼
    assert repo.update(lid, {"arbitrary": "danger"}) is False


def test_bulk_update_status(tmp_db):
    ids = [
        _insert(tmp_db, source="naver", scraped_at=datetime.now().isoformat(), status="pending")
        for _ in range(4)
    ]
    repo = LeadRepository(tmp_db)
    n = repo.bulk_update_status(ids, "approved")
    assert n == 4
    assert repo.count({"status": "approved"}) == 4


def test_record_response_computes_hours(tmp_db):
    past = (datetime.now() - timedelta(hours=3)).isoformat()
    lid = _insert(tmp_db, source="naver", scraped_at=past, status="pending")
    repo = LeadRepository(tmp_db)
    assert repo.record_response(lid, response_time_iso=datetime.now().isoformat()) is True
    got = repo.get(lid)
    assert got["response_time_hours"] is not None
    assert 2.9 <= got["response_time_hours"] <= 3.1


def test_group_by_status(tmp_db):
    for st in ["pending", "pending", "approved", "skipped"]:
        _insert(tmp_db, source="naver", scraped_at=datetime.now().isoformat(), status=st)
    repo = LeadRepository(tmp_db)
    g = repo.group_by_status()
    assert g["pending"] == 2
    assert g["approved"] == 1
    assert g["skipped"] == 1


def test_dynamic_columns(tmp_db):
    """[T4] has_column / columns() 동작 검증."""
    repo = LeadRepository(tmp_db)
    cols = repo.columns()
    assert "id" in cols
    assert "status" in cols
    assert "score" in cols
    assert "non_existent_column" not in cols
    # has_column 래퍼
    assert repo.has_column("status") is True
    assert repo.has_column("nonexistent") is False
    # 캐시 동작: 두 번째 호출은 같은 set
    cols2 = repo.columns()
    assert cols is cols2  # 동일 객체 (캐시)
