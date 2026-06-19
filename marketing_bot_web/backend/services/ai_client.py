"""Codex CLI-only AI client.

This module is the stable application contract for all marketing LLM calls.
The implementation intentionally has no legacy Google SDK fallback: every
text, JSON, structured, batch, and image call goes through `codex exec` via
`services.codex_cli_client`.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

try:
    from dotenv import load_dotenv as _load_dotenv

    _project_root = Path(__file__).resolve().parent.parent.parent.parent
    _env_path = _project_root / ".env"
    if _env_path.exists():
        _load_dotenv(_env_path, override=False)
except Exception:
    pass

try:
    from services import codex_cli_client as _codex_cli
except Exception:
    try:
        from marketing_bot_web.backend.services import codex_cli_client as _codex_cli
    except Exception:
        _codex_cli = None

_codex_batch_results: Dict[str, Dict[str, Any]] = {}


def _ai_disabled() -> bool:
    disabled = os.getenv("MARKETING_BOT_DISABLE_AI", os.getenv("DISABLE_AI", "false"))
    if disabled.strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if os.getenv("PYTEST_CURRENT_TEST") and os.getenv("MARKETING_BOT_ENABLE_AI_IN_TESTS", "false").lower() != "true":
        return True
    return False


def _codex_error_message(exc: Exception) -> str:
    return f"[AI Error] Codex CLI is unavailable: {exc}"


def _codex_model_override(model: Optional[str]) -> Optional[str]:
    if not model:
        return None
    lowered = model.lower()
    if lowered.startswith(("g" + "emini", "google", "qwen")):
        logger.warning("[AI] Ignoring legacy model override: %s", model)
        return None
    return model


def ai_available() -> bool:
    if _ai_disabled() or _codex_cli is None:
        return False
    return _codex_cli.codex_available()


def ai_provider_status() -> Dict[str, Any]:
    if _codex_cli is None:
        return {
            "provider": "codex_cli",
            "available": False,
            "error": "services.codex_cli_client import failed",
        }
    cfg = _codex_cli.load_config()
    return {
        "provider": "codex_cli",
        "available": _codex_cli.codex_available() and not _ai_disabled(),
        "model": cfg.model or _codex_cli.CODEX_MODEL_ALIAS,
        "task_models": _codex_cli.task_model_summary(),
        "sandbox": cfg.sandbox,
        "approval_policy": cfg.approval_policy,
        "bypass_approvals_and_sandbox": cfg.bypass_approvals_and_sandbox,
        "timeout_seconds": cfg.timeout_seconds,
    }


def _require_codex() -> Any:
    if _ai_disabled():
        raise RuntimeError("AI is disabled by environment")
    if _codex_cli is None:
        raise RuntimeError("services.codex_cli_client import failed")
    if not _codex_cli.codex_available():
        cfg = _codex_cli.load_config()
        raise RuntimeError(f"Codex CLI binary not found: {cfg.bin_path}")
    return _codex_cli


def _extract_json(text: str) -> str:
    if "```json" in text:
        return text.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in text:
        return text.split("```", 1)[1].split("```", 1)[0].strip()
    return text.strip()


def _repair_json(text: str) -> Optional[Dict[str, Any]]:
    for i in range(len(text) - 1, -1, -1):
        if text[i] in ("}", "]"):
            try:
                parsed = json.loads(text[: i + 1])
                return parsed if isinstance(parsed, dict) else {"items": parsed}
            except json.JSONDecodeError:
                continue
    return None


def ai_generate(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    task: str = "general",
) -> str:
    try:
        codex = _require_codex()
        result = codex.generate_text(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            task=task,
            model=_codex_model_override(model),
        )
        codex.record_codex_call("ai_generate", result, prompt)
        return result.text
    except Exception as exc:
        logger.error("[Codex CLI] text generation failed: %s", exc)
        return _codex_error_message(exc)


def ai_generate_json(
    prompt: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    task: str = "fast_json",
) -> Optional[Dict[str, Any]]:
    try:
        codex = _require_codex()
        return codex.generate_json(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            task=task,
            model=_codex_model_override(model),
        )
    except Exception as exc:
        logger.error("[Codex CLI] JSON generation failed: %s", exc)
        return None


def ai_generate_stream(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    task: str = "general",
):
    yield ai_generate(
        prompt,
        temperature=temperature,
        max_tokens=max_tokens,
        system_prompt=system_prompt,
        model=model,
        task=task,
    )


def _screen_korean_text(
    text: str,
    prompt: str,
    *,
    call_site: str,
    retry_count: int,
) -> Dict[str, Any]:
    try:
        from services.content_compliance import (
            _resolve_default_db_path,
            log_korean_screen,
            screen_korean_comment,
        )
    except Exception as exc:
        logger.warning("[compliance] import failed, allowing generated text: %s", exc)
        return {"passed": True, "final_text": text, "violations": []}

    result = screen_korean_comment(text, auto_append_disclosure=False)
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
        except Exception as exc:
            logger.debug("[compliance] screen log failed: %s", exc)
    return result


def ai_generate_korean(
    prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 2048,
    system_prompt: Optional[str] = None,
    *,
    compliance_screen: bool = True,
    ai_disclosure_required: bool = True,
    call_site: str = "",
    task: str = "korean_content",
) -> str:
    try:
        codex = _require_codex()
        result = codex.generate_text(
            prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            task=task,
        )
        codex.record_codex_call("ai_generate_korean", result, prompt)
        text = result.text
    except Exception as exc:
        logger.error("[Codex CLI] Korean generation failed: %s", exc)
        return _codex_error_message(exc)

    if not compliance_screen:
        return text

    screen = _screen_korean_text(text, prompt, call_site=call_site, retry_count=0)
    if not screen.get("passed"):
        # 바이럴 댓글은 '실제 다녀온 환자 후기' 톤(1인칭 방문·경험담)을 의도적으로 유지한다
        # (운영 결정 2026-06-19). 그래서 viral_comment 는 retry 시 1인칭 치료 경험 제거를
        # 지시하지 않는다. 단, 단정적 효과·할인·이벤트·실명 의료진 추천 등 경성 의료광고법
        # 위반은 viral 여부와 무관하게 계속 제거한다.
        revision_lines = ["- Use possibility-based wording only."]
        if task != "viral_comment":
            revision_lines.append("- Remove first-person treatment experience wording.")
        revision_lines += [
            "- Remove guaranteed outcomes, discounts, event claims, and comparative superiority.",
            "- Do not recommend named clinicians.",
            "- Keep it natural Korean, 1-2 sentences.",
        ]
        retry_prompt = f"{prompt}\n\n[Required revision]\n" + "\n".join(revision_lines)
        try:
            result = codex.generate_text(
                retry_prompt,
                temperature=min(temperature, 0.6),
                max_tokens=max_tokens,
                system_prompt=system_prompt,
                task=task,
            )
            codex.record_codex_call("ai_generate_korean_retry", result, retry_prompt)
            text = result.text
            screen = _screen_korean_text(text, prompt, call_site=call_site, retry_count=1)
        except Exception as exc:
            logger.error("[Codex CLI] Korean compliance retry failed: %s", exc)
            return _codex_error_message(exc)

    if not screen.get("passed"):
        logger.error(
            "[compliance] generation blocked call_site=%s violations=%s",
            call_site,
            [v.get("category") for v in screen.get("violations", [])],
        )
        return "[AI] generation blocked by medical advertising compliance"

    final = screen.get("final_text") or text
    # 바이럴 댓글은 '실제 다녀온 환자 후기' 톤을 깨지 않도록 AI 보조 고지 푸터를 붙이지
    # 않는다(운영 결정 2026-06-19; viral 댓글 #광고 푸터 비활성과 동일 맥락). 그 외 한국어
    # 콘텐츠는 기존대로 고지 푸터를 유지한다(AI 기본법 대응).
    if ai_disclosure_required and task != "viral_comment":
        try:
            from services.content_compliance import append_ai_disclosure

            final = append_ai_disclosure(final)
        except Exception as exc:
            logger.debug("[compliance] AI disclosure append failed: %s", exc)
    return final


def ai_generate_structured(
    prompt: str,
    response_schema,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    task: str = "structured",
) -> Optional[Any]:
    try:
        codex = _require_codex()
        return codex.generate_structured(
            prompt,
            response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            system_prompt=system_prompt,
            task=task,
            model=_codex_model_override(model),
        )
    except Exception as exc:
        logger.error("[Codex CLI] structured generation failed: %s", exc)
        return None


def ai_generate_batch(
    requests: List[Dict[str, Any]],
    *,
    model: Optional[str] = None,
    display_name: Optional[str] = None,
) -> Optional[str]:
    try:
        codex = _require_codex()
    except Exception as exc:
        logger.error("[Codex CLI] batch unavailable: %s", exc)
        return None

    payload = json.dumps(requests, ensure_ascii=False, sort_keys=True, default=str)
    batch_id = f"codex_local_batch_{int(time.time())}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:10]}"
    results: List[str] = []
    try:
        for req in requests:
            result = codex.generate_text(
                req["prompt"],
                temperature=req.get("temperature", 0.5),
                max_tokens=req.get("max_tokens", 2048),
                system_prompt=req.get("system_prompt"),
                task=req.get("task") or "batch_fast",
                model=_codex_model_override(req.get("model") or model),
            )
            codex.record_codex_call("ai_generate_batch", result, req["prompt"])
            results.append(result.text)
        _codex_batch_results[batch_id] = {
            "status": "SUCCEEDED",
            "results": results,
            "display_name": display_name or f"batch_{len(requests)}items",
            "model": model or get_model_name(),
        }
        return batch_id
    except Exception as exc:
        logger.error("[Codex CLI] batch failed: %s", exc)
        _codex_batch_results[batch_id] = {
            "status": "FAILED",
            "results": results,
            "error": str(exc),
            "display_name": display_name or f"batch_{len(requests)}items",
            "model": model or get_model_name(),
        }
        return None


def ai_batch_status(batch_name: str) -> Optional[str]:
    item = _codex_batch_results.get(batch_name)
    return item.get("status") if item else None


def ai_batch_results(batch_name: str) -> Optional[List[str]]:
    item = _codex_batch_results.get(batch_name)
    if not item or item.get("status") != "SUCCEEDED":
        return None
    return list(item.get("results") or [])


def ai_analyze_image(
    image_source,
    prompt: str,
    *,
    response_schema=None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    model: Optional[str] = None,
    task: str = "vision",
):
    tmp_paths: List[Path] = []
    image_paths: List[Path] = []
    try:
        codex = _require_codex()
        images = image_source if isinstance(image_source, list) else [image_source]
        for img in images:
            if isinstance(img, str) and not img.startswith(("http://", "https://")):
                path = Path(img)
                if path.exists():
                    image_paths.append(path)
                else:
                    logger.warning("[AI:vision] file not found: %s", img)
                continue

            suffix = ".jpg"
            data = None
            if isinstance(img, str) and img.startswith(("http://", "https://")):
                import requests as _requests

                response = _requests.get(img, timeout=15)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
                if content_type.endswith("png"):
                    suffix = ".png"
                elif content_type.endswith("webp"):
                    suffix = ".webp"
                data = response.content
            elif isinstance(img, bytes):
                data = img
            elif isinstance(img, dict) and "data" in img:
                data = img["data"]
                mime = img.get("mime_type", "image/jpeg")
                if mime.endswith("png"):
                    suffix = ".png"
                elif mime.endswith("webp"):
                    suffix = ".webp"
            else:
                import io

                buffer = io.BytesIO()
                img.save(buffer, format="JPEG")
                data = buffer.getvalue()

            if data:
                tmp = tempfile.NamedTemporaryFile(prefix="codex-image-", suffix=suffix, delete=False)
                tmp.write(data)
                tmp.close()
                path = Path(tmp.name)
                tmp_paths.append(path)
                image_paths.append(path)

        if not image_paths:
            logger.error("[AI:vision] no images available")
            return None

        return codex.generate_with_images(
            image_paths,
            prompt,
            response_schema=response_schema,
            temperature=temperature,
            max_tokens=max_tokens,
            task=task,
            model=_codex_model_override(model),
        )
    except Exception as exc:
        logger.error("[Codex CLI] image analysis failed: %s", exc)
        return None
    finally:
        for path in tmp_paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.debug("[AI:vision] temp cleanup failed: %s", path)


def get_model_name() -> str:
    if _codex_cli is None:
        return "codex-cli"
    cfg = _codex_cli.load_config("general")
    return cfg.model or _codex_cli.CODEX_MODEL_ALIAS


def get_korean_model_name() -> str:
    if _codex_cli is None:
        return "codex-cli"
    cfg = _codex_cli.load_config("korean_content")
    return cfg.model or _codex_cli.CODEX_MODEL_ALIAS


def cache_stats() -> Dict[str, Any]:
    return {
        "active_caches": 0,
        "max_size": 0,
        "ttl": None,
        "min_chars": 0,
        "provider": ai_provider_status(),
    }
