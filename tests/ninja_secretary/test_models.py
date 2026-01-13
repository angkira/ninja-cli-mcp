"""
Unit tests for ninja_secretary models.
"""

import pytest
from ninja_secretary.models import (
    AnalyseFileRequest,
    CodebaseReportRequest,
    DocumentSummaryRequest,
    FileSearchRequest,
    SessionReportRequest,
    UpdateDocRequest,
)


def test_analyse_file_request():
    """Test AnalyseFileRequest model creation and validation."""
    # Test with required field only
    request = AnalyseFileRequest(file_path="src/main.py")
    assert request.file_path == "src/main.py"
    assert request.search_pattern is None
    assert request.include_structure is True
    assert request.include_preview is True

    # Test with all fields
    request = AnalyseFileRequest(
        file_path="src/main.py",
        search_pattern="def .*",
        include_structure=False,
        include_preview=False
    )
    assert request.file_path == "src/main.py"
    assert request.search_pattern == "def .*"
    assert request.include_structure is False
    assert request.include_preview is False


def test_analyse_file_request_validation():
    """Test AnalyseFileRequest model validation."""
    # Should fail without required file_path
    with pytest.raises(ValueError):
        AnalyseFileRequest()

    # Should work with file_path
    request = AnalyseFileRequest(file_path="test.py")
    assert request.file_path == "test.py"


def test_file_search_request():
    """Test FileSearchRequest model."""
    request = FileSearchRequest(
        pattern="**/*.py",
        repo_root="/path/to/repo"
    )
    assert request.pattern == "**/*.py"
    assert request.repo_root == "/path/to/repo"
    assert request.max_results == 100  # default value


def test_codebase_report_request():
    """Test CodebaseReportRequest model."""
    request = CodebaseReportRequest(repo_root="/path/to/repo")
    assert request.repo_root == "/path/to/repo"
    assert request.include_metrics is True  # default value


def test_document_summary_request():
    """Test DocumentSummaryRequest model."""
    request = DocumentSummaryRequest(repo_root="/path/to/repo")
    assert request.repo_root == "/path/to/repo"
    assert request.doc_patterns == ["**/*.md", "**/README*", "**/CONTRIBUTING*"]  # default value


def test_session_report_request():
    """Test SessionReportRequest model."""
    request = SessionReportRequest(session_id="test-session")
    assert request.session_id == "test-session"
    assert request.action == "get"  # default value


def test_update_doc_request():
    """Test UpdateDocRequest model."""
    request = UpdateDocRequest(
        module_name="coder",
        doc_type="readme",
        content="New content"
    )
    assert request.module_name == "coder"
    assert request.doc_type == "readme"
    assert request.content == "New content"
    assert request.mode == "replace"  # default value
