"""
Updated tests for OpenCode strategy (post-daemon removal).

Tests basic functionality without daemon complexity.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import Mock

import pytest

from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy


@pytest.fixture
def config():
    """Create test config."""
    config = Mock()
    config.model = "openrouter/anthropic/claude-sonnet-4-20250514"
    return config


@pytest.fixture
def strategy(config):
    """Create OpenCode strategy."""
    return OpenCodeStrategy(bin_path="/usr/local/bin/opencode", config=config)


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment for each test."""
    for key in list(os.environ.keys()):
        if key.startswith("OPENCODE") or key.startswith("NINJA"):
            monkeypatch.delenv(key, raising=False)
    return {}


class TestSimpleSubprocessMode:
    """Test simple subprocess execution (no daemon)."""

    def test_no_attach_flag(self, strategy):
        """Test --attach is never used."""
        result = strategy.build_command(prompt="test task", repo_root="/tmp/test-repo")

        assert "--attach" not in result.command
        assert "/usr/local/bin/opencode" in result.command
        assert "run" in result.command

    def test_basic_structure(self, strategy):
        """Test basic command structure."""
        result = strategy.build_command(prompt="test task", repo_root="/tmp/test-repo")

        cmd = result.command
        assert cmd[0] == "/usr/local/bin/opencode"
        assert cmd[1] == "run"
        assert "--model" in cmd
        assert "test task" in cmd[-1]

    def test_noninteractive_flags_enable_file_writes(self, strategy):
        """Non-interactive OpenCode runs must emit JSON events and allow write tools."""
        result = strategy.build_command(prompt="test task", repo_root="/tmp/test-repo")

        assert "--format" in result.command
        assert result.command[result.command.index("--format") + 1] == "json"
        assert "--dangerously-skip-permissions" in result.command

    def test_working_directory(self, strategy):
        """Test working directory is set correctly."""
        result = strategy.build_command(prompt="test", repo_root="/tmp/test-repo")

        assert result.working_dir == Path("/tmp/test-repo")


class TestModelConfiguration:
    """Test model configuration."""

    def test_uses_configured_model(self, strategy):
        """Test default model from config."""
        result = strategy.build_command(prompt="test", repo_root="/tmp/test")

        assert "openrouter/anthropic/claude-sonnet-4-20250514" in result.command

    def test_model_override(self, strategy):
        """Test model can be overridden."""
        result = strategy.build_command(
            prompt="test", repo_root="/tmp/test", model="google/gemini-2.0-flash-exp"
        )

        assert "google/gemini-2.0-flash-exp" in result.command
        assert "openrouter/anthropic/claude-sonnet-4-20250514" not in result.command


class TestSessionSupport:
    """Test explicit session support."""

    def test_session_id(self, strategy):
        """Test session ID is added when provided."""
        result = strategy.build_command(prompt="test", repo_root="/tmp/test", session_id="abc123")

        assert "--session" in result.command
        idx = result.command.index("--session")
        assert result.command[idx + 1] == "abc123"

    def test_continue_last(self, strategy):
        """Test continue flag."""
        result = strategy.build_command(prompt="test", repo_root="/tmp/test", continue_last=True)

        assert "--continue" in result.command


class TestFileContext:
    """Test file context handling."""

    def test_file_paths_in_prompt(self, strategy):
        """Test file paths are mentioned in prompt."""
        result = strategy.build_command(
            prompt="fix bug",
            repo_root="/tmp/test",
            file_paths=["src/main.py", "tests/test_main.py"],
        )

        prompt = result.command[-1]
        assert "src/main.py" in prompt
        assert "tests/test_main.py" in prompt
        assert "Focus on these files:" in prompt


class TestParseOutput:
    """Test output parsing (JSON event stream + retry handling)."""

    def test_json_edit_tool_paths_detected(self, strategy):
        """Real edit/write tool calls in --format json must count as changes."""
        stdout = "\n".join(
            [
                '{"type":"tool_use","timestamp":1,"sessionID":"s1","part":{"type":"tool","tool":"read",'
                '"callID":"c1","state":{"status":"completed","input":{"filePath":"/repo/readme.md"}}}}',
                '{"type":"tool_use","timestamp":2,"sessionID":"s1","part":{"type":"tool","tool":"edit",'
                '"callID":"c2","state":{"status":"completed","input":{"filePath":"/repo/src/user.py"}}}}',
                '{"type":"tool_use","timestamp":3,"sessionID":"s1","part":{"type":"tool","tool":"write",'
                '"callID":"c3","state":{"status":"completed","input":{"filePath":"/repo/src/new.py"}}}}',
            ]
        )

        parsed = strategy.parse_output(stdout, "", 0)

        assert parsed.success is True
        assert "/repo/src/user.py" in parsed.touched_paths
        assert "/repo/src/new.py" in parsed.touched_paths
        assert not any("readme.md" in p for p in parsed.touched_paths)

    def test_json_failed_edit_ignored(self, strategy):
        """Edit tool calls that errored must not count as modifications."""
        stdout = (
            '{"type":"tool_use","timestamp":1,"sessionID":"s1","part":{"type":"tool","tool":"edit",'
            '"callID":"c1","state":{"status":"error","input":{"filePath":"/repo/src/user.py"}}}}'
        )

        parsed = strategy.parse_output(stdout, "", 0)

        # No completed edits -> treated as a retryable failure, not a success.
        assert parsed.success is False
        assert parsed.touched_paths == []
        assert parsed.retryable_error is True

    def test_no_files_modified_is_retryable(self, strategy):
        """Model answering with text (no edits) -> retryable failure."""
        stdout = (
            "I will now write the implementation to the source file and add "
            "unit tests covering the new behavior."
        )

        parsed = strategy.parse_output(stdout, "", 0)

        assert parsed.success is False
        assert parsed.retryable_error is True

    def test_touched_files_are_not_retryable(self, strategy):
        """A run that actually modified files is a real success."""
        stdout = '{"type":"tool_use","timestamp":1,"sessionID":"s1","part":{"type":"tool","tool":"edit",' \
                 '"callID":"c1","state":{"status":"completed","input":{"filePath":"/repo/src/a.py"}}}}'

        parsed = strategy.parse_output(stdout, "", 0)

        assert parsed.success is True
        assert parsed.retryable_error is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
