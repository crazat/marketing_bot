
import sqlite3
from utils import ConfigManager

def migrate_knowledge():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Migrating Knowledge Table at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Knowledge Index Table
    # Stores metadata and summary of generated files/reports
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS knowledge_index (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        source_file TEXT,     -- Path to the original file
        doc_type TEXT,        -- 'report', 'blog', 'competitor_analysis'
        title TEXT,
        summary TEXT,         -- AI generated 3-line summary
        keywords TEXT,        -- JSON list of keywords
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(source_file)
    );
    """)
    
    conn.commit()
    conn.close()
    print("✅ Knowledge DB schema created.")

if __name__ == "__main__":
    migrate_knowledge()
