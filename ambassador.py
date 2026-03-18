
import random
import requests
from bs4 import BeautifulSoup
from agent_crew import AgentCrew
from utils import logger, ConfigManager

class TheAmbassador:
    """
    Component for Surgical Influencer Scouting.
    Uses 'Google Search Backdoor' to find real influencers without Instagram Login Wall.
    """
    def __init__(self):
        self.crew = AgentCrew()

    def _google_search_influencers(self, location="청주", niche="협찬"):
        """
        Searches Google for Instagram profiles using Selenium (Headless Chrome) to bypass simple bot blocks.
        """
        from retry_helper import SafeSeleniumDriver
        from selenium.webdriver.common.by import By
        import time
        
        results = []
        
        # [Audit Fix] Use SafeSeleniumDriver to prevent Zombie Processes
        with SafeSeleniumDriver(headless=True) as driver:
            try:
                query = f"site:instagram.com \"{location}\" \"{niche}\""
                url = f"https://www.google.com/search?q={query}"
                
                driver.get(url)
                time.sleep(2) # Wait for load
                
                # Google Result Selectors (can vary, so we try generic structure)
                # Standard: .g container -> h3 for title, a for link, .VwiC3b for snippet
                elements = driver.find_elements(By.CSS_SELECTOR, ".tF2Cxc") # Common class for result container
                
                if not elements:
                    # Fallback selector if class name changed
                    elements = driver.find_elements(By.CSS_SELECTOR, ".g")

                for g in elements:
                    try:
                        title_el = g.find_element(By.TAG_NAME, "h3")
                        link_el = g.find_element(By.TAG_NAME, "a")
                        
                        try:
                            snippet_el = g.find_element(By.CSS_SELECTOR, ".VwiC3b") # Snippet class
                            snippet = snippet_el.text
                        except:
                            snippet = "No snippet"
                            
                        title = title_el.text
                        link = link_el.get_attribute("href")
                        
                        if "instagram.com" in link:
                            parts = link.split("instagram.com/")
                            if len(parts) > 1:
                                raw_handle = parts[1].split("/")[0]
                                handle = "@" + raw_handle.strip()
                                
                                # Valid Check
                                if "p/" in handle or "reel" in handle or "explore" in handle: # Skip post links
                                    continue
                                    
                                results.append({
                                    "handle": handle,
                                    "link": link,
                                    "snippet": snippet,
                                    "title": title
                                })
                    except Exception:
                       continue
                       
            except Exception as e:
                logger.error(f"Selenium Google Search Failed: {e}")
            
        return results[:5]

    def scout_and_vet(self, location_filter="청주"):
        """
        1. Search Real Profiles via Google (Selenium).
        2. Analyze Snippet/Title for Vetting.
        3. Draft DM.
        
        ⚠️ LIMITATION (Google Bypass Mode):
        - Cannot retrieve follower count (requires Instagram API/login)
        - Cannot retrieve engagement rate (likes/comments)
        - Cannot analyze recent posts
        - Data is from Google index (may be outdated)
        
        All returned candidates have verification_status='PENDING' and require
        manual verification before outreach.
        """
        logger.info(f"🤝 Ambassador: Searching Google for real '{location_filter}' influencers...")
        logger.warning("⚠️ LIMITED MODE: Follower/engagement data unavailable (requires Instagram API)")
        
        # 1. Real Search
        candidates = self._google_search_influencers(location_filter, "협찬")
        
        # REMOVED: Mock Data Fallback. 
        # If no results, we return empty list to be honest about failure.
        if not candidates:
            return [] # Returns empty, prompting 'Not Found' message in UI

        vetted_list = []
        
        for cand in candidates:
            # 2. Vetting
            cand_snippet = cand.get('snippet', '') + cand.get('title', '')
            
            if "카지노" in cand_snippet or "바카라" in cand_snippet:
                continue

            # 3. Personalized Drafting
            prompt = f"""
            You are the Director of Kyurim Clinic Cheongju.
            Write a Hyper-Personalized DM to this REAL influencer found on Google.
            
            [Target Info]
            Handle: {cand['handle']}
            Profile Snippet: "{cand_snippet}"
            
            [Context]
            We found them because they are active in '{location_filter}'.
            
            [Instruction]
            - Mention something specific from their snippet.
            - Be polite.
            """
            try:
                dm = self.crew.writer.generate(prompt)
                cand['draft_dm'] = dm
                cand['recent_content'] = cand_snippet[:50] + "..." if len(cand_snippet) > 50 else cand_snippet
                
                # ⚠️ LIMITED MODE: These fields cannot be populated via Google bypass
                # Marked clearly to indicate manual verification is required
                cand['followers'] = "[VERIFICATION_REQUIRED]"
                cand['avg_likes'] = "[VERIFICATION_REQUIRED]"
                cand['avg_comments'] = "[VERIFICATION_REQUIRED]"
                cand['verification_status'] = "PENDING"  # New workflow field
                cand['data_source'] = "google_search_limited"  # Indicate data quality
                
                vetted_list.append(cand)
            except Exception as e:
                logger.error(f"Draft generation error: {e}")
                
        return vetted_list

if __name__ == "__main__":
    amb = TheAmbassador()
    results = amb.scout_and_vet("청주")
    for r in results:
        print(f"Handle: {r['handle']}\nSnippet: {r['snippet']}\nDM: {r['draft_dm']}\n---")
