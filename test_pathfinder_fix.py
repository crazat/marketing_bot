#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify Pathfinder data persistence fix
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pathfinder import Pathfinder
from utils import logger
import logging

logging.basicConfig(level=logging.INFO)

def test_batch_save():
    """Test that _batch_save_to_db works with missing region field"""
    print("\n" + "="*60)
    print("Testing Pathfinder Data Persistence Fix")
    print("="*60)
    
    pf = Pathfinder()
    
    # Test Case 1: Insight WITH region field (should work)
    print("\n[Test 1] Insight with region field...")
    test_insights_1 = [{
        'keyword': 'test청주다이어트',
        'volume': 100,
        'competition': 'Low',
        'opp_score': 500.0,
        'tag': 'Test',
        'search_volume': 50,
        'region': '청주'
    }]
    result_1 = pf._batch_save_to_db(test_insights_1)
    print(f"Result: {'✅ SUCCESS' if result_1 else '❌ FAILED'}")
    
    # Test Case 2: Insight WITHOUT region field (should now work with defaults)
    print("\n[Test 2] Insight WITHOUT region field (should add default)...")
    test_insights_2 = [{
        'keyword': 'test세종한의원',
        'volume': 200,
        'competition': 'Low',
        'opp_score': 600.0,
        'tag': 'Test',
        'search_volume': 75
        # NO region field
    }]
    result_2 = pf._batch_save_to_db(test_insights_2)
    print(f"Result: {'✅ SUCCESS' if result_2 else '❌ FAILED'}")
    
    # Test Case 3: Empty insights list
    print("\n[Test 3] Empty insights list...")
    result_3 = pf._batch_save_to_db([])
    print(f"Result: {'✅ SUCCESS (correctly rejected)' if not result_3 else '❌ FAILED (should reject empty)'}")
    
    # Verify data was saved
    print("\n[Verification] Checking database for test keywords...")
    import sqlite3
    from utils import ConfigManager
    config = ConfigManager()
    conn = sqlite3.connect(config.db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT keyword, region FROM keyword_insights WHERE keyword LIKE 'test%'")
    rows = cursor.fetchall()
    conn.close()
    
    print(f"\nFound {len(rows)} test keywords in database:")
    for kw, region in rows:
        print(f"  - {kw}: region='{region}'")
    
    # Final assessment
    print("\n" + "="*60)
    if result_1 and result_2 and not result_3 and len(rows) >= 2:
        print("✅ ALL TESTS PASSED - Fix is working correctly!")
        return True
    else:
        print("❌ SOME TESTS FAILED - Review results above")
        return False

if __name__ == "__main__":
    success = test_batch_save()
    sys.exit(0 if success else 1)
