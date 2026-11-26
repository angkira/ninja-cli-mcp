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
import itertools
import json
import logging
import sys
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from mcp.server import Server, ServerRequestContext
from mcp.server.request_state import RequestStateBoundary, RequestStateSecurity
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp.types import (
    INVALID_PARAMS,
    CallToolRequestParams,
    CallToolResult,
    ElicitRequest,
    ElicitRequestFormParams,
    ElicitResult,
    InputRequiredResult,
    ListToolsResult,
    PaginatedRequestParams,
    TextContent,
    Tool,
    ToolAnnotations,
)
from mcp_types.version import MODERN_PROTOCOL_VERSIONS
from pydantic import ValidationError

from ninja_coder.models import (
    BranchDiscardRequest,
    BranchDiscardResult,
    BranchListRequest,
    BranchListResult,
    BranchMergeRequest,
    BranchMergeResult,
    GetAgentsRequest,
    GetAgentsResult,
    MultiAgentTaskRequest,
    MultiAgentTaskResult,
    ParallelPlanRequest,
    PlanExecutionResult,
    QueryLogsRequest,
    QueryLogsResult,
    SequentialPlanRequest,
    SimpleTaskRequest,
    SimpleTaskResult,
)
from ninja_coder.tools import get_executor
from ninja_common.jobs import JOB_STATUS_CANCELLED, JOB_STATUS_WORKING, JobManager
from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.mcp_ext.apply import apply_extensions
from ninja_common.mcp_ext.wiring import build_protocol_extensions
from ninja_common.mcp_meta import (
    ServerMeta,
    ToolMeta,
    apply_tool_meta,
    dict_result,
    elicit_confirm,
    model_result,
    patch_resource_link,
    server_icon,
    server_kwargs,
    tool_call_result,
)
from ninja_common.mcp_tasks import (
    ProgressCallback,
    SqliteTaskStore,
    make_session_progress_callback,
    task_scope,
)
from ninja_common.security import RequestDeduplicator


if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.context import HandlerResult

    from ninja_common.mcp_ext.models import Task


# NOTE: importing this module must NOT touch ``os.environ``. Config export
# (~/.ninja-mcp.env -> env) happens in :func:`run`, i.e. only when the server
# process is actually started. Tests import ``create_server`` for schema and
# in-memory client inspection, and must not inherit a developer's config.

# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Process-global deduplicator — shared across ALL sessions/connections so that
# client retries over NEW SSE sessions coalesce onto in-flight executions
# instead of spawning duplicate subprocesses.
_deduplicator: RequestDeduplicator | None = None


def _get_deduplicator() -> RequestDeduplicator:
    """Get the process-global request deduplicator, created lazily."""
    global _deduplicator
    if _deduplicator is None:
        _deduplicator = RequestDeduplicator()
    return _deduplicator


#: Tool names served through the submit/poll background-job API.
JOB_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "coder_submit_simple",
        "coder_submit_sequential",
        "coder_submit_parallel",
        "coder_job_status",
        "coder_job_result",
        "coder_job_cancel",
        "coder_jobs_list",
    }
)

#: Sync tools that spawn CLI execution and therefore register a durable job row
#: (the same store the submit/poll API uses) before running. The sync HTTP
#: response is unchanged; the row exists for observability/cancellation when
#: the client disappears mid-flight.
TRACKED_SYNC_TOOLS: frozenset[str] = frozenset(
    {
        "coder_simple_task",
        "coder_execute_plan_sequential",
        "coder_execute_plan_parallel",
        "coder_multi_agent_task",
    }
)

#: Tools a 2026-07-28 client that declared ``io.modelcontextprotocol/tasks``
#: receives a task handle for instead of a blocking result. Every other client
#: keeps the synchronous behaviour described by the tool schema.
TASK_TOOLS: frozenset[str] = frozenset(
    {
        "coder_simple_task",
        "coder_execute_plan_sequential",
        "coder_execute_plan_parallel",
        "coder_multi_agent_task",
    }
)

#: Shared JSON-schema fragment for the optional idempotency key. Added to the
#: sync tool schemas; the submit tool schemas are copies of those and inherit it.
_REQUEST_KEY_SCHEMA: dict[str, Any] = {
    "type": "string",
    "description": (
        "Supply the same request_key to safely retry after a timeout — duplicates "
        "join the in-flight run instead of re-executing."
    ),
}

#: Appended to every tool description that accepts a ``request_key``.
_REQUEST_KEY_NOTE: str = " Same request_key retries join the in-flight run."


def _make_job_progress_factory(
    store: SqliteTaskStore, label: str
) -> Callable[[str], ProgressCallback]:
    """Build a progress-callback factory that refreshes a job's status message.

    The returned callback rides the existing progress tick cadence (one write
    per tick), so DB writes stay bounded. Any store failure is swallowed and
    logged — progress bookkeeping must never break the actual work.
    """

    def _factory(job_id: str) -> ProgressCallback:
        heartbeats = itertools.count(1)

        async def _callback(
            current: float,
            total: float | None = None,
            message: str | None = None,
        ) -> None:
            detail = message.strip() if message else f"heartbeat {next(heartbeats)}"
            try:
                await store.update_task(job_id, status_message=f"{label}: {detail}")
            except Exception:
                logger.debug("Progress update for job %s failed", job_id, exc_info=True)

        return _callback

    return _factory


def _dedup_submit_key(request_key: str | None) -> str | None:
    """Return the deduplicator key for an idempotent submission, if requested."""
    if request_key:
        return f"submit:{request_key}"
    return None


