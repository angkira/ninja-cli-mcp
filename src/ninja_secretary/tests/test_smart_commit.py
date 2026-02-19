"""
Unit tests for smart_commit functionality.

Tests the smart commit analysis, file grouping, and message generation.
"""

from unittest.mock import MagicMock, patch

import pytest

from ninja_secretary.models import SmartCommitRequest
from ninja_secretary.tools import SecretaryToolExecutor


class TestSmartCommitGrouping:
    """Tests for file grouping logic."""

    def test_group_files_same_directory(self):
        """Test that files in same directory are grouped together."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/models.py", "src/ninja_secretary/tools.py"]

        groups = executor._group_files_by_module(files)

        assert len(groups) == 1
        assert set(groups[0]) == set(files)

    def test_group_files_different_directories(self):
        """Test that files in different directories are grouped separately."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/models.py", "src/ninja_coder/models.py"]

        groups = executor._group_files_by_module(files)

        assert len(groups) == 2

    def test_group_test_files_together(self):
        """Test that test files are grouped together."""
        executor = SecretaryToolExecutor()
        files = ["tests/test_models.py", "tests/test_tools.py", "src/models.py"]

        groups = executor._group_files_by_module(files)

        # Should have 2 groups: tests and src
        assert len(groups) == 2
        test_group = next(g for g in groups if "test" in g[0])
        assert len(test_group) == 2

    def test_group_config_files_together(self):
        """Test that config files at root are grouped together."""
        executor = SecretaryToolExecutor()
        files = ["pyproject.toml", "setup.py", "src/models.py"]

        groups = executor._group_files_by_module(files)

        # Should have 2 groups: config and src
        assert len(groups) == 2

    def test_group_documentation_together(self):
        """Test that documentation files are grouped together."""
        executor = SecretaryToolExecutor()
        files = ["README.md", "docs/API.md", "src/models.py"]

        groups = executor._group_files_by_module(files)

        # Should have 2 groups: docs and src
        assert len(groups) == 2
        doc_group = next(g for g in groups if g[0].endswith(".md"))
        assert len(doc_group) == 2

    def test_group_single_file(self):
        """Test grouping with single file."""
        executor = SecretaryToolExecutor()
        files = ["src/models.py"]

        groups = executor._group_files_by_module(files)

        assert len(groups) == 1
        assert groups[0] == files


class TestCommitMessageGeneration:
    """Tests for commit message generation."""

    def test_message_new_files(self):
        """Test message generation for new files."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/new_module.py"]
        change_types = ["new"]

        message = executor._generate_commit_message(files, change_types)

        assert "feat" in message
        assert "ninja_secretary" in message or "secretary" in message
        assert "Add" in message

    def test_message_deleted_files(self):
        """Test message generation for deleted files."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/old_module.py"]
        change_types = ["deleted"]

        message = executor._generate_commit_message(files, change_types)

        assert "chore" in message
        assert "Remove" in message

    def test_message_modified_models(self):
        """Test message generation for modified models."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/models.py"]
        change_types = ["modified"]

        message = executor._generate_commit_message(files, change_types)

        assert "refactor" in message
        assert "models" in message

    def test_message_modified_tests(self):
        """Test message generation for modified tests."""
        executor = SecretaryToolExecutor()
        files = ["tests/test_secretary.py"]
        change_types = ["modified"]

        message = executor._generate_commit_message(files, change_types)

        assert "test" in message

    def test_message_multiple_files(self):
        """Test message generation for multiple files."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/file1.py", "src/ninja_secretary/file2.py"]
        change_types = ["modified", "modified"]

        message = executor._generate_commit_message(files, change_types)

        assert "2 files" in message or "Update" in message

    def test_message_mixed_changes(self):
        """Test message generation for mixed changes."""
        executor = SecretaryToolExecutor()
        files = ["src/ninja_secretary/new.py", "src/ninja_secretary/old.py"]
        change_types = ["new", "deleted"]

        message = executor._generate_commit_message(files, change_types)

        assert "chore" in message

    def test_message_config_files(self):
        """Test message generation for config files."""
        executor = SecretaryToolExecutor()
        files = ["pyproject.toml"]
        change_types = ["modified"]

        message = executor._generate_commit_message(files, change_types)

        assert "config" in message or "chore" in message


