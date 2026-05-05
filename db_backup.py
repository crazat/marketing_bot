"""
Marketing Bot SQLite backup utilities.

Backups are created with SQLite's online backup API so WAL-mode databases are
copied consistently while the application is running.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class DatabaseBackup:
    """Create, verify, restore-support, and maintain SQLite database backups."""

    BACKUP_PREFIX = "marketing_data.db.backup_"
    PRE_RESTORE_PREFIX = "pre_restore_"
    BACKUP_SUFFIX = ".db"

    def __init__(self, db_path: Optional[str] = None, backup_dir: Optional[str] = None):
        root = Path(__file__).resolve().parent
        self.db_path = str(Path(db_path) if db_path else root / "db" / "marketing_data.db")
        self.backup_dir = str(Path(backup_dir) if backup_dir else root / "db" / "backups")

    def _backup_directory(self) -> Path:
        backup_dir = Path(self.backup_dir)
        backup_dir.mkdir(parents=True, exist_ok=True)
        return backup_dir

    def _iter_backup_files(self) -> List[Path]:
        backup_dir = Path(self.backup_dir)
        if not backup_dir.exists():
            return []

        files = set(backup_dir.glob(f"{self.BACKUP_PREFIX}*"))
        files.update(backup_dir.glob(f"{self.PRE_RESTORE_PREFIX}*{self.BACKUP_SUFFIX}"))
        return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)

    @staticmethod
    def _integrity_check(db_path: str) -> bool:
        try:
            with sqlite3.connect(db_path, timeout=30.0) as conn:
                result = conn.execute("PRAGMA integrity_check").fetchone()
                return bool(result and result[0] == "ok")
        except sqlite3.Error as exc:
            logger.warning("SQLite integrity check failed for %s: %s", db_path, exc)
            return False

    def get_backup_status(self) -> Dict[str, Any]:
        backups = []
        for path in self._iter_backup_files():
            stat = path.stat()
            backups.append(
                {
                    "filename": path.name,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

        return {
            "total_backups": len(backups),
            "latest_backup": backups[0] if backups else None,
            "backups": backups[:5],
        }

    def list_backup_files(self) -> List[Path]:
        return self._iter_backup_files()

    def check_file_integrity(self, db_path: str) -> bool:
        return self._integrity_check(db_path)

    def create_backup(self, prefix: Optional[str] = None) -> str:
        if not Path(self.db_path).exists():
            raise FileNotFoundError(f"Database not found: {self.db_path}")

        backup_dir = self._backup_directory()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        name_prefix = prefix if prefix is not None else self.BACKUP_PREFIX.rstrip("_")
        backup_path = backup_dir / f"{name_prefix}_{timestamp}{self.BACKUP_SUFFIX}"

        source = sqlite3.connect(self.db_path, timeout=30.0)
        target = sqlite3.connect(str(backup_path), timeout=30.0)
        try:
            try:
                source.execute("PRAGMA wal_checkpoint(PASSIVE)")
            except sqlite3.Error:
                logger.debug("WAL checkpoint skipped before backup", exc_info=True)
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()

        if not self._integrity_check(str(backup_path)):
            backup_path.unlink(missing_ok=True)
            raise sqlite3.DatabaseError("Backup integrity check failed")

        return str(backup_path)

    def verify_backup(self, backup_path: str) -> bool:
        if not Path(backup_path).exists():
            return False
        if not self._integrity_check(backup_path):
            return False

        tables = [
            "keyword_insights",
            "rank_history",
            "viral_targets",
            "mentions",
            "competitor_reviews",
        ]

        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as original_conn, sqlite3.connect(
                backup_path, timeout=30.0
            ) as backup_conn:
                for table in tables:
                    try:
                        original_count = original_conn.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                        backup_count = backup_conn.execute(
                            f"SELECT COUNT(*) FROM {table}"
                        ).fetchone()[0]
                    except sqlite3.OperationalError:
                        continue
                    if original_count != backup_count:
                        logger.warning(
                            "Backup row count mismatch for %s: original=%s backup=%s",
                            table,
                            original_count,
                            backup_count,
                        )
                        return False
        except sqlite3.Error as exc:
            logger.warning("Backup verification failed for %s: %s", backup_path, exc)
            return False

        return True

    def check_integrity(self) -> bool:
        return self._integrity_check(self.db_path)

    def enable_wal_mode(self) -> bool:
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
                conn.execute("PRAGMA synchronous=NORMAL")
                return str(mode).lower() == "wal"
        except sqlite3.Error as exc:
            logger.warning("Failed to enable WAL mode: %s", exc)
            return False

    def vacuum_database(self) -> bool:
        try:
            with sqlite3.connect(self.db_path, timeout=30.0) as conn:
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("VACUUM")
            return self.check_integrity()
        except sqlite3.Error as exc:
            logger.warning("VACUUM failed: %s", exc)
            return False

    def cleanup_old_backups(self, keep_count: int = 30) -> int:
        if keep_count < 0:
            raise ValueError("keep_count must be non-negative")

        deleted_count = 0
        for backup in self._iter_backup_files()[keep_count:]:
            backup.unlink()
            deleted_count += 1
        return deleted_count

    def run_daily_maintenance(self) -> Dict[str, Any]:
        backup_path = self.create_backup()
        integrity_ok = self.verify_backup(backup_path)
        backups_cleaned = self.cleanup_old_backups(keep_count=30)

        return {
            "backup_path": backup_path,
            "integrity_ok": integrity_ok,
            "backups_cleaned": backups_cleaned,
        }


def main() -> None:
    backup = DatabaseBackup()
    db_path = Path(backup.db_path)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    result = backup.run_daily_maintenance()
    print("Backup completed")
    print(f"backup_path={result['backup_path']}")
    print(f"integrity_ok={result['integrity_ok']}")
    print(f"backups_cleaned={result['backups_cleaned']}")


if __name__ == "__main__":
    main()
