import pytest
from ninja_resources import server

@pytest.mark.asyncio
async def test_resource_registration():
    """Test that resources are properly registered"""
    assert len(server.resources_list) > 0
    # Test executing a resource
    # This would depend on what resources are actually defined

@pytest.mark.asyncio
async def test_prompt_registration():
    """Test that prompts are properly registered"""
    assert len(server.prompts_list) > 0
    # Test executing a prompt
    # This would depend on what prompts are actually defined

@pytest.mark.asyncio
async def test_tool_registration():
    """Test that tools are properly registered"""
    assert "resource_codebase" in server.tools_list
    assert "resource_config" in server.tools_list
    assert "resource_docs" in server.tools_list

@pytest.mark.asyncio
async def test_tool_execution():
    """Test that tools can be executed"""
    result = await server.execute_tool("resource_codebase", query="test")
    assert "test" in result
    
    result = await server.execute_tool("resource_config", config_key="test")
    assert "test" in result["key"]
    
    result = await server.execute_tool("resource_docs", doc_type="test")
    assert "test" in result

@pytest.mark.asyncio
async def test_tool_execution_error():
    """Test that executing non-existent tool raises error"""
    with pytest.raises(ValueError, match="Tool 'nonexistent' not found"):
        await server.execute_tool("nonexistent")
