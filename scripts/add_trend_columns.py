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
            
            # Check existing columns
            cursor.execute("PRAGMA table_info(keyword_insights)")
            columns = [info[1] for info in cursor.fetchall()]
            
            # Add trend_slope
            if 'trend_slope' not in columns:
                print("➕ Adding 'trend_slope' column...")
                cursor.execute("ALTER TABLE keyword_insights ADD COLUMN trend_slope REAL DEFAULT 0.0")
            else:
                print("ℹ️ 'trend_slope' already exists.")
                
            # Add trend_status
            if 'trend_status' not in columns:
                print("➕ Adding 'trend_status' column...")
                cursor.execute("ALTER TABLE keyword_insights ADD COLUMN trend_status TEXT DEFAULT 'unknown'")
            else:
                print("ℹ️ 'trend_status' already exists.")

            # Add trend_checked_at
            if 'trend_checked_at' not in columns:
                print("➕ Adding 'trend_checked_at' column...")
                cursor.execute("ALTER TABLE keyword_insights ADD COLUMN trend_checked_at TIMESTAMP")
            else:
                print("ℹ️ 'trend_checked_at' already exists.")
                
            conn.commit()
            print("✅ Schema update completed.")
                
    except Exception as e:
        print(f"❌ Schema update failed: {e}")

if __name__ == "__main__":
    # Force UTF-8 for Windows console
    sys.stdout.reconfigure(encoding='utf-8')
    update_schema()
