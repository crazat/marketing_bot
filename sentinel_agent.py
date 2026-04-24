import os
import sys
import time
import json
import random
import logging
import hashlib
import uuid
import functools
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from utils import ConfigManager
from db.database import DatabaseManager
from alert_bot import TelegramBot

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate_json

# --- CONFIGURATION ---
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs', 'sentinel.log')

# Setup Logging
logger = logging.getLogger("Sentinel")
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

# File Handler
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
fh = logging.FileHandler(LOG_FILE, encoding='utf-8')
fh.setFormatter(formatter)
logger.addHandler(fh)

# Console Handler (Optional, for debugging)
ch = logging.StreamHandler()
ch.setFormatter(formatter)
logger.addHandler(ch)

# --- USER-AGENT POOL (P2: User-Agent Rotation) ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15"
]

# --- CACHE TTL ---
CACHE_TTL_SECONDS = 86400  # 24 hours


def retry_on_error(max_retries=3, base_delay=2):
    """
    P2: Retry decorator with exponential backoff.
    Delays: 2s, 4s, 8s (base_delay * 2^attempt)
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2 ** attempt)
                        logger.warning(f"[Retry] {func.__name__} failed (attempt {attempt + 1}/{max_retries}): {e}. Retrying in {delay}s...")
                        time.sleep(delay)
                    else:
                        logger.error(f"[Retry] {func.__name__} failed after {max_retries} attempts: {e}")
            return []  # Return empty array on final failure
        return wrapper
    return decorator


class SentinelBrain:
    def __init__(self):
        self.config = ConfigManager()

        # P0: Load targets file for competitors
        targets_path = os.path.join(self.config.root_dir, 'config', 'sentinel_targets.json')
        self.competitors = []
        if os.path.exists(targets_path):
            with open(targets_path, 'r', encoding='utf-8') as f:
                targets = json.load(f)
                self.competitors = targets.get('competitors', [])

        logger.info(f"[Sentinel] Brain Initialized with centralized ai_client")
        logger.info(f"[Sentinel] Monitoring competitors: {self.competitors}")

    def analyze_threat(self, query, text_snippet):
        """
        Analyzes a text snippet for threats using centralized AI client.
        P0: Uses dynamic competitors list from config.
        P0: Returns UNKNOWN on error instead of SAFE.
        """
        # P0: Build competitors string for prompt
        competitors_str = ", ".join(self.competitors) if self.competitors else "None specified"

        prompt = f"""
        You are 'Reputation Sentinel', an AI watchdog for 'Kyurim Clinic (Cheongju)'.
        Analyze the following search result for the query: "{query}"

        [Content Snippet]
        {text_snippet[:1000]}

        [Known Competitors]
        {competitors_str}

        Determine if this content poses a threat.
        Classify into ONE of these categories:
        1. BRAND_RISK: Negative sentiment about 'Kyurim' (Side effects, rude, expensive).
        2. COMPETITOR_VIRAL: Highly suspicious viral marketing for the known competitors listed above.
        3. LOST_OPPORTUNITY: A user asking for recommendations where competitors are heavily recommended.
        4. SAFE: Natural content or positive content about specific clinic.
        5. UNKNOWN: Cannot determine due to ambiguous content (requires manual review).

        Return JSON ONLY:
        {{
            "classification": "BRAND_RISK" | "COMPETITOR_VIRAL" | "LOST_OPPORTUNITY" | "SAFE" | "UNKNOWN",
            "danger_score": 0-100,
            "reason": "Brief explanation",
            "competitor_name": "Name if applicable, else null"
        }}
        """

        try:
            result = ai_generate_json(prompt, temperature=0.3)
            if result:
                return result
            logger.error("[Brain] AI returned None")
            return {"classification": "UNKNOWN", "danger_score": 50, "reason": "AI returned empty response", "competitor_name": None}
        except Exception as e:
            logger.error(f"[Brain] Analysis Error: {e}")
            return {"classification": "UNKNOWN", "danger_score": 50, "reason": f"Analysis Error: {str(e)[:50]}", "competitor_name": None}


class SentinelScout:
    def __init__(self):
        self.config_mgr = ConfigManager()
        self.targets_path = os.path.join(self.config_mgr.root_dir, 'config', 'sentinel_targets.json')
        self.state_path = os.path.join(self.config_mgr.root_dir, 'db', 'sentinel_state.json')
        self.cache_path = os.path.join(self.config_mgr.root_dir, 'db', 'sentinel_cache.json')
        self.load_targets()

        # P1: URL Analysis Cache (with file persistence)
        self._analysis_cache = {}
        self._load_cache_from_file()

        # P1: Database for history
        self.db = DatabaseManager()

        # Telegram Alert Bot
        secrets = self.config_mgr.load_secrets()
        bot_token = secrets.get("TELEGRAM_BOT_TOKEN", "")
        chat_id = secrets.get("TELEGRAM_CHAT_ID", "")
        self.telegram = TelegramBot(bot_token, chat_id)
        self._alerted_urls = set()  # Prevent duplicate alerts within session

    def load_targets(self):
        if os.path.exists(self.targets_path):
            with open(self.targets_path, 'r', encoding='utf-8') as f:
                self.targets = json.load(f)
        else:
            self.targets = {"brand_keywords": [], "battleground_keywords": [], "selectors": {}}
            logger.warning("Target file not found.")

    # --- Cache Persistence Methods ---
    def _load_cache_from_file(self):
        """Load cache from file on startup."""
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self._analysis_cache = json.load(f)
                # Clean expired entries
                now = time.time()
                expired_keys = [k for k, v in self._analysis_cache.items()
                               if (now - v.get('cached_at', 0)) >= CACHE_TTL_SECONDS]
                for k in expired_keys:
                    del self._analysis_cache[k]
                logger.info(f"[Cache] Loaded {len(self._analysis_cache)} entries from file (removed {len(expired_keys)} expired)")
            except Exception as e:
                logger.warning(f"[Cache] Failed to load cache file: {e}")
                self._analysis_cache = {}

    def _save_cache_to_file(self):
        """Persist cache to file."""
        try:
            with open(self.cache_path, 'w', encoding='utf-8') as f:
                json.dump(self._analysis_cache, f, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"[Cache] Failed to save cache file: {e}")

    # --- Telegram Alert Methods ---
    def _send_threat_alert(self, threat_data: dict):
        """Send Telegram alert for detected threat."""
        url = threat_data.get('url', '')
        if url in self._alerted_urls:
            return  # Skip duplicate alerts

        threat_type = threat_data.get('type', 'UNKNOWN')
        emoji_map = {
            'BRAND_RISK': '🚨',
            'COMPETITOR_VIRAL': '⚠️',
            'LOST_OPPORTUNITY': '💡',
            'UNKNOWN': '❓'
        }
        emoji = emoji_map.get(threat_type, '📢')

        message = f"""{emoji} *[Sentinel Alert: {threat_type}]*
