import pytest
import json
from ninja_resources.server import create_server, executor

@pytest.fixture
def server():
    return create_server()

@pytest.mark.asyncio
async def test_list_resources():
    result = await executor("list_resources", {})
    assert isinstance(result, str)
    resources = json.loads(result)
    assert isinstance(resources, list)
    assert len(resources) > 0

@pytest.mark.asyncio
async def test_list_resources_with_filter():
    result = await executor("list_resources", {"filter": "document"})
    assert isinstance(result, str)
    resources = json.loads(result)
    assert isinstance(resources, list)
    # All resources should be of type "document"
    for resource in resources:
        assert resource["type"] == "document"

@pytest.mark.asyncio
async def test_get_resource():
    result = await executor("get_resource", {"resource_id": "test-123"})
    assert isinstance(result, str)
    resource = json.loads(result)
    assert resource["id"] == "test-123"

@pytest.mark.asyncio
async def test_get_resource_missing_id():
    with pytest.raises(ValueError, match="Resource ID is required"):
        await executor("get_resource", {})

@pytest.mark.asyncio
async def test_create_resource():
    args = {
        "name": "Test Resource",
        "type": "document",
        "content": "Test content"
    }
    result = await executor("create_resource", args)
    assert isinstance(result, str)
    assert "Created resource:" in result
    assert "Test Resource" in result

@pytest.mark.asyncio
async def test_create_resource_missing_args():
    with pytest.raises(ValueError, match="Missing required arguments"):
        await executor("create_resource", {"name": "Test"})

@pytest.mark.asyncio
async def test_unknown_tool():
    with pytest.raises(ValueError, match="Unknown tool"):
        await executor("unknown_tool", {})
