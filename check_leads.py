import sqlite3
conn = sqlite3.connect('db/marketing_data.db')
c = conn.cursor()

c.execute('SELECT COUNT(*) FROM mentions')
print(f'전체 리드: {c.fetchone()[0]}개')

c.execute("SELECT COUNT(*) FROM mentions WHERE scraped_at >= datetime('now', '-1 day')")
print(f'최근 24시간: {c.fetchone()[0]}개')

c.execute("SELECT platform, source, COUNT(*) FROM mentions WHERE scraped_at >= datetime('now', '-1 day') GROUP BY platform, source")
print('\n플랫폼별:')
for row in c.fetchall():
    print(f'  platform={row[0]}, source={row[1]}: {row[2]}개')

c.execute('SELECT id, platform, source, title FROM mentions ORDER BY id DESC LIMIT 5')
print('\n최근 5개:')
for row in c.fetchall():
    print(f'  ID {row[0]}: {row[1]} / {row[2]} - {row[3][:40]}...')

conn.close()
