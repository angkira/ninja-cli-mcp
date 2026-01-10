"""
MCP stdio server for ninja-coder module.

This module implements the Model Context Protocol (MCP) server that
exposes tools for delegating code execution to AI coding assistants.

The server communicates via stdin/stdout using the MCP protocol.
All code operations are delegated to the AI code CLI - this server
never directly reads or writes user project files.

Supports any OpenRouter-compatible model (Claude, GPT, Qwen, DeepSeek, etc.)

Usage:
    python -m ninja_coder.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from ninja_coder.models import (
    ApplyPatchRequest,
    ParallelPlanRequest,
    QuickTaskRequest,
    RunTestsRequest,
    SequentialPlanRequest,
)
from ninja_coder.tools import get_executor
from ninja_common.logging_utils import get_logger, setup_logging


if TYPE_CHECKING:
    from collections.abc import Sequence


# Load config from ~/.ninja-mcp.env into environment variables
try:
    from ninja_common.config_manager import ConfigManager
    ConfigManager().export_env()
except FileNotFoundError:
    pass  # Config file may not exist, will use env vars directly
except Exception as e:
    import sys
    print(f"WARNING: Failed to load config from ~/.ninja-mcp.env: {e}", file=sys.stderr)

# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions with JSON Schema
TOOLS: list[Tool] = [
    Tool(
        name="coder_quick_task",
        description=(
            "Delegate a FOCUSED code task to a specialized AI coding agent. "
            "Best for single-file changes or small, well-defined modifications. "
            "\n\n"
            "IDEAL FOR: Creating a file, adding a function/class, implementing a specific feature, "
            "fixing a specific bug, adding types/docstrings to a module. "
            "\n\n"
            "NOT IDEAL FOR: Large refactors across many files (use coder_execute_plan_sequential), "
            "or multiple independent changes (use coder_execute_plan_parallel). "
            "\n\n"
            "Provide a specific task description. Ninja writes code to disk and returns a summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "DETAILED code writing specification. Be specific about WHAT to implement, "
                        "not HOW to implement it. Example: 'Create a User class with email validation "
                        "and password hashing methods' NOT 'add some user stuff'"
                    ),
                },
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "context_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files/directories Ninja should focus on (for context)",
                    "default": [],
                },
                "allowed_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns for files Ninja can modify (e.g., ['src/**/*.py'])",
                    "default": [],
                },
                "deny_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns for files Ninja must NOT touch",
                    "default": [],
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick"],
                    "description": "Execution mode (always 'quick' for single-pass code writing)",
                    "default": "quick",
                },
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="coder_execute_plan_sequential",
        description=(
            "Execute a multi-step implementation plan where each step builds on the previous. "
            "Use for complex features that require ordered implementation steps. "
            "\n\n"
            "WHEN TO USE: Building features with dependencies between steps, "
            "implementing components that must be created in a specific order. "
            "\n\n"
            "Each step runs sequentially, ensuring earlier changes are available to later steps."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick", "full"],
                    "description": "Execution mode: 'quick' for fast single-pass, 'full' for review loops",
                    "default": "quick",
                },
                "global_allowed_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global allowed glob patterns for all steps",
                    "default": [],
                },
                "global_deny_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global deny glob patterns for all steps",
                    "default": [],
                },
                "steps": {
                    "type": "array",
                    "description": "Code writing steps to execute in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique step identifier"},
                            "title": {"type": "string", "description": "Human-readable step title"},
                            "task": {
                                "type": "string",
                                "description": "DETAILED specification of what code to write in this step",
                            },
                            "context_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "allowed_globs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "deny_globs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "default": [],
                            },
                            "max_iterations": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "default": 3,
                            },
                            "test_plan": {
                                "type": "object",
                                "properties": {
                                    "unit": {"type": "array", "items": {"type": "string"}},
                                    "e2e": {"type": "array", "items": {"type": "string"}},
                                },
                                "default": {},
                            },
                            "constraints": {
                                "type": "object",
                                "properties": {
                                    "max_tokens": {"type": "integer", "minimum": 0},
                                    "time_budget_sec": {"type": "integer", "minimum": 0},
                                },
                                "default": {},
                            },
                        },
                        "required": ["id", "title", "task"],
                    },
                },
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_execute_plan_parallel",
        description=(
            "Execute multiple independent implementation tasks in PARALLEL for faster completion. "
            "Use when you have several coding tasks that don't depend on each other. "
            "\n\n"
            "WHEN TO USE: Creating multiple independent modules, implementing separate features, "
            "adding tests for different components, bulk refactoring across unrelated files. "
            "\n\n"
            "Tasks run concurrently (up to 4 by default), significantly reducing total time."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick", "full"],
                    "description": "Execution mode",
                    "default": "quick",
                },
                "fanout": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 16,
                    "description": "Maximum concurrent code writing tasks",
                    "default": 4,
                },
                "global_allowed_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global allowed glob patterns",
                    "default": [],
                },
                "global_deny_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Global deny glob patterns",
                    "default": [],
                },
                "steps": {
                    "type": "array",
                    "description": "Independent code writing steps to execute in parallel",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "task": {
                                "type": "string",
                                "description": "DETAILED specification of what code to write",
                            },
                            "context_paths": {"type": "array", "items": {"type": "string"}},
                            "allowed_globs": {"type": "array", "items": {"type": "string"}},
                            "deny_globs": {"type": "array", "items": {"type": "string"}},
                            "max_iterations": {"type": "integer"},
                            "test_plan": {"type": "object"},
                            "constraints": {"type": "object"},
                        },
                        "required": ["id", "title", "task"],
                    },
                },
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_run_tests",
        description=(
            "⚠️ DEPRECATED - DO NOT USE. "
            "\n\n"
            "Ninja is for CODE WRITING ONLY, not for running tests or commands. "
            "\n\n"
            "To run tests: Use bash tool or execute commands yourself. "
            "Ninja only writes code based on specifications."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "commands": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Test commands (NOT SUPPORTED - use bash tool instead)",
                },
                "timeout_sec": {
                    "type": "integer",
                    "minimum": 10,
                    "maximum": 3600,
                    "description": "Timeout in seconds",
                    "default": 600,
                },
            },
            "required": ["repo_root", "commands"],
        },
    ),
    Tool(
        name="coder_apply_patch",
        description=(
            "⚠️ NOT SUPPORTED. "
            "\n\n"
            "Ninja writes code based on specifications, not patches. "
            "\n\n"
            "To apply changes: Describe what code to write in coder_quick_task. "
            "Ninja will implement it directly."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "patch_content": {
                    "type": "string",
                    "description": "Patch content (NOT SUPPORTED)",
                    "default": "",
                },
                "patch_description": {
                    "type": "string",
                    "description": "Description of the patch (NOT SUPPORTED)",
                    "default": "",
                },
            },
            "required": ["repo_root"],
        },
    ),
]


def create_server() -> Server:
    """
    Create and configure the MCP server with detailed instructions.

    Returns:
        Configured MCP Server instance.
    """
    server = Server(
        "ninja-coder",
        version="0.2.0",
        instructions="""Ninja Coder - Delegate code writing to a specialized AI agent.

