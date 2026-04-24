"""hud_service 단위 테스트."""
from __future__ import annotations

import os
import sys
import tempfile
import time

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(ROOT, "marketing_bot_web", "backend")
for p in (ROOT, BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from services.hud_service import convert_to_kst, parse_scan_progress_from_log, TTLCache


def test_convert_to_kst_basic():
    out = convert_to_kst("2026-04-24 00:00:00")
    assert out == "2026-04-24 09:00:00"


def test_convert_to_kst_handles_bad_input():
    assert convert_to_kst(None) is None
    # 파싱 실패 시 원본 반환 (fallback)
    assert convert_to_kst("invalid") == "invalid"


def test_convert_to_kst_with_fractional():
    # SQLite 부동소수점 부분 제거
    out = convert_to_kst("2026-04-24 00:00:00.123456")
    assert out == "2026-04-24 09:00:00"


def test_parse_scan_progress_idle_when_no_log(tmp_path):
    result = parse_scan_progress_from_log("pathfinder", str(tmp_path))
    assert result["status"] == "idle"
    assert result["progress"] == 0


def test_parse_scan_progress_pathfinder_phase(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "pathfinder_live.log"
    log_file.write_text("some noise\nPHASE 3 진행 중\n", encoding="utf-8")
    result = parse_scan_progress_from_log("pathfinder", str(tmp_path))
    assert result["status"] == "running"
    assert result["progress"] == 60


def test_parse_scan_progress_completed(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "pathfinder_live.log").write_text("PHASE 2\n키워드 수집 완료\n", encoding="utf-8")
    r = parse_scan_progress_from_log("pathfinder", str(tmp_path))
    assert r["status"] == "completed"
    assert r["progress"] == 100


def test_ttl_cache_basic():
    c = TTLCache(ttl_seconds=10)
    assert c.get("x") is None
    c.set("x", 42)
    assert c.get("x") == 42
    c.invalidate("x")
    assert c.get("x") is None


def test_ttl_cache_expiry():
    c = TTLCache(ttl_seconds=1)
    c.set("k", "v")
    assert c.get("k") == "v"
    time.sleep(1.05)
    assert c.get("k") is None


def test_ttl_cache_clear():
    c = TTLCache(ttl_seconds=60)
    c.set("a", 1); c.set("b", 2)
    c.clear()
    assert c.get("a") is None and c.get("b") is None
