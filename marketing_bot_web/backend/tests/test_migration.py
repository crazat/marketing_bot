"""
Migration API Tests
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[Phase 1-4] 마이그레이션 시스템 테스트
"""

import pytest
import sqlite3
import tempfile
import os
from pathlib import Path
from fastapi.testclient import TestClient

import sys
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))


class TestMigrationManager:
    """MigrationManager 단위 테스트"""

    @pytest.fixture
    def temp_db_path(self):
        """임시 데이터베이스 생성"""
        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield Path(db_path)
        try:
            os.unlink(db_path)
        except Exception:
            pass

    def test_migration_manager_init(self, temp_db_path):
        """MigrationManager 초기화 테스트"""
        from services.migration_manager import MigrationManager

        manager = MigrationManager(db_path=temp_db_path)
        assert manager.db_path == temp_db_path
        assert len(manager.migrations) > 0

    def test_run_migrations_creates_schema_versions(self, temp_db_path):
        """마이그레이션 실행 시 schema_versions 테이블 생성"""
        from services.migration_manager import MigrationManager

        manager = MigrationManager(db_path=temp_db_path)
        result = manager.run_migrations()

        # schema_versions 테이블 확인
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_versions'"
        )
        table_exists = cursor.fetchone() is not None
        conn.close()

        assert table_exists
        assert len(result["applied"]) > 0

    def test_migrations_are_idempotent(self, temp_db_path):
        """마이그레이션 중복 실행 시 멱등성 테스트"""
        from services.migration_manager import MigrationManager

        manager = MigrationManager(db_path=temp_db_path)

        # 첫 번째 실행
        result1 = manager.run_migrations()
        applied_count1 = len(result1["applied"])

        # 두 번째 실행
        result2 = manager.run_migrations()
        applied_count2 = len(result2["applied"])
        skipped_count2 = len(result2["skipped"])

        # 두 번째 실행에서는 모두 스킵되어야 함
        assert applied_count2 == 0
        assert skipped_count2 == applied_count1

    def test_get_status(self, temp_db_path):
        """마이그레이션 상태 조회 테스트"""
        from services.migration_manager import MigrationManager

        manager = MigrationManager(db_path=temp_db_path)
        manager.run_migrations()

        status = manager.get_status()

        assert "current_version" in status
        assert "total_migrations" in status
        assert "applied_count" in status
        assert "pending_count" in status
        assert status["current_version"] is not None

    def test_column_exists_helper(self, temp_db_path):
        """_column_exists 헬퍼 메서드 테스트"""
        from services.migration_manager import MigrationManager

        # 테스트 테이블 생성
        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE test_table (id INTEGER, name TEXT)")
        conn.commit()

        manager = MigrationManager(db_path=temp_db_path)

        assert manager._column_exists(cursor, "test_table", "id") is True
        assert manager._column_exists(cursor, "test_table", "name") is True
        assert manager._column_exists(cursor, "test_table", "nonexistent") is False

        conn.close()

    def test_table_exists_helper(self, temp_db_path):
        """_table_exists 헬퍼 메서드 테스트"""
        from services.migration_manager import MigrationManager

        conn = sqlite3.connect(str(temp_db_path))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE existing_table (id INTEGER)")
        conn.commit()

        manager = MigrationManager(db_path=temp_db_path)

        assert manager._table_exists(cursor, "existing_table") is True
        assert manager._table_exists(cursor, "nonexistent_table") is False

        conn.close()


@pytest.mark.api
class TestMigrationAPI:
    """Migration API 엔드포인트 테스트"""

    def test_get_migration_status(self, client):
        """GET /api/migration/status 테스트"""
        response = client.get("/api/migration/status")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert data["success"] is True
        assert "data" in data

    def test_get_migration_history(self, client):
        """GET /api/migration/history 테스트"""
        response = client.get("/api/migration/history")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "data" in data
        assert "history" in data["data"]

    def test_run_migrations_endpoint(self, client):
        """POST /api/migration/run 테스트"""
        response = client.post("/api/migration/run")
        assert response.status_code == 200

        data = response.json()
        assert "success" in data
        assert "data" in data
        # 이미 적용된 마이그레이션은 skipped에 포함됨
        assert "applied" in data["data"] or "skipped" in data["data"]


@pytest.mark.unit
class TestMigrationClass:
    """Migration 클래스 단위 테스트"""

    def test_migration_creation(self):
        """Migration 객체 생성 테스트"""
        from services.migration_manager import Migration

        migration = Migration(
            version="999",
            description="Test migration",
            up_sql=["CREATE TABLE test (id INTEGER)"]
        )

        assert migration.version == "999"
        assert migration.description == "Test migration"
        assert len(migration.up_sql) == 1

    def test_migration_apply_sql(self):
        """Migration SQL 적용 테스트"""
        from services.migration_manager import Migration

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            migration = Migration(
                version="999",
                description="Test migration",
                up_sql=["CREATE TABLE test_apply (id INTEGER, name TEXT)"]
            )

            result = migration.apply(cursor)
            conn.commit()

            assert result is True

            # 테이블 생성 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='test_apply'"
            )
            assert cursor.fetchone() is not None

            conn.close()
        finally:
            os.unlink(db_path)

    def test_migration_with_callback(self):
        """Migration 콜백 함수 테스트"""
        from services.migration_manager import Migration

        callback_called = []

        def test_callback(cursor):
            callback_called.append(True)
            cursor.execute("CREATE TABLE callback_test (id INTEGER)")

        fd, db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            migration = Migration(
                version="998",
                description="Callback test",
                up_func=test_callback
            )

            result = migration.apply(cursor)
            conn.commit()

            assert result is True
            assert len(callback_called) == 1

            # 콜백에서 생성한 테이블 확인
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='callback_test'"
            )
            assert cursor.fetchone() is not None

            conn.close()
        finally:
            os.unlink(db_path)
