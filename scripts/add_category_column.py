import sqlite3
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ConfigManager, logger

def update_schema():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"🛠️ Connecting to DB: {db_path}")
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # Check if column exists
            cursor.execute("PRAGMA table_info(keyword_insights)")
            columns = [info[1] for info in cursor.fetchall()]
            
            if 'category' not in columns:
                print("➕ Adding 'category' column...")
                cursor.execute("ALTER TABLE keyword_insights ADD COLUMN category TEXT DEFAULT '기타'")
                conn.commit()
                print("✅ Column added successfully.")
            else:
                print("ℹ️ 'category' column already exists.")
                
    except Exception as e:
        print(f"❌ Schema update failed: {e}")

if __name__ == "__main__":
    # Force UTF-8 for Windows console
    sys.stdout.reconfigure(encoding='utf-8')
    update_schema()
