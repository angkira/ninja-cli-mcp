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


# ============================================================================
# agent_run_and_diagnose — compound test/diagnostic execution & extraction
# ============================================================================


class FailureDetail(BaseModel):
    """Structured details of a diagnostic failure (test, linter, or compiler)."""

    test_name: str | None = Field(
        default=None, description="Name or identifier of failed test if applicable"
    )
    file_path: str | None = Field(
        default=None, description="File path associated with failure or diagnostic"
    )
    line_number: int | None = Field(
        default=None, description="Line number of failure or diagnostic if applicable"
    )
    error_message: str = Field(..., description="Concise error message or root cause")
    traceback: str | None = Field(
        default=None, description="Stripped or condensed traceback if applicable"
    )


class AgentRunAndDiagnoseRequest(BaseModel):
    """Request to run a command and distill diagnostic outcomes."""

    command: str = Field(..., description="Shell command to execute and diagnose")
    repo_root: str = Field(..., description="Repository root path")
    cwd: str | None = Field(default=None, description="Working directory (defaults to repo_root)")
    timeout: int = Field(default=120, description="Kill the command after this many seconds")
    allow_write: bool = Field(
        default=False, description="Must be True for commands that mutate files/state"
    )
    framework_hint: str | None = Field(
        default=None,
        description="Optional framework hint (e.g. 'pytest', 'ruff', 'mypy')",
    )


class AgentRunAndDiagnoseResult(BaseModel):
    """Distilled outcome of a diagnostic command execution."""

    success: bool = Field(..., description="Whether the command succeeded (exit code 0)")
    summary: str = Field(..., description="High-signal concise summary of outcome")
    returncode: int | None = Field(default=None, description="Process exit code")
    passed_count: int = Field(default=0, description="Count of passed tests or checks")
    failed_count: int = Field(default=0, description="Count of failed tests or checks")
    skipped_count: int = Field(default=0, description="Count of skipped tests or checks")
    error_count: int = Field(
        default=0, description="Count of errors or compiler/linter diagnostics"
    )
    failures: list[FailureDetail] = Field(
        default_factory=list, description="Structured failure details"
    )
    condensed_output: str = Field(default="", description="High-signal condensed stdout/stderr")
    truncated: bool = Field(default=False, description="True when output was truncated")
    safety_warnings: list[str] = Field(default_factory=list, description="Safety dry-run notes")


# ============================================================================
# agent_exec_pipeline — ordered multi-step execution with fail-fast
# ============================================================================


class PipelineStep(BaseModel):
    """A single execution step in an ordered pipeline."""

    command: str = Field(..., description="Shell command to execute")
    name: str | None = Field(default=None, description="Optional step name or label")
    cwd: str | None = Field(
        default=None, description="Working directory for this step (defaults to pipeline cwd)"
    )
    timeout: int = Field(default=120, description="Timeout in seconds for this step")
    allow_write: bool = Field(
        default=False, description="Must be True for commands that mutate files/state"
    )
    continue_on_error: bool = Field(
        default=False, description="If True, pipeline continues even if this step fails"
    )


class PipelineStepResult(BaseModel):
    """Result of a single executed pipeline step."""

    command: str = Field(..., description="Executed command")
    name: str | None = Field(default=None, description="Step name or label")
    success: bool = Field(..., description="Whether this step succeeded")
    returncode: int | None = Field(default=None, description="Process exit code (None if skipped)")
    duration_seconds: float = Field(default=0.0, description="Wall-clock duration in seconds")
    skipped: bool = Field(
        default=False, description="Whether this step was skipped due to prior failure"
    )
    summary: str = Field(..., description="Concise outcome summary")
    condensed_output: str = Field(
        default="", description="High-signal condensed output for this step"
    )


class AgentExecPipelineRequest(BaseModel):
    """Request to run an ordered sequence of shell commands."""

    steps: list[PipelineStep] = Field(..., description="Ordered list of pipeline steps to execute")
    repo_root: str = Field(..., description="Repository root path")
    cwd: str | None = Field(default=None, description="Default working directory for steps")
    fail_fast: bool = Field(
        default=True,
        description="Halt pipeline on first failing step unless step has continue_on_error",
    )


class AgentExecPipelineResult(BaseModel):
    """Result of executing a multi-step pipeline."""

    success: bool = Field(..., description="Whether the pipeline succeeded overall")
    summary: str = Field(..., description="Summary of overall pipeline execution")
    total_duration_seconds: float = Field(
        default=0.0, description="Total wall-clock duration of pipeline in seconds"
    )
    steps: list[PipelineStepResult] = Field(
        default_factory=list, description="Per-step execution results"
    )


# ============================================================================
# agent_distill_logs — clustering, deduplication, and error extraction
# ============================================================================


class LogCluster(BaseModel):
    """A cluster of repeating or identical log entries."""

    pattern: str = Field(..., description="Normalized message pattern representing the cluster")
    count: int = Field(..., description="Number of occurrences in the cluster")
    level: str = Field(default="UNKNOWN", description="Log level of this cluster")
    first_seen: str | None = Field(
        default=None, description="Timestamp of first occurrence if detected"
    )
    last_seen: str | None = Field(
        default=None, description="Timestamp of last occurrence if detected"
    )
    sample_line: str = Field(..., description="Sample raw log line from the cluster")


class AgentDistillLogsRequest(BaseModel):
    """Request to tail and distill log patterns."""

    module: str | None = Field(default=None, description="Daemon/module name (e.g. 'coder')")
    level: str | None = Field(default=None, description="Optional level filter (INFO/ERROR/...)")
    limit: int = Field(default=50, description="Max entries to retrieve (capped at 200)")
    session_id: str | None = Field(default=None, description="Optional session filter")


class AgentDistillLogsResult(BaseModel):
    """Distilled log analysis with clusters and isolated errors."""

    success: bool = Field(..., description="Whether the log distillation succeeded")
    summary: str = Field(..., description="Human-readable summary of distillation")
    total_lines_analyzed: int = Field(default=0, description="Total log lines processed")
    clusters: list[LogCluster] = Field(
        default_factory=list, description="Clusters of repeating log patterns"
    )
    isolated_errors: list[str] = Field(
        default_factory=list, description="Isolated multi-line error blocks or tracebacks"
    )
    source: str = Field(default="", description="Where entries came from")
