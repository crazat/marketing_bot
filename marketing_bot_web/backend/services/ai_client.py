"""
AI Client - 중앙화된 LLM 클라이언트
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

모든 AI 호출은 이 모듈을 통해 이루어집니다.
모델 변경 시 이 파일만 수정하면 전체 시스템에 적용됩니다.

Providers (2026-04-24 이후, Qwen 무료 한도 초과로 전면 교체):
- 기본(분류/JSON):  gemini-2.5-flash-lite (GA)  — $0.10 / $0.40 per 1M tokens
- 한국어 댓글 생성: gemini-3.1-flash-lite-preview — $0.25 / $1.50 per 1M tokens
                   (Preview지만 2.5 Flash 대비 더 저렴·빠름·우수)

환경변수:
- GEMINI_API_KEY            (필수) — config/secrets.json 폴백
- GEMINI_CLASSIFY_MODEL     (선택) — 기본 ai_generate / ai_generate_json 모델
- GEMINI_KOREAN_MODEL       (선택) — ai_generate_korean 모델
"""

import os
import json
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

# ── Model Configuration ────────────────────────────────────────────────

# 기본: 분류/JSON/판단 — 저렴하고 빠른 GA 모델
_MODEL_CLASSIFY = os.getenv("GEMINI_CLASSIFY_MODEL", "gemini-2.5-flash-lite")

# 한국어 창작: 댓글/콘텐츠 — 세대 앞선 preview, 2.5 Flash보다 싸고 우수
_MODEL_KOREAN = os.getenv("GEMINI_KOREAN_MODEL", "gemini-3.1-flash-lite-preview")

_gemini_client = None  # google.genai.Client (지연 초기화)


# ── Client init ────────────────────────────────────────────────────────

def _get_gemini_client():
    """google-genai 클라이언트 싱글톤"""
    global _gemini_client
    if _gemini_client is not None:
        return _gemini_client

    api_key = os.getenv("GEMINI_API_KEY", "")

    # Fallback: config/secrets.json 직접 파싱
    if not api_key:
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.dirname(os.path.abspath(__file__)))))
            secrets_path = os.path.join(project_root, "config", "secrets.json")
            if os.path.exists(secrets_path):
                with open(secrets_path, "r", encoding="utf-8") as f:
                    secrets = json.load(f)
                api_key = secrets.get("GEMINI_API_KEY", "") or ""
        except Exception as e:
            logger.debug(f"secrets.json 폴백 실패: {e}")

    if not api_key:
        logger.error("GEMINI_API_KEY가 설정되지 않았습니다 (환경변수 또는 config/secrets.json)")
        return None

    try:
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
        return _gemini_client
    except Exception as e:
        logger.error(f"[Gemini] 클라이언트 초기화 실패: {e}")
        return None


# ── JSON helpers ───────────────────────────────────────────────────────

def _extract_json(text: str) -> str:
    """마크다운 코드블록에서 JSON 추출"""
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0]
    elif "```" in text:
        text = text.split("```")[1].split("```")[0]
    return text.strip()


def _repair_json(text: str) -> Optional[Dict]:
    """불완전한 JSON 복구 시도 — 마지막 유효한 } 또는 ] 찾기"""
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ('}', ']'):
            try:
                return json.loads(text[:i + 1])
            except json.JSONDecodeError:
                continue
    return None


def _normalize_model(model: Optional[str], default: str) -> str:
    """
    호출자 model 파라미터 정리.
    - None → default
    - 구 Qwen 모델명 ("qwen*") → default (안전 폴백)
    - 그 외 → 그대로 (Gemini 모델명 override)
    """
    if not model:
        return default
    if model.lower().startswith("qwen"):
        logger.warning(f"[AI] 레거시 모델명 '{model}' 요청 → 기본 '{default}'로 대체")
        return default
    return model


# ── Public API ─────────────────────────────────────────────────────────

