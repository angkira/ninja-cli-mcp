"""
Unit tests for ninja_secretary tools.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch

from ninja_secretary.models import (
    AnalyseFileRequest,
    CodebaseReportRequest,
    DocumentSummaryRequest,
    FileSearchRequest,
    SessionReportRequest,
    UpdateDocRequest,
)
from ninja_secretary.tools import SecretaryToolExecutor, get_executor


@pytest.fixture
def executor():
    """Create a SecretaryToolExecutor instance with mocked dependencies."""
    return SecretaryToolExecutor()


@pytest.fixture
def mock_rate_balancer():
    """Mock rate balancer."""
    with patch("ninja_secretary.tools.get_rate_balancer") as mock:
        mock.return_value = Mock()
        mock.return_value.execute_with_retry = AsyncMock(
            side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)
        )
        yield mock.return_value


class TestSecretaryToolExecutor:
    """Tests for SecretaryToolExecutor."""

    @pytest.mark.asyncio
    async def test_analyse_file(self, executor, mock_rate_balancer):
        """Test analyse_file method."""
        request = AnalyseFileRequest(file_path="src/main.py")
        
        # Mock the actual implementation
        with patch.object(executor, '_analyse_file_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "content": "file content"}
            
            result = await executor.analyse_file(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.content == "file content"

    @pytest.mark.asyncio
    async def test_file_search(self, executor, mock_rate_balancer):
        """Test file_search method."""
        request = FileSearchRequest(pattern="**/*.py", repo_root="/test")
        
        # Mock the actual implementation
        with patch.object(executor, '_file_search_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "files": ["test.py"]}
            
            result = await executor.file_search(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.files == ["test.py"]

    @pytest.mark.asyncio
    async def test_codebase_report(self, executor, mock_rate_balancer):
        """Test codebase_report method."""
        request = CodebaseReportRequest(repo_root="/test")
        
        # Mock the actual implementation
        with patch.object(executor, '_codebase_report_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "report": "report content"}
            
            result = await executor.codebase_report(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.report == "report content"

    @pytest.mark.asyncio
    async def test_document_summary(self, executor, mock_rate_balancer):
        """Test document_summary method."""
        request = DocumentSummaryRequest(repo_root="/test")
        
        # Mock the actual implementation
        with patch.object(executor, '_document_summary_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "summary": "doc summary"}
            
            result = await executor.document_summary(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.summary == "doc summary"

    @pytest.mark.asyncio
    async def test_session_report(self, executor, mock_rate_balancer):
        """Test session_report method."""
        request = SessionReportRequest(session_id="test-session")
        
        # Mock the actual implementation
        with patch.object(executor, '_session_report_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "report": "session report"}
            
            result = await executor.session_report(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.report == "session report"

    @pytest.mark.asyncio
    async def test_update_doc(self, executor, mock_rate_balancer):
        """Test update_doc method."""
        request = UpdateDocRequest(
            module_name="coder",
            doc_type="readme",
            content="New content"
        )
        
        # Mock the actual implementation
        with patch.object(executor, '_update_doc_impl') as mock_impl:
            mock_impl.return_value = {"status": "success", "message": "Updated"}
            
            result = await executor.update_doc(request)
            
            mock_impl.assert_called_once_with(request)
            assert result.status == "success"
            assert result.message == "Updated"


def test_get_executor():
    """Test get_executor function."""
    executor1 = get_executor()
    executor2 = get_executor()
    
    # Should return the same instance (singleton)
    assert executor1 is executor2
    assert isinstance(executor1, SecretaryToolExecutor)
