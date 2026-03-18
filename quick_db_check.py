import sqlite3
import sys
from utils import ConfigManager

sys.stdout.reconfigure(encoding='utf-8')

config = ConfigManager()
conn = sqlite3.connect(config.db_path)
cursor = conn.cursor()

cursor.execute("""
    SELECT
        COUNT(*) as total,
        COUNT(CASE WHEN search_volume >= 10 THEN 1 END) as with_volume,
        COUNT(CASE WHEN search_volume = 0 THEN 1 END) as zero_volume,
        COUNT(CASE WHEN opp_score >= 500 THEN 1 END) as kei_500,
        AVG(search_volume) as avg_vol,
        AVG(opp_score) as avg_kei
    FROM keyword_insights
""")

stats = cursor.fetchone()
total, with_vol, zero_vol, kei_500, avg_vol, avg_kei = stats

print("현재 DATABASE 상태")
print("=" * 50)
print(f"Total: {total:,}")
print(f"With Volume (>=10): {with_vol:,} ({with_vol/max(1,total)*100:.1f}%)")
print(f"Zero Volume: {zero_vol:,} ({zero_vol/max(1,total)*100:.1f}%)")
print(f"KEI 500+: {kei_500:,} ({kei_500/max(1,total)*100:.1f}%)")
print(f"Avg Volume: {int(avg_vol):,}")
print(f"Avg KEI: {int(avg_kei):,}")

# 카테고리별
cursor.execute("""
    SELECT category, COUNT(*) as cnt
    FROM keyword_insights
    GROUP BY category
    ORDER BY cnt DESC
    LIMIT 10
""")

print("\n카테고리별 키워드 수:")
for cat, cnt in cursor.fetchall():
    print(f"  {cat}: {cnt:,}")

conn.close()
