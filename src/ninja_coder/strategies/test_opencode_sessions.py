"""
Unit tests for OpenCode strategy session support.

Tests the session_id and continue_last parameters in build_command()
and session ID extraction in parse_output().
"""

from __future__ import annotations

import pytest

from ninja_coder.driver import NinjaConfig
from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy


@pytest.fixture
def opencode_strategy() -> OpenCodeStrategy:
    """Create an OpenCodeStrategy instance for testing."""
    config = NinjaConfig(
        bin_path="opencode",
        openai_base_url="https://openrouter.ai/api/v1",
        openai_api_key="test-key",
        model="anthropic/claude-sonnet-4",
        timeout_sec=300,
    )
    return OpenCodeStrategy(bin_path="opencode", config=config)


# ============================================================================
# build_command() Session Support Tests
# ============================================================================


def test_build_command_with_session_id(opencode_strategy: OpenCodeStrategy):
    """Test build_command() with session_id parameter."""
    result = opencode_strategy.build_command(
        prompt="Continue the work",
        repo_root="/tmp/test",
        session_id="abc123",
    )

    # Verify session flag is in command
    assert "--session" in result.command
    assert "abc123" in result.command

    # Verify session is in the right position (after --model)
    session_idx = result.command.index("--session")
    model_idx = result.command.index("--model")
    assert session_idx > model_idx

    # Verify metadata includes session info
    assert result.metadata["session_id"] == "abc123"
    assert result.metadata["continue_last"] is False


def test_build_command_with_continue_last(opencode_strategy: OpenCodeStrategy):
    """Test build_command() with continue_last parameter."""
    result = opencode_strategy.build_command(
        prompt="Continue the work",
        repo_root="/tmp/test",
        continue_last=True,
    )

    # Verify continue flag is in command
    assert "--continue" in result.command

    # Verify metadata includes session info
    assert result.metadata["session_id"] is None
    assert result.metadata["continue_last"] is True


def test_build_command_without_session_params(opencode_strategy: OpenCodeStrategy):
    """Test build_command() without session parameters (default behavior)."""
    result = opencode_strategy.build_command(
        prompt="Do some work",
        repo_root="/tmp/test",
    )

    # Verify no session flags in command
    assert "--session" not in result.command
    assert "--continue" not in result.command

    # Verify metadata includes session info (both None/False)
    assert result.metadata["session_id"] is None
    assert result.metadata["continue_last"] is False


def test_build_command_session_id_takes_precedence(opencode_strategy: OpenCodeStrategy):
    """Test that session_id takes precedence over continue_last when both provided."""
    result = opencode_strategy.build_command(
        prompt="Continue the work",
        repo_root="/tmp/test",
        session_id="xyz789",
        continue_last=True,  # This should be ignored
    )

    # Verify only session flag is used, not continue
    assert "--session" in result.command
    assert "xyz789" in result.command
    assert "--continue" not in result.command

    # Verify metadata reflects what was requested
    assert result.metadata["session_id"] == "xyz789"
    assert result.metadata["continue_last"] is True  # Stored as-is


def test_build_command_session_with_other_params(opencode_strategy: OpenCodeStrategy):
    """Test session parameters work alongside other parameters."""
    result = opencode_strategy.build_command(
        prompt="Continue multi-agent work",
        repo_root="/tmp/test",
        file_paths=["src/main.py", "tests/test_main.py"],
        model="anthropic/claude-opus-4",
        additional_flags={"enable_multi_agent": True},
        session_id="session-456",
    )

    # Verify session flag is present
    assert "--session" in result.command
    assert "session-456" in result.command

    # Verify other functionality still works
    assert "--model" in result.command
    assert "anthropic/claude-opus-4" in result.command
    assert "ultrawork" in result.command[-1]  # Multi-agent keyword added to prompt
    assert "src/main.py" in result.command[-1]  # Files mentioned in prompt

    # Verify metadata
    assert result.metadata["session_id"] == "session-456"
    assert result.metadata["multi_agent"] is True
    assert result.metadata["model"] == "anthropic/claude-opus-4"


# ============================================================================
# parse_output() Session ID Extraction Tests
# ============================================================================


