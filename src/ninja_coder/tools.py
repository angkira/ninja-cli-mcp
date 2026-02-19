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
    ExecutionMode,
    GetAgentsRequest,
    GetAgentsResult,
    MultiAgentTaskRequest,
    MultiAgentTaskResult,
    ParallelPlanRequest,
    PlanExecutionResult,
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

        # Ensure summary is concise (max 500 chars)
        summary = result.summary[:500] if len(result.summary) > 500 else result.summary

        # Prepare error message if failed
        error_message = None
        if not result.success:
            # Ensure error message is concise (max 300 chars)
            error_message = result.notes[:300] if len(result.notes) > 300 else result.notes

        return StepResult(
            id=step_id,
            status=status,  # type: ignore
            summary=summary,
            files_touched=result.suspected_touched_paths[:10],  # Max 10 paths
            error_message=error_message,
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

            # Validate task is not empty
            if not request.task or not request.task.strip():
                raise ValueError("Task description cannot be empty")

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
        Execute CODE WRITING plan steps in ONE subprocess with structured prompt.

        All steps are executed together in a single process, allowing the AI to maintain
        context across steps and produce a comprehensive result.

        Returns ONLY concise summaries per step - NO source code.

        Args:
            request: Sequential plan request parameters.
            client_id: Client identifier for isolation and rate limiting.

        Returns:
            Plan execution result with per-step CONCISE summaries (no source code).
        """
        logger.info(
            f"Executing {len(request.steps)} steps sequentially (single-process) for {client_id}"
        )

        # Generate task ID and start timer
        plan_task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate repo root
        try:
            validate_repo_root(request.repo_root)
        except ValueError as e:
            return PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=f"❌ {e!s}",
            )

        # 1. Build rich prompt with all steps using PromptBuilder
        from ninja_coder.prompt_builder import PromptBuilder
        from ninja_coder.result_parser import ResultParser

        builder_prompt = PromptBuilder(request.repo_root)
        prompt = builder_prompt.build_sequential_plan(
            steps=request.steps,
            mode=request.mode,
        )

        # 2. Build instruction
        instruction_builder = InstructionBuilder(request.repo_root, request.mode)
        instruction = instruction_builder.build_quick_task(
            task=prompt,
            context_paths=[],  # Already included in prompt
            allowed_globs=request.global_allowed_globs,
            deny_globs=request.global_deny_globs,
        )

        # 3. Execute ONCE
        try:
            result = await self.driver.execute_async(
                repo_root=request.repo_root,
                step_id=f"sequential_plan_{plan_task_id[:8]}",
                instruction=instruction,
                timeout_sec=self._estimate_sequential_timeout(request),
                task_type="sequential_plan",
            )
        except Exception as e:
            logger.error(f"Sequential plan execution failed: {e}")
            return PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=f"❌ Execution error: {e!s}",
            )

        # 4. Parse structured result
        if result.success:
            try:
                parser = ResultParser()
                plan_result = parser.parse_plan_result(result.stdout)
            except Exception as e:
                logger.warning(f"Failed to parse structured result: {e}")
                # Fallback: create basic result
                plan_result = PlanExecutionResult(
                    overall_status="success" if result.success else "failed",
                    steps=[
                        StepResult(
                            id=step.id,
                            status="ok",
                            summary="Completed (details in output)",
                            files_touched=[],
                        )
                        for step in request.steps
                    ],
                    files_modified=result.suspected_touched_paths,
                    notes=result.summary[:500],
                )
        else:
            plan_result = PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=result.summary[:500],
            )

        # 5. Record metrics
        duration = time.time() - start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="coder_execute_plan_sequential",
            task_description=f"Sequential plan ({len(request.steps)} steps)",
            output=result.stdout,
            duration_sec=duration,
            success=result.success,
            execution_mode=request.mode.value,
            repo_root=request.repo_root,
            client_id=client_id,
        )

        return plan_result

    def _estimate_sequential_timeout(self, request: SequentialPlanRequest) -> int:
        """Estimate timeout for sequential plan."""
        base = 300
        per_step = 60
        return base + (per_step * len(request.steps))

    async def execute_plan_parallel(
        self, request: ParallelPlanRequest, client_id: str = "default"
    ) -> PlanExecutionResult:
        """Execute CODE WRITING plan steps in ONE subprocess with parallelization instructions."""

        logger.info(
            f"Executing {len(request.steps)} steps in parallel (single-process, fanout={request.fanout}) for {client_id}"
        )

        # Generate task ID and start timer
        plan_task_id = str(uuid.uuid4())
        start_time = time.time()

        # Validate repo root
        try:
            validate_repo_root(request.repo_root)
        except ValueError as e:
            return PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=f"❌ {e!s}",
            )

        # 1. Build rich prompt with all tasks using PromptBuilder
        from ninja_coder.prompt_builder import PromptBuilder
        from ninja_coder.result_parser import ResultParser

        builder_prompt = PromptBuilder(request.repo_root)
        prompt = builder_prompt.build_parallel_plan(
            tasks=request.steps,
            fanout=request.fanout,
            mode=request.mode,
        )

        # 2. Build instruction
        instruction_builder = InstructionBuilder(request.repo_root, request.mode)
        instruction = instruction_builder.build_quick_task(
            task=prompt,
            context_paths=[],  # Already included in prompt
            allowed_globs=request.global_allowed_globs,
            deny_globs=request.global_deny_globs,
        )

        # 3. Execute ONCE
        try:
            result = await self.driver.execute_async(
                repo_root=request.repo_root,
                step_id=f"parallel_plan_{plan_task_id[:8]}",
                instruction=instruction,
                timeout_sec=self._estimate_parallel_timeout(request),
                task_type="parallel_plan",
            )
        except Exception as e:
            logger.error(f"Parallel plan execution failed: {e}")
            return PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=f"❌ Execution error: {e!s}",
            )

        # 4. Parse structured result
        if result.success:
            try:
                parser = ResultParser()
                plan_result = parser.parse_plan_result(result.stdout)
            except Exception as e:
                logger.warning(f"Failed to parse structured result: {e}")
                # Fallback: create basic result
                plan_result = PlanExecutionResult(
                    overall_status="success" if result.success else "failed",
                    steps=[
                        StepResult(
                            id=step.id,
                            status="ok",
                            summary="Completed (details in output)",
                            files_touched=[],
                        )
                        for step in request.steps
                    ],
                    files_modified=result.suspected_touched_paths,
                    notes=result.summary[:500],
                )
        else:
            plan_result = PlanExecutionResult(
                overall_status="failed",
                steps=[],
                files_modified=[],
                notes=result.summary[:500],
            )

        # 5. Record metrics
        duration = time.time() - start_time
        self._record_metrics(
            task_id=plan_task_id,
            tool_name="coder_execute_plan_parallel",
            task_description=f"Parallel plan ({len(request.steps)} tasks)",
            output=result.stdout,
            duration_sec=duration,
            success=result.success,
            execution_mode=request.mode.value,
            repo_root=request.repo_root,
            client_id=client_id,
        )

        return plan_result

    def _estimate_parallel_timeout(self, request: ParallelPlanRequest) -> int:
        """Estimate timeout for parallel plan."""
        base = 300
        per_task = 30  # Parallel is faster
        return base + (per_task * max(1, len(request.steps) // request.fanout))

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

            # Execute task
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
                    session_id=None,  # Session support removed
                )
            else:
                return MultiAgentTaskResult(
                    status="error",
                    summary=result.summary,
                    notes=result.notes,
                    agents_used=agents,
                    suspected_touched_paths=result.suspected_touched_paths,
                    session_id=None,  # Session support removed
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
