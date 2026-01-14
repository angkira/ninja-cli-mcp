"""MCP Server for Prompts module."""

import asyncio
import json
import sys
from typing import Any

from mcp import types
from mcp.server import Server
from mcp.server.stdio import stdio_server

from ninja_prompts.models import (
    PromptChainRequest,
    PromptRegistryRequest,
    PromptSuggestRequest,
)
from ninja_prompts.tools import PromptToolExecutor


# Initialize server
server = Server("ninja-prompts")

# Initialize executor
_executor = PromptToolExecutor()


# Define tools
TOOLS = [
    types.Tool(
        name="prompt_registry",
        description="Manage prompt templates: list, get, create, update, delete",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "get", "create", "update", "delete"],
                    "description": "Action to perform",
                },
                "prompt_id": {
                    "type": "string",
                    "description": "Prompt identifier (required for get/update/delete)",
                },
                "name": {
                    "type": "string",
                    "description": "Prompt name (required for create)",
                },
                "description": {
                    "type": "string",
                    "description": "Prompt description",
                },
                "template": {
                    "type": "string",
                    "description": "Prompt template with {{variable}} placeholders",
                },
                "variables": {
                    "type": "array",
                    "description": "List of template variables",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags for categorization",
                },
            },
            "required": ["action"],
        },
    ),
    types.Tool(
        name="prompt_suggest",
        description="Get AI-powered suggestions for relevant prompts based on context",
        inputSchema={
            "type": "object",
            "properties": {
                "context": {
                    "type": "object",
                    "description": "Context for suggestions (task, language, file_type, etc.)",
                },
                "max_suggestions": {
                    "type": "integer",
                    "description": "Maximum number of suggestions to return",
                },
            },
        },
    ),
    types.Tool(
        name="prompt_chain",
        description="Compose and execute multi-step prompt workflows",
        inputSchema={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["create", "execute"],
                    "description": "Action to perform",
                },
                "chain_id": {
                    "type": "string",
                    "description": "Unique chain identifier",
                },
                "steps": {
                    "type": "array",
                    "description": "List of workflow steps",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {
                                "type": "string",
                                "description": "Step name",
                            },
                            "prompt_id": {
                                "type": "string",
                                "description": "Prompt to execute",
                            },
                            "variables": {
                                "type": "object",
                                "description": "Variables for this step",
                            },
                        },
                    },
                },
            },
            "required": ["action"],
        },
    ),
]


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    """Return list of available tools."""
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> Any:
    """Route tool calls to executor."""
    try:
        if name == "prompt_registry":
            request = PromptRegistryRequest(**arguments)
            result = await _executor.prompt_registry(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "prompt_suggest":
            request = PromptSuggestRequest(**arguments)
            result = await _executor.prompt_suggest(request)
            return [types.TextContent(text=result.model_dump_json())]

        elif name == "prompt_chain":
            request = PromptChainRequest(**arguments)
            result = await _executor.prompt_chain(request)
            return [types.TextContent(text=result.model_dump_json())]

        else:
            return [types.TextContent(text=json.dumps({"error": f"Unknown tool: {name}"}))]

    except Exception as e:
        return [types.TextContent(text=json.dumps({"error": str(e)}))]


async def main_stdio():
    """Run the MCP server over stdio."""
    # Server instructions
    server.instructions = """
Prompts Module - Manage reusable prompt templates and multi-step workflows.

## Available Tools

1. **prompt_registry** - Manage prompt templates
   - list: List all available prompts
   - get: Retrieve a specific prompt
   - create: Create a new prompt
   - delete: Delete a prompt

2. **prompt_suggest** - Get relevant prompt suggestions
   - Analyze context and suggest matching prompts
   - Based on task, language, file_type, etc.

3. **prompt_chain** - Execute multi-step workflows
   - Compose prompts in sequence
   - Pass outputs from one step to the next
   - Use {{prev.step_name}} syntax for output references

## Built-in Prompts

- code-review-v1: Professional code review
- bug-debugging-v1: Systematic bug investigation
- feature-implementation-v1: Complete feature workflow
- architecture-design-v1: System architecture design

## Example Usage

1. Suggest prompts: prompt_suggest({context: {task: "code-review", language: "python"}})
2. Get a prompt: prompt_registry({action: "get", prompt_id: "code-review-v1"})
3. Execute chain: prompt_chain({action: "execute", steps: [...]})
"""

    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.instructions)


async def main_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP with SSE."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response

    server.instructions = """
Prompts Module - Manage reusable prompt templates and multi-step workflows.

## Available Tools

1. **prompt_registry** - Manage prompt templates
   - list: List all available prompts
   - get: Retrieve a specific prompt
   - create: Create a new prompt
   - delete: Delete a prompt

2. **prompt_suggest** - Get relevant prompt suggestions
   - Analyze context and suggest matching prompts
   - Based on task, language, file_type, etc.

3. **prompt_chain** - Execute multi-step workflows
   - Compose prompts in sequence
   - Pass outputs from one step to the next
   - Use {{prev.step_name}} syntax for output references

## Built-in Prompts

- code-review-v1: Professional code review
- bug-debugging-v1: Systematic bug investigation
- feature-implementation-v1: Complete feature workflow
- architecture-design-v1: System architecture design

## Example Usage

1. Suggest prompts: prompt_suggest({context: {task: "code-review", language: "python"}})
2. Get a prompt: prompt_registry({action: "get", prompt_id: "code-review-v1"})
3. Execute chain: prompt_chain({action: "execute", steps: [...]})
"""

    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        try:
            async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
                await server.run(streams[0], streams[1], server.instructions)
        except Exception as e:
            # Handle any errors in SSE connection gracefully
            import logging
            logging.error(f"Error in SSE handler: {e}", exc_info=True)
        # Note: Don't return Response() here - SSE transport handles the response

    async def handle_messages(scope, receive, send):
        try:
            await sse.handle_post_message(scope, receive, send)
        except Exception as e:
            # Handle closed connections and other errors gracefully
            import logging
            logging.error(f"Error handling SSE message: {e}")
            try:
                await send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await send({
                    "type": "http.response.body",
                    "body": json.dumps({"error": str(e)}).encode(),
                })
            except Exception:
                # Connection already closed, ignore
                pass

    async def app(scope, receive, send):
        path = scope.get("path", "")
        if path == "/sse":
            request = Request(scope, receive, send)
            await handle_sse(request)
        elif path == "/messages" and scope.get("method") == "POST":
            await handle_messages(scope, receive, send)
        else:
            await Response("Not Found", status_code=404)(scope, receive, send)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def run() -> None:
    """Entry point for the ninja-prompts MCP server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ninja Prompts MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8107,
        help="Port for HTTP server (default: 8107)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    run()
