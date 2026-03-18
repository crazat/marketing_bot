import sqlite3
import os
import sys

# Windows Encoding Fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Define DB Path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'db', 'marketing_data.db')

def update_schema():
    print(f"🔌 Connecting to {DB_PATH}...")
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if column exists
        cursor.execute("PRAGMA table_info(competitor_reviews)")
        cols = [info[1] for info in cursor.fetchall()]
        
        if "image_count" not in cols:
            print("🛠️ Adding 'image_count' column to competitor_reviews...")
            try:
                cursor.execute("ALTER TABLE competitor_reviews ADD COLUMN image_count INTEGER DEFAULT 0")
                conn.commit()
                print("✅ Schema updated successfully.")
            except Exception as e:
                print(f"❌ Failed to alter table: {e}")
        else:
            print("ℹ️ 'image_count' column already exists.")
            
        conn.close()
    except Exception as e:
        print(f"❌ Connection failed: {e}")

if __name__ == "__main__":
    update_schema()
