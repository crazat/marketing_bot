import sys
import os
import time
import subprocess
import json
import random
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

# [Robustness] Windows Encoding Fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

# Path to the worker script
WORKER_SCRIPT = os.path.join(os.path.dirname(__file__), 'scrapers', 'cafe_spy.py')
PYTHON_EXE = sys.executable

def get_target_cafes():
    """import cafe_spy to read the config without running it"""
    try:
        sys.path.append(os.path.join(os.path.dirname(__file__), 'scrapers'))
        from cafe_spy import CafeSpy
        spy = CafeSpy()
        return [c['name'] for c in spy.target_cafes]
    except Exception as e:
        print(f"Error loading targets: {e}")
        return []

def run_worker(cafe_name):
    """Runs a single worker process for one cafe"""
    print(f"🚀 [Launcher] Deploying worker for: {cafe_name}")
    try:
        # Run subprocess
        cmd = [PYTHON_EXE, WORKER_SCRIPT, "--cafe_name", cafe_name]
        
        # Redirect output to a log file maybe? For now inherit stdout
        # Using shell=True only if needed, usually list is safer
        result = subprocess.run(cmd, capture_output=False, text=True) # Let it print to main console
        
        if result.returncode == 0:
            print(f"✅ [Launcher] Worker finished: {cafe_name}")
        else:
            print(f"⚠️ [Launcher] Worker failed: {cafe_name} (Code {result.returncode})")
            
    except Exception as e:
        print(f"❌ [Launcher] Error running {cafe_name}: {e}")

def main():
    print(f"[{datetime.now()}] 🐝 Starting Marketing Swarm (Parallel Cafe Spy)...")
    
    targets = get_target_cafes()
    print(f"🎯 Detected {len(targets)} targets: {targets}")
    
    # Max Workers: 7 (Full Parallel Mode)
    MAX_WORKERS = 7
    print(f"⚡ Concurrency Limit: {MAX_WORKERS} agents (Full Swarm)")
    
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        for name in targets:
            # Stagger launch to prevent traffic spike
            time.sleep(random.uniform(1.0, 3.0)) 
            futures.append(executor.submit(run_worker, name))
        
        # Wait for completion
        for future in futures:
            future.result()
            
    print(f"[{datetime.now()}] 🏁 All Swarm Missions Completed.")

if __name__ == "__main__":
    main()
