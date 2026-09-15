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
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolResult,
    Task,
    TextContent,
    Tool,
    ToolExecution,
)
from pydantic import ValidationError

from ninja_coder.models import (
    GetAgentsRequest,
    MultiAgentTaskRequest,
    ParallelPlanRequest,
    QueryLogsRequest,
    SequentialPlanRequest,
    SimpleTaskRequest,
)
from ninja_coder.tools import get_executor
from ninja_common.jobs import JOB_STATUS_CANCELLED, JOB_STATUS_WORKING, JobManager
from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.mcp_tasks import (
    SqliteTaskStore,
    install_tasks,
    refresh_task_after_cancel,
    server_task_scope,
)
from ninja_common.security import RequestDeduplicator


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
            isError=True,
        )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(result.model_dump(), indent=2))],
        isError=False,
    )


def _job_status_payload(task: Task) -> dict[str, Any]:
    """Render a task record as the public job-status payload."""
    return {
        "job_id": task.taskId,
        "status": task.status,
        "created_at": task.createdAt.isoformat(),
        "last_updated_at": task.lastUpdatedAt.isoformat(),
        "status_message": task.statusMessage,
    }


def _job_handle_payload(task: Task, poll_interval_ms: int) -> dict[str, Any]:
    """Render the immediate response returned by a ``coder_submit_*`` call."""
    return {
        "job_id": task.taskId,
        "status": task.status,
        "poll_interval_ms": poll_interval_ms,
    }


