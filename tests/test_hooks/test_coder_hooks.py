"""
Tests for ninja-coder hooks CLI.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from ninja_coder.hooks_cli import (
    FormatFileCommand,
    LintCheckCommand,
    PreCommitCommand,
    main,
)


class TestFormatFileCommand:
    """Test FormatFileCommand functionality."""

    def test_format_file_not_found(self):
        """Test that missing file returns error status."""
        cmd = FormatFileCommand("nonexistent.py")
        result = cmd.execute()

        assert result.status == "error"
        assert "File not found" in result.message
        assert "nonexistent.py" in result.message

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_python_success(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test successful Python file formatting with ruff."""
        # Create a temporary Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        # Mock dependencies
        mock_detect_type.return_value = "python"
        mock_run_subprocess.return_value = (0, "", "")

        cmd = FormatFileCommand(str(test_file))
        result = cmd.execute()

        assert result.status == "formatted"
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "ruff"
        assert result.data["changes"] is True

        # Verify ruff was called correctly
        mock_run_subprocess.assert_called_once()
        call_args = mock_run_subprocess.call_args[0][0]
        assert call_args == ["ruff", "format", str(test_file)]

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_python_check_only(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test Python file format check mode."""
        # Create a temporary Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        # Mock dependencies
        mock_detect_type.return_value = "python"
        mock_run_subprocess.return_value = (0, "", "")

        cmd = FormatFileCommand(str(test_file), check_only=True)
        result = cmd.execute()

        assert result.status == "unchanged"
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "ruff"
        assert result.data["changes"] is False

        # Verify ruff was called with --check flag
        mock_run_subprocess.assert_called_once()
        call_args = mock_run_subprocess.call_args[0][0]
        assert call_args == ["ruff", "format", "--check", str(test_file)]

    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_unknown_type(self, mock_detect_type, tmp_path):
        """Test formatting file with unknown type returns unchanged."""
        # Create a temporary file with unknown extension
        test_file = tmp_path / "test.xyz"
        test_file.write_text("content")

        # Mock dependencies
        mock_detect_type.return_value = "unknown"

        cmd = FormatFileCommand(str(test_file))
        result = cmd.execute()

        assert result.status == "unchanged"
        assert "No formatter configured" in result.message
        assert result.data["file"] == str(test_file)
        assert result.data["file_type"] == "unknown"

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_python_needs_formatting(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test Python file that needs formatting in check mode."""
        # Create a temporary Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        # Mock dependencies - ruff returns exit code 1 when formatting needed
        mock_detect_type.return_value = "python"
        mock_run_subprocess.return_value = (1, "", "")

        cmd = FormatFileCommand(str(test_file), check_only=True)
        result = cmd.execute()

        assert result.status == "fail"
        assert "File needs formatting" in result.message
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "ruff"
        assert result.data["needs_formatting"] is True

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_python_error(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test Python file formatting error."""
        # Create a temporary Python file
        test_file = tmp_path / "test.py"
        test_file.write_text("print('hello')\n")

        # Mock dependencies - ruff returns error
        mock_detect_type.return_value = "python"
        mock_run_subprocess.return_value = (2, "", "Error formatting file")

        cmd = FormatFileCommand(str(test_file))
        result = cmd.execute()

        assert result.status == "error"
        assert "Error formatting file" in result.message
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "ruff"

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_js_ts_success(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test successful JS/TS file formatting with prettier."""
        # Create a temporary JavaScript file
        test_file = tmp_path / "test.js"
        test_file.write_text("console.log('hello');\n")

        # Mock dependencies
        mock_detect_type.return_value = "javascript"
        mock_run_subprocess.return_value = (0, "", "")

        cmd = FormatFileCommand(str(test_file))
        result = cmd.execute()

        assert result.status == "formatted"
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "prettier"
        assert result.data["changes"] is True

        # Verify prettier was called correctly
        mock_run_subprocess.assert_called_once()
        call_args = mock_run_subprocess.call_args[0][0]
        assert call_args == ["npx", "prettier", "--write", str(test_file)]

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.detect_file_type")
    def test_format_js_ts_not_available(self, mock_detect_type, mock_run_subprocess, tmp_path):
        """Test JS/TS file formatting when prettier is not available."""
        # Create a temporary JavaScript file
        test_file = tmp_path / "test.js"
        test_file.write_text("console.log('hello');\n")

        # Mock dependencies - prettier not available (exit code != 0 or 1)
        mock_detect_type.return_value = "javascript"
        mock_run_subprocess.return_value = (127, "", "command not found")

        cmd = FormatFileCommand(str(test_file))
        result = cmd.execute()

        assert result.status == "unchanged"
        assert "Prettier not available" in result.message
        assert result.data["file"] == str(test_file)
        assert result.data["formatter"] == "prettier"


class TestLintCheckCommand:
    """Test LintCheckCommand functionality."""

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.get_staged_files")
    def test_lint_check_pass(self, mock_get_staged_files, mock_run_subprocess, tmp_path):
        """Test lint check that passes with no issues."""
        # Mock dependencies
        mock_get_staged_files.return_value = []
        mock_run_subprocess.return_value = (0, "[]", "")

        cmd = LintCheckCommand(staged=False, repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "pass"
        assert result.data["total_issues"] == 0
        assert result.data["issues"] == []

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.get_staged_files")
    def test_lint_check_fail(self, mock_get_staged_files, mock_run_subprocess, tmp_path):
        """Test lint check that fails with issues."""
        # Mock ruff output with issues
        ruff_output = json.dumps(
            [
                {
                    "filename": "src/test.py",
                    "location": {"row": 5, "column": 10},
                    "code": "E501",
                    "message": "Line too long (88 > 79 characters)",
                },
                {
                    "filename": "src/test.py",
                    "location": {"row": 10, "column": 5},
                    "code": "F401",
                    "message": "'os' imported but unused",
                },
            ]
        )

        # Mock dependencies
        mock_get_staged_files.return_value = []
        mock_run_subprocess.return_value = (1, ruff_output, "")

        cmd = LintCheckCommand(staged=False, repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "fail"
        assert result.data["total_issues"] == 2
        assert len(result.data["issues"]) == 2
        assert result.data["issues"][0]["file"] == "src/test.py"
        assert result.data["issues"][0]["line"] == 5
        assert result.data["issues"][0]["code"] == "E501"
        assert "Line too long" in result.data["issues"][0]["message"]

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.get_staged_files")
    def test_lint_check_staged(self, mock_get_staged_files, mock_run_subprocess, tmp_path):
        """Test lint check on staged files."""
        # Mock staged files
        mock_get_staged_files.return_value = ["src/file1.py", "src/file2.py", "README.md"]
        mock_run_subprocess.return_value = (0, "[]", "")

        cmd = LintCheckCommand(staged=True, repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "pass"
        # Verify ruff was called with only Python files
        mock_run_subprocess.assert_called_once()
        call_args = mock_run_subprocess.call_args[0][0]
        assert "src/file1.py" in call_args
        assert "src/file2.py" in call_args
        assert "README.md" not in call_args

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.get_staged_files")
    def test_lint_check_fix(self, mock_get_staged_files, mock_run_subprocess, tmp_path):
        """Test lint check with auto-fix."""
        # Mock ruff output with issues that can be fixed
        ruff_output = json.dumps(
            [
                {
                    "filename": "src/test.py",
                    "location": {"row": 10, "column": 5},
                    "code": "F401",
                    "message": "'os' imported but unused",
                }
            ]
        )

        # Mock dependencies - ruff fix returns 1 (had issues but fixed)
        mock_get_staged_files.return_value = []
        mock_run_subprocess.return_value = (1, ruff_output, "")

        cmd = LintCheckCommand(staged=False, fix=True, repo_root=str(tmp_path))
        result = cmd.execute()

        # When fix=True, issues are fixed so fixed count = total issues
        assert result.status == "fail"  # ruff exits 1 when there were issues
        assert result.data["fixed"] == 1
        assert result.data["total_issues"] == 1
        # Verify ruff was called with --fix flag
        mock_run_subprocess.assert_called_once()
        call_args = mock_run_subprocess.call_args[0][0]
        assert "--fix" in call_args

    @patch("ninja_coder.hooks_cli.run_subprocess")
    @patch("ninja_coder.hooks_cli.get_staged_files")
    def test_lint_check_json_decode_error(
        self, mock_get_staged_files, mock_run_subprocess, tmp_path
    ):
        """Test lint check when ruff output is invalid JSON."""
        # Mock dependencies with invalid JSON output
        mock_get_staged_files.return_value = []
        mock_run_subprocess.return_value = (1, "Invalid JSON output", "")

        cmd = LintCheckCommand(staged=False, repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "fail"
        assert result.data["issues"] == []


class TestPreCommitCommand:
    """Test PreCommitCommand functionality."""

    @patch("ninja_coder.hooks_cli.get_staged_files")
    @patch("ninja_coder.hooks_cli.LintCheckCommand.execute")
    @patch("ninja_coder.hooks_cli.FormatFileCommand.execute")
    def test_precommit_all_pass(
        self, mock_format_execute, mock_lint_execute, mock_get_staged_files, tmp_path
    ):
        """Test pre-commit when all checks pass."""
        # Mock dependencies
        mock_get_staged_files.return_value = ["src/test.py"]
        mock_lint_execute.return_value = type(
            "obj", (object,), {"status": "pass", "success": True, "data": {"total_issues": 0}}
        )
        mock_format_execute.return_value = type(
            "obj", (object,), {"status": "pass", "success": True}
        )

        cmd = PreCommitCommand(repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "pass"
        assert result.data["checks"]["lint"]["status"] == "pass"
        assert result.data["checks"]["format"]["status"] == "pass"

    @patch("ninja_coder.hooks_cli.get_staged_files")
    @patch("ninja_coder.hooks_cli.LintCheckCommand.execute")
    @patch("ninja_coder.hooks_cli.FormatFileCommand.execute")
    def test_precommit_lint_fail(
        self, mock_format_execute, mock_lint_execute, mock_get_staged_files, tmp_path
    ):
        """Test pre-commit when lint check fails."""
        # Mock dependencies
        mock_get_staged_files.return_value = ["src/test.py"]
        mock_lint_execute.return_value = type(
            "obj", (object,), {"status": "fail", "success": False, "data": {"total_issues": 2}}
        )
        mock_format_execute.return_value = type(
            "obj", (object,), {"status": "pass", "success": True}
        )

        cmd = PreCommitCommand(repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "fail"
        assert result.data["checks"]["lint"]["status"] == "fail"
        assert result.data["checks"]["lint"]["issues"] == 2
        assert result.data["checks"]["format"]["status"] == "pass"

    @patch("ninja_coder.hooks_cli.get_staged_files")
    @patch("ninja_coder.hooks_cli.LintCheckCommand.execute")
    @patch("ninja_coder.hooks_cli.FormatFileCommand.execute")
    def test_precommit_format_fail(
        self, mock_format_execute, mock_lint_execute, mock_get_staged_files, tmp_path
    ):
        """Test pre-commit when format check fails."""
        # Mock dependencies
        mock_get_staged_files.return_value = ["src/test.py"]
        mock_lint_execute.return_value = type(
            "obj", (object,), {"status": "pass", "success": True, "data": {"total_issues": 0}}
        )
        mock_format_execute.return_value = type(
            "obj", (object,), {"status": "fail", "success": False}
        )

        cmd = PreCommitCommand(repo_root=str(tmp_path))
        result = cmd.execute()

        assert result.status == "fail"
        assert result.data["checks"]["lint"]["status"] == "pass"
        assert result.data["checks"]["format"]["status"] == "fail"
        assert result.data["checks"]["format"]["issues"] == 1


class TestCLIIntegration:
    """Test CLI argument parsing and integration."""

    @patch("ninja_coder.hooks_cli.FormatFileCommand")
    def test_main_format_file(self, mock_format_command):
        """Test main function with format-file command."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_format_command.return_value = mock_instance

        # Simulate command line arguments
        with patch("sys.argv", ["hooks_cli.py", "format-file", "test.py"]):
            result = main()

            assert result == 0
            mock_format_command.assert_called_once_with("test.py", False, False)

    @patch("ninja_coder.hooks_cli.FormatFileCommand")
    def test_main_format_file_check(self, mock_format_command):
        """Test main function with format-file --check command."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_format_command.return_value = mock_instance

        # Simulate command line arguments
        with patch("sys.argv", ["hooks_cli.py", "format-file", "test.py", "--check"]):
            result = main()

            assert result == 0
            mock_format_command.assert_called_once_with("test.py", True, False)

    @patch("ninja_coder.hooks_cli.LintCheckCommand")
    def test_main_lint_check(self, mock_lint_command):
        """Test main function with lint-check command."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_lint_command.return_value = mock_instance

        # Simulate command line arguments
        with patch("sys.argv", ["hooks_cli.py", "lint-check"]):
            result = main()

            assert result == 0
            mock_lint_command.assert_called_once_with(False, False, None, False)

    @patch("ninja_coder.hooks_cli.LintCheckCommand")
    def test_main_lint_check_staged_fix(self, mock_lint_command):
        """Test main function with lint-check --staged --fix command."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_lint_command.return_value = mock_instance

        # Simulate command line arguments
        with patch(
            "sys.argv", ["hooks_cli.py", "lint-check", "--staged", "--fix", "--repo-root", "/test"]
        ):
            result = main()

            assert result == 0
            mock_lint_command.assert_called_once_with(True, True, "/test", False)

    @patch("ninja_coder.hooks_cli.PreCommitCommand")
    def test_main_precommit(self, mock_precommit_command):
        """Test main function with pre-commit command."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_precommit_command.return_value = mock_instance

        # Simulate command line arguments
        with patch("sys.argv", ["hooks_cli.py", "pre-commit"]):
            result = main()

            assert result == 0
            mock_precommit_command.assert_called_once_with(None, False)

    @patch("ninja_coder.hooks_cli.FormatFileCommand")
    def test_main_json_output(self, mock_format_command):
        """Test main function with JSON output flag."""
        # Mock the command execution
        mock_instance = type("obj", (object,), {"run": lambda: 0})
        mock_format_command.return_value = mock_instance

        # Simulate command line arguments - --json must come before subcommand
        with patch("sys.argv", ["hooks_cli.py", "--json", "format-file", "test.py"]):
            result = main()

            assert result == 0
            mock_format_command.assert_called_once_with("test.py", False, True)

    def test_main_no_command(self):
        """Test main function with no command provided."""
        # Simulate command line arguments with no command
        with patch("sys.argv", ["hooks_cli.py"]), patch("sys.stderr"), pytest.raises(SystemExit):
            main()
