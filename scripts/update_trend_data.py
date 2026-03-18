#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
트렌드 데이터 업데이트 스크립트
Unknown 상태의 키워드에 대해 트렌드 분석 수행
"""

import sys
import os
import sqlite3
from pathlib import Path

# UTF-8 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

# 프로젝트 루트 경로 추가
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def update_trend_data():
    """Unknown 트렌드 데이터 업데이트"""

    # DataLab 매니저 import
    try:
        from scrapers.naver_datalab_manager import NaverDataLabManager
        datalab = NaverDataLabManager()
        print("[1] Naver DataLab 로드 성공")
    except Exception as e:
        print(f"[ERROR] DataLab 로드 실패: {e}")
        print(f"   트렌드 분석 없이 진행합니다.")
        return

    # DB 연결
    db_path = project_root / "db" / "marketing_data.db"

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

    # Unknown 트렌드 키워드 조회
    cursor.execute("""
        SELECT keyword, grade, source
        FROM keyword_insights
        WHERE (trend_status = 'unknown' OR trend_status IS NULL)
        AND source LIKE 'round%'
        ORDER BY
            CASE grade
                WHEN 'S' THEN 1
                WHEN 'A' THEN 2
                WHEN 'B' THEN 3
                ELSE 4
            END,
            keyword
    """)

    unknown_keywords = cursor.fetchall()
    total = len(unknown_keywords)

    print(f"[3] Unknown 트렌드 키워드: {total}개")

    if total == 0:
        print("[INFO] 업데이트할 키워드가 없습니다.")
        conn.close()
        return

    # 트렌드 분석
    updated = 0
    errors = 0

    print(f"\n[4] 트렌드 분석 시작...")

    for i, (keyword, grade, source) in enumerate(unknown_keywords, 1):
        try:
            # 트렌드 분석
            slope = datalab.get_trend_slope(keyword)

            if slope is not None:
                # 트렌드 상태 판정
                if slope > 0.3:
                    trend_status = "rising"
                elif slope < -0.3:
                    trend_status = "falling"
                else:
                    trend_status = "stable"

                # DB 업데이트
                cursor.execute("""
                    UPDATE keyword_insights
                    SET trend_slope = ?, trend_status = ?
                    WHERE keyword = ?
                """, (slope, trend_status, keyword))

                updated += 1

                if updated % 5 == 0:
                    print(f"   진행: {updated}/{total} ({updated/total*100:.1f}%)")
                    conn.commit()  # 중간 저장

            else:
                # slope가 None이면 unknown 유지
                pass

        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"   [WARNING] 에러: {keyword} - {e}")

        # API Rate Limit
        if i % 20 == 0:
            import time
            time.sleep(1)

    conn.commit()
    conn.close()

    print(f"\n{'='*70}")
    print(f"[완료] 트렌드 데이터 업데이트")
    print(f"   업데이트: {updated}개")
    if errors:
        print(f"   에러: {errors}개")
    print(f"{'='*70}")

    # 최종 통계
    conn = sqlite3.connect(db_path, timeout=30)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN trend_status = 'rising' THEN 1 ELSE 0 END) as rising,
            SUM(CASE WHEN trend_status = 'falling' THEN 1 ELSE 0 END) as falling,
            SUM(CASE WHEN trend_status = 'stable' THEN 1 ELSE 0 END) as stable,
            SUM(CASE WHEN trend_status = 'unknown' THEN 1 ELSE 0 END) as unknown
        FROM keyword_insights
        WHERE source LIKE 'round%'
    """)

    result = cursor.fetchone()

    print(f"\n[최종 통계 - LEGION MODE]")
    print(f"   총 키워드: {result[0]}개")
    print(f"   📈 Rising: {result[1]}개 ({result[1]/result[0]*100:.1f}%)")
    print(f"   📉 Falling: {result[2]}개 ({result[2]/result[0]*100:.1f}%)")
    print(f"   ➡️ Stable: {result[3]}개 ({result[3]/result[0]*100:.1f}%)")
    print(f"   ❓ Unknown: {result[4]}개 ({result[4]/result[0]*100:.1f}%)")

    conn.close()

if __name__ == "__main__":
    update_trend_data()
