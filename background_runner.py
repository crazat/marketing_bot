
import time
from insight_manager import InsightManager

def run_sentinel():
    print("🕵️ Marketing Sentinel Started...")
    mgr = InsightManager()
    
    # 1. Check Ranks (Basic + Sniper)
    print("Checking Search Rankings & View Tab...")
    mgr.generate_rank_insights()
    mgr.generate_view_rank_insights()
    
    # 2. Check Seasonality & Future Trends (Prophet)
    print("Checking Trends (Prophet)...")
    # mgr.generate_seasonal_insights() # Deactivated in favor of Prophet
    mgr.generate_prophet_insights()
    mgr.generate_visual_trend_insights() # Paparazzi
    
    # 3. Competitive Intelligence (Tactician + Spy)
    print("Analyzing Competitors (Tactician & Spy)...")
    mgr.generate_competitor_activity_insights()
    mgr.generate_community_insights()
    mgr.generate_strategic_insights() # TargetedTactician
    
    # 4. Expansion (Pathfinder + Ambassador)
    print("Exploring New Opportunities...")
    mgr.generate_keyword_opportunities()
    mgr.generate_ambassador_insights()
    
    print("✅ Full Auto-Pilot Scan Completed. Check Dashboard.")

if __name__ == "__main__":
    run_sentinel()