def ai_generate(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> str:
    """
    AI 텍스트 생성 (gemini-2.5-flash-lite 기본)

    분류/판단/요약 등 범용 작업에 사용. 한국어 댓글·창작은 ai_generate_korean 권장.

    Args:
        prompt: 프롬프트
        temperature: 생성 온도 (0.0-1.0)
        max_tokens: 최대 출력 토큰
        system_prompt: 시스템 프롬프트 (선택)
        model: 모델명 override (None이면 기본값)

    Returns:
        생성된 텍스트 또는 에러 메시지 ("[AI] ..."로 시작)
    """
    client = _get_gemini_client()
    if client is None:
        return "[AI] API 클라이언트 초기화 실패"

    model_id = _normalize_model(model, _MODEL_CLASSIFY)

    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_prompt:
            config.system_instruction = system_prompt

        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config,
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.error(f"[AI:{model_id}] 생성 실패: {e}")
        return f"[AI] 생성 오류: {str(e)}"


def ai_generate_json(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    AI JSON 생성 (자동 파싱 + 복구)

    Gemini의 response_mime_type="application/json"으로 구조화 응답 강제.
    실패 시 마크다운 블록 추출 + 부분 복구 시도.

    Args:
        prompt: 프롬프트 (JSON 형식 응답 요청 포함)
        temperature: 생성 온도
        max_tokens: 최대 출력 토큰
        system_prompt: 시스템 프롬프트 (선택)
        model: 모델명 override

    Returns:
        파싱된 dict 또는 None
    """
    client = _get_gemini_client()
    if client is None:
        return None

    model_id = _normalize_model(model, _MODEL_CLASSIFY)

    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
            response_mime_type="application/json",
        )
        if system_prompt:
            config.system_instruction = system_prompt

        response = client.models.generate_content(
            model=model_id,
            contents=prompt,
            config=config,
        )
        text = (response.text or "").strip()
        if not text:
            logger.error(f"[AI:{model_id}] JSON 응답 비어있음")
            return None

        # response_mime_type이 JSON을 보장하지만, 마크다운 코드블록이 섞여 들어오는
        # 케이스를 위해 방어적 추출도 수행
        text = _extract_json(text)

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            repaired = _repair_json(text)
            if repaired:
                logger.warning(f"[AI:{model_id}] JSON 복구 성공")
                return repaired
            logger.error(f"[AI:{model_id}] JSON 파싱 실패: {text[:200]}...")
            return None

    except Exception as e:
        logger.error(f"[AI:{model_id}] JSON 생성 실패: {e}")
        return None


def ai_generate_korean(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
) -> str:
    """
    한국어 자연어 생성 전용 (gemini-3.1-flash-lite-preview)

    댓글·블로그·마케팅 문구 등 자연스러움이 중요한 한국어 출력에 사용.
    3.1 Flash Lite Preview는 번역·RAG·instruction following 강화 모델로
    답변형 댓글에 최적. 2.5 Flash보다 싸고 빠르며 대부분 지표에서 우수.

    실패 시 기본 모델(2.5 Flash Lite)로 자동 폴백.

    Args:
        prompt: 프롬프트
        temperature: 생성 온도 (댓글은 0.6-0.8 권장)
        max_tokens: 최대 출력 토큰
        system_prompt: 시스템 프롬프트 (선택)

    Returns:
        생성된 한국어 텍스트
    """
    client = _get_gemini_client()
    if client is None:
        return "[AI] API 클라이언트 초기화 실패"

    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_prompt:
            config.system_instruction = system_prompt

        response = client.models.generate_content(
            model=_MODEL_KOREAN,
            contents=prompt,
            config=config,
        )
        return (response.text or "").strip()
    except Exception as e:
        logger.warning(f"[AI:{_MODEL_KOREAN}] 한국어 생성 실패: {e} → {_MODEL_CLASSIFY}로 폴백")
        return ai_generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            model=_MODEL_CLASSIFY,
        )


# ── Introspection ──────────────────────────────────────────────────────

def get_model_name() -> str:
    """현재 기본(분류) 모델명 반환"""
    return _MODEL_CLASSIFY


def get_korean_model_name() -> str:
    """한국어 생성 모델명 반환"""
    return _MODEL_KOREAN
