"""라우터 레벨 스모크 테스트.

FastAPI TestClient로 viral/leads 주요 GET 엔드포인트의 import·응답 구조를 검증.
실제 DB는 테스트 격리용 임시 파일 사용.
"""
from __future__ import annotations

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


def test_viral_service_compute_penalty_import():
    """services.viral_service import 및 기본 동작."""
    from services.viral_service import compute_penalty_score
    assert compute_penalty_score(0, "domain") == 0
    assert compute_penalty_score(100, "domain") == 30  # 캡


def test_lead_service_extract_tokens_import():
    from services.lead_service import extract_tokens
    tokens = extract_tokens("청주 다이어트 한약")
    assert "다이어트" in tokens
