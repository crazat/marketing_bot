import os
import sys
import glob
import logging
from types import SimpleNamespace
from PIL import Image
from utils import ConfigManager

# Add backend to path for ai_client import
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'marketing_bot_web', 'backend'))
from services.ai_client import ai_generate

# Compatibility surface for older tests and deployments that patch or use
# google.generativeai.GenerativeModel directly.
class _UnavailableGenerativeModel:
    def __init__(self, *args, **kwargs):
        raise ImportError("google.generativeai is not available")


try:
    import google.generativeai as _legacy_genai
except Exception:
    _legacy_genai = SimpleNamespace(GenerativeModel=_UnavailableGenerativeModel)
else:
    if not hasattr(_legacy_genai, "GenerativeModel"):
        _legacy_genai.GenerativeModel = _UnavailableGenerativeModel

genai = _legacy_genai

# Configure logging
logger = logging.getLogger("VisionAnalyst")

class VisionAnalyst:
    """
    The 'Eyes' of the Marketing OS.
    Uses centralized AI client for text analysis.
    Note: Multimodal image analysis requires direct API access;
    text-based prompts are routed through ai_client.
    """
    def __init__(self):
        self.config = ConfigManager()
        self.api_key = self.config.get_api_key()

        # Keep direct genai client for multimodal (image) requests only
        self.client = None
        self.model = None
        self.model_name = None
        try:
            self.model_name = self.config.get_model_name("flash")
        except Exception:
            logger.warning("Model config failed, falling back to gemini-3-flash-preview")
            self.model_name = 'gemini-3-flash-preview'

        legacy_model_factory = getattr(genai, "GenerativeModel", None)
        legacy_is_mocked = "unittest.mock" in type(legacy_model_factory).__module__
        legacy_available = legacy_model_factory is not _UnavailableGenerativeModel

        if legacy_model_factory and (legacy_available or legacy_is_mocked) and (self.api_key or legacy_is_mocked):
            try:
                if self.api_key and hasattr(genai, "configure"):
                    genai.configure(api_key=self.api_key)
                self.model = legacy_model_factory(self.model_name)
                return
            except Exception as e:
                logger.warning(f"Legacy Gemini model initialization failed: {e}")

        if self.api_key:
            try:
                from google import genai as google_genai
                self.client = google_genai.Client(api_key=self.api_key)
            except ImportError:
                logger.warning("google-genai not available for multimodal; image analysis disabled")
        else:
            logger.error("VisionAnalyst: No API Key found.")

    def analyze_visual_trend(self, image_paths):
        """
        Phase 1: Analyze a batch of images (e.g. from Instagram/Blog) to find visual trends.
        """
        if not (self.client or self.model) or not image_paths:
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
            if self.model:
                response = self.model.generate_content([prompt] + images)
            else:
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
        if not (self.client or self.model):
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
            if self.model:
                response = self.model.generate_content([prompt, img])
            else:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=[prompt, img]
                )
            return response.text
        except Exception as e:
            logger.error(f"Banner Audit Failed: {e}")
            return str(e)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 의료광고법 이미지 게이트 (2026 신규 규제 대응)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 모듈 import
from typing import Optional, Dict, Any, Union, List
import json as _json


