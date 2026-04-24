"""lead_service 단위 테스트 — extract_tokens + find_qa_matches."""
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

from services.lead_service import extract_tokens, find_qa_matches


def test_extract_tokens_basic():
    tokens = extract_tokens("청주 다이어트 한약 추천 abc12")
    # 최소 길이 2 이상, 길이 긴 순
    assert "다이어트" in tokens
    assert "abc12" in tokens
    # 중복 제거
    assert len(tokens) == len(set(tokens))
    # 길이 내림차순
    assert all(len(tokens[i]) >= len(tokens[i + 1]) for i in range(len(tokens) - 1))


def test_extract_tokens_empty():
    assert extract_tokens("") == []
    assert extract_tokens("   ") == []


@pytest.fixture
def tmp_db_with_qa():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE qa_repository (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_pattern TEXT,
            question_category TEXT,
            standard_answer TEXT,
            variations TEXT,
            use_count INTEGER DEFAULT 0
        )
        """
    )
    qa_rows = [
        ("청주 다이어트 한약 추천", "diet", "저희 규림한의원이...", "", 10),
        ("교통사고 한의원 입원", "traffic", "교통사고 치료...", "", 5),
        ("여드름 흉터 관리", "skin", "여드름 관리...", "", 3),
        ("광고 마케팅 전략", "unrelated", "...", "", 1),
    ]
    conn.executemany(
        "INSERT INTO qa_repository(question_pattern, question_category, standard_answer, variations, use_count) VALUES (?,?,?,?,?)",
        qa_rows,
    )
    conn.commit()
    yield conn
    conn.close()
    try:
        os.unlink(path)
    except Exception:
        pass


def test_find_qa_matches_relevant(tmp_db_with_qa):
    conn = tmp_db_with_qa
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    matches = find_qa_matches(cur, "청주 다이어트 한약 추천해주세요", max_matches=3)
    assert len(matches) >= 1
    # 첫 매치는 diet 카테고리여야
    assert matches[0]["question_category"] == "diet"


def test_find_qa_matches_empty_text(tmp_db_with_qa):
    conn = tmp_db_with_qa
    cur = conn.cursor()
    assert find_qa_matches(cur, "", max_matches=3) == []


def test_find_qa_matches_irrelevant(tmp_db_with_qa):
    conn = tmp_db_with_qa
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    # 매칭되는 것이 거의 없는 텍스트
    matches = find_qa_matches(cur, "xyz 무관 텍스트", max_matches=3)
    # 광고 패턴 등은 낮은 점수로 제외될 것
    assert all(m["match_score"] >= 20 for m in matches)
