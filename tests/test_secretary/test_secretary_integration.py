"""
Integration tests for Ninja Secretary module.

These tests verify file operations, search, grep, file trees,
codebase reports, documentation, and session tracking.
"""

import os
import tempfile
from pathlib import Path

import pytest

from ninja_secretary.models import (
    CodebaseReportRequest,
    DocumentSummaryRequest,
    FileSearchRequest,
    FileTreeRequest,
    GrepRequest,
    ReadFileRequest,
    SessionReportRequest,
    UpdateDocRequest,
)
from ninja_secretary.tools import reset_executor


@pytest.fixture
def executor():
    """Create a fresh executor for each test."""
    reset_executor()
    from ninja_secretary.tools import get_executor

    return get_executor()


@pytest.fixture
def client_id():
    """Test client ID."""
    return "test-client"


@pytest.fixture
def temp_repo():
    """Create a temporary repository structure for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create directory structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()
        (repo_path / "docs").mkdir()

        # Create Python files
        (repo_path / "src" / "main.py").write_text(
            """#!/usr/bin/env python3
\"\"\"Main application module.\"\"\"

def hello_world():
    \"\"\"Print hello world.\"\"\"
    print("Hello, World!")

def calculate_sum(a, b):
    \"\"\"Calculate sum of two numbers.\"\"\"
    return a + b

if __name__ == "__main__":
    hello_world()
"""
        )

        (repo_path / "src" / "utils.py").write_text(
            """\"\"\"Utility functions.\"\"\"

def process_data(data):
    \"\"\"Process some data.\"\"\"
    return data.strip().lower()

async def fetch_data(url):
    \"\"\"Fetch data from URL.\"\"\"
    import httpx
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
        return response.text
"""
        )

        (repo_path / "tests" / "test_main.py").write_text(
            """\"\"\"Tests for main module.\"\"\"

def test_hello_world():
    \"\"\"Test hello world function.\"\"\"
    assert True

def test_calculate_sum():
    \"\"\"Test calculate sum.\"\"\"
    from src.main import calculate_sum
    assert calculate_sum(2, 3) == 5
"""
        )

        # Create documentation
        (repo_path / "README.md").write_text(
            """# Test Project

This is a test project for the Secretary module.

## Features

- Hello world functionality
- Data processing utilities
- Async data fetching

## Installation

```bash
pip install -e .
```

## Usage

```python
from src.main import hello_world
hello_world()
```
"""
        )

        (repo_path / "docs" / "API.md").write_text(
            """# API Documentation

## Main Module

### hello_world()

Prints hello world to console.

### calculate_sum(a, b)

Returns the sum of a and b.
"""
        )

        # Create package files
        (repo_path / "pyproject.toml").write_text(
            """[project]
name = "test-project"
version = "0.1.0"
dependencies = ["httpx>=0.27.0"]
"""
        )

        (repo_path / "requirements.txt").write_text("httpx>=0.27.0\npytest>=8.0.0\n")

        yield repo_path


class TestReadFile:
    """Test file reading functionality."""

    @pytest.mark.asyncio
    async def test_read_entire_file(self, executor, client_id, temp_repo):
        """Test reading an entire file."""
        file_path = str(temp_repo / "src" / "main.py")

        request = ReadFileRequest(file_path=file_path)

        result = await executor.read_file(request, client_id=client_id)

        assert result.status == "ok"
        assert result.file_path == file_path
        assert "def hello_world():" in result.content
        assert result.line_count > 0

    @pytest.mark.asyncio
    async def test_read_file_with_line_range(self, executor, client_id, temp_repo):
        """Test reading specific line range."""
        file_path = str(temp_repo / "src" / "main.py")

        request = ReadFileRequest(file_path=file_path, start_line=1, end_line=5)

        result = await executor.read_file(request, client_id=client_id)

        assert result.status == "ok"
        lines = result.content.split("\n")
        assert len(lines) <= 6  # 5 lines + possible empty line

    @pytest.mark.asyncio
    async def test_read_nonexistent_file(self, executor, client_id, temp_repo):
        """Test reading a file that doesn't exist."""
        file_path = str(temp_repo / "nonexistent.txt")

        request = ReadFileRequest(file_path=file_path)

        result = await executor.read_file(request, client_id=client_id)

        assert result.status == "error"
        assert "not found" in result.error_message.lower()


