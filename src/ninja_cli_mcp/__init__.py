"""
ninja-cli-mcp: MCP stdio server delegating code work to AI coding assistants.

This package implements a Model Context Protocol (MCP) server that acts as
a coordinator between planning agents (like Claude Code or Copilot CLI) and
an AI code executor. The server never directly reads or writes user
project files - all code operations are delegated to the configured AI CLI.

Architecture:
    Planner (Claude/Copilot) -> MCP Coordinator (this) -> AI Code CLI -> Codebase
"""

__version__ = "0.1.0"
__author__ = "ninja-cli-mcp contributors"

from ninja_cli_mcp.models import (
    ApplyPatchRequest,
    ApplyPatchResult,
    ExecutionMode,
    ParallelPlanRequest,
    PlanExecutionResult,
    PlanStep,
    QuickTaskRequest,
    QuickTaskResult,
    RunTestsRequest,
    SequentialPlanRequest,
    StepResult,
    TestResult,
)


__all__ = [
    "__version__",
    "ExecutionMode",
    "PlanStep",
    "QuickTaskRequest",
    "SequentialPlanRequest",
    "ParallelPlanRequest",
    "RunTestsRequest",
    "ApplyPatchRequest",
    "StepResult",
    "PlanExecutionResult",
    "QuickTaskResult",
    "TestResult",
    "ApplyPatchResult",
]
