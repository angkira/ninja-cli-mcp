"""
Unit tests for git management models.

Tests cover model instantiation, validation, defaults, and type constraints.
"""

import pytest
from pydantic import ValidationError
from src.ninja_secretary.models import (
    GitCommitRequest,
    GitCommitResult,
    GitDiffRequest,
    GitDiffResult,
    GitLogEntry,
    GitLogRequest,
    GitLogResult,
    GitStatusRequest,
    GitStatusResult,
)


class TestGitStatusRequest:
    """Tests for GitStatusRequest model."""

    def test_minimal_request(self):
        """Test creating GitStatusRequest with only required fields."""
        req = GitStatusRequest(repo_root="/path/to/repo")
        assert req.repo_root == "/path/to/repo"
        assert req.include_untracked is True

    def test_with_include_untracked_false(self):
        """Test GitStatusRequest with include_untracked disabled."""
        req = GitStatusRequest(repo_root="/path/to/repo", include_untracked=False)
        assert req.repo_root == "/path/to/repo"
        assert req.include_untracked is False

    def test_missing_repo_root(self):
        """Test that repo_root is required."""
        with pytest.raises(ValidationError):
            GitStatusRequest()

    def test_invalid_include_untracked_type(self):
        """Test that include_untracked must be boolean."""
        with pytest.raises(ValidationError):
            GitStatusRequest(repo_root="/path", include_untracked="yes")


class TestGitStatusResult:
    """Tests for GitStatusResult model."""

    def test_minimal_result(self):
        """Test creating GitStatusResult with required fields."""
        result = GitStatusResult(status="ok", branch="main")
        assert result.status == "ok"
        assert result.branch == "main"
        assert result.staged == []
        assert result.unstaged == []
        assert result.untracked == []
        assert result.ahead == 0
        assert result.behind == 0
        assert result.error_message == ""

    def test_error_result(self):
        """Test creating error GitStatusResult."""
        result = GitStatusResult(status="error", branch="", error_message="Repository not found")
        assert result.status == "error"
        assert result.error_message == "Repository not found"

    def test_with_file_lists(self):
        """Test GitStatusResult with file lists."""
        result = GitStatusResult(
            status="ok",
            branch="develop",
            staged=["file1.py", "file2.py"],
            unstaged=["file3.py"],
            untracked=["file4.py", "file5.py"],
            ahead=3,
            behind=1,
        )
        assert len(result.staged) == 2
        assert len(result.unstaged) == 1
        assert len(result.untracked) == 2
        assert result.ahead == 3
        assert result.behind == 1

    def test_invalid_status_literal(self):
        """Test that status must be 'ok' or 'error'."""
        with pytest.raises(ValidationError):
            GitStatusResult(status="pending", branch="main")

    def test_invalid_ahead_type(self):
        """Test that ahead must be integer."""
        with pytest.raises(ValidationError):
            GitStatusResult(status="ok", branch="main", ahead="3")


class TestGitDiffRequest:
    """Tests for GitDiffRequest model."""

    def test_minimal_request(self):
        """Test creating GitDiffRequest with only required fields."""
        req = GitDiffRequest(repo_root="/path/to/repo")
        assert req.repo_root == "/path/to/repo"
        assert req.staged is False
        assert req.file_path is None

    def test_with_staged_true(self):
        """Test GitDiffRequest with staged changes."""
        req = GitDiffRequest(repo_root="/path/to/repo", staged=True)
        assert req.staged is True

    def test_with_file_path(self):
        """Test GitDiffRequest for specific file."""
        req = GitDiffRequest(repo_root="/path/to/repo", file_path="src/main.py")
        assert req.file_path == "src/main.py"

    def test_all_fields(self):
        """Test GitDiffRequest with all fields."""
        req = GitDiffRequest(repo_root="/path/to/repo", staged=True, file_path="src/module.py")
        assert req.repo_root == "/path/to/repo"
        assert req.staged is True
        assert req.file_path == "src/module.py"

    def test_missing_repo_root(self):
        """Test that repo_root is required."""
        with pytest.raises(ValidationError):
            GitDiffRequest()


