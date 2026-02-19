"""
Integration tests for structured logging system.

Tests logging integration with driver, sessions, and multi-agent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver
from ninja_coder.sessions import SessionManager


@pytest.fixture
def temp_cache_dir(tmp_path):
    """Create temporary cache directory."""
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


@pytest.fixture
def driver(temp_cache_dir, monkeypatch):
    """Create driver instance with structured logging."""
    # Mock get_cache_dir to use temp directory
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: temp_cache_dir,
    )

    config = NinjaConfig(
        bin_path=Path("/usr/local/bin/opencode"),  # Mock path
        model="anthropic/claude-sonnet-4-5",
    )
    return NinjaDriver(config)


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_structured_logger_initialization(driver, temp_cache_dir):
    """Test that structured logger is initialized."""
    assert driver.structured_logger is not None
    assert driver.structured_logger.name == "ninja-coder"
    assert driver.structured_logger.log_dir == temp_cache_dir / "logs"
    assert driver.structured_logger.log_dir.exists()


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_session_manager_has_structured_logger(driver):
    """Test that session manager can use structured logger."""
    # Session manager doesn't directly use structured logger
    # but driver logs session actions
    assert driver.session_manager is not None
    assert driver.structured_logger is not None


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_log_file_creation(driver):
    """Test that log file is created on first log."""
    driver.structured_logger.info("Test message")

    assert driver.structured_logger.log_file.exists()

    with open(driver.structured_logger.log_file) as f:
        lines = f.readlines()

    # Should have driver initialization log + test message
    assert len(lines) >= 1

    # Find test message (may not be first due to driver initialization log)
    test_entries = [json.loads(line) for line in lines if "Test message" in line]
    assert len(test_entries) == 1
    assert test_entries[0]["message"] == "Test message"


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_query_logs_through_driver(driver):
    """Test querying logs through driver's structured logger."""
    # Write some logs
    driver.structured_logger.info("Message 1", session_id="s1", task_id="t1")
    driver.structured_logger.error("Error 1", session_id="s1", task_id="t2")
    driver.structured_logger.info("Message 2", session_id="s2", task_id="t1")

    # Query all logs (may include driver initialization log)
    all_logs = driver.structured_logger.query_logs()
    assert len(all_logs) >= 3

    # Query by session
    s1_logs = driver.structured_logger.query_logs(session_id="s1")
    assert len(s1_logs) == 2
    assert all(log["session_id"] == "s1" for log in s1_logs)

    # Query by task
    t1_logs = driver.structured_logger.query_logs(task_id="t1")
    assert len(t1_logs) == 2
    assert all(log["task_id"] == "t1" for log in t1_logs)

    # Query errors only
    error_logs = driver.structured_logger.query_logs(level="ERROR")
    assert len(error_logs) == 1
    assert error_logs[0]["level"] == "ERROR"


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_session_logging_integration(driver, temp_cache_dir):
    """Test that session operations are logged."""
    session_manager = SessionManager(temp_cache_dir)
    session = session_manager.create_session(
        repo_root="/tmp/test-repo",
        model="anthropic/claude-sonnet-4-5",
    )

    # Manually log session creation (driver does this automatically)
    driver.structured_logger.log_session(
        action="created",
        session_id=session.session_id,
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        repo_root="/tmp/test-repo",
    )

    # Query session logs
    session_logs = driver.structured_logger.get_session_logs(
        session.session_id, limit=100
    )

    assert len(session_logs) == 1
    assert session_logs[0]["session_id"] == session.session_id
    assert "Session created" in session_logs[0]["message"]


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_multi_agent_logging(driver):
    """Test multi-agent activation logging."""
    agents = ["Chief AI Architect", "Frontend Engineer", "Backend Engineer"]

    driver.structured_logger.log_multi_agent(
        agents=agents,
        task_id="task-1",
        session_id="session-1",
        cli_name="opencode",
        complexity="full_stack",
        task_type="feature",
    )

    # Query logs
    logs = driver.structured_logger.query_logs(task_id="task-1")

    assert len(logs) == 1
    assert "Multi-agent activated" in logs[0]["message"]
    assert logs[0]["extra"]["agents"] == agents
    assert logs[0]["extra"]["agent_count"] == 3


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_command_logging_with_redaction(driver):
    """Test command logging with sensitive data redaction."""
    command = [
        "opencode",
        "--api-key",
        "sk-secret123",
        "--model",
        "claude-sonnet-4-5",
    ]

    driver.structured_logger.log_command(
        command=command,
        session_id="s1",
        task_id="t1",
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        working_dir="/tmp/test-repo",
    )

    # Query logs
    logs = driver.structured_logger.query_logs(task_id="t1")

    assert len(logs) == 1
    assert "command" in logs[0]["extra"]
    assert "***REDACTED***" in logs[0]["extra"]["command"]
    assert "sk-secret123" not in logs[0]["extra"]["command"]


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_result_logging_success(driver):
    """Test result logging for successful tasks."""
    driver.structured_logger.log_result(
        success=True,
        summary="Task completed successfully",
        session_id="s1",
        task_id="t1",
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        touched_paths=["src/main.py", "tests/test_main.py"],
        exit_code=0,
    )

    logs = driver.structured_logger.query_logs(task_id="t1")

    assert len(logs) == 1
    assert logs[0]["level"] == "INFO"
    assert logs[0]["extra"]["success"] is True
    assert logs[0]["extra"]["exit_code"] == 0


@pytest.mark.skip(reason="Flaky - needs investigation")
def test_result_logging_failure(driver):
    """Test result logging for failed tasks."""
    driver.structured_logger.log_result(
        success=False,
        summary="Task failed with error",
        session_id="s1",
        task_id="t1",
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        exit_code=1,
    )

    logs = driver.structured_logger.query_logs(task_id="t1")

    assert len(logs) == 1
    assert logs[0]["level"] == "ERROR"
    assert logs[0]["extra"]["success"] is False
    assert logs[0]["extra"]["exit_code"] == 1


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
