#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV에서 LEGION MODE 데이터를 DB로 복구

Usage:
    python scripts/restore_legion_csv.py legion_v3_results.csv
"""

import sys
import os
import csv
import sqlite3
from pathlib import Path

def restore_csv_to_db(csv_path: str, db_path: str = None):
    """CSV 데이터를 DB로 복구"""

    if db_path is None:
        base_dir = Path(__file__).parent.parent
        db_path = base_dir / "db" / "marketing_data.db"

    print(f"📂 CSV: {csv_path}")
    print(f"💾 DB: {db_path}")

    # CSV 읽기
    keywords = []
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keywords.append(row)

    print(f"\n📊 CSV에서 {len(keywords)}개 키워드 읽음")

    # DB 연결 (WAL 모드)
    max_retries = 5
    retry_delay = 2
    conn = None

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=120)
            cursor = conn.cursor()

            # SQLite 최적화
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            break
        except sqlite3.OperationalError as e:
            if attempt < max_retries - 1:
                print(f"   ⚠️  DB 잠금 감지 (시도 {attempt+1}/{max_retries}), {retry_delay}초 후 재시도...")
                import time
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"\n❌ DB 연결 실패: {e}")
                return

    # V3 컬럼 확인 (없으면 추가)
    for col, ctype in [
        ("difficulty", "INTEGER DEFAULT 50"),
        ("opportunity", "INTEGER DEFAULT 50"),
        ("priority_v3", "REAL DEFAULT 0"),
        ("grade", "TEXT DEFAULT 'C'"),
        ("source", "TEXT DEFAULT 'legacy'"),
        ("trend_slope", "REAL DEFAULT 0"),
        ("trend_status", "TEXT DEFAULT 'unknown'")
    ]:
        try:
            cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col} {ctype}")
            print(f"   ✅ 컬럼 추가: {col}")
        except sqlite3.OperationalError:
            pass  # 이미 존재

    # 데이터 삽입
    saved = 0
    updated = 0
    errors = 0

    for row in keywords:
        try:
            keyword = row['keyword']
            search_volume = int(row['search_volume']) if row['search_volume'] else 0
            difficulty = int(row['difficulty']) if row['difficulty'] else 50
            opportunity = int(row['opportunity']) if row['opportunity'] else 50
            grade = row['grade'] or 'C'
            category = row['category'] or '기타'
            priority_score = float(row['priority_score']) if row['priority_score'] else 0
            source = row['source'] or 'legion'
            trend_slope = float(row['trend_slope']) if row['trend_slope'] else 0
            trend_status = row['trend_status'] or 'unknown'

            # INSERT or REPLACE (기존 데이터 있으면 업데이트)
            cursor.execute('''
                INSERT INTO keyword_insights (
                    keyword, search_volume, difficulty, opportunity,
                    grade, category, priority_v3, source,
                    trend_slope, trend_status,
                    volume, competition, opp_score, tag, region
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(keyword) DO UPDATE SET
                    search_volume = excluded.search_volume,
                    difficulty = excluded.difficulty,
                    opportunity = excluded.opportunity,
                    grade = excluded.grade,
                    category = excluded.category,
                    priority_v3 = excluded.priority_v3,
                    source = excluded.source,
                    trend_slope = excluded.trend_slope,
                    trend_status = excluded.trend_status
            ''', (
                keyword, search_volume, difficulty, opportunity,
                grade, category, priority_score, source,
                trend_slope, trend_status,
                search_volume, 'medium', priority_score, grade, '청주'
            ))

            if cursor.rowcount > 0:
                saved += 1
            else:
                updated += 1

        except Exception as e:
            errors += 1
            if errors <= 3:  # 처음 3개만 출력
                print(f"   ⚠️  에러: {keyword} - {e}")

    conn.commit()
    conn.close()

    print(f"\n{'='*70}")
    print(f"✅ 복구 완료!")
    print(f"   💾 신규 저장: {saved}개")
    print(f"   🔄 업데이트: {updated}개")
    if errors:
        print(f"   ❌ 에러: {errors}개")
    print(f"{'='*70}")

    # 통계 출력
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE source LIKE 'round%'")
    legion_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE grade = 'S' AND source LIKE 'round%'")
    s_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE grade = 'A' AND source LIKE 'round%'")
    a_count = cursor.fetchone()[0]

    conn.close()

    print(f"\n📊 DB 통계 (LEGION MODE):")
    print(f"   전체: {legion_count}개")
    print(f"   🔥 S급: {s_count}개")
    print(f"   🟢 A급: {a_count}개")
    print(f"   S/A급: {s_count + a_count}개")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python restore_legion_csv.py <csv_file>")
        sys.exit(1)

    csv_file = sys.argv[1]

    if not os.path.exists(csv_file):
        print(f"❌ 파일 없음: {csv_file}")
        sys.exit(1)

    restore_csv_to_db(csv_file)
