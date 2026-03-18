#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEGION MODE CSV 결과를 DB로 import
"""

import sys
import os
from pathlib import Path
import pandas as pd
import sqlite3
from datetime import datetime

# UTF-8 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def import_legion_csv():
    """legion_v3_results.csv를 DB로 import"""

    project_root = Path(__file__).parent.parent
    csv_path = project_root / "legion_v3_results.csv"
    db_path = project_root / "db" / "marketing_data.db"

    if not csv_path.exists():
        print(f"❌ CSV 파일 없음: {csv_path}")
        return

    print(f"📂 CSV 읽기: {csv_path}")
    df = pd.read_csv(csv_path, encoding='utf-8')

    print(f"   총 {len(df)}개 키워드")
    print(f"   컬럼: {list(df.columns)}")

    # DB 연결
    print(f"\n💾 DB 연결: {db_path}")
    conn = sqlite3.connect(str(db_path), timeout=30)
    cursor = conn.cursor()

    # WAL 모드
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    saved = 0
    errors = 0

    print("\n⏳ DB 저장 중...")

    for idx, row in df.iterrows():
        try:
            keyword = row['keyword']
            search_volume = int(row.get('search_volume', 0))
            difficulty = int(row.get('difficulty', 50))
            opportunity = int(row.get('opportunity', 50))
            priority_v3 = float(row.get('priority_v3', 0))
            grade = row.get('grade', 'C')
            category = row.get('category', '기타')
            source = row.get('source', 'legion')
            trend_slope = float(row.get('trend_slope', 0.0))
            trend_status = row.get('trend_status', 'unknown')

            # 지역 추출
            region = "청주"
            for reg in ["청주", "충주", "제천", "진천", "증평"]:
                if reg in keyword:
                    region = reg
                    break

            # 태그 추출
            tag = "일반"
            if any(w in keyword for w in ["가격", "비용"]):
                tag = "구매의도"
            elif any(w in keyword for w in ["후기", "추천"]):
                tag = "신뢰의도"

            cursor.execute('''
                INSERT INTO keyword_insights (
                    keyword, volume, competition, opp_score, tag, created_at,
                    search_volume, region, category,
                    difficulty, opportunity, priority_v3, grade, source,
                    trend_slope, trend_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(keyword) DO UPDATE SET
                    difficulty=excluded.difficulty,
                    opportunity=excluded.opportunity,
                    priority_v3=excluded.priority_v3,
                    grade=excluded.grade,
                    source=excluded.source,
                    trend_slope=excluded.trend_slope,
                    trend_status=excluded.trend_status,
                    created_at=excluded.created_at
            ''', (
                keyword, 0, "Low" if difficulty < 50 else "High",
                priority_v3, tag, now,
                search_volume, region, category,
                difficulty, opportunity, priority_v3, grade, source,
                trend_slope, trend_status
            ))
            saved += 1

            # 진행 상황 표시
            if (idx + 1) % 100 == 0:
                conn.commit()
                print(f"   진행: {saved}/{len(df)}...")

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"   오류 ({keyword}): {e}")

    # 최종 커밋
    conn.commit()
    conn.close()

    print(f"\n✅ {saved}/{len(df)}개 저장 완료" + (f" (에러: {errors}개)" if errors else ""))

    # 등급별 통계
    cursor = sqlite3.connect(str(db_path)).cursor()
    cursor.execute("SELECT grade, COUNT(*) FROM keyword_insights WHERE source LIKE '%round%' OR source='legion' GROUP BY grade")
    stats = dict(cursor.fetchall())

    print("\n📊 LEGION MODE DB 통계:")
    for grade in ['S', 'A', 'B', 'C']:
        count = stats.get(grade, 0)
        emoji = {'S': '🔥', 'A': '🟢', 'B': '🔵', 'C': '⚪'}[grade]
        print(f"   {emoji} {grade}급: {count}개")

    sa_count = stats.get('S', 0) + stats.get('A', 0)
    print(f"\n   🎯 S/A급 합계: {sa_count}개")

if __name__ == "__main__":
    print("=" * 70)
    print("LEGION MODE CSV → DB Import")
    print("=" * 70)
    import_legion_csv()
