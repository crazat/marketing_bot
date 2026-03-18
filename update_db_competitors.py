
import sqlite3
from utils import ConfigManager
import os
import glob

def migrate_competitors():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"Migrating Competitors Table at: {db_path}")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Competitors Table
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS competitors (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        url TEXT,
        status TEXT DEFAULT 'active',
        last_analyzed DATETIME
    );
    """)
    
    # Auto-discovery from reports
    print("🔍 Scanning reports for existing competitors...")
    report_dir = os.path.join(config.root_dir, 'reports_competitor')
    if os.path.exists(report_dir):
        files = glob.glob(os.path.join(report_dir, "*_Report.md"))
        for f in files:
            fname = os.path.basename(f)
            # Simple heuristic: remove date and _Report.md
            # e.g. 20260111_청주 미올_Report.md -> 청주 미올
            try:
                parts = fname.split('_')
                if len(parts) >= 3:
                    name_part = parts[1] # raw assumption
                    # Exclude self
                    if "규림" not in name_part:
                        print(f"Found candidate: {name_part}")
                        try:
                            cursor.execute("INSERT INTO competitors (name) VALUES (?)", (name_part,))
                            print(f"✅ Registered: {name_part}")
                        except sqlite3.IntegrityError:
                            pass
            except:
                continue

    conn.commit()
    conn.close()
    print("✅ Competitors table ready.")

if __name__ == "__main__":
    migrate_competitors()
