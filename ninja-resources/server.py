import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool


# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define tools
TOOLS = [
    Tool(
        name="list_resources",
        description="List all available resources",
        inputSchema={
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Optional filter for resource types"
                }
            },
            "required": []
        }
    ),
    Tool(
        name="get_resource",
        description="Get details of a specific resource",
        inputSchema={
            "type": "object",
            "properties": {
                "resource_id": {
                    "type": "string",
                    "description": "ID of the resource to retrieve"
                }
            },
            "required": ["resource_id"]
        }
    ),
    Tool(
        name="create_resource",
        description="Create a new resource",
        inputSchema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Name of the resource"
                },
                "type": {
                    "type": "string",
                    "description": "Type of the resource"
                },
                "content": {
                    "type": "string",
                    "description": "Content of the resource"
                }
            },
            "required": ["name", "type", "content"]
        }
    )
]

def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("ninja-resources")
    
    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List all available tools."""
        return TOOLS
    
    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Execute a tool with the given arguments."""
        try:
            result = await executor(name, arguments)
            return [TextContent(type="text", text=result)]
        except Exception as e:
            logger.error(f"Error executing tool {name}: {e!s}")
            return [TextContent(type="text", text=f"Error: {e!s}")]
    
    return server

async def executor(name: str, arguments: dict[str, Any]) -> str:
    """Execute the requested tool."""
    logger.info(f"Executing tool: {name} with arguments: {arguments}")
    
    if name == "list_resources":
        filter_type = arguments.get("filter", "")
        # Simulate resource listing
        resources = [
            {"id": "1", "name": "Document 1", "type": "document"},
            {"id": "2", "name": "Spreadsheet 1", "type": "spreadsheet"},
            {"id": "3", "name": "Presentation 1", "type": "presentation"}
        ]
        
        if filter_type:
            resources = [r for r in resources if r["type"] == filter_type]
            
        return json.dumps(resources, indent=2)
    
    elif name == "get_resource":
        resource_id = arguments.get("resource_id")
        if not resource_id:
            raise ValueError("Resource ID is required")
        
        # Simulate resource retrieval
        resource = {
            "id": resource_id,
            "name": f"Resource {resource_id}",
            "type": "document",
            "content": f"Content of resource {resource_id}",
            "created": "2023-01-01T00:00:00Z"
        }
        return json.dumps(resource, indent=2)
    
    elif name == "create_resource":
        name = arguments.get("name")
        type_ = arguments.get("type")
        content = arguments.get("content")
        
        if not all([name, type_, content]):
            missing = [k for k, v in {"name": name, "type": type_, "content": content}.items() if not v]
            raise ValueError(f"Missing required arguments: {', '.join(missing)}")
        
        # Simulate resource creation
        new_resource = {
            "id": "new-123",
            "name": name,
            "type": type_,
            "content": content,
            "created": "2023-01-01T00:00:00Z"
        }
        return f"Created resource:\n{json.dumps(new_resource, indent=2)}"
    
    else:
        raise ValueError(f"Unknown tool: {name}")

async def main_stdio():
    """Run the server using stdio."""
    server = create_server()
    await server.run_stdio()

async def main_http():
    """Run the server using HTTP."""
    server = create_server()
    await server.run_http(host="localhost", port=3003)

def run():
    """Run the server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Ninja Resources Server")
    parser.add_argument("--http", action="store_true", help="Run as HTTP server")
    args = parser.parse_args()
    
    if args.http:
        asyncio.run(main_http())
    else:
        asyncio.run(main_stdio())

if __name__ == "__main__":
    run()
