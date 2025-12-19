"""
MCP tool implementations.

This module contains the business logic for all MCP tools exposed by the server.
Tools are implemented as async functions that delegate execution to the AI code CLI.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from ninja_cli_mcp.logging_utils import get_logger
from ninja_cli_mcp.metrics import MetricsTracker, create_task_metrics
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
    StepResult,
    TestResult,
)
from ninja_cli_mcp.ninja_driver import InstructionBuilder, NinjaDriver, NinjaResult
from ninja_cli_mcp.path_utils import validate_repo_root
from ninja_cli_mcp.security import InputValidator, monitored, rate_limited


logger = get_logger(__name__)


class ToolExecutor:
    """
    Executor for MCP tools.

    This class provides the implementation for all tools exposed by the MCP server.
    All code execution is delegated to the AI code CLI.
    """

    def __init__(self, driver: NinjaDriver | None = None):
        """
        Initialize the tool executor.

        Args:
            driver: NinjaDriver instance. If None, creates one from env.
        """
        self.driver = driver or NinjaDriver()

    def _result_to_step_result(self, step_id: str, result: NinjaResult) -> StepResult:
        """Convert NinjaResult to StepResult."""
        status: str = "ok" if result.success else "fail"
        if result.exit_code == -1:  # Special case for errors
            status = "error"

        return StepResult(
            id=step_id,
            status=status,  # type: ignore
            summary=result.summary,
            notes=result.notes,
            logs_ref=result.raw_logs_path,
            suspected_touched_paths=result.suspected_touched_paths,
        )

    @rate_limited(max_calls=50, time_window=60, client_id="default")
    @monitored
    async def quick_task(self, request: QuickTaskRequest, client_id: str = "default") -> QuickTaskResult:
        """
        Execute a quick single-pass task.

        This tool runs the AI code CLI in quick mode for fast execution.
        The CLI has full responsibility for reading/writing files.

        Args:
            request: Quick task request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Quick task result with summary and metadata.

        Raises:
            PermissionError: If rate limit is exceeded.
            ValueError: If inputs are invalid.
        """
        logger.info(f"Executing quick task in {request.repo_root} for client {client_id}")

        # Generate task ID and start timer
        task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate and sanitize inputs
        try:
            # Validate repo root with security checks
            repo_path = InputValidator.validate_repo_root(request.repo_root)

            # Sanitize task description
            task = InputValidator.sanitize_string(request.task, max_length=50000)

            # Validate context paths
            if request.context_paths:
                for path in request.context_paths:
                    InputValidator.sanitize_path(path, base_dir=repo_path)

        except ValueError as e:
            # Record failed metrics
            duration = time.time() - start_time
            self._record_metrics(
                task_id=task_id,
                tool_name="ninja_quick_task",
                task_description=request.task[:200],  # Truncate for safety
                output="",
                duration_sec=duration,
                success=False,
                execution_mode="quick",
                repo_root=request.repo_root,
                error_message=f"Input validation failed: {str(e)}",
                client_id=client_id,
            )
            return QuickTaskResult(
                status="error",
                summary=f"Input validation failed: {str(e)}",
                notes="Invalid or potentially unsafe input detected",
            )
        except PermissionError as e:
            # Rate limit exceeded
            logger.warning(f"Rate limit exceeded for quick_task (client {client_id}): {e}")
            return QuickTaskResult(
                status="error",
                summary=str(e),
                notes="Too many requests - please slow down",
            )

        # Build instruction
        builder = InstructionBuilder(request.repo_root, ExecutionMode.QUICK)
        instruction = builder.build_quick_task(
            task=request.task,
            context_paths=request.context_paths,
            allowed_globs=request.allowed_globs,
            deny_globs=request.deny_globs,
        )

        # Execute via AI code CLI
        result = await self.driver.execute_async(
            repo_root=request.repo_root,
            step_id="quick_task",
            instruction=instruction,
        )

        # Record metrics
        duration = time.time() - start_time
        file_scope = ",".join(request.allowed_globs) if request.allowed_globs else None
        self._record_metrics(
            task_id=task_id,
            tool_name="ninja_quick_task",
            task_description=request.task,
            output=result.stdout,
            duration_sec=duration,
            success=result.success,
            execution_mode="quick",
            repo_root=request.repo_root,
            file_scope=file_scope,
            error_message=result.summary if not result.success else None,
            client_id=client_id,
        )

        return QuickTaskResult(
            status="ok" if result.success else "error",
            summary=result.summary,
            notes=result.notes,
            logs_ref=result.raw_logs_path,
            suspected_touched_paths=result.suspected_touched_paths,
        )

    def _record_metrics(
        self,
        task_id: str,
        tool_name: str,
        task_description: str,
        output: str,
        duration_sec: float,
        success: bool,
        execution_mode: str,
        repo_root: str,
        file_scope: str | None = None,
        error_message: str | None = None,
        client_id: str = "default",
    ) -> None:
        """Record metrics for a task execution."""
        try:
            tracker = MetricsTracker(Path(repo_root))
            metrics = create_task_metrics(
                task_id=task_id,
                model=self.driver.config.model,
                tool_name=tool_name,
                task_description=task_description,
                output=output,
                duration_sec=duration_sec,
                success=success,
                execution_mode=execution_mode,
                repo_root=repo_root,
                file_scope=file_scope,
                error_message=error_message,
            )
            # Add client_id to metrics
            metrics.client_id = client_id
            tracker.record_task(metrics)
        except Exception as e:
            logger.warning(f"Failed to record metrics for client {client_id}: {e}")

    async def execute_plan_sequential(
        self,
        request: SequentialPlanRequest,
        client_id: str = "default"
    ) -> PlanExecutionResult:
        """
        Execute plan steps sequentially.

        Each step is executed in order, with each step completing before
        the next begins. The AI code CLI handles all file operations.

        Args:
            request: Sequential plan request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Plan execution result with per-step results.
        """
        logger.info(f"Executing {len(request.steps)} steps sequentially in {request.repo_root} for client {client_id}")

        # Generate task ID and start timer
        plan_task_id = str(uuid.uuid4())
        plan_start_time = time.time()

        # Validate repo root
        try:
            validate_repo_root(request.repo_root)
        except ValueError as e:
            return PlanExecutionResult(
                status="error",
                results=[],
                overall_summary=str(e),
            )

        builder = InstructionBuilder(request.repo_root, request.mode)
        results: list[StepResult] = []
        all_success = True
        any_success = False

        for step in request.steps:
            logger.info(f"Executing step {step.id}: {step.title} for client {client_id}")

            # Track each step separately
            step_task_id = str(uuid.uuid4())
            step_start_time = time.time()

            # Build instruction for this step
            instruction = builder.build_plan_step(
                step=step,
                global_allowed_globs=request.global_allowed_globs,
                global_deny_globs=request.global_deny_globs,
            )

            # Determine timeout
            timeout = (
                step.constraints.time_budget_sec if step.constraints.time_budget_sec > 0 else None
            )

            # Execute via AI code CLI
            result = await self.driver.execute_async(
                repo_root=request.repo_root,
                step_id=step.id,
                instruction=instruction,
                timeout_sec=timeout,
            )

            step_result = self._result_to_step_result(step.id, result)
            results.append(step_result)

            # Record metrics for this step
            step_duration = time.time() - step_start_time
            file_scope = ",".join(step.allowed_globs) if step.allowed_globs else None
            self._record_metrics(
                task_id=step_task_id,
                tool_name="ninja_plan_step_sequential",
                task_description=f"{step.title}: {step.task}",
                output=result.stdout,
                duration_sec=step_duration,
                success=result.success,
                execution_mode=request.mode.value,
                repo_root=request.repo_root,
                file_scope=file_scope,
                error_message=result.summary if not result.success else None,
                client_id=client_id,
            )

            if result.success:
                any_success = True
            else:
                all_success = False
                logger.warning(f"Step {step.id} failed for client {client_id}: {result.summary}")

        # Determine overall status
        if all_success:
            status = "ok"
        elif any_success:
            status = "partial"
        else:
            status = "error"

        # Build overall summary
        ok_count = sum(1 for r in results if r.status == "ok")
        fail_count = sum(1 for r in results if r.status == "fail")
        error_count = sum(1 for r in results if r.status == "error")

        overall_summary = f"Completed {len(results)} steps: {ok_count} ok, {fail_count} failed, {error_count} errors"

        # Record overall plan metrics
        plan_duration = time.time() - plan_start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="ninja_execute_plan_sequential",
            task_description=f"Sequential plan with {len(request.steps)} steps",
            output=overall_summary,
            duration_sec=plan_duration,
            success=all_success,
            execution_mode=request.mode.value,
            repo_root=request.repo_root,
            error_message=overall_summary if not all_success else None,
            client_id=client_id,
        )

        return PlanExecutionResult(
            status=status,  # type: ignore
            results=results,
            overall_summary=overall_summary,
        )

    async def execute_plan_parallel(
        self,
        request: ParallelPlanRequest,
        client_id: str = "default"
    ) -> PlanExecutionResult:
        """
        Execute plan steps in parallel.

        Steps are executed concurrently up to the fanout limit. Each step
        runs in its own subprocess calling the AI code CLI.

        Note: For stronger isolation, consider using git worktrees for each
        parallel execution. This implementation runs against the same repo
        with instructions to respect scope.

        Args:
            request: Parallel plan request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Plan execution result with per-step results and merge report.
        """
        logger.info(
            f"Executing {len(request.steps)} steps in parallel "
            f"(fanout={request.fanout}) in {request.repo_root} for client {client_id}"
        )

        # Generate task ID and start timer
        plan_task_id = str(uuid.uuid4())
        plan_start_time = time.time()

        # Validate repo root
        try:
            validate_repo_root(request.repo_root)
        except ValueError as e:
            return PlanExecutionResult(
                status="error",
                results=[],
                overall_summary=str(e),
            )

        builder = InstructionBuilder(request.repo_root, request.mode)

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(request.fanout)

        async def execute_step(step: PlanStep) -> tuple[str, NinjaResult, float, str]:
            """Execute a single step with semaphore control."""
            step_task_id = str(uuid.uuid4())
            step_start_time = time.time()

            async with semaphore:
                logger.info(f"Starting parallel step {step.id}: {step.title} for client {client_id}")

                # Build instruction with parallel execution hint
                instruction = builder.build_plan_step(
                    step=step,
                    global_allowed_globs=request.global_allowed_globs,
                    global_deny_globs=request.global_deny_globs,
                )

                # Add parallel execution context
                instruction["parallel_context"] = {
                    "is_parallel": True,
                    "total_steps": len(request.steps),
                    "isolation_note": (
                        "This step is running in parallel with other steps. "
                        "Strictly respect the allowed_globs to avoid conflicts. "
                        "Only modify files within your designated scope."
                    ),
                }

                timeout = (
                    step.constraints.time_budget_sec
                    if step.constraints.time_budget_sec > 0
                    else None
                )

                result = await self.driver.execute_async(
                    repo_root=request.repo_root,
                    step_id=step.id,
                    instruction=instruction,
                    timeout_sec=timeout,
                )

                step_duration = time.time() - step_start_time
                return step.id, result, step_duration, step_task_id

        # Execute all steps in parallel
        tasks = [execute_step(step) for step in request.steps]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        results: list[StepResult] = []
        all_success = True
        any_success = False

        for idx, item in enumerate(completed):
            if isinstance(item, Exception):
                # Handle exceptions
                results.append(
                    StepResult(
                        id="unknown",
                        status="error",
                        summary=f"Exception: {item}",
                        notes=str(item),
                    )
                )
                all_success = False
            else:
                step_id, result, step_duration, step_task_id = item
                step_result = self._result_to_step_result(step_id, result)
                results.append(step_result)

                # Record metrics for this step
                step = request.steps[idx]
                file_scope = ",".join(step.allowed_globs) if step.allowed_globs else None
                self._record_metrics(
                    task_id=step_task_id,
                    tool_name="ninja_plan_step_parallel",
                    task_description=f"{step.title}: {step.task}",
                    output=result.stdout,
                    duration_sec=step_duration,
                    success=result.success,
                    execution_mode=request.mode.value,
                    repo_root=request.repo_root,
                    file_scope=file_scope,
                    error_message=result.summary if not result.success else None,
                    client_id=client_id,
                )

                if result.success:
                    any_success = True
                else:
                    all_success = False

        # Determine overall status
        if all_success:
            status = "ok"
        elif any_success:
            status = "partial"
        else:
            status = "error"

        # Build overall summary
        ok_count = sum(1 for r in results if r.status == "ok")
        fail_count = sum(1 for r in results if r.status == "fail")
        error_count = sum(1 for r in results if r.status == "error")

        overall_summary = (
            f"Completed {len(results)} parallel steps: "
            f"{ok_count} ok, {fail_count} failed, {error_count} errors"
        )

        # Create merge report
        merge_report = MergeReport(
            strategy="scope_isolation",
            notes=(
                "Steps executed in parallel against same repository. "
                "Each step was instructed to respect its allowed_globs scope. "
                "Manual review recommended if steps had overlapping scopes. "
                "For stronger isolation, consider using git worktrees."
            ),
        )

        # Record overall plan metrics
        plan_duration = time.time() - plan_start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="ninja_execute_plan_parallel",
            task_description=f"Parallel plan with {len(request.steps)} steps (fanout={request.fanout})",
            output=overall_summary,
            duration_sec=plan_duration,
            success=all_success,
            execution_mode=request.mode.value,
            repo_root=request.repo_root,
            error_message=overall_summary if not all_success else None,
            client_id=client_id,
        )

        return PlanExecutionResult(
            status=status,  # type: ignore
            results=results,
            overall_summary=overall_summary,
            merge_report=merge_report,
        )

    async def run_tests(self, request: RunTestsRequest, client_id: str = "default") -> TestResult:
        """
        Run test commands via the AI code CLI.

        This tool delegates test execution to the AI code CLI, which will
        run the specified commands and report results.

        Args:
            request: Run tests request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Test result with summary and logs reference.
        """
        logger.info(f"Running {len(request.commands)} test commands in {request.repo_root} for client {client_id}")

        # Generate task ID and start timer
        task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate repo root
        try:
            validate_repo_root(request.repo_root)
        except ValueError as e:
            # Record failed metrics
            duration = time.time() - start_time
            self._record_metrics(
                task_id=task_id,
                tool_name="ninja_run_tests",
                task_description=f"Run {len(request.commands)} test commands",
                output="",
                duration_sec=duration,
                success=False,
                execution_mode="test",
                repo_root=request.repo_root,
                error_message=str(e),
                client_id=client_id,
            )
            return TestResult(
                status="error",
                summary=str(e),
            )

        # Build instruction for test execution
        builder = InstructionBuilder(request.repo_root)
        instruction = builder.build_test_task(
            commands=request.commands,
            timeout_sec=request.timeout_sec,
        )

        # Execute via AI code CLI
        result = await self.driver.execute_async(
            repo_root=request.repo_root,
            step_id="run_tests",
            instruction=instruction,
            timeout_sec=request.timeout_sec,
        )

        # Determine status
        if result.success:
            status = "ok"
        elif result.exit_code == -1:
            status = "error"
        else:
            status = "fail"

        # Record metrics
        duration = time.time() - start_time
        self._record_metrics(
            task_id=task_id,
            tool_name="ninja_run_tests",
            task_description=f"Run {len(request.commands)} test commands: {', '.join(request.commands[:3])}{'...' if len(request.commands) > 3 else ''}",
            output=result.stdout,
            duration_sec=duration,
            success=result.success,
            execution_mode="test",
            repo_root=request.repo_root,
            error_message=result.summary if not result.success else None,
            client_id=client_id,
        )

        return TestResult(
            status=status,  # type: ignore
            summary=result.summary,
            logs_ref=result.raw_logs_path,
        )

    async def apply_patch(self, request: ApplyPatchRequest, client_id: str = "default") -> ApplyPatchResult:
        """
        Apply a patch (not supported - delegated to AI code CLI).

        In this architecture, code patches are created and applied by the AI code CLI,
        not by this server. This tool returns a not_supported status.

        If you need to apply patches, include them in the task description for
        ninja_quick_task or execute_plan_sequential/parallel.

        Args:
            request: Apply patch request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Apply patch result with not_supported status.
        """
        logger.info(f"apply_patch called for client {client_id} - this is a no-op shim")

        return ApplyPatchResult(
            status="not_supported",
            message=(
                "Patches are owned by the AI code CLI; this MCP server is plan- and "
                "status-oriented. To apply patches, include them in the task "
                "description for ninja_quick_task or plan execution tools."
            ),
        )


# Singleton executor instance
_executor: ToolExecutor | None = None


def get_executor() -> ToolExecutor:
    """Get the global tool executor instance."""
    global _executor
    if _executor is None:
        _executor = ToolExecutor()
    return _executor


def reset_executor() -> None:
    """Reset the global tool executor (for testing)."""
    global _executor
    _executor = None
