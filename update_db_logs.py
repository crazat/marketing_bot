
import sqlite3
from utils import ConfigManager

def migrate_logs():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Migrating System Logs Table at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # System Logs Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source TEXT,   -- 'Sentinel', 'Scraper', 'Scheduler'
        message TEXT,
        level TEXT DEFAULT 'INFO',
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()
    print("✅ System logs table created.")

if __name__ == "__main__":
    migrate_logs()
