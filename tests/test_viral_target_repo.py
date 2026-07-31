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
            canonical_url TEXT,
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


def test_scan_batch_run_filter_uses_source_scan_run_id_and_keeps_status(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("ALTER TABLE viral_targets ADD COLUMN source_scan_run_id INTEGER DEFAULT 0")
        conn.commit()

    repo = ViralTargetRepository(tmp_db)
    assert repo.insert({
        "id": "old-rediscovered",
        "platform": "kin",
        "url": "https://x/old-rediscovered",
        "title": "old rediscovered",
        "comment_status": "pending",
        "priority_score": 90,
        "matched_keywords": [],
        "source_scan_run_id": 75,
    })
    assert repo.insert({
        "id": "old-rediscovered-skipped",
        "platform": "kin",
        "url": "https://x/old-rediscovered-skipped",
        "title": "old rediscovered skipped",
        "comment_status": "skipped",
        "priority_score": 95,
        "matched_keywords": [],
        "source_scan_run_id": 75,
    })
    assert repo.insert({
        "id": "other-run",
        "platform": "kin",
        "url": "https://x/other-run",
        "title": "other run",
        "comment_status": "pending",
        "priority_score": 100,
        "matched_keywords": [],
        "source_scan_run_id": 74,
    })
    assert repo.insert({
        "id": "today-rescanned",
        "platform": "blog",
        "url": "https://x/today-rescanned",
        "title": "today rescanned",
        "comment_status": "pending",
        "priority_score": 80,
        "matched_keywords": [],
        "source_scan_run_id": 76,
    })

    with sqlite3.connect(tmp_db) as conn:
        conn.execute(
            """
            UPDATE viral_targets
               SET discovered_at = '2026-06-01 10:00:00',
                   last_scanned_at = '2026-06-15 16:10:00'
             WHERE id = 'old-rediscovered'
            """
        )
        conn.execute(
            """
            UPDATE viral_targets
               SET discovered_at = '2026-06-01 10:00:00',
                   last_scanned_at = datetime('now', 'localtime')
             WHERE id = 'today-rescanned'
            """
        )
        conn.commit()

    rows = repo.list({"status": "pending", "scan_batch": "run:75"}, limit=10)
    hour_rows = repo.list({"status": "pending", "scan_batch": "2026-06-15 16"}, limit=10)
    today_rows = repo.list({"status": "pending", "date_filter": "오늘"}, limit=10)

    assert [row["id"] for row in rows] == ["old-rediscovered"]
    assert [row["id"] for row in hour_rows] == ["old-rediscovered"]
    assert "today-rescanned" in {row["id"] for row in today_rows}


def test_insert_uses_canonical_url_for_naver_duplicates(tmp_db):
    repo = ViralTargetRepository(tmp_db)
    first_url = "https://kin.naver.com/qna/detail.naver?docId=123&qb=old"
    second_url = "https://kin.naver.com/qna/detail.naver?docId=123&qb=new"

    assert repo.insert({
        "id": "kin-old",
        "platform": "kin",
        "url": first_url,
        "title": "old",
        "comment_status": "pending",
        "priority_score": 50,
        "matched_keywords": [],
    })
    assert repo.insert({
        "id": "kin-new",
        "platform": "kin",
        "url": second_url,
        "title": "new",
        "comment_status": "pending",
        "priority_score": 55,
        "matched_keywords": [],
    })

    assert repo.count() == 1
    row = repo.get("kin-old")
    assert row is not None
    assert row["scan_count"] == 2
    assert row["canonical_url"] == "https://kin.naver.com/qna/detail.naver?docId=123"


def test_insert_preserves_pathfinder_lineage_when_columns_exist(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        for col, ctype in [
            ("matched_keyword", "TEXT"),
            ("source_scan_run_id", "INTEGER DEFAULT 0"),
            ("matched_keyword_grade", "TEXT"),
            ("matched_keyword_kei", "REAL DEFAULT 0"),
            ("matched_keyword_priority", "REAL DEFAULT 0"),
            ("matched_keyword_category", "TEXT"),
        ]:
            conn.execute(f"ALTER TABLE viral_targets ADD COLUMN {col} {ctype}")
        conn.commit()

    repo = ViralTargetRepository(tmp_db)
    assert repo.insert({
        "id": "lineage-old",
        "platform": "kin",
        "url": "https://x/lineage",
        "title": "lineage",
        "matched_keywords": ["청주 여드름"],
        "source_scan_run_id": 10,
        "matched_keyword_grade": "B",
        "matched_keyword_kei": 3.2,
        "matched_keyword_priority": 71.0,
        "matched_keyword_category": "피부/여드름",
    })
    assert repo.insert({
        "id": "lineage-new",
        "platform": "kin",
        "url": "https://x/lineage",
        "title": "lineage rediscovered",
        "matched_keywords": ["청주 여드름 한의원"],
        "source_scan_run_id": 11,
        "matched_keyword_grade": "A",
        "matched_keyword_kei": 5.1,
        "matched_keyword_priority": 88.0,
        "matched_keyword_category": "피부/여드름",
    })

    row = repo.get("lineage-old")

    assert row is not None
    assert row["scan_count"] == 2
    assert row["matched_keyword"] == "청주 여드름 한의원"
    assert row["source_scan_run_id"] == 11
    assert row["matched_keyword_grade"] == "A"
    assert row["matched_keyword_kei"] == 5.1
    assert row["matched_keyword_priority"] == 88.0
    assert row["matched_keyword_category"] == "피부/여드름"


def test_insert_persists_viral_efficiency_breakdown_and_filters(tmp_db):
    with sqlite3.connect(tmp_db) as conn:
        for col, ctype in [
            ("exposure_score", "REAL DEFAULT 0"),
            ("workability_score", "REAL DEFAULT 0"),
            ("conversion_fit_score", "REAL DEFAULT 0"),
            ("score_breakdown", "TEXT DEFAULT '{}'"),
            ("search_sort", "TEXT"),
            ("search_rank", "INTEGER DEFAULT 0"),
            ("sort_appearances", "TEXT DEFAULT '[]'"),
        ]:
            conn.execute(f"ALTER TABLE viral_targets ADD COLUMN {col} {ctype}")
        conn.commit()

    repo = ViralTargetRepository(tmp_db)
    assert repo.insert({
        "id": "eff-high",
        "platform": "kin",
        "url": "https://x/eff-high",
        "title": "scar clinic fit",
        "comment_status": "pending",
        "priority_score": 82,
        "matched_keywords": ["cheongju scar clinic"],
        "exposure_score": 100,
        "workability_score": 95,
        "conversion_fit_score": 88,
        "score_breakdown": {
            "clinic_treatment_fit_score": 86,
            "worksite_efficiency_score": 91,
        },
        "search_sort": "date",
        "search_rank": 2,
        "sort_appearances": ["date", "sim"],
    })
    assert repo.insert({
        "id": "eff-low",
        "platform": "blog",
        "url": "https://x/eff-low",
        "title": "low fit",
        "comment_status": "pending",
        "priority_score": 120,
        "matched_keywords": ["home care"],
        "score_breakdown": {
            "clinic_treatment_fit_score": 28,
            "worksite_efficiency_score": 35,
        },
    })

    high = repo.get("eff-high")
    assert high is not None
    assert high["score_breakdown"]["clinic_treatment_fit_score"] == 86
    assert high["sort_appearances"] == ["date", "sim"]

    filters = {"min_clinic_fit": 70, "min_worksite_efficiency": 70}
    assert repo.count(filters) == 1
    rows = repo.list(filters, sort="worksite_efficiency", limit=10)
    assert [row["id"] for row in rows] == ["eff-high"]


def test_default_priority_sort_breaks_cap_ties_by_strategic_fit(tmp_db):
    """priority가 동점(150 캡)일 때 worksite/clinic_fit 높은 시그니처 축이 먼저 온다.

    캡 압축으로 큐 상단이 변별력을 잃을 때, 고볼륨 commodity(다이어트, 저 clinic_fit)가
    시그니처 축(흉터/안면비대칭, 고 clinic_fit)을 밀어내던 문제 회귀 방지.
    """
    with sqlite3.connect(tmp_db) as conn:
        conn.execute("ALTER TABLE viral_targets ADD COLUMN score_breakdown TEXT DEFAULT '{}'")
        conn.commit()

    repo = ViralTargetRepository(tmp_db)
    # 모두 priority 150(캡) 동점. discovered_at은 commodity가 더 최근(과거 recency 동점
    # 깨기였다면 commodity가 상단을 차지했을 상황).
    repo.insert({
        "id": "commodity-diet", "platform": "kin", "url": "https://x/diet",
        "title": "청주 다이어트 한약", "comment_status": "pending", "priority_score": 150,
        "category": "다이어트", "discovered_at": "2026-06-13 10:00:00",
        "matched_keywords": ["청주 다이어트"],
        "score_breakdown": {"clinic_treatment_fit_score": 35, "worksite_efficiency_score": 44},
    })
    repo.insert({
        "id": "signature-scar", "platform": "kin", "url": "https://x/scar",
        "title": "청주 여드름흉터 새살침", "comment_status": "pending", "priority_score": 150,
        "category": "흉터/여드름흉터", "discovered_at": "2026-06-01 10:00:00",
        "matched_keywords": ["청주 여드름흉터"],
        "score_breakdown": {"clinic_treatment_fit_score": 88, "worksite_efficiency_score": 95},
    })
    repo.insert({
        "id": "signature-asym", "platform": "cafe", "url": "https://x/asym",
        "title": "청주 안면비대칭 교정", "comment_status": "pending", "priority_score": 150,
        "category": "안면비대칭", "discovered_at": "2026-06-02 10:00:00",
        "matched_keywords": ["청주 안면비대칭"],
        "score_breakdown": {"clinic_treatment_fit_score": 82, "worksite_efficiency_score": 90},
    })

    rows = repo.list({"comment_status": "pending"}, sort="priority", limit=10)
    order = [r["id"] for r in rows]
    # 시그니처 축이 commodity보다 먼저, 그 안에서 worksite 높은 흉터가 안면비대칭보다 먼저
    assert order.index("signature-scar") < order.index("commodity-diet")
    assert order.index("signature-asym") < order.index("commodity-diet")
    assert order.index("signature-scar") < order.index("signature-asym")


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
