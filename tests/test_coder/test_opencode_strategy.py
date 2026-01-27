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
    original_disable_daemon = os.environ.get("OPENCODE_DISABLE_DAEMON")

    # Clear environment variables
    if "OPENCODE_SERVER_URL" in os.environ:
        del os.environ["OPENCODE_SERVER_URL"]
    if "OPENCODE_USE_DAEMON" in os.environ:
        del os.environ["OPENCODE_USE_DAEMON"]
    if "OPENCODE_DISABLE_DAEMON" in os.environ:
        del os.environ["OPENCODE_DISABLE_DAEMON"]

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

    if original_disable_daemon is not None:
        os.environ["OPENCODE_DISABLE_DAEMON"] = original_disable_daemon
    elif "OPENCODE_DISABLE_DAEMON" in os.environ:
        del os.environ["OPENCODE_DISABLE_DAEMON"]


def test_daemon_mode_enabled_by_default(strategy, clean_env):
    """Test that daemon mode is enabled by default."""
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


def test_daemon_mode_disabled_with_env_var_true(strategy, clean_env):
    """Test daemon mode can be disabled with OPENCODE_DISABLE_DAEMON=true."""
    os.environ["OPENCODE_DISABLE_DAEMON"] = "true"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should NOT be called when disabled
        mock_get_daemon.assert_not_called()

        # Command should not have --attach flag
        assert "--attach" not in result.command
        assert result.metadata["server_mode"] is False


def test_daemon_mode_disabled_with_env_var_1(strategy, clean_env):
    """Test daemon mode can be disabled with OPENCODE_DISABLE_DAEMON=1."""
    os.environ["OPENCODE_DISABLE_DAEMON"] = "1"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should NOT be called when disabled
        mock_get_daemon.assert_not_called()
        assert "--attach" not in result.command


def test_daemon_mode_disabled_with_env_var_yes(strategy, clean_env):
    """Test daemon mode can be disabled with OPENCODE_DISABLE_DAEMON=yes."""
    os.environ["OPENCODE_DISABLE_DAEMON"] = "yes"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should NOT be called when disabled
        mock_get_daemon.assert_not_called()
        assert "--attach" not in result.command


def test_daemon_mode_enabled_with_false_string(strategy, clean_env):
    """Test daemon mode is enabled by default even when OPENCODE_DISABLE_DAEMON=false."""
    os.environ["OPENCODE_DISABLE_DAEMON"] = "false"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Daemon should be called (false != true/1/yes, so daemon is enabled)
        mock_daemon.get_or_start_server.assert_called_once()
        assert "--attach" in result.command


def test_manual_server_url_takes_precedence_over_daemon(clean_env):
    """Test that manual OPENCODE_SERVER_URL takes precedence over daemon mode."""
    # Set manual server URL (daemon is enabled by default)
    os.environ["OPENCODE_SERVER_URL"] = "http://localhost:5000"

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
    """Test graceful fallback when daemon fails to start server (daemon enabled by default)."""
    # Daemon is enabled by default, no need to set env var
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
    """Test daemon mode with different repository paths (enabled by default)."""
    # Daemon is enabled by default, no need to set env var
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
    """Test that daemon mode preserves other command options (enabled by default)."""
    # Daemon is enabled by default, no need to set env var
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


def test_daemon_disable_case_insensitive(strategy, clean_env):
    """Test that OPENCODE_DISABLE_DAEMON is case-insensitive."""
    test_cases = ["TRUE", "True", "YES", "Yes", "1"]

    for value in test_cases:
        os.environ["OPENCODE_DISABLE_DAEMON"] = value

        with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
            result = strategy.build_command(
                prompt="test task",
                repo_root="/tmp/test-repo",
            )

            # Daemon should NOT be called when disabled
            mock_get_daemon.assert_not_called()
            assert "--attach" not in result.command

        # Clean up for next iteration
        del os.environ["OPENCODE_DISABLE_DAEMON"]


def test_daemon_not_used_with_session_mode(strategy, clean_env):
    """Test that daemon mode works correctly (no conflict with session mode - enabled by default)."""
    # Daemon is enabled by default, no need to set env var
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
    """Test that build_command returns correct working directory (daemon enabled by default)."""
    # Daemon is enabled by default, no need to set env var
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


def test_timeout_values_for_different_task_types(strategy):
    """Test that get_timeout returns correct values for different task types."""
    # Test quick tasks
    assert strategy.get_timeout("quick") == 300  # 5 minutes

    # Test sequential tasks
    assert strategy.get_timeout("sequential") == 900  # 15 minutes

    # Test parallel tasks
    assert strategy.get_timeout("parallel") == 1200  # 20 minutes

    # Test unknown task type (default)
    assert strategy.get_timeout("unknown") == 600  # 10 minutes default


def test_timeout_values_with_backward_compatibility(strategy):
    """Test that timeouts are increased from old values."""
    # Old values were: quick=180, sequential=600, parallel=900
    # New values are: quick=300, sequential=900, parallel=1200

    # Quick tasks increased from 3min to 5min
    assert strategy.get_timeout("quick") > 180
    assert strategy.get_timeout("quick") == 300

    # Sequential tasks increased from 10min to 15min
    assert strategy.get_timeout("sequential") > 600
    assert strategy.get_timeout("sequential") == 900

    # Parallel tasks increased from 15min to 20min
    assert strategy.get_timeout("parallel") > 900
    assert strategy.get_timeout("parallel") == 1200


def test_daemon_mode_with_both_disable_and_server_url(clean_env):
    """Test that manual server URL takes precedence over daemon disable flag."""
    os.environ["OPENCODE_SERVER_URL"] = "http://localhost:5000"
    os.environ["OPENCODE_DISABLE_DAEMON"] = "true"

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

        # Manual server URL should be used (not daemon, not subprocess)
        assert "--attach" in result.command
        assert "http://localhost:5000" in result.command
        assert result.metadata["server_url"] == "http://localhost:5000"


def test_daemon_mode_backward_compatible_use_daemon_env_var(strategy, clean_env):
    """Test backward compatibility: OPENCODE_USE_DAEMON still works (deprecated but functional)."""
    # Even though daemon is enabled by default, setting OPENCODE_USE_DAEMON=true
    # should still work (no-op since it's already enabled by default)
    os.environ["OPENCODE_USE_DAEMON"] = "true"

    mock_daemon = Mock()
    mock_daemon.get_or_start_server.return_value = "http://localhost:4096"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon", return_value=mock_daemon):
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # Should still work as before (daemon enabled)
        mock_daemon.get_or_start_server.assert_called_once()
        assert "--attach" in result.command


def test_daemon_disabled_falls_back_to_subprocess_mode(strategy, clean_env):
    """Test that disabling daemon mode falls back to subprocess mode (no --attach)."""
    os.environ["OPENCODE_DISABLE_DAEMON"] = "true"

    with patch("ninja_coder.strategies.opencode_strategy.get_daemon") as mock_get_daemon:
        result = strategy.build_command(
            prompt="test task",
            repo_root="/tmp/test-repo",
        )

        # No daemon call
        mock_get_daemon.assert_not_called()

        # No server mode
        assert "--attach" not in result.command
        assert result.metadata["server_mode"] is False
        assert result.metadata["server_url"] is None

        # Command should still be valid
        assert result.command[0] == "/usr/local/bin/opencode"
        assert result.command[1] == "run"
        assert "test task" in result.command[-1]


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
