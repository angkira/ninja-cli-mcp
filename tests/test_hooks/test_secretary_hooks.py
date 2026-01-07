"""
Tests for ninja-secretary hooks CLI.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

from src.ninja_secretary.hooks_cli import (
    AnalyzeChangesCommand,
    HookResult,
    SessionReportCommand,
    ValidatePathCommand,
    main,
)


class TestValidatePathCommand:
    """Tests for ValidatePathCommand."""

    def test_validate_path_success(self, tmp_path):
        """Test successful path validation within repo."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.write_text("test content")

        command = ValidatePathCommand(str(test_file), str(tmp_path))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["status"] == "valid"
        assert result.data["path"] == str(test_file)
        assert result.error is None

    def test_validate_path_traversal(self, tmp_path):
        """Test detection of path traversal attempts."""
        command = ValidatePathCommand("../sensitive_file", str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "path_traversal_detected"

    def test_validate_path_absolute_outside(self, tmp_path):
        """Test detection of absolute paths outside repo."""
        outside_path = "/etc/passwd"
        command = ValidatePathCommand(outside_path, str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "path_traversal_detected"

    def test_validate_path_denied_pattern(self, tmp_path):
        """Test detection of denied path patterns (.git, node_modules, etc.)."""
        # Test .git pattern
        git_file = tmp_path / ".git" / "config"
        command = ValidatePathCommand(str(git_file), str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "denied_path_pattern"

        # Test node_modules pattern
        node_file = tmp_path / "node_modules" / "package" / "index.js"
        command = ValidatePathCommand(str(node_file), str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "denied_path_pattern"

    def test_validate_path_not_found(self, tmp_path):
        """Test handling of non-existent paths."""
        non_existent = tmp_path / "non_existent.txt"
        command = ValidatePathCommand(str(non_existent), str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.data is not None
        assert result.data["status"] == "invalid"
        assert result.data["reason"] == "path_not_found"


class TestSessionReportCommand:
    """Tests for SessionReportCommand."""

    def test_session_report_basic(self, tmp_path):
        """Test basic session report generation."""
        # Create some test files
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.py").write_text("content2")
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        (subdir / "file3.txt").write_text("content3")

        command = SessionReportCommand(str(tmp_path))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["repository"] == str(tmp_path)
        assert result.data["files"] == 3
        assert result.data["directories"] == 1
        assert "generated_at" in result.data

    @patch("ninja_common.path_utils.get_internal_dir")
    def test_session_report_save(self, mock_get_internal_dir, tmp_path):
        """Test saving session report to file."""
        # Setup mock for internal directory
        internal_dir = tmp_path / ".ninja"
        internal_dir.mkdir(parents=True, exist_ok=True)
        mock_get_internal_dir.return_value = internal_dir

        # Create test file
        (tmp_path / "test.txt").write_text("test")

        command = SessionReportCommand(str(tmp_path), save=True)
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert "saved_to" in result.data
        assert Path(result.data["saved_to"]).exists()

    @patch("subprocess.run")
    def test_session_report_git_info(self, mock_run, tmp_path):
        """Test git branch and commit extraction."""

        # Mock git commands
        def mock_subprocess_run(cmd, **kwargs):
            mock_result = Mock()
            if "rev-parse --abbrev-ref HEAD" in " ".join(cmd):
                mock_result.stdout = "main\n"
                mock_result.stderr = ""
                mock_result.returncode = 0
            elif "rev-parse HEAD" in " ".join(cmd):
                mock_result.stdout = "a1b2c3d4e5f6\n"
                mock_result.stderr = ""
                mock_result.returncode = 0
            else:
                raise subprocess.CalledProcessError(1, cmd)
            return mock_result

        mock_run.side_effect = mock_subprocess_run

        command = SessionReportCommand(str(tmp_path))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["branch"] == "main"
        assert result.data["commit"] == "a1b2c3d4"


class TestAnalyzeChangesCommand:
    """Tests for AnalyzeChangesCommand."""

    @patch("subprocess.run")
    def test_analyze_no_changes(self, mock_run, tmp_path):
        """Test analysis when there are no changes."""
        # Mock git diff to return empty output
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        command = AnalyzeChangesCommand(str(tmp_path))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["files_changed"] == 0
        assert result.data["lines_added"] == 0
        assert result.data["lines_removed"] == 0
        assert result.data["changes"] == []

    @patch("subprocess.run")
    def test_analyze_with_changes(self, mock_run, tmp_path):
        """Test analysis with changes."""
        # Mock git diff output
        diff_output = """10\t5\tsrc/file1.py
3\t1\tsrc/file2.py
0\t15\tdeleted_file.py"""

        mock_result = Mock()
        mock_result.stdout = diff_output
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        command = AnalyzeChangesCommand(str(tmp_path))
        result = command.execute()

        assert result.success is True
        assert result.data is not None
        assert result.data["files_changed"] == 3
        assert result.data["lines_added"] == 13  # 10 + 3 + 0
        assert result.data["lines_removed"] == 21  # 5 + 1 + 15
        assert len(result.data["changes"]) == 3

        # Check first change
        assert result.data["changes"][0]["file"] == "src/file1.py"
        assert result.data["changes"][0]["lines_added"] == 10
        assert result.data["changes"][0]["lines_removed"] == 5

    @patch("subprocess.run")
    def test_analyze_since_commit(self, mock_run, tmp_path):
        """Test analysis with --since flag."""
        # Mock git diff output
        diff_output = "5\t2\tsrc/new_file.py"

        mock_result = Mock()
        mock_result.stdout = diff_output
        mock_result.stderr = ""
        mock_result.returncode = 0
        mock_run.return_value = mock_result

        command = AnalyzeChangesCommand(str(tmp_path), since="HEAD~1")
        result = command.execute()

        # Verify git command was called with correct arguments
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "HEAD~1" in call_args
        assert "HEAD" in call_args

        assert result.success is True
        assert result.data is not None
        assert result.data["files_changed"] == 1

    @patch("subprocess.run")
    def test_analyze_git_not_found(self, mock_run, tmp_path):
        """Test handling when git is not found."""
        mock_run.side_effect = FileNotFoundError("git not found")

        command = AnalyzeChangesCommand(str(tmp_path))
        result = command.execute()

        assert result.success is False
        assert result.error is not None
        assert "Git is not installed" in result.error


class TestCLIIntegration:
    """Tests for CLI integration."""

    @patch("sys.argv", ["hooks_cli.py", "validate-path", "test.txt", "--repo-root", "/tmp"])
    @patch("src.ninja_secretary.hooks_cli.ValidatePathCommand")
    def test_main_validate_path(self, mock_command_class):
        """Test CLI argument parsing for validate-path command."""
        mock_instance = Mock()
        mock_instance.execute.return_value = HookResult(success=True, data={"status": "valid"})
        mock_command_class.return_value = mock_instance

        with patch("sys.exit") as mock_exit:
            main()
            mock_exit.assert_called_once_with(0)

    @patch("sys.argv", ["hooks_cli.py", "session-report", "--repo-root", "/tmp", "--save"])
    @patch("src.ninja_secretary.hooks_cli.SessionReportCommand")
    def test_main_session_report(self, mock_command_class):
        """Test CLI argument parsing for session-report command with --save."""
        mock_instance = Mock()
        mock_instance.execute.return_value = HookResult(success=True, data={"saved": True})
        mock_command_class.return_value = mock_instance

        with patch("sys.exit") as mock_exit:
            main()
            mock_exit.assert_called_once_with(0)
            # Verify SessionReportCommand was called with save=True
            mock_command_class.assert_called_once_with("/tmp", True)

    @patch(
        "sys.argv", ["hooks_cli.py", "--json", "validate-path", "test.txt", "--repo-root", "/tmp"]
    )
    @patch("src.ninja_secretary.hooks_cli.ValidatePathCommand")
    def test_main_json_output(self, mock_command_class):
        """Test JSON output format."""
        mock_instance = Mock()
        mock_instance.execute.return_value = HookResult(
            success=True, data={"status": "valid", "path": "test.txt"}
        )
        mock_command_class.return_value = mock_instance

        with patch("builtins.print") as mock_print, patch("sys.exit") as mock_exit:
            main()
            # Verify JSON was printed
            mock_print.assert_called_once()
            printed_output = mock_print.call_args[0][0]
            parsed_json = json.loads(printed_output)
            assert parsed_json["success"] is True
            assert parsed_json["data"]["status"] == "valid"
            mock_exit.assert_called_once_with(0)
