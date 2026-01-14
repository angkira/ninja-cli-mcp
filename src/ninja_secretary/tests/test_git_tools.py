"""
Unit tests for git management tools in SecretaryToolExecutor.

Tests cover git_status, git_diff, git_commit, and git_log methods.
"""

from __future__ import annotations

import subprocess

import pytest

from ninja_secretary.models import (
    GitCommitRequest,
    GitDiffRequest,
    GitLogRequest,
    GitStatusRequest,
)
from ninja_secretary.tools import SecretaryToolExecutor


@pytest.fixture
def executor():
    """Create a SecretaryToolExecutor instance for testing."""
    return SecretaryToolExecutor()


@pytest.fixture
def temp_repo(tmp_path):
    """Create a temporary git repository for testing."""
    repo_path = tmp_path / "test_repo"
    repo_path.mkdir()

    # Initialize git repo
    subprocess.run(
        ["git", "init"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    # Configure git user
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo_path,
        capture_output=True,
        check=True,
    )

    return repo_path


class TestGitStatus:
    """Tests for git_status method."""

    @pytest.mark.asyncio
    async def test_git_status_clean_repo(self, executor, temp_repo):
        """Test git status on a clean repository."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitStatusRequest(repo_root=str(temp_repo))
        result = await executor.git_status(request)

        assert result.status == "ok"
        assert result.branch == "master" or result.branch == "main"
        assert result.staged == []
        assert result.unstaged == []
        assert result.untracked == []

    @pytest.mark.asyncio
    async def test_git_status_with_untracked_files(self, executor, temp_repo):
        """Test git status with untracked files."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create untracked file
        untracked = temp_repo / "untracked.txt"
        untracked.write_text("untracked content")

        request = GitStatusRequest(repo_root=str(temp_repo), include_untracked=True)
        result = await executor.git_status(request)

        assert result.status == "ok"
        assert "untracked.txt" in result.untracked

    @pytest.mark.asyncio
    async def test_git_status_with_staged_changes(self, executor, temp_repo):
        """Test git status with staged changes."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify and stage file
        test_file.write_text("modified content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitStatusRequest(repo_root=str(temp_repo))
        result = await executor.git_status(request)

        assert result.status == "ok"
        assert "test.txt" in result.staged

    @pytest.mark.asyncio
    async def test_git_status_nonexistent_repo(self, executor):
        """Test git status with nonexistent repository."""
        request = GitStatusRequest(repo_root="/nonexistent/path")
        result = await executor.git_status(request)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_git_status_exclude_untracked(self, executor, temp_repo):
        """Test git status excluding untracked files."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create untracked file
        untracked = temp_repo / "untracked.txt"
        untracked.write_text("untracked content")

        request = GitStatusRequest(repo_root=str(temp_repo), include_untracked=False)
        result = await executor.git_status(request)

        assert result.status == "ok"
        assert result.untracked == []


class TestGitDiff:
    """Tests for git_diff method."""

    @pytest.mark.asyncio
    async def test_git_diff_no_changes(self, executor, temp_repo):
        """Test git diff with no changes."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitDiffRequest(repo_root=str(temp_repo))
        result = await executor.git_diff(request)

        assert result.status == "ok"
        assert result.files_changed == 0

    @pytest.mark.asyncio
    async def test_git_diff_with_unstaged_changes(self, executor, temp_repo):
        """Test git diff with unstaged changes."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content\n")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify file
        test_file.write_text("modified content\n")

        request = GitDiffRequest(repo_root=str(temp_repo), staged=False)
        result = await executor.git_diff(request)

        assert result.status == "ok"
        assert result.files_changed > 0

    @pytest.mark.asyncio
    async def test_git_diff_with_staged_changes(self, executor, temp_repo):
        """Test git diff with staged changes."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content\n")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify and stage file
        test_file.write_text("modified content\n")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitDiffRequest(repo_root=str(temp_repo), staged=True)
        result = await executor.git_diff(request)

        assert result.status == "ok"
        assert result.files_changed > 0

    @pytest.mark.asyncio
    async def test_git_diff_nonexistent_repo(self, executor):
        """Test git diff with nonexistent repository."""
        request = GitDiffRequest(repo_root="/nonexistent/path")
        result = await executor.git_diff(request)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()


class TestGitCommit:
    """Tests for git_commit method."""

    @pytest.mark.asyncio
    async def test_git_commit_success(self, executor, temp_repo):
        """Test successful git commit."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create new file and commit
        new_file = temp_repo / "new.txt"
        new_file.write_text("new content")

        request = GitCommitRequest(
            repo_root=str(temp_repo),
            message="Add new file",
            files=["new.txt"],
        )
        result = await executor.git_commit(request)

        assert result.status == "ok"
        assert result.commit_hash
        assert result.message == "Add new file"
        assert "new.txt" in result.files_committed

    @pytest.mark.asyncio
    async def test_git_commit_with_author(self, executor, temp_repo):
        """Test git commit with custom author."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Create new file and commit with custom author
        new_file = temp_repo / "new.txt"
        new_file.write_text("new content")

        request = GitCommitRequest(
            repo_root=str(temp_repo),
            message="Add new file",
            files=["new.txt"],
            author="Custom Author <custom@example.com>",
        )
        result = await executor.git_commit(request)

        assert result.status == "ok"
        assert result.commit_hash

    @pytest.mark.asyncio
    async def test_git_commit_nonexistent_repo(self, executor):
        """Test git commit with nonexistent repository."""
        request = GitCommitRequest(
            repo_root="/nonexistent/path",
            message="Test commit",
        )
        result = await executor.git_commit(request)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_git_commit_no_files_specified(self, executor, temp_repo):
        """Test git commit without specifying files."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        # Modify file and stage it
        test_file.write_text("modified content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitCommitRequest(
            repo_root=str(temp_repo),
            message="Modify test file",
            files=[],
        )
        result = await executor.git_commit(request)

        assert result.status == "ok"
        assert result.commit_hash


