import requests
import concurrent.futures
import time
import random
import logging
import re
import os
import sys

# Add project root to sys.path to find modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from retry_helper import SafeSeleniumDriver
from selenium.webdriver.common.by import By

logger = logging.getLogger("FastScanner")

class FastVolumeScanner:
    """
    The 'Carpet Bomb' Engine (Selenium Swarm Edition).
    Uses 4 Concurrent Headless Browsers to scan volume.
    Slower than requests, but 100% reliable against blocking.
    """
    def __init__(self, max_workers=4):
        self.max_workers = max_workers
        
    def scan(self, keywords):
        """
        Orchestrates the swarm.
        Splits keywords into chunks and assigns to workers.
        """
        total = len(keywords)
        print(f"🚀 Selenium Swarm Assembling: {self.max_workers} Workers for {total} keywords...")
        
        # Split keywords into chunks for each worker
        # If 100 keywords, 4 workers -> 25 each.
        chunk_size = (total // self.max_workers) + 1
        chunks = [keywords[i:i + chunk_size] for i in range(0, total, chunk_size)]
        
        results = []
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_chunk = {executor.submit(self._worker_routine, chunk, i): i for i, chunk in enumerate(chunks)}
            
            for future in concurrent.futures.as_completed(future_to_chunk):
                worker_id = future_to_chunk[future]
                try:
                    worker_results = future.result()
                    results.extend(worker_results)
                    print(f"✅ Worker {worker_id} finished. ({len(worker_results)} processed)")
                except Exception as e:
                    print(f"❌ Worker {worker_id} crashed: {e}")
                    
        return results

    def _worker_routine(self, keywords, worker_id):
        """
        A single worker's life:
        1. Init Driver (Desktop Mode)
        2. Process List
        3. Quit Driver
        """
        worker_results = []
        try:
            # Desktop Mode for consistent "Total Count" visibility
            with SafeSeleniumDriver(mobile=False, headless=True) as driver:
                print(f"🤖 Worker {worker_id} online (Desktop). Processing {len(keywords)} items.")
                
                for idx, kw in enumerate(keywords):
                    vol = 0
                    status = "failed"
                    try:
                        # 1. Go to Desktop Blog Search
                        url = f"https://search.naver.com/search.naver?query={kw}&where=blog"
                        driver.get(url)
                        
                        time.sleep(random.uniform(1.0, 1.5))
                        
                        # 2. Extract Count (Desktop Selectors)
                        found_text = ""
                        # Usually: .sc_new .api_title_area .total_option
                        # Or: .sub_pack .total_tit
                        selectors = [
                            ".total_option", 
                            ".api_title_area .total", 
                            ".sub_pack .total_tit",
                            ".sc_new .total_option"
                        ]
                        
                        for sel in selectors:
                            try:
                                els = driver.find_elements(By.CSS_SELECTOR, sel)
                                for el in els:
                                    txt = el.text.strip()
                                    if "건" in txt and any(c.isdigit() for c in txt):
                                        found_text = txt
                                        break
                                if found_text: break
                            except Exception: continue
                            
                        # Fallback: Search for "전체" or "blo" text pattern if selector fails
                        if not found_text:
                            try:
                                # Look for "전체 123,456건" pattern in specific header areas
                                headers = driver.find_elements(By.CSS_SELECTOR, ".api_title_area, .section_head")
                                for h in headers:
                                    if "전체" in h.text and "건" in h.text:
                                        found_text = h.text
                                        break
                            except Exception: pass

                        # Parse
                        if found_text:
                            # "전체 123,456건"
                            nums = re.findall(r'([\d,]+)\s*건', found_text)
                            if nums:
                                vol = int(nums[0].replace(',', ''))
                                status = "success"
                        else:
                            # Check for "No Results"
                            if "검색결과가 없습니다" in driver.page_source:
                                vol = 0
                                status = "zero"
                            else:
                                # Count items just in case
                                items = driver.find_elements(By.CSS_SELECTOR, "li.bx")
                                if items:
                                    # If items exist but no count, it's ambiguous.
                                    # Desktop usually shows count. If missing, might be very few?
                                    vol = len(items)
                                    status = "fallback_count"
                                else:
                                    vol = 0
                                    status = "error_layout"

                    except Exception as e:
                        pass
                    
                    worker_results.append({
                        "keyword": kw,
                        "volume": vol,
                        "status": status
                    })
                    
                    if idx % 5 == 0:
                        print(f"   [W{worker_id}] '{kw}' -> {vol}")
                        
        except Exception as e:
            print(f"🔥 Worker {worker_id} init failed: {e}")
            pass
            
        return worker_results

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    
    # Test Run with just 2 workers for test
    scanner = FastVolumeScanner(max_workers=2)
    test_kws = ["청주 다이어트", "청주 맛집", "없는키워드12345", "청주 한의원", "다이어트 식단"]
    res = scanner.scan(test_kws)
    for r in res:
        print(r)

if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    import urllib3
    urllib3.disable_warnings()
    
    scanner = FastVolumeScanner()
    test_kws = ["청주 다이어트", " 청주 다이어트 한의원", "없는키워드12345"]
    res = scanner.scan(test_kws)
    for r in res:
        print(r)
