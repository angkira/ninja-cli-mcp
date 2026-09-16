"""
Pydantic models for Ninja Agent MCP tools.

The agent is AUTONOMOUS: it owns shell/logs/processes-jobs ops plus its own
file analysis and review. It knows nothing about coder/researcher/secretary
and never delegates to them — code-writing is invoked directly via coder_*
tools by the central model, not through the agent.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ============================================================================
# Migration hint for every removed ``agent_delegate_*`` / ``agent_plan`` call.
# ============================================================================

#: Shared by the executor, the MCP server, and the CLI parser.
DELEGATE_MIGRATION = (
    "ninja-agent is autonomous: agent_delegate_* / agent_plan were removed. "
    "The agent owns only shell/logs/processes/jobs plus its own "
    "analyze/review. For code-writing call coder directly via coder_* tools "
    "(not through the agent)."
)


# ============================================================================
# agent_exec_command — guarded shell via the in-process runner
# ============================================================================


class AgentExecCommandRequest(BaseModel):
    """Request to run a guarded, non-interactive shell command."""

    command: str = Field(..., description="Shell command to execute")
    repo_root: str = Field(..., description="Repository root (default cwd / safety scope)")
    cwd: str | None = Field(default=None, description="Working directory (defaults to repo_root)")
    timeout: int = Field(default=120, description="Kill the command after this many seconds")
    allow_write: bool = Field(
        default=False, description="Must be True for commands that mutate files/state"
    )


class AgentExecCommandResult(BaseModel):
    """Outcome of a guarded shell invocation."""

    success: bool = Field(..., description="Whether the command exited with code 0")
    summary: str = Field(..., description="Human-readable outcome summary")
    returncode: int | None = Field(default=None, description="Process exit code")
    stdout: str = Field(default="", description="Capped, redacted stdout")
    stderr: str = Field(default="", description="Capped, redacted stderr")
    truncated: bool = Field(default=False, description="True when output was truncated")
    safety_warnings: list[str] = Field(default_factory=list, description="Safety dry-run notes")


# ============================================================================
# agent_tail_logs — capped, redacted log tails
# ============================================================================


class AgentTailLogsRequest(BaseModel):
    """Request for a capped, redacted log tail."""

    module: str | None = Field(default=None, description="Daemon/module name (e.g. 'coder')")
    level: str | None = Field(default=None, description="Optional level filter (INFO/ERROR/...)")
    limit: int = Field(default=50, description="Max entries (capped at 200)")
    session_id: str | None = Field(default=None, description="Optional session filter")


class AgentTailLogsResult(BaseModel):
    """Redacted log-tail result."""

    success: bool = Field(..., description="Whether the query succeeded")
    summary: str = Field(..., description="Human-readable summary")
    entries: list[str] = Field(default_factory=list, description="Redacted log lines")
    source: str = Field(default="", description="Where entries came from")


# ============================================================================
# agent_processes — read-only daemon + resource snapshot
# ============================================================================


class AgentProcessesRequest(BaseModel):
    """Request for a daemon/resource snapshot (no fields: strictly read-only)."""


class AgentProcessesResult(BaseModel):
    """Read-only daemon + host resource snapshot."""

    success: bool = Field(..., description="Whether the snapshot succeeded")
    summary: str = Field(..., description="Human-readable summary")
    daemons: dict = Field(default_factory=dict, description="Daemon status map")
    resources: dict = Field(default_factory=dict, description="Host resource stats")


# ============================================================================
# agent_jobs_overview — read-only job summary
# ============================================================================


class AgentJobsOverviewRequest(BaseModel):
    """Request for a read-only background-job overview."""

    limit: int = Field(default=20, description="Max jobs to include")


class AgentJobsOverviewResult(BaseModel):
    """Read-only job summary list."""

    success: bool = Field(..., description="Whether the query succeeded")
    summary: str = Field(..., description="Human-readable summary")
    jobs: list[dict] = Field(default_factory=list, description="Job summary entries")


# ============================================================================
# agent_analyze — own file analysis (direct reads + ast/grep, no secretary)
# ============================================================================


class AgentAnalyzeRequest(BaseModel):
    """Request to analyze a codebase or focus area."""

    repo_root: str = Field(..., description="Repository root path")
    focus: str | None = Field(
        default=None,
        description="Focus area or search term to narrow analysis (e.g. 'auth', 'parser')",
    )
    include_patterns: list[str] = Field(
        default=["**/*.py", "**/*.ts", "**/*.js", "**/*.go", "**/*.rs", "**/*.java"],
        description="Glob patterns of files to include in analysis",
    )


class AgentAnalyzeResult(BaseModel):
    """Result of a codebase analysis."""

    success: bool = Field(..., description="Whether analysis succeeded")
    summary: str = Field(..., description="Concise summary of the codebase")
    findings: list[str] = Field(default_factory=list, description="List of structured findings")
    touched_paths: list[str] = Field(
        default_factory=list, description="Paths inspected during analysis"
    )


# ============================================================================
# agent_review — own heuristic static review (no LLM, never writes)
# ============================================================================


class AgentReviewFinding(BaseModel):
    """A single review finding."""

    severity: str = Field(..., description="Severity of the finding")
    file_path: str = Field(..., description="File the finding applies to")
    line: int | None = Field(default=None, description="Line number, if applicable")
    message: str = Field(..., description="Human-readable finding message")


class AgentReviewRequest(BaseModel):
    """Request to review files without modifying them."""

    repo_root: str = Field(..., description="Repository root path")
    file_paths: list[str] = Field(..., description="Files to review")
    review_focus: str | None = Field(default=None, description="Optional area to focus review on")


class AgentReviewResult(BaseModel):
    """Result of a code review."""

    success: bool = Field(..., description="Whether review succeeded")
    findings: list[AgentReviewFinding] = Field(default_factory=list, description="Review findings")
    summary: str = Field(default="", description="Overall review summary")
