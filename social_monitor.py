import requests
from bs4 import BeautifulSoup
import json
import os
import time
from datetime import datetime
from utils import ConfigManager, logger
from alert_bot import AlertSystem

# [OPTIMIZATION] Batch processing constants
BATCH_SIZE = 10  # Number of posts to analyze per AI call
AD_MARKERS = ["소정의 원고료", "제공받아", "업체로부터", "수수료를 지급", "광고 포함", "협찬", "체험단"]

class SocialMonitor:
    """
    Real-time Social Listener.
    Tracks keywords on Naver Blog/Cafe Search and alerts on NEW posts.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.alert_system = AlertSystem()
        self.db_path = os.path.join(self.config.root_dir, 'db', 'seen_posts.json')
        self.seen_posts = self._load_seen()
        
        # Total War Mode: Load Master List
        try:
            kw_path = os.path.join(self.config.root_dir, 'config', 'keywords_master.json')
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.keywords = []
            for cat, kw_list in data.items():
                self.keywords.extend(kw_list)
            logger.info(f"🛡️ SocialMonitor loaded {len(self.keywords)} keywords from Master List.")
        except Exception as e:
            logger.error(f"Failed to load master keywords: {e}")
            self.keywords = ["청주 규림한의원", "청주 다이어트 한의원", "청주 한약 다이어트"]
        
    def _load_seen(self):
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def _save_seen(self):
        with open(self.db_path, 'w', encoding='utf-8') as f:
            json.dump(self.seen_posts, f, indent=2)

    def search_naver_blog(self, keyword):
        """Uses Naver API to find posts (Blog + Cafe)."""
        from naver_api_client import NaverApiClient
        client = NaverApiClient()
        
        # 1. Search Blogs
        blog_results = client.search_blog(keyword, 5)
        # 2. Search Cafes
        cafe_results = client.search_cafe(keyword, 5)
        
        clean_results = []
        
        # Combine and Normalize
        # API returns keys: 'title', 'link', 'description', 'bloggername' etc.
        # HTML tags <b> need to be removed.
        import re
        def clean_html(raw_html):
            return re.sub(r'<.*?>', '', raw_html)

        raw_items = (blog_results.get('items', []) + cafe_results.get('items', []))
        
        for item in raw_items:
            try:
                title = clean_html(item['title'])
                desc = clean_html(item['description'])
                link = item['link']
                
                clean_results.append({"title": title, "link": link, "desc": desc})
            except: continue
            
        return clean_results

    def analyze_sentiment(self, text):
        """Uses Gemini to filter ads/spam and find real sentiment."""
        from ai_orchestrator import AIOrchestrator # Lazy import to avoid circular dependency if any

        # We can use the existing orchestration or utils config.
        # For simplicity/robustness, let's use the raw model from utils config.
        from google import genai

        # Configure if not already
        if not hasattr(self, 'client'):
            api_key = self.config.get_api_key()
            self.client = genai.Client(api_key=api_key)
            # FORCE Gemini 3 Flash as requested
            self.model_name = 'gemini-3-flash-preview'

        prompt = f"""
        Analyze this social media post snippet about a Clinic.
        
        [Post]: "{text}"
        
        Classify it into one of these categories:
        1. [AD] : Competitor advertisement or obvious promotion.
        2. [SPAM] : Irrelevant junk.
        3. [REVIEW_POS] : Real user review (Positive).
        4. [REVIEW_NEG] : Real user review (Negative/Complaint).
        5. [QUESTION] : User asking for info.
        
        Output JUST the Category tag (e.g. [AD]).
        """
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            return response.text.strip()
        except:
            return "[UNKNOWN]"

    def analyze_sentiment_batch(self, posts_data):
        """
        [BATCH OPTIMIZATION] Analyze multiple posts in a single AI call.
        Reduces API calls by ~80% compared to individual calls.

        Args:
            posts_data: List of dicts with 'text' and 'id' keys

        Returns:
            dict: {id: sentiment_tag}
        """
        if not posts_data:
            return {}

        from google import genai

        # Configure if not already
        if not hasattr(self, 'client'):
            api_key = self.config.get_api_key()
            self.client = genai.Client(api_key=api_key)
            self.model_name = 'gemini-3-flash-preview'
        
        # Build batch prompt
        posts_text = ""
        for i, p in enumerate(posts_data):
            posts_text += f"\n[Post {i+1}]: \"{p['text'][:200]}\"\n"
        
        prompt = f"""
Analyze these social media posts about clinics/hospitals.
For EACH post, classify into ONE category:
- [AD]: Advertisement/promotion
- [SPAM]: Irrelevant junk
- [REVIEW_POS]: Positive review
- [REVIEW_NEG]: Negative review/complaint
- [QUESTION]: User asking for info

