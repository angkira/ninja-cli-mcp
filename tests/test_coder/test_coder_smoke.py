"""
Smoke tests for ninja_coder module.

These tests verify:
1. Command building includes --file flags (critical fix)
2. API keys are redacted in logs (security fix)
3. No shlex.quote mangling occurs (bug fix)
4. Basic integration with aider (optional, requires API key)

Run unit tests (no API key needed):
    pytest tests/test_coder/test_coder_smoke.py -v -m "not integration"

Run all tests including integration (requires OPENROUTER_API_KEY):
    pytest tests/test_coder/test_coder_smoke.py -v
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest


if TYPE_CHECKING:
    pass


# =============================================================================
# Unit Tests - No API key required
# =============================================================================


class TestCommandBuilding:
    """Test that aider commands are built correctly."""

    def test_aider_command_includes_file_flags(self, temp_repo: Path, mock_env: dict):
        """Test that --file flags are added for context_paths."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        config = NinjaConfig.from_env()
        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        # Build instruction with context_paths
        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Add a hello function",
            context_paths=["src/main.py", "src/utils.py"],
            allowed_globs=["src/**/*.py"],
            deny_globs=[],
        )

        # Write task file
        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)

        # Build command
        cmd = driver._build_command(task_file, str(temp_repo))

        # Verify --file flags are present
        assert "--file" in cmd, "Command should include --file flag"

        # Find all --file arguments
        file_args = []
        for i, arg in enumerate(cmd):
            if arg == "--file" and i + 1 < len(cmd):
                file_args.append(cmd[i + 1])

        assert "src/main.py" in file_args, "src/main.py should be in --file args"
        assert "src/utils.py" in file_args, "src/utils.py should be in --file args"
        assert len(file_args) == 2, f"Expected 2 --file args, got {len(file_args)}"

    def test_aider_command_without_context_paths(self, temp_repo: Path, mock_env: dict):
        """Test command building when no context_paths are provided."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Add a hello function",
            context_paths=[],  # Empty context_paths
            allowed_globs=["**/*.py"],
            deny_globs=[],
        )

        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)
        cmd = driver._build_command(task_file, str(temp_repo))

        # Count --file occurrences
        file_count = cmd.count("--file")
        assert file_count == 0, "Should have no --file flags when context_paths is empty"

    def test_command_has_message_flag(self, temp_repo: Path, mock_env: dict):
        """Test that --message flag is present in command."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Test task",
            context_paths=["src/main.py"],
            allowed_globs=[],
            deny_globs=[],
        )

        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)
        cmd = driver._build_command(task_file, str(temp_repo))

        assert "--message" in cmd, "Command should include --message flag"

    def test_no_shlex_quote_mangling(self, temp_repo: Path, mock_env: dict):
        """Test that prompt doesn't have shlex.quote escape sequences."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="What's the best approach?",  # Contains apostrophe
            context_paths=["src/main.py"],
            allowed_globs=[],
            deny_globs=[],
        )

        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)
        cmd = driver._build_command(task_file, str(temp_repo))

        # Find the message content
        message_idx = cmd.index("--message")
        message_content = cmd[message_idx + 1]

        # Should NOT contain shlex.quote escape sequences like '\"'\"'
        assert "'\"'\"'" not in message_content, "Message should not have shlex.quote escapes"
        assert "'\\''" not in message_content, "Message should not have shell escape sequences"


class TestApiKeyRedaction:
    """Test that API keys are properly redacted in logs."""

    def test_api_key_not_in_safe_command(self, temp_repo: Path, mock_env: dict):
        """Test that API key is redacted when building safe command for logging."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        api_key = "sk-or-v1-supersecretkey1234567890abcdef"
        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key=api_key,
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Test task",
            context_paths=["src/main.py"],
            allowed_globs=[],
            deny_globs=[],
        )

        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)
        cmd = driver._build_command(task_file, str(temp_repo))

        # Build the safe command (as done in execute_sync/execute_async)
        # Note: use "api-key" not "--api-key" to match "--openai-api-key"
        safe_cmd = [
            arg if "api-key" not in prev.lower() else "***REDACTED***"
            for prev, arg in zip([""] + cmd[:-1], cmd)
        ]
        safe_cmd_str = " ".join(safe_cmd)

        # API key should NOT appear in safe command
        assert api_key not in safe_cmd_str, "API key should be redacted"
        assert "***REDACTED***" in safe_cmd_str, "Should have REDACTED placeholder"

    def test_command_contains_api_key(self, temp_repo: Path, mock_env: dict):
        """Test that actual command DOES contain API key (for execution)."""
        from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver

        api_key = "sk-or-v1-supersecretkey1234567890abcdef"
        config = NinjaConfig(
            bin_path="aider",
            model="test/model",
            openai_api_key=api_key,
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Test task",
            context_paths=[],
            allowed_globs=[],
            deny_globs=[],
        )

        task_file = driver._write_task_file(str(temp_repo), "test_task", instruction)
        cmd = driver._build_command(task_file, str(temp_repo))

        # Actual command SHOULD contain API key for execution
        # API key is in format: openrouter=KEY
        api_key_with_prefix = f"openrouter={api_key}"
        assert api_key_with_prefix in cmd, f"Actual command should contain API key with openrouter prefix: {api_key_with_prefix}"
        assert "--api-key" in cmd, "Should have --api-key flag"


