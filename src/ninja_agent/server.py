"""
MCP stdio server for ninja-agent module.

The agent is AUTONOMOUS: guarded shell, log tails, daemon/process snapshots,
read-only job overviews, plus its own file analysis and heuristic review.
It knows nothing about coder/researcher/secretary and never delegates to
them — code-writing is invoked directly via coder_* tools by the central
model, not through the agent.

Usage:
    python -m ninja_agent.server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, TextContent, Tool, ToolExecution

from ninja_agent.models import (
    DELEGATE_MIGRATION,
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentDistillLogsRequest,
    AgentDistillLogsResult,
    AgentExecCommandRequest,
    AgentExecCommandResult,
    AgentExecPipelineRequest,
    AgentExecPipelineResult,
    AgentJobsOverviewRequest,
    AgentJobsOverviewResult,
    AgentProcessesRequest,
    AgentProcessesResult,
    AgentReviewRequest,
    AgentReviewResult,
    AgentRunAndDiagnoseRequest,
    AgentRunAndDiagnoseResult,
    AgentTailLogsRequest,
    AgentTailLogsResult,
)
from ninja_agent.tools import AgentToolExecutor
from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.mcp_tasks import install_tasks, refresh_task_after_cancel, server_task_scope


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions — one tool per capability, all agent_*, no delegate_*.
TOOLS: list[Tool] = [
    Tool(
        name="agent_exec_command",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Run a guarded, non-interactive shell command (tests, git status, ls, "
            "builds). Destructive patterns are refused; mutating commands require "
            "allow_write=True. Output is capped and redacted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root (default cwd / safety scope)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (defaults to repo_root)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Kill the command after this many seconds",
                },
                "allow_write": {
                    "type": "boolean",
                    "description": "Allow file-mutating commands",
                },
            },
            "required": ["command", "repo_root"],
        },
    ),
    Tool(
        name="agent_tail_logs",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Return capped, redacted log tails (daemon .log files / structured logs). "
            "Never returns more than 200 lines/entries."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Daemon/module name (e.g. 'coder')",
                },
                "level": {
                    "type": "string",
                    "description": "Optional level filter (INFO/ERROR/...)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries (capped at 200)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session filter",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="agent_processes",
        execution=ToolExecution(taskSupport="optional"),
        description=("Snapshot daemon statuses plus host resource stats. Strictly read-only."),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="agent_jobs_overview",
        execution=ToolExecution(taskSupport="optional"),
        description=("Summarize pending background jobs/tasks. Strictly read-only."),
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Max jobs to include",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="agent_analyze",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Analyze a codebase with direct file reads + AST/grep heuristics: "
            "structure, file/line counts, function/class counts, syntax errors, "
            "optionally narrowed by a focus term. Never modifies files."
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
        name="agent_review",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Review files without modifying them. Deterministic heuristic static "
            "analysis: long blocks, empty except handlers, missing docstrings, "
            "syntax errors."
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
    Tool(
        name="agent_run_and_diagnose",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Execute a test suite or command, clean ANSI codes, parse failures/counts, "
            "and return high-signal condensed output preserving root cause."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute and diagnose",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root (default cwd / safety scope)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory (defaults to repo_root)",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Kill the command after this many seconds",
                },
                "allow_write": {
                    "type": "boolean",
                    "description": "Allow file-mutating commands",
                },
                "framework_hint": {
                    "type": "string",
                    "description": "Optional framework hint (e.g. 'pytest', 'ruff', 'mypy')",
                },
            },
            "required": ["command", "repo_root"],
        },
    ),
    Tool(
        name="agent_exec_pipeline",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Execute an ordered batch of commands sequentially with wall-clock timing, "
            "per-step condensed output, and fail-fast logic."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "Shell command to execute",
                            },
                            "name": {"type": "string", "description": "Optional step name"},
                            "cwd": {
                                "type": "string",
                                "description": "Working directory for this step",
                            },
                            "timeout": {"type": "integer", "description": "Timeout in seconds"},
                            "allow_write": {
                                "type": "boolean",
                                "description": "Allow file mutations",
                            },
                            "continue_on_error": {
                                "type": "boolean",
                                "description": "Continue pipeline if step fails",
                            },
                        },
                        "required": ["command"],
                    },
                    "description": "Ordered sequence of steps to run",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "cwd": {
                    "type": "string",
                    "description": "Default working directory for steps",
                },
                "fail_fast": {
                    "type": "boolean",
                    "description": "Halt on first failing step (default: True)",
                },
            },
            "required": ["steps", "repo_root"],
        },
    ),
    Tool(
        name="agent_distill_logs",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Retrieve, cluster, and deduplicate repeating log entries, masking dynamic values "
            "and isolating distinct error tracebacks."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "module": {
                    "type": "string",
                    "description": "Daemon/module name (e.g. 'coder')",
                },
                "level": {
                    "type": "string",
                    "description": "Optional level filter (INFO/ERROR/...)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max entries (capped at 200)",
                },
                "session_id": {
                    "type": "string",
                    "description": "Optional session filter",
                },
            },
            "required": [],
        },
    ),
]

# Look up tool definitions by name (used for task-mode validation).
_TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}

#: Removed tool names kept as explicit migration errors.
_REMOVED_TOOLS = frozenset(
    {
        "agent_delegate",
        "agent_delegate_coder",
        "agent_delegate_researcher",
        "agent_delegate_secretary",
        "agent_delegate_runner",
        "agent_delegate_git",
        "agent_plan",
    }
)


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server("ninja-agent")

    # Enable standard MCP Tasks (background/asynchronous tool execution) with a
    # durable store and real cancellation of running work.
    install_tasks(server)

    executor = AgentToolExecutor()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> Any:
        """Handle tool execution requests, synchronously or as a background task."""
        request_ctx = server.request_context
        experimental = request_ctx.experimental
        tool_definition = _TOOLS_BY_NAME.get(name)
        if tool_definition is not None:
            experimental.validate_for_tool(tool_definition)

        async def _invoke() -> list[TextContent]:
            try:
                client_id = arguments.get("client_id", "default")

                if name == "agent_exec_command":
                    exec_request = AgentExecCommandRequest(**arguments)
                    exec_result: AgentExecCommandResult = await executor.exec_command(
                        exec_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(exec_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_tail_logs":
                    logs_request = AgentTailLogsRequest(**arguments)
                    logs_result: AgentTailLogsResult = await executor.tail_logs(
                        logs_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(logs_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_processes":
                    procs_request = AgentProcessesRequest(**arguments)
                    procs_result: AgentProcessesResult = await executor.processes(
                        procs_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(procs_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_jobs_overview":
                    jobs_request = AgentJobsOverviewRequest(**arguments)
                    jobs_result: AgentJobsOverviewResult = await executor.jobs_overview(
                        jobs_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(jobs_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_analyze":
                    analyze_request = AgentAnalyzeRequest(**arguments)
                    analyze_result: AgentAnalyzeResult = await executor.analyze(
                        analyze_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(analyze_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_review":
                    review_request = AgentReviewRequest(**arguments)
                    review_result: AgentReviewResult = await executor.review(
                        review_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(review_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_run_and_diagnose":
                    diag_request = AgentRunAndDiagnoseRequest(**arguments)
                    diag_result: AgentRunAndDiagnoseResult = await executor.run_and_diagnose(
                        diag_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(diag_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_exec_pipeline":
                    pipe_request = AgentExecPipelineRequest(**arguments)
                    pipe_result: AgentExecPipelineResult = await executor.exec_pipeline(
                        pipe_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(pipe_result.model_dump(), indent=2)
                        )
                    ]

                elif name == "agent_distill_logs":
                    distill_request = AgentDistillLogsRequest(**arguments)
                    distill_result: AgentDistillLogsResult = await executor.distill_logs(
                        distill_request, client_id
                    )
                    return [
                        TextContent(
                            type="text", text=json.dumps(distill_result.model_dump(), indent=2)
                        )
                    ]

                elif name in _REMOVED_TOOLS:
                    raise ValueError(DELEGATE_MIGRATION)

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

        if experimental.is_task:
            session = request_ctx.session
            progress_token = request_ctx.meta.progressToken if request_ctx.meta else None

            async def _work(task: Any) -> CallToolResult:
                async with server_task_scope(
                    task, session=session, progress_token=progress_token
                ) as cancellation:
                    content = await _invoke()
                    if cancellation.is_set():
                        await refresh_task_after_cancel(task)
                    return CallToolResult(content=list(content), isError=False)

            return await experimental.run_task(_work)

        return await _invoke()

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
    import sys

    cli_subcommands = {
        "exec-command",
        "tail-logs",
        "processes",
        "jobs-overview",
        "analyze",
        "review",
        "run-and-diagnose",
        "pipeline",
        "distill-logs",
    }
    if len(sys.argv) > 1 and (
        sys.argv[1] in cli_subcommands
        or (sys.argv[1] == "--json" and len(sys.argv) > 2 and sys.argv[2] in cli_subcommands)
    ):
        from ninja_agent import cli

        sys.exit(cli.main(sys.argv[1:]))

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
