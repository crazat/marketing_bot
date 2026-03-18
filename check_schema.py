import sqlite3
conn = sqlite3.connect('db/marketing_data.db')
c = conn.cursor()

print("=== mentions 테이블 구조 ===")
c.execute("PRAGMA table_info(mentions)")
for row in c.fetchall():
    print(f"  {row[1]} ({row[2]})")

print("\n=== 최근 리드 source 확인 ===")
c.execute("SELECT source, COUNT(*) FROM mentions WHERE scraped_at >= datetime('now', '-1 day') GROUP BY source")
for row in c.fetchall():
    print(f"  source={row[0]}: {row[1]}개")

print("\n=== 최근 5개 리드 상세 ===")
c.execute("SELECT id, source, title FROM mentions ORDER BY id DESC LIMIT 5")
for row in c.fetchall():
    print(f"  ID {row[0]}: source={row[1]}")
    print(f"    제목: {row[2][:60]}...")

conn.close()