async def _submit_or_join(
    request_key: str | None,
    submit: Callable[[], Awaitable[dict[str, Any]]],
) -> dict[str, Any]:
    """Run *submit*, coalescing duplicates that share a ``request_key``.

    With a key, concurrent and retried submissions join one in-flight run and
    every caller receives the same job payload; without one, *submit* runs as
    today.
    """
    dedup_key = _dedup_submit_key(request_key)
    if dedup_key is None:
        return await submit()
    joined: dict[str, Any] = await _get_deduplicator().deduplicate(dedup_key, submit)
    return joined


def _text_content(payload: dict[str, Any]) -> TextContent:
    """Render a dict payload as a pretty-printed JSON text block."""
    return TextContent(type="text", text=json.dumps(payload, indent=2))


def _result_payload(result: Any) -> CallToolResult:
    """Convert an executor result model into the storable/synchronous payload."""
    if result is None or not hasattr(result, "model_dump"):
        return CallToolResult(
            content=[
                _text_content(
                    {
                        "status": "error",
                        "error": "Tool produced no result (internal error)",
                        "error_type": "InternalError",
                    }
                )
            ],
            is_error=True,
        )
    links = [patch_resource_link(getattr(result, "patch_path", None))]
    return CallToolResult(
        content=[
            TextContent(type="text", text=json.dumps(result.model_dump(), indent=2)),
            *[link for link in links if link is not None],
        ],
        structured_content=json.loads(json.dumps(result.model_dump(), default=str)),
        is_error=False,
    )


def _job_status_payload(task: Task) -> dict[str, Any]:
    """Render a task record as the public job-status payload."""
    return {
        "job_id": task.task_id,
        "status": task.status,
        "created_at": task.created_at,
        "last_updated_at": task.last_updated_at,
        "status_message": task.status_message,
    }


def _job_handle_payload(task: Task, poll_interval_ms: int) -> dict[str, Any]:
    """Render the immediate response returned by a ``coder_submit_*`` call."""
    return {
        "job_id": task.task_id,
        "status": task.status,
        "poll_interval_ms": poll_interval_ms,
    }


def _stored_result(result: Any) -> tuple[str | None, dict[str, Any] | None]:
    """Extract stored text plus structured payload from a task result, if any."""
    if result is None:
        return None, None
    try:
        dumped = result.model_dump(mode="json", by_alias=True)
    except Exception:
        return None, None
    content = dumped.get("content") if isinstance(dumped, dict) else None
    text: str | None = None
    if content:
        first = content[0]
        if isinstance(first, dict) and first.get("type") == "text":
            maybe_text = first.get("text")
            text = maybe_text if isinstance(maybe_text, str) else None
    structured = dumped.get("structuredContent")
    if not isinstance(structured, dict):
        structured = None
    return text, structured


def _validation_error_payload(exc: ValidationError) -> dict[str, Any]:
    """Render a friendly, indexed validation error payload."""
    messages: list[str] = []
    for err in exc.errors():
        msg = str(err.get("msg", "Invalid input")).replace("Value error, ", "")
        if msg not in messages:
            messages.append(msg)
    detail = "\n".join(messages) or "Invalid tool input."
    return {"status": "error", "error": detail, "error_type": "InvalidPlanInput"}


