"""Tests for hooks_base module."""

import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from src.ninja_common.hooks_base import (
    HookCommand,
    HookResult,
    detect_file_type,
    get_repo_root,
    get_staged_files,
    run_subprocess,
)


class TestHookResult:
    """Tests for HookResult dataclass."""

    def test_success_statuses(self):
        """Test that success property returns True for successful statuses."""
        success_statuses = ["ok", "pass", "valid", "formatted", "unchanged"]
        for status in success_statuses:
            result = HookResult(status=status)
            assert result.success is True, f"Status '{status}' should be successful"

    def test_failure_statuses(self):
        """Test that success property returns False for failure statuses."""
        failure_statuses = ["fail", "error", "invalid"]
        for status in failure_statuses:
            result = HookResult(status=status)
            assert result.success is False, f"Status '{status}' should be failure"

    def test_data_field_default(self):
        """Test that data field defaults to empty dict."""
        result = HookResult(status="ok")
        assert result.data == {}
        assert isinstance(result.data, dict)


class TestDetectFileType:
    """Tests for detect_file_type function."""

    def test_detect_file_type_python(self):
        """Test Python file type detection."""
        assert detect_file_type("test.py") == "python"
        assert detect_file_type("test.pyi") == "python"
        assert detect_file_type("path/to/module.py") == "python"

    def test_detect_file_type_javascript(self):
        """Test JavaScript file type detection."""
        assert detect_file_type("test.js") == "javascript"
        assert detect_file_type("test.jsx") == "javascript"
        assert detect_file_type("test.mjs") == "javascript"
        assert detect_file_type("path/to/module.js") == "javascript"

    def test_detect_file_type_typescript(self):
        """Test TypeScript file type detection."""
        assert detect_file_type("test.ts") == "typescript"
        assert detect_file_type("test.tsx") == "typescript"
        assert detect_file_type("path/to/module.ts") == "typescript"

    def test_detect_file_type_other_languages(self):
        """Test other supported file type detections."""
        assert detect_file_type("test.rs") == "rust"
        assert detect_file_type("test.go") == "go"
        assert detect_file_type("test.json") == "json"
        assert detect_file_type("test.yaml") == "yaml"
        assert detect_file_type("test.yml") == "yaml"
        assert detect_file_type("test.md") == "markdown"
        assert detect_file_type("test.markdown") == "markdown"

    def test_detect_file_type_unknown(self):
        """Test unknown file type detection."""
        assert detect_file_type("test.unknown") == "unknown"
        assert detect_file_type("test") == "unknown"
        assert detect_file_type("") == "unknown"


class TestRunSubprocess:
    """Tests for run_subprocess function."""

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_run_subprocess_success(self, mock_run):
        """Test successful subprocess execution."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "output"
        mock_result.stderr = "error"
        mock_run.return_value = mock_result

        exit_code, stdout, stderr = run_subprocess(["echo", "test"])
        
        assert exit_code == 0
        assert stdout == "output"
        assert stderr == "error"
        mock_run.assert_called_once_with(
            ["echo", "test"],
            cwd=None,
            timeout=30.0,
            capture_output=True,
            text=True,
        )

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_run_subprocess_timeout(self, mock_run):
        """Test subprocess timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30.0)
        
        exit_code, stdout, stderr = run_subprocess(["sleep", "100"])
        
        assert exit_code == -1
        assert stdout == ""
        assert stderr == "Command timed out after 30.0s"

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_run_subprocess_not_found(self, mock_run):
        """Test FileNotFoundError handling."""
        mock_run.side_effect = FileNotFoundError()
        
        exit_code, stdout, stderr = run_subprocess(["nonexistent-command"])
        
        assert exit_code == -1
        assert stdout == ""
        assert stderr == "Command not found: nonexistent-command"


class TestGetRepoRoot:
    """Tests for get_repo_root function."""

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_repo_root_in_git_repo(self, mock_run):
        """Test getting repo root when in a git repository."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "/path/to/repo\n"
        mock_run.return_value = mock_result

        repo_root = get_repo_root("/some/path")
        
        assert repo_root == Path("/path/to/repo")
        mock_run.assert_called_once_with(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path("/some/path"),
            capture_output=True,
            text=True,
            timeout=5.0,
        )

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_repo_root_not_in_git_repo(self, mock_run):
        """Test getting repo root when not in a git repository."""
        mock_result = Mock()
        mock_result.returncode = 128
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        repo_root = get_repo_root("/some/path")
        
        assert repo_root is None

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_repo_root_timeout(self, mock_run):
        """Test get_repo_root timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5.0)
        
        repo_root = get_repo_root("/some/path")
        
        assert repo_root is None

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_repo_root_file_not_found(self, mock_run):
        """Test get_repo_root FileNotFoundError handling."""
        mock_run.side_effect = FileNotFoundError()
        
        repo_root = get_repo_root("/some/path")
        
        assert repo_root is None


