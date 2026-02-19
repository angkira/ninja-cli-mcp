import pytest


"""
Unit tests for ninja-secretary hooks CLI.
"""

import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ninja_secretary.hooks_cli import (
    AnalyzeChangesCommand,
    HookResult,
    SessionReportCommand,
    ValidatePathCommand,
    main,
)


def test_validate_path_command_valid():
    """Test ValidatePathCommand with a valid path."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        test_file = repo_root / "test.txt"
        test_file.write_text("test content")

        command = ValidatePathCommand("test.txt", str(repo_root))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["status"] == "valid"
        assert result.error is None


def test_validate_path_command_path_traversal():
    """Test ValidatePathCommand detects path traversal."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        (repo_root / "test.txt").write_text("test")

        command = ValidatePathCommand("../etc/passwd", str(repo_root))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "path_traversal_detected"


def test_validate_path_command_denied_pattern():
    """Test ValidatePathCommand rejects denied patterns."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        git_dir = repo_root / ".git"
        git_dir.mkdir()
        (git_dir / "config").write_text("test")

        command = ValidatePathCommand(".git/config", str(repo_root))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "denied_path_pattern"


def test_validate_path_command_not_found():
    """Test ValidatePathCommand handles non-existent paths."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)

        command = ValidatePathCommand("nonexistent.txt", str(repo_root))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "path_not_found"


def test_session_report_command():
    """Test SessionReportCommand basic functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        (repo_root / "test.txt").write_text("test")
        (repo_root / "subdir").mkdir()
        (repo_root / "subdir" / "test2.txt").write_text("test2")

        command = SessionReportCommand(str(repo_root))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert "files" in result.data
        assert "directories" in result.data
        assert result.data["files"] >= 2
        assert result.data["directories"] >= 1


def test_session_report_command_save():
    """Test SessionReportCommand with save option."""
    with tempfile.TemporaryDirectory() as temp_dir:
        repo_root = Path(temp_dir)
        (repo_root / "test.txt").write_text("test")

        command = SessionReportCommand(str(repo_root), save=True)
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        # Check that report was saved (path will be in data)
        assert "saved_to" in result.data


@patch("subprocess.run")
def test_analyze_changes_command(mock_run):
    """Test AnalyzeChangesCommand basic functionality."""
    # Mock git diff output
    mock_result = MagicMock()
    mock_result.stdout = "10\t5\tsrc/test.py\n3\t1\tREADME.md\n"
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    command = AnalyzeChangesCommand("/fake/repo")
    result = command.execute()

    assert result.success is True
    assert result.data is not None
    assert result.data["files_changed"] == 2
    assert result.data["lines_added"] == 13
    assert result.data["lines_removed"] == 6
    assert len(result.data["changes"]) == 2


@patch("subprocess.run")
def test_analyze_changes_command_since(mock_run):
    """Test AnalyzeChangesCommand with since parameter."""
    mock_result = MagicMock()
    mock_result.stdout = "20\t10\tsrc/new.py\n"
    mock_result.stderr = ""
    mock_result.returncode = 0
    mock_run.return_value = mock_result

    command = AnalyzeChangesCommand("/fake/repo", since="HEAD~1")
    result = command.execute()

    # Check that the command was called with the right arguments
    mock_run.assert_called_once()
    args, _kwargs = mock_run.call_args
    assert "HEAD~1" in args[0]
    assert "HEAD" in args[0]

    assert result.success is True
    assert result.data is not None
    assert result.data["files_changed"] == 1


@patch("subprocess.run")
def test_analyze_changes_command_git_error(mock_run):
    """Test AnalyzeChangesCommand handles git errors."""
    mock_run.side_effect = subprocess.CalledProcessError(1, "git diff")

    command = AnalyzeChangesCommand("/fake/repo")
    result = command.execute()

    assert result.success is False
    assert result.error is not None
    assert "Git command failed" in result.error


@patch("subprocess.run")
def test_analyze_changes_command_no_git(mock_run):
    """Test AnalyzeChangesCommand handles missing git."""
    mock_run.side_effect = FileNotFoundError()

    command = AnalyzeChangesCommand("/fake/repo")
    result = command.execute()

    assert result.success is False
    assert result.error is not None
    assert "Git is not installed" in result.error


@patch("ninja_secretary.hooks_cli.ValidatePathCommand")
def test_main_validate_path(mock_command_class):
    """Test main function with validate-path command."""
    mock_result = HookResult(success=True, data={"status": "valid"})
    mock_command_instance = MagicMock()
    mock_command_instance.execute.return_value = mock_result
    mock_command_class.return_value = mock_command_instance

    captured = io.StringIO()
    with patch.object(sys, "argv", ["hooks_cli.py", "validate-path", "test.txt", "--repo-root", "/tmp"]), \
         patch.object(sys, "stdout", captured), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0

    output = captured.getvalue()
    assert "valid" in output


@patch("ninja_secretary.hooks_cli.ValidatePathCommand")
def test_main_json_output(mock_command_class):
    """Test main function with JSON output."""
    mock_result = HookResult(success=True, data={"status": "valid"})
    mock_command_instance = MagicMock()
    mock_command_instance.execute.return_value = mock_result
    mock_command_class.return_value = mock_command_instance

    captured = io.StringIO()
    with patch.object(sys, "argv", ["hooks_cli.py", "--json", "validate-path", "test.txt", "--repo-root", "/tmp"]), \
         patch.object(sys, "stdout", captured), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0

    output = captured.getvalue()
    parsed = json.loads(output)
    assert parsed["success"] is True
    assert parsed["data"]["status"] == "valid"


@patch("ninja_secretary.hooks_cli.SessionReportCommand")
def test_main_session_report(mock_command_class):
    """Test main function with session-report command."""
    mock_result = HookResult(success=True, data={"files": 10})
    mock_command_instance = MagicMock()
    mock_command_instance.execute.return_value = mock_result
    mock_command_class.return_value = mock_command_instance

    captured = io.StringIO()
    with patch.object(sys, "argv", ["hooks_cli.py", "session-report", "--repo-root", "/tmp"]), \
         patch.object(sys, "stdout", captured), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0

    output = captured.getvalue()
    assert "10" in output


@patch("ninja_secretary.hooks_cli.AnalyzeChangesCommand")
def test_main_analyze_changes(mock_command_class):
    """Test main function with analyze-changes command."""
    mock_result = HookResult(success=True, data={"files_changed": 5})
    mock_command_instance = MagicMock()
    mock_command_instance.execute.return_value = mock_result
    mock_command_class.return_value = mock_command_instance

    captured = io.StringIO()
    with patch.object(sys, "argv", ["hooks_cli.py", "analyze-changes", "--repo-root", "/tmp"]), \
         patch.object(sys, "stdout", captured), \
         pytest.raises(SystemExit) as exc_info:
        main()
    assert exc_info.value.code == 0

    output = captured.getvalue()
    assert "5" in output


@patch("sys.argv", ["hooks_cli.py", "invalid-command"])
def test_main_invalid_command():
    """Test main function with invalid command."""
    with patch("sys.stderr") as mock_stderr:
        with pytest.raises(SystemExit):
            main()
        output = mock_stderr.write.call_args[0][0]
        assert "invalid choice" in output
