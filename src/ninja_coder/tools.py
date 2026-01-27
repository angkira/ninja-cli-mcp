"""
MCP tool implementations for the Coder module.

This module contains the business logic for all code-related MCP tools.
Tools are implemented as async functions that delegate execution to the AI code CLI.

IMPORTANT: Tools return ONLY concise summaries to the orchestrator, never source code.
"""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from datetime import datetime
from pathlib import Path

from ninja_coder.driver import InstructionBuilder, NinjaDriver, NinjaResult
from ninja_coder.models import (
    AgentInfo,
    ApplyPatchRequest,
    ApplyPatchResult,
    ContinueSessionRequest,
    ContinueSessionResult,
    CreateSessionRequest,
    CreateSessionResult,
    DeleteSessionRequest,
    DeleteSessionResult,
    ExecutionMode,
    GetAgentsRequest,
    GetAgentsResult,
    ListSessionsRequest,
    ListSessionsResult,
    MergeReport,
    MultiAgentTaskRequest,
    MultiAgentTaskResult,
    ParallelPlanRequest,
    PlanExecutionResult,
    PlanStep,
    QueryLogsRequest,
    QueryLogsResult,
    RunTestsRequest,
    SequentialPlanRequest,
    SimpleTaskRequest,
    SimpleTaskResult,
    StepResult,
    TestResult,
)
from ninja_common.logging_utils import get_logger
from ninja_common.metrics import MetricsTracker, create_task_metrics
from ninja_common.path_utils import validate_repo_root
from ninja_common.security import InputValidator, monitored, rate_limited


logger = get_logger(__name__)


