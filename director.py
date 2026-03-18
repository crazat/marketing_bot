
import logging
from agent_crew import AgentCrew
from utils import logger

class TheDirector:
    """
    Component for generating Short-form Video Scripts (Reels/Shorts).
    "Compact, Visual, Trendy"
    """
    def __init__(self):
        self.crew = AgentCrew()

    def action(self, topic):
        """
        Generates a 1-minute video script.
        """
        logger.info(f"🎥 The Director: Action! Topic: {topic}")
        
        prompt = f"""
        Create a viral Short-form Video Script (Reels/Shorts/TikTok) for a Korean Medicine Clinic.
        Topic: {topic}
        
        Format:
        # 🎬 Title: [Catchy Hook Title]
        ## 🎵 BGM: [Trending Song Recommendation]
        
        | Time | Visual (Camera/Action) | Audio (Script/Subtitle) |
        |---|---|---|
        | 0-3s | [Hook Visual] | [Hook Line] |
        | 3-15s | [Main Content] | [Explanation] |
        | ... | ... | ... |
        | End | [CTA] | [Call to Action] |
        
        Keep it under 60 seconds. Make it visual-first.
        """
        
        return self.crew.writer.generate(prompt)

if __name__ == "__main__":
    d = TheDirector()
    print(d.action("청주 교통사고 입원"))