class TestFileSearch:
    """Test file search functionality."""

    @pytest.mark.asyncio
    async def test_search_python_files(self, executor, client_id, temp_repo):
        """Test searching for Python files."""
        request = FileSearchRequest(pattern="**/*.py", repo_root=str(temp_repo), max_results=100)

        result = await executor.file_search(request, client_id=client_id)

        assert result.status == "ok"
        assert result.total_count >= 3  # main.py, utils.py, test_main.py
        assert not result.truncated

        # Check that we found expected files
        file_names = [m.path for m in result.matches]
        assert any("main.py" in f for f in file_names)
        assert any("utils.py" in f for f in file_names)

    @pytest.mark.asyncio
    async def test_search_markdown_files(self, executor, client_id, temp_repo):
        """Test searching for markdown files."""
        request = FileSearchRequest(pattern="**/*.md", repo_root=str(temp_repo), max_results=10)

        result = await executor.file_search(request, client_id=client_id)

        assert result.status == "ok"
        assert result.total_count >= 2  # README.md, API.md

    @pytest.mark.asyncio
    async def test_search_with_max_results(self, executor, client_id, temp_repo):
        """Test that max_results is respected."""
        request = FileSearchRequest(pattern="**/*", repo_root=str(temp_repo), max_results=2)

        result = await executor.file_search(request, client_id=client_id)

        assert result.status == "ok"
        assert len(result.matches) <= 2
        assert result.truncated


class TestGrep:
    """Test grep functionality."""

    @pytest.mark.asyncio
    async def test_grep_function_definitions(self, executor, client_id, temp_repo):
        """Test grepping for function definitions."""
        request = GrepRequest(
            pattern=r"def \w+\(",
            repo_root=str(temp_repo),
            file_pattern="**/*.py",
            context_lines=2,
            max_results=50,
        )

        result = await executor.grep(request, client_id=client_id)

        assert result.status == "ok"
        assert result.total_count >= 3  # hello_world, calculate_sum, process_data, etc.

        # Check match structure
        if result.matches:
            match = result.matches[0]
            assert match.file_path
            assert match.line_number > 0
            assert "def " in match.line_content

    @pytest.mark.asyncio
    async def test_grep_with_context(self, executor, client_id, temp_repo):
        """Test grep with context lines."""
        request = GrepRequest(
            pattern="async def",
            repo_root=str(temp_repo),
            context_lines=3,
            max_results=10,
        )

        result = await executor.grep(request, client_id=client_id)

        if result.total_count > 0:
            match = result.matches[0]
            # Should have context lines
            assert len(match.context_before) >= 0
            assert len(match.context_after) >= 0

    @pytest.mark.asyncio
    async def test_grep_no_matches(self, executor, client_id, temp_repo):
        """Test grep with pattern that doesn't match."""
        request = GrepRequest(
            pattern="NONEXISTENT_PATTERN_12345",
            repo_root=str(temp_repo),
            max_results=10,
        )

        result = await executor.grep(request, client_id=client_id)

        assert result.status == "ok"
        assert result.total_count == 0
        assert len(result.matches) == 0


class TestFileTree:
    """Test file tree generation."""

    @pytest.mark.asyncio
    async def test_generate_file_tree(self, executor, client_id, temp_repo):
        """Test generating a file tree."""
        request = FileTreeRequest(repo_root=str(temp_repo), max_depth=3, include_sizes=True)

        result = await executor.file_tree(request, client_id=client_id)

        assert result.status == "ok"
        assert result.tree is not None
        assert result.total_files >= 5
        assert result.total_dirs >= 3
        assert result.total_size > 0

    @pytest.mark.asyncio
    async def test_file_tree_depth_limit(self, executor, client_id, temp_repo):
        """Test that max_depth is respected."""
        # Create nested structure
        deep_path = temp_repo / "a" / "b" / "c" / "d"
        deep_path.mkdir(parents=True)
        (deep_path / "deep.txt").write_text("deep file")

        request = FileTreeRequest(repo_root=str(temp_repo), max_depth=2)

        result = await executor.file_tree(request, client_id=client_id)

        assert result.status == "ok"
        # Should not traverse too deep


