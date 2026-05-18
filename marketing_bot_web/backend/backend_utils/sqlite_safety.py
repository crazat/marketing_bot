"""Process-wide SQLite safety defaults for the web backend."""

from __future__ import annotations

import sqlite3
from typing import Any


_ORIGINAL_CONNECT = sqlite3.connect
_INSTALLED = False
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_BUSY_TIMEOUT_MS = 10_000
DEFAULT_CACHE_SIZE_KB = -8_000


def _configure_connection(conn: sqlite3.Connection) -> None:
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute(f"PRAGMA busy_timeout={DEFAULT_BUSY_TIMEOUT_MS}")
        conn.execute(f"PRAGMA cache_size={DEFAULT_CACHE_SIZE_KB}")
    except sqlite3.Error:
        # Some special connections, such as in-memory databases, may not support every pragma.
        pass


def safe_connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
    kwargs.setdefault("timeout", DEFAULT_TIMEOUT_SECONDS)
    conn = _ORIGINAL_CONNECT(*args, **kwargs)
    _configure_connection(conn)
    return conn


def install_sqlite_safety() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    sqlite3.connect = safe_connect
    _INSTALLED = True
