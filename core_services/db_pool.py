"""
Database Connection Pool
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 5.0] 보안 강화 - 스레드 안전한 DB 연결 관리

SQLite 동시성 문제 해결:
- 스레드 락을 통한 안전한 연결 관리
- 컨텍스트 매니저로 자동 정리
- WAL 모드 활성화
- 연결 타임아웃 설정
"""

import sqlite3
import threading
import logging
from typing import Optional, Generator, Any
from contextlib import contextmanager
from pathlib import Path
import os

logger = logging.getLogger(__name__)

# 기본 DB 경로
DEFAULT_DB_PATH = Path(__file__).parent.parent / 'db' / 'marketing_data.db'


class DatabaseConnectionError(Exception):
    """DB 연결 에러"""
    pass


class DatabasePool:
    """
    SQLite 연결 풀 (스레드 안전)

    SQLite는 단일 writer 제한이 있어 진정한 연결 풀링은 불가능하지만,
    이 클래스는 스레드 락을 통해 동시 접근을 관리합니다.

    사용법:
        from services.db_pool import get_db_pool

        pool = get_db_pool()
        with pool.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM mentions")
            results = cursor.fetchall()
    """

    _instance: Optional['DatabasePool'] = None
    _lock = threading.Lock()

    # 기본 설정
    DEFAULT_TIMEOUT = 30.0  # 연결 타임아웃 (초)
    BUSY_TIMEOUT = 10000    # SQLite busy 타임아웃 (밀리초)

    def __new__(cls, db_path: str = None) -> 'DatabasePool':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, db_path: str = None) -> None:
        if self._initialized:
            return

        # 환경 변수로 DB 경로 오버라이드 가능
        db_override = os.environ.get('MARKETING_BOT_DB_PATH')
        if db_override:
            self.db_path = db_override
        elif db_path:
            self.db_path = db_path
        else:
            self.db_path = str(DEFAULT_DB_PATH)

        self._write_lock = threading.RLock()  # 재진입 가능 락
        self._local = threading.local()
        self._initialized = True

        # 초기 설정 (WAL 모드 활성화 등)
        self._init_database()

        logger.info(f"🔌 DatabasePool 초기화: {self.db_path}")

    def _init_database(self) -> None:
        """데이터베이스 초기 설정"""
        try:
            conn = sqlite3.connect(self.db_path, timeout=self.DEFAULT_TIMEOUT)
            cursor = conn.cursor()

            # WAL 모드 활성화 (더 나은 동시성)
            cursor.execute("PRAGMA journal_mode=WAL")

            # busy 타임아웃 설정
            cursor.execute(f"PRAGMA busy_timeout={self.BUSY_TIMEOUT}")

            # 동기화 모드 설정 (성능과 안정성 균형)
            cursor.execute("PRAGMA synchronous=NORMAL")

            # 캐시 크기 설정 (16MB)
            cursor.execute("PRAGMA cache_size=-16000")

            conn.commit()
            conn.close()

            logger.info("✅ DB 설정 완료 (WAL 모드, busy_timeout 설정됨)")

        except Exception as e:
            logger.error(f"❌ DB 초기화 실패: {e}")
            raise DatabaseConnectionError(f"DB 초기화 실패: {e}")

    def _create_connection(self) -> sqlite3.Connection:
        """새 연결 생성"""
        conn = sqlite3.connect(
            self.db_path,
            timeout=self.DEFAULT_TIMEOUT,
            check_same_thread=False,
            isolation_level='DEFERRED'
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def get_connection(self, readonly: bool = False) -> Generator[sqlite3.Connection, None, None]:
        """
        DB 연결 획득 (컨텍스트 매니저)

        Args:
            readonly: 읽기 전용 모드 (True면 락 없이 연결)

        Yields:
            sqlite3.Connection

        Example:
            with pool.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM mentions")
        """
        conn = None
        acquired = False

        try:
            # 쓰기 작업은 락 획득
            if not readonly:
                acquired = self._write_lock.acquire(timeout=self.DEFAULT_TIMEOUT)
                if not acquired:
                    raise DatabaseConnectionError(
                        "DB 쓰기 락 획득 타임아웃. 다른 프로세스가 DB를 사용 중입니다."
                    )

            conn = self._create_connection()
            yield conn

            # 성공하면 커밋
            if not readonly:
                conn.commit()

        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            logger.error(f"❌ DB 에러: {e}")
            raise DatabaseConnectionError(f"DB 에러: {e}")

        finally:
            if conn:
                conn.close()
            if acquired:
                self._write_lock.release()

    @contextmanager
    def get_cursor(self, readonly: bool = False) -> Generator[sqlite3.Cursor, None, None]:
        """
        DB 커서 획득 (편의 메서드)

        Args:
            readonly: 읽기 전용 모드

        Yields:
            sqlite3.Cursor

        Example:
            with pool.get_cursor() as cursor:
                cursor.execute("SELECT * FROM mentions")
                results = cursor.fetchall()
        """
        with self.get_connection(readonly=readonly) as conn:
            yield conn.cursor()

    def execute(
        self,
        query: str,
        params: tuple = (),
        readonly: bool = False
    ) -> list:
        """
        쿼리 실행 및 결과 반환 (간편 메서드)

        Args:
            query: SQL 쿼리
            params: 쿼리 파라미터
            readonly: 읽기 전용 모드

        Returns:
            결과 리스트

        Example:
            results = pool.execute(
                "SELECT * FROM mentions WHERE status = ?",
                ('pending',)
            )
        """
        with self.get_cursor(readonly=readonly) as cursor:
            cursor.execute(query, params)
            if query.strip().upper().startswith('SELECT'):
                return cursor.fetchall()
            return []

    def execute_many(
        self,
        query: str,
        params_list: list
    ) -> int:
        """
        배치 쿼리 실행

        Args:
            query: SQL 쿼리
            params_list: 파라미터 리스트

        Returns:
            영향받은 행 수

        Example:
            count = pool.execute_many(
                "INSERT INTO mentions (title, content) VALUES (?, ?)",
                [('제목1', '내용1'), ('제목2', '내용2')]
            )
        """
        with self.get_cursor() as cursor:
            cursor.executemany(query, params_list)
            return cursor.rowcount

    def health_check(self) -> dict:
        """
        DB 상태 확인

        Returns:
            상태 정보 딕셔너리
        """
        try:
            with self.get_cursor(readonly=True) as cursor:
                # 기본 연결 테스트
                cursor.execute("SELECT 1")

                # WAL 상태 확인
                cursor.execute("PRAGMA journal_mode")
                journal_mode = cursor.fetchone()[0]

                # 무결성 검사 (빠른 버전)
                cursor.execute("PRAGMA quick_check")
                integrity = cursor.fetchone()[0]

                # 테이블 수 확인
                cursor.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                )
                table_count = cursor.fetchone()[0]

            return {
                'status': 'healthy',
                'journal_mode': journal_mode,
                'integrity': integrity,
                'table_count': table_count,
                'db_path': self.db_path
            }

        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'db_path': self.db_path
            }


# 싱글톤 인스턴스 접근자
_pool_instance: Optional[DatabasePool] = None


def get_db_pool(db_path: str = None) -> DatabasePool:
    """DatabasePool 싱글톤 인스턴스 반환"""
    global _pool_instance
    if _pool_instance is None:
        _pool_instance = DatabasePool(db_path)
    return _pool_instance


def reset_pool() -> None:
    """연결 풀 리셋 (테스트용)"""
    global _pool_instance
    _pool_instance = None
    DatabasePool._instance = None