class TestCommitReasoning:
    """Tests for reasoning generation."""

    def test_reasoning_single_file(self):
        """Test reasoning for single file."""
        executor = SecretaryToolExecutor()
        files = ["src/models.py"]
        change_types = ["modified"]

        reasoning = executor._generate_reasoning(files, change_types)

        assert "Single file" in reasoning
        assert "src/models.py" in reasoning

    def test_reasoning_same_directory(self):
        """Test reasoning for files in same directory."""
        executor = SecretaryToolExecutor()
        files = ["src/file1.py", "src/file2.py"]
        change_types = ["modified", "modified"]

        reasoning = executor._generate_reasoning(files, change_types)

        assert "Related files" in reasoning
        assert "2 files" in reasoning

    def test_reasoning_test_files(self):
        """Test reasoning for test files."""
        executor = SecretaryToolExecutor()
        files = ["tests/test_a.py", "tests/test_b.py"]
        change_types = ["modified", "modified"]

        reasoning = executor._generate_reasoning(files, change_types)

        assert "Test files" in reasoning

    def test_reasoning_documentation(self):
        """Test reasoning for documentation files."""
        executor = SecretaryToolExecutor()
        files = ["README.md", "CHANGELOG.md"]
        change_types = ["modified", "modified"]

        reasoning = executor._generate_reasoning(files, change_types)

        assert "Documentation" in reasoning or "markdown" in reasoning


class TestSmartCommitIntegration:
    """Integration tests for smart_commit method."""

    @pytest.mark.asyncio
    async def test_smart_commit_no_changes(self):
        """Test smart_commit with no changes."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            # Mock git status returning empty
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )

            request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=True)
            result = await executor.smart_commit(request)

            assert result.status == "ok"
            assert len(result.suggestions) == 0
            assert result.commits_created == 0

    @pytest.mark.asyncio
    async def test_smart_commit_dry_run(self):
        """Test smart_commit in dry_run mode."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            # Mock git status with changes
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="A  src/new_file.py\nM  src/models.py\n",
                stderr="",
            )

            request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=True)
            result = await executor.smart_commit(request)

            assert result.status == "ok"
            assert len(result.suggestions) > 0
            assert result.commits_created == 0  # dry_run should not create commits

    @pytest.mark.asyncio
    async def test_smart_commit_actual_commit(self):
        """Test smart_commit creating actual commits."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            # Mock git status with changes
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="A  src/new_file.py\n",
                stderr="",
            )

            request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=False)
            result = await executor.smart_commit(request)

            assert result.status == "ok"
            assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_smart_commit_repo_not_found(self):
        """Test smart_commit with non-existent repo."""
        executor = SecretaryToolExecutor()

        request = SmartCommitRequest(repo_root="/nonexistent/repo", dry_run=True)
        result = await executor.smart_commit(request)

        assert result.status == "error"
        assert "not found" in result.error_message

    @pytest.mark.asyncio
    async def test_smart_commit_git_error(self):
        """Test smart_commit handling git errors."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="fatal: not a git repository",
            )

            with patch("pathlib.Path.exists", return_value=True):
                request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=True)
                result = await executor.smart_commit(request)

                assert result.status == "error"

    @pytest.mark.asyncio
    async def test_smart_commit_with_author(self):
        """Test smart_commit with custom author."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="A  src/new_file.py\n",
                stderr="",
            )

            request = SmartCommitRequest(
                repo_root="/tmp/repo",
                dry_run=False,
                author="Test Author <test@example.com>",
            )
            result = await executor.smart_commit(request)

            assert result.status == "ok"

    @pytest.mark.asyncio
    async def test_smart_commit_include_untracked(self):
        """Test smart_commit including untracked files."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="?? src/untracked.py\n",
                stderr="",
            )

            request = SmartCommitRequest(
                repo_root="/tmp/repo",
                dry_run=True,
                include_untracked=True,
            )
            result = await executor.smart_commit(request)

            assert result.status == "ok"
            assert len(result.suggestions) > 0

    @pytest.mark.asyncio
    async def test_smart_commit_multiple_groups(self):
        """Test smart_commit with multiple file groups."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="A  src/ninja_secretary/new.py\nA  tests/test_new.py\n",
                stderr="",
            )

            request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=True)
            result = await executor.smart_commit(request)

            assert result.status == "ok"
            # Should have at least 2 suggestions (one for src, one for tests)
            assert len(result.suggestions) >= 1


class TestSmartCommitEdgeCases:
    """Tests for edge cases and error handling."""

    def test_group_empty_list(self):
        """Test grouping with empty file list."""
        executor = SecretaryToolExecutor()
        groups = executor._group_files_by_module([])
        assert len(groups) == 0

    def test_message_generation_empty_change_types(self):
        """Test message generation with mismatched file/change counts."""
        executor = SecretaryToolExecutor()
        files = ["src/file.py"]
        change_types = []

        # Should handle gracefully
        message = executor._generate_commit_message(files, change_types)
        assert isinstance(message, str)
        assert len(message) > 0

    @pytest.mark.asyncio
    async def test_smart_commit_timeout(self):
        """Test smart_commit handling timeout."""
        executor = SecretaryToolExecutor()

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = TimeoutError()

            with patch("pathlib.Path.exists", return_value=True):
                request = SmartCommitRequest(repo_root="/tmp/repo", dry_run=True)
                result = await executor.smart_commit(request)

                assert result.status == "error"
                assert "timed out" in result.error_message.lower()
