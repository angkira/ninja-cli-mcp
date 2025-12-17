"""Tests for MCP tool implementations."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from ninja_cli_mcp.models import (
    ApplyPatchRequest,
    ExecutionMode,
    ParallelPlanRequest,
    PlanStep,
    QuickTaskRequest,
    RunTestsRequest,
    SequentialPlanRequest,
)
from ninja_cli_mcp.ninja_driver import NinjaDriver, NinjaResult
from ninja_cli_mcp.tools import ToolExecutor, get_executor, reset_executor


@pytest.fixture
def mock_driver() -> MagicMock:
    """Create a mock NinjaDriver."""
    from ninja_cli_mcp.ninja_driver import NinjaConfig

    driver = MagicMock(spec=NinjaDriver)
    driver.execute_async = AsyncMock()
    # Add config attribute for metrics recording
    driver.config = NinjaConfig(
        bin_path="mock-cli",
        model="mock-model"
    )
    return driver


@pytest.fixture
def executor(mock_driver: MagicMock) -> ToolExecutor:
    """Create a ToolExecutor with a mock driver."""
    return ToolExecutor(driver=mock_driver)


class TestToolExecutorInit:
    """Tests for ToolExecutor initialization."""

    def test_default_driver(self, mock_env: dict[str, str]) -> None:
        reset_executor()
        executor = ToolExecutor()
        assert executor.driver is not None

    def test_custom_driver(self, mock_driver: MagicMock) -> None:
        executor = ToolExecutor(driver=mock_driver)
        assert executor.driver is mock_driver


class TestGetExecutor:
    """Tests for get_executor singleton."""

    def test_returns_same_instance(self, mock_env: dict[str, str]) -> None:
        reset_executor()
        executor1 = get_executor()
        executor2 = get_executor()
        assert executor1 is executor2

    def test_reset_creates_new_instance(self, mock_env: dict[str, str]) -> None:
        reset_executor()
        executor1 = get_executor()
        reset_executor()
        executor2 = get_executor()
        assert executor1 is not executor2


class TestQuickTask:
    """Tests for ninja_quick_task tool."""

    @pytest.mark.asyncio
    async def test_successful_execution(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=True,
            summary="Task completed",
            notes="Added 2 files",
            suspected_touched_paths=["src/new.py"],
            raw_logs_path="/tmp/logs/task.log",
            model_used="anthropic/claude-sonnet-4",
        )

        request = QuickTaskRequest(
            task="Add hello function",
            repo_root=str(temp_repo),
            # Don't use context_paths to avoid validation complexity in test
        )

        result = await executor.quick_task(request)

        assert result.status == "ok"
        assert result.summary == "Task completed"
        assert "src/new.py" in result.suspected_touched_paths
        mock_driver.execute_async.assert_called_once()

    @pytest.mark.asyncio
    async def test_failed_execution(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=False,
            summary="Task failed",
            notes="Syntax error",
        )

        request = QuickTaskRequest(
            task="Do something",
            repo_root=str(temp_repo),
        )

        result = await executor.quick_task(request)

        assert result.status == "error"
        assert result.summary == "Task failed"

    @pytest.mark.asyncio
    async def test_invalid_repo_root(self, executor: ToolExecutor) -> None:
        request = QuickTaskRequest(
            task="Do something",
            repo_root="/nonexistent/path/12345",
        )

        result = await executor.quick_task(request)

        assert result.status == "error"
        assert "does not exist" in result.summary


class TestExecutePlanSequential:
    """Tests for execute_plan_sequential tool."""

    @pytest.mark.asyncio
    async def test_all_steps_succeed(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=True,
            summary="Step completed",
        )

        steps = [
            PlanStep(id="1", title="Step 1", task="Task 1"),
            PlanStep(id="2", title="Step 2", task="Task 2"),
        ]

        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        result = await executor.execute_plan_sequential(request)

        assert result.status == "ok"
        assert len(result.results) == 2
        assert all(r.status == "ok" for r in result.results)
        assert mock_driver.execute_async.call_count == 2

    @pytest.mark.asyncio
    async def test_partial_success(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        # First call succeeds, second fails
        mock_driver.execute_async.side_effect = [
            NinjaResult(success=True, summary="OK"),
            NinjaResult(success=False, summary="Failed"),
        ]

        steps = [
            PlanStep(id="1", title="Step 1", task="Task 1"),
            PlanStep(id="2", title="Step 2", task="Task 2"),
        ]

        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        result = await executor.execute_plan_sequential(request)

        assert result.status == "partial"
        assert result.results[0].status == "ok"
        assert result.results[1].status == "fail"

    @pytest.mark.asyncio
    async def test_all_steps_fail(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=False,
            summary="Failed",
        )

        steps = [PlanStep(id="1", title="Step 1", task="Task 1")]

        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        result = await executor.execute_plan_sequential(request)

        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_respects_time_budget(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(success=True, summary="OK")

        from ninja_cli_mcp.models import StepConstraints

        steps = [
            PlanStep(
                id="1",
                title="Step 1",
                task="Task 1",
                constraints=StepConstraints(time_budget_sec=120),
            ),
        ]

        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        await executor.execute_plan_sequential(request)

        # Check that timeout was passed
        call_kwargs = mock_driver.execute_async.call_args.kwargs
        assert call_kwargs["timeout_sec"] == 120


class TestExecutePlanParallel:
    """Tests for execute_plan_parallel tool."""

    @pytest.mark.asyncio
    async def test_parallel_execution(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=True,
            summary="Step completed",
        )

        steps = [
            PlanStep(id="1", title="Step 1", task="Task 1"),
            PlanStep(id="2", title="Step 2", task="Task 2"),
            PlanStep(id="3", title="Step 3", task="Task 3"),
        ]

        request = ParallelPlanRequest(
            repo_root=str(temp_repo),
            fanout=2,
            steps=steps,
        )

        result = await executor.execute_plan_parallel(request)

        assert result.status == "ok"
        assert len(result.results) == 3
        assert mock_driver.execute_async.call_count == 3

    @pytest.mark.asyncio
    async def test_includes_merge_report(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(success=True, summary="OK")

        steps = [PlanStep(id="1", title="Step 1", task="Task 1")]

        request = ParallelPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        result = await executor.execute_plan_parallel(request)

        assert result.merge_report is not None
        assert result.merge_report.strategy == "scope_isolation"

    @pytest.mark.asyncio
    async def test_handles_mixed_results(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.side_effect = [
            NinjaResult(success=True, summary="OK"),
            NinjaResult(success=False, summary="Failed"),
        ]

        steps = [
            PlanStep(id="1", title="Step 1", task="Task 1"),
            PlanStep(id="2", title="Step 2", task="Task 2"),
        ]

        request = ParallelPlanRequest(
            repo_root=str(temp_repo),
            steps=steps,
        )

        result = await executor.execute_plan_parallel(request)

        assert result.status == "partial"


class TestRunTests:
    """Tests for run_tests tool."""

    @pytest.mark.asyncio
    async def test_successful_tests(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=True,
            summary="All tests passed",
            raw_logs_path="/tmp/test.log",
        )

        request = RunTestsRequest(
            repo_root=str(temp_repo),
            commands=["pytest tests/"],
        )

        result = await executor.run_tests(request)

        assert result.status == "ok"
        assert result.summary == "All tests passed"

    @pytest.mark.asyncio
    async def test_failed_tests(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=False,
            summary="3 tests failed",
            exit_code=1,
        )

        request = RunTestsRequest(
            repo_root=str(temp_repo),
            commands=["pytest tests/"],
        )

        result = await executor.run_tests(request)

        assert result.status == "fail"

    @pytest.mark.asyncio
    async def test_error_status(
        self,
        executor: ToolExecutor,
        mock_driver: MagicMock,
        temp_repo: Path,
    ) -> None:
        mock_driver.execute_async.return_value = NinjaResult(
            success=False,
            summary="Error",
            exit_code=-1,
        )

        request = RunTestsRequest(
            repo_root=str(temp_repo),
            commands=["pytest"],
        )

        result = await executor.run_tests(request)

        assert result.status == "error"


class TestApplyPatch:
    """Tests for apply_patch tool."""

    @pytest.mark.asyncio
    async def test_returns_not_supported(self, executor: ToolExecutor) -> None:
        request = ApplyPatchRequest(
            repo_root="/tmp/repo",
            patch_content="diff content",
        )

        result = await executor.apply_patch(request)

        assert result.status == "not_supported"
        assert "AI code CLI" in result.message
