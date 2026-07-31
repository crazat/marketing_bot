"""Codex CLI adapter for API-like LLM calls.

The marketing system treats this module as the boundary between application
code and `codex exec`.  It keeps the rest of the backend on the existing
ai_client function contracts while removing the hard dependency on legacy AI
credentials for text and JSON generation.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
CODEX_MODEL_ALIAS = "codex-cli"

TASK_GENERAL = "general"
TASK_FAST_JSON = "fast_json"
TASK_KOREAN_CONTENT = "korean_content"
TASK_STRUCTURED = "structured"
TASK_VISION = "vision"
TASK_VIRAL_COMMENT = "viral_comment"
TASK_COMPLIANCE = "compliance"
TASK_STRATEGY = "strategy"
TASK_BATCH_FAST = "batch_fast"

# [2026-07-11] GPT-5.6 패밀리(Sol/Terra/Luna) 재분배.
#   Sol   = frontier 추론(5.5 동일가 $5/$30 = 무료 품질 업그레이드) → 고위험 컴플라이언스·전략·댓글
#   Terra = 균형 production($2.50/$15) → 일반 추론·한국어 초안·비전
#   Luna  = 대량 정형($1/$6·1.05M 컨텍스트) → 스키마 판정·분류·추출·배치
# structured(바이럴 unified 판정)→Luna는 라이브 판정 품질 검증 후 확정 권장(모델-티어 변경 게이트).
TASK_MODEL_DEFAULTS: Dict[str, Dict[str, str]] = {
    TASK_GENERAL: {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "verbosity": "medium",
        "description": "General marketing reasoning and plain text generation.",
    },
    TASK_FAST_JSON: {
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "verbosity": "low",
        "description": "Fast JSON classification, tagging, extraction, and short summaries.",
    },
    TASK_KOREAN_CONTENT: {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "verbosity": "medium",
        "description": "Korean medical marketing copy after local compliance screening.",
    },
    TASK_STRUCTURED: {
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "verbosity": "low",
        "description": "Schema-constrained JSON and Pydantic structured output.",
    },
    TASK_VISION: {
        "model": "gpt-5.6-terra",
        "reasoning_effort": "medium",
        "verbosity": "medium",
        "description": "Image-backed evidence, creative, and screenshot analysis.",
    },
    TASK_VIRAL_COMMENT: {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "verbosity": "medium",
        "description": "High-quality Korean viral infiltration comments before local compliance gates.",
    },
    TASK_COMPLIANCE: {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "high",
        "verbosity": "low",
        "description": "Medical advertising law, risk review, and final safety judgment.",
    },
    TASK_STRATEGY: {
        "model": "gpt-5.6-sol",
        "reasoning_effort": "xhigh",
        "verbosity": "medium",
        "description": "World-class readiness, competitive strategy, and executive synthesis.",
    },
    TASK_BATCH_FAST: {
        "model": "gpt-5.6-luna",
        "reasoning_effort": "low",
        "verbosity": "low",
        "description": "Bulk low-risk extraction or classification runs.",
    },
}


class CodexCliError(RuntimeError):
    """Raised when Codex CLI cannot produce a usable final response."""


@dataclass(frozen=True)
class CodexCliConfig:
    bin_path: str
    model: Optional[str]
    profile: Optional[str]
    reasoning_effort: Optional[str]
    verbosity: Optional[str]
    task: str
    cwd: Path
    sandbox: str
    approval_policy: str
    bypass_approvals_and_sandbox: bool
    timeout_seconds: int
    ephemeral: bool
    ignore_rules: bool
    skip_git_repo_check: bool


@dataclass(frozen=True)
class CodexCliResult:
    text: str
    model: str
    latency_ms: int
    stderr_tail: str
    stdout_tail: str
    task: str = TASK_GENERAL
    fallback_used: bool = False


def _truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _clean_optional(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if stripped.lower() in {"auto", "default", "none", "null", "codex-cli"}:
        return None
    return stripped


def _task_key(task: Optional[str]) -> str:
    key = (task or TASK_GENERAL).strip().lower().replace("-", "_")
    return key if key in TASK_MODEL_DEFAULTS else TASK_GENERAL


def _env_name(base: str, task: str) -> str:
    return f"{base}_{task.upper()}"


def _task_defaults_enabled() -> bool:
    return _truthy(os.getenv("CODEX_CLI_USE_TASK_MODEL_DEFAULTS", "true"))


def _resolve_task_value(base: str, task: str, default: Optional[str]) -> Optional[str]:
    task_value = _clean_optional(os.getenv(_env_name(base, task)))
    if task_value is not None:
        return task_value
    global_value = _clean_optional(os.getenv(base))
    if global_value is not None:
        return global_value
    return default if _task_defaults_enabled() else None


def provider_name() -> str:
    return os.getenv("MARKETING_BOT_AI_PROVIDER", "codex").strip().lower()


def codex_enabled() -> bool:
    provider = provider_name()
    return provider not in {"off", "none", "disabled", "false", "0"}


def codex_available() -> bool:
    cfg = load_config()
    return bool(shutil.which(cfg.bin_path))


def load_config(
    task: Optional[str] = None,
    *,
    model_override: Optional[str] = None,
    profile_override: Optional[str] = None,
    reasoning_effort_override: Optional[str] = None,
    verbosity_override: Optional[str] = None,
) -> CodexCliConfig:
    task_name = _task_key(task)
    defaults = TASK_MODEL_DEFAULTS[task_name]
    timeout_raw = os.getenv(_env_name("CODEX_CLI_TIMEOUT_SECONDS", task_name)) or os.getenv("CODEX_CLI_TIMEOUT_SECONDS", "180")
    try:
        timeout_seconds = max(5, int(timeout_raw))
    except ValueError:
        timeout_seconds = 180

    cwd = Path(os.getenv("CODEX_CLI_CD", str(PROJECT_ROOT))).expanduser()
    model = _clean_optional(model_override) or _resolve_task_value("CODEX_CLI_MODEL", task_name, defaults.get("model"))
    profile = _clean_optional(profile_override) or _resolve_task_value("CODEX_CLI_PROFILE", task_name, None)
    reasoning_effort = _clean_optional(reasoning_effort_override) or _resolve_task_value(
        "CODEX_CLI_REASONING_EFFORT", task_name, defaults.get("reasoning_effort")
    )
    verbosity = _clean_optional(verbosity_override) or _resolve_task_value(
        "CODEX_CLI_VERBOSITY", task_name, defaults.get("verbosity")
    )

    return CodexCliConfig(
        bin_path=os.getenv("CODEX_CLI_BIN", "codex"),
        model=model,
        profile=profile,
        reasoning_effort=reasoning_effort,
        verbosity=verbosity,
        task=task_name,
        cwd=cwd,
        sandbox=os.getenv("CODEX_CLI_SANDBOX", "read-only"),
        approval_policy=os.getenv("CODEX_CLI_APPROVAL_POLICY", "never"),
        bypass_approvals_and_sandbox=_truthy(os.getenv("CODEX_CLI_BYPASS_APPROVALS_AND_SANDBOX", "true")),
        timeout_seconds=timeout_seconds,
        ephemeral=_truthy(os.getenv("CODEX_CLI_EPHEMERAL", "true")),
        ignore_rules=_truthy(os.getenv("CODEX_CLI_IGNORE_RULES", "true")),
        skip_git_repo_check=_truthy(os.getenv("CODEX_CLI_SKIP_GIT_REPO_CHECK", "false")),
    )


def task_model_summary() -> Dict[str, Any]:
    return {
        task: {
            "model": load_config(task).model or CODEX_MODEL_ALIAS,
            "profile": load_config(task).profile,
            "reasoning_effort": load_config(task).reasoning_effort,
            "verbosity": load_config(task).verbosity,
            "bypass_approvals_and_sandbox": load_config(task).bypass_approvals_and_sandbox,
            "description": spec["description"],
        }
        for task, spec in TASK_MODEL_DEFAULTS.items()
    }


def _schema_to_dict(schema: Any) -> Dict[str, Any]:
    if schema is None:
        raise ValueError("schema is required")
    if isinstance(schema, dict):
        return schema
    if hasattr(schema, "model_json_schema"):
        return schema.model_json_schema()
    if hasattr(schema, "schema"):
        return schema.schema()
    raise TypeError(f"unsupported response_schema type: {type(schema)!r}")


def _extract_json(text: str) -> str:
    stripped = (text or "").strip()
    if "```json" in stripped:
        return stripped.split("```json", 1)[1].split("```", 1)[0].strip()
    if "```" in stripped:
        return stripped.split("```", 1)[1].split("```", 1)[0].strip()
    return stripped


def parse_json_text(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    candidate = _extract_json(text)
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else {"items": parsed}
    except json.JSONDecodeError:
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(candidate[start : end + 1])
            return parsed if isinstance(parsed, dict) else {"items": parsed}
        except json.JSONDecodeError:
            return None
    return None


def _tail(text: str, limit: int = 4000) -> str:
    if not text:
        return ""
    return text[-limit:]


def _build_base_prompt(
    prompt: str,
    *,
    system_prompt: Optional[str],
    response_mode: str,
    temperature: float,
    max_tokens: int,
) -> str:
    brand_context = os.getenv("MARKETING_BOT_BRAND_NAME", "the marketing system").strip() or "the marketing system"
    blocks = [
        f"You are the non-interactive LLM worker for {brand_context}.",
        "Return only the final answer requested by the application. Do not describe internal reasoning.",
        "Do not edit files, run shell commands, browse the repository, or mention Codex unless the task explicitly asks for it.",
        "Korean medical marketing compliance: avoid guaranteed outcomes, before/after superiority claims, patient inducement, and unverified comparative claims.",
        f"Response mode: {response_mode}. Temperature hint: {temperature}. Max output token hint: {max_tokens}.",
    ]
    if system_prompt:
        blocks.extend(["", "[System instructions]", system_prompt.strip()])
    blocks.extend(["", "[Task]", prompt.strip()])
    return "\n".join(blocks).strip()


def _run_codex_exec(
    prompt: str,
    *,
    output_schema: Optional[Dict[str, Any]] = None,
    images: Optional[Iterable[Path]] = None,
    timeout_seconds: Optional[int] = None,
    task: str = TASK_GENERAL,
    model_override: Optional[str] = None,
    profile_override: Optional[str] = None,
    reasoning_effort_override: Optional[str] = None,
    verbosity_override: Optional[str] = None,
) -> CodexCliResult:
    cfg = load_config(
        task,
        model_override=model_override,
        profile_override=profile_override,
        reasoning_effort_override=reasoning_effort_override,
        verbosity_override=verbosity_override,
    )
    resolved_bin = shutil.which(cfg.bin_path)
    if not resolved_bin:
        raise CodexCliError(f"Codex CLI binary not found: {cfg.bin_path}")

    cfg.cwd.mkdir(parents=True, exist_ok=True)
    try:
        return _run_codex_exec_once(
            cfg,
            resolved_bin,
            prompt,
            output_schema=output_schema,
            images=images,
            timeout_seconds=timeout_seconds,
            fallback_used=False,
        )
    except CodexCliError:
        fallback_enabled = _truthy(os.getenv("CODEX_CLI_MODEL_FALLBACK", "true"))
        global_model = _clean_optional(os.getenv("CODEX_CLI_MODEL"))
        should_retry = fallback_enabled and cfg.model and cfg.model != global_model
        if not should_retry:
            raise
        fallback_cfg = replace(
            cfg,
            model=global_model,
            profile=_clean_optional(os.getenv("CODEX_CLI_PROFILE")),
        )
        logger.warning(
            "[codex_cli] task model failed; retrying with %s for task=%s",
            fallback_cfg.model or CODEX_MODEL_ALIAS,
            cfg.task,
        )
        return _run_codex_exec_once(
            fallback_cfg,
            resolved_bin,
            prompt,
            output_schema=output_schema,
            images=images,
            timeout_seconds=timeout_seconds,
            fallback_used=True,
        )


def _run_codex_exec_once(
    cfg: CodexCliConfig,
    resolved_bin: str,
    prompt: str,
    *,
    output_schema: Optional[Dict[str, Any]] = None,
    images: Optional[Iterable[Path]] = None,
    timeout_seconds: Optional[int] = None,
    fallback_used: bool = False,
) -> CodexCliResult:
    start = time.time()
    output_file = tempfile.NamedTemporaryFile(prefix="codex-final-", suffix=".txt", delete=False)
    output_path = Path(output_file.name)
    output_file.close()

    schema_path: Optional[Path] = None
    try:
        args = [
            resolved_bin,
            "exec",
            "--cd",
            str(cfg.cwd),
            "--color",
            "never",
            "--output-last-message",
            str(output_path),
        ]
        if cfg.bypass_approvals_and_sandbox:
            args.append("--dangerously-bypass-approvals-and-sandbox")
        else:
            args.extend([
                "--sandbox",
                cfg.sandbox,
                "--config",
                f'approval_policy="{cfg.approval_policy}"',
            ])
        if cfg.ephemeral:
            args.append("--ephemeral")
        if cfg.ignore_rules:
            args.append("--ignore-rules")
        if cfg.skip_git_repo_check:
            args.append("--skip-git-repo-check")
        if cfg.model:
            args.extend(["--model", cfg.model])
        if cfg.profile:
            args.extend(["--profile", cfg.profile])
        if cfg.reasoning_effort:
            args.extend(["--config", f'model_reasoning_effort="{cfg.reasoning_effort}"'])
        if cfg.verbosity:
            args.extend(["--config", f'model_verbosity="{cfg.verbosity}"'])
        for image_path in images or []:
            args.extend(["--image", str(image_path)])
        if output_schema is not None:
            schema_file = tempfile.NamedTemporaryFile(prefix="codex-schema-", suffix=".json", mode="w", encoding="utf-8", delete=False)
            json.dump(output_schema, schema_file, ensure_ascii=False)
            schema_file.close()
            schema_path = Path(schema_file.name)
            args.extend(["--output-schema", str(schema_path)])
        args.append("-")

        env = os.environ.copy()
        env.setdefault("NO_COLOR", "1")
        proc = subprocess.run(
            args,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=str(cfg.cwd),
            env=env,
            timeout=timeout_seconds or cfg.timeout_seconds,
        )
        try:
            final_text = output_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            final_text = ""
        if not final_text:
            final_text = (proc.stdout or "").strip()

        if proc.returncode != 0:
            raise CodexCliError(
                f"codex exec failed rc={proc.returncode}: {_tail(proc.stderr or proc.stdout, 1200)}"
            )
        if not final_text:
            raise CodexCliError("codex exec returned an empty final response")

        return CodexCliResult(
            text=final_text,
            model=cfg.model or CODEX_MODEL_ALIAS,
            latency_ms=int((time.time() - start) * 1000),
            stderr_tail=_tail(proc.stderr),
            stdout_tail=_tail(proc.stdout),
            task=cfg.task,
            fallback_used=fallback_used,
        )
    except subprocess.TimeoutExpired as exc:
        raise CodexCliError(f"codex exec timed out after {timeout_seconds or cfg.timeout_seconds}s") from exc
    finally:
        for path in (output_path, schema_path):
            if path:
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    logger.debug("temporary Codex file cleanup failed: %s", path)


def generate_text(
    prompt: str,
    *,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    task: str = TASK_GENERAL,
    model: Optional[str] = None,
    profile: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    verbosity: Optional[str] = None,
) -> CodexCliResult:
    request = _build_base_prompt(
        prompt,
        system_prompt=system_prompt,
        response_mode="plain_text",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return _run_codex_exec(
        request,
        task=task,
        model_override=model,
        profile_override=profile,
        reasoning_effort_override=reasoning_effort,
        verbosity_override=verbosity,
    )


def generate_json(
    prompt: str,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    task: str = TASK_FAST_JSON,
    model: Optional[str] = None,
    profile: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    verbosity: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    request = _build_base_prompt(
        prompt
        + "\n\nReturn only a valid JSON object. Do not wrap it in Markdown fences.",
        system_prompt=system_prompt,
        response_mode="json_object",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    result = _run_codex_exec(
        request,
        task=task,
        model_override=model,
        profile_override=profile,
        reasoning_effort_override=reasoning_effort,
        verbosity_override=verbosity,
    )
    parsed = parse_json_text(result.text)
    if parsed is None:
        raise CodexCliError(f"Codex returned non-JSON output: {result.text[:300]}")
    return parsed


def generate_structured(
    prompt: str,
    response_schema: Any,
    *,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    system_prompt: Optional[str] = None,
    task: str = TASK_STRUCTURED,
    model: Optional[str] = None,
    profile: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    verbosity: Optional[str] = None,
) -> Any:
    schema = _schema_to_dict(response_schema)
    request = _build_base_prompt(
        prompt,
        system_prompt=system_prompt,
        response_mode="json_schema",
        temperature=temperature,
        max_tokens=max_tokens,
    )
    result = _run_codex_exec(
        request,
        output_schema=schema,
        task=task,
        model_override=model,
        profile_override=profile,
        reasoning_effort_override=reasoning_effort,
        verbosity_override=verbosity,
    )
    parsed = json.loads(_extract_json(result.text))
    if isinstance(response_schema, dict):
        return parsed
    if hasattr(response_schema, "model_validate"):
        return response_schema.model_validate(parsed)
    if hasattr(response_schema, "parse_obj"):
        return response_schema.parse_obj(parsed)
    return parsed


def generate_with_images(
    image_paths: List[Path],
    prompt: str,
    *,
    response_schema: Any = None,
    temperature: float = 0.3,
    max_tokens: int = 1024,
    system_prompt: Optional[str] = None,
    task: str = TASK_VISION,
    model: Optional[str] = None,
    profile: Optional[str] = None,
    reasoning_effort: Optional[str] = None,
    verbosity: Optional[str] = None,
) -> Any:
    response_mode = "json_schema" if response_schema is not None else "plain_text"
    request = _build_base_prompt(
        prompt,
        system_prompt=system_prompt,
        response_mode=response_mode,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    schema = _schema_to_dict(response_schema) if response_schema is not None else None
    result = _run_codex_exec(
        request,
        output_schema=schema,
        images=image_paths,
        task=task,
        model_override=model,
        profile_override=profile,
        reasoning_effort_override=reasoning_effort,
        verbosity_override=verbosity,
    )
    if response_schema is None:
        return result.text
    parsed = json.loads(_extract_json(result.text))
    if isinstance(response_schema, dict):
        return parsed
    if hasattr(response_schema, "model_validate"):
        return response_schema.model_validate(parsed)
    if hasattr(response_schema, "parse_obj"):
        return response_schema.parse_obj(parsed)
    return parsed


def record_codex_call(caller_module: str, result: CodexCliResult, prompt: str) -> None:
    try:
        from services.ai_cost import record_call

        record_call(
            caller_module=caller_module,
            model=result.model,
            input_tokens=max(1, len(prompt) // 4),
            output_tokens=max(1, len(result.text) // 4),
            cached_tokens=0,
            latency_ms=result.latency_ms,
        )
    except Exception as exc:
        logger.debug("[codex_cli] cost logging skipped: %s", exc)
