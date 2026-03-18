import sqlite3
import os
import sys

# Force UTF-8 for console output
sys.stdout.reconfigure(encoding='utf-8')

db_path = 'marketing_bot/db/marketing_data.db'
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

print("--- Reading Raw Bytes / String ---")
cursor.execute("SELECT title, content FROM mentions WHERE target_name='News' ORDER BY id DESC LIMIT 3")
rows = cursor.fetchall()

for r in rows:
    print(f"Title: {r[0]}")
    print(f"Content: {r[1]}")
    
conn.close()
