from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from routers import config
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