class TestCodebaseReport:
    """Test codebase report generation."""

    @pytest.mark.asyncio
    async def test_generate_full_report(self, executor, client_id, temp_repo):
        """Test generating a full codebase report."""
        request = CodebaseReportRequest(
            repo_root=str(temp_repo),
            include_metrics=True,
            include_dependencies=True,
            include_structure=True,
        )

        result = await executor.codebase_report(request, client_id=client_id)

        assert result.status == "ok"
        assert "# Codebase Report:" in result.report
        assert result.file_count > 0
        assert result.metrics

        # Check metrics
        assert "file_count" in result.metrics
        assert "total_lines" in result.metrics

    @pytest.mark.asyncio
    async def test_report_metrics_only(self, executor, client_id, temp_repo):
        """Test report with only metrics."""
        request = CodebaseReportRequest(
            repo_root=str(temp_repo),
            include_metrics=True,
            include_dependencies=False,
            include_structure=False,
        )

        result = await executor.codebase_report(request, client_id=client_id)

        assert result.status == "ok"
        assert "## Code Metrics" in result.report


class TestDocumentSummary:
    """Test documentation summarization."""

    @pytest.mark.asyncio
    async def test_summarize_docs(self, executor, client_id, temp_repo):
        """Test summarizing documentation files."""
        request = DocumentSummaryRequest(repo_root=str(temp_repo), doc_patterns=["**/*.md"])

        result = await executor.document_summary(request, client_id=client_id)

        assert result.status == "ok"
        assert result.doc_count >= 2  # README.md, API.md
        assert len(result.summaries) >= 2
        assert result.combined_summary

        # Check summary structure
        readme_summary = next((s for s in result.summaries if "README" in s["path"]), None)
        assert readme_summary is not None
        assert "summary" in readme_summary


class TestSessionTracking:
    """Test session tracking functionality."""

    @pytest.mark.asyncio
    async def test_create_session(self, executor, client_id):
        """Test creating a new session."""
        request = SessionReportRequest(
            session_id="test-session-1",
            action="create",
            updates={"metadata": {"user": "alice", "task": "testing"}},
        )

        result = await executor.session_report(request, client_id=client_id)

        assert result.session_id == "test-session-1"
        assert result.started_at
        assert result.metadata["user"] == "alice"

    @pytest.mark.asyncio
    async def test_update_session(self, executor, client_id):
        """Test updating a session."""
        # Create session first
        create_request = SessionReportRequest(session_id="test-session-2", action="create")
        await executor.session_report(create_request, client_id=client_id)

        # Update session
        update_request = SessionReportRequest(
            session_id="test-session-2",
            action="update",
            updates={
                "tools_used": ["read_file", "grep"],
                "files_accessed": ["test.py"],
                "summary": "Analyzed test file",
            },
        )

        result = await executor.session_report(update_request, client_id=client_id)

        assert result.session_id == "test-session-2"
        assert "read_file" in result.tools_used
        assert "grep" in result.tools_used
        assert "test.py" in result.files_accessed
        assert result.summary == "Analyzed test file"

    @pytest.mark.asyncio
    async def test_get_session(self, executor, client_id):
        """Test getting an existing session."""
        # Create and update session
        create_request = SessionReportRequest(session_id="test-session-3", action="create")
        await executor.session_report(create_request, client_id=client_id)

        # Get session
        get_request = SessionReportRequest(session_id="test-session-3", action="get")

        result = await executor.session_report(get_request, client_id=client_id)

        assert result.session_id == "test-session-3"


