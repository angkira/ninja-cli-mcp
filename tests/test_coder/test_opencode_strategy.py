"""
Tests for OpenCodeStrategy daemon integration.

Tests the integration of OpenCode daemon with the strategy build_command method,
ensuring proper precedence of manual server URL over daemon mode, and graceful
fallback when daemon fails.
"""

import os
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from ninja_coder.strategies.opencode_strategy import OpenCodeStrategy


@pytest.fixture
def mock_config():
    """Create a mock NinjaConfig."""
    config = Mock()
    config.model = "anthropic/claude-sonnet-4-5"
    return config


@pytest.fixture
def strategy(mock_config):
    """Create OpenCodeStrategy instance."""
    return OpenCodeStrategy(bin_path="/usr/local/bin/opencode", config=mock_config)


@pytest.fixture
def clean_env():
    """Provide a clean environment without server-related variables."""
    original_server_url = os.environ.get("OPENCODE_SERVER_URL")
    original_use_daemon = os.environ.get("OPENCODE_USE_DAEMON")

    # Clear environment variables
    if "OPENCODE_SERVER_URL" in os.environ:
        del os.environ["OPENCODE_SERVER_URL"]
    if "OPENCODE_USE_DAEMON" in os.environ:
        del os.environ["OPENCODE_USE_DAEMON"]

    yield

    # Restore original values
    if original_server_url is not None:
        os.environ["OPENCODE_SERVER_URL"] = original_server_url
    elif "OPENCODE_SERVER_URL" in os.environ:
        del os.environ["OPENCODE_SERVER_URL"]

    if original_use_daemon is not None:
        os.environ["OPENCODE_USE_DAEMON"] = original_use_daemon
    elif "OPENCODE_USE_DAEMON" in os.environ:
        del os.environ["OPENCODE_USE_DAEMON"]


def test_daemon_mode_disabled_by_default(strategy, clean_env):
    """Test that daemon mode is disabled by default."""
    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should not be called
        mock_get_daemon.assert_not_called()

        # Command should not have --attach flag
        assert "--attach" not in result.command
        assert result.metadata["server_mode"] is False


def test_daemon_mode_enabled_with_env_var_true(strategy, clean_env):
    """Test daemon mode when OPENCODE_USE_DAEMON=true."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should be called with correct repo_root
        mock_daemon.get_or_start_server.assert_called_once_with("/tmp/test-repo")

        # Command should have --attach flag
        assert "--attach" in result.command
        assert "http://localhost:4096" in result.command
        assert result.metadata["server_mode"] is True
        assert result.metadata["server_url"] == "http://localhost:4096"


def test_daemon_mode_enabled_with_env_var_1(strategy, clean_env):
    """Test daemon mode when OPENCODE_USE_DAEMON=1."""
    os.environ["OPENCODE_USE_DAEMON"] = "1"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4097"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        mock_daemon.get_or_start_server.assert_called_once()
        assert "--attach" in result.command
        assert "http://localhost:4097" in result.command


def test_daemon_mode_enabled_with_env_var_yes(strategy, clean_env):
    """Test daemon mode when OPENCODE_USE_DAEMON=yes."""
    os.environ["OPENCODE_USE_DAEMON"] = "yes"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4098"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        mock_daemon.get_or_start_server.assert_called_once()
        assert "--attach" in result.command


def test_daemon_mode_disabled_with_false_string(strategy, clean_env):
    """Test daemon mode is disabled when OPENCODE_USE_DAEMON=false."""
    os.environ["OPENCODE_USE_DAEMON"] = "false"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        mock_get_daemon.assert_not_called()
        assert "--attach" not in result.command


def test_manual_server_url_takes_precedence_over_daemon(clean_env):
    """Test that manual OPENCODE_SERVER_URL takes precedence over daemon mode."""
    # Set both environment variables
    os.environ["OPENCODE_SERVER_URL"] = "http://localhost:5000"
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    # Create a new strategy instance to pick up the env var
    config = Mock()
    config.model = "anthropic/claude-sonnet-4-5"
    strategy = OpenCodeStrategy(bin_path="/usr/local/bin/opencode", config=config)

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should NOT be called because manual URL takes precedence
        mock_get_daemon.assert_not_called()

        # Manual server URL should be used
        assert "--attach" in result.command
        assert "http://localhost:5000" in result.command
        assert result.metadata["server_url"] == "http://localhost:5000"


def test_daemon_failure_graceful_fallback(strategy, clean_env):
    """Test graceful fallback when daemon fails to start server."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.side_effect = Exception("Failed to start server")

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        # Should not raise exception
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Should fall back to subprocess mode (no --attach flag)
        assert "--attach" not in result.command
        assert result.metadata["server_mode"] is False


