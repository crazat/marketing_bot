from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta

import pytest

import main as backend_main
from utils import json_io
from utils.json_io import atomic_write_json, json_file_lock
from backend_utils.database import _configure_connection
from routers import config
from schemas.response import ApiResponse, ErrorResponse, PaginatedResponse
from services import file_watcher as file_watcher_module
from services.file_watcher import FileWatcher
from services.process_jobs import ProcessJob, ProcessJobManager


def test_keywords_payload_is_trimmed_and_deduplicated() -> None:
    payload = {
        "naver_place": [" alpha ", "", "beta", "alpha"],
        "blog_seo": ["beta", "gamma"],
        "ignored": ["delta"],
    }

    assert config._normalize_keywords_payload(payload) == {
        "naver_place": ["alpha", "beta"],
        "blog_seo": ["gamma"],
    }


def test_keywords_payload_rejects_invalid_shape() -> None:
    with pytest.raises(ValueError):
        config._normalize_keywords_payload({"naver_place": "alpha"})

    with pytest.raises(ValueError):
        config._normalize_keywords_payload({"naver_place": [123]})


def test_process_job_manager_prunes_old_finished_jobs() -> None:
    manager = ProcessJobManager(max_retained_jobs=10)
    now = datetime.now()

    with manager._lock:
        for index in range(12):
            job_id = f"job-{index}"
            manager._jobs[job_id] = ProcessJob(
                job_id=job_id,
                key=f"key-{index}",
                cmd=["python", "-V"],
                cwd=".",
                log_file=f"log-{index}.txt",
                timeout_seconds=10,
                started_at=(now - timedelta(minutes=10 - index)).isoformat(),
                status="completed",
                finished_at=(now - timedelta(minutes=5 - index)).isoformat(),
            )

        manager._prune_finished_locked()

    assert len(manager._jobs) == 10
    assert "job-0" not in manager._jobs
    assert "job-1" not in manager._jobs
    assert "job-11" in manager._jobs


def test_scheduler_state_save_is_atomic_under_lock(monkeypatch, tmp_path) -> None:
    state_file = tmp_path / "scheduler_state.json"
    lock_file = tmp_path / ".scheduler.lock"
    payload = {"08:00": "2026-05-17", "03:00": "2026-05-16"}

    monkeypatch.setattr(backend_main, "SCHEDULER_STATE_FILE", str(state_file))
    monkeypatch.setattr(backend_main, "SCHEDULER_LOCK_FILE", str(lock_file))

    with backend_main.scheduler_state_lock():
        backend_main.save_scheduler_state(payload)

    assert backend_main.load_scheduler_state() == payload
    assert json.loads(state_file.read_text(encoding="utf-8")) == payload
    assert not list(tmp_path.glob(".*.tmp"))


def test_atomic_write_json_preserves_existing_file_on_replace_failure(monkeypatch, tmp_path) -> None:
    config_file = tmp_path / "config.json"
    atomic_write_json(config_file, {"version": 1})

    def fail_replace(src: str, dst: str) -> None:
        raise OSError("replace failed")

    monkeypatch.setattr(json_io.os, "replace", fail_replace)

    with pytest.raises(OSError):
        atomic_write_json(config_file, {"version": 2})

    assert json.loads(config_file.read_text(encoding="utf-8")) == {"version": 1}
    assert not list(tmp_path.glob(".config.json.*.tmp"))


def test_json_file_lock_supports_locked_atomic_update(tmp_path) -> None:
    config_file = tmp_path / "targets.json"

    with json_file_lock(config_file):
        atomic_write_json(config_file, {"targets": ["alpha"]}, acquire_lock=False)

    assert json.loads(config_file.read_text(encoding="utf-8")) == {"targets": ["alpha"]}


def test_sqlite_connection_defaults_include_timeout_and_cache() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        _configure_connection(conn)
        assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 10_000
        assert conn.execute("PRAGMA cache_size").fetchone()[0] == -8_000
    finally:
        conn.close()


def test_response_models_serialize_timestamps_as_json_strings() -> None:
    response_payload = json.loads(ApiResponse.success({"ok": True}).model_dump_json())
    paginated_payload = json.loads(PaginatedResponse.success([{"id": 1}], total=1).model_dump_json())
    error_payload = json.loads(ErrorResponse.create("failed").model_dump_json())

    assert isinstance(response_payload["timestamp"], str)
    assert isinstance(paginated_payload["timestamp"], str)
    assert isinstance(error_payload["timestamp"], str)


class _DummyWebSocketManager:
    def __init__(self) -> None:
        self.logs: list[str] = []
        self.statuses: list[dict] = []

    async def send_pathfinder_log(self, line: str) -> None:
        self.logs.append(line)

    async def send_pathfinder_status(self, status_data: dict) -> None:
        self.statuses.append(status_data)


@pytest.mark.asyncio
async def test_file_watcher_ignores_malformed_status_until_valid(tmp_path) -> None:
    ws_manager = _DummyWebSocketManager()
    watcher = FileWatcher(ws_manager)
    watcher.log_dir = tmp_path
    watcher.log_file = tmp_path / "pathfinder_live.log"
    watcher.status_file = tmp_path / "pathfinder_status.json"

    watcher.status_file.write_text("{bad json", encoding="utf-8")
    await watcher._check_status_file()
    assert ws_manager.statuses == []

    watcher.status_file.write_text('{"status": "running", "message": "ok"}', encoding="utf-8")
    await watcher._check_status_file()
    assert ws_manager.statuses == [{"status": "running", "message": "ok"}]


def test_file_watcher_recent_logs_uses_bounded_tail(tmp_path) -> None:
    ws_manager = _DummyWebSocketManager()
    watcher = FileWatcher(ws_manager)
    watcher.log_file = tmp_path / "pathfinder_live.log"
    watcher.log_file.write_text(
        "\n".join(f"line-{index}" for index in range(1100)),
        encoding="utf-8",
    )

    logs = watcher.get_recent_logs(lines=5000)

    assert len(logs) == 1000
    assert logs[0] == "line-100"
    assert logs[-1] == "line-1099"


@pytest.mark.asyncio
async def test_file_watcher_start_is_idempotent_in_polling_mode(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(file_watcher_module, "HAS_WATCHDOG", False)

    watcher = FileWatcher(_DummyWebSocketManager())
    watcher.log_dir = tmp_path
    watcher.log_file = tmp_path / "pathfinder_live.log"
    watcher.status_file = tmp_path / "pathfinder_status.json"

    await watcher.start()
    first_task = watcher._polling_task
    await watcher.start()

    assert first_task is watcher._polling_task
    await watcher.stop()
    assert watcher._polling_task is None
