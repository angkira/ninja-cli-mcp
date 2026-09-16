"""Tests for Junie CLI strategy (JetBrains Junie, host-auth)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies import CLIStrategyRegistry, check_junie_auth
from ninja_coder.strategies.base import CLICommandResult
from ninja_coder.strategies.junie_strategy import JunieStrategy
from ninja_common.operator_models import resolve_junie_effort


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


# --- model normalization ---


@pytest.fixture(autouse=True)
def _clean_junie_effort_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Effort env vars must not leak between tests (or from the dev shell)."""
    for key in (
        "NINJA_JUNIE_EFFORT",
        "NINJA_JUNIE_EFFORT_QUICK",
        "NINJA_JUNIE_EFFORT_SEQUENTIAL",
        "NINJA_JUNIE_EFFORT_PARALLEL",
    ):
        monkeypatch.delenv(key, raising=False)


def _model_flag(result: CLICommandResult) -> str:
    return result.command[result.command.index("--model") + 1]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("deepseek-v4-flash", "deepseek-v4-flash"),
        ("junie/deepseek-v4-flash", "deepseek-v4-flash"),
        ("openai/gpt-5.6-luna", "gpt-5.6-luna"),
        ("gpt-5.6-luna", "gpt-5.6-luna"),
        ("gemini-3.8-flash", "gemini-3.8-flash"),
        ("grok-4.6", "grok-4.6"),
        # Legacy aliases resolve to versioned ids / pass through.
        ("grok", "grok-4.6"),
        ("gemini-flash", "gemini-3.8-flash"),
        ("gpt", "gpt-5.6-luna"),
        ("sonnet", "sonnet"),
        ("opus", "opus"),
    ],
)
def test_build_command_normalizes_model(raw: str, expected: str) -> None:
    strategy = JunieStrategy("junie", _config(model=""))
    result = strategy.build_command(prompt="Hi", repo_root="/repo", model=raw)
    assert _model_flag(result) == expected


def test_build_command_config_model_with_prefix_normalized() -> None:
    strategy = JunieStrategy("junie", _config(model="junie/grok-4.6"))
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    assert _model_flag(result) == "grok-4.6"


def test_build_command_unknown_model_raises_loudly() -> None:
    strategy = JunieStrategy("junie", _config(model=""))
    with pytest.raises(ValueError, match="Unknown Junie model"):
        strategy.build_command(prompt="Hi", repo_root="/repo", model="openrouter/x/y")


def test_build_command_unknown_model_error_lists_valid() -> None:
    strategy = JunieStrategy("junie", _config(model=""))
    with pytest.raises(ValueError, match="deepseek-v4-flash"):
        strategy.build_command(prompt="Hi", repo_root="/repo", model="nope")


# --- effort flag ---


def test_build_command_no_effort_by_default() -> None:
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    assert "--effort" not in result.command
    assert result.metadata["effort"] is None


def test_build_command_effort_per_call_override() -> None:
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(
        prompt="Hi", repo_root="/repo", additional_flags={"effort": "high"}
    )
    assert result.command[result.command.index("--effort") + 1] == "high"
    assert result.metadata["effort"] == "high"


def test_build_command_effort_from_global_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "low")
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    assert result.command[result.command.index("--effort") + 1] == "low"


def test_build_command_effort_per_call_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "low")
    strategy = JunieStrategy("junie", _config())
    result = strategy.build_command(
        prompt="Hi", repo_root="/repo", additional_flags={"effort": "medium"}
    )
    assert result.command[result.command.index("--effort") + 1] == "medium"


def test_build_command_invalid_effort_raises() -> None:
    strategy = JunieStrategy("junie", _config())
    with pytest.raises(ValueError, match="Invalid Junie effort"):
        strategy.build_command(prompt="Hi", repo_root="/repo", additional_flags={"effort": "ultra"})


def test_resolve_junie_effort_task_type_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "low")
    monkeypatch.setenv("NINJA_JUNIE_EFFORT_SEQUENTIAL", "high")
    assert resolve_junie_effort(task_type="sequential") == "high"
    assert resolve_junie_effort(task_type="sequential_plan") == "high"
    assert resolve_junie_effort(task_type="quick") == "low"
    assert resolve_junie_effort(explicit="medium", task_type="sequential") == "medium"
    assert resolve_junie_effort() == "low"


def test_resolve_junie_effort_unset_returns_none() -> None:
    assert resolve_junie_effort() is None
    assert resolve_junie_effort(task_type="quick") is None


def test_resolve_junie_effort_invalid_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "turbo")
    with pytest.raises(ValueError, match="Invalid Junie effort"):
        resolve_junie_effort()


# --- driver passthrough (effort by task_type, junie only) ---


def _junie_driver(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """NinjaDriver wired to the Junie strategy (isolated cache dir)."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )
    from ninja_coder.driver import NinjaDriver

    config = NinjaConfig(bin_path="junie", model="deepseek-v4-flash", openai_api_key="")
    return NinjaDriver(config)


def test_driver_attaches_junie_effort_by_task_type(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "low")
    monkeypatch.setenv("NINJA_JUNIE_EFFORT_SEQUENTIAL", "high")
    driver = _junie_driver(tmp_path, monkeypatch)
    assert driver._strategy.name == "junie"
    assert driver._additional_flags_for_task(False, "quick") == {"effort": "low"}
    assert driver._additional_flags_for_task(False, "sequential") == {"effort": "high"}
    assert driver._additional_flags_for_task(True, "quick") == {
        "use_coding_plan": True,
        "effort": "low",
    }


def test_driver_omits_effort_when_unset(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _junie_driver(tmp_path, monkeypatch)
    assert driver._additional_flags_for_task(False, "quick") is None
    assert driver._additional_flags_for_task(True, "quick") == {"use_coding_plan": True}


def test_driver_no_effort_for_other_operators(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NINJA_JUNIE_EFFORT", "low")
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )
    from ninja_coder.driver import NinjaDriver

    config = NinjaConfig(bin_path="aider", model="x/y", openai_api_key="")
    driver = NinjaDriver(config)
    assert driver._additional_flags_for_task(False, "quick") is None
