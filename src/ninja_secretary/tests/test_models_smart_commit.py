"""
Unit tests for smart commit models.

Tests the SmartCommitRequest, CommitSuggestion, and SmartCommitResult models.
"""

import pytest
from pydantic import ValidationError

from src.ninja_secretary.models import (
    CommitSuggestion,
    SmartCommitRequest,
    SmartCommitResult,
)


class TestSmartCommitRequest:
    """Tests for SmartCommitRequest model."""

    def test_smart_commit_request_minimal(self):
        """Test SmartCommitRequest with only required fields."""
        request = SmartCommitRequest(repo_root="/path/to/repo")
        assert request.repo_root == "/path/to/repo"
        assert request.include_untracked is False
        assert request.dry_run is False
        assert request.author is None

    def test_smart_commit_request_all_fields(self):
        """Test SmartCommitRequest with all fields specified."""
        request = SmartCommitRequest(
            repo_root="/path/to/repo",
            include_untracked=True,
            dry_run=True,
            author="John Doe <john@example.com>",
        )
        assert request.repo_root == "/path/to/repo"
        assert request.include_untracked is True
        assert request.dry_run is True
        assert request.author == "John Doe <john@example.com>"

    def test_smart_commit_request_missing_repo_root(self):
        """Test SmartCommitRequest fails without repo_root."""
        with pytest.raises(ValidationError):
            SmartCommitRequest()

    def test_smart_commit_request_dry_run_true(self):
        """Test SmartCommitRequest with dry_run enabled."""
        request = SmartCommitRequest(repo_root="/repo", dry_run=True)
        assert request.dry_run is True

    def test_smart_commit_request_include_untracked_true(self):
        """Test SmartCommitRequest with include_untracked enabled."""
        request = SmartCommitRequest(repo_root="/repo", include_untracked=True)
        assert request.include_untracked is True

    def test_smart_commit_request_author_override(self):
        """Test SmartCommitRequest with author override."""
        author = "Jane Smith <jane@example.com>"
        request = SmartCommitRequest(repo_root="/repo", author=author)
        assert request.author == author

    def test_smart_commit_request_field_descriptions(self):
        """Test that all fields have descriptions."""
        schema = SmartCommitRequest.model_json_schema()
        properties = schema["properties"]
        
        assert "description" in properties["repo_root"]
        assert "description" in properties["include_untracked"]
        assert "description" in properties["dry_run"]
        assert "description" in properties["author"]


class TestCommitSuggestion:
    """Tests for CommitSuggestion model."""

    def test_commit_suggestion_basic(self):
        """Test CommitSuggestion with basic data."""
        suggestion = CommitSuggestion(
            files=["src/main.py", "src/utils.py"],
            message="Add new utility functions",
            reasoning="These files are related to utility functions",
        )
        assert suggestion.files == ["src/main.py", "src/utils.py"]
        assert suggestion.message == "Add new utility functions"
        assert suggestion.reasoning == "These files are related to utility functions"

    def test_commit_suggestion_single_file(self):
        """Test CommitSuggestion with a single file."""
        suggestion = CommitSuggestion(
            files=["README.md"],
            message="Update documentation",
            reasoning="Documentation update",
        )
        assert suggestion.files == ["README.md"]
        assert len(suggestion.files) == 1

    def test_commit_suggestion_multiple_files(self):
        """Test CommitSuggestion with multiple files."""
        files = ["file1.py", "file2.py", "file3.py", "file4.py"]
        suggestion = CommitSuggestion(
            files=files,
            message="Refactor module",
            reasoning="All files are part of the same module",
        )
        assert suggestion.files == files
        assert len(suggestion.files) == 4

    def test_commit_suggestion_empty_files_list(self):
        """Test CommitSuggestion with empty files list."""
        suggestion = CommitSuggestion(
            files=[],
            message="Empty commit",
            reasoning="No files",
        )
        assert suggestion.files == []

    def test_commit_suggestion_missing_files(self):
        """Test CommitSuggestion fails without files."""
        with pytest.raises(ValidationError):
            CommitSuggestion(
                message="Test",
                reasoning="Test",
            )

    def test_commit_suggestion_missing_message(self):
        """Test CommitSuggestion fails without message."""
        with pytest.raises(ValidationError):
            CommitSuggestion(
                files=["test.py"],
                reasoning="Test",
            )

    def test_commit_suggestion_missing_reasoning(self):
        """Test CommitSuggestion fails without reasoning."""
        with pytest.raises(ValidationError):
            CommitSuggestion(
                files=["test.py"],
                message="Test",
            )

    def test_commit_suggestion_long_message(self):
        """Test CommitSuggestion with a long commit message."""
        long_message = "This is a very long commit message that describes " \
                      "multiple changes across the codebase in great detail"
        suggestion = CommitSuggestion(
            files=["file.py"],
            message=long_message,
            reasoning="Long message test",
        )
        assert suggestion.message == long_message

    def test_commit_suggestion_field_descriptions(self):
        """Test that all fields have descriptions."""
        schema = CommitSuggestion.model_json_schema()
        properties = schema["properties"]
        
        assert "description" in properties["files"]
        assert "description" in properties["message"]
        assert "description" in properties["reasoning"]


