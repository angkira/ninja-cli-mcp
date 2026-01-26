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
    status: Literal["ok", "fail", "error"] = Field(..., description="Execution status")
    summary: str = Field(..., description="Brief summary of what was done")
    notes: str = Field(default="", description="Additional notes or warnings")
    logs_ref: str = Field(default="", description="Path to detailed logs")
    suspected_touched_paths: list[str] = Field(
        default_factory=list,
        description="Paths that were likely modified (best-effort)",
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

    status: Literal["ok", "partial", "error"] = Field(..., description="Overall status")
    results: list[StepResult] = Field(..., description="Per-step results")
    overall_summary: str = Field(..., description="Summary of entire execution")
    merge_report: MergeReport | None = Field(
        default=None,
        description="Merge report (for parallel execution)",
    )


class TestResult(BaseModel):
    """Result of test execution."""

    status: Literal["ok", "fail", "error"] = Field(..., description="Test status")
    summary: str = Field(..., description="Test summary")
    logs_ref: str = Field(default="", description="Path to test logs")


class ApplyPatchResult(BaseModel):
    """Result of patch application."""

    status: Literal["ok", "not_supported", "error"] = Field(..., description="Status")


# Session Management Models


class CreateSessionRequest(BaseModel):
    """Request to create a new conversation session."""

    repo_root: str = Field(..., description="Absolute path to repository root")
    initial_task: str = Field(..., description="Initial task to execute")
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


class ContinueSessionRequest(BaseModel):
    """Request to continue an existing session."""

    session_id: str = Field(..., description="Session ID to continue")
    task: str = Field(..., description="New task to execute")
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


class ListSessionsRequest(BaseModel):
    """Request to list sessions."""

    repo_root: str = Field(default="", description="Optional repository filter")


class DeleteSessionRequest(BaseModel):
    """Request to delete a session."""

    session_id: str = Field(..., description="Session ID to delete")


class SessionSummary(BaseModel):
    """Summary of a conversation session."""

    session_id: str = Field(..., description="Session identifier")
    repo_root: str = Field(..., description="Repository root path")
    model: str = Field(..., description="Model used in session")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    updated_at: str = Field(..., description="Last update timestamp (ISO format)")
    message_count: int = Field(..., description="Total message count")
    user_message_count: int = Field(..., description="User message count")
    assistant_message_count: int = Field(..., description="Assistant message count")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Session metadata",
    )


class CreateSessionResult(BaseModel):
    """Result of session creation."""

    status: Literal["ok", "error"] = Field(..., description="Creation status")
    session_id: str | None = Field(None, description="Created session ID")
    summary: str = Field(..., description="Task execution summary")
    notes: str = Field(default="", description="Additional notes")
    suspected_touched_paths: list[str] = Field(
        default_factory=list,
        description="Files modified in initial task",
    )


class ContinueSessionResult(BaseModel):
    """Result of session continuation."""

    status: Literal["ok", "error"] = Field(..., description="Continuation status")
    session_id: str = Field(..., description="Session ID")
    summary: str = Field(..., description="Task execution summary")
    notes: str = Field(default="", description="Additional notes")
    suspected_touched_paths: list[str] = Field(
        default_factory=list,
        description="Files modified in this task",
    )


class ListSessionsResult(BaseModel):
    """Result of listing sessions."""

    status: Literal["ok", "error"] = Field(..., description="List status")
    sessions: list[SessionSummary] = Field(
        default_factory=list,
        description="List of session summaries",
    )
    count: int = Field(..., description="Total session count")


class DeleteSessionResult(BaseModel):
    """Result of session deletion."""

    status: Literal["ok", "error", "not_found"] = Field(..., description="Delete status")
    message: str = Field(..., description="Result message")


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
    session_id: str | None = Field(
        None,
        description="Optional session ID to continue (for persistent context)",
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
