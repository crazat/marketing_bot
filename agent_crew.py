from utils import ConfigManager, logger
from google import genai
import json
import os
import glob
from datetime import datetime
import sys

if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

class BaseAgent:
    def __init__(self, role_name):
        self.config = ConfigManager()
        self.role_name = role_name
        self.api_key = self.config.get_api_key()
        
        if self.api_key:
            # New SDK Initialization
            self.client = genai.Client(api_key=self.api_key)
            # We don't instantiate a persistent model object anymore, we pass model name to the call
            self.model_name = self.config.get_model_name("pro") 
        else:
            self.client = None
            logger.error(f"[{role_name}] API Key missing.")

    def generate(self, prompt: str, max_retries: int = 3) -> str:
        """Generate content with retry logic for transient failures."""
        if not self.client: 
            return "Error: AI not configured."
        
        delay = 1.0
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt
                )
                # Track API usage
                try:
                    from api_tracker import get_tracker
                    tokens = len(prompt) // 4 + len(response.text) // 4  # Rough estimate
                    get_tracker().log_call('gemini', f'{self.role_name}/generate', tokens=tokens, success=True)
                except Exception:
                    pass
                return response.text.strip()
            except Exception as e:
                error_str = str(e).lower()
                # Track failed call
                try:
                    from api_tracker import get_tracker
                    get_tracker().log_call('gemini', f'{self.role_name}/generate', success=False, error=str(e)[:100])
                except Exception:
                    pass
                # Retry on rate limit or transient errors
                if any(x in error_str for x in ['quota', 'rate', '429', 'timeout', 'unavailable']):
                    if attempt < max_retries - 1:
                        logger.warning(f"[{self.role_name}] Transient error (retry {attempt+1}/{max_retries}): {e}")
                        import time
                        time.sleep(delay)
                        delay *= 2
                        continue
                # Non-retryable error
                logger.error(f"[{self.role_name}] Generation Error: {e}")
                return f"Error: {e}"
        return "Error: Max retries exceeded"

class ResearchAgent(BaseAgent):
    def __init__(self):
        super().__init__("Researcher")
    
    def gather_intel(self, topic):
        logger.info(f"🕵️ Researcher looking up: {topic}")
        # In a real scenario, this would trigger web search tools (SerpApi etc).
        # For Phase 3 MVP, we simulate deep context gathering from internal DB + Knowledge Base.
        
        context_data = ""
        # 1. Internal DB (Sentiments) - Real Data Connection
        try:
            import sqlite3
            db_path = os.path.join(self.config.root_dir, 'db', 'marketing_data.db')
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                # Fetch recent negative sentiments from competitors to exploit
                cursor.execute("SELECT content, sentiment FROM competitor_reviews WHERE sentiment='negative' ORDER BY id DESC LIMIT 5")
                rows = cursor.fetchall()
                if rows:
                    complaints = [r[0][:50]+"..." for r in rows]
                    context_data += f"[Real Market Intel] Recent competitor complaints to avoid/exploit: {'; '.join(complaints)}\n"
                else:
                    context_data += "[Real Market Intel] No specific competitor complaints found recently.\n"
        except Exception as e:
            logger.warning(f"Failed to fetch DB context: {e}")
            context_data += "[Internal Data] (DB Connection Failed)\n"
        
        # 2. Knowledge Base (Theory)
        # We assume the agent 'knows' medical theory or we inject some rules.
        
        prompt = f"""
        You are a Medical Research Assistant.
        Topic: {topic}
        
        Provide a structured research brief for a Blog Writer.
        1. **Medical Fact**: What is the physiological cause of {topic}? (Briefly)
        2. **Patient Pain Points**: What are they most worried about?
        3. **Key Stats/Trends**: Are there seasonal trends for this in Korea?
        
        Output as bullet points.
        """
        return self.generate(prompt)

class WriterAgent(BaseAgent):
    def __init__(self):
        super().__init__("Writer")
        
    def write_draft(self, topic, research_summary, mode="General"):
        logger.info(f"✍️ Writer drafting: {topic}")
        
        prompt = f"""
        You are a Professional Medical Blog Writer (Persona: Dr. Han from Kyurim Cheongju).
        Topic: {topic}
        Mode: {mode}
        
        [Research Brief]:
        {research_summary}
        
        Write a high-quality blog post draft.
        - Tone: Empathetic, Professional, Local (Cheongju).
        - Structure: Title -> Intro -> Cause -> Solution -> CTA.
        - Use emojis for readability.
        """
        return self.generate(prompt)

from seo_scorer import SeoScorer

class EditorAgent(BaseAgent):
    def __init__(self):
        super().__init__("Editor")
        self.scorer = SeoScorer()
        
    def review_and_refine(self, draft, topic):
        logger.info(f"⚖️ Editor reviewing draft...")
        
        # 1. SEO Scoring
        # Assume topic is the main keyword for simplicity, or extract it.
        # For now, we take the first 2 words of topic as keyword if long
        main_keyword = topic.split()[0] if topic else "한의원"
        
        analysis = self.scorer.analyze(draft, main_keyword)
        score = analysis['score']
        feedback = "\n".join(analysis['feedback'])
        
        logger.info(f"📊 Initial SEO Score: {score}/100")
        
        # 2. Refine Prompt based on Score
        prompt = f"""
        You are a Senior Editor (and SEO Expert).
        
        [Original Draft]:
        {draft[:4000]}
        
        [SEO Analysis Report]:
        Score: {score}/100
        Feedback:
        {feedback}
        
        **Your Mission**:
        1. Fix the issues mentioned in Feedback (Especially Keyword Density and Length).
        2. Ensure the tone is natural and compliant (Medical Law).
        3. Make sure the score would be 90+ after your edit.
        
        Output the **Final Polished Version** only.
        """
        
        refined_content = self.generate(prompt)
        
        # Double Check (Optional: Score again)
        # final_analysis = self.scorer.analyze(refined_content, main_keyword)
        # logger.info(f"📊 Final SEO Score: {final_analysis['score']}/100")
        
        # Append report for user visibility
        final_output = f"""
<!-- SEO Report -->
<!-- Initial Score: {score} -->
<!-- Feedback: {feedback} -->

{refined_content}
"""
        return final_output.strip()

class AgentCrew:
    def __init__(self):
        self.researcher = ResearchAgent()
        self.writer = WriterAgent()
        self.editor = EditorAgent()
        
    def produce_content(self, topic, mode="General"):
        logger.info(f"🚀 Crew starting production on: {topic}")
        
        # 1. Research
        intel = self.researcher.gather_intel(topic)
        
        # 2. Write
        draft = self.writer.write_draft(topic, intel, mode)
        
        # 3. Edit
        final_post = self.editor.review_and_refine(draft, topic)
        
        return {
            "topic": topic,
            "research": intel,
            "draft": draft,
            "final": final_post
        }

# Maintain backward compatibility wrapper
class LLMContentGenerator:
    def __init__(self):
        self.crew = AgentCrew()
        
    def generate_premium_blog(self, topic, mode="General", weather=""):
        # Wrapper to use the new Crew system but return string as expected by dashboard
        result = self.crew.produce_content(topic, mode)
        return f"""
# 🕵️ Research Note
{result['research']}

---

# ✍️ Initial Draft
{result['draft'][:200]}... (omitted)

---

# ✨ Final Polished Post (Editor Verified)
{result['final']}
        """

if __name__ == "__main__":
    crew = AgentCrew()
    res = crew.produce_content("다이어트 요요", "Diet Mode")
    print(res['final'])
