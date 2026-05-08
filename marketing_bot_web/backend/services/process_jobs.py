"""Small process job manager for long-running local scripts."""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


class ProcessAlreadyRunning(RuntimeError):
    def __init__(self, key: str, job: "ProcessJob"):
        super().__init__(f"{key} is already running")
        self.key = key
        self.job = job

    @property
    def job_snapshot(self) -> Dict[str, Any]:
        return self.job.snapshot()


@dataclass
class ProcessJob:
    job_id: str
    key: str
    cmd: List[str]
    cwd: str
    log_file: str
    timeout_seconds: int
    started_at: str
    status: str = "running"
    finished_at: Optional[str] = None
    return_code: Optional[int] = None
    error: Optional[str] = None
    process: subprocess.Popen = field(repr=False, compare=False, default=None)

    def snapshot(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "key": self.key,
            "cmd": self.cmd,
            "cwd": self.cwd,
            "log_file": self.log_file,
            "timeout_seconds": self.timeout_seconds,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "return_code": self.return_code,
            "error": self.error,
        }


def popen_process_group_kwargs() -> Dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def terminate_process_tree(process: subprocess.Popen, *, force: bool = False) -> None:
    if process.poll() is not None:
        return

    if os.name == "nt":
        if force:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
        else:
            try:
                process.send_signal(signal.CTRL_BREAK_EVENT)
            except (ValueError, OSError):
                process.terminate()
        return

    try:
        sig = signal.SIGKILL if force else signal.SIGTERM
        os.killpg(os.getpgid(process.pid), sig)
    except ProcessLookupError:
        return
    except OSError:
        if force:
            process.kill()
        else:
            process.terminate()


class ProcessJobManager:
    def __init__(self, max_retained_jobs: int = 100):
        self._jobs: Dict[str, ProcessJob] = {}
        self._active_by_key: Dict[str, str] = {}
        self._lock = threading.RLock()
        self._max_retained_jobs = max(10, max_retained_jobs)

    def _default_log_file(self, key: str, cwd: str) -> str:
        safe_key = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in key)
        log_dir = Path(cwd) / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return str(log_dir / f"{safe_key}_{stamp}.log")

    @staticmethod
    def _popen_kwargs() -> Dict[str, Any]:
        return popen_process_group_kwargs()

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen, *, force: bool = False) -> None:
        terminate_process_tree(process, force=force)

    def _prune_finished_locked(self) -> None:
        if len(self._jobs) <= self._max_retained_jobs:
            return

        active_job_ids = set(self._active_by_key.values())
        finished_jobs = [
            job
            for job in self._jobs.values()
            if job.job_id not in active_job_ids and job.status != "running"
        ]
        overflow = len(self._jobs) - self._max_retained_jobs
        for job in sorted(finished_jobs, key=lambda item: item.finished_at or item.started_at)[:overflow]:
            self._jobs.pop(job.job_id, None)

    def start(
        self,
        *,
        key: str,
        cmd: List[str],
        cwd: str,
        timeout_seconds: int = 1800,
        log_file: Optional[str] = None,
        allow_concurrent: bool = False,
    ) -> Dict[str, Any]:
        if not cmd:
            raise ValueError("cmd must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if not Path(cwd).is_dir():
            raise FileNotFoundError(f"cwd does not exist: {cwd}")

        with self._lock:
            self._prune_finished_locked()
            active_job_id = self._active_by_key.get(key)
            if active_job_id and not allow_concurrent:
                active_job = self._jobs.get(active_job_id)
                if active_job and active_job.process and active_job.process.poll() is None:
                    raise ProcessAlreadyRunning(key, active_job)
                self._active_by_key.pop(key, None)

            job_id = uuid.uuid4().hex
            resolved_log_file = log_file or self._default_log_file(key, cwd)
            Path(resolved_log_file).parent.mkdir(parents=True, exist_ok=True)

            log_handle = open(resolved_log_file, "w", encoding="utf-8", errors="replace")
            try:
                log_handle.write(f"=== job started ===\n")
                log_handle.write(f"key: {key}\n")
                log_handle.write(f"cwd: {cwd}\n")
                log_handle.write(f"cmd: {' '.join(cmd)}\n")
                log_handle.write(f"started_at: {datetime.now().isoformat()}\n\n")
                log_handle.flush()

                process = subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    shell=False,
                    **self._popen_kwargs(),
                )
            except Exception:
                log_handle.close()
                raise

            job = ProcessJob(
                job_id=job_id,
                key=key,
                cmd=list(cmd),
                cwd=cwd,
                log_file=resolved_log_file,
                timeout_seconds=timeout_seconds,
                started_at=datetime.now().isoformat(),
                process=process,
            )
            self._jobs[job_id] = job
            self._active_by_key[key] = job_id

            thread = threading.Thread(
                target=self._monitor,
                args=(job_id, log_handle),
                daemon=True,
            )
            thread.start()
            return job.snapshot()

    def _monitor(self, job_id: str, log_handle) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
        if not job:
            try:
                log_handle.close()
            except Exception:
                pass
            return

        try:
            return_code = job.process.wait(timeout=job.timeout_seconds)
            status = "completed" if return_code == 0 else "failed"
            error = None if return_code == 0 else f"exit code {return_code}"
        except subprocess.TimeoutExpired:
            self._terminate_process_tree(job.process, force=True)
            return_code = job.process.wait()
            status = "timed_out"
            error = f"timed out after {job.timeout_seconds}s"
        except Exception as exc:
            return_code = job.process.poll()
            status = "failed"
            error = str(exc)

        finished_at = datetime.now().isoformat()
        try:
            log_handle.write(f"\n=== job finished ===\n")
            log_handle.write(f"status: {status}\n")
            log_handle.write(f"return_code: {return_code}\n")
            if error:
                log_handle.write(f"error: {error}\n")
            log_handle.write(f"finished_at: {finished_at}\n")
        finally:
            log_handle.close()

        with self._lock:
            job.status = status
            job.return_code = return_code
            job.error = error
            job.finished_at = finished_at
            if self._active_by_key.get(job.key) == job_id:
                self._active_by_key.pop(job.key, None)
            self._prune_finished_locked()

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.snapshot() if job else None

    def get_active(self, key: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job_id = self._active_by_key.get(key)
            job = self._jobs.get(job_id) if job_id else None
            return job.snapshot() if job else None

    def stop(self, key: str) -> bool:
        with self._lock:
            job_id = self._active_by_key.get(key)
            job = self._jobs.get(job_id) if job_id else None
        if not job or not job.process or job.process.poll() is not None:
            return False
        self._terminate_process_tree(job.process, force=True)
        return True


process_job_manager = ProcessJobManager()
