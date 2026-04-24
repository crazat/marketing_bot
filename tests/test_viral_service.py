"""viral_service 단위 테스트 — compute_penalty_score + fetch_adaptive_penalties."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

BACKEND = os.path.join(ROOT, "marketing_bot_web", "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

from services.viral_service import compute_penalty_score, fetch_adaptive_penalties


def test_compute_penalty_score_bounds():
    assert compute_penalty_score(0, "domain") == 0
    assert compute_penalty_score(1, "domain") == 3
    assert compute_penalty_score(5, "domain") == 15
    assert compute_penalty_score(20, "domain") == 30  # 캡
    assert compute_penalty_score(20, "author") == 20


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE viral_adaptive_penalties (
            key_type TEXT NOT NULL,
            key_value TEXT NOT NULL,
            skip_count INTEGER DEFAULT 0,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (key_type, key_value)
        )
        """
    )
    for kind, val, n in [
        ("domain", "cafe.naver.com/ad1", 10),
        ("domain", "cafe.naver.com/ad2", 5),
        ("author", "user1", 4),
        ("domain", "cafe.naver.com/ok", 1),  # 임계값 미만
    ]:
        conn.execute(
            "INSERT INTO viral_adaptive_penalties(key_type, key_value, skip_count) VALUES (?, ?, ?)",
            (kind, val, n),
        )
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_fetch_adaptive_penalties_threshold(tmp_db):
    items = fetch_adaptive_penalties(tmp_db, min_skip=3)
    values = {it["key_value"] for it in items}
    assert "cafe.naver.com/ad1" in values
    assert "cafe.naver.com/ad2" in values
    assert "user1" in values
    assert "cafe.naver.com/ok" not in values

    # DESC 정렬 확인
    counts = [it["skip_count"] for it in items]
    assert counts == sorted(counts, reverse=True)


def test_fetch_adaptive_penalties_min_skip_high(tmp_db):
    items = fetch_adaptive_penalties(tmp_db, min_skip=7)
    assert len(items) == 1
    assert items[0]["key_value"] == "cafe.naver.com/ad1"


# [U3] VerificationCache 테스트
def test_verification_cache_set_get():
    from services.viral_service import VerificationCache
    c = VerificationCache(ttl_seconds=60, max_size=10)
    assert c.get("http://x") is None
    c.set("http://x", {"ok": True})
    assert c.get("http://x") == {"ok": True}
    assert c.size() == 1


def test_verification_cache_expires():
    import time
    from services.viral_service import VerificationCache
    c = VerificationCache(ttl_seconds=1)
    c.set("http://x", {"v": 1})
    assert c.get("http://x") == {"v": 1}
    time.sleep(1.1)
    assert c.get("http://x") is None


def test_verification_cache_max_size_eviction():
    from services.viral_service import VerificationCache
    c = VerificationCache(ttl_seconds=60, max_size=5, cleanup_threshold=100)
    for i in range(7):
        c.set(f"http://u{i}", {"i": i})
    # 10을 상한으로 넘으면 80%(=4)개만 남김
    assert c.size() <= 5


def test_verification_cache_clear():
    from services.viral_service import VerificationCache
    c = VerificationCache()
    c.set("a", {"v": 1}); c.set("b", {"v": 2})
    c.clear()
    assert c.size() == 0
