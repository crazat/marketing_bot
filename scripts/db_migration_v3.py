#!/usr/bin/env python3
"""
DB Migration: Pathfinder V3 스키마 확장
- keyword_insights 테이블에 V3 컬럼 추가
- serp_analysis, competitor_analysis, gap_keywords 테이블 생성
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

import sqlite3
import os
from datetime import datetime


def migrate_v3(db_path: str = None):
    """V3 스키마 마이그레이션 실행"""

    if db_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")

    print(f"DB 경로: {db_path}")

    if not os.path.exists(db_path):
        print("DB 파일이 존재하지 않습니다. 새로 생성됩니다.")

    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()

    print("\n[1/4] keyword_insights 테이블 V3 컬럼 추가...")

    # 기존 컬럼 확인
    cursor.execute("PRAGMA table_info(keyword_insights)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # V3 컬럼 추가
    v3_columns = [
        ("difficulty", "INTEGER DEFAULT 50"),
        ("opportunity", "INTEGER DEFAULT 50"),
        ("priority_v3", "REAL DEFAULT 0"),
        ("grade", "TEXT DEFAULT 'C'"),
        ("is_gap_keyword", "INTEGER DEFAULT 0"),  # SQLite는 BOOLEAN 없음
        ("serp_analyzed_at", "TIMESTAMP"),
        ("source", "TEXT DEFAULT 'legacy'")  # autocomplete, related, competitor, legacy
    ]

    for col_name, col_type in v3_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col_name} {col_type}")
                print(f"   + {col_name} 컬럼 추가됨")
            except sqlite3.OperationalError as e:
                print(f"   - {col_name} 이미 존재 또는 오류: {e}")
        else:
            print(f"   - {col_name} 이미 존재")

    print("\n[2/4] serp_analysis 테이블 생성...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS serp_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            top_10_json TEXT,
            difficulty INTEGER DEFAULT 50,
            opportunity INTEGER DEFAULT 50,
            blog_count INTEGER DEFAULT 0,
            avg_days_since INTEGER DEFAULT 90,
            official_blog_count INTEGER DEFAULT 0,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("   + serp_analysis 테이블 준비 완료")

    print("\n[3/4] competitor_analysis 테이블 생성...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS competitor_analysis (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            competitor_name TEXT,
            blog_url TEXT,
            blog_id TEXT,
            total_posts INTEGER DEFAULT 0,
            top_keywords_json TEXT,
            posting_frequency REAL DEFAULT 0,
            analyzed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(competitor_name, blog_id)
        )
    ''')
    print("   + competitor_analysis 테이블 준비 완료")

    print("\n[4/4] gap_keywords 테이블 생성...")
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS gap_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT UNIQUE,
            found_in_competitors TEXT,
            frequency INTEGER DEFAULT 0,
            priority REAL DEFAULT 0,
            our_status TEXT DEFAULT 'missing',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    print("   + gap_keywords 테이블 준비 완료")

    conn.commit()
    conn.close()

    print("\n" + "=" * 50)
    print("V3 스키마 마이그레이션 완료!")
    print("=" * 50)


def verify_migration(db_path: str = None):
    """마이그레이션 검증"""

    if db_path is None:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        db_path = os.path.join(base_dir, "db", "marketing_data.db")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    print("\n[검증] 테이블 목록:")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    for t in sorted(tables):
        print(f"   - {t}")

    print("\n[검증] keyword_insights 컬럼:")
    cursor.execute("PRAGMA table_info(keyword_insights)")
    for row in cursor.fetchall():
        print(f"   - {row[1]}: {row[2]}")

    conn.close()


if __name__ == "__main__":
    migrate_v3()
    verify_migration()
