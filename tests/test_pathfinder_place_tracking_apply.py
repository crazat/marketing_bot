import asyncio

from marketing_bot_web.backend.routers import pathfinder as pathfinder_router


class _FakeDatabaseManager:
    def __init__(self):
        self.db_path = "fake.db"
        self.added = []

    def get_tracked_keywords(self):
        return [{"keyword": "청주교통사고한의원"}]

    def add_keyword_to_tracking(self, keyword: str) -> bool:
        self.added.append(keyword)
        return True


def test_clean_place_tracking_keyword_limits_control_chars():
    raw = "  청주\t교통사고\x00한의원  " + ("가" * 120)

    cleaned = pathfinder_router._clean_place_tracking_keyword(raw)

    assert "\x00" not in cleaned
    assert "\t" not in cleaned
    assert len(cleaned) <= 100
    assert cleaned.startswith("청주 교통사고한의원")


def test_apply_place_tracking_candidates_dedupes_and_skips_existing(monkeypatch):
    fake_db = _FakeDatabaseManager()
    monkeypatch.setattr(pathfinder_router, "DatabaseManager", lambda: fake_db)

    request = pathfinder_router.PlaceTrackingCandidateApplyRequest(
        keywords=[
            " 청주 교통사고 한의원 ",
            "청주교통사고한의원",
            "분평동 한의원\x00",
            "오창 한의원",
        ],
        limit=3,
    )

    result = asyncio.run(pathfinder_router.apply_place_tracking_candidates(request))

    assert result["success"] is True
    assert result["requested_count"] == 3
    assert result["added_keywords"] == ["분평동 한의원", "오창 한의원"]
    assert result["skipped_keywords"] == [
        {"keyword": "청주 교통사고 한의원", "reason": "already_tracked"}
    ]
    assert fake_db.added == ["분평동 한의원", "오창 한의원"]
