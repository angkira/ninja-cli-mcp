"""Tests for Pi CLI strategy (pi.dev coding agent)."""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies import CLIStrategyRegistry, check_pi_auth
from ninja_coder.strategies.base import CLICommandResult
from ninja_coder.strategies.pi_strategy import DEFAULT_PI_MODEL, PiStrategy
from ninja_common.operator_models import (
    normalize_pi_model,
    operator_from_bin,
    resolve_pi_thinking,
)


def _config(**kwargs) -> NinjaConfig:
    defaults = {"bin_path": "pi", "model": DEFAULT_PI_MODEL, "openai_api_key": ""}
    defaults.update(kwargs)
    return NinjaConfig(**defaults)


# --- build_command ---


def test_build_command_flags_order():
    strategy = PiStrategy("/usr/local/bin/pi", _config())
    result = strategy.build_command(prompt="Fix bug", repo_root="/repo")

    assert isinstance(result, CLICommandResult)
    cmd = result.command
    assert cmd[0] == "/usr/local/bin/pi"
    assert cmd[1:4] == ["-p", "--mode", "json"]
    assert "--model" in cmd
    idx = cmd.index("--model")
    assert cmd[idx + 1] == DEFAULT_PI_MODEL
    assert cmd[-1] == "Fix bug"


def test_build_command_default_model():
    strategy = PiStrategy("pi", _config(model=""))
    result = strategy.build_command(prompt="Hi", repo_root="/repo")
    idx = result.command.index("--model")
    assert result.command[idx + 1] == DEFAULT_PI_MODEL


def test_build_command_file_paths_folded_into_prompt():
    strategy = PiStrategy("pi", _config())
    result = strategy.build_command(
        prompt="Update auth", repo_root="/repo", file_paths=["src/auth.py"]
    )
    assert result.command[-1] == "Update auth\n\nFocus on these files: src/auth.py"


def test_build_command_thinking_override():
    strategy = PiStrategy("pi", _config())
    result = strategy.build_command(
        prompt="Solve math",
        repo_root="/repo",
        additional_flags={"thinking": "high"},
    )
    assert "--thinking" in result.command
    idx = result.command.index("--thinking")
    assert result.command[idx + 1] == "high"
    assert result.metadata["thinking"] == "high"


def test_build_command_thinking_from_env():
    strategy = PiStrategy("pi", _config())
    with patch.dict(os.environ, {"NINJA_PI_THINKING": "low"}, clear=False):
        result = strategy.build_command(prompt="Solve math", repo_root="/repo")
    assert "--thinking" in result.command
    idx = result.command.index("--thinking")
    assert result.command[idx + 1] == "low"


def test_build_command_env_inherit_no_keys():
    strategy = PiStrategy("pi", _config())
    with patch.dict(os.environ, {"CUSTOM_ENV_TEST": "test-val"}, clear=False):
        result = strategy.build_command(prompt="Hi", repo_root="/repo")
    assert result.env["CUSTOM_ENV_TEST"] == "test-val"
    assert result.metadata["timeout"] == int(os.environ.get("NINJA_PI_TIMEOUT", "600"))


# --- check_pi_auth ---


def test_check_pi_auth_no_binary():
    with patch("ninja_coder.strategies.pi_strategy.shutil.which", return_value=None):
        assert check_pi_auth() is False