# Tool definitions with JSON Schema
TOOLS: list[Tool] = [
    Tool(
        name="coder_simple_task",
        description=(
            "Tiny 1-2 line fix in one file/function (typo, field, small bugfix), "
            "in-place with safety-commit, no worktree. "
            "Quick model — not for multi-file work, use sequential. "
            "Summary only, no source code." + _REQUEST_KEY_NOTE
        ),
        input_schema={
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
                    "description": "Files/directories Ninja should focus on (for context). ⚠️ IMPORTANT: If using Aider as the code CLI, do NOT mix directories and individual files in context_paths. Either provide only directories (for repo-wide context) or only individual files.",
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
                "request_key": _REQUEST_KEY_SCHEMA,
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="coder_execute_plan_sequential",
        description=(
            "Ordered multi-step plan (multi-file features, refactors, rewrites). "
            "Heavy model, isolated ninja/* worktree." + _REQUEST_KEY_NOTE
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to repository root",
                },
                "mode": {
                    "type": "string",
                    "enum": ["quick", "full"],
                    "description": "Execution mode: 'quick' for fast single-pass, 'full' for review loops",
                    "default": "quick",
                },
                "use_dialogue_mode": {
                    "type": "boolean",
                    "description": "Use dialogue mode for persistent conversation across steps (default: false)",
                    "default": False,
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
                            "id": {
                                "type": "string",
                                "description": "Optional unique step id. Auto-generated as 'step_1', 'step_2', … when omitted.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional human-readable title. Derived from the first line of 'task' when omitted.",
                            },
                            "task": {
                                "type": "string",
                                "description": "REQUIRED. DETAILED specification of what code to write in this step. A step without a non-empty 'task' is rejected.",
                            },
                            "context_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Files/directories Ninja should focus on for this step. ⚠️ IMPORTANT: If using Aider as code CLI, do NOT mix directories and individual files in context_paths. Either provide only directories (for repo-wide context) or only individual files.",
                                "default": [],
                            },
                            "allowed_globs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Glob patterns for allowed file operations",
                            },
                            "deny_globs": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Glob patterns to deny file operations",
                            },
                            "max_iterations": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 10,
                                "description": "Max iterations for test-fix loop in full mode",
                                "default": 3,
                            },
                            "test_plan": {
                                "type": "object",
                                "properties": {
                                    "unit": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "Unit test commands",
                                    },
                                    "e2e": {
                                        "type": "array",
                                        "items": {"type": "string"},
                                        "description": "End-to-end test commands",
                                    },
                                },
                                "default": {},
                            },
                            "constraints": {
                                "type": "object",
                                "properties": {
                                    "max_tokens": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "description": "Max tokens (0 = unlimited)",
                                    },
                                    "time_budget_sec": {
                                        "type": "integer",
                                        "minimum": 0,
                                        "description": "Time budget in seconds (0 = unlimited)",
                                    },
                                },
                                "default": {},
                            },
                        },
                        # Only 'task' is conceptually required; it is
                        # enforced server-side with an indexed, model-readable
                        # error. Keeping this JSON schema permissive lets that
                        # error reach the model instead of the opaque
                        # schema-level rejection (e.g. demanding an 'id')
                        # produced by client-side input validation.
                        "required": [],
                    },
                },
                "request_key": _REQUEST_KEY_SCHEMA,
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_execute_plan_parallel",
        description=(
            "Independent steps in parallel (atomic, non-overlapping files). "
            "complexity every call: 'simple' = trivial edits in-place, no worktree; "
            "'complex' = real work in ninja/* worktree. Never mix — split into two calls."
            + _REQUEST_KEY_NOTE
        ),
        input_schema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "complex"],
                    "description": (
                        "REQUIRED: 'simple' = trivial edits in-place; "
                        "'complex' = real work in worktree. Split mixed batches."
                    ),
                    "default": "complex",
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
                            "id": {
                                "type": "string",
                                "description": "Optional unique step id. Auto-generated as 'step_1', 'step_2', … when omitted.",
                            },
                            "title": {
                                "type": "string",
                                "description": "Optional human-readable title. Derived from the first line of 'task' when omitted.",
                            },
                            "task": {
                                "type": "string",
                                "description": "REQUIRED. SIMPLE, FOCUSED specification of what code to write. Keep it minimal and atomic. A step without a non-empty 'task' is rejected.",
                            },
                            "context_paths": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Files/directories Ninja should focus on for this step. ⚠️ IMPORTANT: If using Aider as code CLI, do NOT mix directories and individual files in context_paths. Either provide only directories (for repo-wide context) or only individual files.",
                            },
                            "allowed_globs": {"type": "array", "items": {"type": "string"}},
                            "deny_globs": {"type": "array", "items": {"type": "string"}},
                            "max_iterations": {"type": "integer"},
                            "test_plan": {"type": "object"},
                            "constraints": {"type": "object"},
                        },
                        # Only 'task' is conceptually required; it is
                        # enforced server-side with an indexed, model-readable
                        # error. Keeping this JSON schema permissive lets that
                        # error reach the model instead of the opaque
                        # schema-level rejection (e.g. demanding an 'id')
                        # produced by client-side input validation.
                        "required": [],
                    },
                },
                "request_key": _REQUEST_KEY_SCHEMA,
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_get_agents",
        description="List specialized agents for multi-agent orchestration.",
        input_schema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="coder_multi_agent_task",
        description=(
            "Complex task with coordinated specialized agents (full-stack, system design, large refactors)."
            + _REQUEST_KEY_NOTE
        ),
        input_schema={
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": (
                        "Complex task description requiring multiple specialized agents. "
                        "Be specific about requirements (e.g., 'Build e-commerce platform with "
                        "React frontend, FastAPI backend, PostgreSQL database, and Docker deployment')"
                    ),
                },
                "repo_root": {
                    "type": "string",
                    "description": "Absolute path to the repository root",
                },
                "context_paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Files/directories for context",
                    "default": [],
                },
                "allowed_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Glob patterns for files the agents should focus on. "
                        "Prompt-level guidance only: this is NOT an enforced sandbox."
                    ),
                    "default": ["**/*"],
                },
                "deny_globs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Glob patterns for files the agents should avoid. "
                        "Prompt-level guidance only: this is NOT an enforced sandbox."
                    ),
                    "default": [],
                },
                "request_key": _REQUEST_KEY_SCHEMA,
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="coder_query_logs",
        description="Query JSONL logs for debugging (filter by session, task, CLI, level; limit/offset paging).",
        input_schema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Filter by session ID",
                    "default": "",
                },
                "task_id": {
                    "type": "string",
                    "description": "Filter by task ID",
                    "default": "",
                },
                "cli_name": {
                    "type": "string",
                    "description": "Filter by CLI name (aider, opencode)",
                    "default": "",
                },
                "level": {
                    "type": "string",
                    "description": "Filter by log level (INFO, DEBUG, WARNING, ERROR)",
                    "default": "",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum entries to return (1-1000)",
                    "default": 100,
                    "minimum": 1,
                    "maximum": 1000,
                },
                "offset": {
                    "type": "integer",
                    "description": "Number of entries to skip (for pagination)",
                    "default": 0,
                    "minimum": 0,
                },
            },
            "required": [],
        },
    ),
]

# Look up tool definitions by name (used for task-mode validation).
_TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


# --- Submit/poll background-job API -----------------------------------------
# These tools work in every MCP host, even ones that do not advertise the
# standard MCP Tasks capability: they start work in the server's background and
# return a job handle the caller polls. Schemas reuse the synchronous tool
# schemas so submit arguments stay identical.
_JOB_ID_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "job_id": {
            "type": "string",
            "description": "Job id returned by a coder_submit_* call.",
        }
    },
    "required": ["job_id"],
}

