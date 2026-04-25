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
import hashlib
import logging
import threading
from typing import Optional, Dict, Any, List, Type, Iterable
from collections import OrderedDict
from contextlib import contextmanager

logger = logging.getLogger(__name__)

# Logfire span (선택적 — 미설치/초기화 안 됐어도 무료)
try:
    import logfire as _logfire
    _HAS_LOGFIRE = True
except Exception:
    _HAS_LOGFIRE = False

# Langfuse observe (선택적 — 환경변수로 켜기. LANGFUSE_HOST/PUBLIC_KEY/SECRET_KEY)
try:
    from langfuse import observe as _langfuse_observe
    _HAS_LANGFUSE = bool(os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY"))
except Exception:
    _HAS_LANGFUSE = False
    def _langfuse_observe(*a, **k):
        def deco(fn): return fn
        return deco


def _observe(name: str = ""):
    """Langfuse @observe — 키 없으면 no-op."""
    if _HAS_LANGFUSE:
        return _langfuse_observe(name=name) if name else _langfuse_observe()
    def deco(fn): return fn
    return deco


@contextmanager
def _trace(name: str, **attrs):
    """logfire span 컨텍스트 — 없으면 no-op."""
    if _HAS_LOGFIRE:
        with _logfire.span(name, **attrs) as span:
            yield span
    else:
        yield None

# 컨텍스트 캐싱: Gemini 2.5 Flash Lite 최소 2048 토큰 (한국어 ~1500자, 영어 ~6000자)
# system_prompt가 이 임계값 이상이면 자동 캐싱 (75-90% 비용 절감)
_CACHE_MIN_CHARS = 1500
_CACHE_TTL = "3600s"  # 1시간
_cache_registry: "OrderedDict[str, str]" = OrderedDict()  # hash -> cache_name
_cache_registry_lock = threading.Lock()
_CACHE_REGISTRY_MAX = 16

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

@_observe(name="ai_generate")
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

    import time as _time
    with _trace("ai_generate", model=model_id, prompt_len=len(prompt),
                has_system=bool(system_prompt)):
        t0 = _time.time()
        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            cache_used = False
            if system_prompt:
                cache_name = _get_or_create_cached_content(client, model_id, system_prompt)
                if cache_name:
                    config.cached_content = cache_name
                    cache_used = True
                else:
                    config.system_instruction = system_prompt

            response = client.models.generate_content(
                model=model_id,
                contents=prompt,
                config=config,
            )
            text = (response.text or "").strip()
            # 비용 기록
            try:
                from services.ai_cost import record_call
                usage = getattr(response, "usage_metadata", None)
                in_tok = getattr(usage, "prompt_token_count", 0) if usage else 0
                out_tok = getattr(usage, "candidates_token_count", 0) if usage else 0
                cached_tok = getattr(usage, "cached_content_token_count", 0) if usage else 0
                record_call(
                    caller_module="ai_generate",
                    model=model_id,
                    input_tokens=in_tok,
                    output_tokens=out_tok,
                    cached_tokens=cached_tok or 0,
                    latency_ms=int((_time.time() - t0) * 1000),
                )
            except Exception as _e:
                logger.debug(f"[ai_cost] record_call skip: {_e}")
            if _HAS_LOGFIRE:
                _logfire.info(
                    "ai_generate_complete",
                    model=model_id,
                    cache_used=cache_used,
                    output_len=len(text),
                )
            return text
        except Exception as e:
            logger.error(f"[AI:{model_id}] 생성 실패: {e}")
            return f"[AI] 생성 오류: {str(e)}"


@_observe(name="ai_generate_json")
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
            cache_name = _get_or_create_cached_content(client, model_id, system_prompt)
            if cache_name:
                config.cached_content = cache_name
            else:
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


def ai_generate_stream(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
):
    """SSE/EventSource 친화적 스트리밍 generator.

    Yields:
        text chunks (string)
    """
    client = _get_gemini_client()
    if client is None:
        yield "[AI] API 클라이언트 초기화 실패"
        return
    model_id = _normalize_model(model, _MODEL_KOREAN)
    try:
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_prompt:
            cache_name = _get_or_create_cached_content(client, model_id, system_prompt)
            if cache_name:
                config.cached_content = cache_name
            else:
                config.system_instruction = system_prompt
        stream = client.models.generate_content_stream(
            model=model_id, contents=prompt, config=config,
        )
        for chunk in stream:
            txt = getattr(chunk, "text", None)
            if txt:
                yield txt
    except Exception as e:
        logger.error(f"[AI:{model_id}] stream 실패: {e}")
        yield f"\n[AI] stream 오류: {e}"


@_observe(name="ai_generate_korean")
def ai_generate_korean(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
    *,
    compliance_screen: bool = True,
    ai_disclosure_required: bool = True,
    call_site: str = "",
) -> str:
    """
    한국어 자연어 생성 전용 (gemini-3.1-flash-lite-preview)

    댓글·블로그·마케팅 문구 등 자연스러움이 중요한 한국어 출력에 사용.
    3.1 Flash Lite Preview는 번역·RAG·instruction following 강화 모델로
    답변형 댓글에 최적. 2.5 Flash보다 싸고 빠르며 대부분 지표에서 우수.

    실패 시 기본 모델(2.5 Flash Lite)로 자동 폴백.

    의료광고법 컴플라이언스: compliance_screen=True (기본)면 생성 후 자동 스크린.
    high severity 위반 검출 시 1회 재시도 (가능성 표현으로 부드럽게 다시).
    의료 콘텐츠 + 광고/협찬 표기 부재 시 #광고 자동 첨부.
    모든 호출은 ai_korean_screen_log 테이블에 기록.

    Args:
        prompt: 프롬프트
        temperature: 생성 온도 (댓글은 0.6-0.8 권장)
        max_tokens: 최대 출력 토큰
        system_prompt: 시스템 프롬프트 (선택)
        compliance_screen: 컴플라이언스 자동 스크린 (기본 True)
        call_site: 호출 위치 표시 (감사 로그용, 예: "viral_hunter")

    Returns:
        생성된 한국어 텍스트 (스크린 통과/자동 수정된 최종본)
    """
    client = _get_gemini_client()
    if client is None:
        return "[AI] API 클라이언트 초기화 실패"

    def _call(p: str) -> str:
        from google.genai import types
        config = types.GenerateContentConfig(
            temperature=temperature,
            max_output_tokens=max_tokens,
        )
        if system_prompt:
            cache_name = _get_or_create_cached_content(client, _MODEL_KOREAN, system_prompt)
            if cache_name:
                config.cached_content = cache_name
            else:
                config.system_instruction = system_prompt
        response = client.models.generate_content(
            model=_MODEL_KOREAN,
            contents=p,
            config=config,
        )
        return (response.text or "").strip()

    try:
        text = _call(prompt)
    except Exception as e:
        logger.warning(f"[AI:{_MODEL_KOREAN}] 한국어 생성 실패: {e} → {_MODEL_CLASSIFY}로 폴백")
        text = ai_generate(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            model=_MODEL_CLASSIFY,
        )

    if not compliance_screen:
        return text

    # 컴플라이언스 게이트
    try:
        from services.content_compliance import (
            screen_korean_comment, log_korean_screen, _resolve_default_db_path,
        )
    except Exception as e:
        logger.warning(f"[compliance] 모듈 import 실패, 스크린 건너뜀: {e}")
        return text

    result = screen_korean_comment(text)
    retry_count = 0

    # high severity 위반 → 1회 재시도 (제약 강화 프롬프트)
    if not result.get("passed"):
        retry_count = 1
        retry_prompt = (
            f"{prompt}\n\n[필수 제약]\n"
            "- 1인칭 후기 화법(저는/제가/내가) 금지\n"
            "- 치료효과 단정 표현(완치/100%/확실히/반드시) 금지\n"
            "- 타 의료기관 비교/최상급 표현 금지\n"
            "- 의료진 합성 추천 표현 금지\n"
            "- '도움이 될 수 있습니다' 등 가능성 표현 사용\n"
        )
        try:
            text = _call(retry_prompt)
        except Exception as e:
            logger.warning(f"[compliance] 재시도 실패: {e}")
        result = screen_korean_comment(text)

    db_path = _resolve_default_db_path()
    if db_path:
        try:
            log_korean_screen(
                db_path,
                call_site=call_site,
                prompt_sample=prompt,
                generated_text=text,
                screen_result=result,
                retry_count=retry_count,
            )
        except Exception as e:
            logger.debug(f"[compliance] 로그 실패: {e}")

    if not result.get("passed"):
        # 재시도 후에도 위반 → 안전한 대체 텍스트
        logger.error(
            f"[compliance] 재시도 후에도 위반 (call_site={call_site}, "
            f"violations={[v.get('category') for v in result.get('violations', [])]})"
        )
        return "[AI] 의료광고법 위반 가능성으로 생성 차단됨"

    final = result.get("final_text") or text
    # AI 기본법 (2026/1) — 생성 사실 고지 의무 자동 첨부
    if ai_disclosure_required:
        try:
            from services.content_compliance import append_ai_disclosure
            final = append_ai_disclosure(final)
        except Exception as e:
            logger.debug(f"[compliance] AI 고지 첨부 실패 (계속): {e}")
    return final


# ── Context Caching ────────────────────────────────────────────────────

def _system_prompt_hash(model: str, system_prompt: str) -> str:
    """system_prompt + model 조합의 안정된 해시."""
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(system_prompt.encode("utf-8"))
    return h.hexdigest()


def _get_or_create_cached_content(
    client, model: str, system_prompt: str
) -> Optional[str]:
    """
    system_prompt가 충분히 길면 cached content를 만들고 cache name 반환.
    이후 호출에서 같은 system_prompt면 cache name 재사용 → 75-90% 비용 절감.

    Returns:
        cache_name (예: "cachedContents/abc...") or None (캐싱 미사용)
    """
    if not system_prompt or len(system_prompt) < _CACHE_MIN_CHARS:
        return None

    key = _system_prompt_hash(model, system_prompt)
    with _cache_registry_lock:
        if key in _cache_registry:
            # LRU touch
            _cache_registry.move_to_end(key)
            return _cache_registry[key]

    try:
        from google.genai import types
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                system_instruction=system_prompt,
                ttl=_CACHE_TTL,
                display_name=f"sysprompt_{key[:10]}",
            ),
        )
        cache_name = cache.name
        with _cache_registry_lock:
            _cache_registry[key] = cache_name
            # LRU eviction
            while len(_cache_registry) > _CACHE_REGISTRY_MAX:
                _cache_registry.popitem(last=False)
        logger.info(f"[AI:cache] created {cache_name} (key={key[:10]}, sys_prompt={len(system_prompt)}c)")
        return cache_name
    except Exception as e:
        # 캐시 실패는 치명적이지 않음 (정상 호출로 폴백)
        logger.debug(f"[AI:cache] create failed (non-fatal): {e}")
        return None