USE THIS TOOL WHEN you need to:
• Create new files or modules
• Implement features, functions, or classes
• Refactor or modify existing code
• Add types, docstrings, or tests
• Fix bugs (when you know what needs to change)

HOW TO USE:
1. Describe WHAT you want (be specific about files, functions, behavior)
2. Call coder_quick_task with your specification
3. Ninja writes the code directly to disk
4. You get a summary of changes - then verify/test the results

EXAMPLE SPECIFICATION:
"Create src/utils/validator.py with:
 - validate_email(email: str) -> bool using regex
 - validate_password(pwd: str) -> bool (min 8 chars, 1 digit, 1 upper)
 Include type hints and docstrings."

For multiple independent tasks, use coder_execute_plan_parallel for faster execution.""",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """Handle tool invocations."""
        # Extract client/session ID from MCP context if available
        # Note: RequestContext is not available in current mcp version
        # Client ID extraction will be added when MCP library supports it
        client_id = "default"

        logger.info(f"[{client_id}] Tool called: {name}")
        logger.debug(f"[{client_id}] Arguments: {json.dumps(arguments, indent=2)}")

        executor = get_executor()

        try:
            if name == "coder_quick_task":
                request = QuickTaskRequest(**arguments)
                result = await executor.quick_task(request, client_id=client_id)

            elif name == "coder_execute_plan_sequential":
                request = SequentialPlanRequest(**arguments)
                result = await executor.execute_plan_sequential(request, client_id=client_id)

            elif name == "coder_execute_plan_parallel":
                request = ParallelPlanRequest(**arguments)
                result = await executor.execute_plan_parallel(request, client_id=client_id)

            elif name == "coder_run_tests":
                request = RunTestsRequest(**arguments)
                result = await executor.run_tests(request, client_id=client_id)

            elif name == "coder_apply_patch":
                request = ApplyPatchRequest(**arguments)
                result = await executor.apply_patch(request, client_id=client_id)

            else:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": f"Unknown tool: {name}"}),
                    )
                ]

            # Serialize result to JSON
            result_json = result.model_dump()
            logger.info(
                f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result_json, indent=2),
                )
            ]

        except Exception as e:
            logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    ),
                )
            ]

    return server


async def main_stdio() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting ninja-coder server (stdio mode)")

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

    logger.info(f"Starting ninja-coder server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
        return Response()

    async def handle_messages(scope, receive, send):
        await sse.handle_post_message(scope, receive, send)

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
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ninja Coder MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8100,
        help="Port for HTTP server (default: 8100)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    # Load config from ~/.ninja-mcp.env into environment variables
    # This ensures settings like NINJA_CODE_BIN are available
    try:
        from ninja_common.config_manager import ConfigManager

        ConfigManager().export_env()
    except Exception:
        pass  # Config file may not exist, continue with env vars

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
