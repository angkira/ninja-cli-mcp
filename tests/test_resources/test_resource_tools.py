"""Tests for resource tools."""

import pytest
from unittest.mock import AsyncMock, patch

from ninja_resources.tools import ResourceToolExecutor, get_executor
from ninja_resources.models import (
    ResourceCodebaseRequest,
    ResourceConfigRequest,
    ResourceDocsRequest,
)


class TestResourceToolExecutor:
    """Tests for ResourceToolExecutor class."""

    @pytest.fixture
    def executor(self) -> ResourceToolExecutor:
        """Create a ResourceToolExecutor instance for testing."""
        return ResourceToolExecutor()

    def test_singleton_pattern(self) -> None:
        """Test that get_executor returns singleton instance."""
        # Reset the singleton instance
        from ninja_resources.tools import _executor_instance
        import ninja_resources.tools
        ninja_resources.tools._executor_instance = None

        executor1 = get_executor()
        executor2 = get_executor()
        assert executor1 is executor2
        assert isinstance(executor1, ResourceToolExecutor)

    @pytest.mark.asyncio
    async def test_resource_codebase_success(self, executor: ResourceToolExecutor) -> None:
        """Test resource_codebase method with successful execution."""
        request = ResourceCodebaseRequest(
            repo_root="/test/repo"
        )
        
        # Mock the manager's load_codebase method
        with patch.object(executor.manager, 'load_codebase', new=AsyncMock()) as mock_load:
            mock_load.return_value = {
                "summary": "Test summary",
                "structure": {"files": [], "directories": []},
                "files": []
            }
            
            result = await executor.resource_codebase(request)
            assert result.status == "ok"
            assert result.summary == "Test summary"
            assert result.resource_id.startswith("codebase-")

    @pytest.mark.asyncio
    async def test_resource_config_success(self, executor: ResourceToolExecutor) -> None:
        """Test resource_config method with successful execution."""
        request = ResourceConfigRequest(
            repo_root="/test/repo"
        )
        
        # Mock the manager's load_config method
        with patch.object(executor.manager, 'load_config', new=AsyncMock()) as mock_load:
            mock_load.return_value = {
                "files": []
            }
            
            result = await executor.resource_config(request)
            assert result.status == "ok"
            assert result.resource_id.startswith("config-")

    @pytest.mark.asyncio
    async def test_resource_docs_success(self, executor: ResourceToolExecutor) -> None:
        """Test resource_docs method with successful execution."""
        request = ResourceDocsRequest(
            repo_root="/test/repo"
        )
        
        # Mock the manager's load_docs method
        with patch.object(executor.manager, 'load_docs', new=AsyncMock()) as mock_load:
            mock_load.return_value = {
                "entries": []
            }
            
            result = await executor.resource_docs(request)
            assert result.status == "ok"
            assert result.resource_id.startswith("docs-")


if __name__ == "__main__":
    pytest.main([__file__])