def _stored_result_text(result: Any) -> str | None:
    """Extract the first text block from a stored task result, if any."""
    if result is None:
        return None
    try:
        dumped = result.model_dump(mode="json", by_alias=True)
    except Exception:
        return None
    content = dumped.get("content") if isinstance(dumped, dict) else None
    if not content:
        return None
    first = content[0]
    if isinstance(first, dict) and first.get("type") == "text":
        text = first.get("text")
        return text if isinstance(text, str) else None
    return None


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
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Delegate CODE WRITING to Ninja AI agent using SIMPLE task specification. "
            "Ninja ONLY writes/edits code files based on your specification. "
            "\n\n"
            "✅ USE FOR REALLY simple edits ONLY: 1-2 lines, a tiny fix in ONE "
            "file/function (add a field, fix a typo, small bugfix). "
            "Runs IN-PLACE on your current branch with safety-commit, WITHOUT worktree. "
            "\n\n"
            "⚠️ WARNING: Runs on the fast 'quick' model with a short timeout. "
            "NEVER use for rewriting a class, multi-file features, large "
            "implementations, MR stabilization or big refactors - it will time out. "
            "Use coder_execute_plan_sequential instead. "
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
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="coder_execute_plan_sequential",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Execute a multi-step CODE WRITING plan sequentially. "
            "Each step delegates code writing to Ninja AI agent. "
            "\n\n"
            "✅ USE FOR: LONG multi-step plans where order matters and the work is too "
            "big for coder_simple_task: multi-file features, MR stabilization, big refactors, "
            "multi-step implementations, rewriting a class. Each step writes code based on your specification. "
            "Heavy model, longer timeout. Runs ISOLATED in a ninja/* worktree "
            "(main branch stays untouched; merge the branch when ready). "
            "\n\n"
            "📋 DIALOGUE MODE (OpenCode CLI only):\n"
            "When sequential steps are closely related (same module, feature, files, scope), "
            "enable dialogue mode by setting use_dialogue_mode=true.\n"
            "This maintains conversation context across all steps instead of spawning "
            "separate subprocesses for each step.\n"
            "Set NINJA_USE_DIALOGUE_MODE=true environment variable."
        ),
        inputSchema={
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
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_execute_plan_parallel",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Execute independent CODE WRITING steps in parallel with configurable concurrency. "
            "Each step delegates code writing to Ninja AI agent. "
            "You MUST consciously choose `complexity` on every call: "
            "'simple' for TRULY trivial edits (1-2 lines, tiny fix per step — "
            "runs IN-PLACE on your branch with safety-commit, NO worktree, "
            "fast quick-model, short timeout), 'complex' for real implementation "
            "work (runs ISOLATED in a ninja/* worktree). "
            "NEVER mix: split a mixed batch into TWO calls (simple separately, "
            "complex separately). "
            "Keep each step ATOMIC with non-overlapping file scopes to avoid conflicts. "
            "\n\n"
            "Examples: {repo_root, complexity: 'simple', steps: [{id, title, task: 'fix typo'}]} "
            "vs {repo_root, complexity: 'complex', steps: [{id, title, task: 'implement feature'}]}. "
            "\n\n"
            "❌ NEVER USE FOR: Running tests, executing commands, tasks with dependencies. "
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
                "complexity": {
                    "type": "string",
                    "enum": ["simple", "complex"],
                    "description": (
                        "REQUIRED choice: 'simple' = trivial edits (1-2 lines per step), "
                        "in-place without worktree; 'complex' = real implementation, "
                        "isolated ninja/* worktree. Never mix in one call — split mixed "
                        "batches into two calls."
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
            },
            "required": ["repo_root", "steps"],
        },
    ),
    Tool(
        name="coder_get_agents",
        description=(
            "Get information about available specialized agents for multi-agent orchestration. "
            "\n\n"
            "Returns list of 7 specialized agents:\n"
            "• Chief AI Architect - System design and architecture\n"
            "• Frontend Engineer - React, Vue, UI components\n"
            "• Backend Engineer - APIs, databases, server logic\n"
            "• DevOps Engineer - CI/CD, Docker, infrastructure\n"
            "• Oracle - Decision making and code review\n"
            "• Librarian - Documentation and organization\n"
            "• Explorer - Code analysis and refactoring\n"
            "\n\n"
            "✅ USE FOR: Understanding what agents are available for complex tasks."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
            "required": [],
        },
    ),
    Tool(
        name="coder_multi_agent_task",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Execute a complex task with multi-agent orchestration (oh-my-opencode). "
            "Automatically selects and coordinates specialized agents based on task requirements. "
            "\n\n"
            "✅ USE FOR: Full-stack applications, complex architectures, tasks requiring multiple "
            "specialized skills, large-scale refactoring, system design + implementation. "
            "\n\n"
            "🤖 AGENTS: Chief Architect, Frontend Engineer, Backend Engineer, DevOps, Oracle, "
            "Librarian, Explorer work in parallel with shared context. "
            "\n\n"
            "⏱️ NOTE: Multi-agent tasks take longer but provide comprehensive solutions."
        ),
        inputSchema={
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
            },
            "required": ["task", "repo_root"],
        },
    ),
    Tool(
        name="coder_query_logs",
        description=(
            "Query structured logs with filters for debugging and analysis. "
            "\n\n"
            "Logs are stored in JSONL format at ~/.cache/ninja-mcp/logs/ninja-YYYYMMDD.jsonl. "
            "Each entry includes: timestamp, level, message, session_id, task_id, cli_name, model, and extra metadata. "
            "\n\n"
            "✅ USE FOR: Debugging failed tasks, analyzing session history, tracking multi-agent execution, "
            "monitoring system behavior, finding errors. "
            "\n\n"
            "💡 FILTERS: Combine session_id, task_id, cli_name, and level to narrow results. "
            "Use limit/offset for pagination."
        ),
        inputSchema={
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
            description=(
                "Submit a SIMPLE CODE WRITING task to run in the BACKGROUND and "
                "return a job handle immediately. Works in any MCP host, even "
                "those without the standard MCP Tasks capability. Returns "
                "{job_id, status:'working', poll_interval_ms}: poll "
                "coder_job_status until terminal, then fetch coder_job_result. "
                "Arguments are identical to coder_simple_task."
            ),
            inputSchema=dict(_TOOLS_BY_NAME["coder_simple_task"].inputSchema),
        ),
        Tool(
            name="coder_submit_sequential",
            description=(
                "Submit a multi-step SEQUENTIAL CODE WRITING plan to run in the "
                "BACKGROUND and return a job handle immediately. Works in any MCP "
                "host, even those without the standard MCP Tasks capability. "
                "Returns {job_id, status:'working', poll_interval_ms}: poll "
                "coder_job_status until terminal, then fetch coder_job_result. "
                "Arguments are identical to coder_execute_plan_sequential."
            ),
            inputSchema=dict(_TOOLS_BY_NAME["coder_execute_plan_sequential"].inputSchema),
        ),
        Tool(
            name="coder_submit_parallel",
            description=(
                "Submit an INDEPENDENT PARALLEL CODE WRITING plan to run in the "
                "BACKGROUND and return a job handle immediately. Works in any MCP "
                "host, even those without the standard MCP Tasks capability. "
                "Returns {job_id, status:'working', poll_interval_ms}: poll "
                "coder_job_status until terminal, then fetch coder_job_result. "
                "Arguments are identical to coder_execute_plan_parallel."
            ),
            inputSchema=dict(_TOOLS_BY_NAME["coder_execute_plan_parallel"].inputSchema),
        ),
        Tool(
            name="coder_job_status",
            description=(
                "Get the status of a background job created by coder_submit_*. "
                "Returns {job_id, status, created_at, last_updated_at, "
                "status_message}; status is one of working|completed|failed|"
                "cancelled. Poll this until it is no longer 'working', then call "
                "coder_job_result."
            ),
            inputSchema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_job_result",
            description=(
                "Fetch the result payload of a background job created by "
                "coder_submit_*. While the job is still working it returns "
                "{job_id, status:'working', poll_interval_ms}; once terminal it "
                "returns the same JSON payload the synchronous tool would have "
                "returned."
            ),
            inputSchema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_job_cancel",
            description=(
                "Cancel a running background job and actually interrupt its work. "
                "Idempotent and safe for unknown or already-terminal job ids. "
                "Returns the final job status."
            ),
            inputSchema=dict(_JOB_ID_SCHEMA),
        ),
        Tool(
            name="coder_jobs_list",
            description=(
                "List known background jobs (oldest first) with optional cursor "
                "pagination. Returns {jobs: [...], next_cursor}."
            ),
            inputSchema={
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

_TOOLS_BY_NAME.update({tool.name: tool for tool in TOOLS if tool.name in JOB_TOOL_NAMES})


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
4. 🥷 CALL coder_simple_task with specification
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

• coder_simple_task
  REALLY simple edits only: 1-2 lines, tiny fix in one file/function.
  In-place + safety-commit, WITHOUT worktree. NEVER for class rewrites
  or multi-file work — use sequential. Returns: Summary only (files changed, brief description)

• coder_execute_plan_sequential
  Long multi-step plans where order matters. WITH ninja/* worktree, heavy model.
  Returns: Summary per step

• coder_execute_plan_parallel
  Independent tasks at once (atomic steps, non-overlapping files).
  complexity='simple' = trivial edits, IN-PLACE without worktree;
  complexity='complex' (default) = real work, WITH ninja/* worktree.
  Never mix in one call — split into two calls.
  Returns: Summary per step + merge report

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 EXAMPLES:

User: "Add user authentication"

You:
1. Read existing code structure (if needed)
2. Plan: Need User model, auth routes, password hashing
3. Call coder_simple_task with detailed spec:
   "Create authentication system:
    - src/models/user.py: User class with email, password_hash
    - src/auth/password.py: hash_password and verify_password using bcrypt
    - src/api/auth.py: /login and /register endpoints
    Include type hints, docstrings, error handling"
4. Review Ninja's summary
5. Run tests yourself: bash "pytest tests/test_auth.py"
6. If tests fail, call coder_simple_task again with fix specification

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ REMEMBER:
   • Ninja writes code, YOU orchestrate
   • Ninja returns summaries, NOT source code
   • YOU read files, run tests, validate
   • Write detailed specs, get quality code

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""",
    )

    # Enable standard MCP Tasks (background/asynchronous tool execution) with a
    # durable store and real cancellation of running work. Registers
    # tasks/get | tasks/result | tasks/list | tasks/cancel and declares the
    # ServerTasksCapability during initialization.
    #
    # The same store backs the always-available submit/poll job API below, so
    # both views agree on jobs and survive across calls and processes.
    store = SqliteTaskStore()
    install_tasks(server, store=store)
    jobs = JobManager(store)

    # Use the process-global deduplicator for request deduplication
    deduplicator = _get_deduplicator()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        """Handle tool invocations, synchronously or as a background task.

        When the client sends a task-augmented ``tools/call`` (standard MCP
        Tasks capability) for a tool marked ``taskSupport="optional"``, the work
        runs in the background and a ``CreateTaskResult`` handle is returned
        immediately. Otherwise the tool runs synchronously as before.
        """
        request_ctx = server.request_context
        experimental = request_ctx.experimental
        tool_definition = _TOOLS_BY_NAME.get(name)
        if tool_definition is not None:
            experimental.validate_for_tool(tool_definition)

        async def _handle_job_tool() -> list[TextContent]:
            """Serve the always-available submit/poll background-job tools."""
            executor = get_executor()

            if name == "coder_submit_simple":
                try:
                    simple_request = SimpleTaskRequest(**arguments)
                except ValidationError as exc:
                    return [_text_content(_validation_error_payload(exc))]

                async def _simple_work() -> CallToolResult:
                    result = await executor.simple_task(simple_request, client_id="default")
                    return _result_payload(result)

                task = await jobs.submit(_simple_work, status_message="coder_simple_task")
                return [_text_content(_job_handle_payload(task, jobs.poll_interval_ms))]

            if name == "coder_submit_sequential":
                try:
                    sequential_request = SequentialPlanRequest(**arguments)
                except ValidationError as exc:
                    return [_text_content(_validation_error_payload(exc))]

                async def _sequential_work() -> CallToolResult:
                    result = await executor.execute_plan_sequential(
                        sequential_request, client_id="default"
                    )
                    return _result_payload(result)

                task = await jobs.submit(
                    _sequential_work, status_message="coder_execute_plan_sequential"
                )
                return [_text_content(_job_handle_payload(task, jobs.poll_interval_ms))]

            if name == "coder_submit_parallel":
                try:
                    parallel_request = ParallelPlanRequest(**arguments)
                except ValidationError as exc:
                    return [_text_content(_validation_error_payload(exc))]

                async def _parallel_work() -> CallToolResult:
                    result = await executor.execute_plan_parallel(
                        parallel_request, client_id="default"
                    )
                    return _result_payload(result)

                task = await jobs.submit(
                    _parallel_work, status_message="coder_execute_plan_parallel"
                )
                return [_text_content(_job_handle_payload(task, jobs.poll_interval_ms))]

            job_id = str(arguments.get("job_id", ""))
            unknown = _text_content(
                {
                    "job_id": job_id,
                    "status": "error",
                    "error": f"Unknown job: {job_id}",
                    "error_type": "UnknownJob",
                }
            )

            if name == "coder_job_status":
                task = await jobs.status(job_id)
                return [unknown] if task is None else [_text_content(_job_status_payload(task))]

            if name == "coder_job_result":
                task = await jobs.status(job_id)
                if task is None:
                    return [unknown]
                if task.status == JOB_STATUS_WORKING:
                    return [
                        _text_content(
                            {
                                "job_id": job_id,
                                "status": task.status,
                                "poll_interval_ms": jobs.poll_interval_ms,
                            }
                        )
                    ]
                stored_text = _stored_result_text(await jobs.result(job_id))
                if stored_text is None:
                    stored_text = json.dumps(
                        {
                            "job_id": job_id,
                            "status": task.status,
                            "status_message": task.statusMessage,
                        },
                        indent=2,
                    )
                return [TextContent(type="text", text=stored_text)]

            if name == "coder_job_cancel":
                task = await jobs.cancel(job_id)
                if task is None:
                    return [_text_content({"job_id": job_id, "status": JOB_STATUS_CANCELLED})]
                return [_text_content(_job_status_payload(task))]

            # coder_jobs_list
            try:
                listed, next_cursor = await jobs.list_jobs(
                    arguments.get("cursor"), arguments.get("limit")
                )
            except ValueError as exc:
                return [
                    _text_content(
                        {"status": "error", "error": str(exc), "error_type": "InvalidCursor"}
                    )
                ]
            return [
                _text_content(
                    {
                        "jobs": [_job_status_payload(job) for job in listed],
                        "next_cursor": next_cursor,
                    }
                )
            ]

        async def _invoke() -> list[TextContent]:
            if name in JOB_TOOL_NAMES:
                return await _handle_job_tool()
            client_id = "default"
            logger.info(f"[{client_id}] Tool called: {name}")
            logger.debug(f"[{client_id}] Arguments: {json.dumps(arguments, indent=2)}")
            executor = get_executor()
            SKIP_DEDUP = {"coder_get_agents", "coder_query_logs"}

            async def _execute() -> Any:
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
                else:
                    raise ValueError(f"Unknown tool: {name}")

            try:
                if name in SKIP_DEDUP:
                    result = await _execute()
                else:
                    key = RequestDeduplicator.make_key(name, arguments)
                    result = await deduplicator.deduplicate(key, _execute)

                if result is None or not hasattr(result, "model_dump"):
                    # Defensive: an executor must always return a result model.
                    # Never let a None/invalid result crash with AttributeError —
                    # return a proper MCP error envelope instead.
                    logger.error(
                        f"[{client_id}] Tool {name} returned invalid result: {type(result).__name__}"
                    )
                    return [
                        TextContent(
                            type="text",
                            text=json.dumps(
                                {
                                    "status": "error",
                                    "error": f"Tool {name} produced no result (internal error)",
                                    "error_type": "InternalError",
                                }
                            ),
                        )
                    ]

                result_json = result.model_dump()
                logger.info(
                    f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
                )
                return [TextContent(type="text", text=json.dumps(result_json, indent=2))]

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
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {
                                "status": "error",
                                "error": detail,
                                "error_type": "InvalidPlanInput",
                            }
                        ),
                    )
                ]

            except ValueError as e:
                if "Unknown tool" in str(e):
                    return [TextContent(type="text", text=json.dumps({"error": str(e)}))]
                raise

            except Exception as e:
                logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
                return [
                    TextContent(
                        type="text",
                        text=json.dumps(
                            {"status": "error", "error": str(e), "error_type": type(e).__name__}
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
                        # The task was cancelled while work was in flight. Sync
                        # the SDK's cached status so it skips auto-completion of
                        # an already-terminal task (avoids tearing down tasks).
                        await refresh_task_after_cancel(task)
                    return CallToolResult(content=list(content), isError=False)

            return await experimental.run_task(_work)

        return await _invoke()

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
