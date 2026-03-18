import sqlite3
import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from pathfinder import Pathfinder

def purge_garbage():
    pf = Pathfinder()
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'db', 'marketing_data.db')
    
    print(f"🧹 Connecting to DB: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get all keywords
    cursor.execute("SELECT keyword FROM keyword_insights")
    all_rows = cursor.fetchall()
    total = len(all_rows)
    print(f"📦 Total keywords in DB: {total}")
    
    deleted_count = 0
    kept_count = 0
    
    deleted_examples = []
    
    for row in all_rows:
        kw = row[0]
        if not pf._is_medically_relevant(kw):
            cursor.execute("DELETE FROM keyword_insights WHERE keyword = ?", (kw,))
            deleted_count += 1
            if len(deleted_examples) < 10:
                deleted_examples.append(kw)
        else:
            kept_count += 1
            
    conn.commit()
    conn.close()
    
    print(f"✅ Purge Complete.")
    print(f"🗑️ Deleted: {deleted_count}")
    print(f"🛡️ Kept: {kept_count}")
    print(f"📝 Deleted Examples: {deleted_examples}")

if __name__ == "__main__":
    purge_garbage()
