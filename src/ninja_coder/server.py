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


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions with JSON Schema
TOOLS: list[Tool] = [
    Tool(
        name="coder_quick_task",
        description=(
            "Delegate CODE WRITING ONLY to Ninja AI agent (via Aider). "
            "Ninja ONLY writes/edits code files based on your specification. "
            "\n\n"
            "✅ USE FOR: Writing code, creating files, refactoring, adding features, fixing bugs, "
            "adding docstrings/types, implementing functions/classes. "
            "\n\n"
            "❌ NEVER USE FOR: Running commands, executing tests, checking output, bash/shell operations, "
            "reading file contents (you should read files yourself if needed for planning). "
            "\n\n"
            "YOU provide the specification, Ninja writes the code. "
            "Ninja returns ONLY a summary (file paths changed, brief description). "
            "NO source code is returned to you - Ninja writes directly to files."
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
            "Execute a multi-step CODE WRITING plan sequentially. "
            "Each step delegates code writing to Ninja AI agent. "
            "\n\n"
            "✅ USE FOR: Multi-step code implementations where steps must happen in order. "
            "Each step writes code based on your specification. "
            "\n\n"
            "❌ NEVER USE FOR: Running tests, executing commands, checking outputs. "
            "This is ONLY for writing code in multiple sequential steps. "
            "\n\n"
            "Returns summary of each step (files changed, brief description). "
            "NO source code is returned - Ninja writes directly to files."
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
            "Execute CODE WRITING steps in parallel with configurable concurrency. "
            "Each step delegates code writing to Ninja AI agent. "
            "\n\n"
            "✅ USE FOR: Independent code writing tasks that can happen simultaneously "
            "(e.g., creating separate modules, different feature implementations). "
            "\n\n"
            "❌ NEVER USE FOR: Running tests, executing commands, tasks with dependencies. "
            "Steps should have non-overlapping file scopes to avoid conflicts. "
            "\n\n"
            "Returns summary of each step plus merge report. "
            "NO source code is returned - Ninja writes directly to files."
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
        instructions="""🥷 Ninja Coder: Delegate CODE WRITING to AI Agent (Aider)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚠️  CRITICAL: Ninja ONLY writes code. NO bash, NO tests, NO file reading for you.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 WHAT NINJA DOES:
   ✅ Writes/edits code files based on your specification
   ✅ Creates new files and directories
   ✅ Refactors existing code
   ✅ Adds features, fixes bugs, implements functions/classes
   ✅ Returns ONLY summary: "Modified X files: brief description"

🚫 WHAT NINJA DOES NOT DO:
   ❌ Run commands (bash, shell, npm, pytest, etc.)
   ❌ Execute tests or check test output
   ❌ Read files for you (YOU read files for planning)
   ❌ Return source code to you (writes directly to disk)
   ❌ Validate or check anything (YOU validate after)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎯 YOUR WORKFLOW:

1. 📖 READ files yourself (if needed for planning)
2. 🧠 PLAN what code needs to be written
3. 📝 WRITE detailed specification for Ninja
4. 🥷 CALL coder_quick_task with specification
5. ✅ REVIEW Ninja's summary (files changed)
6. 🧪 RUN tests yourself (using bash tool)
7. 🔄 REPEAT if needed

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📝 SPECIFICATION QUALITY:

❌ BAD:  "add authentication"
❌ BAD:  "fix the bug"
❌ BAD:  "improve the code"

✅ GOOD: "Create src/auth.py with User class containing:
          - email: str field with validation
          - password_hash: str field
          - hash_password(password: str) method using bcrypt
          - verify_password(password: str) -> bool method
          Add type hints and docstrings."

✅ GOOD: "In src/api/routes.py, add POST /login endpoint that:
          - Accepts JSON with email and password
          - Validates credentials using User.verify_password
          - Returns JWT token on success
          - Returns 401 on failure
          Handle all error cases with proper status codes."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 AVAILABLE TOOLS:

• coder_quick_task
  Single code writing task. Use for most implementations.
  Returns: Summary only (files changed, brief description)

• coder_execute_plan_sequential
  Multi-step code writing where order matters.
  Returns: Summary per step

• coder_execute_plan_parallel
  Independent code writing tasks (non-overlapping files).
  Returns: Summary per step + merge report

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 EXAMPLES:

User: "Add user authentication"

You:
1. Read existing code structure (if needed)
2. Plan: Need User model, auth routes, password hashing
3. Call coder_quick_task with detailed spec:
   "Create authentication system:
    - src/models/user.py: User class with email, password_hash
    - src/auth/password.py: hash_password and verify_password using bcrypt
    - src/api/auth.py: /login and /register endpoints
    Include type hints, docstrings, error handling"
4. Review Ninja's summary
5. Run tests yourself: bash "pytest tests/test_auth.py"
6. If tests fail, call coder_quick_task again with fix specification

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ REMEMBER:
   • Ninja writes code, YOU orchestrate
   • Ninja returns summaries, NOT source code
   • YOU read files, run tests, validate
   • Write detailed specs, get quality code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""",
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
    import uvicorn  # noqa: PLC0415
    from mcp.server.sse import SseServerTransport  # noqa: PLC0415
    from starlette.requests import Request  # noqa: PLC0415
    from starlette.responses import Response  # noqa: PLC0415

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
    import argparse  # noqa: PLC0415

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
