
import sqlite3
from utils import ConfigManager

def register_bulk_competitors():
    config = ConfigManager()
    db_path = config.db_path
    
    competitors = [
        "자연과한의원 청주점",
        "청주 나비솔 한방병원",
        "하늘체한의원 청주점",
        "청주 자생한방병원",
        "청주 필한방병원",
        "리치한방병원",
        "후 한의원 청주점",
        "하늘마음한의원 청주점"
    ]
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    print("🚀 Registering Bulk Competitors...")
    for comp in competitors:
        try:
            cursor.execute("INSERT INTO competitors (name) VALUES (?)", (comp,))
            print(f"✅ Added: {comp}")
        except sqlite3.IntegrityError:
            print(f"⚠️ Already exists: {comp}")
            
    conn.commit()
    conn.close()
    print("✅ Bulk registration complete.")

if __name__ == "__main__":
    register_bulk_competitors()
