import sys
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

print("DEBUG: Repro - Starts")

# Mimic the hardcoded driver init
def test_driver():
    print("DEBUG: Repro - Initializing Driver...")
    try:
        driver_path = r"C:\Users\craza\.wdm\drivers\chromedriver\win64\144.0.7559.60\chromedriver-win32\chromedriver.exe"
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        driver = webdriver.Chrome(service=Service(driver_path), options=options)
        driver.set_page_load_timeout(60)
        print("DEBUG: Repro - Driver Success!")
        driver.quit()
    except Exception as e:
        print(f"DEBUG: Repro - Driver Failed: {e}")

# Mimic the imports in cafe_spy.py
try:
    import os
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(current_dir) # Since we will run from root, current_dir is root? No, waiting.
    # We will run this file from root. So __file__ is ./repro_cafe_spy.py
    # cafe_spy is in scrapers/. 
    
    # Let's adjust sys.path as cafe_spy does
    # In cafe_spy: 
    # current_dir = .../scrapers
    # project_root = .../marketing_bot
    
    sys.path.insert(0, os.getcwd())
    print(f"DEBUG: Repro - Sys Path: {sys.path[0]}")
    
    # Test Import 1: Utils (Logger)
    print("DEBUG: Repro - Importing Logger...")
    from utils import logger
    print("DEBUG: Repro - Logger Imported.")

    # Test Import 2: Database
    print("DEBUG: Repro - Importing DatabaseManager...")
    from db.database import DatabaseManager
    print("DEBUG: Repro - DatabaseManager Imported.")
    
    # Test DB Init
    print("DEBUG: Repro - Initializing DB...")
    db = DatabaseManager()
    print("DEBUG: Repro - DB Initialized.")

except ImportError as e:
    print(f"DEBUG: Repro - Import Error: {e}")
except Exception as e:
    print(f"DEBUG: Repro - General Error: {e}")

if __name__ == "__main__":
    test_driver()
