from google import genai
import os
import glob
import logging
from PIL import Image
from utils import ConfigManager

import logging

# Configure logging
logger = logging.getLogger("VisionAnalyst")

class VisionAnalyst:
    """
    👁️ The 'Eyes' of the Marketing OS.
    Uses Gemini 3 Flash (Multimodal) to analyze images.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.api_key = self.config.get_api_key()

        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
            # Try requested model, fallback to gemini-3-flash-preview if fails
            try:
                self.model_name = self.config.get_model_name("flash")
            except Exception:
                logger.warning(f"Model config failed, falling back to gemini-3-flash-preview")
                self.model_name = 'gemini-3-flash-preview'
        else:
            logger.error("VisionAnalyst: No API Key found.")
            self.client = None
            self.model_name = None

    def analyze_visual_trend(self, image_paths):
        """
        Phase 1: Analyze a batch of images (e.g. from Instagram/Blog) to find visual trends.
        """
        if not self.client or not image_paths:
            return None

        logger.info(f"👁️ analyzing {len(image_paths)} images for Visual Trends...")

        # Load Images
        images = []
        valid_paths = []
        for p in image_paths:
            try:
                if os.path.exists(p):
                    img = Image.open(p)
                    images.append(img)
                    valid_paths.append(p)
            except Exception as e:
                logger.warning(f"Failed to load image {p}: {e}")

        if not images:
            return "No valid images to analyze."

        prompt = """
        You are a 'Visual Trend Analyst' for a Plastic Surgery/Dermatology Marketing Team.
        These images are the current top-performing posts for our target keywords.

        1. **Identify Common Patterns**: What is the recurring visual theme? (e.g. Mirror selfies, Food close-ups, Text-heavy banners, Before/After)
        2. **Atmosphere**: What is the color palette and vibe? (e.g. Minimalist white, Vivid pink, Dark & Moody)
        3. **Actionable Advice**: How should we take our next photo to fit this trend? Be specific about angle and lighting.

        Output in Korean.
        Structure:
        **[비주얼 패턴]**: ...
        **[분위기(Vibe)]**: ...
        **[촬영 가이드]**: ...
        """

        try:
            # Multimodal request: Text Prompt + Images
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt] + images
            )
            return response.text
        except Exception as e:
            logger.error(f"Vision Analysis Failed: {e}")
            return f"Error analyzing images: {e}"

    def audit_banner_quality(self, image_path):
        """
        Phase 1.5: Analyze Competitor Banners or Our Own assets.
        """
        if not self.client:
            return None

        try:
            img = Image.open(image_path)
            prompt = """
            Analyze this promotional banner/image.
            1. **Key Message**: What is the main text or offer?
            2. **Design Quality**: Is it professional? Rate 1-10.
            3. **Psychological Trigger**: What emotion does it try to evoke? (Urgency, Trust, Envy?)

            Output in Korean.
            """
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[prompt, img]
            )
            return response.text
        except Exception as e:
            logger.error(f"Banner Audit Failed: {e}")
            return str(e)

if __name__ == "__main__":
    # Test
    analyst = VisionAnalyst()
    print("Vision Analyst Online. Ready for Gemini 3 Flash input.")
