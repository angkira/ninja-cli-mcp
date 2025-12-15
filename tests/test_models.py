"""Tests for Pydantic models."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from ninja_cli_mcp.models import (
    ApplyPatchRequest,
    ApplyPatchResult,
    ExecutionMode,
    MergeReport,
    ParallelPlanRequest,
    PlanExecutionResult,
    PlanStep,
    QuickTaskRequest,
    QuickTaskResult,
    RunTestsRequest,
    SequentialPlanRequest,
    StepConstraints,
    StepResult,
    TestPlan,
    TestResult,
)


class TestExecutionMode:
    """Tests for ExecutionMode enum."""

    def test_quick_mode(self) -> None:
        assert ExecutionMode.QUICK.value == "quick"

    def test_full_mode(self) -> None:
        assert ExecutionMode.FULL.value == "full"


class TestTestPlan:
    """Tests for TestPlan model."""

    def test_empty_test_plan(self) -> None:
        plan = TestPlan()
        assert plan.unit == []
        assert plan.e2e == []

    def test_test_plan_with_commands(self) -> None:
        plan = TestPlan(unit=["pytest tests/"], e2e=["npm run e2e"])
        assert plan.unit == ["pytest tests/"]
        assert plan.e2e == ["npm run e2e"]


class TestStepConstraints:
    """Tests for StepConstraints model."""

    def test_default_constraints(self) -> None:
        constraints = StepConstraints()
        assert constraints.max_tokens == 0
        assert constraints.time_budget_sec == 0

    def test_constraints_with_values(self) -> None:
        constraints = StepConstraints(max_tokens=4096, time_budget_sec=120)
        assert constraints.max_tokens == 4096
        assert constraints.time_budget_sec == 120

    def test_negative_values_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StepConstraints(max_tokens=-1)


class TestPlanStep:
    """Tests for PlanStep model."""

    def test_minimal_step(self) -> None:
        step = PlanStep(id="1", title="Test", task="Do something")
        assert step.id == "1"
        assert step.title == "Test"
        assert step.task == "Do something"
        assert step.context_paths == []
        assert step.max_iterations == 3

    def test_full_step(self) -> None:
        step = PlanStep(
            id="step-001",
            title="Add feature",
            task="Implement the feature",
            context_paths=["src/"],
            allowed_globs=["**/*.py"],
            deny_globs=["**/*.pyc"],
            max_iterations=5,
            test_plan=TestPlan(unit=["pytest"]),
            constraints=StepConstraints(time_budget_sec=300),
        )
        assert step.id == "step-001"
        assert step.max_iterations == 5
        assert step.test_plan.unit == ["pytest"]
        assert step.constraints.time_budget_sec == 300

    def test_max_iterations_bounds(self) -> None:
        with pytest.raises(ValidationError):
            PlanStep(id="1", title="Test", task="Task", max_iterations=0)

        with pytest.raises(ValidationError):
            PlanStep(id="1", title="Test", task="Task", max_iterations=11)


class TestQuickTaskRequest:
    """Tests for QuickTaskRequest model."""

    def test_minimal_request(self) -> None:
        req = QuickTaskRequest(task="Add function", repo_root="/tmp/repo")
        assert req.task == "Add function"
        assert req.repo_root == "/tmp/repo"
        assert req.mode == "quick"
        assert req.context_paths == []

    def test_full_request(self) -> None:
        req = QuickTaskRequest(
            task="Refactor code",
            repo_root="/home/user/project",
            context_paths=["src/main.py"],
            allowed_globs=["src/**"],
            deny_globs=["**/*.bak"],
        )
        assert req.context_paths == ["src/main.py"]
        assert req.allowed_globs == ["src/**"]

    def test_missing_required_fields(self) -> None:
        with pytest.raises(ValidationError):
            QuickTaskRequest(task="Test")  # type: ignore

        with pytest.raises(ValidationError):
            QuickTaskRequest(repo_root="/tmp")  # type: ignore


class TestSequentialPlanRequest:
    """Tests for SequentialPlanRequest model."""

    def test_minimal_request(self) -> None:
        steps = [PlanStep(id="1", title="Step 1", task="Do step 1")]
        req = SequentialPlanRequest(repo_root="/tmp/repo", steps=steps)
        assert req.mode == ExecutionMode.QUICK
        assert len(req.steps) == 1

    def test_full_mode_request(self) -> None:
        steps = [PlanStep(id="1", title="Step 1", task="Do step 1")]
        req = SequentialPlanRequest(
            repo_root="/tmp/repo",
            mode=ExecutionMode.FULL,
            global_allowed_globs=["**/*.py"],
            global_deny_globs=["**/venv/**"],
            steps=steps,
        )
        assert req.mode == ExecutionMode.FULL
        assert req.global_allowed_globs == ["**/*.py"]


class TestParallelPlanRequest:
    """Tests for ParallelPlanRequest model."""

    def test_default_fanout(self) -> None:
        steps = [PlanStep(id="1", title="Step 1", task="Do step 1")]
        req = ParallelPlanRequest(repo_root="/tmp/repo", steps=steps)
        assert req.fanout == 4

    def test_custom_fanout(self) -> None:
        steps = [PlanStep(id="1", title="Step 1", task="Do step 1")]
        req = ParallelPlanRequest(repo_root="/tmp/repo", fanout=8, steps=steps)
        assert req.fanout == 8

    def test_fanout_bounds(self) -> None:
        steps = [PlanStep(id="1", title="Step 1", task="Do step 1")]

        with pytest.raises(ValidationError):
            ParallelPlanRequest(repo_root="/tmp", fanout=0, steps=steps)

        with pytest.raises(ValidationError):
            ParallelPlanRequest(repo_root="/tmp", fanout=17, steps=steps)


class TestRunTestsRequest:
    """Tests for RunTestsRequest model."""

    def test_minimal_request(self) -> None:
        req = RunTestsRequest(repo_root="/tmp/repo", commands=["pytest"])
        assert req.timeout_sec == 600
        assert req.commands == ["pytest"]

    def test_custom_timeout(self) -> None:
        req = RunTestsRequest(
            repo_root="/tmp/repo",
            commands=["pytest", "npm test"],
            timeout_sec=1200,
        )
        assert req.timeout_sec == 1200

    def test_timeout_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RunTestsRequest(repo_root="/tmp", commands=["pytest"], timeout_sec=5)

        with pytest.raises(ValidationError):
            RunTestsRequest(repo_root="/tmp", commands=["pytest"], timeout_sec=4000)


class TestResultModels:
    """Tests for result models."""

    def test_quick_task_result(self) -> None:
        result = QuickTaskResult(
            status="ok",
            summary="Task completed successfully",
            notes="Created 2 files",
            logs_ref="/tmp/logs/task.log",
            suspected_touched_paths=["src/main.py", "src/utils.py"],
        )
        assert result.status == "ok"
        assert len(result.suspected_touched_paths) == 2

    def test_step_result(self) -> None:
        result = StepResult(
            id="step-001",
            status="ok",
            summary="Step completed",
        )
        assert result.id == "step-001"
        assert result.notes == ""

    def test_plan_execution_result(self) -> None:
        results = [
            StepResult(id="1", status="ok", summary="Done"),
            StepResult(id="2", status="fail", summary="Failed"),
        ]
        result = PlanExecutionResult(
            status="partial",
            results=results,
            overall_summary="1 of 2 steps completed",
        )
        assert result.status == "partial"
        assert len(result.results) == 2
        assert result.merge_report is None

    def test_plan_execution_result_with_merge_report(self) -> None:
        result = PlanExecutionResult(
            status="ok",
            results=[],
            overall_summary="Done",
            merge_report=MergeReport(strategy="scope_isolation", notes="OK"),
        )
        assert result.merge_report is not None
        assert result.merge_report.strategy == "scope_isolation"

    def test_test_result(self) -> None:
        result = TestResult(status="fail", summary="3 tests failed")
        assert result.status == "fail"
        assert result.logs_ref == ""

    def test_apply_patch_result(self) -> None:
        result = ApplyPatchResult(
            status="not_supported",
            message="Use AI code CLI directly",
        )
        assert result.status == "not_supported"