class TestGitLog:
    """Tests for git_log method."""

    @pytest.mark.asyncio
    async def test_git_log_success(self, executor, temp_repo):
        """Test successful git log retrieval."""
        # Create initial commit
        test_file = temp_repo / "test.txt"
        test_file.write_text("test content")

        subprocess.run(
            ["git", "add", "test.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitLogRequest(repo_root=str(temp_repo), max_count=10)
        result = await executor.git_log(request)

        assert result.status == "ok"
        assert len(result.commits) > 0
        assert result.commits[0].hash
        assert result.commits[0].author
        assert result.commits[0].date
        assert result.commits[0].message

    @pytest.mark.asyncio
    async def test_git_log_multiple_commits(self, executor, temp_repo):
        """Test git log with multiple commits."""
        # Create multiple commits
        for i in range(3):
            test_file = temp_repo / f"file{i}.txt"
            test_file.write_text(f"content {i}")

            subprocess.run(
                ["git", "add", f"file{i}.txt"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

        request = GitLogRequest(repo_root=str(temp_repo), max_count=10)
        result = await executor.git_log(request)

        assert result.status == "ok"
        assert len(result.commits) == 3

    @pytest.mark.asyncio
    async def test_git_log_with_file_filter(self, executor, temp_repo):
        """Test git log filtered by file."""
        # Create commits for different files
        file1 = temp_repo / "file1.txt"
        file1.write_text("content 1")

        subprocess.run(
            ["git", "add", "file1.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Add file1"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        file2 = temp_repo / "file2.txt"
        file2.write_text("content 2")

        subprocess.run(
            ["git", "add", "file2.txt"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        subprocess.run(
            ["git", "commit", "-m", "Add file2"],
            cwd=temp_repo,
            capture_output=True,
            check=True,
        )

        request = GitLogRequest(
            repo_root=str(temp_repo),
            max_count=10,
            file_path="file1.txt",
        )
        result = await executor.git_log(request)

        assert result.status == "ok"
        assert len(result.commits) == 1
        assert "file1" in result.commits[0].message

    @pytest.mark.asyncio
    async def test_git_log_nonexistent_repo(self, executor):
        """Test git log with nonexistent repository."""
        request = GitLogRequest(repo_root="/nonexistent/path", max_count=10)
        result = await executor.git_log(request)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_git_log_max_count(self, executor, temp_repo):
        """Test git log respects max_count parameter."""
        # Create multiple commits
        for i in range(5):
            test_file = temp_repo / f"file{i}.txt"
            test_file.write_text(f"content {i}")

            subprocess.run(
                ["git", "add", f"file{i}.txt"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

            subprocess.run(
                ["git", "commit", "-m", f"Commit {i}"],
                cwd=temp_repo,
                capture_output=True,
                check=True,
            )

        request = GitLogRequest(repo_root=str(temp_repo), max_count=2)
        result = await executor.git_log(request)

        assert result.status == "ok"
        assert len(result.commits) <= 2
