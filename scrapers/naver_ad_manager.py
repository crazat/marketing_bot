
import time
import hmac
import hashlib
import base64
import requests
import os
import sys
import logging

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils import ConfigManager

logger = logging.getLogger("NaverAdManager")

class NaverAdManager:
    """
    Manages communication with Naver Search Ad API (RelKwdStat).
    Retrieves precise monthly search volume (PC + Mobile).

    [API Key Rotation]
    - 여러 API 키 지원: NAVER_AD_ACCESS_KEY, NAVER_AD_ACCESS_KEY_2, NAVER_AD_ACCESS_KEY_3...
    - 할당량 초과(429) 시 자동으로 다음 키로 전환
    """
    BASE_URL = "https://api.naver.com"

    def __init__(self):
        self.config = ConfigManager()

        # [API Key Rotation] 여러 키 로드
        self.api_keys = []
        self._load_api_keys()

        self.current_key_index = 0

        if not self.api_keys:
            logger.warning("⚠️ Naver Ad API credentials missing! Search Volume will be unavailable.")
            self.disabled = True
        else:
            self.disabled = False
            self._set_current_key(0)
            logger.info(f"✅ Naver Ad API 로드: {len(self.api_keys)}개 키 사용 가능")

        # [CACHING] In-memory cache for current session
        self._memory_cache = {}  # {keyword: {volume: int, cached_at: datetime}}
        self._cache_ttl_days = 7  # Cache validity: 7 days

        # Initialize DB cache table
        self._init_cache_table()

    def _load_api_keys(self):
        """여러 API 키 로드 (NAVER_AD_ACCESS_KEY, _2, _3...)"""
        # 기본 키
        key1 = self.config.get_api_key("NAVER_AD_ACCESS_KEY")
        secret1 = self.config.get_api_key("NAVER_AD_SECRET_KEY")
        customer1 = self.config.get_api_key("NAVER_AD_CUSTOMER_ID")

        if key1 and secret1 and customer1:
            self.api_keys.append({
                'access_key': key1,
                'secret_key': secret1,
                'customer_id': customer1,
                'exhausted': False
            })

        # 추가 키 (_2, _3, _4...)
        for i in range(2, 10):
            key = self.config.get_api_key(f"NAVER_AD_ACCESS_KEY_{i}")
            secret = self.config.get_api_key(f"NAVER_AD_SECRET_KEY_{i}")
            customer = self.config.get_api_key(f"NAVER_AD_CUSTOMER_ID_{i}")

            if key and secret and customer:
                self.api_keys.append({
                    'access_key': key,
                    'secret_key': secret,
                    'customer_id': customer,
                    'exhausted': False
                })
            else:
                break  # 연속된 키가 없으면 중단

    def _set_current_key(self, index: int):
        """현재 사용할 API 키 설정"""
        if 0 <= index < len(self.api_keys):
            self.current_key_index = index
            current = self.api_keys[index]
            self.api_key = current['access_key']
            self.secret_key = current['secret_key']
            self.customer_id = current['customer_id']
            return True
        return False

    def _rotate_to_next_key(self) -> bool:
        """다음 API 키로 전환 (할당량 초과 시)"""
        # 현재 키를 exhausted로 표시
        if self.api_keys:
            self.api_keys[self.current_key_index]['exhausted'] = True

        # 사용 가능한 다음 키 찾기
        for i in range(len(self.api_keys)):
            next_index = (self.current_key_index + 1 + i) % len(self.api_keys)
            if not self.api_keys[next_index]['exhausted']:
                self._set_current_key(next_index)
                logger.info(f"🔄 API 키 로테이션: 키 #{next_index + 1}로 전환")
                return True

        # 모든 키 소진
        logger.warning("⚠️ 모든 API 키 할당량 소진!")
        return False

    def _reset_exhausted_keys(self):
        """모든 키의 exhausted 상태 초기화 (새 세션 시작 시)"""
        for key in self.api_keys:
            key['exhausted'] = False



    def _generate_signature(self, timestamp, method, uri):
        """Generates HMAC-SHA256 signature for Naver Ad API."""
        message = f"{timestamp}.{method}.{uri}"
        hash = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256)
        return base64.b64encode(hash.digest()).decode("utf-8")

    def _get_headers(self, method, uri):
        timestamp = str(int(time.time() * 1000))
        signature = self._generate_signature(timestamp, method, uri)
        
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "X-Timestamp": timestamp,
            "X-API-KEY": self.api_key,
            "X-Customer": str(self.customer_id),
            "X-Signature": signature
        }
    
    # ============================================================
    # CACHING LAYER: 7-day cache for keyword volumes
    # ============================================================
    
    def _init_cache_table(self):
        """Initialize SQLite cache table for keyword volumes"""
        try:
            import sqlite3
            with sqlite3.connect(self.config.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.execute('''CREATE TABLE IF NOT EXISTS keyword_volume_cache (
                    keyword TEXT PRIMARY KEY,
                    volume INTEGER,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
                conn.commit()
        except Exception as e:
            logger.warning(f"Failed to init cache table: {e}")
    
    def _get_cached_volumes(self, keywords):
        """
        Check cache (memory + DB) for keyword volumes.
        Returns: (cached_results: dict, uncached_keywords: list)
        """
        from datetime import datetime, timedelta
        import sqlite3
        
        cached_results = {}
        uncached = []
        cutoff_date = datetime.now() - timedelta(days=self._cache_ttl_days)
        
        for kw in keywords:
            # 1. Check memory cache first
            if kw in self._memory_cache:
                entry = self._memory_cache[kw]
                if entry['cached_at'] > cutoff_date:
                    cached_results[kw] = entry['volume']
                    continue
            
            # Not in memory, will check DB later
            uncached.append(kw)
        
        if not uncached:
            return cached_results, []
        
        # 2. Check DB cache for remaining
        still_uncached = []
        try:
            with sqlite3.connect(self.config.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                placeholders = ','.join(['?'] * len(uncached))
                cursor.execute(f'''
                    SELECT keyword, volume, cached_at 
                    FROM keyword_volume_cache 
                    WHERE keyword IN ({placeholders})
                ''', uncached)
                
                db_results = {row[0]: {'volume': row[1], 'cached_at': datetime.fromisoformat(row[2])} 
                             for row in cursor.fetchall()}
                
                for kw in uncached:
                    if kw in db_results:
                        entry = db_results[kw]
                        if entry['cached_at'] > cutoff_date:
                            cached_results[kw] = entry['volume']
                            # Also update memory cache
                            self._memory_cache[kw] = entry
                        else:
                            still_uncached.append(kw)  # Expired
                    else:
                        still_uncached.append(kw)
        except Exception as e:
            logger.warning(f"Cache read error: {e}")
            still_uncached = uncached
        
        return cached_results, still_uncached
    
    def _save_to_cache(self, results):
        """
        Save keyword volumes to both memory and DB cache.
        """
        from datetime import datetime
        import sqlite3
        
        now = datetime.now()
        
        # 1. Update memory cache
        for kw, vol in results.items():
            self._memory_cache[kw] = {'volume': vol, 'cached_at': now}
        
        # 2. Update DB cache
        try:
            with sqlite3.connect(self.config.db_path, timeout=10) as conn:
                cursor = conn.cursor()
                cursor.executemany('''
                    INSERT OR REPLACE INTO keyword_volume_cache (keyword, volume, cached_at)
                    VALUES (?, ?, ?)
                ''', [(kw, vol, now.isoformat()) for kw, vol in results.items()])
                conn.commit()
        except Exception as e:
            logger.warning(f"Cache write error: {e}")

    def get_keyword_volumes(self, keywords):
        """
        Retrieves monthly search volume for a list of keywords.
        Returns a dictionary: {keyword: total_search_volume}
        
        [CACHING] Uses 7-day cache to minimize API calls:
        1. Check memory cache
        2. Check SQLite cache
        3. Only call API for uncached keywords
        4. Save new results to cache
        """
        if not (self.api_key and self.secret_key):
            return {}

        # Circuit Breaker check
        if getattr(self, 'disabled', False):
            return {}
        
        # [CACHE FIRST] Check cached volumes
        cached_results, uncached_keywords = self._get_cached_volumes(keywords)
        
        if cached_results:
            logger.info(f"💾 Cache HIT: {len(cached_results)}/{len(keywords)} keywords from cache")
        
        if not uncached_keywords:
            return cached_results  # All from cache!
        
        logger.info(f"🔍 Fetching {len(uncached_keywords)} uncached keywords from API...")

        api_results = {}
        uri = "/keywordstool"
        method = "GET"

        chunk_size = 5
        chunks = [uncached_keywords[i:i + chunk_size] for i in range(0, len(uncached_keywords), chunk_size)]

        for chunk in chunks:
            if getattr(self, 'disabled', False): break
            
            try:
                query_params = {
                    "hintKeywords": ",".join([k.replace(" ", "") for k in chunk]),
                    "showDetail": 1
                }
                # logger.info(f"DEBUG AD API: {query_params['hintKeywords']}")
                
                headers = self._get_headers(method, uri)
                
                resp = requests.get(self.BASE_URL + uri, params=query_params, headers=headers, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    keyword_list = data.get("keywordList", [])
                    # logger.info(f"   API 200 OK. Received {len(keyword_list)} items. First: {keyword_list[0] if keyword_list else 'None'}")
                    
                    for item in keyword_list:
                        kw = item["relKeyword"].strip()
                        
                        # Parse PC/Mobile Counts
                        pc_cnt = item["monthlyPcQcCnt"]
                        mo_cnt = item["monthlyMobileQcCnt"]
                        
                        if isinstance(pc_cnt, str) and "<" in pc_cnt: pc_cnt = 5
                        if isinstance(mo_cnt, str) and "<" in mo_cnt: mo_cnt = 5
                        
                        total_vol = int(pc_cnt) + int(mo_cnt)
                        
                        # [UNLEASHED MODE]
                        # Capture EVERYTHING the API gives us.
                        # This typically returns 100+ related keywords for every 5 inputs.
                        api_results[kw] = total_vol
                        
                    # Ensure original seeds are present (even if 0 vol) to prevent key errors
                    for k in chunk:
                        # API might return "청주다이어트" (no space) when we asked "청주 다이어트"
                        # Simple normalization check
                        found = False
                        k_norm = k.replace(" ", "")
                        for res_key in list(api_results.keys()):
                            if res_key.replace(" ", "") == k_norm:
                                found = True
                                break
                        if not found:
                            api_results[k] = 0
                            
                    time.sleep(0.2) # Rate limit safety (limit is high but good practice)
                    
                elif resp.status_code == 429:
                    # [API Key Rotation] 할당량 초과 - 다음 키로 전환
                    logger.warning(f"⚠️ API 할당량 초과 (429) - 키 로테이션 시도...")
                    if self._rotate_to_next_key():
                        # 현재 chunk 재시도
                        time.sleep(1)
                        continue
                    else:
                        logger.error("🚫 모든 API 키 할당량 소진. 중단.")
                        break

                elif resp.status_code in [401, 403]:
                    logger.error(f"🚫 Naver Ad API Auth Failed ({resp.status_code}). Trying next key...")
                    if not self._rotate_to_next_key():
                        logger.error("🚫 모든 API 키 인증 실패. Disabling.")
                        self.disabled = True
                        break
                else:
                    logger.error(f"Naver Ad API Error {resp.status_code}: {repr(resp.content)}")
                    time.sleep(1) # Backoff

            except Exception as e:
                logger.error(f"Error fetching AD API for chunk: {e}")
        
        # [CACHE] Save new API results to cache
        if api_results:
            self._save_to_cache(api_results)
            logger.info(f"💾 Cached {len(api_results)} new keyword volumes")
        
        # Merge cached + API results (None 방어 처리)
        cached_results = cached_results if cached_results else {}
        api_results = api_results if api_results else {}
        final_results = {**cached_results, **api_results}
        return final_results

if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)
    mgr = NaverAdManager()
    kws = ["청주다이어트", "청주 공황장애"]
    vols = mgr.get_keyword_volumes(kws)
    print(f"Test Results: {vols}")
