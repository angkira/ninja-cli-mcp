"""
Pydantic models for Ninja Coder MCP tools.

These models define the API surface for the coder module.
All models use strict validation and comprehensive type hints.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ExecutionMode(str, Enum):
    """Execution mode for plan steps."""

    QUICK = "quick"
    FULL = "full"


class TaskComplexity(str, Enum):
    """Task complexity levels for intelligent model selection."""

    PARALLEL = "parallel"  # Multiple independent tasks
    SEQUENTIAL = "sequential"  # Multi-step dependent tasks
    QUICK = "quick"  # Single-pass simple task


class ModelClass(str, Enum):
    """Model capability tiers for abstract model selection.

    Callers pick a tier instead of a concrete model id, so routing stays
    configurable without code changes:

    - SMART: strongest model for complex/high-stakes work
    - BALANCED: default tier for ordinary code tasks
    - FAST: cheapest/fastest for trivial or high-volume work
    """

    SMART = "smart"
    BALANCED = "balanced"
    FAST = "fast"


class TestPlan(BaseModel):
    """Test commands to run for validation."""

    unit: list[str] = Field(default_factory=list, description="Unit test commands")
    e2e: list[str] = Field(default_factory=list, description="End-to-end test commands")


class StepConstraints(BaseModel):
    """Resource constraints for a plan step."""

    max_tokens: int = Field(default=0, ge=0, description="Max tokens (0 = unlimited)")
    time_budget_sec: int = Field(
        default=0, ge=0, description="Time budget in seconds (0 = unlimited)"
    )


class PlanStep(BaseModel):
    """A single step in an execution plan.

    Only ``task`` is required: it carries the actual instruction for the AI
    code CLI. ``id`` and ``title`` are optional conveniences — they are
    auto-derived so a caller cannot fail a whole plan just for omitting a
    label (this exact failure produced
    ``Input validation error: 'id' is a required property``).
    """

    id: str = Field(
        default="",
        description="Unique step identifier. Optional — auto-generated as 'step_N' when omitted.",
    )
    title: str = Field(
        default="",
        description="Human-readable step title. Optional — derived from the first task line when omitted.",
    )
    task: str = Field(..., description="Detailed task description for the AI code CLI")
    context_paths: list[str] = Field(
        default_factory=list,
        description="Paths to pay special attention to",
    )
    allowed_globs: list[str] = Field(
        default_factory=list,
        description="Glob patterns for allowed file operations",
    )
    deny_globs: list[str] = Field(
        default_factory=list,
        description="Glob patterns to deny file operations",
    )
    max_iterations: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Max iterations for test-fix loop in full mode",
    )
    test_plan: TestPlan = Field(
        default_factory=TestPlan,
        description="Test commands to validate the step",
    )
    constraints: StepConstraints = Field(
        default_factory=StepConstraints,
        description="Resource constraints",
    )

    @model_validator(mode="after")
    def _fill_optional_defaults(self) -> PlanStep:
        """Backfill ``id``/``title`` so downstream code always sees strings."""
        if not self.id.strip():
            self.id = f"step_{uuid.uuid4().hex[:8]}"
        if not self.title.strip():
            stripped = self.task.strip()
            first_line = stripped.splitlines()[0] if stripped else self.id
            self.title = first_line[:80]
        return self


def _normalize_plan_steps(steps: Any) -> Any:
    """Validate and normalize a raw ``steps`` array before ``PlanStep`` parsing.

    Produces a model-readable error naming the offending index instead of the
    opaque ``Input validation error: '<field>' is a required property`` emitted
    by schema-level client validation.

    Rules:
        - ``steps`` must be an array (an empty array remains a valid no-op).
        - Every element must be a step object (``dict`` or ``PlanStep``).
        - Every step must carry a non-empty string ``task`` (the only truly
          required field — the instruction for the AI code CLI).
        - ``id`` defaults to ``step_<n>`` (1-based); ``title`` defaults to the
          first line of ``task``.

    Args:
        steps: Raw value supplied for the ``steps`` field.

    Returns:
        The (possibly mutated) steps value, suitable for ``PlanStep`` parsing.

    Raises:
        ValueError: With a precise, indexed message suitable to return to the
            calling model.
    """
    if not isinstance(steps, list):
        raise ValueError(
            "'steps' must be an array of step objects (got "
            f"{type(steps).__name__}). Each step needs a 'task' — the instruction "
            "for the AI code CLI."
        )
    for i, step in enumerate(steps):
        if isinstance(step, PlanStep):
            if not step.task.strip():
                raise ValueError(f"steps[{i}] is missing the required 'task' field.")
            continue
        if not isinstance(step, dict):
            raise ValueError(
                f"steps[{i}] must be an object, got {type(step).__name__}. "
                "Each step is e.g. {'id': 's1', 'title': 'Add helper', 'task': '...'}."
            )
        task = step.get("task")
        if not isinstance(task, str) or not task.strip():
            raise ValueError(
                f"steps[{i}] is missing the required 'task' field. Put the instruction "
                f"for the AI code CLI in 'task'. Fields received: {sorted(step.keys())}."
            )
        if not step.get("id"):
            step["id"] = f"step_{i + 1}"
        if not step.get("title"):
            step["title"] = task.strip().splitlines()[0][:80]
    return steps


# ============================================================================
# Request Models
# ============================================================================


class SimpleTaskRequest(BaseModel):
    """Request for a simple single-pass task execution."""

    task: str = Field(..., description="Task description for the AI code CLI")
    repo_root: str = Field(..., description="Absolute path to repository root")
    context_paths: list[str] = Field(
        default_factory=list,
        description="Paths to pay special attention to",
    )
    allowed_globs: list[str] = Field(
        default_factory=list,
        description="Glob patterns for allowed file operations",
    )
    deny_globs: list[str] = Field(
        default_factory=list,
        description="Glob patterns to deny file operations",
    )
    mode: Literal["quick"] = Field(
        default="quick",
        description="Execution mode (future-proof)",
    )
    model_class: ModelClass | None = Field(
        default=None,
        description="Model tier: smart, balanced, or fast. If unset, the default "
        "routing for the task type is used.",
    )


class SequentialPlanRequest(BaseModel):
    """Request for sequential plan execution.

    Enable dialogue mode (persistent conversation) when:
    - Multiple steps are closely related (same module, feature, files)
    - Steps build upon previous context
    - Set USE_DIALOGUE_MODE=true environment variable

    Without dialogue mode, each step spawns a new subprocess.
    With dialogue mode, AI maintains context across all steps.
    """

    repo_root: str = Field(..., description="Absolute path to repository root")
    mode: ExecutionMode = Field(
        default=ExecutionMode.QUICK,
        description="Execution mode (future-proof)",
    )
    use_dialogue_mode: bool = Field(
        default=False,
        description="Use dialogue mode for persistent conversation across steps (set NINJA_USE_DIALOGUE_MODE=true)",
    )
    global_allowed_globs: list[str] = Field(
        default_factory=list,
        description="Global allowed glob patterns",
    )
    global_deny_globs: list[str] = Field(
        default_factory=list,
        description="Global deny glob patterns",
    )
    steps: list[PlanStep] = Field(..., description="Plan steps to execute in order")

    @model_validator(mode="before")
    @classmethod
    def _validate_steps(cls, data: Any) -> Any:
        if isinstance(data, dict) and "steps" in data:
            _normalize_plan_steps(data["steps"])
        return data


#: Complexity selector for parallel plans. Kept as a Literal alias (not a
#: member of TaskComplexity) to avoid collisions: TaskComplexity routes
#: models (quick/sequential/parallel), while this routes isolation
#: (simple=in-place, complex=worktree).
ParallelPlanComplexity = Literal["simple", "complex"]


class ParallelPlanRequest(BaseModel):
    """Request for parallel plan execution."""

    repo_root: str = Field(..., description="Absolute path to repository root")
    complexity: ParallelPlanComplexity = Field(
        default="complex",
        description=(
            "REQUIRED choice, default 'complex'. 'simple' = trivial edits "
            "(1-2 lines, tiny fix per step), runs IN-PLACE without worktree "
            "(task_type=quick). 'complex' = real implementation work, runs "
            "ISOLATED in a ninja/* worktree (task_type=parallel_plan). "
            "Never mix: split a mixed batch into two calls."
        ),
    )
    mode: ExecutionMode = Field(
        default=ExecutionMode.QUICK,
        description="Execution mode",
    )
    fanout: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum concurrent executions",
    )
    global_allowed_globs: list[str] = Field(
        default_factory=list,
        description="Global allowed glob patterns",
    )
    global_deny_globs: list[str] = Field(
        default_factory=list,
        description="Global deny glob patterns",
    )
    steps: list[PlanStep] = Field(..., description="Plan steps to execute in parallel")

    @model_validator(mode="before")
    @classmethod
    def _validate_steps(cls, data: Any) -> Any:
        if isinstance(data, dict) and "steps" in data:
            _normalize_plan_steps(data["steps"])
        return data


# ============================================================================
# Response Models
# ============================================================================


class StepResult(BaseModel):
    """Result of a single plan step execution."""

    id: str = Field(..., description="Step identifier")
    status: Literal["ok", "fail", "skipped"] = Field(..., description="Execution status")
    summary: str = Field(..., description="Brief summary of what was done")
    files_touched: list[str] = Field(
        default_factory=list,
        description="Files that were modified in this step",
    )
    error_message: str | None = Field(
        None,
        description="Error message if step failed",
    )


class MergeReport(BaseModel):
    """Report on merge strategy for parallel execution."""

    strategy: str = Field(..., description="Merge strategy used or recommended")
    notes: str = Field(default="", description="Additional merge notes")


class SimpleTaskResult(BaseModel):
    """Result of a simple task execution."""

    status: Literal["ok", "error"] = Field(..., description="Execution status")
    summary: str = Field(..., description="Brief summary of what was done")
    notes: str = Field(default="", description="Additional notes or warnings")
    logs_ref: str = Field(default="", description="Path to detailed logs")
    suspected_touched_paths: list[str] = Field(
        default_factory=list,
        description="Paths that were likely modified (best-effort)",
    )


class PlanExecutionResult(BaseModel):
    """Result of plan execution (sequential or parallel)."""

    overall_status: Literal["success", "partial", "failed"] = Field(
        ..., description="Overall execution status"
    )
    steps: list[StepResult] = Field(..., description="Per-step results")
    files_modified: list[str] = Field(
        default_factory=list,
        description="All files modified across all steps",
    )
    notes: str = Field(default="", description="Additional notes or warnings")
    execution_time: float | None = Field(
        None,
        description="Total execution time in seconds",
    )


# Multi-Agent Models


class AgentInfo(BaseModel):
    """Information about a specialized agent."""

    name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Agent description")
    keywords: list[str] = Field(..., description="Keywords that trigger this agent")


class GetAgentsRequest(BaseModel):
    """Request to get available agents."""

    pass  # No parameters needed


class GetAgentsResult(BaseModel):
    """Result of getting agents."""

    status: Literal["ok", "error"] = Field(..., description="Status")
    total_agents: int = Field(..., description="Total number of available agents")
    agents: list[AgentInfo] = Field(..., description="List of available agents")


class MultiAgentTaskRequest(BaseModel):
    """Request to execute task with multi-agent orchestration."""

    task: str = Field(..., description="Task description")
    repo_root: str = Field(..., description="Absolute path to repository root")
    context_paths: list[str] = Field(
        default_factory=list,
        description="Files/directories to focus on",
    )
    allowed_globs: list[str] = Field(
        default_factory=lambda: ["**/*"],
        description="Allowed file patterns",
    )
    deny_globs: list[str] = Field(
        default_factory=list,
        description="Denied file patterns",
    )


class MultiAgentTaskResult(BaseModel):
    """Result of multi-agent task execution."""

    status: Literal["ok", "error"] = Field(..., description="Execution status")
    summary: str = Field(..., description="Task execution summary")
    notes: str = Field(default="", description="Additional notes")
    agents_used: list[str] = Field(..., description="Agents that were activated")
    suspected_touched_paths: list[str] = Field(
        default_factory=list,
        description="Files modified",
    )
    session_id: str | None = Field(None, description="Session ID if session was used")
    message: str = Field(..., description="Result message")


# ============================================================================
# Log Query Models
# ============================================================================


class QueryLogsRequest(BaseModel):
    """Request to query structured logs."""

    session_id: str | None = Field(None, description="Filter by session ID")
    task_id: str | None = Field(None, description="Filter by task ID")
    cli_name: str | None = Field(None, description="Filter by CLI name (aider, opencode)")
    level: str | None = Field(None, description="Filter by log level (INFO, DEBUG, WARNING, ERROR)")
    limit: int = Field(100, ge=1, le=1000, description="Maximum entries to return")
    offset: int = Field(0, ge=0, description="Number of entries to skip")


class QueryLogsResult(BaseModel):
    """Result of log query."""

    status: Literal["ok", "error"] = Field(..., description="Query status")
    entries: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Log entries matching filters",
    )
    total_count: int = Field(..., description="Total matching entries")
    returned_count: int = Field(..., description="Number of entries returned")
    message: str = Field(..., description="Result message")
