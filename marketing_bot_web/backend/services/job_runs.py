"""
Job Run Tracking + 의존성 게이트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

기존 schedule==1.2.2 cron 잡 위에 얇게 쌓는 신뢰성 레이어.

기능:
- @track_run("job_name") 데코레이터: 시작/종료/예외/timeout을 job_runs 테이블에 기록
- requires_recent("upstream_job", hours=N): 의존 잡이 N시간 내 성공했어야만 진행
- /api/jobs/runs API에서 조회 가능 → Dashboard Chronos Timeline에 색상 표시

사용:
    from services.job_runs import track_run, requires_recent

    @track_run("place_sniper", timeout_seconds=1800)
    def job_sniper():
        # 스캔 로직
        ...

    @track_run("intelligence_synthesizer")
    def job_intel():
        if not requires_recent("place_sniper", hours=24):
            return {"skipped": "place_sniper not recent"}
        # 정상 실행
        ...
"""

from __future__ import annotations

import functools
import logging
import os
import sqlite3
import threading
import time
import traceback
from contextlib import contextmanager
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_lock = threading.Lock()


def _db_path() -> str:
    here = os.path.dirname(os.path.abspath(__file__))
    # services → backend → marketing_bot_web → root
    root = os.path.dirname(os.path.dirname(os.path.dirname(here)))
    return os.path.join(root, "db", "marketing_data.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def ensure_table():
    """job_runs 테이블 생성 (db_init.py에서 호출)."""
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS job_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_name TEXT NOT NULL,
                started_at TIMESTAMP NOT NULL,
                ended_at TIMESTAMP,
                duration_seconds REAL,
                status TEXT NOT NULL,            -- running | success | failed | timeout | skipped
                exit_code INTEGER,
                error_msg TEXT,
                stdout_tail TEXT,
                metadata_json TEXT
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_runs_job_started
            ON job_runs(job_name, started_at DESC)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_job_runs_started
            ON job_runs(started_at DESC)
        """)
        conn.commit()
    finally:
        if conn:
            conn.close()


def _record_start(job_name: str, metadata: Optional[Dict[str, Any]] = None) -> Optional[int]:
    """잡 시작 기록 → run_id 반환."""
    conn = None
    try:
        ensure_table()
        conn = _connect()
        cur = conn.cursor()
        import json as _json
        cur.execute("""
            INSERT INTO job_runs (job_name, started_at, status, metadata_json)
            VALUES (?, ?, 'running', ?)
        """, (
            job_name,
            datetime.utcnow().isoformat(timespec="seconds"),
            _json.dumps(metadata or {}, ensure_ascii=False),
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.warning(f"[job_runs] _record_start 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


def _record_end(
    run_id: int,
    status: str,
    error_msg: Optional[str] = None,
    duration: Optional[float] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    if run_id is None:
        return
    conn = None
    try:
        conn = _connect()
        cur = conn.cursor()
        import json as _json
        cur.execute("""
            UPDATE job_runs
            SET ended_at = ?, status = ?, error_msg = ?, duration_seconds = ?,
                metadata_json = COALESCE(?, metadata_json)
            WHERE id = ?
        """, (
            datetime.utcnow().isoformat(timespec="seconds"),
            status,
            (error_msg or "")[:1000] if error_msg else None,
            duration,
            _json.dumps(metadata, ensure_ascii=False) if metadata else None,
            run_id,
        ))
        conn.commit()
    except Exception as e:
        logger.warning(f"[job_runs] _record_end 실패: {e}")
    finally:
        if conn:
            conn.close()


def track_run(
    job_name: str,
    *,
    timeout_seconds: Optional[int] = None,
    retries: int = 0,
    retry_backoff: float = 30.0,
):
    """잡 함수에 데코레이터로 적용. 시작/종료 자동 기록 + 옵션 retry.

    timeout_seconds: 워치독은 별도 thread로 구현 안 됨 — 기록만 위해.
                     실제 강제종료는 호출자 (예: subprocess wrapper)가 책임.
    retries: 0 (default) = 재시도 없음
    retry_backoff: 재시도 사이 대기 (초)
    """
    def deco(fn: Callable):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            attempt = 0
            last_err: Optional[BaseException] = None
            while attempt <= retries:
                run_id = _record_start(job_name, metadata={"attempt": attempt + 1})
                start_ts = time.time()
                try:
                    result = fn(*args, **kwargs)
                    duration = time.time() - start_ts
                    if isinstance(result, dict) and result.get("skipped"):
                        _record_end(run_id, "skipped", duration=duration, metadata=result)
                    else:
                        _record_end(run_id, "success", duration=duration,
                                    metadata={"result": str(result)[:200]} if result else None)
                    return result
                except Exception as e:
                    duration = time.time() - start_ts
                    last_err = e
                    err_msg = f"{type(e).__name__}: {e}"
                    _record_end(run_id, "failed", error_msg=err_msg, duration=duration,
                                metadata={"traceback": traceback.format_exc()[-500:]})
                    logger.error(f"[job_runs] {job_name} attempt {attempt+1}/{retries+1} 실패: {err_msg}")
                    attempt += 1
                    if attempt <= retries:
                        wait = retry_backoff * attempt
                        logger.info(f"[job_runs] {job_name} 재시도 {wait}s 대기")
                        time.sleep(wait)
            # 모든 시도 실패
            if last_err:
                raise last_err
        return wrapper
    return deco


def requires_recent(upstream_job: str, hours: int = 24) -> bool:
    """upstream_job이 hours 내 성공한 적 있는지 확인.

    False면 이 잡을 skip 해야 함.
    """
    conn = None
    try:
        ensure_table()
        conn = _connect()
        cur = conn.cursor()
        cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat(timespec="seconds")
        cur.execute("""
            SELECT COUNT(*) FROM job_runs
            WHERE job_name = ? AND status = 'success' AND started_at >= ?
        """, (upstream_job, cutoff))
        n = cur.fetchone()[0]
        if n == 0:
            logger.warning(f"[job_runs] {upstream_job} 최근 {hours}h 내 성공 기록 없음 — 의존 잡 skip 권장")
            return False
        return True
    except Exception as e:
        logger.warning(f"[job_runs] requires_recent 실패 (안전상 True 반환): {e}")
        return True  # 의존성 체크 실패는 잡 자체 진행
    finally:
        if conn:
            conn.close()


def recent_runs(limit: int = 100, job_name: Optional[str] = None) -> list:
    """최근 실행 기록 (API/Dashboard용)."""
    conn = None
    try:
        ensure_table()
        conn = _connect()
        cur = conn.cursor()
        if job_name:
            cur.execute("""
                SELECT * FROM job_runs WHERE job_name = ?
                ORDER BY started_at DESC LIMIT ?
            """, (job_name, limit))
        else:
            cur.execute("""
                SELECT * FROM job_runs ORDER BY started_at DESC LIMIT ?
            """, (limit,))
        return [dict(r) for r in cur.fetchall()]
    finally:
        if conn:
            conn.close()


def job_summary() -> Dict[str, Dict[str, Any]]:
    """잡별 요약 (마지막 실행 시각·상태·평균 소요시간) — Dashboard용."""
    conn = None
    try:
        ensure_table()
        conn = _connect()
        cur = conn.cursor()
        cur.execute("""
            SELECT job_name,
                   MAX(started_at) as last_started,
                   AVG(duration_seconds) as avg_duration,
                   SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as n_success,
                   SUM(CASE WHEN status='failed' THEN 1 ELSE 0 END) as n_failed
            FROM job_runs
            WHERE started_at >= datetime('now', '-7 days')
            GROUP BY job_name
        """)
        out = {}
        for r in cur.fetchall():
            row = dict(r)
            # 마지막 실행 상태
            cur.execute("""
                SELECT status, error_msg FROM job_runs
                WHERE job_name = ? ORDER BY started_at DESC LIMIT 1
            """, (row["job_name"],))
            last = cur.fetchone()
            row["last_status"] = last["status"] if last else None
            row["last_error"] = last["error_msg"] if last else None
            out[row["job_name"]] = row
        return out
    finally:
        if conn:
            conn.close()


# CLI 테스트
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    @track_run("test_job_success")
    def good_job():
        time.sleep(0.5)
        return {"ok": True}

    @track_run("test_job_failure", retries=1, retry_backoff=0.1)
    def bad_job():
        raise ValueError("simulated")

    @track_run("test_job_dependent")
    def dependent_job():
        if not requires_recent("test_job_success", hours=1):
            return {"skipped": "no upstream success"}
        return {"executed": True}

    good_job()
    try: bad_job()
    except: pass
    dependent_job()
    print("\n=== Job Summary ===")
    for k, v in job_summary().items():
        print(k, v)
