import subprocess
from pathlib import Path

from marketing_bot_web.backend.services import ai_client
from marketing_bot_web.backend.services import codex_cli_client as codex


def test_codex_exec_uses_stdin_prompt_and_final_output_file(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setenv("CODEX_CLI_CD", str(tmp_path))
    monkeypatch.setenv("CODEX_CLI_BIN", "codex")
    monkeypatch.setenv("CODEX_CLI_BYPASS_APPROVALS_AND_SANDBOX", "true")
    monkeypatch.setenv("CODEX_CLI_EPHEMERAL", "true")
    monkeypatch.setenv("CODEX_CLI_IGNORE_RULES", "true")
    monkeypatch.setattr(codex.shutil, "which", lambda value: value)

    def fake_run(args, **kwargs):
        calls["args"] = args
        calls["input"] = kwargs["input"]
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text("codex-ok", encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(codex.subprocess, "run", fake_run)

    result = codex.generate_text("Return codex-ok", system_prompt="System")

    assert result.text == "codex-ok"
    assert calls["args"][:2] == ["codex", "exec"]
    assert calls["args"][-1] == "-"
    assert "--dangerously-bypass-approvals-and-sandbox" in calls["args"]
    assert "--sandbox" not in calls["args"]
    assert 'approval_policy="never"' not in calls["args"]
    assert "--model" in calls["args"]
    assert "gpt-5.4" in calls["args"]
    assert 'model_reasoning_effort="medium"' in calls["args"]
    assert 'model_verbosity="medium"' in calls["args"]
    assert "--ephemeral" in calls["args"]
    assert "--ignore-rules" in calls["args"]
    assert "System" in calls["input"]
    assert "Return codex-ok" in calls["input"]


def test_task_model_routing_uses_fast_json_defaults(monkeypatch, tmp_path):
    calls = {}

    monkeypatch.setenv("CODEX_CLI_CD", str(tmp_path))
    monkeypatch.setattr(codex.shutil, "which", lambda value: value)

    def fake_run(args, **kwargs):
        calls["args"] = args
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text('{"ok": true}', encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(codex.subprocess, "run", fake_run)

    result = codex.generate_json("Return ok")

    assert result == {"ok": True}
    assert calls["args"][calls["args"].index("--model") + 1] == "gpt-5.4-mini"
    assert 'model_reasoning_effort="low"' in calls["args"]
    assert 'model_verbosity="low"' in calls["args"]


def test_task_model_override_and_fallback_to_cli_default(monkeypatch, tmp_path):
    calls = []

    monkeypatch.setenv("CODEX_CLI_CD", str(tmp_path))
    monkeypatch.setenv("CODEX_CLI_MODEL_FAST_JSON", "blocked-model")
    monkeypatch.delenv("CODEX_CLI_MODEL", raising=False)
    monkeypatch.setattr(codex.shutil, "which", lambda value: value)

    def fake_run(args, **kwargs):
        calls.append(args)
        if "--model" in args and args[args.index("--model") + 1] == "blocked-model":
            return subprocess.CompletedProcess(args, 2, stdout="", stderr="model unavailable")
        output_path = Path(args[args.index("--output-last-message") + 1])
        output_path.write_text('{"ok": true}', encoding="utf-8")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(codex.subprocess, "run", fake_run)

    result = codex.generate_json("Return ok")

    assert result == {"ok": True}
    assert len(calls) == 2
    assert calls[0][calls[0].index("--model") + 1] == "blocked-model"
    assert "--model" not in calls[1]


def test_codex_json_parser_accepts_markdown_fence():
    assert codex.parse_json_text('```json\n{"score": 91}\n```') == {"score": 91}


def test_ai_client_uses_codex_and_ignores_legacy_model_override(monkeypatch):
    monkeypatch.setenv("MARKETING_BOT_AI_PROVIDER", "codex")
    monkeypatch.setenv("MARKETING_BOT_ENABLE_AI_IN_TESTS", "true")
    monkeypatch.setattr(ai_client._codex_cli, "codex_available", lambda: True)

    def fake_generate_text(prompt, **kwargs):
        assert kwargs["model"] is None
        return codex.CodexCliResult(
            text="codex-text",
            model="codex-cli",
            latency_ms=12,
            stderr_tail="",
            stdout_tail="",
        )

    monkeypatch.setattr(ai_client._codex_cli, "generate_text", fake_generate_text)
    monkeypatch.setattr(ai_client._codex_cli, "record_codex_call", lambda *args, **kwargs: None)

    assert ai_client.ai_generate("hello", model="google-legacy") == "codex-text"


def test_ai_client_codex_local_batch_contract(monkeypatch):
    monkeypatch.setenv("MARKETING_BOT_AI_PROVIDER", "codex")
    monkeypatch.setenv("MARKETING_BOT_ENABLE_AI_IN_TESTS", "true")
    monkeypatch.setattr(ai_client._codex_cli, "codex_available", lambda: True)

    def fake_generate_text(prompt, **kwargs):
        return codex.CodexCliResult(
            text=f"done:{prompt}",
            model="codex-cli",
            latency_ms=1,
            stderr_tail="",
            stdout_tail="",
        )

    monkeypatch.setattr(ai_client._codex_cli, "generate_text", fake_generate_text)
    monkeypatch.setattr(ai_client._codex_cli, "record_codex_call", lambda *args, **kwargs: None)

    batch_name = ai_client.ai_generate_batch([{"prompt": "a"}, {"prompt": "b"}])

    assert batch_name and batch_name.startswith("codex_local_batch_")
    assert ai_client.ai_batch_status(batch_name) == "SUCCEEDED"
    assert ai_client.ai_batch_results(batch_name) == ["done:a", "done:b"]


def test_ai_provider_status_reports_codex(monkeypatch, tmp_path):
    monkeypatch.setenv("MARKETING_BOT_AI_PROVIDER", "codex")
    monkeypatch.setenv("MARKETING_BOT_ENABLE_AI_IN_TESTS", "true")
    monkeypatch.setenv("CODEX_CLI_CD", str(tmp_path))
    monkeypatch.setattr(codex.shutil, "which", lambda value: value)

    status = ai_client.ai_provider_status()

    assert status["provider"] == "codex_cli"
    assert status["available"] is True
    assert status["model"] == "gpt-5.4"
    assert status["task_models"]["fast_json"]["model"] == "gpt-5.4-mini"
    assert status["task_models"]["viral_comment"]["model"] == "gpt-5.5"
    assert status["task_models"]["viral_comment"]["reasoning_effort"] == "high"
    assert status["task_models"]["compliance"]["reasoning_effort"] == "high"
    assert status["task_models"]["strategy"]["reasoning_effort"] == "xhigh"
    assert status["bypass_approvals_and_sandbox"] is True
