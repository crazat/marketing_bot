#!/usr/bin/env python3
"""LEGION DB 데이터 확인"""
import sqlite3
import time
import os

# WSL 환경: 로컬로 복사 후 읽기
import shutil
original_db = os.path.join(os.path.dirname(__file__), "db", "marketing_data.db")
db_path = "/tmp/check_legion.db"
shutil.copy2(original_db, db_path)
print(f"DB 복사 완료: {db_path}")

for i in range(3):
    try:
        conn = sqlite3.connect(db_path, timeout=30)
        cursor = conn.cursor()

        print("=" * 50)
        print("LEGION DB 데이터 확인")
        print("=" * 50)

        # Source별 현황
        cursor.execute('''
            SELECT source, COUNT(*) as total,
                   COUNT(CASE WHEN grade IN ('S','A') THEN 1 END) as sa_count
            FROM keyword_insights
            WHERE source IS NOT NULL AND source != ''
            GROUP BY source
            ORDER BY total DESC
        ''')

        print("\nSource별 키워드 현황:")
        print("-" * 50)
        for row in cursor.fetchall():
            print(f"  {row[0]:20} | 총: {row[1]:4}개 | S/A: {row[2]:3}개")

        # 전체 통계
        cursor.execute("SELECT COUNT(*) FROM keyword_insights")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE grade = 'S'")
        s_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE grade = 'A'")
        a_count = cursor.fetchone()[0]

        print(f"\n전체 통계:")
        print(f"  총 키워드: {total}개")
        print(f"  S급: {s_count}개")
        print(f"  A급: {a_count}개")

        conn.close()
        break
    except Exception as e:
        print(f"시도 {i+1}: {e}")
        time.sleep(2)