def test_check_pi_auth_help_ok():
    with (
        patch("ninja_coder.strategies.pi_strategy.shutil.which", return_value="/bin/pi"),
        patch("ninja_coder.strategies.pi_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=0)
        assert check_pi_auth() is True
        run.assert_called_once_with(
            ["/bin/pi", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )


def test_check_pi_auth_help_fails():
    with (
        patch("ninja_coder.strategies.pi_strategy.shutil.which", return_value="/bin/pi"),
        patch("ninja_coder.strategies.pi_strategy.subprocess.run") as run,
    ):
        run.return_value = MagicMock(returncode=1)
        assert check_pi_auth() is False


# --- registry resolution ---


def test_registry_resolves_pi():
    strategy = CLIStrategyRegistry.get_strategy("/path/to/pi", _config())
    assert isinstance(strategy, PiStrategy)
    assert strategy.name == "pi"


def test_operator_from_bin_safely_matches_pi():
    assert operator_from_bin("pi") == "pi"
    assert operator_from_bin("/usr/local/bin/pi") == "pi"
    assert operator_from_bin("pi-agent") == "pi"
    assert operator_from_bin("python") != "pi"
    assert operator_from_bin("pip") != "pi"


# --- parse_output ---


def test_parse_output_auth_detect():
    strategy = PiStrategy("pi", _config())
    parsed = strategy.parse_output(
        stdout="",
        stderr="AuthenticationError: not authenticated or login required",
        exit_code=1,
    )
    assert parsed.success is False
    assert "authentication" in parsed.summary.lower() or "auth" in parsed.notes.lower()


def test_parse_output_rate_limit_retryable():
    strategy = PiStrategy("pi", _config())
    parsed = strategy.parse_output(
        stdout="Rate limit exceeded. HTTP 429 Too Many Requests",
        stderr="",
        exit_code=1,
    )
    assert parsed.success is False
    assert parsed.retryable_error is True
    assert strategy.should_retry(
        stdout="Rate limit exceeded. HTTP 429 Too Many Requests", stderr="", exit_code=1
    )


def test_parse_output_success():
    strategy = PiStrategy("pi", _config())
    stdout = json.dumps(
        {
            "type": "tool_execution_end",
            "toolName": "write",
            "args": {"path": "src/main.py"},
            "result": {"content": [{"type": "text", "text": "Successfully wrote to src/main.py"}]},
            "isError": False,
        }
    )
    parsed = strategy.parse_output(stdout=stdout, stderr="", exit_code=0)
    assert parsed.success is True
    assert "src/main.py" in parsed.touched_paths
    assert "1 file" in parsed.summary


def test_parse_output_extracts_edit_and_write_events():
    strategy = PiStrategy("pi", _config())
    lines = [
        json.dumps({"type": "turn_start"}),
        json.dumps(
            {
                "type": "tool_execution_start",
                "toolName": "write",
                "args": {"path": "file1.txt", "content": "abc"},
            }
        ),
        json.dumps(
            {
                "type": "tool_execution_end",
                "toolName": "write",
                "args": {"path": "file1.txt"},
                "isError": False,
            }
        ),
        json.dumps(
            {
                "type": "tool_execution_start",
                "toolName": "edit",
                "args": {"path": "file2.py", "edits": []},
            }
        ),
        json.dumps(
            {
                "type": "tool_execution_end",
                "toolName": "edit",
                "args": {"path": "file2.py"},
                "isError": False,
            }
        ),
    ]
    stdout = "\n".join(lines)
    parsed = strategy.parse_output(stdout=stdout, stderr="", exit_code=0)
    assert parsed.success is True
    assert parsed.touched_paths == ["file1.txt", "file2.py"]


def test_parse_output_regex_fallback():
    strategy = PiStrategy("pi", _config())
    stdout = "I have updated src/calc.py and edited tests/test_calc.py for you."
    parsed = strategy.parse_output(stdout=stdout, stderr="", exit_code=0)
    assert parsed.success is True
    assert "src/calc.py" in parsed.touched_paths or "tests/test_calc.py" in parsed.touched_paths


def test_get_timeout_respects_task_type():
    strategy = PiStrategy("pi", _config())
    with patch.dict(os.environ, {"NINJA_PI_TIMEOUT_QUICK": "120"}, clear=False):
        assert strategy.get_timeout("quick") == 120
        assert strategy.get_timeout("quick_plan") == 120
        assert strategy.get_timeout("sequential") == 600


# --- thinking resolution ---


def test_resolve_pi_thinking_precedence():
    # Explicit beats env
    with patch.dict(os.environ, {"NINJA_PI_THINKING": "low"}, clear=False):
        assert resolve_pi_thinking(explicit="high") == "high"

    # Task type env beats global env
    with patch.dict(
        os.environ,
        {"NINJA_PI_THINKING": "low", "NINJA_PI_THINKING_QUICK": "minimal"},
        clear=False,
    ):
        assert resolve_pi_thinking(task_type="quick") == "minimal"
        assert resolve_pi_thinking(task_type="sequential") == "low"

    # Unset returns None
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_pi_thinking() is None


def test_resolve_pi_thinking_invalid_raises():
    with pytest.raises(ValueError, match="Invalid Pi thinking level"):
        resolve_pi_thinking(explicit="ultra")


def test_normalize_pi_model():
    assert normalize_pi_model("") == ""
    assert normalize_pi_model("pi/deepseek-v4.1-flash") == "deepseek-v4.1-flash"
    assert normalize_pi_model("deepseek-v4.1-flash") == "deepseek-v4.1-flash"


# --- driver passthrough (thinking by task_type, pi only) ---


def _pi_driver(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """NinjaDriver wired to the Pi strategy (isolated cache dir)."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )
    from ninja_coder.driver import NinjaDriver

    config = NinjaConfig(bin_path="pi", model="deepseek-v4.1-flash", openai_api_key="")
    return NinjaDriver(config)


def test_driver_attaches_pi_thinking_by_task_type(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NINJA_PI_THINKING", "low")
    monkeypatch.setenv("NINJA_PI_THINKING_SEQUENTIAL", "high")
    driver = _pi_driver(tmp_path, monkeypatch)
    assert driver._strategy.name == "pi"
    assert driver._additional_flags_for_task(False, "quick") == {"thinking": "low"}
    assert driver._additional_flags_for_task(False, "sequential") == {"thinking": "high"}
    assert driver._additional_flags_for_task(True, "quick") == {
        "use_coding_plan": True,
        "thinking": "low",
    }


def test_driver_omits_thinking_when_unset(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    driver = _pi_driver(tmp_path, monkeypatch)
    assert driver._additional_flags_for_task(False, "quick") is None
    assert driver._additional_flags_for_task(True, "quick") == {"use_coding_plan": True}
