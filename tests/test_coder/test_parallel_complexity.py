"""Complexity routing for coder_execute_plan_parallel.

simple -> task_type=quick (in-place, no worktree);
complex (default) -> task_type=parallel_plan (isolated worktree).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pytest
from pydantic import ValidationError

from ninja_coder.driver import NinjaResult
from ninja_coder.models import ParallelPlanRequest, PlanStep
from ninja_coder.tools import ToolExecutor


if TYPE_CHECKING:
    from pathlib import Path


def _ok_result() -> NinjaResult:
    payload = {
        "overall_status": "success",
        "steps_completed": ["t1"],
        "steps_failed": [],
        "step_summaries": {"t1": "Done"},
        "files_modified": [],
        "notes": "",
    }
    return NinjaResult(
        success=True,
        stdout=f"```json\n{json.dumps(payload)}\n```",
        stderr="",
        exit_code=0,
        summary="Success",
        notes="",
        suspected_touched_paths=[],
        model_used="test-model",
    )


def _executor() -> tuple[ToolExecutor, Mock]:
    driver = Mock()
    driver.config = Mock(model="test-model")
    driver.execute_async = AsyncMock(return_value=_ok_result())
    return ToolExecutor(driver=driver), driver


def _steps() -> list[PlanStep]:
    return [PlanStep(id="t1", title="T1", task="Fix typo in one line")]


@pytest.mark.asyncio
async def test_simple_routes_to_quick(tmp_path: Path) -> None:
    executor, driver = _executor()
    request = ParallelPlanRequest(
        repo_root=str(tmp_path), complexity="simple", steps=_steps()
    )
    await executor.execute_plan_parallel(request)
    assert driver.execute_async.call_args.kwargs["task_type"] == "quick"


@pytest.mark.asyncio
async def test_complex_routes_to_parallel_plan(tmp_path: Path) -> None:
    executor, driver = _executor()
    request = ParallelPlanRequest(
        repo_root=str(tmp_path), complexity="complex", steps=_steps()
    )
    await executor.execute_plan_parallel(request)
    assert driver.execute_async.call_args.kwargs["task_type"] == "parallel_plan"


@pytest.mark.asyncio
async def test_default_is_complex(tmp_path: Path) -> None:
    executor, driver = _executor()
    request = ParallelPlanRequest(repo_root=str(tmp_path), steps=_steps())
    assert request.complexity == "complex"
    await executor.execute_plan_parallel(request)
    assert driver.execute_async.call_args.kwargs["task_type"] == "parallel_plan"


def test_invalid_complexity_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ParallelPlanRequest(
            repo_root=str(tmp_path), complexity="medium", steps=_steps()  # type: ignore[arg-type]
        )


def test_simple_timeout_shorter_than_complex(tmp_path: Path) -> None:
    executor, _ = _executor()
    steps = [
        PlanStep(id=f"t{i}", title=f"T{i}", task="x") for i in range(4)
    ]
    simple = ParallelPlanRequest(
        repo_root=str(tmp_path), complexity="simple", steps=steps
    )
    complex_ = ParallelPlanRequest(
        repo_root=str(tmp_path), complexity="complex", steps=steps
    )
    assert executor._estimate_parallel_timeout(simple) < executor._estimate_parallel_timeout(
        complex_
    )