TOOLS.extend(
    [
        Tool(
            name="coder_submit_simple",
            description="Submit coder_simple_task as a background job: poll coder_job_status until terminal, then coder_job_result.",
            input_schema=dict(_TOOLS_BY_NAME["coder_simple_task"].input_schema),
        ),
        Tool(
            name="coder_submit_sequential",
            description="Submit coder_execute_plan_sequential as a background job: poll coder_job_status until terminal, then coder_job_result.",
            input_schema=dict(_TOOLS_BY_NAME["coder_execute_plan_sequential"].input_schema),
        ),
        Tool(
            name="coder_submit_parallel",
            description="Submit coder_execute_plan_parallel as a background job: poll coder_job_status until terminal, then coder_job_result.",
            input_schema=dict(_TOOLS_BY_NAME["coder_execute_plan_parallel"].input_schema),
        ),
        Tool(
            name="coder_job_status",
            description=(
                "Poll a coder_submit_* job until no longer working (working|completed|failed|"
                "cancelled), then call coder_job_result."
            ),
            input_schema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_job_result",
            description=(
                "Fetch a coder_submit_* job result (same payload as the sync tool); "
                "while working returns poll_interval_ms."
            ),
            input_schema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_job_cancel",
            description=(
                "Cancel a running coder_submit_* job; idempotent, safe for unknown or terminal ids."
            ),
            input_schema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_branches_list",
            description=(
                "List ninja/* isolation branches (committed agent work, checkout already "
                "removed), newest first. Read-only."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_root": {
                        "type": "string",
                        "description": "Absolute path to the repository root",
                    },
                },
                "required": ["repo_root"],
            },
        ),
        Tool(
            name="coder_branch_merge",
            description=(
                "Merge a ninja/* isolation branch into the repo's current branch. "
                "A conflicting merge is aborted and the repo is left unchanged."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_root": {
                        "type": "string",
                        "description": "Absolute path to the repository root",
                    },
                    "branch": {
                        "type": "string",
                        "description": "ninja/* branch to merge (see coder_branches_list)",
                    },
                },
                "required": ["repo_root", "branch"],
            },
        ),
        Tool(
            name="coder_branch_discard",
            description=(
                "Delete a ninja/* isolation branch. Refuses unmerged work unless force=true; "
                "only merge or discard after reviewing the changes."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "repo_root": {
                        "type": "string",
                        "description": "Absolute path to the repository root",
                    },
                    "branch": {
                        "type": "string",
                        "description": "ninja/* branch to delete (see coder_branches_list)",
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Delete even if the branch has unmerged commits",
                        "default": False,
                    },
                },
                "required": ["repo_root", "branch"],
            },
        ),
        Tool(
            name="coder_jobs_list",
            description="List background jobs oldest-first with cursor pagination.",
            input_schema={
                "type": "object",
                "properties": {
                    "cursor": {
                        "type": "string",
                        "description": "Opaque cursor returned as next_cursor by a previous call.",
                    },
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 100,
                        "description": "Maximum number of jobs to return.",
                    },
                },
                "required": [],
            },
        ),
    ]
)

_destructive = ToolAnnotations(destructive_hint=True)
_idempotent = ToolAnnotations(idempotent_hint=True)
_destructive_idempotent = ToolAnnotations(destructive_hint=True, idempotent_hint=True)
_readonly = ToolAnnotations(read_only_hint=True, idempotent_hint=True)

# Tool metadata: titles, behavior hints, and result models for
# outputSchema + structuredContent. Job-handle tools return plain dicts.
_TOOL_META: dict[str, ToolMeta] = {
    "coder_simple_task": ToolMeta(
        title="Simple code task",
        annotations=_destructive_idempotent,
        result_model=SimpleTaskResult,
    ),
    "coder_execute_plan_sequential": ToolMeta(
        title="Sequential plan",
        annotations=_destructive_idempotent,
        result_model=PlanExecutionResult,
    ),
    "coder_execute_plan_parallel": ToolMeta(
        title="Parallel plan",
        annotations=_destructive_idempotent,
        result_model=PlanExecutionResult,
    ),
    "coder_get_agents": ToolMeta(
        title="List agents", annotations=_readonly, result_model=GetAgentsResult
    ),
    "coder_multi_agent_task": ToolMeta(
        title="Multi-agent task",
        annotations=_destructive_idempotent,
        result_model=MultiAgentTaskResult,
    ),
    "coder_query_logs": ToolMeta(
        title="Query logs", annotations=_readonly, result_model=QueryLogsResult
    ),
    "coder_submit_simple": ToolMeta(
        title="Submit simple task", annotations=_destructive_idempotent
    ),
    "coder_submit_sequential": ToolMeta(
        title="Submit sequential plan", annotations=_destructive_idempotent
    ),
    "coder_submit_parallel": ToolMeta(
        title="Submit parallel plan", annotations=_destructive_idempotent
    ),
    "coder_job_status": ToolMeta(title="Job status", annotations=_readonly, result_model=None),
    "coder_job_result": ToolMeta(title="Job result", annotations=_readonly),
    "coder_job_cancel": ToolMeta(title="Cancel job", annotations=_destructive_idempotent),
    "coder_branches_list": ToolMeta(
        title="List branches", annotations=_readonly, result_model=BranchListResult
    ),
    "coder_branch_merge": ToolMeta(
        title="Merge branch", annotations=_destructive, result_model=BranchMergeResult
    ),
    "coder_branch_discard": ToolMeta(
        title="Discard branch",
        annotations=_destructive,
        result_model=BranchDiscardResult,
    ),
    "coder_jobs_list": ToolMeta(title="List jobs", annotations=_readonly),
}

TOOLS = apply_tool_meta(TOOLS, _TOOL_META, server_icon("coder"))


def _is_unmerged_refusal(message: str | None) -> bool:
    """Detect a refuse-to-delete-branch outcome caused by unmerged commits."""
    text = message or ""
    return "not fully merged" in text or "unmerged" in text.lower()


#: Key the branch-deletion confirmation is filed under in
#: ``InputRequiredResult.input_requests`` and, echoed back, in
#: ``CallToolRequestParams.input_responses``.
_CONFIRM_INPUT_KEY: str = "confirm_branch_delete"

#: ``op`` claim of the branch-discard ``request_state`` payload, so state minted
#: for another future operation can never be reused here.
_BRANCH_DISCARD_OP: str = "branch_discard"


