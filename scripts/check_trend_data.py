import sqlite3
import sys

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('c:/Users/craza/Dropbox/Projects/marketing_bot/db/marketing_data.db')
cursor = conn.cursor()
cursor.execute('SELECT keyword, trend_slope, trend_status, trend_checked_at FROM keyword_insights ORDER BY created_at DESC LIMIT 10')
print(f"{'Keyword':<20} | {'Slope':<10} | {'Status':<15} | {'Checked At'}")
print("-" * 70)
for row in cursor.fetchall():
    print(f"{row[0]:<20} | {row[1]:<10} | {row[2]:<15} | {row[3]}")
conn.close()
