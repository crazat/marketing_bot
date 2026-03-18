import requests
from urllib3.util.retry import Retry
import time
import random
import logging
import json
import re
from bs4 import BeautifulSoup
from urllib.parse import quote
from utils import ConfigManager

# Configure Logger in a way that plays nice with the main system
logger = logging.getLogger("KeywordHarvester")
logging.basicConfig(level=logging.INFO)

class KeywordHarvester:
    """
    The 'Snowball' Engine.
    Recursively gathers related keywords from Naver to build a massive target pool.
    """
    # [Filter] Strictly whitelist medical/clinic related terms
    MEDICAL_KEYWORDS = [
        # Facilities
        "병원", "의원", "한의원", "클리닉", "내과", "외과", "치과", "피부과", "성형외과", 
        "산부인과", "비뇨기과", "정형외과", "이비인후과", "정신과", "소아과", "안과", "요양병원",
        # Treatments & Procedures
        "치료", "수술", "시술", "교정", "검사", "진료", "입원", "재활", "처방",
        "다이어트", "비만", "살빼기", "식단", "피티", "요가", "필라테스", # Health/Fitness allows
        "여드름", "피부", "모공", "흉터", "점빼기", "아토피", "습진", "두드러기", "탈모",
        "보톡스", "필러", "리프팅", "슈링크", "인모드", "울쎄라", "제모", "레이저",
        "통증", "디스크", "관절", "염좌", "교통사고", "후유증", "추나", "도수",
        "한약", "보약", "임플란트", "스케일링", "사랑니", "미백", "라식", "라섹",
        "우울증", "불면증", "공황장애", "상담", "언어치료", "발달센터"
    ]
    
    # [Filter] Explicit Blacklist
    BLACKLIST_KEYWORDS = [
        "유기견", "강아지", "고양이", "동물", "분양", "미용", "호텔", "카페", "맛집", 
        "물류", "이사", "용달", "퀵", "수리", "정비", "세탁", "청소", "철거", "폐기물",
        "학원", "과외", "학교", "유치원", "어린이집", "부동산", "아파트", "매매", "전세",
        "여행", "숙소", "펜션", "모텔", "대출", "보험", "법률", "변호사", "노무사"
    ]

    def __init__(self):
        self.headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        }
        self.config = ConfigManager()
        
        # [Multi-Key Support] Load all available Search API keys
        self.api_keys = self.config.get_api_key_list("NAVER_SEARCH_KEYS")
        
        # Fallback to legacy behavior if list is empty
        if not self.api_keys:
            # 1. Try numbered keys first (NAVER_SEARCH_CLIENT_ID_1, _2...)
            for i in range(1, 10):
                cid = self.config.get_api_key(f"NAVER_SEARCH_CLIENT_ID_{i}")
                sec = self.config.get_api_key(f"NAVER_SEARCH_SECRET_{i}")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})
            
            # 2. If no numbered keys, try standard specific keys
            if not self.api_keys:
                cid = self.config.get_api_key("NAVER_SEARCH_CLIENT_ID")
                sec = self.config.get_api_key("NAVER_SEARCH_SECRET")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})
                    
            # 3. Fallback to legacy global keys
            if not self.api_keys:
                cid = self.config.get_api_key("NAVER_CLIENT_ID")
                sec = self.config.get_api_key("NAVER_CLIENT_SECRET")
                if cid and sec:
                    self.api_keys.append({"id": cid, "secret": sec})
        
        self.current_key_index = 0
        if self.api_keys:
            logger.info(f"🗝️ Loaded {len(self.api_keys)} Search API Key(s) for rotation.")
        else:
            logger.warning("⚠️ No Naver Search API keys found!")

        self.session = requests.Session()
        
        # [Crucial Fix] Increase Pool & Add Backoff Strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=50, 
            pool_maxsize=50,
            max_retries=retry_strategy
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        
        # [Circuit Breaker] Global state track consecutive failures
        self.consecutive_429s = 0
        
        self.session.headers.update(self.headers)

    def _check_circuit_breaker(self):
        """
        Checks if the circuit breaker is open. If so, sleeps until cooldown.
        """
        # If we had too many consecutive 429s, pause operations
        if self.consecutive_429s >= 10:
            logger.error(f"⛔ CIRCUIT BREAKER TRIPPED! Too many 429s ({self.consecutive_429s}). Sleeping 60s...")
            time.sleep(60)
            self.consecutive_429s = 0 # Reset after penalty

    def _get_next_headers(self):
        """Rotates API keys and returns headers for the next request."""
        if not self.api_keys:
            return {}
            
        # Round-robin rotation
        key_data = self.api_keys[self.current_key_index]
        self.current_key_index = (self.current_key_index + 1) % len(self.api_keys)
        
        return {
            "X-Naver-Client-Id": key_data["id"],
            "X-Naver-Client-Secret": key_data["secret"]
        }

    def harvest(self, seeds, depth=1, max_limit=1000):
        """
        Main entry point.
        seeds: list of starting keywords
        depth: 1 = scan seeds, 2 = scan results of depth 1
        """
        if isinstance(seeds, str):
            seeds = [seeds]
            
        collected = set(seeds)
        queue = list(seeds)
        history = set(seeds) # To avoid re-scanning
        
        logger.info(f"❄️ Snowball started with {len(seeds)} seeds (Target Depth: {depth})...")
        
        current_depth = 0
        while current_depth < depth and len(collected) < max_limit:
            current_depth += 1
            logger.info(f"🔄 Processing Depth {current_depth} (Queue: {len(queue)})...")
            
            next_queue = []
            
            for idx, keyword in enumerate(queue):
                if len(collected) >= max_limit:
                    break
                    
                # Rate Limiting (Fast but polite)
                time.sleep(random.uniform(0.1, 0.3)) 
                
                # 1. Fetch Related (Autosuggest + Associated)
                new_kws = self._fetch_naver_related(keyword)
                
                for nk in new_kws:
                    # Clean & Filter
                    nk = nk.strip()
                    if len(nk) < 2: continue # Too short
                    if nk in collected: continue
                    
                    collected.add(nk)
                    next_queue.append(nk)
                    
                # Progress Log every 10 items
                if idx % 10 == 0:
                    print(f"   [{idx}/{len(queue)}] '{keyword}' spawned {len(new_kws)} new. Total: {len(collected)}")
            
            # Update queue for next depth
            queue = list(set(next_queue) - history)
            history.update(queue)
            
            if not queue:
                logger.info("   -> Dead end. No more keywords found.")
                break
                
        logger.info(f"✅ Harvest Complete. Gathered {len(collected)} unique keywords.")
        return list(collected)



    def get_naver_blog_count(self, keyword):
        """
        Gets the number of Naver blog posts for a keyword using Naver Search API.
        This is the 'Supply' metric for KEI calculation.
        """
        # Redundant imports removed
        
        if not self.api_keys:
            return 0

        # [Circuit Breaker] Check strictly before making ANY requests
        self._check_circuit_breaker()
            
        url = "https://openapi.naver.com/v1/search/blog.json"
        
        # [Rotation] Get headers with the next key in line
        # headers = self._get_next_headers() # MOVED INSIDE RETRY LOOP
        params = {"query": keyword, "display": 1, "sort": "sim"}
        
        # [Safety Net] Explicit Loop to catch Connection/Pool errors and WAIT
        max_retries = len(self.api_keys) + 1
        for attempt in range(max_retries):
            # Get current key headers
            headers = self._get_next_headers() if attempt > 0 else self._get_next_headers() # Always get next? Or stick?
            # Better logic: Keep current unless error
            if attempt == 0:
                 # Re-use current index for first attempt (don't rotate yet)
                 # But _get_next_headers autoincrements. Need separate get_current?
                 # For simplicity, we just rotate on every retry or let the helper handle it.
                 # Let's simple rotate on error.
                 # Hack: _get_next_headers rotates. We might rotate unnecessarily on first call?
                 # Let's adjust _get_next_headers behavior or just accept it (Round Robin is fine).
                 pass
            
            try:
                resp = self.session.get(url, headers=headers, params=params, timeout=5)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Success resets the circuit breaker count
                    self.consecutive_429s = 0
                    
                    # [Throttling] Prevent hitting 10 QPS limit
                    time.sleep(0.1)
                    return data.get('total', 0)
                    
                elif resp.status_code in [429, 403]:
                    self.consecutive_429s += 1
                    logger.warning(f"⚠️ Search API Quota Exceeded/Auth Error ({resp.status_code}). Rotating key... (Consecutive Failures: {self.consecutive_429s})")
                    time.sleep(0.5)
                    continue # Try next key
                else:
                    logger.error(f"Search API Error {resp.status_code}")
                    break
                    
            except Exception as e:
                logger.error(f"Request Error: {e}")
                time.sleep(1)
        
        return 0



    def _is_medically_relevant(self, keyword):
        """
        Filters junk keywords using Whitelist/Blacklist approach.
        Returns True if the keyword is marketing-worthy for the clinic.
        """
        # 1. Check Blacklist first (Fast fail)
        for bad in self.BLACKLIST_KEYWORDS:
            if bad in keyword:
                return False
                
        # 2. Check Whitelist (Must contain at least one medical term)
        for good in self.MEDICAL_KEYWORDS:
            if good in keyword:
                return True
                
        # 3. Special Case: Brand Name "규림"
        if "규림" in keyword:
            return True
            
        return False

    def _fetch_naver_related(self, keyword):
        """
        Fetches related keywords from multiple sources and merges them.
        """
        results = set()
        
        # [Strategy 1a] Desktop Autosuggest API
        try:
            enc_kw = quote(keyword)
            ac_url = f"https://ac.search.naver.com/nx/ac?q={enc_kw}&con=1&frm=nv&ans=2&r_format=json&q_enc=UTF-8&st=100&r_enc=UTF-8"
            ac_resp = self.session.get(ac_url, timeout=2, verify=False)
            if ac_resp.status_code == 200:
                data = ac_resp.json()
                items = data.get('items', [])
                for group in items:
                    for item in group:
                        if item and isinstance(item, list):
                            kw = item[0]
                            if self._is_medically_relevant(kw):
                                results.add(kw)
        except Exception as e:
            # [Phase 2] 로깅 추가 (디버깅용)
            if self.verbose:
                print(f"   ⚠️ Desktop autosuggest failed: {e}")

        # [Strategy 1b] Mobile Autosuggest API (Often richer)
        try:
            mac_url = f"https://mac.search.naver.com/mobile/ac?q={enc_kw}&con=1&frm=nv&ans=2&r_format=json&q_enc=UTF-8&st=100&r_enc=UTF-8"
            mac_resp = self.session.get(mac_url, timeout=2, verify=False)
            if mac_resp.status_code == 200:
                data = mac_resp.json()
                items = data.get('items', [])
                for group in items:
                    for item in group:
                        if item and isinstance(item, list):
                            kw = item[0]
                            if self._is_medically_relevant(kw):
                                results.add(kw)
        except Exception as e:
            # [Phase 2] 로깅 추가 (디버깅용)
            if self.verbose:
                print(f"   ⚠️ Mobile autosuggest failed: {e}")

        # [Strategy 2] Desktop Search Scraping (Always run to maximize yield)
        try:
            # Randomize UA slightly
            self.session.headers.update({"User-Agent": f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/{random.randint(90,110)}.0.0.0 Safari/537.36"})
            
            url = f"https://search.naver.com/search.naver?query={quote(keyword)}"
            resp = self.session.get(url, timeout=3, verify=False)
            
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                
                # Verified Selectors from debug_related.py
                # 1. Text-based block splitting (most robust)
                blocks = soup.select(".related_srch, .lst_related_srch, .api_related_search")
                for block in blocks:
                    text_content = block.get_text(separator="\n").split("\n")
                    for t in text_content:
                        t = t.strip()
                        # [Filter Junk UI Text]
                        if len(t) < 2 or len(t) > 30: continue # Broadened to 30
                        if any(x in t for x in ["더보기", "열기", "닫기", "신고", "삭제", "검색어", "로그인", "회원가입", "메뉴", "바로가기"]): continue
                        if "..." in t: continue
                        
                        if self._is_medically_relevant(t):
                            results.add(t)

                # 2. Individual items (Classic)
                tags = soup.select(".lst_related_srch .item, .related_srch .tit, .related_srch a, .keyword_challenge .tit")
                for tag in tags:
                     clean = tag.get_text(strip=True)
                     # [Filter Junk UI Text]
                     if len(clean) < 2 or len(clean) > 30: continue
                     if any(x in clean for x in ["더보기", "열기", "닫기", "신고", "삭제", "검색어", "로그인", "회원가입"]): continue
                     results.add(clean)
                        
        except Exception as e:
            # print(f"DEBUG: Scraper Exception: {e}")
            pass
            
        return list(results)

if __name__ == "__main__":
    import sys
    # [Windows Fix] Force UTF-8 for console output
    sys.stdout.reconfigure(encoding='utf-8')
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Test Run
    harvester = KeywordHarvester()
    seeds = ["청주 다이어트"]
    # depth=1 first to check validity
    result = harvester.harvest(seeds, depth=1, max_limit=100)
    print(f"\nFinal Result ({len(result)}):")
    for k in result[:20]:
        print(k)