# ── Structured output (Pydantic schema) ────────────────────────────────

def ai_generate_structured(
    prompt: str,
    response_schema,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
) -> Optional[Any]:
    """
    Pydantic 모델 기반 구조화 생성 (parse-and-recover 불필요).

    Gemini의 response_schema 기능 활용. 잘못된 JSON 자체가 발생하지 않음.

    Args:
        prompt: 사용자 프롬프트
        response_schema: Pydantic BaseModel 클래스 또는 dict 스키마
        temperature/max_tokens/system_prompt/model: 표준 옵션

    Returns:
        파싱된 Pydantic 인스턴스 (또는 dict 스키마면 dict) — 실패 시 None
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
            response_schema=response_schema,
        )
        if system_prompt:
            cache_name = _get_or_create_cached_content(client, model_id, system_prompt)
            if cache_name:
                config.cached_content = cache_name
            else:
                config.system_instruction = system_prompt

        response = client.models.generate_content(
            model=model_id, contents=prompt, config=config,
        )
        # 신 SDK는 .parsed 속성 제공
        parsed = getattr(response, "parsed", None)
        if parsed is not None:
            return parsed
        # 폴백: text → json
        text = (response.text or "").strip()
        if not text:
            return None
        return json.loads(_extract_json(text))
    except Exception as e:
        logger.error(f"[AI:{model_id}] structured 생성 실패: {e}")
        return None


# ── Batch API (50% discount, 24h SLA) ──────────────────────────────────

def ai_generate_batch(
    requests: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Optional[str]:
    """
    배치 작업 제출. Pathfinder 키워드 분류, 리뷰 NLP 등 비대화형 작업에 최적.
    Gemini 배치는 50% 할인 + 24시간 SLA.

    Args:
        requests: [{"prompt": "...", "system_prompt": "...", "temperature": 0.5}, ...]
                  최소 한 개 이상의 prompt 필요
        model: 모델 override
        display_name: 작업 표시명 (선택)

    Returns:
        batch_job 이름 (조회 가능 식별자) — 실패 시 None

    Note:
        결과 조회는 별도 함수 ai_batch_status / ai_batch_results 사용.
        배치 결과는 24시간 내 완료, 보통 수분~수시간.
    """
    client = _get_gemini_client()
    if client is None:
        return None
    model_id = _normalize_model(model, _MODEL_CLASSIFY)

    try:
        from google.genai import types
        inline_requests = []
        for req in requests:
            cfg = types.GenerateContentConfig(
                temperature=req.get("temperature", 0.5),
                max_output_tokens=req.get("max_tokens", 2048),
            )
            if req.get("system_prompt"):
                cfg.system_instruction = req["system_prompt"]
            inline_requests.append({
                "contents": [{"parts": [{"text": req["prompt"]}], "role": "user"}],
                "config": cfg.model_dump() if hasattr(cfg, "model_dump") else dict(cfg),
            })

        job = client.batches.create(
            model=model_id,
            src=inline_requests,
            config={"display_name": display_name or f"batch_{len(requests)}items"},
        )
        logger.info(f"[AI:batch] submitted {job.name} ({len(requests)} requests)")
        return job.name
    except Exception as e:
        logger.error(f"[AI:batch] submit 실패: {e}")
        return None


def ai_batch_status(batch_name: str) -> Optional[str]:
    """배치 상태 조회 (PENDING / RUNNING / SUCCEEDED / FAILED 등)."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        job = client.batches.get(name=batch_name)
        # state는 enum or str
        state = getattr(job, "state", None)
        return str(state) if state else None
    except Exception as e:
        logger.error(f"[AI:batch] status 조회 실패: {e}")
        return None


