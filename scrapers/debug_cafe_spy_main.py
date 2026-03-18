
import sys
import os

print("STEP 1: Standard Imports")

# Robust Path Setup for Hybrid Execution (Standalone vs Module)
import os
import sys
print("DEBUG: Core imports done. Setting up paths...")

# Determine the project root based on the script location
# cafe_spy.py is in /scrapers, so root is one level up
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)

if project_root not in sys.path:
    sys.path.insert(0, project_root)
print(f"DEBUG: Path set. Root: {project_root}")

# Now standard imports should work if running from root or scrapers/
try:
    print("DEBUG: Importing DatabaseManager...")
    from db.database import DatabaseManager
    print("DEBUG: DatabaseManager Imported. Importing Logger...")
    from utils import logger
    print("DEBUG: Logger Imported.")
except ImportError:
    # This might happen if project structure is totally different, but sys.path insert shields us
    print("⚠️ Import Error: Check directory structure.")
    sys.exit(1)

print("STEP 2: Class Definition")

class CafeSpy:
    def __init__(self):
        print("CafeSpy Init")

if __name__ == "__main__":
    print("STEP 3: Main Block Reached")
    try:
        spy = CafeSpy()
        print("Success")
    except Exception as e:
        print(f"Error: {e}")
