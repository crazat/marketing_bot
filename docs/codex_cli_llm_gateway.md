# Codex CLI LLM Gateway

This project now uses Codex CLI as the primary LLM execution layer.

## Why this path

The official Codex non-interactive interface is `codex exec`. It is designed for
scripted workflows, supports stdin prompts, JSONL events, `--output-last-message`,
and `--output-schema` for structured final responses. The current backend is
Python and already calls synchronous `ai_client` functions, so a subprocess
adapter is the smallest reliable migration step.

For longer-lived agent workflows, Codex also exposes MCP server, app-server, and
SDK surfaces. Those are better candidates for future multi-turn engineering
automation, not for simple marketing text/JSON calls that need to preserve the
existing function contracts.

## Runtime defaults

```env
MARKETING_BOT_AI_PROVIDER=codex
CODEX_CLI_BIN=codex
CODEX_CLI_MODEL=
CODEX_CLI_SANDBOX=read-only
CODEX_CLI_APPROVAL_POLICY=never
CODEX_CLI_BYPASS_APPROVALS_AND_SANDBOX=true
CODEX_CLI_TIMEOUT_SECONDS=180
CODEX_CLI_EPHEMERAL=true
CODEX_CLI_IGNORE_RULES=true
CODEX_CLI_USE_TASK_MODEL_DEFAULTS=true
CODEX_CLI_MODEL_FALLBACK=true
MARKETING_BOT_AI_LEGACY_FALLBACK=false
```

`CODEX_CLI_BYPASS_APPROVALS_AND_SANDBOX=true` maps to Codex CLI's
`--dangerously-bypass-approvals-and-sandbox` flag. When enabled, the adapter
does not pass `--sandbox` or `approval_policy` because the bypass flag controls
both behaviors.

`CODEX_CLI_MODEL` is a global override. Leave it blank unless operations wants
to force every task through one model. Task-specific defaults below are used
when `CODEX_CLI_USE_TASK_MODEL_DEFAULTS=true`.

## Purpose Routing

| Task | Default model | Reasoning | Verbosity | Used for |
| --- | --- | --- | --- | --- |
| `general` | `gpt-5.4` | `medium` | `medium` | Normal text generation and broad analysis |
| `fast_json` | `gpt-5.4-mini` | `low` | `low` | Classification, extraction, small JSON, lead/review tagging |
| `korean_content` | `gpt-5.4` | `medium` | `medium` | Korean ad and blog drafts before local compliance gates |
| `structured` | `gpt-5.4-mini` | `low` | `low` | Pydantic and JSON Schema constrained responses |
| `vision` | `gpt-5.4` | `medium` | `medium` | Image/screenshot/evidence analysis |
| `viral_comment` | `gpt-5.5` | `high` | `medium` | High-quality Korean viral infiltration comments before local compliance gates |
| `compliance` | `gpt-5.5` | `high` | `low` | Medical advertising law and high-risk copy review |
| `strategy` | `gpt-5.5` | `xhigh` | `medium` | World-class readiness, executive synthesis, council voting |
| `batch_fast` | `gpt-5.3-codex-spark` | `low` | `low` | Bulk low-risk text extraction or classification |

On this ChatGPT-authenticated Codex CLI installation, `codex debug models`
currently exposes `gpt-5.5`, `gpt-5.4`, `gpt-5.4-mini`,
`gpt-5.3-codex-spark`, and `codex-auto-review`. API model names such as
`gpt-5.1`, `gpt-5.1-codex`, and `gpt-5-nano` return a Codex CLI 400 in this
account, so production routing uses the local Codex catalog names above.

Each task can be overridden independently:

```env
CODEX_CLI_MODEL_COMPLIANCE=gpt-5.5
CODEX_CLI_REASONING_EFFORT_COMPLIANCE=high
CODEX_CLI_VERBOSITY_COMPLIANCE=low
CODEX_CLI_PROFILE_STRATEGY=
```

If a task-specific model fails, `CODEX_CLI_MODEL_FALLBACK=true` retries once
with the global `CODEX_CLI_MODEL` or the authenticated Codex CLI default model.

## Adapter behavior

- `ai_generate` calls `codex exec` and returns the final message on the
  `general` route unless a caller passes another task.
- `ai_generate_json` asks for a JSON object and parses the final message on the
  `fast_json` route by default.
- `ai_generate_structured` converts Pydantic schemas to JSON Schema and passes
  them through `--output-schema`.
- `ai_generate_korean` still runs the existing Korean medical advertising
  compliance screen after generation.
- `ai_generate_stream` yields one final chunk because `codex exec` is not a
  token streaming API.
- `ai_generate_batch` runs a local synchronous Codex batch and exposes a
  `codex_local_batch_*` handle through the existing status/results functions.
- `ai_analyze_image` maps local files, URLs, bytes, dict image payloads, and PIL
  images to Codex `--image` arguments.

## Safety posture

The default CLI run is read-only, approval-free, ephemeral, and ignores Codex
rules files. Marketing generation should not need repository reads, shell
commands, or file edits. If a future workflow needs workspace writes, create a
separate reviewed path instead of loosening this gateway globally.

## Rollback

Use one of these only during a controlled transition:

```env
MARKETING_BOT_AI_PROVIDER=codex_cli
```

or

```env
MARKETING_BOT_AI_LEGACY_FALLBACK=true
CODEX_CLI_API_KEY=...
```

## Sources checked on 2026-06-02

- Codex manual: non-interactive mode, CLI command reference, SDK, and MCP server
  sections from `https://developers.openai.com/codex/codex-manual.md`.
- Codex CLI repository: `https://github.com/openai/codex`.
- Local Codex CLI model catalog via `codex debug models` on 2026-06-02.
- Local smoke tests for `gpt-5.4`, `gpt-5.4-mini`, and
  `gpt-5.3-codex-spark` via `codex exec --model ...`.
