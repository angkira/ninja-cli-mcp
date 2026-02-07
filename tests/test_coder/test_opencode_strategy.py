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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
