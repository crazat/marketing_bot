import sqlite3
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('db/marketing_data.db')
cursor = conn.cursor()

cursor.execute("SELECT COUNT(*) FROM mentions WHERE source='youtube_comment'")
total = cursor.fetchone()[0]
print(f"YouTube 리드 총: {total}건")

cursor.execute("""
    SELECT id, keyword, content, memo, scraped_at, url
    FROM mentions
    WHERE source='youtube_comment'
    ORDER BY id DESC LIMIT 10
""")
rows = cursor.fetchall()

print("\n최근 10건:")
for r in rows:
    print(f"[ID:{r[0]}] 키워드: {r[1]}")
    print(f"  내용: {r[2][:80]}...")
    print(f"  분류: {r[3]}")
    print(f"  URL: {r[5][:50] if r[5] else 'N/A'}...")
    print()

conn.close()