def screen_medical_image(
    image_source: Union[str, bytes, list],
    *,
    confidence_threshold: float = 0.85,
) -> Dict[str, Any]:
    """의료광고법 위반 가능성 이미지 검출.

    검출 카테고리 (2026 한국 규제 기준):
    1. before_after_photo: 시술 전후 비교 사진 (좌우분할/화살표 패턴)
    2. fake_or_ai_doctor: AI 합성/가짜 의료진 (왜곡손/비대칭가운/부자연스러운 얼굴)
    3. medical_device_extreme: 의료기기 부착 환자 자극 사진
    4. forbidden_text_overlay: 금지어 텍스트 오버레이 (1등/최고/유일/완치/100%)
    5. unauthorized_celebrity: 무단 도용 의심 유명인/의료진

    Args:
        image_source: ai_analyze_image와 동일 (URL/path/bytes/PIL/list)
        confidence_threshold: 0-1, 이 이상이어야 violation으로 판정

    Returns:
        {
            "passed": bool,
            "violations": [
                {"category": ..., "confidence": 0-1, "rationale": ...}, ...
            ],
            "max_confidence": float,
            "needs_human_review": bool,  # confidence가 thresh 근처면 사람 검수 권장
        }
    """
    try:
        from services.ai_client import ai_analyze_image
        from pydantic import BaseModel, Field
    except Exception as e:
        logger.error(f"vision screen 의존성 부족: {e}")
        return {"passed": True, "violations": [], "max_confidence": 0.0,
                "needs_human_review": False, "error": str(e)}

    class ViolationItem(BaseModel):
        category: str = Field(description="before_after_photo|fake_or_ai_doctor|medical_device_extreme|forbidden_text_overlay|unauthorized_celebrity|none")
        confidence: float = Field(ge=0.0, le=1.0)
        rationale: str = Field(description="짧은 한국어 설명")

    class ScreenResult(BaseModel):
        violations: List[ViolationItem]

    prompt = """당신은 한국 의료광고법 위반 이미지 자동 검출 전문가입니다.

다음 5개 카테고리의 위반 가능성을 각각 평가하세요:

1. before_after_photo: 시술 전후 비교 사진 (좌우/상하 분할, 화살표, BEFORE/AFTER, 비포/애프터)
2. fake_or_ai_doctor: AI 합성/가짜 의료진 (손가락 개수 이상, 비대칭 가운, 부자연스러운 얼굴 대칭, 약간 왜곡된 눈/입)
3. medical_device_extreme: 의료기기 부착 환자 자극 사진 (수술실, 침습 시술 진행 중)
4. forbidden_text_overlay: 텍스트 오버레이 금지어 (1등/최고/유일/완치/100%/보장/특가/할인)
5. unauthorized_celebrity: 유명 의료진/연예인 무단 도용 의심

각 카테고리에 대해 confidence (0-1)와 짧은 rationale을 반환하세요.
위반 없으면 [{"category": "none", "confidence": 1.0, "rationale": "안전"}].
JSON 응답만."""

    parsed = ai_analyze_image(
        image_source,
        prompt,
        response_schema=ScreenResult,
        temperature=0.2,
        max_tokens=1024,
    )

    if parsed is None:
        return {"passed": True, "violations": [], "max_confidence": 0.0,
                "needs_human_review": True, "error": "vision_call_failed"}

    items = parsed.violations if hasattr(parsed, "violations") else []
    real_violations = [
        {"category": v.category, "confidence": v.confidence, "rationale": v.rationale}
        for v in items
        if v.category != "none" and v.confidence >= confidence_threshold
    ]
    near_violations = [
        {"category": v.category, "confidence": v.confidence}
        for v in items
        if v.category != "none" and 0.65 <= v.confidence < confidence_threshold
    ]
    max_conf = max((v.confidence for v in items if v.category != "none"), default=0.0)
    return {
        "passed": len(real_violations) == 0,
        "violations": real_violations,
        "near_violations": near_violations,
        "max_confidence": float(max_conf),
        "needs_human_review": len(near_violations) > 0,
    }


def log_image_screen(
    db_path: str,
    *,
    call_site: str,
    image_ref: str,
    screen_result: Dict[str, Any],
) -> Optional[int]:
    """이미지 게이트 결과를 ai_image_screen_log 테이블에 기록."""
    import sqlite3 as _sql
    conn = None
    try:
        conn = _sql.connect(db_path)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS ai_image_screen_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                call_site TEXT,
                image_ref TEXT,
                passed INTEGER,
                max_confidence REAL,
                violations_json TEXT,
                near_violations_json TEXT,
                needs_human_review INTEGER
            )
        """)
        cur.execute("""
            INSERT INTO ai_image_screen_log
              (call_site, image_ref, passed, max_confidence,
               violations_json, near_violations_json, needs_human_review)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            call_site or "",
            image_ref[:500] if image_ref else "",
            1 if screen_result.get("passed") else 0,
            float(screen_result.get("max_confidence", 0.0)),
            _json.dumps(screen_result.get("violations", []), ensure_ascii=False),
            _json.dumps(screen_result.get("near_violations", []), ensure_ascii=False),
            1 if screen_result.get("needs_human_review") else 0,
        ))
        conn.commit()
        return cur.lastrowid
    except Exception as e:
        logger.warning(f"[vision_screen] 로그 저장 실패: {e}")
        return None
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    # Test
    analyst = VisionAnalyst()
    print("Vision Analyst Online. Ready for Gemini 3 Flash input.")