키워드: {threat_data.get('keyword', 'N/A')}
제목: {threat_data.get('title', 'N/A')[:50]}
위험도: {threat_data.get('score', 0)}/100
사유: {threat_data.get('reason', 'N/A')[:100]}
[바로가기]({url})"""

        self.telegram.send_message(message)
        self._alerted_urls.add(url)

    # --- P1: Cache Methods ---
    def _get_cache_key(self, url: str) -> str:
        """Generate SHA256 hash of URL for cache key."""
        return hashlib.sha256(url.encode('utf-8')).hexdigest()

    def _is_cache_valid(self, cache_entry: dict) -> bool:
        """Check if cache entry is still within TTL."""
        if not cache_entry:
            return False
        cached_at = cache_entry.get('cached_at', 0)
        return (time.time() - cached_at) < CACHE_TTL_SECONDS

    def _get_from_cache(self, url: str) -> dict:
        """Retrieve analysis result from cache if valid."""
        cache_key = self._get_cache_key(url)
        cache_entry = self._analysis_cache.get(cache_key)
        if cache_entry and self._is_cache_valid(cache_entry):
            logger.debug(f"[Cache] HIT: {url[:50]}...")
            return cache_entry.get('result')
        return None

    def _save_to_cache(self, url: str, result: dict):
        """Save analysis result to cache (memory + file)."""
        cache_key = self._get_cache_key(url)
        self._analysis_cache[cache_key] = {
            'result': result,
            'cached_at': time.time()
        }
        logger.debug(f"[Cache] SAVED: {url[:50]}...")
        # Persist to file every 10 new entries
        if len(self._analysis_cache) % 10 == 0:
            self._save_cache_to_file()

    def update_state(self, health_score, active_threats, unknown_threats=None):
        """Update sentinel state file with current scan results."""
        state = {
            "last_scan": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "health_score": health_score,
            "active_threats": active_threats,
            "unknown_threats": unknown_threats or [],
            "status": "ACTIVE"
        }
        with open(self.state_path, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

    def patrol(self):
        from db.status_manager import status_manager  # 수정안 3: 상태 관리
        brain = SentinelBrain()
        logger.info("[Sentinel] Patrol Started...")

        while True:
            # 수정안 2: 사이클별 에러 격리
            try:
                # Generate scan batch ID for tracking
                scan_id = str(uuid.uuid4())[:8]
                logger.info(f"[Sentinel] Scan Batch: {scan_id}")

                # 1. Refresh Targets
                self.load_targets()
                threats = []
                unknown_threats = []  # P0: Separate list for UNKNOWN classification

                # 2. Scan Brand Keywords (Priority 1)
                for kw in self.targets.get('brand_keywords', []):
                    try:
                        logger.info(f"[Scan] Brand Zone: {kw}")
                        results = self.search_naver_view(kw)
                        for res in results:
                            # P1: Check cache first
                            cached_result = self._get_from_cache(res['url'])
                            if cached_result:
                                analysis = cached_result
                            else:
                                analysis = brain.analyze_threat(kw, res['text'])
                                self._save_to_cache(res['url'], analysis)

                            threat_data = {
                                "scan_id": scan_id,
                                "type": analysis['classification'],
                                "keyword": kw,
                                "title": res['title'],
                                "url": res['url'],
                                "score": analysis['danger_score'],
                                "reason": analysis['reason'],
                                "competitor_name": analysis.get('competitor_name')
                            }

                            if analysis['classification'] == 'BRAND_RISK' and analysis['danger_score'] > 60:
                                logger.warning(f"[ALERT] BRAND RISK: {res['title']}")
                                threats.append(threat_data)
                                self.db.insert_sentinel_threat(threat_data)
                                self._send_threat_alert(threat_data)  # Telegram alert
                            elif analysis['classification'] == 'UNKNOWN':
                                logger.info(f"[UNKNOWN] Needs Review: {res['title']}")
                                unknown_threats.append(threat_data)
                                self.db.insert_sentinel_threat(threat_data)
                    except Exception as kw_err:
                        logger.error(f"[Scan] Brand keyword '{kw}' failed: {kw_err}")
                        continue  # 다음 키워드 진행

                    time.sleep(random.uniform(5, 10))

                # 3. Scan Battleground (Priority 2)
                for kw in self.targets.get('battleground_keywords', []):
                    try:
                        logger.info(f"[Scan] Battleground: {kw}")
                        results = self.search_naver_view(kw)
                        for res in results:
                            # P1: Check cache first
                            cached_result = self._get_from_cache(res['url'])
                            if cached_result:
                                analysis = cached_result
                            else:
                                analysis = brain.analyze_threat(kw, res['text'])
                                self._save_to_cache(res['url'], analysis)

                            threat_data = {
                                "scan_id": scan_id,
                                "type": analysis['classification'],
                                "keyword": kw,
                                "title": res['title'],
                                "url": res['url'],
                                "score": analysis['danger_score'],
                                "reason": analysis['reason'],
                                "competitor_name": analysis.get('competitor_name')
                            }

                            if analysis['classification'] in ['COMPETITOR_VIRAL', 'LOST_OPPORTUNITY'] and analysis['danger_score'] > 70:
                                logger.info(f"[ALERT] {analysis['classification']}: {res['title']}")
                                threats.append(threat_data)
                                self.db.insert_sentinel_threat(threat_data)
                                self._send_threat_alert(threat_data)  # Telegram alert
                            elif analysis['classification'] == 'UNKNOWN':
                                logger.info(f"[UNKNOWN] Needs Review: {res['title']}")
                                unknown_threats.append(threat_data)
                                self.db.insert_sentinel_threat(threat_data)
                    except Exception as kw_err:
                        logger.error(f"[Scan] Battleground keyword '{kw}' failed: {kw_err}")
                        continue  # 다음 키워드 진행

                    time.sleep(random.uniform(5, 10))

                # Save cache to file at end of each patrol cycle
                self._save_cache_to_file()

                # 4. Calculate Health Score
                # P0: UNKNOWN threats get -3 points
                health = 100
                for t in threats:
                    if t['type'] == 'BRAND_RISK':
                        health -= 20
                    elif t['type'] == 'COMPETITOR_VIRAL':
                        health -= 5
                    elif t['type'] == 'LOST_OPPORTUNITY':
                        health -= 10

                # P0: Apply UNKNOWN penalty
                health -= len(unknown_threats) * 3

                health = max(0, health)

                # 5. Report State
                self.update_state(health, threats, unknown_threats)
                logger.info(f"[Sentinel] Cycle Complete. Health: {health}. Threats: {len(threats)}. Unknown: {len(unknown_threats)}")

                # 수정안 3: 사이클 완료 시 상태 업데이트
                status_manager.update_status(
                    "Reputation Sentinel",
                    "IDLE",
                    f"Cycle complete. Health: {health}. Next scan in 30m"
                )

            except Exception as cycle_err:
                # 수정안 2: 사이클 실패해도 다음 사이클 진행
                logger.error(f"[Sentinel] Cycle Failed: {cycle_err}")
                self.update_state(0, [], [])  # 실패 상태 기록
                status_manager.update_status(
                    "Reputation Sentinel",
                    "ERROR",
                    f"Cycle failed: {str(cycle_err)[:100]}"
                )

            finally:
                # Sleep before next full patrol
                sleep_time = 1800  # 30 mins
                logger.info(f"[Sentinel] Resting for {sleep_time / 60} mins...")
                time.sleep(sleep_time)

    @retry_on_error(max_retries=3, base_delay=2)
    def search_naver_view(self, keyword):
        """
        Scraper for Naver VIEW/Blog tab.
        P2: Uses configurable selectors.
        P2: Rotates User-Agent.
        P2: Applies retry logic via decorator.
        """
        url = f"https://search.naver.com/search.naver?where=view&sm=tab_jum&query={keyword}"

        # P2: Random User-Agent selection
        headers = {
            "User-Agent": random.choice(USER_AGENTS)
        }

        res = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(res.text, 'html.parser')

        # P2: Get selectors from config
        selectors = self.targets.get('selectors', {}).get('naver_view', {})
        container_selectors = selectors.get('container', ['.view_wrap', '.total_wrap'])
        title_selectors = selectors.get('title', ['.title_link', '.api_txt_lines'])
        desc_selectors = selectors.get('description', ['.dsc_link', '.api_txt_lines.dsc_txt'])

        # Try container selectors in order
        items = []
        for selector in container_selectors:
            items = soup.select(selector)
            if items:
                break

        results = []
        for item in items[:3]:  # Top 3 only
            title_el = None
            for selector in title_selectors:
                title_el = item.select_one(selector)
                if title_el:
                    break

            desc_el = None
            for selector in desc_selectors:
                desc_el = item.select_one(selector)
                if desc_el:
                    break

            if title_el:
                title = title_el.get_text(strip=True)
                link = title_el.get('href')
                desc = desc_el.get_text(strip=True) if desc_el else ""
                results.append({"title": title, "url": link, "text": title + " " + desc})

        return results


if __name__ == "__main__":
    from db.status_manager import status_manager
    try:
        status_manager.update_status("Reputation Sentinel", "RUNNING", "Starting Watchdog Sequence")
        scout = SentinelScout()
        scout.patrol()
    except KeyboardInterrupt:
        status_manager.update_status("Reputation Sentinel", "STOPPED", "Manual Interruption")
    except Exception as e:
        logger.critical(f"Sentinel Crashed: {e}")
        status_manager.update_status("Reputation Sentinel", "ERROR", str(e))
