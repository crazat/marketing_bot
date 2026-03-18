"""
pytest 공통 픽스처 및 설정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 2] 테스트 인프라
- 공통 픽스처 정의
- 모킹 헬퍼
- 테스트 데이터베이스 설정
"""

import os
import sys
import sqlite3
import tempfile
from pathlib import Path
from typing import Generator
import pytest
from fastapi.testclient import TestClient

# 백엔드 모듈 경로 추가
backend_path = Path(__file__).parent.parent
project_root = backend_path.parent.parent  # marketing_bot
sys.path.insert(0, str(backend_path))
sys.path.insert(0, str(project_root))

from main import app


# ========== 앱 픽스처 ==========

@pytest.fixture(scope="session")
def test_client() -> Generator[TestClient, None, None]:
    """FastAPI 테스트 클라이언트"""
    with TestClient(app) as client:
        yield client


@pytest.fixture(scope="function")
def client() -> Generator[TestClient, None, None]:
    """함수별 테스트 클라이언트 (상태 초기화 필요 시)"""
    with TestClient(app) as client:
        yield client


# ========== 데이터베이스 픽스처 ==========

@pytest.fixture(scope="function")
def temp_db() -> Generator[str, None, None]:
    """임시 테스트용 데이터베이스"""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 기본 테이블 생성
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS keyword_insights (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            grade TEXT DEFAULT 'C',
            search_volume INTEGER DEFAULT 0,
            difficulty INTEGER DEFAULT 50,
            category TEXT DEFAULT '기타',
            opportunity INTEGER DEFAULT 0,
            kei REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS viral_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            platform TEXT NOT NULL,
            url TEXT,
            title TEXT,
            author TEXT,
            content TEXT,
            priority_score INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            matched_keyword TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS rank_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            rank INTEGER,
            status TEXT DEFAULT 'pending',
            scanned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    conn.commit()
    conn.close()

    yield db_path

    # 정리
    try:
        os.unlink(db_path)
    except Exception:
        pass


# ========== 모킹 픽스처 ==========

@pytest.fixture
def mock_keywords() -> list:
    """테스트용 키워드 데이터"""
    return [
        {
            "keyword": "청주 한의원",
            "grade": "S",
            "search_volume": 5000,
            "difficulty": 30,
            "category": "한의원",
            "opportunity": 85,
            "kei": 166.67
        },
        {
            "keyword": "청주 다이어트",
            "grade": "A",
            "search_volume": 3000,
            "difficulty": 40,
            "category": "다이어트",
            "opportunity": 70,
            "kei": 75.0
        },
        {
            "keyword": "청주 교통사고 한의원",
            "grade": "B",
            "search_volume": 800,
            "difficulty": 20,
            "category": "한의원",
            "opportunity": 60,
            "kei": 40.0
        }
    ]


@pytest.fixture
def mock_viral_targets() -> list:
    """테스트용 바이럴 타겟 데이터"""
    return [
        {
            "id": 1,
            "platform": "cafe",
            "title": "청주 한의원 추천해주세요",
            "content": "청주에서 좋은 한의원 찾고 있어요",
            "priority_score": 85,
            "status": "new",
            "matched_keyword": "청주 한의원"
        },
        {
            "id": 2,
            "platform": "blog",
            "title": "다이어트 한약 후기",
            "content": "한의원에서 다이어트 한약 받았는데 효과 좋네요",
            "priority_score": 65,
            "status": "processing",
            "matched_keyword": "다이어트 한약"
        }
    ]


# ========== 유틸리티 픽스처 ==========

@pytest.fixture
def sample_text_for_scoring() -> dict:
    """PriorityScorer 테스트용 텍스트 샘플"""
    return {
        "question": "청주에서 한의원 추천해주세요. 다이어트 하려고 하는데 좋은 곳 알려주세요.",
        "hot_lead": "청주 한의원 예약하려고 합니다. 가격이 얼마인가요?",
        "general": "오늘 날씨가 좋네요.",
        "competitor": "OO한의원 다녀왔는데 별로였어요. 다른 곳 추천해주세요."
    }


# ========== 스킵 마커 ==========

def pytest_configure(config):
    """pytest 설정 훅"""
    config.addinivalue_line("markers", "slow: 느린 테스트")
    config.addinivalue_line("markers", "integration: 통합 테스트")
    config.addinivalue_line("markers", "unit: 단위 테스트")
    config.addinivalue_line("markers", "api: API 테스트")
