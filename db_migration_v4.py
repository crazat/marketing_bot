
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'db', 'marketing_data.db')

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column exists
        cursor.execute("PRAGMA table_info(keyword_insights)")
        columns = [info[1] for info in cursor.fetchall()]
        
        if 'search_volume' not in columns:
            print("Adding 'search_volume' column...")
            cursor.execute("ALTER TABLE keyword_insights ADD COLUMN search_volume INTEGER DEFAULT 0")
        else:
            print("'search_volume' column already exists.")
            
        conn.commit()
        print("Migration successful.")
    except Exception as e:
        print(f"Migration failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