def ai_batch_results(batch_name: str) -> Optional[List[str]]:
    """배치 완료 결과 텍스트 리스트. 미완료/실패면 None."""
    client = _get_gemini_client()
    if client is None:
        return None
    try:
        job = client.batches.get(name=batch_name)
        state = str(getattr(job, "state", ""))
        if "SUCCEEDED" not in state:
            return None
        results = []
        for r in (job.dest.inlined_responses or []):
            try:
                txt = r.response.candidates[0].content.parts[0].text
                results.append(txt or "")
            except Exception:
                results.append("")
        return results
    except Exception as e:
        logger.error(f"[AI:batch] results 조회 실패: {e}")
        return None


# ── Vision (Multimodal) ───────────────────────────────────────────────

_MODEL_VISION = os.getenv("GEMINI_VISION_MODEL", "gemini-2.5-flash-lite")


def ai_analyze_image(
    image_source,
    prompt: str,
    *,
    response_schema=None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    model: Optional[str] = None,
):
    """이미지 분석 (Gemini Vision).

    Args:
        image_source: 다음 중 하나
            - bytes (raw image bytes)
            - str (URL or file path)
            - PIL.Image.Image
            - dict {"mime_type": "image/jpeg", "data": bytes}
            - list (multiple images, 위 형식 mix 가능)
        prompt: 분석 지시
        response_schema: Pydantic 모델 — 구조화 응답 (선택)
        temperature/max_tokens/model: 표준 옵션

    Returns:
        - schema 있으면 parsed instance
        - 없으면 text str
        - 실패 시 None
    """
    client = _get_gemini_client()
    if client is None:
        return None
    model_id = _normalize_model(model, _MODEL_VISION)

    # 입력 정규화
    images = image_source if isinstance(image_source, list) else [image_source]
    parts = []
    for img in images:
        try:
            if isinstance(img, str):
                if img.startswith(("http://", "https://")):
                    import requests as _rq
                    r = _rq.get(img, timeout=15)
                    r.raise_for_status()
                    mime = r.headers.get("content-type", "image/jpeg").split(";")[0]
                    parts.append({"inline_data": {"mime_type": mime, "data": r.content}})
                else:
                    # 파일 경로
                    if not os.path.exists(img):
                        logger.warning(f"[AI:vision] file not found: {img}")
                        continue
                    with open(img, "rb") as f:
                        data = f.read()
                    ext = os.path.splitext(img)[1].lower().lstrip(".")
                    mime = f"image/{ext if ext != 'jpg' else 'jpeg'}"
                    parts.append({"inline_data": {"mime_type": mime, "data": data}})
            elif isinstance(img, bytes):
                parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img}})
            elif isinstance(img, dict) and "data" in img:
                parts.append({"inline_data": {
                    "mime_type": img.get("mime_type", "image/jpeg"), "data": img["data"]}})
            else:
                # PIL.Image
                try:
                    import io as _io
                    buf = _io.BytesIO()
                    img.save(buf, format="JPEG")
                    parts.append({"inline_data": {"mime_type": "image/jpeg", "data": buf.getvalue()}})
                except Exception as e:
                    logger.warning(f"[AI:vision] unsupported image type: {type(img)} ({e})")
        except Exception as e:
            logger.warning(f"[AI:vision] image load 실패: {e}")
    parts.append({"text": prompt})

    if not [p for p in parts if "inline_data" in p]:
        logger.error("[AI:vision] 이미지 0건")
        return None

    with _trace("ai_analyze_image", model=model_id, n_images=len(parts) - 1):
        try:
            from google.genai import types
            cfg_kwargs = dict(
                temperature=temperature,
                max_output_tokens=max_tokens,
            )
            if response_schema:
                cfg_kwargs["response_mime_type"] = "application/json"
                cfg_kwargs["response_schema"] = response_schema
            cfg = types.GenerateContentConfig(**cfg_kwargs)
            response = client.models.generate_content(
                model=model_id,
                contents=[{"parts": parts}],
                config=cfg,
            )
            if response_schema:
                parsed = getattr(response, "parsed", None)
                if parsed is not None:
                    return parsed
                # fallback parse
                txt = (response.text or "").strip()
                return json.loads(_extract_json(txt)) if txt else None
            return (response.text or "").strip()
        except Exception as e:
            logger.error(f"[AI:vision:{model_id}] 실패: {e}")
            return None


# ── Introspection ──────────────────────────────────────────────────────

def get_model_name() -> str:
    """현재 기본(분류) 모델명 반환"""
    return _MODEL_CLASSIFY


def get_korean_model_name() -> str:
    """한국어 생성 모델명 반환"""
    return _MODEL_KOREAN


def cache_stats() -> Dict[str, Any]:
    """캐시 레지스트리 상태 반환 (디버깅/관측)."""
    with _cache_registry_lock:
        return {
            "active_caches": len(_cache_registry),
            "max_size": _CACHE_REGISTRY_MAX,
            "ttl": _CACHE_TTL,
            "min_chars": _CACHE_MIN_CHARS,
        }
