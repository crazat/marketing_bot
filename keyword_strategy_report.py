#!/usr/bin/env python3
"""
키워드 전략 리포트 생성기
- 티어별 키워드 분류
- 블로그 포스팅 우선순위 제안
- 카테고리별 최적 키워드 추출
"""
import sqlite3
import csv
from datetime import datetime

def generate_report():
    conn = sqlite3.connect('db/marketing_data.db')
    cursor = conn.cursor()

    print("=" * 80)
    print("📊 키워드 전략 리포트")
    print(f"   생성일: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 80)

    # ============================================================
    # 1. 티어별 키워드 분류
    # ============================================================
    print("\n" + "=" * 80)
    print("🏆 TIER 1: Platinum (KEI 500+) - 최우선 공략")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 500
        ORDER BY opp_score DESC
    ''')
    tier1 = cursor.fetchall()
    if tier1:
        for row in tier1:
            print(f"⭐ {row[0]} | 검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | {row[4]}")
    else:
        print("   (없음)")
    print(f"\n   총 {len(tier1)}개")

    print("\n" + "=" * 80)
    print("🥇 TIER 2: Gold (KEI 300-499) - 적극 공략")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 300 AND opp_score < 500
        ORDER BY opp_score DESC
    ''')
    tier2 = cursor.fetchall()
    for row in tier2:
        print(f"🥇 {row[0]} | 검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | {row[4]}")
    print(f"\n   총 {len(tier2)}개")

    print("\n" + "=" * 80)
    print("🥈 TIER 3: Silver (KEI 100-299) - 보조 공략")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 100 AND opp_score < 300
        ORDER BY opp_score DESC
        LIMIT 20
    ''')
    tier3 = cursor.fetchall()
    for row in tier3:
        print(f"🥈 {row[0]} | 검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | {row[4]}")

    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 100 AND opp_score < 300')
    tier3_count = cursor.fetchone()[0]
    print(f"\n   총 {tier3_count}개 (상위 20개 표시)")

    print("\n" + "=" * 80)
    print("🥉 TIER 4: Bronze (KEI 50-99) - Longtail 전략")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 50 AND opp_score < 100
        ORDER BY opp_score DESC
        LIMIT 20
    ''')
    tier4 = cursor.fetchall()
    for row in tier4:
        print(f"🥉 {row[0]} | 검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | {row[4]}")

    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 50 AND opp_score < 100')
    tier4_count = cursor.fetchone()[0]
    print(f"\n   총 {tier4_count}개 (상위 20개 표시)")

    # ============================================================
    # 2. 검색량 기준 효율적인 키워드 (검색량 100+ AND 공급 10,000 이하)
    # ============================================================
    print("\n" + "=" * 80)
    print("🎯 효율적인 키워드 (검색량 100+ AND 공급 10,000 이하)")
    print("   → 실제 수요 있고 경쟁 가능한 키워드")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE search_volume >= 100 AND volume <= 10000
        ORDER BY opp_score DESC
        LIMIT 30
    ''')
    efficient = cursor.fetchall()
    for i, row in enumerate(efficient, 1):
        print(f"{i:2d}. {row[0]} | 검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | {row[4]}")

    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE search_volume >= 100 AND volume <= 10000')
    efficient_count = cursor.fetchone()[0]
    print(f"\n   총 {efficient_count}개 (상위 30개 표시)")

    # ============================================================
    # 3. 카테고리별 TOP 3 키워드
    # ============================================================
    print("\n" + "=" * 80)
    print("📁 카테고리별 TOP 3 키워드 (블로그 주제 추천)")
    print("=" * 80)

    cursor.execute('SELECT DISTINCT category FROM keyword_insights ORDER BY category')
    categories = [row[0] for row in cursor.fetchall()]

    for cat in categories:
        cursor.execute('''
            SELECT keyword, search_volume, volume, opp_score
            FROM keyword_insights
            WHERE category = ?
            ORDER BY opp_score DESC
            LIMIT 3
        ''', (cat,))
        top3 = cursor.fetchall()

        if top3:
            print(f"\n📌 [{cat}]")
            for i, row in enumerate(top3, 1):
                kei_emoji = "⭐" if row[3] >= 300 else "🔹" if row[3] >= 100 else "▪️"
                print(f"   {i}. {kei_emoji} {row[0]} (검색량: {row[1]:,}, KEI: {row[3]:.0f})")

    # ============================================================
    # 4. 구매 의도 키워드 (가격, 비용, 후기, 추천 포함)
    # ============================================================
    print("\n" + "=" * 80)
    print("💰 구매 의도 키워드 (가격/비용/후기/추천 포함)")
    print("   → 전환율 높은 키워드")
    print("=" * 80)
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category
        FROM keyword_insights
        WHERE (keyword LIKE '%가격%' OR keyword LIKE '%비용%'
               OR keyword LIKE '%후기%' OR keyword LIKE '%추천%')
        ORDER BY opp_score DESC
        LIMIT 20
    ''')
    intent_keywords = cursor.fetchall()
    for i, row in enumerate(intent_keywords, 1):
        print(f"{i:2d}. {row[0]} | 검색량: {row[1]:,} | KEI: {row[3]:.0f} | {row[4]}")
    print(f"\n   총 {len(intent_keywords)}개 (상위 20개 표시)")

    # ============================================================
    # 5. 지역 특화 키워드 (동네명 포함)
    # ============================================================
    print("\n" + "=" * 80)
    print("📍 지역 특화 키워드 (동네명 포함)")
    print("   → 지역 밀착 SEO 전략")
    print("=" * 80)
    dong_names = ['복대동', '가경동', '율량동', '산남동', '용암동', '오창', '오송']
    for dong in dong_names:
        cursor.execute('''
            SELECT keyword, search_volume, volume, opp_score, category
            FROM keyword_insights
            WHERE keyword LIKE ?
            ORDER BY opp_score DESC
            LIMIT 3
        ''', (f'%{dong}%',))
        dong_kws = cursor.fetchall()
        if dong_kws:
            print(f"\n📍 [{dong}]")
            for row in dong_kws:
                print(f"   • {row[0]} (검색량: {row[1]:,}, KEI: {row[3]:.0f})")

    # ============================================================
    # 6. 블로그 포스팅 우선순위 TOP 30
    # ============================================================
    print("\n" + "=" * 80)
    print("📝 블로그 포스팅 우선순위 TOP 30")
    print("   (KEI × 검색량 가중치 기준)")
    print("=" * 80)
    cursor.execute('''
        SELECT
            keyword,
            search_volume,
            volume,
            opp_score,
            category,
            (opp_score * LOG(search_volume + 1)) as priority_score
        FROM keyword_insights
        WHERE opp_score >= 30
        ORDER BY priority_score DESC
        LIMIT 30
    ''')
    priority = cursor.fetchall()
    for i, row in enumerate(priority, 1):
        print(f"{i:2d}. {row[0]}")
        print(f"    검색량: {row[1]:,} | 공급: {row[2]:,} | KEI: {row[3]:.0f} | 우선순위 점수: {row[5]:.0f}")

    # ============================================================
    # 7. CSV 내보내기
    # ============================================================
    print("\n" + "=" * 80)
    print("📥 CSV 파일 내보내기")
    print("=" * 80)

    # 전체 키워드 CSV
    cursor.execute('''
        SELECT keyword, search_volume, volume, opp_score, category,
               CASE
                   WHEN opp_score >= 500 THEN 'Platinum'
                   WHEN opp_score >= 300 THEN 'Gold'
                   WHEN opp_score >= 100 THEN 'Silver'
                   WHEN opp_score >= 50 THEN 'Bronze'
                   ELSE 'Standard'
               END as tier
        FROM keyword_insights
        ORDER BY opp_score DESC
    ''')
    all_keywords = cursor.fetchall()

    filename = f'keyword_strategy_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['키워드', '검색량', '공급(블로그수)', 'KEI', '카테고리', '티어'])
        writer.writerows(all_keywords)

    print(f"✅ 전체 키워드 저장: {filename}")

    # 우선순위 TOP 100 CSV
    cursor.execute('''
        SELECT
            keyword,
            search_volume,
            volume,
            opp_score,
            category,
            CASE
                WHEN opp_score >= 500 THEN 'Platinum'
                WHEN opp_score >= 300 THEN 'Gold'
                WHEN opp_score >= 100 THEN 'Silver'
                WHEN opp_score >= 50 THEN 'Bronze'
                ELSE 'Standard'
            END as tier
        FROM keyword_insights
        WHERE opp_score >= 30
        ORDER BY (opp_score * LOG(search_volume + 1)) DESC
        LIMIT 100
    ''')
    top100 = cursor.fetchall()

    filename_top = f'keyword_priority_top100_{datetime.now().strftime("%Y%m%d_%H%M")}.csv'
    with open(filename_top, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.writer(f)
        writer.writerow(['키워드', '검색량', '공급(블로그수)', 'KEI', '카테고리', '티어'])
        writer.writerows(top100)

    print(f"✅ 우선순위 TOP 100 저장: {filename_top}")

    # ============================================================
    # 8. 요약 통계
    # ============================================================
    print("\n" + "=" * 80)
    print("📊 요약 통계")
    print("=" * 80)

    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 500')
    platinum = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 300 AND opp_score < 500')
    gold = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 100 AND opp_score < 300')
    silver = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score >= 50 AND opp_score < 100')
    bronze = cursor.fetchone()[0]
    cursor.execute('SELECT COUNT(*) FROM keyword_insights WHERE opp_score < 50')
    standard = cursor.fetchone()[0]

    total = platinum + gold + silver + bronze + standard

    print(f"""
┌─────────────────────────────────────────────────────────────┐
│  티어          │  개수      │  비율      │  전략              │
├─────────────────────────────────────────────────────────────┤
│  ⭐ Platinum   │  {platinum:4d}개    │  {platinum/total*100:5.1f}%   │  최우선 공략       │
│  🥇 Gold       │  {gold:4d}개    │  {gold/total*100:5.1f}%   │  적극 공략         │
│  🥈 Silver     │  {silver:4d}개    │  {silver/total*100:5.1f}%   │  보조 공략         │
│  🥉 Bronze     │  {bronze:4d}개    │  {bronze/total*100:5.1f}%   │  Longtail 전략    │
│  ▪️ Standard   │  {standard:4d}개    │  {standard/total*100:5.1f}%   │  경쟁 심함 (보류)  │
├─────────────────────────────────────────────────────────────┤
│  총계          │  {total:4d}개    │  100.0%   │                    │
└─────────────────────────────────────────────────────────────┘
""")

    print("\n" + "=" * 80)
    print("💡 블로그 포스팅 전략 권장사항")
    print("=" * 80)
    print("""
1. 🎯 핵심 전략: Platinum + Gold 키워드 집중 공략
   - Platinum (1개): 반드시 1위 노려야 함
   - Gold (3개): 적극적으로 콘텐츠 생산

2. 📝 콘텐츠 생산 순서:
   ① Platinum/Gold 키워드로 메인 포스트 작성
   ② Silver 키워드로 서브 포스트 작성 (메인 포스트 링크)
   ③ Bronze 키워드로 Longtail 포스트 (틈새 공략)

3. 🔗 내부 링크 전략:
   - 모든 서브 포스트에서 메인 포스트로 링크
   - 관련 카테고리 포스트끼리 상호 링크

4. 📍 지역 밀착 전략:
   - 동네명 포함 키워드 우선 공략 (가경동, 복대동, 오창 등)
   - 경쟁이 낮고 지역 특화 가능

5. 💰 전환 최적화:
   - '가격', '비용', '후기' 키워드는 전환율 높음
   - CTA(Call to Action) 강화
""")

    conn.close()
    print("\n✅ 리포트 생성 완료!")

if __name__ == "__main__":
    generate_report()