def test_parse_output_extracts_session_id_pattern1(opencode_strategy: OpenCodeStrategy):
    """Test extraction of session ID with 'Session: <id>' pattern."""
    stdout = """
    OpenCode CLI v1.0.0
    Starting task...
    Session: abc-123-def-456
    Task completed successfully.
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id == "abc-123-def-456"


def test_parse_output_extracts_session_id_pattern2(opencode_strategy: OpenCodeStrategy):
    """Test extraction of session ID with 'session: <id>' pattern (case insensitive)."""
    stdout = """
    Starting OpenCode session...
    session: xyz789abc
    Executing task...
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id == "xyz789abc"


def test_parse_output_extracts_session_id_pattern3(opencode_strategy: OpenCodeStrategy):
    """Test extraction of session ID with 'session_id: <id>' pattern."""
    stdout = """
    OpenCode initialized
    session_id: test-session-12345
    Ready to execute...
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id == "test-session-12345"


def test_parse_output_no_session_id(opencode_strategy: OpenCodeStrategy):
    """Test parse_output when no session ID is present in output."""
    stdout = """
    Task started
    Modified file: src/main.py
    Task completed
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id is None


def test_parse_output_session_id_with_ansi_codes(opencode_strategy: OpenCodeStrategy):
    """Test session ID extraction works with ANSI color codes in output."""
    # ANSI codes for colors: \x1B[32m (green), \x1B[0m (reset)
    stdout = """
    \x1b[32mOpenCode CLI\x1b[0m
    \x1b[32mSession:\x1b[0m \x1b[33msession-with-colors-123\x1b[0m
    Task running...
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id == "session-with-colors-123"


def test_parse_output_session_id_multiple_matches(opencode_strategy: OpenCodeStrategy):
    """Test that first session ID match is used when multiple patterns exist."""
    stdout = """
    Session: first-session-id
    Some output...
    session_id: second-session-id
    More output...
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    # Should extract the first match
    assert result.session_id == "first-session-id"


def test_parse_output_session_id_with_file_changes(opencode_strategy: OpenCodeStrategy):
    """Test session ID extraction alongside file change detection."""
    stdout = """
    Session: task-session-999
    | Edit     src/main.py
    | Write    src/utils.py
    Modified 2 files
    """

    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)

    assert result.success is True
    assert result.session_id == "task-session-999"
    assert "src/main.py" in result.touched_paths
    assert "src/utils.py" in result.touched_paths


def test_parse_output_session_id_on_error(opencode_strategy: OpenCodeStrategy):
    """Test session ID is still extracted even when task fails."""
    stdout = """
    Session: error-session-abc
    Starting task...
    """
    stderr = "Error: Authentication failed"

    result = opencode_strategy.parse_output(stdout=stdout, stderr=stderr, exit_code=1)

    assert result.success is False
    assert result.session_id == "error-session-abc"


# ============================================================================
# Edge Cases and Validation Tests
# ============================================================================


def test_build_command_empty_session_id(opencode_strategy: OpenCodeStrategy):
    """Test that empty string session_id is treated as None."""
    result = opencode_strategy.build_command(
        prompt="Do work",
        repo_root="/tmp/test",
        session_id="",  # Empty string
    )

    # Empty string is falsy, so no session flag should be added
    assert "--session" not in result.command
    assert result.metadata["session_id"] == ""


def test_build_command_session_id_with_special_chars(opencode_strategy: OpenCodeStrategy):
    """Test session_id with special characters is handled correctly."""
    special_session_id = "session-2024_01_27-abc@123"
    result = opencode_strategy.build_command(
        prompt="Continue work",
        repo_root="/tmp/test",
        session_id=special_session_id,
    )

    assert "--session" in result.command
    assert special_session_id in result.command
    assert result.metadata["session_id"] == special_session_id


def test_parse_output_session_id_case_insensitive(opencode_strategy: OpenCodeStrategy):
    """Test session ID extraction is case-insensitive."""
    stdout = "SESSION: upper-case-session"
    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)
    assert result.session_id == "upper-case-session"

    stdout = "Session: mixed-Case-SESSION"
    result = opencode_strategy.parse_output(stdout=stdout, stderr="", exit_code=0)
    assert result.session_id == "mixed-Case-SESSION"


def test_backward_compatibility(opencode_strategy: OpenCodeStrategy):
    """Test that existing code without session parameters still works."""
    # This should work without any session parameters
    result = opencode_strategy.build_command(
        prompt="Old style call",
        repo_root="/tmp/test",
    )

    assert result.command is not None
    assert result.metadata is not None
    # Session fields should exist but be None/False
    assert "session_id" in result.metadata
    assert "continue_last" in result.metadata
