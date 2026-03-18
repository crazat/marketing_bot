
import sqlite3
from utils import ConfigManager

def add_new_targets():
    config = ConfigManager()
    db_path = config.db_path
    
    new_targets = [
        "데이릴 한의원",
        "리샘한의원",
        "아름턱한의원"
    ]
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🚀 Adding Special Competitors (Asymmetry)...")
    for comp in new_targets:
        try:
            cursor.execute("INSERT INTO competitors (name) VALUES (?)", (comp,))
            print(f"✅ Added: {comp}")
        except sqlite3.IntegrityError:
            print(f"⚠️ Already exists: {comp}")
            
    conn.commit()
    
    # Check full list
    print("\n[Current Watch List]")
    cursor.execute("SELECT name FROM competitors WHERE status='active'")
    rows = cursor.fetchall()
    for r in rows:
        print(f"- {r[0]}")
        
    conn.close()

if __name__ == "__main__":
    add_new_targets()
