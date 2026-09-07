"""Tests for Junie CLI strategy (JetBrains Junie, host-auth)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies import CLIStrategyRegistry, check_junie_auth
from ninja_coder.strategies.base import CLICommandResult
from ninja_coder.strategies.junie_strategy import JunieStrategy


def _config(**kwargs) -> NinjaConfig:
    defaults = {"bin_path": "junie", "model": "deepseek-v4-flash", "openai_api_key": ""}
    defaults.update(kwargs)
    return NinjaConfig(**defaults)


# --- build_command ---


def test_build_command_flags_order():
    strategy = JunieStrategy("/Users/test/.local/bin/junie", _config())
    result = strategy.build_command(prompt="Fix bug", repo_root="/repo")

    assert isinstance(result, CLICommandResult)
    cmd = result.command
    assert cmd[0].endswith("junie")
    assert cmd[1:8] == [
        "--model",
        "deepseek-v4-flash",
        "--output-format",
        "text",
        "-p",
        "/repo",
        "--skip-update-check",
    ]
    assert cmd[-2:] == ["--task", "Fix bug"]
    assert "--auth" not in cmd


def test_build_command_default_model():
    strategy = JunieStrategy("junie", _config(model=""))
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    idx = result.command.index("--model")
    assert result.command[idx + 1] == "deepseek-v4-flash"


def test_build_command_session_continuity():
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(
        prompt="Hi", repo_root="/repo", session_id="s-1", continue_last=True
    )
    assert "--session-id" in result.command
    assert result.command[result.command.index("--session-id") + 1] == "s-1"
    assert "--resume" in result.command


def test_build_command_file_paths_folded_into_prompt():
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(
        prompt="Update auth", repo_root="/repo", file_paths=["src/auth.py"]
    )
    assert result.command[-1] == "Update auth\n\nFocus on these files: src/auth.py"


def test_build_command_env_inherit_no_keys():
    strategy = JunieStrategy("junie", _config())
    with patch.dict(os.environ, {"JUNIE_API_KEY": "must-not-leak"}, clear=False):
        result = strategy.build_command(prompt="Hi", repo_root="/repo")
    # Host-auth: env inherited as-is, no key injection by the strategy
    assert result.env["JUNIE_API_KEY"] == "must-not-leak"
    assert "--auth" not in result.command
    assert result.metadata["timeout"] == int(os.environ.get("NINJA_JUNIE_TIMEOUT", "600"))


# --- check_junie_auth ---


def test_check_junie_auth_no_binary():
    with patch("ninja_coder.strategies.junie_strategy.shutil.which", return_value=None):
        assert check_junie_auth() is False


def test_check_junie_auth_help_ok():
    with (
        patch("ninja_coder.strategies.junie_strategy.shutil.which", return_value="/bin/junie"),
        patch("ninja_coder.strategies.junie_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=0)
        assert check_junie_auth() is True
        args = run.call_args[0][0]
        assert args == ["/bin/junie", "--help"]


def test_check_junie_auth_help_fails():
    with (
        patch("ninja_coder.strategies.junie_strategy.shutil.which", return_value="/bin/junie"),
        patch("ninja_coder.strategies.junie_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=1)
        assert check_junie_auth() is False


# --- registry ---


def test_registry_resolves_junie():
    strategy = CLIStrategyRegistry.get_strategy("/Users/t/.local/bin/junie", _config())
    assert isinstance(strategy, JunieStrategy)
    assert strategy.name == "junie"
    assert "junie" in CLIStrategyRegistry.list_strategies()


# --- parse_output ---


def test_parse_output_auth_detect():
    strategy = JunieStrategy("junie", _config())
    parsed = strategy.parse_output("", "Error: not authenticated", 1)
    assert parsed.success is False
    assert "run 'junie' interactively" in parsed.notes.lower()


def test_parse_output_junie_api_key_marker():
    strategy = JunieStrategy("junie", _config())
    parsed = strategy.parse_output("", "missing junie_api_key", 1)
    assert parsed.success is False
    assert "Authentication error" in parsed.summary


def test_parse_output_rate_limit_retryable():
    strategy = JunieStrategy("junie", _config())
    parsed = strategy.parse_output("", "rate limit exceeded", 1)
    assert parsed.retryable_error is True
    assert strategy.should_retry("", "rate limit exceeded", 1) is True


def test_parse_output_success():
    strategy = JunieStrategy("junie", _config())
    parsed = strategy.parse_output("Done", "", 0)
    assert parsed.success is True
