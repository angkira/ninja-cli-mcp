"""
MCP stdio server for ninja-agent module.

The agent is an orchestrator: it plans, analyzes, delegates, and reviews,
but never writes code itself. Code-writing is delegated to the coder module.
Analysis is delegated to the secretary module, and web research to the
researcher module.

Usage:
    python -m ninja_agent.server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ninja_agent.models import (
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentDelegateRequest,
    AgentDelegateResult,
    AgentPlanRequest,
    AgentPlanResult,
    AgentReviewRequest,
    AgentReviewResult,
)
from ninja_agent.tools import AgentToolExecutor
from ninja_common.logging_utils import get_logger, setup_logging


if TYPE_CHECKING:
    from collections.abc import Sequence


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="agent_analyze",
        description=(
            "Analyze a codebase: structure, file counts, and optionally a focus area. "
            "Delegates to the secretary module. Never modifies files."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path to analyze",
                },
                "focus": {
                    "type": "string",
                    "description": "Optional focus area or search term to narrow analysis",
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns of files to include",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="agent_plan",
        description=(
            "Decompose a high-level task into an ordered execution plan. Each step is "
            "routed to the appropriate sub-agent (coder for code, researcher for research, "
            "secretary for analysis, self for review)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "High-level task description",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "context_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths relevant to the task",
                },
                "steps_requested": {
                    "type": "integer",
                    "description": "Optional hint for number of steps",
                },
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="agent_delegate",
        description=(
            "Delegate a subtask to a specific sub-agent: 'coder' writes code, 'researcher' "
            "does a web search, 'secretary' analyzes the codebase. Use this to dispatch "
            "work to specialized agents."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "subtask": {
                    "type": "string",
                    "description": "Subtask description",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "delegate_to": {
                    "type": "string",
                    "enum": ["coder", "researcher", "secretary"],
                    "description": "Sub-agent to invoke",
                },
                "context_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths relevant to the subtask",
                },
                "model_class": {
                    "type": "string",
                    "enum": ["smart", "balanced", "fast"],
                    "description": "Model tier for the coder sub-agent (default: smart)",
                },
            },
            "required": ["subtask", "repo_root", "delegate_to"],
        },
    ),
    Tool(
        name="agent_review",
        description=(
            "Review files without modifying them. Heuristic static analysis for long "
            "blocks, empty except handlers, missing docstrings, and syntax errors."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "file_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files to review (relative to repo_root)",
                },
                "review_focus": {
                    "type": "string",
                    "description": "Optional area to focus review on",
                },
            },
            "required": ["repo_root", "file_paths"],
        },
    ),
]


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("ninja-agent")
    executor = AgentToolExecutor()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> Sequence[TextContent]:
        """Handle tool execution requests."""
        try:
            client_id = arguments.get("client_id", "default")

            if name == "agent_analyze":
                analyze_request = AgentAnalyzeRequest(**arguments)
                analyze_result: AgentAnalyzeResult = await executor.analyze(
                    analyze_request, client_id
                )
                return [
                    TextContent(type="text", text=json.dumps(analyze_result.model_dump(), indent=2))
                ]

            elif name == "agent_plan":
                plan_request = AgentPlanRequest(**arguments)
                plan_result: AgentPlanResult = await executor.plan(plan_request, client_id)
                return [
                    TextContent(type="text", text=json.dumps(plan_result.model_dump(), indent=2))
                ]

            elif name == "agent_delegate":
                delegate_request = AgentDelegateRequest(**arguments)
                delegate_result: AgentDelegateResult = await executor.delegate(
                    delegate_request, client_id
                )
                return [
                    TextContent(
                        type="text", text=json.dumps(delegate_result.model_dump(), indent=2)
                    )
                ]

            elif name == "agent_review":
                review_request = AgentReviewRequest(**arguments)
                review_result: AgentReviewResult = await executor.review(review_request, client_id)
                return [
                    TextContent(type="text", text=json.dumps(review_result.model_dump(), indent=2))
                ]

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "success": False,
                            "error": str(e),
                            "tool": name,
                        }
                    ),
                )
            ]

    return server


async def main_stdio() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting ninja-agent server (stdio mode)")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for requests")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def main_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP with SSE."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response

    logger.info(f"Starting ninja-agent server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request: Any) -> Response:
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    async def handle_messages(scope: Any, receive: Any, send: Any) -> None:
        await sse.handle_post_message(scope, receive, send)

    async def app(scope: Any, receive: Any, send: Any) -> None:
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
    """Run the server with command-line argument parsing."""
    parser = argparse.ArgumentParser(description="Ninja Agent MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8103,
        help="Port for HTTP server (default: 8103)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    if args.http:
        asyncio.run(main_http(args.host, args.port))
    else:
        asyncio.run(main_stdio())


if __name__ == "__main__":
    run()
