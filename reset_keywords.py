"""keyword_insights 테이블 초기화"""
import sqlite3
import os
import sys
from utils import ConfigManager

# Windows 인코딩 수정
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

config = ConfigManager()
db_path = config.db_path

print(f"Database: {db_path}")

# 백업 확인
backup_files = [f for f in os.listdir(os.path.dirname(db_path)) if f.startswith('marketing_data.db.backup_')]
print(f"Backups found: {len(backup_files)}")
if backup_files:
    latest = sorted(backup_files)[-1]
    print(f"  Latest: {latest}")

# 초기화
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 현재 키워드 수 확인
cursor.execute("SELECT COUNT(*) FROM keyword_insights")
before_count = cursor.fetchone()[0]
print(f"\nBefore: {before_count:,} keywords")

# 삭제
cursor.execute("DELETE FROM keyword_insights")
conn.commit()

cursor.execute("SELECT COUNT(*) FROM keyword_insights")
after_count = cursor.fetchone()[0]
print(f"After: {after_count:,} keywords")

# VACUUM으로 공간 회수
cursor.execute("VACUUM")
conn.commit()

conn.close()

print("\nkeyword_insights table reset complete!")
print("\nNext step:")
print("  python pathfinder.py")
