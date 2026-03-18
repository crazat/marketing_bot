"""
Marketing Bot Database Backup
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

데이터베이스 백업 및 유지보수
- SQLite 백업 (복사 방식)
- 무결성 검사
- 자동 백업 정리
- API 연동 지원
"""

import sqlite3
import shutil
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional


class DatabaseBackup:
    """데이터베이스 백업 관리 클래스"""

    def __init__(self, db_path: str = None, backup_dir: str = None):
        """
        초기화

        Args:
            db_path: DB 파일 경로 (기본: 프로젝트/db/marketing_data.db)
            backup_dir: 백업 디렉토리 (기본: 프로젝트/db/backups)
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = str(Path(__file__).parent / "db" / "marketing_data.db")

        if backup_dir:
            self.backup_dir = backup_dir
        else:
            self.backup_dir = str(Path(__file__).parent / "db" / "backups")

    def get_backup_status(self) -> Dict[str, Any]:
        """
        백업 상태 조회

        Returns:
            - total_backups: 총 백업 수
            - latest_backup: 최근 백업 정보
            - backups: 최근 5개 백업 목록
        """
        backups = []
        backup_path = Path(self.backup_dir)

        if backup_path.exists():
            # 모든 백업 파일 찾기
            for f in backup_path.glob("marketing_data.db.backup_*"):
                backups.append({
                    'filename': f.name,
                    'size_mb': round(f.stat().st_size / (1024 * 1024), 2),
                    'created': datetime.fromtimestamp(f.stat().st_mtime).isoformat()
                })

        # 최신순 정렬
        backups.sort(key=lambda x: x['created'], reverse=True)

        return {
            'total_backups': len(backups),
            'latest_backup': backups[0] if backups else None,
            'backups': backups[:5]  # 최근 5개만
        }

    def create_backup(self) -> str:
        """
        백업 생성

        Returns:
            백업 파일 경로
        """
        # 백업 디렉토리 생성
        backup_dir = Path(self.backup_dir)
        backup_dir.mkdir(exist_ok=True)

        # 타임스탬프 생성
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = backup_dir / f"marketing_data.db.backup_{timestamp}"

        # 파일 복사
        shutil.copy2(self.db_path, str(backup_path))

        return str(backup_path)

    def verify_backup(self, backup_path: str) -> bool:
        """
        백업 무결성 검사

        Args:
            backup_path: 백업 파일 경로

        Returns:
            무결성 검사 통과 여부
        """
        try:
            # 원본 레코드 수
            original_conn = sqlite3.connect(self.db_path)
            original_cursor = original_conn.cursor()

            # 백업 레코드 수
            backup_conn = sqlite3.connect(backup_path)
            backup_cursor = backup_conn.cursor()

            # 주요 테이블 검증
            tables = [
                'keyword_insights',
                'rank_history',
                'viral_targets',
                'mentions',
                'competitor_reviews'
            ]

            all_match = True

            for table in tables:
                try:
                    original_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    original_count = original_cursor.fetchone()[0]

                    backup_cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    backup_count = backup_cursor.fetchone()[0]

                    if original_count != backup_count:
                        all_match = False
                        break

                except sqlite3.OperationalError:
                    # 테이블이 없으면 스킵
                    continue

            original_conn.close()
            backup_conn.close()

            return all_match

        except Exception as e:
            print(f"[Backup Verify Error] {e}")
            return False

    def cleanup_old_backups(self, keep_count: int = 30) -> int:
        """
        오래된 백업 정리

        Args:
            keep_count: 유지할 백업 수

        Returns:
            삭제된 백업 수
        """
        backup_dir = Path(self.backup_dir)

        if not backup_dir.exists():
            return 0

        # 모든 백업 파일 찾기
        backups = sorted(
            backup_dir.glob("marketing_data.db.backup_*"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        )

        # 오래된 백업 삭제
        deleted_count = 0
        if len(backups) > keep_count:
            old_backups = backups[keep_count:]
            for backup in old_backups:
                backup.unlink()
                deleted_count += 1

        return deleted_count

    def run_daily_maintenance(self) -> Dict[str, Any]:
        """
        일일 유지보수 실행 (백업 + 검증 + 정리)

        Returns:
            - backup_path: 백업 파일 경로
            - integrity_ok: 무결성 검사 통과 여부
            - backups_cleaned: 삭제된 백업 수
        """
        # 1. 백업 생성
        backup_path = self.create_backup()

        # 2. 무결성 검사
        integrity_ok = self.verify_backup(backup_path)

        # 3. 오래된 백업 정리
        backups_cleaned = self.cleanup_old_backups(keep_count=30)

        return {
            'backup_path': backup_path,
            'integrity_ok': integrity_ok,
            'backups_cleaned': backups_cleaned
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 스크립트 실행 (CLI용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def main():
    """메인 실행 함수 (CLI 모드)"""

    print("=" * 70)
    print("Marketing Bot - Database Backup")
    print("=" * 70)

    backup = DatabaseBackup()

    # DB 파일 크기 확인
    db_path = Path(backup.db_path)
    if db_path.exists():
        db_size = db_path.stat().st_size / (1024 * 1024)
        print(f"\nDB 파일: {db_path}")
        print(f"크기: {db_size:.2f} MB\n")
    else:
        print(f"\n❌ DB 파일을 찾을 수 없습니다: {db_path}")
        return

    # 백업 실행
    print("📦 백업 시작...")
    result = backup.run_daily_maintenance()

    # 결과 출력
    print(f"✅ 백업 완료!")
    print(f"   백업 파일: {result['backup_path']}")
    print(f"   무결성 검사: {'✅ 통과' if result['integrity_ok'] else '❌ 실패'}")
    print(f"   정리된 백업: {result['backups_cleaned']}개")

    # 백업 상태 확인
    status = backup.get_backup_status()
    print(f"\n📊 백업 상태:")
    print(f"   총 백업 수: {status['total_backups']}개")

    if status['latest_backup']:
        print(f"   최근 백업: {status['latest_backup']['filename']}")
        print(f"   생성 시간: {status['latest_backup']['created']}")

    print("\n" + "=" * 70)
    print("✅ 전체 작업 완료!")
    print("=" * 70)


if __name__ == "__main__":
    main()
