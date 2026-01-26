"""MCP stdio server for ninja-resources module.

This module implements a Model Context Protocol (MCP) server that
exposes tools and resources for loading codebase context as queryable resources.

Usage:
    python -m ninja_resources.server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

import uvicorn
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.types import (
    EmbeddedResource,
    TextContent,
    Tool,
)

from ninja_common.logging_utils import get_logger, setup_logging
from ninja_resources.models import (
    ResourceCodebaseRequest,
    ResourceConfigRequest,
    ResourceDocsRequest,
)
from ninja_resources.tools import get_executor


if TYPE_CHECKING:
    from collections.abc import Sequence


setup_logging(level=logging.INFO)
logger = get_logger(__name__)


TOOLS: list[Tool] = [
    Tool(
        name="resource_codebase",
        description=(
            "Load codebase structure and metadata as a queryable resource. "
            "Returns directory tree, language breakdown, file counts, and size analysis. "
            "\n\n"
            "Use this for: Understanding project structure, finding files, "
            "generating metrics, preparing context for code generation."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path (absolute path)",
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to include (default: all)",
                    "default": [],
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to exclude",
                    "default": [],
                },
                "max_files": {
                    "type": "integer",
                    "description": "Maximum files to scan (default: 1000)",
                    "minimum": 1,
                    "default": 1000,
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="resource_config",
        description=(
            "Load configuration files (package.json, tsconfig.json, etc.) as resources. "
            "Returns parsed configuration data for analysis. "
            "\n\n"
            "Use this for: Understanding project config, reading settings, "
            "analyzing dependencies, extracting metadata."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path (absolute path)",
                },
                "config_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Config file patterns (default: common configs)",
                    "default": [],
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="resource_docs",
        description=(
            "Load documentation files (README, CONTRIBUTING, etc.) as resources. "
            "Returns structured documentation with summaries. "
            "\n\n"
            "Use this for: Quick project overview, finding key info, "
            "generating documentation summaries."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path (absolute path)",
                },
                "doc_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Documentation file patterns",
                    "default": ["**/*.md", "**/README*", "**/CONTRIBUTING*"],
                },
            },
            "required": ["repo_root"],
        },
    ),
]


def create_server() -> Server:
    server = Server("ninja-resources")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        executor = get_executor()
        client_id = arguments.get("client_id", "default")

        try:
            if name == "resource_codebase":
                request = ResourceCodebaseRequest(**arguments)
                result = await executor.resource_codebase(request, client_id=client_id)
                return [TextContent(type="text", text=result.model_dump_json())]

            elif name == "resource_config":
                request = ResourceConfigRequest(**arguments)
                result = await executor.resource_config(request, client_id=client_id)
                return [TextContent(type="text", text=result.model_dump_json())]

            elif name == "resource_docs":
                request = ResourceDocsRequest(**arguments)
                result = await executor.resource_docs(request, client_id=client_id)
                return [TextContent(type="text", text=result.model_dump_json())]

            else:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"error": f"Unknown tool: {name}"}
                        ),
                    )
                ]

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e!s}", exc_info=True)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "error": f"Tool execution failed: {e!s}",
                            "tool": name,
                        }
                    ),
                )
            ]

    @server.list_resources()
    async def list_resources() -> list[EmbeddedResource]:
        return [
            EmbeddedResource(
                uri="ninja://templates/python",
                name="Python Template",
                description="Template for Python files",
                mimeType="text/x-python",
            ),
            EmbeddedResource(
                uri="ninja://templates/javascript",
                name="JavaScript Template",
                description="Template for JavaScript files",
                mimeType="application/javascript",
            ),
        ]

    @server.read_resource()
    async def read_resource(uri: str) -> str:
        if uri == "ninja://templates/python":
            content = """#!/usr/bin/env python3

def main():
    print("Hello from Python template!")

if __name__ == "__main__":
    main()
"""
        elif uri == "ninja://templates/javascript":
            content = '''#!/usr/bin/env node

function main() {
    console.log("Hello from JavaScript template!");
}

if (require.main === module) {
    main();
}
'''
        else:
            raise ValueError(f"Unknown resource: {uri}")

        return content

    return server


async def main_stdio():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


async def main_http(host: str, port: int) -> None:
    from starlette.requests import Request
    from starlette.responses import Response

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    async def handle_messages(request):
        try:
            await sse.handle_post_message(request.scope, request.receive, request._send)
        except Exception as e:
            logger.error(f"Error handling SSE message: {e!s}", exc_info=True)
            try:
                await request._send({
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [[b"content-type", b"application/json"]],
                })
                await request._send({
                    "type": "http.response.body",
                    "body": json.dumps({"error": str(e)}).encode(),
                })
            except Exception:
                pass

    async def app(scope, receive, send):
        path = scope.get("path", "")
        if path == "/sse":
            request = Request(scope, receive, send)
            await handle_sse(request)
        elif path == "/messages" and scope.get("method") == "POST":
            request = Request(scope, receive, send)
            await handle_messages(request)
        else:
            await Response("Not Found", status_code=404)(scope, receive, send)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def run() -> None:
    """Run the server with command-line argument parsing."""
    parser = argparse.ArgumentParser(description="Ninja Resources MCP Server")
    parser.add_argument("--http", action="store_true", help="Run in HTTP/SSE mode (default: stdio)")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8106, help="Port to bind to (default: 8106)")

    args = parser.parse_args()

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        logger.info("Server shutting down...")
    except Exception as e:
        logger.error(f"Fatal error: {e!s}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
