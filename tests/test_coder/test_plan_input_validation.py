"""Plan-step input tolerance and model-readable validation errors.

Regression guard for the incident where a caller sent a step containing only
``context_paths`` (no ``id``/``title``/``task``) and got the opaque
``Input validation error: 'id' is a required property`` from schema-level
client validation instead of a clear, actionable message.

Contract:
    - ``id`` and ``title`` are optional and auto-derived.
    - ``task`` is required; a missing/blank one yields an indexed error.
    - the tool's declared JSON schema must not require ``id``/``title``.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from ninja_coder.models import ParallelPlanRequest, PlanStep, SequentialPlanRequest


def _first_error(exc: ValidationError) -> str:
    """Return pydantic's human message with its 'Value error, ' wrapper stripped."""
    return str(exc.errors()[0]["msg"]).replace("Value error, ", "")


def test_step_requires_only_task() -> None:
    """id/title are optional; task alone is enough."""
    step = PlanStep(task="Add an is_even helper to utils.py")
    assert step.id  # auto-generated
    assert step.title == "Add an is_even helper to utils.py"


def test_sequential_autofills_missing_id_and_title() -> None:
    steps: Any = [{"task": "write a"}, {"id": "b", "task": "write b"}]
    request = SequentialPlanRequest(repo_root="/tmp", steps=steps)
    assert [s.id for s in request.steps] == ["step_1", "b"]
    assert request.steps[0].title == "write a"
    assert request.steps[1].title == "write b"


def test_parallel_autofills_missing_id_and_title() -> None:
    steps: Any = [{"task": "a"}, {"id": "keep", "title": "Keep", "task": "b"}]
    request = ParallelPlanRequest(repo_root="/tmp", steps=steps)
    assert [s.id for s in request.steps] == ["step_1", "keep"]
    assert request.steps[1].title == "Keep"


def test_task_only_step_is_accepted() -> None:
    """The exact incident shape with a well-formed first step must pass."""
    steps: Any = [
        {"task": "Create the phase-2 training configs"},
        {"id": "verify", "task": "Verify the configs parse"},
    ]
    request = SequentialPlanRequest(
        repo_root="/home/angkira/Project/software/cortex",
        mode="full",  # type: ignore[arg-type]
        steps=steps,
    )
    assert len(request.steps) == 2


def test_missing_task_error_names_the_step_index() -> None:
    steps: Any = [
        {"context_paths": ["training/"]},
        {"id": "d4", "title": "D4", "task": "do work"},
    ]
    with pytest.raises(ValidationError) as exc_info:
        SequentialPlanRequest(repo_root="/tmp", steps=steps)
    message = _first_error(exc_info.value)
    assert "steps[0]" in message
    assert "task" in message
    assert "context_paths" in message  # echo received fields


def test_malformed_steps_errors_are_clear() -> None:
    """Non-array steps, non-object steps, and blank tasks all error clearly."""
    for payload in ("nope", 42, [42], [{"task": "  "}]):
        with pytest.raises(ValidationError) as exc_info:
            SequentialPlanRequest(repo_root="/tmp", steps=payload)  # type: ignore[arg-type]
        message = _first_error(exc_info.value)
        assert "steps" in message


def test_empty_steps_is_accepted_as_noop() -> None:
    """Backward compatibility: an empty plan is a valid no-op."""
    request = SequentialPlanRequest(repo_root="/tmp", steps=[])
    assert request.steps == []


def test_declared_tool_schema_does_not_require_id_or_title() -> None:
    """The MCP inputSchema must match the model: only task is required."""
    from ninja_coder.server import TOOLS

    for tool_name in (
        "coder_execute_plan_sequential",
        "coder_execute_plan_parallel",
    ):
        tool = next(t for t in TOOLS if t.name == tool_name)
        step_items = tool.inputSchema["properties"]["steps"]["items"]
        assert step_items.get("required", []) == [], tool_name
        assert "id" in step_items["properties"], tool_name
        assert "title" in step_items["properties"], tool_name
        assert "task" in step_items["properties"], tool_name