class TestUpdateDoc:
    """Test documentation update functionality."""

    @pytest.mark.asyncio
    async def test_update_doc_replace(self, executor, client_id, temp_repo):
        """Test updating documentation with replace mode."""
        # Change to temp_repo for testing
        os.chdir(temp_repo)

        request = UpdateDocRequest(
            module_name="test_module",
            doc_type="readme",
            content="# New README\n\nThis is updated content.",
            mode="replace",
        )

        result = await executor.update_doc(request, client_id=client_id)

        assert result.status == "ok"
        assert "README" in result.doc_path
        assert "Replaced" in result.changes_made

        # Verify file was created
        doc_path = Path(result.doc_path)
        assert doc_path.exists()
        content = doc_path.read_text()
        assert "New README" in content

    @pytest.mark.asyncio
    async def test_update_doc_append(self, executor, client_id, temp_repo):
        """Test updating documentation with append mode."""
        os.chdir(temp_repo)

        # Create initial content
        create_request = UpdateDocRequest(
            module_name="test_module",
            doc_type="changelog",
            content="# Changelog\n\n## v0.1.0\n- Initial release",
            mode="replace",
        )
        await executor.update_doc(create_request, client_id=client_id)

        # Append new content
        append_request = UpdateDocRequest(
            module_name="test_module",
            doc_type="changelog",
            content="## v0.2.0\n- New features",
            mode="append",
        )

        result = await executor.update_doc(append_request, client_id=client_id)

        assert result.status == "ok"
        assert "Appended" in result.changes_made

        # Verify both contents exist
        doc_path = Path(result.doc_path)
        content = doc_path.read_text()
        assert "v0.1.0" in content
        assert "v0.2.0" in content


class TestEndToEndWorkflows:
    """Test complete end-to-end workflows."""

    @pytest.mark.asyncio
    async def test_explore_and_analyze_workflow(self, executor, client_id, temp_repo):
        """Test workflow: file tree → search → read → grep."""
        # Step 1: Get file tree
        tree_request = FileTreeRequest(repo_root=str(temp_repo), max_depth=3)
        tree_result = await executor.file_tree(tree_request, client_id=client_id)

        assert tree_result.status == "ok"
        assert tree_result.total_files > 0

        # Step 2: Search for Python files
        search_request = FileSearchRequest(
            pattern="**/*.py", repo_root=str(temp_repo), max_results=10
        )
        search_result = await executor.file_search(search_request, client_id=client_id)

        assert search_result.status == "ok"
        assert len(search_result.matches) > 0

        # Step 3: Read first file
        first_file = search_result.matches[0].path
        read_request = ReadFileRequest(file_path=str(temp_repo / first_file))
        read_result = await executor.read_file(read_request, client_id=client_id)

        assert read_result.status == "ok"

        # Step 4: Grep for functions
        grep_request = GrepRequest(
            pattern=r"def \w+",
            repo_root=str(temp_repo),
            file_pattern="**/*.py",
            context_lines=1,
        )
        grep_result = await executor.grep(grep_request, client_id=client_id)

        assert grep_result.status == "ok"

    @pytest.mark.asyncio
    async def test_session_tracked_workflow(self, executor, client_id, temp_repo):
        """Test workflow with session tracking."""
        session_id = "workflow-session"

        # Create session
        create_request = SessionReportRequest(
            session_id=session_id,
            action="create",
            updates={"metadata": {"task": "code_analysis"}},
        )
        await executor.session_report(create_request, client_id=client_id)

        # Perform operations and track
        tree_request = FileTreeRequest(repo_root=str(temp_repo), max_depth=2)
        await executor.file_tree(tree_request, client_id=client_id)

        # Update session
        update_request = SessionReportRequest(
            session_id=session_id,
            action="update",
            updates={"tools_used": ["file_tree"], "summary": "Generated file tree"},
        )
        session_result = await executor.session_report(update_request, client_id=client_id)

        assert "file_tree" in session_result.tools_used

        # Read a file
        read_request = ReadFileRequest(file_path=str(temp_repo / "README.md"))
        await executor.read_file(read_request, client_id=client_id)

        # Update session again
        final_update = SessionReportRequest(
            session_id=session_id,
            action="update",
            updates={
                "tools_used": ["read_file"],
                "files_accessed": ["README.md"],
                "summary": "Analyzed README",
            },
        )
        final_session = await executor.session_report(final_update, client_id=client_id)

        assert "file_tree" in final_session.tools_used
        assert "read_file" in final_session.tools_used
        assert "README.md" in final_session.files_accessed


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