class TestSmartCommitResult:
    """Tests for SmartCommitResult model."""

    def test_smart_commit_result_success(self):
        """Test SmartCommitResult with successful status."""
        result = SmartCommitResult(status="ok")
        assert result.status == "ok"
        assert result.suggestions == []
        assert result.commits_created == 0
        assert result.error_message == ""

    def test_smart_commit_result_error(self):
        """Test SmartCommitResult with error status."""
        result = SmartCommitResult(
            status="error",
            error_message="Failed to analyze repository",
        )
        assert result.status == "error"
        assert result.error_message == "Failed to analyze repository"

    def test_smart_commit_result_with_suggestions(self):
        """Test SmartCommitResult with commit suggestions."""
        suggestions = [
            CommitSuggestion(
                files=["src/main.py"],
                message="Add main function",
                reasoning="Core functionality",
            ),
            CommitSuggestion(
                files=["tests/test_main.py"],
                message="Add tests for main",
                reasoning="Test coverage",
            ),
        ]
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
        )
        assert result.status == "ok"
        assert len(result.suggestions) == 2
        assert result.suggestions[0].message == "Add main function"
        assert result.suggestions[1].message == "Add tests for main"

    def test_smart_commit_result_commits_created(self):
        """Test SmartCommitResult with commits_created count."""
        result = SmartCommitResult(
            status="ok",
            commits_created=3,
        )
        assert result.commits_created == 3

    def test_smart_commit_result_dry_run_no_commits(self):
        """Test SmartCommitResult for dry_run (no commits created)."""
        suggestions = [
            CommitSuggestion(
                files=["file.py"],
                message="Test",
                reasoning="Test",
            ),
        ]
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
            commits_created=0,  # dry_run means no actual commits
        )
        assert result.commits_created == 0
        assert len(result.suggestions) == 1

    def test_smart_commit_result_actual_commits(self):
        """Test SmartCommitResult with actual commits created."""
        suggestions = [
            CommitSuggestion(
                files=["file1.py"],
                message="Commit 1",
                reasoning="Reason 1",
            ),
            CommitSuggestion(
                files=["file2.py"],
                message="Commit 2",
                reasoning="Reason 2",
            ),
        ]
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
            commits_created=2,
        )
        assert result.commits_created == 2
        assert len(result.suggestions) == 2

    def test_smart_commit_result_missing_status(self):
        """Test SmartCommitResult fails without status."""
        with pytest.raises(ValidationError):
            SmartCommitResult()

    def test_smart_commit_result_invalid_status(self):
        """Test SmartCommitResult fails with invalid status."""
        with pytest.raises(ValidationError):
            SmartCommitResult(status="invalid")

    def test_smart_commit_result_field_descriptions(self):
        """Test that all fields have descriptions."""
        schema = SmartCommitResult.model_json_schema()
        properties = schema["properties"]
        
        assert "description" in properties["status"]
        assert "description" in properties["suggestions"]
        assert "description" in properties["commits_created"]
        assert "description" in properties["error_message"]

    def test_smart_commit_result_serialization(self):
        """Test SmartCommitResult can be serialized to JSON."""
        suggestions = [
            CommitSuggestion(
                files=["file.py"],
                message="Test commit",
                reasoning="Test reason",
            ),
        ]
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
            commits_created=1,
        )
        
        json_data = result.model_dump_json()
        assert "ok" in json_data
        assert "Test commit" in json_data
        assert "Test reason" in json_data

    def test_smart_commit_result_deserialization(self):
        """Test SmartCommitResult can be deserialized from JSON."""
        json_str = """{
            "status": "ok",
            "suggestions": [
                {
                    "files": ["file.py"],
                    "message": "Test",
                    "reasoning": "Test reason"
                }
            ],
            "commits_created": 1,
            "error_message": ""
        }"""
        
        result = SmartCommitResult.model_validate_json(json_str)
        assert result.status == "ok"
        assert len(result.suggestions) == 1
        assert result.commits_created == 1


class TestSmartCommitModelsIntegration:
    """Integration tests for smart commit models."""

    def test_request_to_result_workflow(self):
        """Test a complete workflow from request to result."""
        # Create a request
        request = SmartCommitRequest(
            repo_root="/path/to/repo",
            include_untracked=True,
            dry_run=False,
        )
        
        # Create suggestions based on request
        suggestions = [
            CommitSuggestion(
                files=["src/feature.py"],
                message="Add new feature",
                reasoning="Feature implementation",
            ),
        ]
        
        # Create result
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
            commits_created=1,
        )
        
        assert request.repo_root == "/path/to/repo"
        assert result.status == "ok"
        assert len(result.suggestions) == 1

    def test_multiple_suggestions_result(self):
        """Test SmartCommitResult with multiple suggestions."""
        suggestions = [
            CommitSuggestion(
                files=["file1.py", "file2.py"],
                message="Refactor utilities",
                reasoning="Code cleanup",
            ),
            CommitSuggestion(
                files=["tests/test_utils.py"],
                message="Add unit tests",
                reasoning="Test coverage",
            ),
            CommitSuggestion(
                files=["README.md"],
                message="Update documentation",
                reasoning="Documentation update",
            ),
        ]
        
        result = SmartCommitResult(
            status="ok",
            suggestions=suggestions,
            commits_created=3,
        )
        
        assert len(result.suggestions) == 3
        assert result.commits_created == 3
        assert all(s.files for s in result.suggestions)
