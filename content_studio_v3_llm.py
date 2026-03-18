import os
import json
import sys
import glob
from datetime import datetime
import warnings
import warnings
warnings.filterwarnings("ignore")
# import google.generativeai as genai removed

# Windows console encoding fix
if sys.platform.startswith('win'):
    sys.stdout.reconfigure(encoding='utf-8')

from agent_crew import AgentCrew
from utils import logger

class LLMContentGenerator:
    """
    Phase 3: Multi-Agent Adapter.
    This class now delegates work to the AgentCrew (Research -> Write -> Edit).
    """
    def __init__(self):
        self.crew = AgentCrew()
        # self.simple_model removed (using AgentCrew directly) 

    def generate_premium_blog(self, topic, mode="미용/다이어트 모드", weather="맑음"):
        logger.info(f"Requesting Premium Blog via Crew: {topic}")
        result = self.crew.produce_content(topic, mode)
        
        # Format for display
        return f"""
# 🕵️ Research Summary
{result['research']}

<!-- draft omitted -->

# ✨ Final Polished Post (Editor Verified)
{result['final']}
"""

    def generate_ad_copy(self, product, discount=""):
        # Simple task, direct generation via writer agent
        prompt = f"Write 5 ad copies for {product} with offer {discount}."
        return self.crew.writer.generate(prompt)

    # Legacy methods can communicate via simple prompts to the Writer Agent
    def generate_calendar(self, month=None):
        prompt = f"Create a content calendar for {month or 'this month'}."
        return self.crew.writer.generate(prompt)
        
    # Support for random "simple" methods if needed
    def __getattr__(self, name):
        # Fallback for undefined methods to just ask the writer agent generic questions?
        # Better to be explicit or fail. 
        # But to be safe for legacy calls in dashboard:
        def method(*args, **kwargs):
            return f"Feature {name} is being migrated to Multi-Agent system."
        return method

if __name__ == "__main__":
    generator = LLMContentGenerator()
    
    # Test New Features
    print("\n📅 [Test Planner]:")
    # print(generator.generate_calendar("January"))
    
    print("\n👑 [Test Premium Blog]:")
    # print(generator.generate_premium_blog("청주 여드름 흉터", mode="미용/다이어트 모드"))
