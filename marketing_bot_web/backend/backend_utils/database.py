"""
Database Connection Utility
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

DB 연결 보일러플레이트 중복 제거를 위한 컨텍스트 매니저
- 14개 라우터에서 동일한 패턴 반복 → 단일 유틸리티로 통합
- 자동 연결 종료로 리소스 누수 방지
"""

from contextlib import contextmanager
from typing import Generator
import sqlite3
import sys
from pathlib import Path

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent.parent)
sys.path.insert(0, parent_dir)

from db.database import DatabaseManager


def _configure_connection(conn: sqlite3.Connection) -> None:
    """
    [Phase 1 - 성능/안정성] 연결에 WAL 모드 및 동시성 설정 적용

    - WAL 모드: 동시 읽기/쓰기 가능
    - busy_timeout: 락 대기 시간 (5초)
    - synchronous=NORMAL: 성능과 안정성 균형
    """
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")  # 5초 대기
    conn.execute("PRAGMA cache_size=-8000")   # 8MB 캐시


@contextmanager
def get_db_connection(row_factory: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """
    데이터베이스 연결 컨텍스트 매니저

    Args:
        row_factory: True이면 sqlite3.Row를 row_factory로 설정 (딕셔너리처럼 접근 가능)

    Yields:
        sqlite3.Connection: 데이터베이스 연결 객체

    Usage:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM table")
            results = cursor.fetchall()
        # 자동으로 연결 종료됨

    Example (row_factory=True):
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, name FROM users")
            for row in cursor.fetchall():
                print(row['id'], row['name'])  # 딕셔너리처럼 접근
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path, timeout=30.0)

    if row_factory:
        conn.row_factory = sqlite3.Row

    # [Phase 1] WAL 모드 및 동시성 설정 적용
    _configure_connection(conn)

    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_db_cursor(row_factory: bool = True, commit: bool = False) -> Generator[sqlite3.Cursor, None, None]:
    """
    데이터베이스 커서 컨텍스트 매니저

    Args:
        row_factory: True이면 sqlite3.Row를 row_factory로 설정
        commit: True이면 종료 시 자동 커밋

    Yields:
        sqlite3.Cursor: 데이터베이스 커서 객체

    Usage:
        with get_db_cursor(commit=True) as cursor:
            cursor.execute("INSERT INTO table VALUES (?)", (value,))
        # 자동으로 커밋 및 연결 종료됨
    """
    db = DatabaseManager()
    conn = sqlite3.connect(db.db_path, timeout=30.0)

    if row_factory:
        conn.row_factory = sqlite3.Row

    # [Phase 1] WAL 모드 및 동시성 설정 적용
    _configure_connection(conn)

    cursor = conn.cursor()

    try:
        yield cursor
        if commit:
            conn.commit()
    finally:
        conn.close()


def execute_query(query: str, params: tuple = (), fetch_one: bool = False, fetch_all: bool = True):
    """
    단순 쿼리 실행 헬퍼

    Args:
        query: SQL 쿼리문
        params: 쿼리 파라미터
        fetch_one: True이면 fetchone() 결과 반환
        fetch_all: True이면 fetchall() 결과 반환 (기본값)

    Returns:
        쿼리 결과 또는 None

    Usage:
        # 단일 행 조회
        row = execute_query("SELECT * FROM users WHERE id = ?", (1,), fetch_one=True)

        # 여러 행 조회
        rows = execute_query("SELECT * FROM users WHERE status = ?", ('active',))

        # 결과 없이 실행 (INSERT/UPDATE/DELETE)
        execute_query("UPDATE users SET status = ? WHERE id = ?", ('inactive', 1), fetch_all=False)
    """
    with get_db_cursor() as cursor:
        cursor.execute(query, params)

        if fetch_one:
            return cursor.fetchone()
        elif fetch_all:
            return cursor.fetchall()
        return None


def execute_write(query: str, params: tuple = ()) -> int:
    """
    쓰기 쿼리 실행 헬퍼 (INSERT/UPDATE/DELETE)

    Args:
        query: SQL 쿼리문
        params: 쿼리 파라미터

    Returns:
        영향받은 행 수

    Usage:
        affected = execute_write("DELETE FROM users WHERE status = ?", ('deleted',))
        print(f"{affected}개 행 삭제됨")
    """
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(query, params)
        return cursor.rowcount


def execute_insert(query: str, params: tuple = ()) -> int:
    """
    INSERT 쿼리 실행 및 마지막 삽입된 ID 반환

    Args:
        query: INSERT SQL 쿼리문
        params: 쿼리 파라미터

    Returns:
        마지막 삽입된 행의 ID (lastrowid)

    Usage:
        new_id = execute_insert(
            "INSERT INTO users (name, email) VALUES (?, ?)",
            ('John', 'john@example.com')
        )
        print(f"새 사용자 ID: {new_id}")
    """
    with get_db_cursor(commit=True) as cursor:
        cursor.execute(query, params)
        return cursor.lastrowid
