import sys
import os
import subprocess
import time

# Windows encoding fix
sys.stdout.reconfigure(encoding='utf-8')

def run_test(script_name, description):
    print(f"\n--- 🧪 Testing: {description} ({script_name}) ---")
    try:
        start = time.time()
        # Run with timeout to prevent hanging
        result = subprocess.run(
            ["python", script_name],
            cwd=os.getcwd(),
            capture_output=True,
            text=True,
            timeout=60, # 60s timeout per script
            encoding='utf-8',
            errors='ignore'
        )
        duration = time.time() - start
        
        if result.returncode == 0:
            print(f"✅ PASS ({duration:.1f}s)")
            # Print last 3 lines of output to verify it actually did something
            lines = result.stdout.strip().split('\n')
            for line in lines[-3:]:
                print(f"   > {line}")
            return True, result.stdout
        else:
            print(f"❌ FAIL (Exit Code: {result.returncode})")
            print(result.stderr[:500])
            return False, result.stderr
            
    except subprocess.TimeoutExpired:
        print("❌ TIMEOUT (killed after 60s)")
        return False, "Timeout"
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return False, str(e)

scripts = [
    ("marketing_bot/scrapers/scraper_news.py", "News Scraper"),
    ("marketing_bot/scrapers/scraper_google.py", "Google Ranker"),
    ("marketing_bot/scrapers/scraper_instagram.py", "Instagram Monitor"),
    # ("marketing_bot/scrapers/scraper_tiktok_monitor.py", "TikTok Monitor"), # Might need manual check or longer timeout
    ("marketing_bot/scrapers/scraper_karrot.py", "Karrot Scraper"),
    ("marketing_bot/content_factory.py", "Content Factory (Track B)")
]

results = {}

print("🚀 Starting System Verification Suite...")
for script, desc in scripts:
    success, log = run_test(script, desc)
    results[desc] = success

print("\n--- 📊 Summary ---")
for desc, success in results.items():
    icon = "✅" if success else "❌"
    print(f"{icon} {desc}")