def test_daemon_mode_with_different_repos(strategy, clean_env):
    """Test daemon mode with different repository paths."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.side_effect = [
        "http://localhost:4096",
        "http://localhost:4097",
    ]

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        # First repo
        result1 = strategy.build_command(
            prompt="test task 1",
            repo_root="/tmp/repo1",
        )

        # Second repo
        result2 = strategy.build_command(
            prompt="test task 2",
            repo_root="/tmp/repo2",
        )

        # Daemon should be called for both repos
        assert mock_daemon.get_or_start_server.call_count == 2
        mock_daemon.get_or_start_server.assert_any_call("/tmp/repo1")
        mock_daemon.get_or_start_server.assert_any_call("/tmp/repo2")

        # Different server URLs should be used
        assert "http://localhost:4096" in result1.command
        assert "http://localhost:4097" in result2.command


def test_daemon_mode_preserves_other_command_options(strategy, clean_env):
    """Test that daemon mode preserves other command options."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task with files",
            repo_root="/tmp/test-repo",
            file_paths=["src/main.py", "src/utils.py"],
            model="anthropic/claude-opus-4",
            additional_flags={"enable_multi_agent": True},
        )

        # Verify command structure
        assert result.command[0] == "/usr/local/bin/opencode"
        assert result.command[1] == "run"
        assert "--model" in result.command
        assert "anthropic/claude-opus-4" in result.command
        assert "--attach" in result.command
        assert "http://localhost:4096" in result.command

        # Verify prompt includes file paths
        prompt = result.command[-1]
        assert "src/main.py" in prompt
        assert "src/utils.py" in prompt
        assert "ultrawork" in prompt.lower()  # multi-agent activated

        # Verify metadata
        assert result.metadata["server_mode"] is True
        assert result.metadata["multi_agent"] is True


def test_daemon_mode_case_insensitive(strategy, clean_env):
    """Test that OPENCODE_USE_DAEMON is case-insensitive."""
    test_cases = ["TRUE", "True", "YES", "Yes", "1"]

    for value in test_cases:
        os.environ["OPENCODE_USE_DAEMON"] = value

        mock_daemon = Mock()
        mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

        with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
            result = strategy.build_command(
                prompt="test task",
                repo_root="/tmp/test-repo",
            )

            # Daemon should be called
            mock_daemon.get_or_start_server.assert_called_once()
            assert "--attach" in result.command

        # Reset for next iteration
        mock_daemon.reset_mock()


def test_daemon_not_used_with_session_mode(strategy, clean_env):
    """Test that daemon mode works correctly (no conflict with session mode)."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
            session_id="test-session-123",
        )

        # When server mode is active (via daemon), session flags should not be added
        # (as per existing logic: sessions don't work with --attach)
        assert "--session" not in result.command
        assert "--attach" in result.command


def test_build_command_working_directory(strategy, clean_env):
    """Test that build_command returns correct working directory."""
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        repo_path = "/tmp/test-repo"
        result = strategy.build_command(
            prompt="test task",
            repo_root=repo_path,
        )

        # Verify working directory is set correctly
        assert result.working_dir == Path(repo_path)


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
