#!/usr/bin/env python3
"""
Pathfinder V3 실행 스크립트
- Naver 자동완성 기반 실제 검색 키워드 수집
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from pathfinder import Pathfinder

def main():
    print("=" * 60)
    print("🚀 Pathfinder V3: Naver 자동완성 기반 키워드 수집")
    print("=" * 60)

    pf = Pathfinder()

    # V3 실행 (최대 300개 키워드)
    count = pf.run_campaign_v3(max_keywords=300)

    print("\n" + "=" * 60)
    print(f"✅ 완료! 총 {count}개 키워드 저장")
    print("=" * 60)

    # 결과 확인
    print("\n📊 DB 확인...")
    import sqlite3
    from utils import ConfigManager

    conn = sqlite3.connect(ConfigManager().db_path)
    cursor = conn.cursor()

    # 전체 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as kei_500,
            COUNT(CASE WHEN opp_score >= 300 AND opp_score < 500 THEN 1 END) as kei_300,
            AVG(search_volume) as avg_vol,
            AVG(opp_score) as avg_kei
        FROM keyword_insights
    """)
    row = cursor.fetchone()

    print(f"\n📈 전체 통계:")
    print(f"   - 총 키워드: {row[0]:,}개")
    print(f"   - KEI 500+ (Golden): {row[1]}개 ({row[1]/max(1,row[0])*100:.1f}%)")
    print(f"   - KEI 300-499 (Gold): {row[2]}개")
    print(f"   - 평균 검색량: {row[3]:.0f}" if row[3] else "   - 평균 검색량: N/A")
    print(f"   - 평균 KEI: {row[4]:.0f}" if row[4] else "   - 평균 KEI: N/A")

    # 카테고리별 분포
    print(f"\n📁 카테고리별 분포:")
    cursor.execute("""
        SELECT category, COUNT(*) as cnt, COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as golden
        FROM keyword_insights
        GROUP BY category
        ORDER BY cnt DESC
    """)
    for cat, cnt, golden in cursor.fetchall():
        print(f"   - {cat}: {cnt}개 (Golden: {golden})")

    # Top 10 Golden Keywords
    print(f"\n💎 Top 10 Golden Keywords (KEI 500+):")
    cursor.execute("""
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 500
        ORDER BY opp_score DESC
        LIMIT 10
    """)
    for i, (kw, vol, supply, kei, cat) in enumerate(cursor.fetchall(), 1):
        print(f"   {i}. {kw}")
        print(f"      검색량: {vol:,} | 공급: {supply:,} | KEI: {kei:.0f} | {cat}")

    conn.close()


if __name__ == "__main__":
    main()
