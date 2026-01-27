"""
Tests for structured logging system.

Tests log entry creation, JSONL writing, querying, and redaction.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ninja_common.structured_logger import LogEntry, StructuredLogger


@pytest.fixture
def temp_log_dir(tmp_path):
    """Create temporary log directory."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture
def logger(temp_log_dir):
    """Create structured logger instance."""
    return StructuredLogger("test-logger", temp_log_dir)


def test_log_entry_creation():
    """Test LogEntry dataclass creation."""
    entry = LogEntry(
        timestamp="2026-01-26T12:00:00Z",
        level="INFO",
        logger_name="test",
        message="Test message",
        session_id="abc123",
        task_id="task-1",
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        extra={"key": "value"},
    )

    assert entry.timestamp == "2026-01-26T12:00:00Z"
    assert entry.level == "INFO"
    assert entry.logger_name == "test"
    assert entry.message == "Test message"
    assert entry.session_id == "abc123"
    assert entry.task_id == "task-1"
    assert entry.cli_name == "opencode"
    assert entry.model == "anthropic/claude-sonnet-4-5"
    assert entry.extra == {"key": "value"}


def test_log_entry_to_dict():
    """Test LogEntry to_dict excludes None values."""
    entry = LogEntry(
        timestamp="2026-01-26T12:00:00Z",
        level="INFO",
        logger_name="test",
        message="Test message",
        session_id="abc123",
        task_id=None,  # None value
        cli_name=None,  # None value
    )

    data = entry.to_dict()

    assert "timestamp" in data
    assert "level" in data
    assert "message" in data
    assert "session_id" in data
    assert "task_id" not in data  # None excluded
    assert "cli_name" not in data  # None excluded
    assert "extra" not in data  # None excluded


def test_logger_initialization(temp_log_dir):
    """Test StructuredLogger initialization."""
    logger = StructuredLogger("test-logger", temp_log_dir)

    assert logger.name == "test-logger"
    assert logger.log_dir == temp_log_dir
    assert logger.log_dir.exists()

    # Check log file name format
    today = datetime.now(UTC).strftime("%Y%m%d")
    expected_file = temp_log_dir / f"ninja-{today}.jsonl"
    assert logger.log_file == expected_file


