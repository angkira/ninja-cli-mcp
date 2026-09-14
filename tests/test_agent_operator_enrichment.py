"""Secretary/agent run through their own operator (LLM), with heuristic fallback."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import pytest

from ninja_agent.models import AgentPlanRequest, AgentReviewRequest
from ninja_agent.tools import AgentToolExecutor


if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.asyncio
async def test_agent_plan_uses_operator_reasoning(tmp_path: Path) -> None:
    executor = AgentToolExecutor()
    with patch(
        "ninja_coder.driver.run_operator_text",
        new=AsyncMock(return_value=(True, "LLM-PLAN")),
    ):
        result = await executor.plan(
            AgentPlanRequest(task="Add a feature", repo_root=str(tmp_path))
        )
    assert result.reasoning == "LLM-PLAN"


@pytest.mark.asyncio
async def test_agent_plan_falls_back_to_heuristic(tmp_path: Path) -> None:
    executor = AgentToolExecutor()
    with patch(
        "ninja_coder.driver.run_operator_text",
        new=AsyncMock(return_value=(False, "")),
    ):
        result = await executor.plan(
            AgentPlanRequest(task="Add a feature", repo_root=str(tmp_path))
        )
    assert result.reasoning.startswith("Heuristic decomposition")


@pytest.mark.asyncio
async def test_agent_review_appends_operator_summary(tmp_path: Path) -> None:
    (tmp_path / "mod.py").write_text("def f():\n    return 1\n")
    executor = AgentToolExecutor()
    with patch(
        "ninja_coder.driver.run_operator_text",
        new=AsyncMock(return_value=(True, "LLM-REVIEW")),
    ):
        result = await executor.review(
            AgentReviewRequest(repo_root=str(tmp_path), file_paths=["mod.py"])
        )
    assert result.summary.endswith("LLM-REVIEW")
    assert result.success
