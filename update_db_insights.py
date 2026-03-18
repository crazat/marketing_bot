
import sqlite3
from utils import ConfigManager

def migrate_insights():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Migrating Insights Table at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Insights Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS insights (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT,
        title TEXT,
        content TEXT,
        meta_json TEXT,
        status TEXT DEFAULT 'new',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()
    print("✅ Insights table created.")

if __name__ == "__main__":
    migrate_insights()
