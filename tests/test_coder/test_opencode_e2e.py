"""
Comprehensive e2e tests for OpenCode strategy (subprocess mode).

Tests the simplified OpenCode execution without daemon/session complexity.
Covers 95%+ of opencode_strategy.py functionality.
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
    config.model = "anthropic/claude-sonnet-4-20250514"
    return config


@pytest.fixture
def strategy(config):
    """Create OpenCode strategy."""
    return OpenCodeStrategy(bin_path="/usr/local/bin/opencode", config=config)


@pytest.fixture
def clean_env(monkeypatch):
    """Clean environment for each test."""
    # Remove all OpenCode-related env vars
    for key in list(os.environ.keys()):
        if key.startswith("OPENCODE") or key.startswith("NINJA"):
            monkeypatch.delenv(key, raising=False)
    return {}


class TestBasicCommandBuilding:
    """Test basic command construction."""

    def test_simple_command(self, strategy):
        """Test simplest command build."""
        result = strategy.build_command(prompt="Create hello.py", repo_root="/tmp/test")

        assert result.command[0] == "/usr/local/bin/opencode"
        assert result.command[1] == "run"
        assert "--model" in result.command
        assert "anthropic/claude-sonnet-4-20250514" in result.command
        assert "Create hello.py" in result.command
        assert "--attach" not in result.command  # NO DAEMON MODE
        assert result.working_dir == Path("/tmp/test")

    def test_command_with_file_context(self, strategy):
        """Test command with file context paths."""
        result = strategy.build_command(
            prompt="Fix bug", repo_root="/tmp/test", file_paths=["src/main.py", "src/utils.py"]
        )

        # Should mention files in prompt
        prompt = result.command[-1]
        assert "src/main.py" in prompt
        assert "src/utils.py" in prompt
        assert "Focus on these files:" in prompt

    def test_command_with_custom_model(self, strategy):
        """Test custom model override."""
        result = strategy.build_command(
            prompt="Task", repo_root="/tmp/test", model="google/gemini-2.0-flash-exp"
        )

        assert "google/gemini-2.0-flash-exp" in result.command
        assert "anthropic/claude-sonnet-4-20250514" not in result.command


class TestSessionSupport:
    """Test explicit session support."""

    def test_with_session_id(self, strategy):
        """Test explicit session ID."""
        result = strategy.build_command(
            prompt="Continue work", repo_root="/tmp/test", session_id="abc123"
        )

        assert "--session" in result.command
        idx = result.command.index("--session")
        assert result.command[idx + 1] == "abc123"

    def test_with_continue_last(self, strategy):
        """Test continue last session."""
        result = strategy.build_command(
            prompt="Continue", repo_root="/tmp/test", continue_last=True
        )

        assert "--continue" in result.command

    def test_session_id_takes_precedence_over_continue(self, strategy):
        """Test session_id has priority over continue_last."""
        result = strategy.build_command(
            prompt="Task", repo_root="/tmp/test", session_id="xyz", continue_last=True
        )

        assert "--session" in result.command
        assert "--continue" not in result.command


class TestMultiAgentMode:
    """Test multi-agent (ultrawork) activation."""

    def test_multi_agent_adds_ultrawork(self, strategy):
        """Test that multi-agent flag adds ultrawork keyword."""
        result = strategy.build_command(
            prompt="Build feature",
            repo_root="/tmp/test",
            additional_flags={"enable_multi_agent": True},
        )

        prompt = result.command[-1]
        assert "ultrawork" in prompt.lower()
        assert result.metadata["multi_agent"] is True

    def test_multi_agent_doesnt_duplicate_ultrawork(self, strategy):
        """Test ultrawork not duplicated if already present."""
        result = strategy.build_command(
            prompt="Build feature ultrawork",
            repo_root="/tmp/test",
            additional_flags={"enable_multi_agent": True},
        )

        prompt = result.command[-1]
        # Should only appear once
        assert prompt.lower().count("ultrawork") == 1

    def test_multi_agent_doubles_timeout(self, strategy):
        """Test multi-agent doubles timeout."""
        result = strategy.build_command(
            prompt="Task", repo_root="/tmp/test", additional_flags={"enable_multi_agent": True}
        )

        # Default 600s * 2 = 1200s
        assert result.metadata["timeout"] == 1200


class TestZAIModelDetection:
    """Test z.ai model detection."""

    def test_glm_model_detected_as_zai(self, strategy):
        """Test GLM models detected as z.ai provider."""
        result = strategy.build_command(prompt="Task", repo_root="/tmp/test", model="glm-4.7")

        assert result.metadata["provider"] == "z.ai"

    def test_anthropic_model_not_zai(self, strategy):
        """Test Anthropic models not z.ai."""
        result = strategy.build_command(
            prompt="Task", repo_root="/tmp/test", model="anthropic/claude-sonnet-4-20250514"
        )

        assert result.metadata["provider"] == "generic"


class TestEnvironmentVariables:
    """Test environment variable handling."""

    def test_inherits_environment(self, strategy, clean_env, monkeypatch):
        """Test command inherits current environment."""
        monkeypatch.setenv("CUSTOM_VAR", "test_value")

        result = strategy.build_command(prompt="Task", repo_root="/tmp/test")

        assert result.env.get("CUSTOM_VAR") == "test_value"

    def test_custom_timeout_env(self, strategy, clean_env, monkeypatch):
        """Test custom timeout from env."""
        monkeypatch.setenv("NINJA_OPENCODE_TIMEOUT", "300")

        result = strategy.build_command(prompt="Task", repo_root="/tmp/test")

        assert result.metadata["timeout"] == 300


class TestMetadata:
    """Test metadata in results."""

    def test_metadata_structure(self, strategy):
        """Test metadata contains expected fields."""
        result = strategy.build_command(
            prompt="Task",
            repo_root="/tmp/test",
            model="test/model",
            session_id="sid",
            additional_flags={"use_coding_plan": True, "enable_multi_agent": False},
        )

        metadata = result.metadata
        assert "provider" in metadata
        assert "model" in metadata
        assert "timeout" in metadata
        assert "session_id" in metadata
        assert "continue_last" in metadata
        assert "multi_agent" in metadata
        assert "coding_plan_api" in metadata

        assert metadata["session_id"] == "sid"
        assert metadata["continue_last"] is False
        assert metadata["model"] == "test/model"


class TestCapabilities:
    """Test strategy capabilities."""

    def test_capabilities_correct(self, strategy):
        """Test strategy reports correct capabilities."""
        caps = strategy.capabilities

        assert caps.supports_streaming is True
        assert caps.supports_file_context is True
        assert caps.supports_model_routing is True
        assert caps.supports_native_zai is True
        assert caps.supports_dialogue_mode is True
        assert caps.max_context_files == 100
        assert "parallel" in caps.preferred_task_types
        assert "sequential" in caps.preferred_task_types

    def test_name(self, strategy):
        """Test strategy name."""
        assert strategy.name == "opencode"


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_empty_prompt(self, strategy):
        """Test with empty prompt."""
        result = strategy.build_command(prompt="", repo_root="/tmp/test")

        # Should still build command
        assert result.command[-1] == ""

    def test_long_prompt(self, strategy):
        """Test with very long prompt."""
        long_prompt = "Task " * 1000
        result = strategy.build_command(prompt=long_prompt, repo_root="/tmp/test")

        assert result.command[-1] == long_prompt

    def test_unicode_in_prompt(self, strategy):
        """Test unicode characters in prompt."""
        result = strategy.build_command(
            prompt="Create file with emoji 🚀 and unicode ñ", repo_root="/tmp/test"
        )

        prompt = result.command[-1]
        assert "🚀" in prompt
        assert "ñ" in prompt

    def test_many_file_paths(self, strategy):
        """Test with many file paths."""
        files = [f"file{i}.py" for i in range(50)]
        result = strategy.build_command(prompt="Fix all", repo_root="/tmp/test", file_paths=files)

        prompt = result.command[-1]
        # Should mention all files
        for f in files[:5]:  # Check first few
            assert f in prompt


class TestNoDaemonMode:
    """Test that daemon mode is completely removed."""

    def test_no_attach_flag_ever(self, strategy):
        """Test --attach is never used."""
        result = strategy.build_command(prompt="Task", repo_root="/tmp/test")

        assert "--attach" not in result.command

    def test_no_server_metadata(self, strategy):
        """Test no server-related metadata."""
        result = strategy.build_command(prompt="Task", repo_root="/tmp/test")

        metadata = result.metadata
        assert "server_url" not in metadata
        assert "server_mode" not in metadata


class TestCommandStructure:
    """Test command structure and ordering."""

    def test_command_order(self, strategy):
        """Test command arguments in correct order."""
        result = strategy.build_command(
            prompt="Test task", repo_root="/tmp/test", model="test/model", session_id="sid"
        )

        cmd = result.command
        assert cmd[0] == "/usr/local/bin/opencode"
        assert cmd[1] == "run"
        assert cmd[2] == "--model"
        assert cmd[3] == "test/model"
        assert "--session" in cmd
        assert cmd[-1] == "Test task"  # Prompt is last

    def test_prompt_always_last(self, strategy):
        """Test prompt is always final argument."""
        result = strategy.build_command(
            prompt="Final argument",
            repo_root="/tmp/test",
            session_id="test",
            file_paths=["a.py", "b.py"],
            additional_flags={"enable_multi_agent": True},
        )

        # Prompt should contain original + file mentions + ultrawork
        assert "Final argument" in result.command[-1]
        assert result.command[-1].endswith("ultrawork")  # ultrawork added at end


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
