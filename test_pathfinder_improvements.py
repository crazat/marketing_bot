"""
Pathfinder 개선사항 검증 스크립트
- AI Seed 생성 확인
- 최소 검색량 필터 확인
- Dashboard 메트릭 확인
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from pathfinder import Pathfinder
import sqlite3
from utils import ConfigManager

def test_seed_generation():
    """시드 생성 테스트"""
    print("\n" + "="*60)
    print("📋 TEST 1: AI Seed Generation")
    print("="*60)

    pf = Pathfinder()
    seeds = pf._generate_ai_seeds()

    print(f"\n✅ Total Seeds Generated: {len(seeds):,}")
    print(f"   Expected: ~992 (16 categories × 62 seeds)")

    # 단어 수 분석
    word_counts = [len(seed[0].split()) for seed in seeds]
    avg_words = sum(word_counts) / len(word_counts)
    max_words = max(word_counts)

    print(f"\n📊 Keyword Length Analysis:")
    print(f"   Average Word Count: {avg_words:.1f}")
    print(f"   Max Word Count: {max_words}")
    print(f"   Expected: 2-3 words average, max 4 words")

    # 지역 분포
    cheongju_count = sum(1 for seed, cat in seeds if '청주' in seed)
    dong_count = sum(1 for seed, cat in seeds if any(dong in seed for dong in ['복대동', '율량동', '가경동', '산남동', '용암동']))

    print(f"\n🗺️ Regional Distribution:")
    print(f"   '청주' 포함: {cheongju_count:,} ({cheongju_count/len(seeds)*100:.1f}%)")
    print(f"   동네명 포함: {dong_count:,} ({dong_count/len(seeds)*100:.1f}%)")
    print(f"   Expected: 청주 70%+, 동네명 30%+")

    # 샘플 출력
    print(f"\n📋 Sample Seeds (First 10):")
    for i, (seed, cat) in enumerate(seeds[:10], 1):
        print(f"   {i}. [{cat}] {seed}")

    # 검증
    if len(seeds) < 800 or len(seeds) > 1200:
        print("\n⚠️ WARNING: Seed count out of expected range (800-1200)")
    if avg_words > 3:
        print("\n⚠️ WARNING: Average word count too high")
    if max_words > 5:
        print("\n⚠️ WARNING: Some keywords are too long")
    if cheongju_count / len(seeds) < 0.6:
        print("\n⚠️ WARNING: Too few '청주' keywords")

    print("\n✅ Seed Generation Test Complete!")
    return True

def test_database_quality():
    """데이터베이스 품질 테스트"""
    print("\n" + "="*60)
    print("📊 TEST 2: Database Quality Check")
    print("="*60)

    config = ConfigManager()
    db_path = config.db_path

    if not os.path.exists(db_path):
        print("⚠️ Database not found. Run Pathfinder first.")
        return False

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 전체 통계
    cursor.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN search_volume >= 10 THEN 1 END) as with_volume,
            COUNT(CASE WHEN search_volume = 0 THEN 1 END) as zero_volume,
            COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as kei_500,
            COUNT(CASE WHEN opp_score >= 1000 THEN 1 END) as kei_1000,
            AVG(search_volume) as avg_vol,
            AVG(opp_score) as avg_kei,
            MIN(search_volume) as min_vol,
            MAX(search_volume) as max_vol
        FROM keyword_insights
    """)

    stats = cursor.fetchone()
    total, with_volume, zero_volume, kei_500, kei_1000, avg_vol, avg_kei, min_vol, max_vol = stats

    print(f"\n📈 Overall Statistics:")
    print(f"   Total Keywords: {total:,}")
    print(f"   With Volume (>=10): {with_volume:,} ({with_volume/max(1,total)*100:.1f}%)")
    print(f"   Zero Volume: {zero_volume:,} ({zero_volume/max(1,total)*100:.1f}%)")
    print(f"   KEI 500+: {kei_500:,} ({kei_500/max(1,total)*100:.1f}%)")
    print(f"   KEI 1000+: {kei_1000:,} ({kei_1000/max(1,total)*100:.1f}%)")
    print(f"   Avg Search Volume: {int(avg_vol):,}")
    print(f"   Avg KEI: {int(avg_kei):,}")
    print(f"   Min/Max Volume: {int(min_vol):,} / {int(max_vol):,}")

    print(f"\n🎯 Target Metrics:")
    print(f"   ✓ Zero Volume: Should be 0% (Got: {zero_volume/max(1,total)*100:.1f}%)")
    print(f"   ✓ KEI 500+: Target 3-5% (Got: {kei_500/max(1,total)*100:.1f}%)")
    print(f"   ✓ Avg Volume: Target 80-150 (Got: {int(avg_vol):,})")

    # 카테고리별 분포
    cursor.execute("""
        SELECT
            category,
            COUNT(*) as total,
            COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as golden,
            AVG(search_volume) as avg_vol
        FROM keyword_insights
        WHERE search_volume >= 10
        GROUP BY category
        ORDER BY golden DESC
        LIMIT 10
    """)

    print(f"\n📊 Category Distribution (Top 10):")
    print(f"   {'Category':<30} {'Total':>8} {'KEI 500+':>10} {'Avg Vol':>10}")
    print(f"   {'-'*60}")
    for row in cursor.fetchall():
        cat, total, golden, avg_vol = row
        print(f"   {cat:<30} {total:>8,} {golden:>10,} {int(avg_vol):>10,}")

    # Top 20 Golden Keys
    cursor.execute("""
        SELECT keyword, search_volume, doc_count as supply, opp_score, category
        FROM keyword_insights
        WHERE opp_score >= 500
        ORDER BY opp_score DESC
        LIMIT 20
    """)

    print(f"\n💎 Top 20 Golden Keywords (KEI 500+):")
    print(f"   {'Keyword':<40} {'Vol':>8} {'KEI':>8} {'Category':<20}")
    print(f"   {'-'*80}")
    for row in cursor.fetchall():
        kw, vol, supply, kei, cat = row
        print(f"   {kw:<40} {int(vol):>8,} {int(kei):>8,} {cat:<20}")

    conn.close()

    # 검증
    success = True
    if zero_volume > 0:
        print(f"\n⚠️ WARNING: Found {zero_volume:,} keywords with 0 search volume!")
        success = False

    quality_score = kei_500 / max(1, with_volume) * 100
    if quality_score < 1:
        print(f"\n⚠️ WARNING: Quality score too low ({quality_score:.1f}% < 1%)")
        success = False
    elif quality_score < 3:
        print(f"\n⚡ INFO: Quality score acceptable but below target ({quality_score:.1f}% < 3%)")

    if avg_vol < 30:
        print(f"\n⚠️ WARNING: Average search volume too low ({int(avg_vol):,} < 30)")
        success = False

    print("\n✅ Database Quality Test Complete!")
    return success

