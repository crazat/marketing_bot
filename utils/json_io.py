"""Small JSON file helpers for durable config/state writes."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Callable, Iterator

_LOCKS_GUARD = threading.Lock()
_PATH_LOCKS: dict[Path, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    resolved = path.resolve()
    with _LOCKS_GUARD:
        lock = _PATH_LOCKS.get(resolved)
        if lock is None:
            lock = threading.RLock()
            _PATH_LOCKS[resolved] = lock
        return lock


@contextmanager
def json_file_lock(path: str | os.PathLike[str]) -> Iterator[None]:
    """Serialize read-modify-write access to a JSON file across threads/processes."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    lock_path = target.with_name(f".{target.name}.lock")

    local_lock = _path_lock(target)
    with local_lock:
        lock_file = open(lock_path, "a+b")
        try:
            lock_file.seek(0, os.SEEK_END)
            if lock_file.tell() == 0:
                lock_file.write(b"0")
                lock_file.flush()
            lock_file.seek(0)

            if os.name == "nt":
                import msvcrt

                msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)

                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                try:
                    import fcntl
                except ImportError:
                    yield
                else:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                    try:
                        yield
                    finally:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            lock_file.close()


def _atomic_write_json_unlocked(
    path: Path,
    data: Any,
    *,
    ensure_ascii: bool,
    indent: int | None,
    default: Callable[[Any], Any] | None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)

    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=ensure_ascii, indent=indent, default=default)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
    except Exception:
        try:
            tmp_path.unlink()
        except OSError:
            pass
        raise


def atomic_write_json(
    path: str | os.PathLike[str],
    data: Any,
    *,
    ensure_ascii: bool = False,
    indent: int | None = 2,
    default: Callable[[Any], Any] | None = None,
    acquire_lock: bool = True,
) -> None:
    """Write JSON through a same-directory temp file and atomically replace target."""
    target = Path(path)
    if acquire_lock:
        with json_file_lock(target):
            _atomic_write_json_unlocked(
                target,
                data,
                ensure_ascii=ensure_ascii,
                indent=indent,
                default=default,
            )
    else:
        _atomic_write_json_unlocked(
            target,
            data,
            ensure_ascii=ensure_ascii,
            indent=indent,
            default=default,
        )
