"""
DB Migration: Add region column to keyword_insights table
"""
import sqlite3
import os
from utils import ConfigManager

def migrate():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Database: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Check if column already exists
    cursor.execute("PRAGMA table_info(keyword_insights)")
    columns = [col[1] for col in cursor.fetchall()]
    
    if 'region' in columns:
        print("[OK] Column 'region' already exists. No migration needed.")
    else:
        print("[RUN] Adding 'region' column...")
        cursor.execute("ALTER TABLE keyword_insights ADD COLUMN region TEXT DEFAULT '기타'")
        conn.commit()
        print("[DONE] Migration complete!")
    
    conn.close()

if __name__ == "__main__":
    migrate()
