import sqlite3
import sys

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('c:/Users/craza/Dropbox/Projects/marketing_bot/db/marketing_data.db')
cursor = conn.cursor()
cursor.execute('SELECT keyword, category FROM keyword_insights ORDER BY created_at DESC LIMIT 10')
for row in cursor.fetchall():
    print(f"Keyword: {row[0]}, Category: {row[1]}")
conn.close()
