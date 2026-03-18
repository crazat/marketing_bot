"""
Marketing Bot DB 스키마 확인
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

실제 테이블 구조 파악
"""

import sqlite3
from pathlib import Path


def check_schema():
    """DB 스키마 확인"""

    db_path = Path(__file__).parent.parent / "db" / "marketing_data.db"

    if not db_path.exists():
        print(f"❌ DB 파일을 찾을 수 없습니다: {db_path}")
        return

    print("=" * 70)
    print("Marketing Bot - DB 스키마 확인")
    print("=" * 70)
    print(f"\nDB 파일: {db_path}\n")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # 1. 모든 테이블 목록
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    print("📋 테이블 목록:")
    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"   - {table}: {count:,}개 레코드")

    # 2. mentions 테이블 스키마
    print("\n" + "=" * 70)
    print("📊 mentions 테이블 스키마:")
    print("=" * 70)
    cursor.execute("PRAGMA table_info(mentions)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[1]:20s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")

    # mentions.status 값 확인
    cursor.execute("SELECT DISTINCT status FROM mentions")
    statuses = [row[0] for row in cursor.fetchall()]
    print(f"\n   status 값: {statuses}")

    # 3. viral_targets 테이블 스키마
    print("\n" + "=" * 70)
    print("📊 viral_targets 테이블 스키마:")
    print("=" * 70)
    cursor.execute("PRAGMA table_info(viral_targets)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[1]:20s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")

    # 샘플 데이터 1개 확인
    cursor.execute("SELECT * FROM viral_targets LIMIT 1")
    sample = cursor.fetchone()
    if sample:
        print(f"\n   샘플 레코드:")
        cursor.execute("PRAGMA table_info(viral_targets)")
        col_names = [col[1] for col in cursor.fetchall()]
        for i, col_name in enumerate(col_names):
            value = sample[i] if i < len(sample) else None
            print(f"      {col_name}: {value}")

    # 4. rank_history 테이블 스키마
    print("\n" + "=" * 70)
    print("📊 rank_history 테이블 스키마:")
    print("=" * 70)
    cursor.execute("PRAGMA table_info(rank_history)")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   {col[1]:20s} {col[2]:15s} {'NOT NULL' if col[3] else ''}")

    # rank_history.status 값 확인
    cursor.execute("SELECT DISTINCT status FROM rank_history")
    statuses = [row[0] for row in cursor.fetchall()]
    print(f"\n   status 값: {statuses}")

    conn.close()

    print("\n" + "=" * 70)
    print("✅ 스키마 확인 완료!")
    print("=" * 70)


if __name__ == "__main__":
    check_schema()
