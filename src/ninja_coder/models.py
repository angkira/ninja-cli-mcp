"""
Pydantic models for Ninja Coder MCP tools.

These models define the API surface for the coder module.
All models use strict validation and comprehensive type hints.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ExecutionMode(str, Enum):
    """Execution mode for plan steps."""

    QUICK = "quick"
    FULL = "full"


class TaskComplexity(str, Enum):
    """Task complexity levels for intelligent model selection."""

    PARALLEL = "parallel"  # Multiple independent tasks
    SEQUENTIAL = "sequential"  # Multi-step dependent tasks
    QUICK = "quick"  # Single-pass simple task


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
    """A single step in an execution plan."""

    id: str = Field(..., description="Unique step identifier")
    title: str = Field(..., description="Human-readable step title")
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


class ParallelPlanRequest(BaseModel):
    """Request for parallel plan execution."""

    repo_root: str = Field(..., description="Absolute path to repository root")
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


class RunTestsRequest(BaseModel):
    """Request to run tests via the AI code CLI."""

    repo_root: str = Field(..., description="Absolute path to repository root")
    commands: list[str] = Field(..., description="Test commands to execute")
    timeout_sec: int = Field(
        default=600,
        ge=10,
        le=3600,
        description="Timeout in seconds",
    )


class ApplyPatchRequest(BaseModel):
    """Request to apply a patch (delegated to AI code CLI)."""

    repo_root: str = Field(..., description="Absolute path to repository root")
    patch_content: str = Field(default="", description="Patch content (if applicable)")
    patch_description: str = Field(default="", description="Description of the patch")


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


class TestResult(BaseModel):
    """Result of test execution."""

    status: Literal["ok", "fail", "error"] = Field(..., description="Test status")
    summary: str = Field(..., description="Test summary")
    logs_ref: str = Field(default="", description="Path to test logs")


class ApplyPatchResult(BaseModel):
    """Result of patch application."""

    status: Literal["ok", "not_supported", "error"] = Field(..., description="Status")


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