def test_basic_logging(logger, temp_log_dir):
    """Test basic log writing."""
    logger.log("INFO", "Test message", session_id="test-session")

    # Check file exists and contains entry
    assert logger.log_file.exists()

    with open(logger.log_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["level"] == "INFO"
    assert entry["message"] == "Test message"
    assert entry["logger_name"] == "test-logger"
    assert entry["session_id"] == "test-session"
    assert "timestamp" in entry


def test_convenience_methods(logger):
    """Test convenience logging methods."""
    logger.info("Info message", task_id="task-1")
    logger.debug("Debug message", task_id="task-2")
    logger.warning("Warning message", task_id="task-3")
    logger.error("Error message", task_id="task-4")

    with open(logger.log_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 4

    entries = [json.loads(line) for line in lines]
    assert entries[0]["level"] == "INFO"
    assert entries[1]["level"] == "DEBUG"
    assert entries[2]["level"] == "WARNING"
    assert entries[3]["level"] == "ERROR"


def test_log_command(logger):
    """Test command logging with redaction."""
    logger.log_command(
        command=["opencode", "--api-key", "secret123", "--model", "claude-sonnet-4-5"],
        session_id="session-1",
        task_id="task-1",
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["level"] == "INFO"
    assert "Executing:" in entry["message"]
    assert "command" in entry["extra"]

    # Check redaction
    command = entry["extra"]["command"]
    assert "***REDACTED***" in command
    assert "secret123" not in command


def test_log_result(logger):
    """Test result logging."""
    logger.log_result(
        success=True,
        summary="Task completed successfully",
        session_id="session-1",
        task_id="task-1",
        touched_paths=["src/main.py", "tests/test_main.py"],
        exit_code=0,
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["level"] == "INFO"  # Success = INFO
    assert entry["message"] == "Task completed successfully"
    assert entry["extra"]["success"] is True
    assert entry["extra"]["exit_code"] == 0
    assert len(entry["extra"]["touched_paths"]) == 2


def test_log_result_failure(logger):
    """Test result logging for failures."""
    logger.log_result(
        success=False,
        summary="Task failed",
        session_id="session-1",
        task_id="task-1",
        exit_code=1,
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["level"] == "ERROR"  # Failure = ERROR
    assert entry["extra"]["success"] is False
    assert entry["extra"]["exit_code"] == 1


def test_log_multi_agent(logger):
    """Test multi-agent activation logging."""
    logger.log_multi_agent(
        agents=["Chief AI Architect", "Frontend Engineer", "Backend Engineer"],
        task_id="task-1",
        session_id="session-1",
        complexity="full_stack",
        task_type="feature",
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["level"] == "INFO"
    assert "Multi-agent activated" in entry["message"]
    assert entry["extra"]["agents"] == [
        "Chief AI Architect",
        "Frontend Engineer",
        "Backend Engineer",
    ]
    assert entry["extra"]["agent_count"] == 3
    assert entry["extra"]["complexity"] == "full_stack"


def test_log_session(logger):
    """Test session action logging."""
    logger.log_session(
        action="created",
        session_id="session-1",
        cli_name="opencode",
        model="anthropic/claude-sonnet-4-5",
        repo_root="/tmp/test-repo",
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["level"] == "INFO"
    assert entry["message"] == "Session created: session-1"
    assert entry["session_id"] == "session-1"
    assert entry["cli_name"] == "opencode"  # cli_name is a direct field
    assert entry["model"] == "anthropic/claude-sonnet-4-5"  # model is a direct field
    assert entry["extra"]["action"] == "created"
    assert entry["extra"]["repo_root"] == "/tmp/test-repo"


def test_query_logs_no_filters(logger):
    """Test querying logs without filters."""
    # Write multiple entries
    logger.info("Message 1", task_id="task-1")
    logger.info("Message 2", task_id="task-2")
    logger.error("Error 1", task_id="task-3")

    results = logger.query_logs()

    assert len(results) == 3
    assert results[0]["message"] == "Message 1"
    assert results[1]["message"] == "Message 2"
    assert results[2]["message"] == "Error 1"


def test_query_logs_by_session(logger):
    """Test querying logs by session_id."""
    logger.info("Session 1 msg 1", session_id="session-1")
    logger.info("Session 2 msg 1", session_id="session-2")
    logger.info("Session 1 msg 2", session_id="session-1")

    results = logger.query_logs(session_id="session-1")

    assert len(results) == 2
    assert all(r["session_id"] == "session-1" for r in results)


def test_query_logs_by_task(logger):
    """Test querying logs by task_id."""
    logger.info("Task 1 msg 1", task_id="task-1")
    logger.info("Task 2 msg 1", task_id="task-2")
    logger.info("Task 1 msg 2", task_id="task-1")

    results = logger.query_logs(task_id="task-1")

    assert len(results) == 2
    assert all(r["task_id"] == "task-1" for r in results)


def test_query_logs_by_level(logger):
    """Test querying logs by level."""
    logger.info("Info message")
    logger.error("Error message")
    logger.warning("Warning message")
    logger.error("Another error")

    results = logger.query_logs(level="ERROR")

    assert len(results) == 2
    assert all(r["level"] == "ERROR" for r in results)


def test_query_logs_by_cli_name(logger):
    """Test querying logs by CLI name."""
    logger.info("Message 1", cli_name="aider")
    logger.info("Message 2", cli_name="opencode")
    logger.info("Message 3", cli_name="aider")

    results = logger.query_logs(cli_name="aider")

    assert len(results) == 2
    assert all(r["cli_name"] == "aider" for r in results)


def test_query_logs_with_limit(logger):
    """Test querying logs with limit."""
    for i in range(10):
        logger.info(f"Message {i}")

    results = logger.query_logs(limit=5)

    assert len(results) == 5


def test_query_logs_with_offset(logger):
    """Test querying logs with offset."""
    for i in range(10):
        logger.info(f"Message {i}")

    results = logger.query_logs(limit=5, offset=3)

    assert len(results) == 5
    assert results[0]["message"] == "Message 3"
    assert results[4]["message"] == "Message 7"


def test_query_logs_combined_filters(logger):
    """Test querying logs with multiple filters."""
    logger.info("Msg 1", session_id="s1", task_id="t1", cli_name="aider")
    logger.error("Msg 2", session_id="s1", task_id="t1", cli_name="aider")
    logger.info("Msg 3", session_id="s1", task_id="t2", cli_name="aider")
    logger.info("Msg 4", session_id="s2", task_id="t1", cli_name="opencode")

    results = logger.query_logs(
        session_id="s1",
        task_id="t1",
        cli_name="aider",
    )

    assert len(results) == 2
    assert all(r["session_id"] == "s1" for r in results)
    assert all(r["task_id"] == "t1" for r in results)
    assert all(r["cli_name"] == "aider" for r in results)


def test_count_logs(logger):
    """Test counting logs."""
    logger.info("Message 1", session_id="s1")
    logger.info("Message 2", session_id="s1")
    logger.info("Message 3", session_id="s2")

    count_all = logger.count_logs()
    count_s1 = logger.count_logs(session_id="s1")
    count_s2 = logger.count_logs(session_id="s2")

    assert count_all == 3
    assert count_s1 == 2
    assert count_s2 == 1


def test_count_logs_by_level(logger):
    """Test counting logs by level."""
    logger.info("Info 1")
    logger.error("Error 1")
    logger.error("Error 2")
    logger.warning("Warning 1")

    error_count = logger.count_logs(level="ERROR")
    info_count = logger.count_logs(level="INFO")

    assert error_count == 2
    assert info_count == 1


def test_get_recent_errors(logger):
    """Test getting recent errors."""
    logger.info("Normal message")
    logger.error("Error 1", task_id="task-1")
    logger.info("Another normal message")
    logger.error("Error 2", task_id="task-2")

    errors = logger.get_recent_errors(limit=10)

    assert len(errors) == 2
    assert all(e["level"] == "ERROR" for e in errors)
    assert errors[0]["message"] == "Error 1"
    assert errors[1]["message"] == "Error 2"


def test_get_session_logs(logger):
    """Test getting all logs for a session."""
    logger.info("Session 1 - msg 1", session_id="session-1")
    logger.error("Session 1 - error", session_id="session-1")
    logger.info("Session 2 - msg 1", session_id="session-2")
    logger.info("Session 1 - msg 2", session_id="session-1")

    session_logs = logger.get_session_logs("session-1", limit=100)

    assert len(session_logs) == 3
    assert all(log["session_id"] == "session-1" for log in session_logs)


def test_command_redaction_key_value_format(logger):
    """Test command redaction for --key=value format."""
    command = ["opencode", "--api-key=secret123", "--model", "claude"]
    redacted = logger._redact_command(command)

    assert redacted[0] == "opencode"
    assert redacted[1] == "--api-key=***REDACTED***"
    assert redacted[2] == "--model"
    assert redacted[3] == "claude"
    assert "secret123" not in redacted


def test_command_redaction_separate_value(logger):
    """Test command redaction for --key value format."""
    command = ["opencode", "--api-key", "secret123", "--model", "claude"]
    redacted = logger._redact_command(command)

    assert redacted[0] == "opencode"
    assert redacted[1] == "--api-key"
    assert redacted[2] == "***REDACTED***"
    assert redacted[3] == "--model"
    assert redacted[4] == "claude"
    assert "secret123" not in redacted


def test_command_redaction_multiple_sensitive(logger):
    """Test redacting multiple sensitive arguments."""
    command = [
        "tool",
        "--password",
        "pass123",
        "--token",
        "tok456",
        "--normal-arg",
        "value",
    ]
    redacted = logger._redact_command(command)

    assert "***REDACTED***" in redacted
    assert "pass123" not in redacted
    assert "tok456" not in redacted
    assert "value" in redacted
    assert redacted.count("***REDACTED***") == 2


def test_query_logs_empty_file(logger):
    """Test querying when log file doesn't exist."""
    # Don't write any logs
    results = logger.query_logs()

    assert results == []


def test_count_logs_empty_file(logger):
    """Test counting when log file doesn't exist."""
    # Don't write any logs
    count = logger.count_logs()

    assert count == 0


def test_log_with_extra_fields(logger):
    """Test logging with extra fields."""
    logger.log(
        "INFO",
        "Test message",
        session_id="s1",
        task_id="t1",
        custom_field="custom_value",
        numeric_field=42,
        list_field=["a", "b", "c"],
    )

    with open(logger.log_file, "r") as f:
        entry = json.loads(f.readline())

    assert entry["extra"]["custom_field"] == "custom_value"
    assert entry["extra"]["numeric_field"] == 42
    assert entry["extra"]["list_field"] == ["a", "b", "c"]


def test_jsonl_format_multiple_entries(logger):
    """Test that multiple entries are properly JSONL formatted."""
    logger.info("Message 1")
    logger.info("Message 2")
    logger.info("Message 3")

    with open(logger.log_file, "r") as f:
        lines = f.readlines()

    assert len(lines) == 3

    # Each line should be valid JSON
    for line in lines:
        entry = json.loads(line)
        assert "timestamp" in entry
        assert "level" in entry
        assert "message" in entry


def test_query_logs_malformed_json(logger, temp_log_dir):
    """Test that malformed JSON lines are skipped gracefully."""
    # Write valid and invalid entries
    logger.info("Valid message 1")

    # Manually append malformed JSON
    with open(logger.log_file, "a") as f:
        f.write("{ invalid json }\n")

    logger.info("Valid message 2")

    results = logger.query_logs()

    # Should only return valid entries
    assert len(results) == 2
    assert results[0]["message"] == "Valid message 1"
    assert results[1]["message"] == "Valid message 2"


def test_log_file_daily_rotation(temp_log_dir):
    """Test that log file name includes date."""
    logger = StructuredLogger("test", temp_log_dir)

    today = datetime.now(UTC).strftime("%Y%m%d")
    expected_filename = f"ninja-{today}.jsonl"

    assert logger.log_file.name == expected_filename


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
