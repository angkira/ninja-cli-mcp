"""
MCP stdio server for ninja-cli-mcp.

This module implements the Model Context Protocol (MCP) server that
exposes tools for delegating code execution to AI coding assistants.

The server communicates via stdin/stdout using the MCP protocol.
All code operations are delegated to the AI code CLI - this server
never directly reads or writes user project files.

Supports any OpenRouter-compatible model (Claude, GPT, Qwen, DeepSeek, etc.)

Usage:
    python -m ninja_cli_mcp.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any, Sequence

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from ninja_cli_mcp.logging_utils import get_logger, setup_logging
from ninja_cli_mcp.models import (
    ApplyPatchRequest,
    ParallelPlanRequest,
    QuickTaskRequest,
    RunTestsRequest,
    SequentialPlanRequest,
)
from ninja_cli_mcp.tools import get_executor


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions with JSON Schema
TOOLS: list[Tool] = [
    Tool(
        name="ninja_quick_task",
        description=(
            "Execute a single-pass code task via Aider (AI agent). "
            "Aider reads files, makes changes, and returns results. You don't need to read files yourself. "
            "Use for: docstrings, type hints, refactoring, creating files, bug fixes. "
            "Supports any OpenRouter model (Claude, GPT, Qwen, DeepSeek, etc.)"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Task description for the AI code CLI to execute",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "context_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to pay special attention to",
                    "default": [],
                },
                "allowed_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns for allowed file operations",
                    "default": [],
                },
                "deny_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Glob patterns to deny file operations",
                    "default": [],
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick"],
                    "description": "Execution mode (future-proof)",
                    "default": "quick",
                },
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="execute_plan_sequential",
        description=(
            "Execute a multi-step plan sequentially. Each step is executed in order, "
            "with the AI code CLI handling all file operations. "
            "Supports quick mode (single pass) or full mode (with review/test loops)."
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
                    "description": "Plan steps to execute in order",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string", "description": "Unique step identifier"},
                            "title": {"type": "string", "description": "Human-readable step title"},
                            "task": {"type": "string", "description": "Detailed task description"},
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
        name="execute_plan_parallel",
        description=(
            "Execute plan steps in parallel with a configurable fanout limit. "
            "Each step runs in its own subprocess. Steps should have non-overlapping "
            "scopes for best results. Returns a merge report for coordination."
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
                    "description": "Maximum concurrent executions",
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
                    "description": "Plan steps to execute in parallel",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "task": {"type": "string"},
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
        name="run_tests",
        description=(
            "Run test commands via the AI code CLI. The CLI executes the specified "
            "test commands and reports results. Returns summary and logs reference."
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
                    "description": "Test commands to execute",
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
        name="apply_patch",
        description=(
            "Apply a patch (not supported - delegated to AI code CLI). "
            "In this architecture, patches are owned by the AI code CLI. "
            "Include patch content in task descriptions for other tools instead."
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
                    "description": "Patch content (if applicable)",
                    "default": "",
                },
                "patch_description": {
                    "type": "string",
                    "description": "Description of the patch",
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
        "ninja-cli-mcp",
        version="1.0.0",
        instructions="""ninja-cli-mcp: Delegate ALL code work to AI agent (Aider via OpenRouter)

CRITICAL: You MUST NOT read/view/inspect files yourself. ALWAYS delegate to ninja-cli-mcp.

What ninja-cli-mcp does:
• Executes code changes via Aider (AI coding agent)
• Creates, edits, deletes files automatically  
• Runs tests and validates changes
• Handles full implementation without your involvement

Your role as planner:
1. Break task into clear steps
2. Call ninja-cli-mcp tools with descriptions
3. Review status/summary (NOT source code)
4. Move to next step

DO NOT:
❌ Read files (delegate to ninja tools)
❌ Write code snippets (delegate to ninja tools)  
❌ Inspect implementation (trust the tool)

DO:
✅ Use ninja_quick_task for single changes
✅ Use execute_plan_sequential for multi-step tasks
✅ Use execute_plan_parallel for independent tasks
✅ Review returned status only

Example:
User: "Add authentication module"
You: execute_plan_sequential([
  "Create auth.py with login/logout",
  "Add password hashing utils",
  "Create session management", 
  "Add middleware",
  "Write tests"
])
Aider implements each step completely."""
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """Handle tool invocations."""
        logger.info(f"Tool called: {name}")
        logger.debug(f"Arguments: {json.dumps(arguments, indent=2)}")

        executor = get_executor()

        try:
            if name == "ninja_quick_task":
                request = QuickTaskRequest(**arguments)
                result = await executor.quick_task(request)

            elif name == "execute_plan_sequential":
                request = SequentialPlanRequest(**arguments)
                result = await executor.execute_plan_sequential(request)

            elif name == "execute_plan_parallel":
                request = ParallelPlanRequest(**arguments)
                result = await executor.execute_plan_parallel(request)

            elif name == "run_tests":
                request = RunTestsRequest(**arguments)
                result = await executor.run_tests(request)

            elif name == "apply_patch":
                request = ApplyPatchRequest(**arguments)
                result = await executor.apply_patch(request)

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
                f"Tool {name} completed with status: {result_json.get('status', 'unknown')}"
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result_json, indent=2),
                )
            ]

        except Exception as e:
            logger.error(f"Tool {name} failed: {e}", exc_info=True)
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


async def main() -> None:
    """Run the MCP server."""
    logger.info("Starting ninja-cli-mcp server")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for requests")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


def run() -> None:
    """Entry point for running the server."""
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
