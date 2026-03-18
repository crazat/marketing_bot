"""
TikTok Hybrid Monitor
하이브리드 시스템: Research API 우선, Creative Center 폴백

데이터 소스 구분 (source 필드):
- tiktok_api: Research API에서 수집한 비디오
- tiktok_cc_hashtag: Creative Center 해시태그
- tiktok_cc_music: Creative Center 음악
- tiktok_cc_creator: Creative Center 크리에이터
- tiktok_comment: 댓글 리드
"""
import sys
import os
import time
import random
import json
from datetime import datetime

# Windows encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from db.database import DatabaseManager

import argparse
import logging

logger = logging.getLogger("TikTokMonitor")


class TikTokHybridMonitor:
    """
    TikTok Hybrid Monitor

    동작 방식:
    1. Research API 설정 확인 → API 모드 실행
    2. API 미설정 또는 quota 초과 → Creative Center 폴백
    3. LeadClassifier로 댓글 리드 분석 (optional)
    """

    def __init__(self, headless=True, keywords=None):
        self.db = DatabaseManager()
        self.headless = headless
        self.keywords = keywords or []
        self.mode = None  # 'api', 'creative_center', 'hybrid'

        # Load keywords if not provided
        if not self.keywords:
            self.keywords = self._load_master_keywords()

        # Check API availability
        self._api_client = None
        self._cc_scraper = None

    def _load_master_keywords(self) -> list:
        """Load keywords from master config."""
        try:
            kw_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                'config', 'keywords_master.json'
            )
            with open(kw_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            keywords = []
            for cat, kw_list in data.items():
                keywords.extend(kw_list)

            print(f"[{datetime.now()}] Loaded {len(keywords)} keywords from master config")
            return keywords

        except Exception as e:
            logger.warning(f"Failed to load master keywords: {e}")
            return ["청주 다이어트", "청주 한의원"]  # Fallback defaults

    def _init_api_client(self):
        """Initialize TikTok API client (lazy loading)."""
        if self._api_client is None:
            try:
                from scrapers.tiktok_api_client import TikTokResearchAPIClient
                self._api_client = TikTokResearchAPIClient()
            except ImportError:
                logger.warning("TikTok API client module not found")
                return None
        return self._api_client

    def _init_cc_scraper(self):
        """Initialize Creative Center scraper (lazy loading)."""
        if self._cc_scraper is None:
            try:
                from scrapers.tiktok_creative_center import TikTokCreativeCenterScraper
                self._cc_scraper = TikTokCreativeCenterScraper(headless=self.headless)
            except ImportError:
                logger.warning("Creative Center scraper module not found")
                return None
        return self._cc_scraper

    def _check_api_available(self) -> bool:
        """Check if TikTok Research API is available and configured."""
        try:
            client = self._init_api_client()
            if client and client.is_configured():
                if not client.circuit_breaker.is_open():
                    return True
                else:
                    print(f"   [API] Circuit breaker OPEN - quota exceeded")
        except Exception as e:
            logger.debug(f"API check failed: {e}")
        return False

    def _determine_mode(self) -> str:
        """Determine which mode to run in."""
        api_available = self._check_api_available()

        if api_available:
            # API available - use hybrid (API + CC for trends)
            return "hybrid"
        else:
            # API not available - Creative Center only
            return "creative_center"

    def run(self):
        """Main entry point - runs hybrid scan."""
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] TikTok Hybrid Monitor Starting")
        print(f"   Headless: {self.headless}")
        print(f"   Keywords: {len(self.keywords)}")
        print(f"{'='*60}\n")

        # Determine mode
        self.mode = self._determine_mode()
        print(f"   Mode: {self.mode.upper()}")

        results = {
            'mode': self.mode,
            'api_videos': 0,
            'api_comments': 0,
            'cc_hashtags': 0,
            'cc_music': 0,
            'cc_creators': 0,
            'total': 0,
            'errors': []
        }

        try:
            if self.mode == "hybrid":
                results = self._run_hybrid_mode(results)
            elif self.mode == "creative_center":
                results = self._run_creative_center_mode(results)
            else:
                results = self._run_creative_center_mode(results)

        except Exception as e:
            results['errors'].append(f"Monitor error: {e}")
            logger.error(f"Monitor failed: {e}")

        # Summary
        self._print_summary(results)
        return results

    def _run_hybrid_mode(self, results: dict) -> dict:
        """
        Hybrid mode: API for keyword search + Creative Center for trends.
        """
        print(f"\n[HYBRID MODE] Running API + Creative Center")

        # 1. API: Keyword search
        try:
            client = self._init_api_client()
            if client:
                print(f"\n--- Phase 1: API Video Search ---")
                # Use subset of keywords for API (rate limiting)
                api_keywords = self.keywords[:10]  # Limit to 10 keywords

                for kw in api_keywords:
                    try:
                        videos = client.search_videos(kw, max_count=10)
                        results['api_videos'] += len(videos)

                        # Get comments for top videos
                        for video in videos[:3]:
                            video_id = video.get("id")
                            if video_id:
                                comments = client.get_video_comments(video_id, max_count=20)
                                results['api_comments'] += len(comments)

                                # Filter and save lead comments
                                video_url = f"https://www.tiktok.com/video/{video_id}"
                                self._process_comments_for_leads(comments, video_url, kw)

                        time.sleep(random.uniform(1, 2))

                    except Exception as e:
                        results['errors'].append(f"API search '{kw}': {e}")
                        continue

        except Exception as e:
            results['errors'].append(f"API mode failed: {e}")

        # 2. Creative Center: Trend data
        print(f"\n--- Phase 2: Creative Center Trends ---")
        results = self._run_creative_center_mode(results, hashtags_only=False)

        results['total'] = (
            results['api_videos'] +
            results['api_comments'] +
            results['cc_hashtags'] +
            results['cc_music'] +
            results['cc_creators']
        )

        return results

    def _run_creative_center_mode(self, results: dict, hashtags_only: bool = False) -> dict:
        """
        Creative Center mode: Scrape trending data.
        """
        print(f"\n[CREATIVE CENTER MODE] Scraping trends...")

        try:
            scraper = self._init_cc_scraper()
            if not scraper:
                results['errors'].append("Creative Center scraper not available")
                return results

            # Hashtags (priority)
            try:
                hashtags = scraper.scrape_hashtags(limit=50)
                results['cc_hashtags'] = len(hashtags)
            except Exception as e:
                results['errors'].append(f"CC hashtags: {e}")

            if not hashtags_only:
                time.sleep(random.uniform(2, 4))

                # Music
                try:
                    music = scraper.scrape_music(limit=30)
                    results['cc_music'] = len(music)
                except Exception as e:
                    results['errors'].append(f"CC music: {e}")

                time.sleep(random.uniform(2, 4))

                # Creators
                try:
                    creators = scraper.scrape_creators(limit=20)
                    results['cc_creators'] = len(creators)
                except Exception as e:
                    results['errors'].append(f"CC creators: {e}")

        except Exception as e:
            results['errors'].append(f"Creative Center mode failed: {e}")

        if self.mode == "creative_center":
            results['total'] = (
                results['cc_hashtags'] +
                results['cc_music'] +
                results['cc_creators']
            )

        return results

    def _process_comments_for_leads(self, comments: list, video_url: str, keyword: str):
        """
        Process comments and save potential leads.
        Uses LeadClassifier if available.
        """
        lead_keywords = ["?", "어디", "추천", "알려", "찾", "문의", "가격", "비용", "예약", "연락처"]

        for comment in comments:
            text = comment.get("text", "")

            # Basic lead detection
            is_potential_lead = any(lk in text.lower() for lk in lead_keywords)

            if is_potential_lead:
                # Try to use LeadClassifier for better classification
                memo = ""
                try:
                    from lead_classifier import LeadClassifier
                    classifier = LeadClassifier()
                    classification = classifier.classify(text)
                    memo = f"[{classification.get('category', 'Unknown')}] {classification.get('confidence', 0):.0%}"
                except Exception:
                    memo = "[Potential Lead]"

                # Save to DB
                self.db.insert_mention({
                    "target_name": "TikTok",
                    "keyword": keyword,
                    "source": "tiktok_comment",
                    "title": f"Comment Lead: {text[:40]}...",
                    "content": text,
                    "url": video_url,
                    "image_url": "",
                    "date_posted": datetime.now().strftime("%Y-%m-%d"),
                    "memo": memo
                })

    def _print_summary(self, results: dict):
        """Print run summary."""
        print(f"\n{'='*60}")
        print(f"[{datetime.now()}] TikTok Monitor Complete")
        print(f"{'='*60}")
        print(f"   Mode: {results['mode'].upper()}")
        print(f"   ---")

        if results['mode'] == 'hybrid':
            print(f"   API Videos: {results['api_videos']}")
            print(f"   API Comments: {results['api_comments']}")

        print(f"   CC Hashtags: {results['cc_hashtags']}")
        print(f"   CC Music: {results['cc_music']}")
        print(f"   CC Creators: {results['cc_creators']}")
        print(f"   ---")
        print(f"   Total Items: {results['total']}")

        if results['errors']:
            print(f"   Errors: {len(results['errors'])}")
            for err in results['errors'][:3]:
                print(f"      - {err[:50]}...")

        print(f"{'='*60}\n")