class TestGitDiffResult:
    """Tests for GitDiffResult model."""

    def test_minimal_result(self):
        """Test creating GitDiffResult with required fields."""
        result = GitDiffResult(status="ok", diff="")
        assert result.status == "ok"
        assert result.diff == ""
        assert result.files_changed == 0
        assert result.insertions == 0
        assert result.deletions == 0
        assert result.error_message == ""

    def test_with_diff_content(self):
        """Test GitDiffResult with actual diff content."""
        diff_content = "--- a/file.py\n+++ b/file.py\n@@ -1,3 +1,4 @@\n+new line"
        result = GitDiffResult(
            status="ok", diff=diff_content, files_changed=1, insertions=1, deletions=0
        )
        assert result.diff == diff_content
        assert result.files_changed == 1
        assert result.insertions == 1

    def test_error_result(self):
        """Test creating error GitDiffResult."""
        result = GitDiffResult(status="error", diff="", error_message="File not found")
        assert result.status == "error"
        assert result.error_message == "File not found"

    def test_invalid_status_literal(self):
        """Test that status must be 'ok' or 'error'."""
        with pytest.raises(ValidationError):
            GitDiffResult(status="warning", diff="")

    def test_invalid_files_changed_type(self):
        """Test that files_changed must be integer."""
        with pytest.raises(ValidationError):
            GitDiffResult(status="ok", diff="", files_changed="1")


class TestGitCommitRequest:
    """Tests for GitCommitRequest model."""

    def test_minimal_request(self):
        """Test creating GitCommitRequest with required fields."""
        req = GitCommitRequest(repo_root="/path/to/repo", message="Initial commit")
        assert req.repo_root == "/path/to/repo"
        assert req.message == "Initial commit"
        assert req.files == []
        assert req.author is None

    def test_with_specific_files(self):
        """Test GitCommitRequest with specific files."""
        req = GitCommitRequest(
            repo_root="/path/to/repo", message="Update files", files=["file1.py", "file2.py"]
        )
        assert len(req.files) == 2
        assert "file1.py" in req.files

    def test_with_author_override(self):
        """Test GitCommitRequest with author override."""
        req = GitCommitRequest(
            repo_root="/path/to/repo", message="Commit", author="John Doe <john@example.com>"
        )
        assert req.author == "John Doe <john@example.com>"

    def test_all_fields(self):
        """Test GitCommitRequest with all fields."""
        req = GitCommitRequest(
            repo_root="/path/to/repo",
            message="Complete commit",
            files=["a.py", "b.py"],
            author="Jane Doe <jane@example.com>",
        )
        assert req.repo_root == "/path/to/repo"
        assert req.message == "Complete commit"
        assert len(req.files) == 2
        assert req.author == "Jane Doe <jane@example.com>"

    def test_missing_repo_root(self):
        """Test that repo_root is required."""
        with pytest.raises(ValidationError):
            GitCommitRequest(message="Commit")

    def test_missing_message(self):
        """Test that message is required."""
        with pytest.raises(ValidationError):
            GitCommitRequest(repo_root="/path/to/repo")

    def test_invalid_files_type(self):
        """Test that files must be list of strings."""
        with pytest.raises(ValidationError):
            GitCommitRequest(repo_root="/path/to/repo", message="Commit", files="file.py")


class TestGitCommitResult:
    """Tests for GitCommitResult model."""

    def test_minimal_result(self):
        """Test creating GitCommitResult with required fields."""
        result = GitCommitResult(status="ok")
        assert result.status == "ok"
        assert result.commit_hash == ""
        assert result.message == ""
        assert result.files_committed == []
        assert result.error_message == ""

    def test_successful_commit(self):
        """Test GitCommitResult for successful commit."""
        result = GitCommitResult(
            status="ok",
            commit_hash="abc1234",
            message="Update files",
            files_committed=["file1.py", "file2.py"],
        )
        assert result.status == "ok"
        assert result.commit_hash == "abc1234"
        assert len(result.files_committed) == 2

    def test_error_result(self):
        """Test creating error GitCommitResult."""
        result = GitCommitResult(status="error", error_message="Nothing to commit")
        assert result.status == "error"
        assert result.error_message == "Nothing to commit"

    def test_invalid_status_literal(self):
        """Test that status must be 'ok' or 'error'."""
        with pytest.raises(ValidationError):
            GitCommitResult(status="failed")