class ToolExecutor:
    """
    Executor for MCP tools.

    This class provides the implementation for all tools exposed by the MCP server.
    All code execution is delegated to the AI code CLI.

    IMPORTANT: All responses are kept concise - only summaries, never source code.
    """

    def __init__(self, driver: NinjaDriver | None = None):
        """
        Initialize the tool executor.

        Args:
            driver: NinjaDriver instance. If None, creates one from env.
        """
        self.driver = driver or NinjaDriver()

    def _result_to_step_result(self, step_id: str, result: NinjaResult) -> StepResult:
        """
        Convert NinjaResult to StepResult.

        Returns ONLY concise summary information, no source code.
        """
        status: str = "ok" if result.success else "fail"
        if result.exit_code == -1:  # Special case for errors
            status = "error"

        # Ensure summary is concise (max 500 chars)
        summary = result.summary[:500] if len(result.summary) > 500 else result.summary

        # Ensure notes are concise (max 300 chars)
        notes = result.notes[:300] if len(result.notes) > 300 else result.notes

        return StepResult(
            id=step_id,
            status=status,  # type: ignore
            summary=summary,
            notes=notes,
            logs_ref=result.raw_logs_path,
            suspected_touched_paths=result.suspected_touched_paths[:10],  # Max 10 paths
        )

    @rate_limited(max_calls=50, time_window=60)
    @monitored
    async def simple_task(
        self, request: SimpleTaskRequest, client_id: str = "default"
    ) -> SimpleTaskResult:
        """
        Execute a simple single-pass CODE WRITING task.

        This tool runs the AI code CLI in quick mode for fast code writing.
        The CLI has full responsibility for reading/writing files.

        Returns ONLY a concise summary - NO source code is returned.

        Args:
            request: Simple task request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Simple task result with CONCISE summary and metadata (no source code).

        Raises:
            PermissionError: If rate limit is exceeded.
            ValueError: If inputs are invalid.
        """
        logger.info(f"Executing simple task in {request.repo_root} for client {client_id}")

        # Generate task ID and start timer
        task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate and sanitize inputs
        try:
            # Validate repo root with security checks
            repo_path = InputValidator.validate_repo_root(request.repo_root)

            # Sanitize task description
            InputValidator.sanitize_string(request.task, max_length=50000)

            # Validate context paths
            if request.context_paths:
                for path in request.context_paths:
                    InputValidator.sanitize_path(path, base_dir=repo_path)

        except ValueError as e:
            # Record failed metrics
            duration = time.time() - start_time
            self._record_metrics(
                task_id=task_id,
                tool_name="coder_simple_task",
                task_description=request.task[:200],  # Truncate for safety
                output="",
                duration_sec=duration,
                success=False,
                execution_mode="quick",
                repo_root=request.repo_root,
                error_message=f"Input validation failed: {e!s}",
                client_id=client_id,
            )
            return SimpleTaskResult(
                status="error",
                summary=f"❌ Input validation failed: {e!s}",
                notes="Invalid or potentially unsafe input detected",
            )
        except PermissionError as e:
            # Rate limit exceeded
            logger.warning(f"Rate limit exceeded for simple_task (client {client_id}): {e}")
            return SimpleTaskResult(
                status="error",
                summary=f"⚠️ Rate limit exceeded: {e!s}",
                notes="Too many requests - please slow down",
            )

        # Build instruction (reuse on retry)
        builder = InstructionBuilder(request.repo_root, ExecutionMode.QUICK)
        instruction = builder.build_quick_task(
            task=request.task,
            context_paths=request.context_paths,
            allowed_globs=request.allowed_globs,
            deny_globs=request.deny_globs,
        )

        # Retry configuration (configurable via environment variables)
        max_retries = int(os.environ.get("NINJA_MAX_RETRIES", "2"))
        retry_delay_sec = int(os.environ.get("NINJA_RETRY_DELAY_SEC", "5"))

        # Execute with retry logic for aider errors
        last_result = None
        attempt = 0
        for attempt in range(max_retries + 1):  # +1 for initial attempt
            if attempt > 0:
                logger.info(
                    f"Retrying task (attempt {attempt + 1}/{max_retries + 1}) after aider error for client {client_id}"
                )
                await asyncio.sleep(retry_delay_sec)

            # Execute via AI code CLI
            result = await self.driver.execute_async(
                repo_root=request.repo_root,
                step_id=f"simple_task_attempt_{attempt}",
                instruction=instruction,
                task_type="quick",  # Simple tasks are always quick
            )

            last_result = result

            # Success - no retry needed
            if result.success:
                if attempt > 0:
                    logger.info(f"Task succeeded on attempt {attempt + 1} for client {client_id}")
                break

            # Check if this is a retryable aider error
            if hasattr(result, "aider_error_detected") and result.aider_error_detected:
                logger.warning(
                    f"Aider error detected on attempt {attempt + 1} for client {client_id}: {result.notes[:100]}"
                )
                # Continue to retry (unless we're out of attempts)
                if attempt < max_retries:
                    continue
                else:
                    logger.error(
                        f"Max retries ({max_retries}) exceeded for aider errors for client {client_id}"
                    )
            else:
                # Non-retryable error (validation, API key, model not found, etc.)
                logger.error(f"Non-retryable error for client {client_id}: {result.summary[:100]}")
                break

        # Record metrics with retry info
        duration = time.time() - start_time
        file_scope = ",".join(request.allowed_globs) if request.allowed_globs else None

        # Add retry info to notes if we retried
        final_notes = last_result.notes
        if attempt > 0:
            retry_info = f" [Succeeded after {attempt} {'retry' if attempt == 1 else 'retries'}]"
            final_notes = (
                f"{final_notes}{retry_info}" if final_notes else f"Task completed{retry_info}"
            )

        self._record_metrics(
            task_id=task_id,
            tool_name="coder_simple_task",
            task_description=request.task,
            output=last_result.stdout,
            duration_sec=duration,
            success=last_result.success,
            execution_mode="quick",
            repo_root=request.repo_root,
            file_scope=file_scope,
            error_message=last_result.summary if not last_result.success else None,
            client_id=client_id,
        )

        # Return CONCISE result (no source code)
        return SimpleTaskResult(
            status="ok" if last_result.success else "error",
            summary=last_result.summary[:500],  # Ensure concise
            notes=final_notes[:300] if final_notes else "",  # Ensure concise
            logs_ref=last_result.raw_logs_path,
            suspected_touched_paths=last_result.suspected_touched_paths[:10],  # Max 10 paths
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
            tracker.record_task(metrics)
        except Exception as e:
            logger.warning(f"Failed to record metrics for client {client_id}: {e}")

    async def execute_plan_sequential(
        self, request: SequentialPlanRequest, client_id: str = "default"
    ) -> PlanExecutionResult:
        """
        Execute CODE WRITING plan steps sequentially.

        Each step is executed in order, with each step completing before
        the next begins. The AI code CLI handles all file operations.

        Returns ONLY concise summaries per step - NO source code.

        Args:
            request: Sequential plan request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Plan execution result with per-step CONCISE summaries (no source code).
        """
        logger.info(
            f"Executing {len(request.steps)} steps sequentially in {request.repo_root} for client {client_id}"
        )

        # Note: OpenCode strategy supports dialogue mode (supports_dialogue_mode=True)
        # for persistent multi-step conversations with context retention.
        # This can improve quality by maintaining AI context across steps.
        # Currently implemented in atomic mode (subprocess per step).
        # To enable: set NINJA_USE_DIALOGUE_MODE=true environment variable

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
                overall_summary=f"❌ {e!s}",
            )

        builder = InstructionBuilder(request.repo_root, request.mode)
        results: list[StepResult] = []
        all_success = True
        any_success = False

        # Note: OpenCode strategy supports dialogue mode for context retention
        # This can improve quality by maintaining AI context across sequential steps.
        # To enable: set NINJA_USE_DIALOGUE_MODE=true environment variable
        # Currently: atomic mode (subprocess per step) is used for all CLIs.

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

            # Retry configuration (same as simple_task)
            max_retries = int(os.environ.get("NINJA_MAX_RETRIES", "2"))
            retry_delay_sec = int(os.environ.get("NINJA_RETRY_DELAY_SEC", "5"))

            # Execute with retry logic for aider errors
            last_result = None
            retry_count = 0
            for retry_count in range(max_retries + 1):  # +1 for initial attempt
                if retry_count > 0:
                    logger.info(
                        f"Retrying step {step.id} (attempt {retry_count + 1}/{max_retries + 1}) "
                        f"after aider error for client {client_id}"
                    )
                    await asyncio.sleep(retry_delay_sec)

                # Execute via AI code CLI
                result = await self.driver.execute_async(
                    repo_root=request.repo_root,
                    step_id=f"{step.id}_attempt_{retry_count}",
                    instruction=instruction,
                    timeout_sec=timeout,
                    task_type="sequential",  # Plan steps are sequential
                )

                last_result = result

                # Success - no retry needed
                if result.success:
                    if retry_count > 0:
                        logger.info(
                            f"Step {step.id} succeeded on attempt {retry_count + 1} for client {client_id}"
                        )
                    break

                # Check if this is a retryable aider error
                if hasattr(result, "aider_error_detected") and result.aider_error_detected:
                    logger.warning(
                        f"Aider error detected in step {step.id} on attempt {retry_count + 1} "
                        f"for client {client_id}: {result.notes[:100]}"
                    )
                    # Continue to retry (unless we're out of attempts)
                    if retry_count < max_retries:
                        continue
                    else:
                        logger.error(
                            f"Max retries ({max_retries}) exceeded for step {step.id} for client {client_id}"
                        )
                else:
                    # Non-retryable error
                    logger.error(
                        f"Non-retryable error in step {step.id} for client {client_id}: {result.summary[:100]}"
                    )
                    break

            # Add retry info to step result if we retried
            step_result = self._result_to_step_result(step.id, last_result)
            if retry_count > 0 and last_result.success:
                retry_info = f" [After {retry_count} {'retry' if retry_count == 1 else 'retries'}]"
                step_result.notes = (
                    f"{step_result.notes}{retry_info}"
                    if step_result.notes
                    else f"Completed{retry_info}"
                )

            results.append(step_result)

            # Record metrics for this step
            step_duration = time.time() - step_start_time
            file_scope = ",".join(step.allowed_globs) if step.allowed_globs else None
            self._record_metrics(
                task_id=step_task_id,
                tool_name="coder_plan_step_sequential",
                task_description=f"{step.title}: {step.task}",
                output=last_result.stdout,
                duration_sec=step_duration,
                success=last_result.success,
                execution_mode=request.mode.value,
                repo_root=request.repo_root,
                file_scope=file_scope,
                error_message=last_result.summary if not last_result.success else None,
                client_id=client_id,
            )

            if last_result.success:
                any_success = True
            else:
                all_success = False
                logger.warning(
                    f"Step {step.id} failed for client {client_id}: {last_result.summary}"
                )

        # Determine overall status
        if all_success:
            status = "ok"
        elif any_success:
            status = "partial"
        else:
            status = "error"

        # Build CONCISE overall summary
        ok_count = sum(1 for r in results if r.status == "ok")
        fail_count = sum(1 for r in results if r.status == "fail")
        error_count = sum(1 for r in results if r.status == "error")

        overall_summary = (
            f"{'✅' if all_success else '⚠️' if any_success else '❌'} "
            f"Completed {len(results)} steps: "
            f"{ok_count} ok, {fail_count} failed, {error_count} errors"
        )

        # Record overall plan metrics
        plan_duration = time.time() - plan_start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="coder_execute_plan_sequential",
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
        self, request: ParallelPlanRequest, client_id: str = "default"
    ) -> PlanExecutionResult:
        """
        Execute CODE WRITING plan steps in parallel.

        Steps are executed concurrently up to the fanout limit. Each step
        runs in its own subprocess calling the AI code CLI.

        Returns ONLY concise summaries per step - NO source code.

        Note: For stronger isolation, consider using git worktrees for each
        parallel execution. This implementation runs against the same repo
        with instructions to respect scope.

        Args:
            request: Parallel plan request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Plan execution result with per-step CONCISE summaries and merge report.
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
                overall_summary=f"❌ {e!s}",
            )

        builder = InstructionBuilder(request.repo_root, request.mode)

        # Create semaphore to limit concurrency
        semaphore = asyncio.Semaphore(request.fanout)

        async def execute_step(step: PlanStep) -> tuple[str, NinjaResult, float, str]:
            """Execute a single step with semaphore control."""
            step_task_id = str(uuid.uuid4())
            step_start_time = time.time()

            async with semaphore:
                logger.info(
                    f"Starting parallel step {step.id}: {step.title} for client {client_id}"
                )

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
                    task_type="parallel",  # Parallel execution
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
                        summary=f"❌ Exception: {item!s}"[:200],
                        notes=str(item)[:200],
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
                    tool_name="coder_plan_step_parallel",
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

        # Build CONCISE overall summary
        ok_count = sum(1 for r in results if r.status == "ok")
        fail_count = sum(1 for r in results if r.status == "fail")
        error_count = sum(1 for r in results if r.status == "error")

        overall_summary = (
            f"{'✅' if all_success else '⚠️' if any_success else '❌'} "
            f"Completed {len(results)} parallel steps: "
            f"{ok_count} ok, {fail_count} failed, {error_count} errors"
        )

        # Create CONCISE merge report
        merge_report = MergeReport(
            strategy="scope_isolation",
            notes=(
                "Steps executed in parallel with scope isolation. "
                "Manual review recommended if steps had overlapping scopes."
            ),
        )

        # Record overall plan metrics
        plan_duration = time.time() - plan_start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="coder_execute_plan_parallel",
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
        ⚠️ DEPRECATED - Run test commands via the AI code CLI.

        This tool is deprecated because Ninja is for CODE WRITING ONLY.
        Use bash tool or execute commands yourself to run tests.

        Args:
            request: Run tests request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Test result indicating this tool is deprecated.
        """
        logger.warning(f"run_tests called for client {client_id} - this tool is deprecated")

        return TestResult(
            status="error",
            summary=(
                "⚠️ DEPRECATED: Ninja is for code writing only. "
                "Use bash tool to run tests: bash 'pytest tests/'"
            ),
        )

    async def apply_patch(
        self,
        request: ApplyPatchRequest,
        client_id: str = "default",
    ) -> ApplyPatchResult:
        """
        Apply a patch (not supported - delegated to AI code CLI).

        In this architecture, code patches are created and applied by the AI code CLI,
        not by this server. This tool returns a not_supported status.

        If you need to apply patches, include them in the task description for
        coder_simple_task or execute_plan_sequential/parallel.

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
                "⚠️ NOT SUPPORTED: Ninja writes code based on specifications, not patches. "
                "To apply changes, describe what code to write in coder_simple_task."
            ),
        )

    async def create_session(
        self,
        request: CreateSessionRequest,
        client_id: str = "default",
    ) -> CreateSessionResult:
        """Create a new conversation session and execute the initial task.

        Args:
            request: Create session request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Create session result with session_id.
        """
        logger.info(f"[{client_id}] Creating session for {request.repo_root}")

        step_id = f"session_create_{int(datetime.utcnow().timestamp())}"

        try:
            # Execute with session using the driver's execute_with_session method
            result = await self.driver.execute_with_session(
                task=request.initial_task,
                repo_root=request.repo_root,
                step_id=step_id,
                create_session=True,
                context_paths=request.context_paths,
                allowed_globs=request.allowed_globs,
                deny_globs=request.deny_globs,
            )

            if result.success:
                return CreateSessionResult(
                    status="ok",
                    session_id=result.session_id,
                    summary=result.summary,
                    notes=result.notes,
                    suspected_touched_paths=result.suspected_touched_paths,
                )
            else:
                return CreateSessionResult(
                    status="error",
                    session_id=result.session_id,
                    summary=result.summary,
                    notes=result.notes,
                    suspected_touched_paths=result.suspected_touched_paths,
                )

        except Exception as e:
            logger.error(f"[{client_id}] Session creation failed: {e}", exc_info=True)
            return CreateSessionResult(
                status="error",
                summary=f"❌ Failed to create session: {str(e)[:100]}",
                notes=str(e),
            )

    async def continue_session(
        self,
        request: ContinueSessionRequest,
        client_id: str = "default",
    ) -> ContinueSessionResult:
        """Continue an existing session with a new task.

        Args:
            request: Continue session request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Continue session result.
        """
        logger.info(f"[{client_id}] Continuing session {request.session_id}")

        step_id = f"session_continue_{int(datetime.utcnow().timestamp())}"

        try:
            # Execute with existing session
            result = await self.driver.execute_with_session(
                task=request.task,
                repo_root=request.repo_root,
                step_id=step_id,
                session_id=request.session_id,
                context_paths=request.context_paths,
                allowed_globs=request.allowed_globs,
                deny_globs=request.deny_globs,
            )

            if result.success:
                return ContinueSessionResult(
                    status="ok",
                    session_id=request.session_id,
                    summary=result.summary,
                    notes=result.notes,
                    suspected_touched_paths=result.suspected_touched_paths,
                )
            else:
                return ContinueSessionResult(
                    status="error",
                    session_id=request.session_id,
                    summary=result.summary,
                    notes=result.notes,
                    suspected_touched_paths=result.suspected_touched_paths,
                )

        except Exception as e:
            logger.error(f"[{client_id}] Session continuation failed: {e}", exc_info=True)
            return ContinueSessionResult(
                status="error",
                session_id=request.session_id,
                summary=f"❌ Failed to continue session: {str(e)[:100]}",
                notes=str(e),
            )

    async def list_sessions(
        self,
        request: ListSessionsRequest,
        client_id: str = "default",
    ) -> ListSessionsResult:
        """List all conversation sessions, optionally filtered by repository.

        Args:
            request: List sessions request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            List sessions result with session summaries.
        """
        logger.info(f"[{client_id}] Listing sessions for {request.repo_root or 'all repos'}")

        try:
            # Get sessions from driver's session manager
            repo_filter = request.repo_root if request.repo_root else None
            sessions = self.driver.session_manager.list_sessions(repo_root=repo_filter)

            # Convert to summaries
            from ninja_coder.models import SessionSummary

            session_summaries = []
            for session in sessions:
                summary_dict = self.driver.session_manager.get_session_summary(session.session_id)
                if summary_dict:
                    session_summaries.append(SessionSummary(**summary_dict))

            return ListSessionsResult(
                status="ok",
                sessions=session_summaries,
                count=len(session_summaries),
            )

        except Exception as e:
            logger.error(f"[{client_id}] List sessions failed: {e}", exc_info=True)
            return ListSessionsResult(
                status="error",
                sessions=[],
                count=0,
            )

    async def delete_session(
        self,
        request: DeleteSessionRequest,
        client_id: str = "default",
    ) -> DeleteSessionResult:
        """Delete a conversation session.

        Args:
            request: Delete session request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Delete session result.
        """
        logger.info(f"[{client_id}] Deleting session {request.session_id}")

        try:
            # Delete session using driver's session manager
            deleted = self.driver.session_manager.delete_session(request.session_id)

            if deleted:
                # Structured logging: Session deleted
                self.driver.structured_logger.log_session(
                    action="deleted",
                    session_id=request.session_id,
                )

                return DeleteSessionResult(
                    status="ok",
                    message=f"✅ Session {request.session_id} deleted successfully",
                )
            else:
                # Structured logging: Session not found
                self.driver.structured_logger.warning(
                    f"Session not found for deletion: {request.session_id}",
                    session_id=request.session_id,
                )

                return DeleteSessionResult(
                    status="not_found",
                    message=f"⚠️ Session {request.session_id} not found",
                )

        except Exception as e:
            logger.error(f"[{client_id}] Delete session failed: {e}", exc_info=True)
            return DeleteSessionResult(
                status="error",
                message=f"❌ Failed to delete session: {str(e)[:100]}",
            )

    async def get_agents(
        self,
        request: GetAgentsRequest,
        client_id: str = "default",
    ) -> GetAgentsResult:
        """Get information about available specialized agents.

        Args:
            request: Get agents request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Get agents result with agent information.
        """
        logger.info(f"[{client_id}] Getting available agents")

        try:
            # Import multi-agent orchestrator
            from ninja_coder.multi_agent import MultiAgentOrchestrator

            # Create orchestrator (requires OpenCode strategy)
            if hasattr(self.driver._strategy, "build_command_with_multi_agent"):
                orchestrator = MultiAgentOrchestrator(self.driver._strategy)
                summary = orchestrator.get_agent_summary()

                agents = [
                    AgentInfo(
                        name=agent["name"],
                        description=agent["description"],
                        keywords=agent["keywords"],
                    )
                    for agent in summary["agents"]
                ]

                return GetAgentsResult(
                    status="ok",
                    total_agents=summary["total_agents"],
                    agents=agents,
                )
            else:
                return GetAgentsResult(
                    status="error",
                    total_agents=0,
                    agents=[],
                )

        except Exception as e:
            logger.error(f"[{client_id}] Get agents failed: {e}", exc_info=True)
            return GetAgentsResult(
                status="error",
                total_agents=0,
                agents=[],
            )

    async def multi_agent_task(
        self,
        request: MultiAgentTaskRequest,
        client_id: str = "default",
    ) -> MultiAgentTaskResult:
        """Execute task with multi-agent orchestration.

        Args:
            request: Multi-agent task request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Multi-agent task result.
        """
        logger.info(f"[{client_id}] Executing multi-agent task for {request.repo_root}")

        step_id = f"multiagent_{int(datetime.utcnow().timestamp())}"

        try:
            # Verify strategy supports multi-agent
            if not hasattr(self.driver._strategy, "build_command_with_multi_agent"):
                return MultiAgentTaskResult(
                    status="error",
                    summary="❌ Multi-agent orchestration requires OpenCode CLI",
                    notes="Current CLI does not support multi-agent mode. Set NINJA_CODE_BIN=opencode",
                    agents_used=[],
                )

            # Import multi-agent orchestrator
            from ninja_coder.multi_agent import MultiAgentOrchestrator

            orchestrator = MultiAgentOrchestrator(self.driver._strategy)

            # Analyze task
            analysis = orchestrator.analyze_task(request.task, request.context_paths)

            # Select agents
            agents = orchestrator.select_agents(request.task, analysis)
            logger.info(f"🤖 Selected {len(agents)} agents: {', '.join(agents)}")

            # Build enhanced prompt with ultrawork
            context = {
                "complexity": analysis.complexity,
                "task_type": analysis.task_type,
                "estimated_files": analysis.estimated_files,
            }
            enhanced_prompt = orchestrator.build_ultrawork_prompt(request.task, agents, context)

            # Build instruction
            builder = InstructionBuilder(request.repo_root, mode=ExecutionMode.QUICK)
            instruction = builder.build_quick_task(
                task=enhanced_prompt,
                context_paths=request.context_paths,
                allowed_globs=request.allowed_globs,
                deny_globs=request.deny_globs,
            )

            # Execute with or without session
            if request.session_id:
                # Continue existing session
                result = await self.driver.execute_with_session(
                    task=enhanced_prompt,
                    repo_root=request.repo_root,
                    step_id=step_id,
                    session_id=request.session_id,
                    context_paths=request.context_paths,
                    allowed_globs=request.allowed_globs,
                    deny_globs=request.deny_globs,
                )
            else:
                # Execute without session
                result = await self.driver.execute_async(
                    repo_root=request.repo_root,
                    step_id=step_id,
                    instruction=instruction,
                    task_type="parallel",  # Multi-agent is like parallel execution
                )

            if result.success:
                return MultiAgentTaskResult(
                    status="ok",
                    summary=result.summary,
                    notes=result.notes,
                    agents_used=agents,
                    suspected_touched_paths=result.suspected_touched_paths,
                    session_id=result.session_id,
                )
            else:
                return MultiAgentTaskResult(
                    status="error",
                    summary=result.summary,
                    notes=result.notes,
                    agents_used=agents,
                    suspected_touched_paths=result.suspected_touched_paths,
                    session_id=result.session_id,
                )

        except Exception as e:
            logger.error(f"[{client_id}] Multi-agent task failed: {e}", exc_info=True)
            return MultiAgentTaskResult(
                status="error",
                summary=f"❌ Failed to execute multi-agent task: {str(e)[:100]}",
                notes=str(e),
                agents_used=[],
            )

    async def query_logs(
        self,
        request: QueryLogsRequest,
        client_id: str = "default",
    ) -> QueryLogsResult:
        """Query structured logs with filters.

        Args:
            request: Query logs request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Query logs result with matching entries.
        """
        logger.info(
            f"[{client_id}] Querying logs: session_id={request.session_id}, "
            f"task_id={request.task_id}, level={request.level}, limit={request.limit}"
        )

        try:
            # Query using driver's structured logger
            entries = self.driver.structured_logger.query_logs(
                session_id=request.session_id,
                task_id=request.task_id,
                cli_name=request.cli_name,
                level=request.level,
                limit=request.limit,
                offset=request.offset,
            )

            # Count total matching entries
            total_count = self.driver.structured_logger.count_logs(
                session_id=request.session_id,
                task_id=request.task_id,
                cli_name=request.cli_name,
                level=request.level,
            )

            return QueryLogsResult(
                status="ok",
                entries=entries,
                total_count=total_count,
                returned_count=len(entries),
                message=f"✅ Found {total_count} matching log entries (returned {len(entries)})",
            )

        except Exception as e:
            logger.error(f"[{client_id}] Query logs failed: {e}", exc_info=True)
            return QueryLogsResult(
                status="error",
                entries=[],
                total_count=0,
                returned_count=0,
                message=f"❌ Failed to query logs: {str(e)[:100]}",
            )


# Singleton executor instance
_executor: ToolExecutor | None = None
_executor_config_hash: str | None = None


def _get_config_hash() -> str:
    """
    Get a hash of the current configuration from environment variables.

    This is used to detect when configuration changes require recreating the executor.
    """
    import hashlib

    # Get all config-relevant env vars
    config_vars = [
        ("NINJA_CODE_BIN", os.getenv("NINJA_CODE_BIN", "")),
        ("NINJA_MODEL", os.getenv("NINJA_MODEL", "")),
        ("OPENROUTER_MODEL", os.getenv("OPENROUTER_MODEL", "")),
        ("OPENAI_MODEL", os.getenv("OPENAI_MODEL", "")),
        ("OPENAI_BASE_URL", os.getenv("OPENAI_BASE_URL", "")),
        ("OPENROUTER_API_KEY", os.getenv("OPENROUTER_API_KEY", "")),
        ("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", "")),
        ("NINJA_TIMEOUT_SEC", os.getenv("NINJA_TIMEOUT_SEC", "")),
    ]

    # Create a stable hash of the configuration
    config_str = "|".join(f"{k}={v}" for k, v in sorted(config_vars))
    return hashlib.sha256(config_str.encode()).hexdigest()


def get_executor() -> ToolExecutor:
    """
    Get the global tool executor instance.

    If configuration has changed since last call, recreates the executor
    with the new configuration.
    """
    global _executor, _executor_config_hash

    current_config_hash = _get_config_hash()

    # Recreate executor if config changed or doesn't exist
    if _executor is None or _executor_config_hash != current_config_hash:
        if _executor is not None:
            logger.info("Configuration changed, recreating executor")
        _executor = ToolExecutor()
        _executor_config_hash = current_config_hash

    return _executor


def reset_executor() -> None:
    """Reset the global tool executor (for testing)."""
    global _executor, _executor_config_hash
    _executor = None
    _executor_config_hash = None