class TestGetStagedFiles:
    """Tests for get_staged_files function."""

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_staged_files_success(self, mock_run):
        """Test successful retrieval of staged files."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "file1.py\nfile2.js\n\nfile3.ts\n"
        mock_run.return_value = mock_result

        staged_files = get_staged_files("/repo/root")
        
        assert staged_files == ["file1.py", "file2.js", "file3.ts"]
        mock_run.assert_called_once_with(
            ["git", "diff", "--cached", "--name-only"],
            cwd="/repo/root",
            capture_output=True,
            text=True,
            timeout=5.0,
        )

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_staged_files_no_staged_files(self, mock_run):
        """Test when there are no staged files."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        mock_run.return_value = mock_result

        staged_files = get_staged_files("/repo/root")
        
        assert staged_files == []

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_staged_files_timeout(self, mock_run):
        """Test get_staged_files timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5.0)
        
        staged_files = get_staged_files("/repo/root")
        
        assert staged_files == []

    @patch("src.ninja_common.hooks_base.subprocess.run")
    def test_get_staged_files_file_not_found(self, mock_run):
        """Test get_staged_files FileNotFoundError handling."""
        mock_run.side_effect = FileNotFoundError()
        
        staged_files = get_staged_files("/repo/root")
        
        assert staged_files == []


class ConcreteHookCommand(HookCommand):
    """Concrete implementation of HookCommand for testing."""
    
    def execute(self) -> HookResult:
        """Execute the hook command."""
        return HookResult(status="ok", message="Test command executed")


class TestHookCommand:
    """Tests for HookCommand base class."""

    def test_hook_command_initialization(self):
        """Test HookCommand initialization."""
        cmd = ConcreteHookCommand()
        assert cmd.json_output is False
        
        cmd_json = ConcreteHookCommand(json_output=True)
        assert cmd_json.json_output is True

    @patch("builtins.print")
    def test_run_success_human_readable(self, mock_print):
        """Test run method with human readable output."""
        cmd = ConcreteHookCommand()
        result = cmd.run()
        
        assert result == 0
        mock_print.assert_called_once_with("Test command executed")

    @patch("json.dumps")
    @patch("builtins.print")
    def test_run_success_json_output(self, mock_print, mock_dumps):
        """Test run method with JSON output."""
        mock_dumps.return_value = '{"status": "ok", "message": "Test command executed"}'
        
        cmd = ConcreteHookCommand(json_output=True)
        result = cmd.run()
        
        assert result == 0
        mock_dumps.assert_called_once()
        mock_print.assert_called_once_with('{"status": "ok", "message": "Test command executed"}')

    @patch("builtins.print")
    def test_run_failure_human_readable(self, mock_print):
        """Test run method with failure status in human readable output."""
        class FailingHookCommand(HookCommand):
            def execute(self) -> HookResult:
                return HookResult(status="error", message="Test error")
        
        cmd = FailingHookCommand()
        result = cmd.run()
        
        assert result == 1
        mock_print.assert_called_once_with("Test error")

    @patch("json.dumps")
    @patch("builtins.print")
    def test_run_failure_json_output(self, mock_print, mock_dumps):
        """Test run method with failure status in JSON output."""
        mock_dumps.return_value = '{"status": "error", "message": "Test error"}'
        
        class FailingHookCommand(HookCommand):
            def execute(self) -> HookResult:
                return HookResult(status="error", message="Test error")
        
        cmd = FailingHookCommand(json_output=True)
        result = cmd.run()
        
        assert result == 1
        mock_dumps.assert_called_once()
        mock_print.assert_called_once_with('{"status": "error", "message": "Test error"}')

    @patch("builtins.print")
    def test_run_exception_handling_human_readable(self, mock_print):
        """Test run method exception handling with human readable output."""
        class ExceptionHookCommand(HookCommand):
            def execute(self) -> HookResult:
                raise ValueError("Test exception")
        
        cmd = ExceptionHookCommand()
        result = cmd.run()
        
        assert result == 1
        mock_print.assert_called_once()

    @patch("json.dumps")
    @patch("builtins.print")
    def test_run_exception_handling_json_output(self, mock_print, mock_dumps):
        """Test run method exception handling with JSON output."""
        mock_dumps.return_value = '{"status": "error", "message": "Test exception"}'
        
        class ExceptionHookCommand(HookCommand):
            def execute(self) -> HookResult:
                raise ValueError("Test exception")
        
        cmd = ExceptionHookCommand(json_output=True)
        result = cmd.run()
        
        assert result == 1
        mock_dumps.assert_called_once()
        mock_print.assert_called_once_with('{"status": "error", "message": "Test exception"}')
