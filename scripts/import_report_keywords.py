#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
보고서 키워드를 DB에 추가
"""

import sys
import os
import csv
import sqlite3
from pathlib import Path

# UTF-8 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def import_report_keywords():
    """보고서 키워드를 DB에 추가"""

    # 1. CSV 읽기
    csv_file = "report_keywords_analysis.csv"
    if not os.path.exists(csv_file):
        print(f"[ERROR] CSV 파일 없음: {csv_file}")
        return

    keywords_data = []
    with open(csv_file, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            keywords_data.append(row)

    print(f"[1] CSV에서 {len(keywords_data)}개 키워드 읽음")

    # 2. DB 연결
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / "db" / "marketing_data.db"

    max_retries = 5
    retry_delay = 2
    conn = None

    for attempt in range(max_retries):
        try:
            conn = sqlite3.connect(db_path, timeout=120)
            cursor = conn.cursor()

            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=60000")
            break
        except sqlite3.OperationalError as e:
            if attempt < max_retries - 1:
                print(f"   [WARNING] DB 잠금 감지 (시도 {attempt+1}/{max_retries}), {retry_delay}초 후 재시도...")
                import time
                time.sleep(retry_delay)
                retry_delay *= 2
            else:
                print(f"[ERROR] DB 연결 실패: {e}")
                return

    print(f"[2] DB 연결 성공: {db_path}")

    # 3. 기존 키워드 확인
    cursor.execute("SELECT keyword FROM keyword_insights")
    existing_keywords = set([row[0] for row in cursor.fetchall()])

    # 4. 신규 키워드만 필터링
    new_keywords = []
    for row in keywords_data:
        if row['keyword'] not in existing_keywords:
            new_keywords.append(row)

    print(f"[3] 신규 키워드: {len(new_keywords)}개")

    if len(new_keywords) == 0:
        print("[INFO] 추가할 신규 키워드가 없습니다.")
        conn.close()
        return

    # 5. 키워드 추가
    added = 0
    errors = 0

    for row in new_keywords:
        try:
            keyword = row['keyword']
            category = row['category']
            source_type = row['type']  # main, sub, blog

            # 기본값 설정 (보고서 키워드는 B급으로 시작)
            difficulty = 60  # 보통 난이도
            opportunity = 50  # 보통 기회
            grade = 'B'  # B급으로 시작
            priority = 40  # 보통 우선순위
            search_volume = 30  # 추정 검색량

            # 야간진료, 교통사고 등은 A급으로
            if '야간진료' in keyword or '교통사고' in keyword or '한방병원' in keyword:
                grade = 'A'
                priority = 60
                difficulty = 50
                opportunity = 60
                search_volume = 50

            cursor.execute('''
                INSERT INTO keyword_insights (
                    keyword, search_volume, difficulty, opportunity,
                    grade, category, priority_v3, source,
                    volume, competition, opp_score, tag, region
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                keyword, search_volume, difficulty, opportunity,
                grade, category, priority, f'report_{source_type}',
                search_volume, 'medium', priority, grade, '청주'
            ))

            added += 1

            if added % 10 == 0:
                print(f"   진행: {added}/{len(new_keywords)}...")

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"   [WARNING] 에러: {keyword} - {e}")

    conn.commit()
    conn.close()

    print(f"\n{'='*70}")
    print(f"[완료] 보고서 키워드 추가")
    print(f"   추가: {added}개")
    if errors:
        print(f"   에러: {errors}개")
    print(f"{'='*70}")

    # 6. 통계 출력
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE source LIKE 'report_%'")
    report_total = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE source LIKE 'report_%' AND grade IN ('S', 'A')")
    report_sa = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM keyword_insights")
    total = cursor.fetchone()[0]

    conn.close()

    print(f"\n[DB 통계]")
    print(f"   보고서 키워드: {report_total}개 (S/A급: {report_sa}개)")
    print(f"   전체 키워드: {total}개")

if __name__ == "__main__":
    import_report_keywords()
