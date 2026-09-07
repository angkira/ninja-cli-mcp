"""
Pydantic models for Ninja Agent MCP tools.

The agent module is an orchestrator: it plans, analyzes, delegates, and
reviews — but never writes code itself. Code-writing is delegated to the
coder module. This module defines the API surface for the agent tools.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
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


class AgentPlanStep(BaseModel):
    """A single step in an execution plan."""

    title: str = Field(..., description="Short title of the step")
    description: str = Field(..., description="What this step accomplishes")
    delegate_to: Literal["coder", "researcher", "secretary", "self"] = Field(
        ..., description="Which sub-agent handles this step"
    )
    dependencies: list[int] = Field(
        default_factory=list, description="Indices of steps this step depends on"
    )


class AgentPlanRequest(BaseModel):
    """Request to decompose a task into an execution plan."""

    task: str = Field(..., description="High-level task description")
    repo_root: str = Field(..., description="Repository root path")
    context_paths: list[str] = Field(default_factory=list, description="Paths relevant to the task")
    steps_requested: int | None = Field(
        default=None, description="Optional hint for number of steps"
    )


class AgentPlanResult(BaseModel):
    """Result of plan decomposition."""

    success: bool = Field(..., description="Whether planning succeeded")
    plan: list[AgentPlanStep] = Field(default_factory=list, description="Ordered execution steps")
    reasoning: str = Field(default="", description="Explanation of the plan")


class AgentDelegateRequest(BaseModel):
    """Request to delegate a subtask to a specific sub-agent."""

    subtask: str = Field(..., description="Subtask description")
    repo_root: str = Field(..., description="Repository root path")
    delegate_to: Literal["coder", "researcher", "secretary"] = Field(
        ..., description="Sub-agent to invoke"
    )
    context_paths: list[str] = Field(
        default_factory=list, description="Paths relevant to the subtask"
    )
    model_class: Literal["smart", "balanced", "fast"] | None = Field(
        default=None, description="Model tier for the coder sub-agent (default: smart)"
    )


class AgentDelegateResult(BaseModel):
    """Result of a delegation call."""

    success: bool = Field(..., description="Whether the delegate succeeded")
    summary: str = Field(..., description="Concise summary from the sub-agent")
    delegate_to: str = Field(..., description="Sub-agent that was invoked")
    raw_output: str = Field(default="", description="Raw output from the sub-agent")


class AgentReviewFinding(BaseModel):
    """A single review finding."""

    severity: Literal["critical", "warning", "info"] = Field(
        ..., description="Severity of the finding"
    )
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
