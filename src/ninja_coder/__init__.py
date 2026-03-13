"""Ninja Coder - Code execution module for Ninja MCP."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from ninja_coder.models import (
    ApplyPatchRequest,
    ApplyPatchResult,
    ExecutionMode,
    ParallelPlanRequest,
    PlanExecutionResult,
    RunTestsRequest,
    SequentialPlanRequest,
    SimpleTaskRequest,
    SimpleTaskResult,
    StepResult,
    TestResult,
)


__all__ = [
    "ApplyPatchRequest",
    "ApplyPatchResult",
    "ExecutionMode",
    "ParallelPlanRequest",
    "PlanExecutionResult",
    "RunTestsRequest",
    "SequentialPlanRequest",
    "SimpleTaskRequest",
    "SimpleTaskResult",
    "StepResult",
    "TestResult",
]
