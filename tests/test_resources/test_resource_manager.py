"""Tests for resource manager."""

import pytest
from unittest.mock import AsyncMock, patch

from ninja_resources.resource_manager import ResourceManager


class TestResourceManager:
    """Tests for ResourceManager class."""

    @pytest.fixture
    def manager(self) -> ResourceManager:
        """Create a ResourceManager instance for testing."""
        return ResourceManager()

    @pytest.mark.asyncio
    async def test_load_codebase(self, manager: ResourceManager) -> None:
        """Test load_codebase method."""
        result = await manager.load_codebase("/test/repo")
        assert isinstance(result, dict)
        assert "summary" in result
        assert "structure" in result
        assert "files" in result

    @pytest.mark.asyncio
    async def test_load_config(self, manager: ResourceManager) -> None:
        """Test load_config method."""
        result = await manager.load_config("/test/repo")
        assert isinstance(result, dict)
        assert "files" in result

    @pytest.mark.asyncio
    async def test_load_docs(self, manager: ResourceManager) -> None:
        """Test load_docs method."""
        result = await manager.load_docs("/test/repo")
        assert isinstance(result, dict)
        assert "entries" in result


if __name__ == "__main__":
    pytest.main([__file__])