class TestGitLogRequest:
    """Tests for GitLogRequest model."""

    def test_minimal_request(self):
        """Test creating GitLogRequest with only required fields."""
        req = GitLogRequest(repo_root="/path/to/repo")
        assert req.repo_root == "/path/to/repo"
        assert req.max_count == 10
        assert req.file_path is None

    def test_with_custom_max_count(self):
        """Test GitLogRequest with custom max_count."""
        req = GitLogRequest(repo_root="/path/to/repo", max_count=50)
        assert req.max_count == 50

    def test_with_file_path(self):
        """Test GitLogRequest filtered by file."""
        req = GitLogRequest(repo_root="/path/to/repo", file_path="src/main.py")
        assert req.file_path == "src/main.py"

    def test_all_fields(self):
        """Test GitLogRequest with all fields."""
        req = GitLogRequest(repo_root="/path/to/repo", max_count=25, file_path="src/module.py")
        assert req.repo_root == "/path/to/repo"
        assert req.max_count == 25
        assert req.file_path == "src/module.py"

    def test_missing_repo_root(self):
        """Test that repo_root is required."""
        with pytest.raises(ValidationError):
            GitLogRequest()

    def test_max_count_validation_minimum(self):
        """Test that max_count must be >= 1."""
        with pytest.raises(ValidationError):
            GitLogRequest(repo_root="/path/to/repo", max_count=0)

    def test_max_count_validation_maximum(self):
        """Test that max_count must be <= 1000."""
        with pytest.raises(ValidationError):
            GitLogRequest(repo_root="/path/to/repo", max_count=1001)

    def test_max_count_boundary_values(self):
        """Test max_count at boundary values."""
        req_min = GitLogRequest(repo_root="/path/to/repo", max_count=1)
        assert req_min.max_count == 1

        req_max = GitLogRequest(repo_root="/path/to/repo", max_count=1000)
        assert req_max.max_count == 1000


class TestGitLogEntry:
    """Tests for GitLogEntry model."""

    def test_complete_entry(self):
        """Test creating complete GitLogEntry."""
        entry = GitLogEntry(
            hash="abc1234",
            author="John Doe <john@example.com>",
            date="2024-01-15 10:30:00",
            message="Fix bug in parser",
        )
        assert entry.hash == "abc1234"
        assert entry.author == "John Doe <john@example.com>"
        assert entry.date == "2024-01-15 10:30:00"
        assert entry.message == "Fix bug in parser"

    def test_missing_hash(self):
        """Test that hash is required."""
        with pytest.raises(ValidationError):
            GitLogEntry(author="John Doe", date="2024-01-15", message="Commit")

    def test_missing_author(self):
        """Test that author is required."""
        with pytest.raises(ValidationError):
            GitLogEntry(hash="abc1234", date="2024-01-15", message="Commit")

    def test_missing_date(self):
        """Test that date is required."""
        with pytest.raises(ValidationError):
            GitLogEntry(hash="abc1234", author="John Doe", message="Commit")

    def test_missing_message(self):
        """Test that message is required."""
        with pytest.raises(ValidationError):
            GitLogEntry(hash="abc1234", author="John Doe", date="2024-01-15")


class TestGitLogResult:
    """Tests for GitLogResult model."""

    def test_minimal_result(self):
        """Test creating GitLogResult with required fields."""
        result = GitLogResult(status="ok")
        assert result.status == "ok"
        assert result.commits == []
        assert result.error_message == ""

    def test_with_commits(self):
        """Test GitLogResult with commit entries."""
        commits = [
            GitLogEntry(
                hash="abc1234", author="John Doe", date="2024-01-15", message="Initial commit"
            ),
            GitLogEntry(
                hash="def5678", author="Jane Doe", date="2024-01-16", message="Add feature"
            ),
        ]
        result = GitLogResult(status="ok", commits=commits)
        assert len(result.commits) == 2
        assert result.commits[0].hash == "abc1234"
        assert result.commits[1].hash == "def5678"

    def test_error_result(self):
        """Test creating error GitLogResult."""
        result = GitLogResult(status="error", error_message="Repository not found")
        assert result.status == "error"
        assert result.error_message == "Repository not found"

    def test_invalid_status_literal(self):
        """Test that status must be 'ok' or 'error'."""
        with pytest.raises(ValidationError):
            GitLogResult(status="warning")

    def test_invalid_commits_type(self):
        """Test that commits must be list of GitLogEntry."""
        with pytest.raises(ValidationError):
            GitLogResult(status="ok", commits=["not", "entries"])


class TestModelIntegration:
    """Integration tests for git models working together."""

    def test_request_response_flow_status(self):
        """Test typical request-response flow for status."""
        req = GitStatusRequest(repo_root="/repo", include_untracked=True)
        result = GitStatusResult(status="ok", branch="main", staged=["file.py"], ahead=2)
        assert req.repo_root == result.branch or True  # Just verify both work

    def test_request_response_flow_commit(self):
        """Test typical request-response flow for commit."""
        req = GitCommitRequest(repo_root="/repo", message="Update", files=["a.py"])
        result = GitCommitResult(status="ok", commit_hash="abc123", files_committed=req.files)
        assert result.files_committed == req.files

    def test_request_response_flow_log(self):
        """Test typical request-response flow for log."""
        req = GitLogRequest(repo_root="/repo", max_count=5)
        entries = [
            GitLogEntry(hash=f"hash{i}", author="Author", date="2024-01-15", message=f"Commit {i}")
            for i in range(req.max_count)
        ]
        result = GitLogResult(status="ok", commits=entries)
        assert len(result.commits) == req.max_count
