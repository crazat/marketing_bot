#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
카테고리 표준화 스크립트
중복/변형된 카테고리를 표준 카테고리로 통일
"""

import sys
import os
import sqlite3
from pathlib import Path

# UTF-8 설정
if os.name == 'nt':
    sys.stdout.reconfigure(encoding='utf-8')

def standardize_categories():
    """카테고리 표준화"""

    # 카테고리 매핑 (LEGION MODE와 동일)
    CATEGORY_MAPPING = {
        "안면비대칭": ["안면비대칭", "얼굴비대칭", "턱비대칭", "비대칭교정", "안면비대칭_교정", "안면비대칭교정"],
        "체형교정": ["체형교정", "골반교정", "척추교정", "자세교정", "휜다리", "체형교정_골반"],
        "교통사고": ["교통사고", "자동차사고", "후유증", "입원", "교통사고_입원", "교통사고입원"],
        "피부/여드름": ["여드름", "여드름흉터", "새살침", "피부", "아토피", "흉터", "여드름_피부", "피부여드름"],
        "다이어트": ["다이어트", "비만", "살빼", "체중", "다이어트_비만"],
        "통증": ["통증", "디스크", "허리", "어깨", "무릎", "관절", "통증_디스크"],
        "탈모": ["탈모", "두피", "원형탈모", "탈모_두피"],
        "비염": ["비염", "알레르기", "축농증", "비염_알레르기"],
        "여성건강": ["갱년기", "생리", "산후", "불임", "여성건강_산후"],
        "기타": ["불면", "두통", "어지럼", "소화", "한의원", "기타"]
    }

    # 역매핑 생성 (변형 → 표준)
    reverse_mapping = {}
    for standard, variants in CATEGORY_MAPPING.items():
        for variant in variants:
            reverse_mapping[variant] = standard

    # DB 연결
    base_dir = Path(__file__).parent.parent
    db_path = base_dir / "db" / "marketing_data.db"

    print("=" * 70)
    print("카테고리 표준화")
    print("=" * 70)
    print(f"\n💾 DB: {db_path}")

    conn = sqlite3.connect(str(db_path), timeout=30)
    cursor = conn.cursor()

    # WAL 모드
    cursor.execute("PRAGMA journal_mode=WAL")

    # 현재 카테고리 분포 확인
    print("\n📊 현재 카테고리 분포:")
    cursor.execute("SELECT category, COUNT(*) FROM keyword_insights GROUP BY category ORDER BY COUNT(*) DESC")
    current_categories = cursor.fetchall()

    for cat, count in current_categories:
        standard = reverse_mapping.get(cat, cat)
        if cat != standard:
            print(f"   ⚠️  {cat}: {count}개 → {standard}")
        else:
            print(f"   ✓  {cat}: {count}개")

    # 변경 필요한 카테고리 찾기
    updates_needed = []
    for cat, count in current_categories:
        standard = reverse_mapping.get(cat, cat)
        if cat != standard:
            updates_needed.append((cat, standard, count))

    if not updates_needed:
        print("\n✅ 모든 카테고리가 이미 표준화되어 있습니다.")
        conn.close()
        return

    # 변경 실행
    print(f"\n🔧 {len(updates_needed)}개 카테고리 표준화 중...")

    total_updated = 0
    for old_cat, new_cat, count in updates_needed:
        cursor.execute(
            "UPDATE keyword_insights SET category = ? WHERE category = ?",
            (new_cat, old_cat)
        )
        updated = cursor.rowcount
        total_updated += updated
        print(f"   {old_cat} → {new_cat}: {updated}개")

    conn.commit()

    # 최종 결과 확인
    print(f"\n✅ 총 {total_updated}개 키워드 업데이트 완료")

    print("\n📊 표준화 후 카테고리 분포:")
    cursor.execute("SELECT category, COUNT(*) FROM keyword_insights GROUP BY category ORDER BY COUNT(*) DESC")
    final_categories = cursor.fetchall()

    for cat, count in final_categories:
        print(f"   {cat}: {count}개")

    conn.close()
    print("\n" + "=" * 70)

if __name__ == "__main__":
    standardize_categories()
