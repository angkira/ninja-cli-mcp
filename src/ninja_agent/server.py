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
from typing import Any, cast

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)

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
from ninja_common.mcp_ext.apply import apply_extensions
from ninja_common.mcp_ext.wiring import build_protocol_extensions
from ninja_common.mcp_meta import (
    ServerMeta,
    ToolMeta,
    apply_tool_meta,
    server_icon,
    server_kwargs,
)
from ninja_common.mcp_tasks import SqliteTaskStore, make_session_progress_callback, task_scope


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions — one tool per capability, all agent_*, no delegate_*.
TOOLS: list[Tool] = [
    Tool(
        name="agent_exec_command",
        description=(
            "Single guarded shell command (git status, ls, single test). "
            "Mutations need allow_write=True. Use run_and_diagnose for tests/lints, "
            "pipeline for multi-step."
        ),
        input_schema={
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
        description="Read-only log tails (max 200). Use distill_logs when you need clusters-errors summary.",
        input_schema={
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
        description="Daemon statuses plus host resource stats; strictly read-only.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="agent_jobs_overview",
        description="Pending background jobs/tasks summary; strictly read-only.",
        input_schema={
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
        description=(
            "Analyze a codebase (structure, counts, syntax errors) via file reads and AST/grep heuristics; optional focus term. Never modifies files."
        ),
        input_schema={
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
        description=(
            "Heuristic static review: syntax errors (critical), empty except/pass (warning). "
            "No style/docstring noise; never modifies."
        ),
        input_schema={
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
        description=(
            "Run tests/lints and distill failures (counts, file:line, root cause). Prefer over exec_command for verification."
        ),
        input_schema={
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
        description=(
            "Ordered multi-step shell (build-then-test). Fail-fast by default; per-step condensed output."
        ),
        input_schema={
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
        description=(
            "Tail logs + cluster repeats + isolate tracebacks. Use instead of tail_logs for noisy failures."
        ),
        input_schema={
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

_RO = ToolAnnotations(read_only_hint=True, idempotent_hint=True)

# Tool metadata: titles, behavior hints, and result models for
# outputSchema + structuredContent.
_TOOL_META: dict[str, ToolMeta] = {
    "agent_exec_command": ToolMeta(
        title="Run shell command",
        annotations=ToolAnnotations(destructive_hint=True),
        result_model=AgentExecCommandResult,
    ),
    "agent_tail_logs": ToolMeta(
        title="Tail logs", annotations=_RO, result_model=AgentTailLogsResult
    ),
    "agent_processes": ToolMeta(
        title="Process snapshot", annotations=_RO, result_model=AgentProcessesResult
    ),
    "agent_jobs_overview": ToolMeta(
        title="Jobs overview", annotations=_RO, result_model=AgentJobsOverviewResult
    ),
    "agent_analyze": ToolMeta(
        title="Analyze codebase", annotations=_RO, result_model=AgentAnalyzeResult
    ),
    "agent_review": ToolMeta(title="Review files", annotations=_RO, result_model=AgentReviewResult),
    "agent_run_and_diagnose": ToolMeta(
        title="Run and diagnose",
        annotations=ToolAnnotations(destructive_hint=True),
        result_model=AgentRunAndDiagnoseResult,
    ),
    "agent_exec_pipeline": ToolMeta(
        title="Run pipeline",
        annotations=ToolAnnotations(destructive_hint=True),
        result_model=AgentExecPipelineResult,
    ),
    "agent_distill_logs": ToolMeta(
        title="Distill logs", annotations=_RO, result_model=AgentDistillLogsResult
    ),
}

TOOLS = apply_tool_meta(TOOLS, _TOOL_META, server_icon("agent"))

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

#: Tools a 2026-07-28 client that declared ``io.modelcontextprotocol/tasks``
#: receives a task handle for instead of a blocking result. Every other client
#: keeps the synchronous behaviour described by the tool schema.
TASK_TOOLS: frozenset[str] = frozenset({"agent_run_and_diagnose", "agent_exec_pipeline"})


def create_server() -> Server:
    """Create and configure the MCP server."""
    executor = AgentToolExecutor()

    # Durable task store for the Tasks extension; one instance per server.
    store = SqliteTaskStore()
    # Skills advertise ``skills/*`` and serve skill files through Resources;
    # Tasks turns the long-running tools into durable task handles for clients
    # that declared it. Both are 2026-07-28 only.
    extensions = build_protocol_extensions("agent", store, TASK_TOOLS)

    async def list_tools(
        _ctx: ServerRequestContext[Any, Any],
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        """List available tools."""
        return ListToolsResult(tools=TOOLS)

    async def call_tool(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        """Handle tool execution requests synchronously."""
        name = params.name
        arguments: dict[str, Any] = dict(params.arguments or {})

        async def _invoke_text() -> list[TextContent]:
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

        async def _invoke() -> tuple[list[TextContent], dict[str, Any]]:
            texts = await _invoke_text()
            structured: dict[str, Any] = {}
            if texts and getattr(texts[0], "type", "") == "text":
                try:
                    parsed = json.loads(texts[0].text)
                    if isinstance(parsed, dict):
                        structured = parsed
                except (json.JSONDecodeError, TypeError):
                    structured = {}
            return texts, structured

        # Progress forwarding: when the caller passed a progress token in
        # ``_meta``, bridge driver progress to ``notifications/progress``.
        progress_token = (ctx.meta or {}).get("progress_token")
        if progress_token is not None:
            callback = make_session_progress_callback(ctx.session, progress_token)
            async with task_scope(f"sync-{name}", progress=callback):
                texts, structured = await _invoke()
        else:
            texts, structured = await _invoke()

        return CallToolResult(content=list(texts), structured_content=structured, is_error=False)

    # The lowlevel server runs no extension interceptors, so the Tasks
    # ``tools/call`` interceptor is composed here. ``call_tool`` itself is left
    # untouched: it is the straight-through path for every non-declaring client.
    async def call_tool_with_tasks(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        """Run ``call_tool`` behind the Tasks extension's interceptor."""

        async def call_next(_ctx: ServerRequestContext[Any, Any]) -> CallToolResult:
            return await call_tool(ctx, params)

        # A task-augmented call answers with a ``resultType: "task"`` envelope
        # instead; the wire serializer accepts any result model here.
        claimed = await extensions.tasks_ext.intercept_tool_call(params, ctx, call_next)
        return cast("CallToolResult", claimed)

    server = Server(
        "ninja-agent",
        **server_kwargs(
            ServerMeta(
                instructions="""Ninja Agent: autonomous routine ops. exec_command: single guarded shell (mutations need allow_write). run_and_diagnose: tests/lints with failure distillation. exec_pipeline: ordered multi-step. tail_logs/distill_logs: log tails vs clustered errors. processes/jobs_overview: read-only snapshots. analyze/review: read-only codebase analysis. Long runs emit progress notifications (~every 10s) when the client passes a progressToken — keep the token to avoid client timeouts.""",
                kind="agent",
            )
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool_with_tasks,
        on_list_resources=extensions.on_list_resources,
        on_read_resource=extensions.on_read_resource,
    )
    apply_extensions(server, [extensions.skills_ext, extensions.tasks_ext])
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
    """Run the MCP server over HTTP (SSE at /sse, streamable HTTP at /mcp)."""
    import uvicorn

    from ninja_common.mcp_http import build_asgi_app

    logger.info(f"Starting ninja-agent server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    app = build_asgi_app(server, host=host)

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