# Legacy compatibility wrapper
class TikTokMonitor(TikTokHybridMonitor):
    """
    Legacy wrapper for backward compatibility.
    Maps old interface to new hybrid monitor.
    """

    def __init__(self):
        # Parse arguments like original
        parser = argparse.ArgumentParser()
        parser.add_argument("keywords", nargs='*', help="Keywords")
        parser.add_argument("--headed", action="store_true", help="Run with visible browser")

        full_arg_str = " ".join(sys.argv[1:])
        headed = "--headed" in full_arg_str

        if headed:
            full_arg_str = full_arg_str.replace("--headed", "").strip()

        if full_arg_str:
            keywords = [k.strip() for k in full_arg_str.split(',')]
        else:
            keywords = None

        super().__init__(headless=not headed, keywords=keywords)


if __name__ == "__main__":
    # Check for new-style arguments
    if "--help" in sys.argv or "-h" in sys.argv:
        print("""
TikTok Hybrid Monitor
=====================

Usage:
    python scraper_tiktok_monitor.py [keywords] [--headed]

Options:
    keywords    Comma-separated keywords (optional, loads from config)
    --headed    Run with visible browser window

Modes:
    - HYBRID: API (if configured) + Creative Center
    - CREATIVE_CENTER: Trend scraping only (fallback)

Examples:
    python scraper_tiktok_monitor.py
    python scraper_tiktok_monitor.py "청주 다이어트,청주 한의원" --headed
        """)
        sys.exit(0)

    # Run monitor
    monitor = TikTokMonitor()
    monitor.run()
