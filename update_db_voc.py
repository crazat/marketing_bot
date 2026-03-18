
import sqlite3
from utils import ConfigManager

def migrate_voc():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Migrating VoC (Review) Table at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Competitor Reviews Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS competitor_reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        competitor_name TEXT,
        source TEXT,          -- 'naver_receipt', 'blog_review'
        content TEXT,
        sentiment TEXT,       -- 'positive', 'negative', 'neutral'
        keywords TEXT,        -- JSON list extracted keywords
        review_date DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """)
    
    conn.commit()
    conn.close()
    print("✅ VoC DB schema created.")

if __name__ == "__main__":
    migrate_voc()
