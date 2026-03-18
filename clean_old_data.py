#!/usr/bin/env python3
"""
DB에서 오래된 실행 데이터 삭제 (최근 6시간 데이터만 유지)
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
import sqlite3
from datetime import datetime, timedelta

DB_PATH = "db/marketing_data.db"

def clean_old_data(hours_to_keep: int = 6):
    """오래된 데이터 삭제"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 삭제 전 통계
    cursor.execute("SELECT COUNT(*), grade FROM keyword_insights GROUP BY grade")
    before_stats = {row[1]: row[0] for row in cursor.fetchall()}

    print("=" * 80)
    print("🗑️ 오래된 데이터 삭제")
    print("=" * 80)
    print()
    print("📊 삭제 전:")
    for grade in ['S', 'A', 'B', 'C']:
        count = before_stats.get(grade, 0)
        print(f"   {grade}급: {count}개")

    # 최근 N시간 데이터만 유지
    cutoff = datetime.now() - timedelta(hours=hours_to_keep)
    cutoff_str = cutoff.strftime('%Y-%m-%d %H:%M:%S')

    print()
    print(f"🕐 기준 시간: {cutoff_str} 이전 데이터 삭제")
    print()

    # 삭제할 데이터 확인
    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE created_at < ?", (cutoff_str,))
    to_delete = cursor.fetchone()[0]

    if to_delete == 0:
        print("✅ 삭제할 데이터가 없습니다.")
        conn.close()
        return

    print(f"⚠️ {to_delete}개 레코드를 삭제합니다...")

    # 삭제 실행
    cursor.execute("DELETE FROM keyword_insights WHERE created_at < ?", (cutoff_str,))
    conn.commit()

    # 삭제 후 통계
    cursor.execute("SELECT COUNT(*), grade FROM keyword_insights GROUP BY grade")
    after_stats = {row[1]: row[0] for row in cursor.fetchall()}

    print()
    print("📊 삭제 후:")
    for grade in ['S', 'A', 'B', 'C']:
        count = after_stats.get(grade, 0)
        before = before_stats.get(grade, 0)
        print(f"   {grade}급: {count}개 (이전: {before}개, {count - before:+d})")

    # VACUUM으로 DB 크기 최적화
    print()
    print("🔧 DB 최적화 중...")
    cursor.execute("VACUUM")

    conn.close()

    print()
    print(f"✅ 완료! {to_delete}개 레코드 삭제됨")
    print()
    print("💡 대시보드를 새로고침하면 최신 데이터만 표시됩니다.")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="오래된 키워드 데이터 삭제")
    parser.add_argument("--hours", type=int, default=6, help="유지할 시간 (기본: 6시간)")
    parser.add_argument("--yes", action="store_true", help="확인 없이 바로 삭제")

    args = parser.parse_args()

    if not args.yes:
        print(f"⚠️ {args.hours}시간 이전 데이터를 삭제합니다.")
        confirm = input("계속하시겠습니까? (yes/no): ")
        if confirm.lower() != 'yes':
            print("취소되었습니다.")
            sys.exit(0)

    clean_old_data(args.hours)
