import sqlite3
import os
import sys
import pandas as pd

# Force UTF-8 output
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

db_path = r'c:\Users\craza\Dropbox\Projects\marketing_bot\db\marketing_data.db'

def analyze_data():
    if not os.path.exists(db_path):
        print(f"ERROR: Database not found at {db_path}")
        return

    try:
        conn = sqlite3.connect(db_path)
        
        # 1. Sample keywords with high Search Volume
        print("--- Top 20 Keywords by Search Volume ---")
        query_top_vol = "SELECT keyword, search_volume, volume, opp_score, category, trend_slope FROM keyword_insights ORDER BY search_volume DESC LIMIT 20"
        df_top_vol = pd.read_sql_query(query_top_vol, conn)
        print(df_top_vol)
        print("\n")

        # 2. Sample keywords with high Opportunity Score (KEI)
        print("--- Top 20 Keywords by Opportunity Score (KEI) ---")
        query_top_kei = "SELECT keyword, search_volume, volume, opp_score, category, trend_slope FROM keyword_insights WHERE search_volume > 100 ORDER BY opp_score DESC LIMIT 20"
        df_top_kei = pd.read_sql_query(query_top_kei, conn)
        print(df_top_kei)
        print("\n")

        # 3. Check for Trend Data coverage
        print("--- Trend Data Summary ---")
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM keyword_insights WHERE trend_status != 'unknown'")
        trend_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM keyword_insights")
        total_count = cursor.fetchone()[0]
        print(f"Total Keywords: {total_count}")
        print(f"Keywords with Trend Data: {trend_count}")
        
        if trend_count > 0:
            print("\n--- Samples with Trend Data ---")
            query_trends = "SELECT keyword, trend_slope, trend_status FROM keyword_insights WHERE trend_status != 'unknown' LIMIT 10"
            df_trends = pd.read_sql_query(query_trends, conn)
            print(df_trends)

        # 4. Distribution of Categories
        print("\n--- Category Distribution ---")
        query_cat = "SELECT category, COUNT(*) as count FROM keyword_insights GROUP BY category ORDER BY count DESC"
        df_cat = pd.read_sql_query(query_cat, conn)
        print(df_cat)

        conn.close()
    except Exception as e:
        print(f"ERROR analyzing database: {e}")

if __name__ == "__main__":
    analyze_data()
