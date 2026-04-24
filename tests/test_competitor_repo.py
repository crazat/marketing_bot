"""CompetitorRepository 단위 테스트."""
from __future__ import annotations

import os
import sqlite3
import sys
import tempfile

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from repositories.competitor_repo import CompetitorRepository


@pytest.fixture
def tmp_db():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE competitor_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT,
            source TEXT,
            content TEXT,
            sentiment TEXT DEFAULT 'neutral',
            keywords TEXT DEFAULT '[]',
            review_date TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE competitor_weaknesses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT,
            weakness_type TEXT,
            description TEXT,
            severity TEXT DEFAULT 'Medium',
            source_url TEXT,
            opportunity_keywords TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE competitor_rankings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT NOT NULL,
            keyword TEXT NOT NULL,
            rank INTEGER DEFAULT 0,
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            scanned_date TEXT DEFAULT (DATE('now')),
            note TEXT,
            UNIQUE(competitor_name, keyword, scanned_date)
        );
        """
    )
    # 샘플 리뷰
    for i in range(6):
        conn.execute(
            "INSERT INTO competitor_reviews(competitor_name, source, content, sentiment) VALUES (?, ?, ?, ?)",
            ("자연과한의원" if i % 2 == 0 else "경희한의원", "naver", f"review {i}",
             "positive" if i < 3 else ("negative" if i < 5 else "neutral")),
        )
    conn.commit()
    conn.close()
    yield path
    try:
        os.unlink(path)
    except Exception:
        pass


def test_list_reviews_and_count(tmp_db):
    repo = CompetitorRepository(tmp_db)
    assert repo.count_reviews() == 6
    assert repo.count_reviews(competitor_name="자연과한의원") == 3
    assert repo.count_reviews(sentiment="positive") == 3


def test_sentiment_breakdown(tmp_db):
    repo = CompetitorRepository(tmp_db)
    b = repo.sentiment_breakdown()
    assert b.get("positive") == 3
    assert b.get("negative") == 2
    assert b.get("neutral") == 1


def test_weaknesses_insert_list(tmp_db):
    repo = CompetitorRepository(tmp_db)
    repo.insert_weakness("자연과한의원", "가격", "비쌈", severity="High")
    repo.insert_weakness("자연과한의원", "대기시간", "길다", severity="Low")
    repo.insert_weakness("경희한의원", "서비스", "불친절", severity="Medium")
    all_ = repo.list_weaknesses()
    assert len(all_) == 3
    high_only = repo.list_weaknesses(min_severity="High")
    assert len(high_only) == 1
    assert high_only[0]["weakness_type"] == "가격"
    mid_up = repo.list_weaknesses(min_severity="Medium")
    assert len(mid_up) == 2


def test_ranking_upsert_and_latest(tmp_db):
    repo = CompetitorRepository(tmp_db)
    repo.upsert_ranking("자연과한의원", "청주 한의원", rank=3, scanned_date="2026-04-23")
    repo.upsert_ranking("자연과한의원", "청주 한의원", rank=2, scanned_date="2026-04-24")
    assert repo.latest_rank("자연과한의원", "청주 한의원") == 2
    hist = repo.rank_history("자연과한의원", "청주 한의원", days=7)
    assert len(hist) == 2
    assert hist[0]["rank"] == 3
    assert hist[1]["rank"] == 2
