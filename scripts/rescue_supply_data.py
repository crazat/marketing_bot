import sys
import os
import sqlite3
import pandas as pd
import concurrent.futures
from tqdm import tqdm
import time

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scrapers.keyword_harvester import KeywordHarvester
from utils import ConfigManager, logger

# [Windows Fix] Force UTF-8 for console output
sys.stdout.reconfigure(encoding='utf-8')

def rescue_data():
    config = ConfigManager()
    db_path = config.db_path
    
    print(f"🚑 Connecting to DB: {db_path}")
    
    # 1. Fetch Failed Keywords (Volume = 0)
    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql("SELECT id, keyword, search_volume FROM keyword_insights WHERE volume = 0", conn)
        
    print(f"📋 Found {len(df)} keywords with 0 supply (failed scans).")
    
    if len(df) == 0:
        print("🎉 No failed keywords found! Nothing to rescue.")
        return

    # 2. Re-Scan Logic
    harvester = KeywordHarvester()
    updated_results = []
    
    print("🚀 Starting Rescue Scan (Parallel Mode)...")
    
    def scan(row):
        kw = row['keyword']
        vol = row['search_volume']
        
        # Harvester has built-in retry/backoff now
        doc_count = harvester.get_naver_blog_count(kw)
        
        # Re-calc Opp Score
        # Simple Logic: Score = Search Vol / (Doc Count + 1) * 10
        opp_score = round((vol / (doc_count + 1)) * 10, 2)
        tag = "꿀통🍯" if opp_score >= 50 else "쏘쏘😐"
        if opp_score < 10: tag = "레드오션🔥"
        
        return (doc_count, "Low" if doc_count < 1000 else "High", opp_score, tag, row['id'])

    # Using ThreadPool
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(scan, row): row for _, row in df.iterrows()}
        
        for future in tqdm(concurrent.futures.as_completed(futures), total=len(futures)):
            updated_results.append(future.result())
            
    # 3. Batch Update DB
    print("💾 Updating Database...")
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            UPDATE keyword_insights 
            SET volume=?, competition=?, opp_score=?, tag=?
            WHERE id=?
        """, updated_results)
        conn.commit()
        
    print("✅ Database Updated Successfully.")
    
    # 4. Export to Excel/CSV
    output_file = os.path.join(config.root_dir, "salvaged_keywords_v1.csv")
    
    # Fetch fresh data
    with sqlite3.connect(db_path) as conn:
        # Load all data to sort in pandas (or sort in SQL)
        final_df = pd.read_sql("SELECT * FROM keyword_insights WHERE volume > 0 ORDER BY opp_score DESC", conn)
        
    # Explicit Sort again just to be sure
    final_df = final_df.sort_values(by='opp_score', ascending=False)
    
    final_df.to_csv(output_file, index=False, encoding='utf-8-sig')
    print(f"📂 Exported salvaged data to: {output_file}")

if __name__ == "__main__":
    rescue_data()
