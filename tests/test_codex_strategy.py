"""Tests for Codex CLI strategy (OpenAI Codex, host-auth)."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies import CLIStrategyRegistry, check_codex_auth
from ninja_coder.strategies.base import CLICommandResult
from ninja_coder.strategies.codex_strategy import CodexStrategy


def _config(**kwargs) -> NinjaConfig:
    defaults = {"bin_path": "codex", "model": "gpt-5.6-luna", "openai_api_key": ""}
    defaults.update(kwargs)
    return NinjaConfig(**defaults)


# --- build_command ---


def test_build_command_flags_order():
    strategy = CodexStrategy("/Users/test/.local/bin/codex", _config())
    result = strategy.build_command(prompt="Fix bug", repo_root="/repo")

    assert isinstance(result, CLICommandResult)
    cmd = result.command
    assert cmd[0].endswith("codex")
    assert cmd[1:9] == [
        "exec",
        "-m",
        "gpt-5.6-luna",
        "-s",
        "workspace-write",
        "-C",
        "/repo",
        "--skip-git-repo-check",
    ]
    assert "--json" in cmd
    assert cmd[-1] == "Fix bug"


def test_build_command_default_model():
    strategy = CodexStrategy("codex", _config(model=""))
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    idx = result.command.index("-m")
    assert result.command[idx + 1] == "gpt-5.6-luna"


def test_build_command_sandbox_override():
    strategy = CodexStrategy("codex", _config())
    result = strategy.build_command(
        prompt="Hi", repo_root="/repo", additional_flags={"sandbox": "read-only"}
    )
    idx = result.command.index("-s")
    assert result.command[idx + 1] == "read-only"


def test_build_command_file_paths_folded_into_prompt():
    strategy = CodexStrategy("codex", _config())
    result = strategy.build_command(
        prompt="Update auth", repo_root="/repo", file_paths=["src/auth.py"]
    )
    assert result.command[-1] == "Update auth\n\nFocus on these files: src/auth.py"


def test_build_command_env_inherit_no_keys():
    strategy = CodexStrategy("codex", _config())
    with patch.dict(os.environ, {"CODEX_API_KEY": "must-not-leak"}, clear=False):
        result = strategy.build_command(prompt="Hi", repo_root="/repo")
    # Host-auth: env inherited as-is, no key injection by the strategy
    assert result.env["CODEX_API_KEY"] == "must-not-leak"
    assert result.metadata["timeout"] == int(os.environ.get("NINJA_CODEX_TIMEOUT", "600"))


# --- check_codex_auth ---


def test_check_codex_auth_no_binary():
    with patch("ninja_coder.strategies.codex_strategy.shutil.which", return_value=None):
        assert check_codex_auth() is False


def test_check_codex_auth_help_ok():
    with (
        patch("ninja_coder.strategies.codex_strategy.shutil.which", return_value="/bin/codex"),
        patch("ninja_coder.strategies.codex_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=0)
        assert check_codex_auth() is True
        args = run.call_args[0][0]
        assert args == ["/bin/codex", "--help"]


def test_check_codex_auth_help_fails():
    with (
        patch("ninja_coder.strategies.codex_strategy.shutil.which", return_value="/bin/codex"),
        patch("ninja_coder.strategies.codex_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=1)
        assert check_codex_auth() is False


# --- registry ---


def test_registry_resolves_codex():
    strategy = CLIStrategyRegistry.get_strategy("/Users/t/.local/bin/codex", _config())
    assert isinstance(strategy, CodexStrategy)
    assert strategy.name == "codex"
    assert "codex" in CLIStrategyRegistry.list_strategies()


# --- parse_output ---


def test_parse_output_auth_detect():
    strategy = CodexStrategy("codex", _config())
    parsed = strategy.parse_output("", "Error: not authenticated", 1)
    assert parsed.success is False
    assert "run 'codex login'" in parsed.notes.lower()


def test_parse_output_login_required():
    strategy = CodexStrategy("codex", _config())
    parsed = strategy.parse_output("", "login required", 1)
    assert parsed.success is False
    assert "Authentication error" in parsed.summary


def test_parse_output_rate_limit_retryable():
    strategy = CodexStrategy("codex", _config())
    parsed = strategy.parse_output("", "rate limit exceeded", 1)
    assert parsed.retryable_error is True
    assert strategy.should_retry("", "rate limit exceeded", 1) is True


def test_parse_output_success():
    strategy = CodexStrategy("codex", _config())
    parsed = strategy.parse_output("Done", "", 0)
    assert parsed.success is True


def test_parse_output_extracts_file_change_events():
    strategy = CodexStrategy("codex", _config())
    events = [
        {"type": "thread.started", "thread_id": "t-1"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "working"}},
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": "/repo/src/a.py", "kind": "add"}],
            },
        },
        {
            "type": "item.completed",
            "item": {
                "type": "file_change",
                "changes": [{"path": "/repo/src/b.py", "kind": "edit"}],
            },
        },
    ]
    stdout = "\n".join(json.dumps(e) for e in events)
    parsed = strategy.parse_output(stdout, "", 0)
    assert parsed.success is True
    assert parsed.touched_paths == ["/repo/src/a.py", "/repo/src/b.py"]
    assert "Modified 2 file(s)" in parsed.summary


def test_parse_output_ignores_invalid_json_lines():
    strategy = CodexStrategy("codex", _config())
    parsed = strategy.parse_output("not-json\n{broken", "", 0)
    assert parsed.success is True


# --- get_timeout ---


def test_get_timeout_respects_task_type():
    strategy = CodexStrategy("codex", _config())
    full = strategy.get_timeout("sequential")
    quick = strategy.get_timeout("quick")
    assert quick == full // 2


# --- multi-agent ---


def test_build_command_with_multi_agent_appends_subagent_directive():
    strategy = CodexStrategy("codex", _config())
    result = strategy.build_command_with_multi_agent(
        prompt="Refactor auth", repo_root="/repo", agents=["explorer", "reviewer"]
    )
    assert "subagents" in result.command[-1].lower()
    assert "explorer" in result.command[-1]
    assert result.metadata["multi_agent"] is True