def _branch_delete_schema(branch: str) -> dict[str, Any]:
    """JSON schema for the single ``confirm`` boolean the confirmation asks for."""
    return {
        "type": "object",
        "properties": {
            "confirm": {
                "type": "boolean",
                "title": "Delete branch",
                "description": f"Confirm: delete branch {branch}",
            }
        },
        "required": ["confirm"],
    }


def _encode_branch_discard_state(request: BranchDiscardRequest) -> str:
    """Mint the plaintext ``request_state`` for one branch-deletion round.

    The plaintext is handed to ``RequestStateBoundary``, which seals it before it
    reaches the wire; handlers never touch the codec.

    Args:
        request: The discard the state belongs to.

    Returns:
        JSON naming the operation, the branch and the repository it applies to.
    """
    return json.dumps(
        {
            "op": _BRANCH_DISCARD_OP,
            "branch": request.branch,
            "repo_root": request.repo_root,
            "issued_at": datetime.now(UTC).isoformat(),
        },
        sort_keys=True,
    )


def _verify_branch_discard_state(request: BranchDiscardRequest, request_state: str | None) -> None:
    """Reject an unsealed ``request_state`` that does not describe this discard.

    The boundary already binds the sealed token to the request name and
    arguments; this second check keeps the handler correct on its own terms.

    Args:
        request: The discard the retry asks for.
        request_state: The unsealed state the client echoed back.

    Raises:
        MCPError: ``request_state`` is missing, malformed, or names another
            operation, branch, or repository.
    """
    if request_state is None:
        raise MCPError(
            INVALID_PARAMS,
            "request_state is required to confirm the deletion of unmerged work",
        )
    try:
        state = json.loads(request_state)
    except (TypeError, ValueError):
        state = None
    expected = {
        "op": _BRANCH_DISCARD_OP,
        "branch": request.branch,
        "repo_root": request.repo_root,
    }
    if not isinstance(state, dict) or any(
        state.get(key) != value for key, value in expected.items()
    ):
        raise MCPError(
            INVALID_PARAMS,
            "request_state does not match this branch deletion",
        )


def _confirmed(response: object) -> bool:
    """True only when the client accepted the form and ticked the box."""
    if not isinstance(response, ElicitResult):
        return False
    return response.action == "accept" and (response.content or {}).get("confirm") is True


async def _force_discard_branch(
    executor: Any, request: BranchDiscardRequest, *, client_id: str
) -> BranchDiscardResult:
    """Re-run the discard with ``force`` and annotate a successful deletion."""
    forced = BranchDiscardRequest(
        repo_root=request.repo_root,
        branch=request.branch,
        force=True,
    )
    result = await executor.discard_branch(forced, client_id=client_id)
    if result.status == "ok":
        result = result.model_copy(
            update={"message": f"{result.message} (confirmed via elicitation)"}
        )
    return result


async def _discard_branch_with_confirmation(
    ctx: ServerRequestContext[Any, Any],
    params: CallToolRequestParams,
    request: BranchDiscardRequest,
    *,
    executor: Any,
    client_id: str,
) -> BranchDiscardResult | InputRequiredResult:
    """Discard a branch, confirming first when the branch holds unmerged work.

    A plain discard runs unconditionally. An unmerged-branch refusal without
    ``force`` becomes a confirmation round, carried the way the connection's
    protocol era allows: 2025-era connections keep the push-style elicitation
    (a server-initiated request mid-call), while 2026-07-28 connections answer
    with an ``input_required`` result the client resolves and retries.

    Args:
        ctx: Request context, used for the protocol version and the legacy session.
        params: The tool-call params, which carries the client's retry responses.
        request: The validated discard request.
        executor: Tool executor performing the git operation.
        client_id: Client identity for executor logging.

    Returns:
        The discard result, or the ``input_required`` round asking to confirm.

    Raises:
        MCPError: A retry carried a ``request_state`` that does not match this
            branch deletion.
    """
    if ctx.protocol_version not in MODERN_PROTOCOL_VERSIONS:
        # 2025-era connections still allow a server-initiated request mid-call.
        result = await executor.discard_branch(request, client_id=client_id)
        if request.force or not _is_unmerged_refusal(result.message):
            return result
        confirmed = await elicit_confirm(
            ctx.session,
            f"Branch '{request.branch}' has unmerged commits. Delete it anyway?",
            item_label=f"delete branch {request.branch}",
        )
        if confirmed:
            return await _force_discard_branch(executor, request, client_id=client_id)
        return result

    if params.input_responses:
        # The retry round. The state is verified before any git work, so a
        # tampered echo never triggers an operation; a confirmed answer forces
        # the deletion, and anything else re-answers with the live outcome.
        _verify_branch_discard_state(request, params.request_state)
        if _confirmed(params.input_responses.get(_CONFIRM_INPUT_KEY)):
            return await _force_discard_branch(executor, request, client_id=client_id)
        return await executor.discard_branch(request, client_id=client_id)

    result = await executor.discard_branch(request, client_id=client_id)
    if request.force or not _is_unmerged_refusal(result.message):
        return result

    # 2026-07-28 has no mid-call back-channel: ask in a retry instead.
    return InputRequiredResult(
        input_requests={
            _CONFIRM_INPUT_KEY: ElicitRequest(
                params=ElicitRequestFormParams(
                    message=f"Branch '{request.branch}' has unmerged commits. Delete it anyway?",
                    requested_schema=_branch_delete_schema(request.branch),
                )
            )
        },
        request_state=_encode_branch_discard_state(request),
    )


