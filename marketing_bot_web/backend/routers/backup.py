"""
Database Backup API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

데이터베이스 백업 관리 및 상태 조회
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Dict, Any, List
import sys
import os
import re
from pathlib import Path
from datetime import datetime

# 상위 디렉토리를 path에 추가
parent_dir = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, parent_dir)

from db_backup import DatabaseBackup
from backend_utils.error_handlers import handle_exceptions

router = APIRouter()


@router.get("/status")
@handle_exceptions
async def get_backup_status() -> Dict[str, Any]:
    """
    백업 상태 조회

    Returns:
        - total_backups: 총 백업 수
        - latest_backup: 가장 최근 백업 정보
        - backups: 최근 5개 백업 목록
        - db_size_mb: 현재 DB 크기 (MB)
        - days_since_backup: 마지막 백업 이후 경과 일수
    """
    try:
        backup = DatabaseBackup()
        status = backup.get_backup_status()

        # DB 크기 추가
        if os.path.exists(backup.db_path):
            db_size_bytes = os.path.getsize(backup.db_path)
            status['db_size_mb'] = round(db_size_bytes / (1024 * 1024), 2)
        else:
            status['db_size_mb'] = 0

        # 마지막 백업 이후 경과 일수 계산
        if status['latest_backup']:
            last_backup_time = datetime.fromisoformat(status['latest_backup']['created'])
            days_diff = (datetime.now() - last_backup_time).days
            status['days_since_backup'] = days_diff

            # 경고 레벨 결정
            if days_diff >= 7:
                status['warning_level'] = 'critical'
            elif days_diff >= 3:
                status['warning_level'] = 'warning'
            else:
                status['warning_level'] = 'ok'
        else:
            status['days_since_backup'] = None
            status['warning_level'] = 'critical'

        return status

    except Exception as e:
        print(f"[Backup Status Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"백업 상태 조회 실패: {str(e)}")


@router.post("/create")
@handle_exceptions
async def create_backup(background_tasks: BackgroundTasks) -> Dict[str, Any]:
    """
    수동 백업 생성 (백그라운드 실행)

    Returns:
        - status: 시작 상태
        - message: 상태 메시지
    """
    try:
        backup = DatabaseBackup()

        # 동기적으로 백업 실행 (빠른 작업이므로)
        result = backup.run_daily_maintenance()

        if result['backup_path']:
            return {
                'status': 'success',
                'message': '백업이 성공적으로 완료되었습니다',
                'backup_path': result['backup_path'],
                'integrity_ok': result['integrity_ok'],
                'backups_cleaned': result['backups_cleaned']
            }
        else:
            raise HTTPException(status_code=500, detail="백업 생성에 실패했습니다")

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Backup Create Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"백업 생성 실패: {str(e)}")


@router.get("/list")
@handle_exceptions
async def list_backups() -> List[Dict[str, Any]]:
    """
    모든 백업 목록 조회

    Returns:
        백업 파일 목록 (전체)
    """
    try:
        backup = DatabaseBackup()

        backups = []
        if os.path.exists(backup.backup_dir):
            for f in os.listdir(backup.backup_dir):
                if f.endswith(".db"):
                    path = os.path.join(backup.backup_dir, f)
                    backups.append({
                        'filename': f,
                        'size_kb': round(os.path.getsize(path) / 1024, 1),
                        'size_mb': round(os.path.getsize(path) / (1024 * 1024), 2),
                        'created': datetime.fromtimestamp(os.path.getmtime(path)).isoformat()
                    })

        # 최신순 정렬
        backups.sort(key=lambda x: x['created'], reverse=True)

        return backups

    except Exception as e:
        print(f"[Backup List Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"백업 목록 조회 실패: {str(e)}")


@router.post("/integrity-check")
@handle_exceptions
async def check_integrity() -> Dict[str, Any]:
    """
    데이터베이스 무결성 검사

    Returns:
        - integrity_ok: 무결성 상태
        - message: 결과 메시지
    """
    try:
        backup = DatabaseBackup()
        is_ok = backup.check_integrity()

        return {
            'integrity_ok': is_ok,
            'message': '데이터베이스가 정상입니다' if is_ok else '데이터베이스에 문제가 있습니다',
            'checked_at': datetime.now().isoformat()
        }

    except Exception as e:
        print(f"[Integrity Check Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"무결성 검사 실패: {str(e)}")


@router.post("/vacuum")
@handle_exceptions
async def vacuum_database() -> Dict[str, Any]:
    """
    데이터베이스 최적화 (VACUUM)

    Returns:
        - success: 성공 여부
        - message: 결과 메시지
    """
    try:
        backup = DatabaseBackup()

        # VACUUM 전 크기
        before_size = os.path.getsize(backup.db_path) if os.path.exists(backup.db_path) else 0

        success = backup.vacuum_database()

        # VACUUM 후 크기
        after_size = os.path.getsize(backup.db_path) if os.path.exists(backup.db_path) else 0

        saved_kb = round((before_size - after_size) / 1024, 1)

        return {
            'success': success,
            'message': 'VACUUM 최적화가 완료되었습니다' if success else 'VACUUM 실패',
            'before_size_mb': round(before_size / (1024 * 1024), 2),
            'after_size_mb': round(after_size / (1024 * 1024), 2),
            'saved_kb': saved_kb
        }

    except Exception as e:
        print(f"[Vacuum Error] {str(e)}")
        raise HTTPException(status_code=500, detail=f"VACUUM 실패: {str(e)}")


@router.post("/restore/{filename}")
@handle_exceptions
async def restore_backup(filename: str) -> Dict[str, Any]:
    """
    [Phase 5.2] 백업 복구

    **주의**: 현재 데이터베이스가 선택한 백업으로 덮어씌워집니다.
    복구 전에 현재 상태의 백업이 자동으로 생성됩니다.

    Args:
        filename: 복구할 백업 파일명

    Returns:
        - success: 복구 성공 여부
        - message: 결과 메시지
        - pre_restore_backup: 복구 전 생성된 백업 파일명
    """
    import shutil
    import sqlite3

    try:
        backup = DatabaseBackup()

        # [보안] Path Traversal 방어
        # 1. 파일명 패턴 검증 (알파벳, 숫자, 언더스코어, 하이픈, 점만 허용)
        if not re.match(r'^[a-zA-Z0-9_\-\.]+\.db$', filename):
            raise HTTPException(
                status_code=400,
                detail="유효하지 않은 파일명입니다. 파일명은 알파벳, 숫자, _, -, .만 포함할 수 있습니다."
            )

        # 2. 경로 탐색 문자 차단
        if '..' in filename or '/' in filename or '\\' in filename:
            raise HTTPException(
                status_code=400,
                detail="잘못된 파일 경로입니다."
            )

        # 3. 경로 정규화 후 범위 확인
        backup_path = (Path(backup.backup_dir) / filename).resolve()
        backup_dir_resolved = Path(backup.backup_dir).resolve()

        # 4. 백업 디렉토리 내부인지 확인
        try:
            backup_path.relative_to(backup_dir_resolved)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="허용되지 않은 파일 경로입니다."
            )

        backup_path_str = str(backup_path)

        # 5. 백업 파일 존재 확인
        if not os.path.exists(backup_path_str):
            raise HTTPException(status_code=404, detail="백업 파일을 찾을 수 없습니다.")

        # 6. 백업 파일 무결성 검사
        try:
            conn = sqlite3.connect(backup_path_str)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()

            if result != "ok":
                raise HTTPException(status_code=400, detail="선택한 백업 파일이 손상되었습니다")
        except sqlite3.Error as e:
            raise HTTPException(status_code=400, detail=f"백업 파일 검증 실패: {str(e)}")

        # 7. 현재 DB 백업 (복구 전 안전 백업)
        pre_restore_backup = f"pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
        pre_restore_path = str(Path(backup.backup_dir) / pre_restore_backup)

        try:
            shutil.copy2(backup.db_path, pre_restore_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"복구 전 백업 생성 실패: {str(e)}")

        # 8. 복구 실행
        try:
            shutil.copy2(backup_path_str, backup.db_path)
        except Exception as e:
            # 복구 실패 시 롤백
            shutil.copy2(pre_restore_path, backup.db_path)
            raise HTTPException(status_code=500, detail=f"복구 실패, 원래 상태로 롤백됨: {str(e)}")

        # 9. 복구된 DB 무결성 검사
        try:
            conn = sqlite3.connect(backup.db_path)
            cursor = conn.cursor()
            cursor.execute("PRAGMA integrity_check")
            result = cursor.fetchone()[0]
            conn.close()

            if result != "ok":
                # 복구 실패 시 롤백
                shutil.copy2(pre_restore_path, backup.db_path)
                raise HTTPException(status_code=500, detail="복구된 DB에 문제가 있어 롤백되었습니다")
        except sqlite3.Error:
            shutil.copy2(pre_restore_path, backup.db_path)
            raise HTTPException(status_code=500, detail="복구된 DB 검증 실패, 롤백되었습니다")

        return {
            'success': True,
            'message': f'백업 "{filename}"에서 복구가 완료되었습니다',
            'pre_restore_backup': pre_restore_backup,
            'restored_at': datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"[Restore Error] {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"복구 실패: {str(e)}")