{posts_text}

Output format (ONE per line, in order):
1. [TAG]
2. [TAG]
...

Output ONLY the numbered list, nothing else.
"""

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt
            )
            lines = response.text.strip().split('\n')
            
            results = {}
            for i, line in enumerate(lines):
                if i < len(posts_data):
                    # Extract tag from line like "1. [AD]"
                    tag = "[UNKNOWN]"
                    for possible_tag in ["[AD]", "[SPAM]", "[REVIEW_POS]", "[REVIEW_NEG]", "[QUESTION]"]:
                        if possible_tag in line:
                            tag = possible_tag
                            break
                    results[posts_data[i]['id']] = tag
            
            # Fill in any missing
            for p in posts_data:
                if p['id'] not in results:
                    results[p['id']] = "[UNKNOWN]"
            
            logger.info(f"   📊 Batch analyzed {len(posts_data)} posts in 1 API call")
            return results
            
        except Exception as e:
            logger.error(f"Batch analysis failed: {e}")
            # Fallback: return unknown for all
            return {p['id']: "[UNKNOWN]" for p in posts_data}

    def run_cycle(self):
        """
        [OPTIMIZED] Two-phase processing:
        1. Collect new posts + pre-filter obvious ads
        2. Batch AI analysis for remaining posts
        """
        logger.info("📡 Scanning Social Media (Batch Optimized Sentinel)...")
        new_findings = 0
        
        # Phase 1: Collect all new posts
        posts_to_analyze = []  # {'link', 'title', 'text', 'keyword'}
        pre_filtered_ads = 0
        
        for k in self.keywords:
            posts = self.search_naver_blog(k)
            for p in posts:
                link = p['link']
                if link not in self.seen_posts:
                    full_text = f"{p['title']} {p.get('desc', '')}"
                    
                    # Pre-filter obvious ads (saves API calls)
                    is_obvious_ad = any(m in full_text for m in AD_MARKERS)
                    
                    if is_obvious_ad:
                        self.seen_posts[link] = {
                            "title": p['title'],
                            "keyword": k,
                            "date": str(datetime.now()),
                            "sentiment": "[AD_FILTERED]"
                        }
                        pre_filtered_ads += 1
                    else:
                        posts_to_analyze.append({
                            'link': link,
                            'title': p['title'],
                            'text': full_text,
                            'keyword': k,
                            'id': link  # Use link as unique ID
                        })
        
        if pre_filtered_ads > 0:
            logger.info(f"   🚫 Pre-filtered {pre_filtered_ads} obvious ads")
        
        if not posts_to_analyze:
            self._save_seen()
            return "No new posts to analyze."
        
        logger.info(f"   📋 {len(posts_to_analyze)} new posts collected for analysis")
        
        # Phase 2: Batch AI Analysis
        all_results = {}
        
        # Process in batches of BATCH_SIZE
        for i in range(0, len(posts_to_analyze), BATCH_SIZE):
            batch = posts_to_analyze[i:i + BATCH_SIZE]
            batch_results = self.analyze_sentiment_batch(batch)
            all_results.update(batch_results)
        
        # Phase 3: Process results and send alerts
        for post in posts_to_analyze:
            link = post['link']
            sentiment_tag = all_results.get(link, "[UNKNOWN]")
            
            # Record as seen
            self.seen_posts[link] = {
                "title": post['title'],
                "keyword": post['keyword'],
                "date": str(datetime.now()),
                "sentiment": sentiment_tag
            }
            
            # Filter: Ignore Ads/Spam
            if "AD" in sentiment_tag or "SPAM" in sentiment_tag:
                continue
            
            # It's valuable! Alert!
            self.alert_system.bot.send_message(
                f"🔔 [Social Alert] {sentiment_tag}\n"
                f"키워드: {post['keyword']}\n"
                f"제목: {post['title']}\n"
                f"링크: {link}"
            )
            new_findings += 1
        
        self._save_seen()
        
        # Calculate API savings
        individual_calls = len(posts_to_analyze)
        batch_calls = (len(posts_to_analyze) + BATCH_SIZE - 1) // BATCH_SIZE
        savings_pct = round((1 - batch_calls / max(individual_calls, 1)) * 100)
        
        logger.info(f"   💰 API Savings: {batch_calls} calls instead of {individual_calls} ({savings_pct}% reduced)")
        
        if new_findings > 0:
            return f"Found {new_findings} relevant insights (batch analyzed, filtered ads)."
        else:
            return "No new relevant insights."

if __name__ == "__main__":
    monitor = SocialMonitor()
    print(monitor.run_cycle())
```