def create_server() -> Server:
    """
    Create and configure the MCP server with detailed instructions.

    Returns:
        Configured MCP Server instance.
    """
    # Durable store shared by the always-available submit/poll job API, so jobs
    # survive across calls and processes. The standard MCP Tasks extension
    # reuses this same store, so its task handles are durable over the same
    # rows the job API reads.
    store = SqliteTaskStore()
    # A previous daemon run cannot be resumed: any row still 'working' owned by
    # a demonstrably dead process is reconciled to 'failed' so it is observable
    # and cancellable. Tasks owned by live coexisting stdio/daemon processes
    # or legacy rows with unknown ownership are preserved.
    swept = store.sweep_stale_working("lost: daemon restart before completion")
    if swept:
        logger.info("Reconciled %d stale working jobs from dead owners", swept)
    jobs = JobManager(store)

    # Skills advertise ``skills/*`` and serve skill files through Resources;
    # Tasks turns the four long-running tools into durable task handles for
    # clients that declared it. Both are 2026-07-28 only.
    extensions = build_protocol_extensions("coder", store, TASK_TOOLS)

    # Use the process-global deduplicator for request deduplication
    deduplicator = _get_deduplicator()

    async def list_tools(
        _ctx: ServerRequestContext[Any, Any],
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        """Return the list of available tools."""
        return ListToolsResult(tools=TOOLS)

    async def call_tool(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult | InputRequiredResult:
        """Handle tool invocations synchronously.

        Long-running tools keep the connection busy; callers that expect more
        than ~60s use the ``coder_submit_*`` / ``coder_job_status`` /
        ``coder_job_result`` poll API, which returns a job handle immediately.
        """
        name = params.name
        arguments: dict[str, Any] = dict(params.arguments or {})

        async def _handle_job_tool() -> tuple[list, dict[str, Any] | None, bool]:
            """Serve the always-available submit/poll background-job tools."""
            executor = get_executor()
            request_key = str(arguments.get("request_key") or "") or None

            if name == "coder_submit_simple":
                try:
                    simple_request = SimpleTaskRequest(**arguments)
                except ValidationError as exc:
                    texts, structured = dict_result(_validation_error_payload(exc))
                    return texts, structured, True

                async def _simple_work() -> CallToolResult:
                    result = await executor.simple_task(simple_request, client_id="default")
                    return _result_payload(result)

                async def _submit_simple() -> dict[str, Any]:
                    task = await jobs.submit(
                        _simple_work,
                        status_message="coder_simple_task",
                        progress_factory=_make_job_progress_factory(store, "coder_simple_task"),
                    )
                    return _job_handle_payload(task, jobs.poll_interval_ms)

                handle = await _submit_or_join(request_key, _submit_simple)
                texts, structured = dict_result(handle)
                return texts, structured, False

            if name == "coder_submit_sequential":
                try:
                    sequential_request = SequentialPlanRequest(**arguments)
                except ValidationError as exc:
                    texts, structured = dict_result(_validation_error_payload(exc))
                    return texts, structured, True

                async def _sequential_work() -> CallToolResult:
                    result = await executor.execute_plan_sequential(
                        sequential_request, client_id="default"
                    )
                    return _result_payload(result)

                async def _submit_sequential() -> dict[str, Any]:
                    task = await jobs.submit(
                        _sequential_work,
                        status_message="coder_execute_plan_sequential",
                        progress_factory=_make_job_progress_factory(
                            store, "coder_execute_plan_sequential"
                        ),
                    )
                    return _job_handle_payload(task, jobs.poll_interval_ms)

                handle = await _submit_or_join(request_key, _submit_sequential)
                texts, structured = dict_result(handle)
                return texts, structured, False

            if name == "coder_submit_parallel":
                try:
                    parallel_request = ParallelPlanRequest(**arguments)
                except ValidationError as exc:
                    texts, structured = dict_result(_validation_error_payload(exc))
                    return texts, structured, True

                async def _parallel_work() -> CallToolResult:
                    result = await executor.execute_plan_parallel(
                        parallel_request, client_id="default"
                    )
                    return _result_payload(result)

                async def _submit_parallel() -> dict[str, Any]:
                    task = await jobs.submit(
                        _parallel_work,
                        status_message="coder_execute_plan_parallel",
                        progress_factory=_make_job_progress_factory(
                            store, "coder_execute_plan_parallel"
                        ),
                    )
                    return _job_handle_payload(task, jobs.poll_interval_ms)

                handle = await _submit_or_join(request_key, _submit_parallel)
                texts, structured = dict_result(handle)
                return texts, structured, False

            if name == "coder_jobs_list":
                try:
                    listed, next_cursor = await jobs.list_jobs(
                        arguments.get("cursor"), arguments.get("limit")
                    )
                except ValueError as exc:
                    # Tool-level (business) error envelope: the call itself
                    # succeeded, so it stays a non-error result.
                    texts, structured = dict_result(
                        {"status": "error", "error": str(exc), "error_type": "InvalidCursor"}
                    )
                    return texts, structured, False
                texts, structured = dict_result(
                    {
                        "jobs": [_job_status_payload(job) for job in listed],
                        "next_cursor": next_cursor,
                    }
                )
                return texts, structured, False

            raw_job_id = arguments.get("job_id")
            if raw_job_id is not None and not isinstance(raw_job_id, str):
                # The schema declares job_id as a string; coercing 12345 to
                # "12345" hides a client bug behind a confusing UnknownJob.
                texts, structured = dict_result(
                    {
                        "job_id": "",
                        "status": "error",
                        "error": "job_id must be a string",
                        "error_type": "InvalidInput",
                    }
                )
                return texts, structured, True
            job_id = (raw_job_id or "").strip()
            if not job_id:
                # The SDK no longer validates ``input_schema`` before dispatch,
                # so the required ``job_id`` is enforced here.
                texts, structured = dict_result(
                    {
                        "job_id": "",
                        "status": "error",
                        "error": "job_id is required",
                        "error_type": "InvalidInput",
                    }
                )
                return texts, structured, True
            unknown_payload = {
                "job_id": job_id,
                "status": "error",
                "error": f"Unknown job: {job_id}",
                "error_type": "UnknownJob",
            }

            if name == "coder_job_status":
                task = await jobs.status(job_id)
                if task is None:
                    texts, structured = dict_result(unknown_payload)
                    return texts, structured, False
                texts, structured = dict_result(_job_status_payload(task))
                return texts, structured, False

            if name == "coder_job_result":
                task = await jobs.status(job_id)
                if task is None:
                    texts, structured = dict_result(unknown_payload)
                    return texts, structured, False
                if task.status == JOB_STATUS_WORKING:
                    texts, structured = dict_result(
                        {
                            "job_id": job_id,
                            "status": task.status,
                            "poll_interval_ms": jobs.poll_interval_ms,
                        }
                    )
                    return texts, structured, False
                stored = await jobs.result(job_id)
                stored_text, stored_structured = _stored_result(stored)
                if stored_text is None:
                    texts, structured = dict_result(
                        {
                            "job_id": job_id,
                            "status": task.status,
                            "status_message": task.status_message,
                        }
                    )
                    return texts, structured, False
                if stored_structured is None:
                    try:
                        parsed = json.loads(stored_text)
                        stored_structured = (
                            parsed if isinstance(parsed, dict) else {"text": stored_text}
                        )
                    except (json.JSONDecodeError, TypeError):
                        stored_structured = {"text": stored_text}
                blocks: list = [TextContent(type="text", text=stored_text)]
                return blocks, stored_structured, False

            if name == "coder_job_cancel":
                task = await jobs.cancel(job_id)
                if task is None:
                    texts, structured = dict_result(
                        {"job_id": job_id, "status": JOB_STATUS_CANCELLED}
                    )
                    return texts, structured, False
                texts, structured = dict_result(_job_status_payload(task))
                return texts, structured, False

            raise ValueError(f"Unknown job tool: {name}")

        async def _invoke() -> tuple[list, dict[str, Any] | None, bool] | InputRequiredResult:
            if name in JOB_TOOL_NAMES:
                return await _handle_job_tool()
            client_id = "default"
            logger.info(f"[{client_id}] Tool called: {name}")
            logger.debug(f"[{client_id}] Arguments: {json.dumps(arguments, indent=2)}")
            executor = get_executor()
            SKIP_DEDUP = {
                "coder_get_agents",
                "coder_query_logs",
                "coder_branches_list",
                "coder_branch_merge",
                "coder_branch_discard",
            }
            request_key = str(arguments.get("request_key") or "") or None

            async def _dispatch() -> Any:
                if name == "coder_simple_task":
                    request = SimpleTaskRequest(**arguments)
                    return await executor.simple_task(request, client_id=client_id)
                elif name == "coder_execute_plan_sequential":
                    request = SequentialPlanRequest(**arguments)
                    return await executor.execute_plan_sequential(request, client_id=client_id)
                elif name == "coder_execute_plan_parallel":
                    request = ParallelPlanRequest(**arguments)
                    return await executor.execute_plan_parallel(request, client_id=client_id)
                elif name == "coder_get_agents":
                    request = GetAgentsRequest(**arguments)
                    return await executor.get_agents(request, client_id=client_id)
                elif name == "coder_multi_agent_task":
                    request = MultiAgentTaskRequest(**arguments)
                    return await executor.multi_agent_task(request, client_id=client_id)
                elif name == "coder_query_logs":
                    request = QueryLogsRequest(**arguments)
                    return await executor.query_logs(request, client_id=client_id)
                elif name == "coder_branches_list":
                    request = BranchListRequest(**arguments)
                    return await executor.list_branches(request, client_id=client_id)
                elif name == "coder_branch_merge":
                    request = BranchMergeRequest(**arguments)
                    return await executor.merge_branch(request, client_id=client_id)
                elif name == "coder_branch_discard":
                    request = BranchDiscardRequest(**arguments)
                    return await _discard_branch_with_confirmation(
                        ctx,
                        params,
                        request,
                        executor=executor,
                        client_id=client_id,
                    )
                else:
                    raise ValueError(f"Unknown tool: {name}")

            async def _execute() -> Any:
                # Every sync execution registers its own durable row so it stays
                # observable and cancellable if the client disappears mid-flight.
                if name not in TRACKED_SYNC_TOOLS:
                    return await _dispatch()

                captured: list[Any] = []

                async def _tracked_work() -> CallToolResult:
                    result = await _dispatch()
                    captured.append(result)
                    return _result_payload(result)

                await jobs.run_tracked(
                    _tracked_work,
                    status_message=name,
                    progress_factory=_make_job_progress_factory(store, name),
                )
                return captured[0] if captured else None

            try:
                if name in SKIP_DEDUP:
                    result = await _execute()
                else:
                    dedup_key = _dedup_submit_key(request_key)
                    key = (
                        dedup_key
                        if dedup_key is not None
                        else RequestDeduplicator.make_key(name, arguments)
                    )
                    result = await deduplicator.deduplicate(key, _execute)

                if isinstance(result, InputRequiredResult):
                    # Multi round-trip: the client resolves the embedded input
                    # requests and retries this call with `input_responses`.
                    logger.info(f"[{client_id}] Tool {name} awaits client input before completing")
                    return result

                if result is None or not hasattr(result, "model_dump"):
                    # Defensive: an executor must always return a result model.
                    # Never let a None/invalid result crash with AttributeError —
                    # return a proper MCP error envelope instead.
                    logger.error(
                        f"[{client_id}] Tool {name} returned invalid result: {type(result).__name__}"
                    )
                    texts, structured = dict_result(
                        {
                            "status": "error",
                            "error": f"Tool {name} produced no result (internal error)",
                            "error_type": "InternalError",
                        }
                    )
                    return texts, structured, True

                result_json = result.model_dump()
                logger.info(
                    f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
                )
                links = [patch_resource_link(getattr(result, "patch_path", None))]
                texts, structured = model_result(
                    result, extra_blocks=[link for link in links if link is not None]
                )
                return texts, structured, False

            except ValidationError as e:
                # Surface our friendly, indexed plan errors instead of pydantic's
                # multi-line dump. `_normalize_plan_steps` raises ValueError, which
                # pydantic wraps as "Value error, <message>".
                messages: list[str] = []
                for err in e.errors():
                    msg = str(err.get("msg", "Invalid input")).replace("Value error, ", "")
                    if msg not in messages:
                        messages.append(msg)
                detail = "\n".join(messages) or "Invalid tool input."
                logger.warning(f"[{client_id}] Tool {name} input rejected: {detail}")
                texts, structured = dict_result(
                    {
                        "status": "error",
                        "error": detail,
                        "error_type": "InvalidPlanInput",
                    }
                )
                return texts, structured, True

            except ValueError as e:
                if "Unknown tool" in str(e):
                    texts, structured = dict_result({"error": str(e)})
                    return texts, structured, True
                raise

            except MCPError:
                # Protocol-level failures (a tampered `request_state`, a refused
                # input request) belong in the JSON-RPC error channel, not in a
                # tool-result payload the model would read as an answer.
                raise

            except Exception as e:
                # Unhandled exception escaping the handler: framework-level.
                logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
                texts, structured = dict_result(
                    {"status": "error", "error": str(e), "error_type": type(e).__name__}
                )
                return texts, structured, True

        # Sync path: when the client passed a progressToken, bind a progress
        # scope so the ~10s streaming heartbeats from the driver reach the
        # client as notifications/progress instead of silence. This keeps
        # long sync calls (3-15 min) from hitting client timeouts. Without a
        # token there is nothing to send to — prefer coder_submit_* there.
        progress_token = (ctx.meta or {}).get("progress_token")
        if progress_token is not None:
            callback = make_session_progress_callback(ctx.session, progress_token)
            async with task_scope(f"sync-{name}", progress=callback):
                outcome = await _invoke()
        else:
            outcome = await _invoke()

        if isinstance(outcome, InputRequiredResult):
            return outcome
        texts, structured, is_error = outcome
        return tool_call_result((texts, structured), is_error=is_error)

    # The lowlevel server runs no extension interceptors, so the Tasks
    # ``tools/call`` interceptor is composed here. ``call_tool`` itself is left
    # untouched: it is the straight-through path for every non-declaring client.
    async def call_tool_with_tasks(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult | InputRequiredResult | dict[str, Any] | None:
        """Run ``call_tool`` behind the Tasks extension's interceptor."""

        async def call_next(_ctx: ServerRequestContext[Any, Any]) -> HandlerResult:
            return await call_tool(ctx, params)

        return await extensions.tasks_ext.intercept_tool_call(params, ctx, call_next)

    server = Server(
        "ninja-coder",
        version="0.2.0",
        **server_kwargs(
            ServerMeta(
                instructions="""Ninja Coder: delegate code writing to an AI agent.

CRITICAL: Ninja only writes code — no bash, no tests, no file reading for you. You validate.
Tools: coder_simple_task = tiny 1-2 line fix, in-place with safety-commit, no worktree;
coder_execute_plan_sequential = ordered multi-step work in an isolated ninja/* worktree;
coder_execute_plan_parallel = independent atomic steps; complexity='simple' in-place, 'complex' (default) worktree — never mix in one call.
Isolated plan work is committed to a ninja/* branch and its checkout is removed right after the run. Review and integrate it with coder_branches_list, coder_branch_merge (ninja/* only, conflicts aborted), and coder_branch_discard.
Spec format: GOOD = file, symbol, behavior, types, error handling (e.g. "In src/api/routes.py add POST /login ... 401 on failure").
Ninja returns a summary only (files changed, brief description); you read files, run tests, review. Same request_key retries join the in-flight run.
LONG TASKS: sync tools block the MCP connection for the whole run (often 3-15 min). For anything expected >60s prefer coder_submit_* then poll coder_job_status until terminal, then coder_job_result. Sync calls also emit progress notifications (~every 10s) when the client passes a progressToken — keep the token to avoid client timeouts.""",
                kind="coder",
            )
        ),
        on_list_tools=list_tools,
        on_call_tool=call_tool_with_tasks,
        on_list_resources=extensions.on_list_resources,
        on_read_resource=extensions.on_read_resource,
    )
    apply_extensions(server, [extensions.skills_ext, extensions.tasks_ext])
    # `coder_branch_discard` confirms deletion of unmerged work with a
    # multi-round-trip `input_required` result on 2026-07-28, where servers
    # cannot send requests to clients mid-call. This boundary seals the
    # plaintext `request_state` the handler mints and rejects any tampered,
    # expired, or replayed echo before the handler runs. Every other request
    # method (and every result that is not `input_required`) passes through.
    server.middleware.append(
        RequestStateBoundary(
            RequestStateSecurity.ephemeral(),
            default_audience="ninja-coder",
        )
    )
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
    """Run the MCP server over HTTP (SSE at /sse, streamable HTTP at /mcp)."""
    import uvicorn

    from ninja_common.mcp_http import build_asgi_app

    logger.info(f"Starting ninja-coder server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    app = build_asgi_app(server, host=host)

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
