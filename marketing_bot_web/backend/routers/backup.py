"""Database backup and maintenance API."""

from __future__ import annotations

import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

parent_dir = str(Path(__file__).parent.parent.parent)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

from backend_utils.error_handlers import handle_exceptions
from db.database import DatabaseManager
from db_backup import DatabaseBackup

router = APIRouter()


def _safe_backup_path(backup: DatabaseBackup, filename: str) -> Path:
    if not re.match(r"^[A-Za-z0-9_.-]+$", filename):
        raise HTTPException(
            status_code=400,
            detail="Invalid filename. Use only letters, numbers, _, -, and .",
        )
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid file path")

    backup_dir = Path(backup.backup_dir).resolve()
    backup_path = (backup_dir / filename).resolve()
    try:
        backup_path.relative_to(backup_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="File path is outside backup directory") from exc

    if not backup_path.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")
    return backup_path


@router.get("/status")
@handle_exceptions
async def get_backup_status() -> Dict[str, Any]:
    backup = DatabaseBackup()
    status = backup.get_backup_status()

    if os.path.exists(backup.db_path):
        db_size_bytes = os.path.getsize(backup.db_path)
        status["db_size_mb"] = round(db_size_bytes / (1024 * 1024), 2)
    else:
        status["db_size_mb"] = 0

    if status["latest_backup"]:
        last_backup_time = datetime.fromisoformat(status["latest_backup"]["created"])
        days_diff = (datetime.now() - last_backup_time).days
        status["days_since_backup"] = days_diff
        if days_diff >= 7:
            status["warning_level"] = "critical"
        elif days_diff >= 3:
            status["warning_level"] = "warning"
        else:
            status["warning_level"] = "ok"
    else:
        status["days_since_backup"] = None
        status["warning_level"] = "critical"

    return status


@router.post("/create")
@handle_exceptions
async def create_backup(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    del background_tasks
    backup = DatabaseBackup()
    result = backup.run_daily_maintenance()

    return {
        "status": "success",
        "message": "Backup completed successfully",
        "backup_path": result["backup_path"],
        "integrity_ok": result["integrity_ok"],
        "backups_cleaned": result["backups_cleaned"],
    }


@router.get("/list")
@handle_exceptions
async def list_backups() -> List[Dict[str, Any]]:
    backup = DatabaseBackup()
    backups: List[Dict[str, Any]] = []

    for path in backup.list_backup_files():
        stat = path.stat()
        backups.append(
            {
                "filename": path.name,
                "size_kb": round(stat.st_size / 1024, 1),
                "size_mb": round(stat.st_size / (1024 * 1024), 2),
                "created": datetime.fromtimestamp(stat.st_mtime).isoformat(),
            }
        )

    backups.sort(key=lambda item: item["created"], reverse=True)
    return backups


@router.post("/integrity-check")
@handle_exceptions
async def check_integrity() -> Dict[str, Any]:
    backup = DatabaseBackup()
    is_ok = backup.check_integrity()
    return {
        "integrity_ok": is_ok,
        "message": "Database integrity check passed" if is_ok else "Database integrity check failed",
        "checked_at": datetime.now().isoformat(),
    }


@router.post("/vacuum")
@handle_exceptions
async def vacuum_database() -> Dict[str, Any]:
    backup = DatabaseBackup()
    before_size = os.path.getsize(backup.db_path) if os.path.exists(backup.db_path) else 0
    success = backup.vacuum_database()
    after_size = os.path.getsize(backup.db_path) if os.path.exists(backup.db_path) else 0

    return {
        "success": success,
        "message": "VACUUM completed" if success else "VACUUM failed",
        "before_size_mb": round(before_size / (1024 * 1024), 2),
        "after_size_mb": round(after_size / (1024 * 1024), 2),
        "saved_kb": round((before_size - after_size) / 1024, 1),
    }


@router.post("/restore/{filename}")
@handle_exceptions
async def restore_backup(filename: str) -> Dict[str, Any]:
    backup = DatabaseBackup()
    backup_path = _safe_backup_path(backup, filename)

    if not backup.check_file_integrity(str(backup_path)):
        raise HTTPException(status_code=400, detail="Backup file integrity check failed")

    try:
        pre_restore_path = backup.create_backup(prefix="pre_restore")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create pre-restore backup: {exc}") from exc

    try:
        source = sqlite3.connect(str(backup_path), timeout=30.0)
        target = sqlite3.connect(backup.db_path, timeout=30.0)
        try:
            source.backup(target)
            target.commit()
        finally:
            target.close()
            source.close()
    except Exception as exc:
        shutil.copy2(pre_restore_path, backup.db_path)
        raise HTTPException(status_code=500, detail=f"Restore failed and was rolled back: {exc}") from exc

    if not backup.check_integrity():
        shutil.copy2(pre_restore_path, backup.db_path)
        raise HTTPException(status_code=500, detail="Restored database failed integrity check and was rolled back")

    return {
        "success": True,
        "message": f'Restored from backup "{filename}"',
        "pre_restore_backup": Path(pre_restore_path).name,
        "restored_at": datetime.now().isoformat(),
    }


@router.get("/retention/preview")
async def preview_retention_cleanup():
    try:
        from services.data_retention import get_table_sizes, run_retention_cleanup

        db = DatabaseManager()
        preview = run_retention_cleanup(db.db_path, dry_run=True)
        preview["table_sizes"] = get_table_sizes(db.db_path)[:15]
        return preview
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/retention/execute")
async def execute_retention_cleanup():
    try:
        from services.data_retention import run_full_maintenance

        db = DatabaseManager()
        return run_full_maintenance(db.db_path)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/retention/table-sizes")
async def get_all_table_sizes():
    try:
        from services.data_retention import get_table_sizes

        db = DatabaseManager()
        sizes = get_table_sizes(db.db_path)
        return {
            "tables": sizes,
            "total_tables": len(sizes),
            "total_rows": sum(row["rows"] for row in sizes),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
