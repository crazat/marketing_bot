import sqlite3
import os
import sys

# Force UTF-8 output
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

db_path = r'c:\Users\craza\Dropbox\Projects\marketing_bot\db\marketing_data.db'

if not os.path.exists(db_path):
    print(f"ERROR: Database not found at {db_path}")
else:
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM keyword_insights")
        count = cursor.fetchone()[0]
        print(f"Total keywords in keyword_insights: {count}")
        
        cursor.execute("SELECT COUNT(*) FROM system_logs")
        log_count = cursor.fetchone()[0]
        print(f"Total system logs: {log_count}")
        
        cursor.execute("SELECT created_at, message FROM system_logs ORDER BY id DESC LIMIT 5")
        recent_logs = cursor.fetchall()
        print("\nRecent Logs:")
        for log in recent_logs:
            print(f"  {log[0]}: {log[1]}")
            
        conn.close()
    except Exception as e:
        print(f"ERROR accessing database: {e}")