def test_keyword_length():
    """키워드 길이 테스트"""
    print("\n" + "="*60)
    print("📏 TEST 3: Keyword Length Distribution")
    print("="*60)

    config = ConfigManager()
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT keyword FROM keyword_insights WHERE search_volume >= 10")
    keywords = [row[0] for row in cursor.fetchall()]
    conn.close()

    if not keywords:
        print("⚠️ No keywords with volume >= 10 found")
        return False

    word_counts = [len(kw.split()) for kw in keywords]
    avg_words = sum(word_counts) / len(word_counts)

    # 분포 계산
    dist = {}
    for wc in word_counts:
        dist[wc] = dist.get(wc, 0) + 1

    print(f"\n📊 Word Count Distribution:")
    for wc in sorted(dist.keys()):
        count = dist[wc]
        pct = count / len(word_counts) * 100
        bar = '█' * int(pct / 2)
        print(f"   {wc} words: {count:>6,} ({pct:>5.1f}%) {bar}")

    print(f"\n📈 Statistics:")
    print(f"   Average: {avg_words:.1f} words")
    print(f"   Expected: 3-4 words")
    print(f"   Total Keywords: {len(keywords):,}")

    long_keywords = [kw for kw in keywords if len(kw.split()) > 5]
    if long_keywords:
        print(f"\n⚠️ Found {len(long_keywords):,} keywords with 6+ words:")
        for kw in long_keywords[:5]:
            print(f"   - {kw}")

    print("\n✅ Keyword Length Test Complete!")
    return True

if __name__ == "__main__":
    print("\n" + "="*60)
    print("🧪 PATHFINDER IMPROVEMENT VALIDATION")
    print("="*60)

    # Test 1: Seed Generation
    test_seed_generation()

    # Test 2: Database Quality (if exists)
    if os.path.exists(ConfigManager().db_path):
        test_database_quality()
        test_keyword_length()
    else:
        print("\n⚠️ Database not found. Please run Pathfinder first:")
        print("   python pathfinder.py")

    print("\n" + "="*60)
    print("✅ ALL TESTS COMPLETE!")
    print("="*60)
    print("\nNext Steps:")
    print("1. If seeds look good, run: python pathfinder.py")
    print("2. Wait 3-5 minutes for Total War mode to complete")
    print("3. Run this test again to check database quality")
    print("4. Open dashboard: streamlit run dashboard_ultra.py")
