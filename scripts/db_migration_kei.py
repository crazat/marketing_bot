#!/usr/bin/env python3
"""
DB Migration: KEI 컬럼 추가
- keyword_insights: document_count, kei, kei_grade 추가
- serp_cache: document_count 추가
"""
import sqlite3
import os
import sys
from datetime import datetime

# 상위 디렉토리 추가 (utils import용)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def migrate_keyword_insights(conn: sqlite3.Connection):
    """keyword_insights 테이블에 KEI 컬럼 추가"""
    cursor = conn.cursor()

    # 추가할 컬럼 목록
    columns_to_add = [
        ("document_count", "INTEGER DEFAULT 0"),
        ("kei", "REAL DEFAULT 0.0"),
        ("kei_grade", "TEXT DEFAULT 'C'"),
    ]

    # 기존 컬럼 확인
    cursor.execute("PRAGMA table_info(keyword_insights)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    added_count = 0
    for col_name, col_type in columns_to_add:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE keyword_insights ADD COLUMN {col_name} {col_type}")
                print(f"  ✅ keyword_insights.{col_name} 추가됨")
                added_count += 1
            except sqlite3.OperationalError as e:
                print(f"  ⚠️ keyword_insights.{col_name} 추가 실패: {e}")
        else:
            print(f"  ℹ️ keyword_insights.{col_name} 이미 존재")

    return added_count


def migrate_serp_cache(conn: sqlite3.Connection):
    """serp_cache 테이블에 document_count 컬럼 추가"""
    cursor = conn.cursor()

    # serp_cache 테이블 존재 확인
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='serp_cache'")
    if not cursor.fetchone():
        print("  ℹ️ serp_cache 테이블 없음 - 생성 중...")
        cursor.execute('''
            CREATE TABLE serp_cache (
                keyword TEXT PRIMARY KEY,
                difficulty INTEGER,
                opportunity INTEGER,
                grade TEXT,
                document_count INTEGER DEFAULT 0,
                cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_serp_cached_at ON serp_cache(cached_at)')
        print("  ✅ serp_cache 테이블 생성됨 (document_count 포함)")
        return 1

    # 기존 컬럼 확인
    cursor.execute("PRAGMA table_info(serp_cache)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    if "document_count" not in existing_columns:
        try:
            cursor.execute("ALTER TABLE serp_cache ADD COLUMN document_count INTEGER DEFAULT 0")
            print("  ✅ serp_cache.document_count 추가됨")
            return 1
        except sqlite3.OperationalError as e:
            print(f"  ⚠️ serp_cache.document_count 추가 실패: {e}")
            return 0
    else:
        print("  ℹ️ serp_cache.document_count 이미 존재")
        return 0


def recalculate_existing_kei(conn: sqlite3.Connection):
    """
    기존 데이터의 KEI 재계산
    KEI = 검색량² / 총문서수
    """
    cursor = conn.cursor()

    # 검색량과 document_count가 있는 키워드 조회
    cursor.execute("""
        SELECT keyword, search_volume, document_count
        FROM keyword_insights
        WHERE search_volume > 0
    """)
    rows = cursor.fetchall()

    if not rows:
        print("  ℹ️ 재계산할 데이터 없음")
        return 0

    updated = 0
    for keyword, search_volume, document_count in rows:
        # document_count가 없으면 추정값 사용
        if not document_count or document_count <= 0:
            # 난이도 기반 추정: difficulty가 높을수록 문서 수가 많다고 가정
            cursor.execute("SELECT difficulty FROM keyword_insights WHERE keyword = ?", (keyword,))
            diff_row = cursor.fetchone()
            difficulty = diff_row[0] if diff_row and diff_row[0] else 50

            # 추정 공식: 난이도 1당 1000문서 기준
            document_count = max(1000, difficulty * 1000)

        # KEI 계산
        kei = round((search_volume ** 2) / document_count, 2)

        # KEI 등급 결정
        if kei >= 500:
            kei_grade = 'S'
        elif kei >= 200:
            kei_grade = 'A'
        elif kei >= 50:
            kei_grade = 'B'
        else:
            kei_grade = 'C'

        cursor.execute("""
            UPDATE keyword_insights
            SET kei = ?, kei_grade = ?, document_count = ?
            WHERE keyword = ?
        """, (kei, kei_grade, document_count, keyword))
        updated += 1

    return updated


def main():
    """마이그레이션 메인 함수"""
    print("=" * 60)
    print("🔧 KEI 컬럼 마이그레이션")
    print("=" * 60)

    # DB 경로
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(base_dir, "db", "marketing_data.db")
    serp_cache_path = os.path.join(base_dir, "db", "serp_cache.db")

    # 1. marketing_data.db 마이그레이션
    print(f"\n📂 DB 경로: {db_path}")

    if not os.path.exists(db_path):
        print("❌ marketing_data.db 파일이 없습니다.")
        return

    conn = sqlite3.connect(db_path)

    print("\n[1/3] keyword_insights 테이블 마이그레이션...")
    added_kw = migrate_keyword_insights(conn)

    conn.commit()

    # 2. serp_cache.db 마이그레이션
    print(f"\n📂 SERP 캐시 경로: {serp_cache_path}")

    serp_conn = sqlite3.connect(serp_cache_path)

    print("\n[2/3] serp_cache 테이블 마이그레이션...")
    added_serp = migrate_serp_cache(serp_conn)

    serp_conn.commit()
    serp_conn.close()

    # 3. 기존 데이터 KEI 재계산
    print("\n[3/3] 기존 데이터 KEI 재계산...")
    updated = recalculate_existing_kei(conn)
    print(f"  ✅ {updated}개 키워드 KEI 재계산 완료")

    conn.commit()
    conn.close()

    # 결과 요약
    print("\n" + "=" * 60)
    print("📊 마이그레이션 결과")
    print("=" * 60)
    print(f"  keyword_insights 컬럼 추가: {added_kw}개")
    print(f"  serp_cache 컬럼 추가: {added_serp}개")
    print(f"  KEI 재계산: {updated}개")

    # 스키마 확인
    print("\n[검증] keyword_insights 스키마:")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("PRAGMA table_info(keyword_insights)")
    for row in cursor.fetchall():
        print(f"  - {row[1]} ({row[2]})")
    conn.close()

    print("\n✅ 마이그레이션 완료!")


if __name__ == "__main__":
    main()
