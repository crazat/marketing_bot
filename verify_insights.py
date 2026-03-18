
import sys
import os
sys.path.append(os.getcwd())

try:
    from insight_manager import InsightManager
    
    print("Initializing InsightManager...")
    mgr = InsightManager()
    
    # Check Active Insights
    active = mgr.get_active_insights()
    print(f"✅ Found {len(active)} active insights.")
    for i in active:
        print(f"   - [{i['type']}] {i['title']} (Meta: {i['meta']})")

except Exception as e:
    print(f"❌ Verification Failed: {e}")