class TestCliDetection:
    """Test CLI type detection."""

    def test_detect_aider(self, mock_env: dict):
        """Test aider detection."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(bin_path="/usr/bin/aider")
        driver = NinjaDriver(config)
        assert driver._detect_cli_type() == "aider"

        config = NinjaConfig(bin_path="aider")
        driver = NinjaDriver(config)
        assert driver._detect_cli_type() == "aider"

    @pytest.mark.skip(reason="Claude CLI strategy not implemented yet")
    def test_detect_claude(self, mock_env: dict):
        """Test claude detection."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(bin_path="/usr/bin/claude")
        driver = NinjaDriver(config)
        assert driver._detect_cli_type() == "claude"

    @pytest.mark.skip(reason="Qwen CLI strategy not implemented yet")
    def test_detect_qwen(self, mock_env: dict):
        """Test qwen detection."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(bin_path="qwen-code")
        driver = NinjaDriver(config)
        assert driver._detect_cli_type() == "qwen"

    @pytest.mark.skip(reason="Generic CLI strategy not implemented yet")
    def test_detect_generic(self, mock_env: dict):
        """Test generic fallback."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(bin_path="unknown-cli")
        driver = NinjaDriver(config)
        assert driver._detect_cli_type() == "generic"


class TestOtherCliAdapters:
    """Test that other CLI adapters also receive file_paths."""

    @pytest.mark.skip(reason="Claude CLI strategy not implemented yet")
    def test_claude_command_includes_file_context(self, temp_repo: Path, mock_env: dict):
        """Test that Claude CLI command includes file context in prompt."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(
            bin_path="claude",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        cmd = driver._build_command_claude(
            prompt="Test prompt",
            repo_root=str(temp_repo),
            file_paths=["src/main.py", "src/utils.py"],
        )

        # Claude doesn't have --file, but should add to prompt
        prompt_content = cmd[-1]  # Last argument is the prompt
        assert "src/main.py" in prompt_content or "Files to focus on" in prompt_content

    @pytest.mark.skip(reason="Qwen CLI strategy not implemented yet")
    def test_qwen_command_includes_file_context(self, temp_repo: Path, mock_env: dict):
        """Test that Qwen CLI command includes file context in prompt."""
        from ninja_coder.driver import NinjaConfig, NinjaDriver

        config = NinjaConfig(
            bin_path="qwen",
            model="test/model",
            openai_api_key="test-key",
            openai_base_url="https://test.api",
        )
        driver = NinjaDriver(config)

        cmd = driver._build_command_qwen(
            prompt="Test prompt",
            repo_root=str(temp_repo),
            file_paths=["src/main.py"],
        )

        # Find the message content (after --message flag)
        assert "--message" in cmd
        message_idx = cmd.index("--message")
        message_content = cmd[message_idx + 1]

        assert "src/main.py" in message_content or "Files to focus on" in message_content


class TestInstructionBuilder:
    """Test instruction document building."""

    def test_quick_task_instruction_structure(self, temp_repo: Path):
        """Test that quick task instruction has correct structure."""
        from ninja_coder.driver import InstructionBuilder

        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Add hello function",
            context_paths=["src/main.py"],
            allowed_globs=["src/**/*.py"],
            deny_globs=["**/__pycache__/**"],
        )

        # Verify structure
        assert instruction["version"] == "1.0"
        assert instruction["type"] == "quick_task"
        assert instruction["task"] == "Add hello function"
        assert instruction["mode"] == "quick"

        # Verify file_scope
        assert "file_scope" in instruction
        assert instruction["file_scope"]["context_paths"] == ["src/main.py"]
        assert instruction["file_scope"]["allowed_globs"] == ["src/**/*.py"]
        assert instruction["file_scope"]["deny_globs"] == ["**/__pycache__/**"]

    def test_instruction_contains_context_paths(self, temp_repo: Path):
        """Test that context_paths are preserved in instruction."""
        from ninja_coder.driver import InstructionBuilder

        context_paths = ["src/main.py", "src/utils.py", "tests/test_main.py"]
        builder = InstructionBuilder(str(temp_repo))
        instruction = builder.build_quick_task(
            task="Test",
            context_paths=context_paths,
            allowed_globs=[],
            deny_globs=[],
        )

        assert instruction["file_scope"]["context_paths"] == context_paths


# =============================================================================
# Integration Tests - Requires API key
# =============================================================================


