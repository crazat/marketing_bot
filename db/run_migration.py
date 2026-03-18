import sys
import os

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

if __name__ == "__main__":
    print("Running Database Migration...")
    try:
        db = DatabaseManager()
        # triggering _init_db inside __init__
        print("Database schema updated successfully.")
        print("   - Checked/Added 'status' column")
        print("   - Checked/Added 'memo' column")
        print("   - Checked/Added 'image_url' column")
    except Exception as e:
        print(f"Migration Failed: {e}")
