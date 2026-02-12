"""
Integration tests for sequential plan execution.

Tests the complete flow of sequential plan execution including:
- Single subprocess execution for all steps
- Structured prompt building via PromptBuilder
- Result parsing via ResultParser
- Error handling and fallback scenarios
- Timeout estimation
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver, NinjaResult
from ninja_coder.models import (
    ExecutionMode,
    PlanExecutionResult,
    PlanStep,
    SequentialPlanRequest,
    StepResult,
    TestPlan,
)
from ninja_coder.tools import ToolExecutor


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary test repository with basic structure."""
    repo = tmp_path / "test_repo"
    repo.mkdir()

    # Create basic directory structure
    (repo / "src").mkdir()
    (repo / "tests").mkdir()

    # Create some test files
    (repo / "src" / "__init__.py").write_text("")
    (repo / "src" / "models.py").write_text("# Models module\n")
    (repo / "tests" / "__init__.py").write_text("")

    return repo


@pytest.fixture
def mock_driver():
    """Create a mock driver with basic config."""
    driver = Mock(spec=NinjaDriver)
    driver.config = NinjaConfig(
        model="anthropic/claude-3.5-sonnet",
        bin_path="opencode",
    )
    driver._strategy = Mock()
    driver._strategy.name = "opencode"
    driver.session_manager = Mock()
    driver.structured_logger = Mock()
    driver.structured_logger.info = Mock()
    driver.structured_logger.log_command = Mock()
    driver.structured_logger.log_result = Mock()
    return driver


@pytest.fixture
def executor(mock_driver):
    """Create ToolExecutor with mock driver."""
    return ToolExecutor(driver=mock_driver)


@pytest.fixture
def sample_sequential_request(temp_repo: Path) -> SequentialPlanRequest:
    """Create a sample sequential plan request with 3 steps."""
    return SequentialPlanRequest(
        repo_root=str(temp_repo),
        mode=ExecutionMode.QUICK,
        steps=[
            PlanStep(
                id="step1",
                title="Create User Model",
                task="Create a User model in src/models.py with fields: id, email, password_hash",
                context_paths=["src/models.py"],
            ),
            PlanStep(
                id="step2",
                title="Create User Service",
                task="Create a UserService class in src/services.py with methods: register, login",
                context_paths=["src/models.py"],
            ),
            PlanStep(
                id="step3",
                title="Create API Routes",
                task="Create API routes in src/routes.py for /register and /login endpoints",
                context_paths=["src/models.py", "src/services.py"],
            ),
        ],
    )


@pytest.mark.asyncio
class TestSequentialPlanEndToEnd:
    """Test complete sequential plan execution flow."""

    async def test_sequential_plan_with_mock_cli_success(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Test sequential plan with mocked CLI returning structured JSON."""
        # Mock the driver's execute_async to return success with structured JSON
        mock_stdout = """
```json
{
  "overall_status": "success",
  "steps_completed": ["step1", "step2", "step3"],
  "steps_failed": [],
  "step_summaries": {
    "step1": "Created User model in src/models.py with id, email, password_hash fields",
    "step2": "Created UserService class in src/services.py with register and login methods",
    "step3": "Created API routes in src/routes.py for /register and /login"
  },
  "files_modified": [
    "src/models.py",
    "src/services.py",
    "src/routes.py"
  ],
  "notes": "All steps completed successfully"
}
```
        """

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="✅ Sequential plan completed: 3/3 steps successful",
                notes="All steps completed",
                suspected_touched_paths=["src/models.py", "src/services.py", "src/routes.py"],
                stdout=mock_stdout,
                stderr="",
                exit_code=0,
                model_used="anthropic/claude-3.5-sonnet",
            )
        )

        # Execute sequential plan
        result = await executor.execute_plan_sequential(sample_sequential_request)

        # Verify execute_async was called once (not 3 times!)
        assert executor.driver.execute_async.call_count == 1

        # Verify task_type was passed correctly
        call_kwargs = executor.driver.execute_async.call_args.kwargs
        assert call_kwargs["task_type"] == "sequential_plan"

        # Verify result
        assert result.overall_status == "success"
        assert len(result.steps) == 3

        # Check all steps succeeded
        for step in result.steps:
            assert step.status == "ok"
            assert step.summary  # Has summary

        # Check files modified
        assert len(result.files_modified) == 3
        assert "src/models.py" in result.files_modified

    async def test_sequential_plan_with_partial_failure(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Test sequential plan where step 2 fails."""
        # Mock CLI output with partial failure
        mock_stdout = """
```json
{
  "overall_status": "partial",
  "steps_completed": ["step1"],
  "steps_failed": ["step2"],
  "step_summaries": {
    "step1": "Created User model successfully",
    "step2": "Failed to create UserService: Import error",
    "step3": "Skipped due to previous failure"
  },
  "files_modified": ["src/models.py"],
  "notes": "Step 2 failed, step 3 was skipped"
}
```
        """

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=False,
                summary="❌ Sequential plan failed at step 2",
                notes="Step 2 failed with import error",
                suspected_touched_paths=["src/models.py"],
                stdout=mock_stdout,
                stderr="ImportError: Cannot import User model",
                exit_code=1,
                model_used="anthropic/claude-3.5-sonnet",
            )
        )

        result = await executor.execute_plan_sequential(sample_sequential_request)

        # Verify failure (when success=False, ResultParser creates "failed" status even if JSON says "partial")
        # This is expected fallback behavior
        assert result.overall_status == "failed"
        assert len(result.steps) == 0  # No steps on complete failure

    async def test_sequential_plan_complete_failure(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Test sequential plan with complete failure (CLI error)."""
        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=False,
                summary="❌ CLI execution failed",
                notes="OpenCode returned error",
                suspected_touched_paths=[],
                stdout="",
                stderr="Error: Invalid API key",
                exit_code=1,
                model_used="anthropic/claude-3.5-sonnet",
            )
        )

        result = await executor.execute_plan_sequential(sample_sequential_request)

        # Verify complete failure
        assert result.overall_status == "failed"
        assert len(result.steps) == 0  # No steps completed
        assert len(result.files_modified) == 0


@pytest.mark.asyncio
class TestPromptBuilderIntegration:
    """Test PromptBuilder is called correctly."""

    async def test_prompt_builder_called_with_correct_params(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Verify PromptBuilder constructs the prompt correctly."""
        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout='{"overall_status": "success", "steps_completed": [], "step_summaries": {}}',
                stderr="",
                exit_code=0,
            )
        )

        # Patch PromptBuilder to verify it's called
        with patch("ninja_coder.prompt_builder.PromptBuilder") as MockPromptBuilder:
            mock_builder_instance = Mock()
            mock_builder_instance.build_sequential_plan.return_value = "# SEQUENTIAL EXECUTION PLAN\n..."
            MockPromptBuilder.return_value = mock_builder_instance

            await executor.execute_plan_sequential(sample_sequential_request)

            # Verify PromptBuilder was instantiated with repo_root
            MockPromptBuilder.assert_called_once_with(sample_sequential_request.repo_root)

            # Verify build_sequential_plan was called with steps and mode
            mock_builder_instance.build_sequential_plan.assert_called_once()
            call_kwargs = mock_builder_instance.build_sequential_plan.call_args.kwargs
            assert call_kwargs["steps"] == sample_sequential_request.steps
            assert call_kwargs["mode"] == sample_sequential_request.mode


@pytest.mark.asyncio
class TestResultParserIntegration:
    """Test ResultParser extracts results correctly."""

    async def test_result_parser_called_on_success(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Verify ResultParser is called to parse structured output."""
        mock_stdout = '{"overall_status": "success", "steps_completed": ["step1"], "step_summaries": {"step1": "Done"}}'

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout=mock_stdout,
                stderr="",
                exit_code=0,
            )
        )

        # Patch ResultParser
        with patch("ninja_coder.result_parser.ResultParser") as MockResultParser:
            mock_parser_instance = Mock()
            mock_parser_instance.parse_plan_result.return_value = PlanExecutionResult(
                overall_status="success",
                steps=[
                    StepResult(id="step1", status="ok", summary="Done", files_touched=[])
                ],
                files_modified=[],
                notes="Parsed result",
            )
            MockResultParser.return_value = mock_parser_instance

            result = await executor.execute_plan_sequential(sample_sequential_request)

            # Verify ResultParser was used
            mock_parser_instance.parse_plan_result.assert_called_once_with(mock_stdout)

            # Verify we got the parsed result
            assert result.overall_status == "success"
            assert len(result.steps) == 1

    async def test_result_parser_fallback_on_parse_error(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Test fallback when ResultParser fails to parse output."""
        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout="Invalid JSON output",  # Not valid JSON
                stderr="",
                exit_code=0,
                suspected_touched_paths=["file1.py", "file2.py"],
            )
        )

        result = await executor.execute_plan_sequential(sample_sequential_request)

        # Verify fallback result was created
        assert result.overall_status == "success"
        assert len(result.steps) == 3  # All steps in request

        # All steps should have basic status
        for i, step in enumerate(result.steps):
            assert step.id == sample_sequential_request.steps[i].id
            assert step.status == "ok"
            assert "Completed" in step.summary or "details in output" in step.summary


@pytest.mark.asyncio
class TestTimeoutEstimation:
    """Test timeout estimation for sequential plans."""

    def test_estimate_sequential_timeout_single_step(self, executor: ToolExecutor, temp_repo: Path):
        """Test timeout estimation for 1 step."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=[
                PlanStep(id="step1", title="Single Step", task="Do something")
            ],
        )

        timeout = executor._estimate_sequential_timeout(request)

        # Base (300s) + 1 step (60s) = 360s
        assert timeout == 360

    def test_estimate_sequential_timeout_three_steps(self, executor: ToolExecutor, temp_repo: Path):
        """Test timeout estimation for 3 steps."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=[
                PlanStep(id=f"step{i}", title=f"Step {i}", task="Do something")
                for i in range(1, 4)
            ],
        )

        timeout = executor._estimate_sequential_timeout(request)

        # Base (300s) + 3 steps (180s) = 480s
        assert timeout == 480

    def test_estimate_sequential_timeout_five_steps(self, executor: ToolExecutor, temp_repo: Path):
        """Test timeout estimation for 5 steps."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=[
                PlanStep(id=f"step{i}", title=f"Step {i}", task="Do something")
                for i in range(1, 6)
            ],
        )

        timeout = executor._estimate_sequential_timeout(request)

        # Base (300s) + 5 steps (300s) = 600s
        assert timeout == 600


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in sequential execution."""

    async def test_sequential_with_cli_exception(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Test handling of CLI exceptions during execution."""
        executor.driver.execute_async = AsyncMock(
            side_effect=RuntimeError("CLI crashed")
        )

        result = await executor.execute_plan_sequential(sample_sequential_request)

        # Verify error is caught and returned as failed result
        assert result.overall_status == "failed"
        assert "Execution error" in result.notes

    async def test_sequential_with_invalid_repo_root(self, executor: ToolExecutor):
        """Test handling of invalid repo_root."""
        request = SequentialPlanRequest(
            repo_root="/nonexistent/path/to/repo",
            steps=[
                PlanStep(id="step1", title="Test", task="Do something")
            ],
        )

        result = await executor.execute_plan_sequential(request)

        # Verify validation error
        assert result.overall_status == "failed"
        assert "does not exist" in result.notes or "not a directory" in result.notes

    async def test_sequential_with_empty_steps(self, executor: ToolExecutor, temp_repo: Path):
        """Test handling of request with no steps."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=[],  # Empty!
        )

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Nothing to do",
                stdout='{"overall_status": "success", "steps_completed": [], "step_summaries": {}}',
                stderr="",
                exit_code=0,
            )
        )

        result = await executor.execute_plan_sequential(request)

        # Should complete successfully but with no steps
        assert result.overall_status == "success"
        assert len(result.steps) == 0


@pytest.mark.asyncio
class TestGlobalGlobPatterns:
    """Test global allowed_globs and deny_globs."""

    async def test_global_globs_passed_to_instruction(
        self,
        executor: ToolExecutor,
        temp_repo: Path,
    ):
        """Verify global globs are passed to InstructionBuilder."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            global_allowed_globs=["src/**/*.py"],
            global_deny_globs=["tests/**/*"],
            steps=[
                PlanStep(id="step1", title="Test", task="Do something")
            ],
        )

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout='{"overall_status": "success", "steps_completed": [], "step_summaries": {}}',
                stderr="",
                exit_code=0,
            )
        )

        # Patch InstructionBuilder to capture its usage
        with patch("ninja_coder.tools.InstructionBuilder") as MockInstructionBuilder:
            mock_builder_instance = Mock()
            mock_builder_instance.build_quick_task.return_value = {"task": "test"}
            MockInstructionBuilder.return_value = mock_builder_instance

            await executor.execute_plan_sequential(request)

            # Verify build_quick_task was called with global globs
            call_kwargs = mock_builder_instance.build_quick_task.call_args.kwargs
            assert call_kwargs["allowed_globs"] == ["src/**/*.py"]
            assert call_kwargs["deny_globs"] == ["tests/**/*"]


@pytest.mark.asyncio
class TestStepWithTestPlan:
    """Test sequential execution with test plans."""

    async def test_step_with_unit_tests(
        self,
        executor: ToolExecutor,
        temp_repo: Path,
    ):
        """Test step with unit test commands."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            mode=ExecutionMode.FULL,  # Full mode with testing
            steps=[
                PlanStep(
                    id="step1",
                    title="Create Model with Tests",
                    task="Create User model and tests",
                    test_plan=TestPlan(
                        unit=["pytest tests/test_models.py"],
                        e2e=[],
                    ),
                    max_iterations=3,
                )
            ],
        )

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success with tests",
                stdout='{"overall_status": "success", "steps_completed": ["step1"], "step_summaries": {"step1": "Created model, tests passed"}}',
                stderr="",
                exit_code=0,
            )
        )

        result = await executor.execute_plan_sequential(request)

        # Verify success
        assert result.overall_status == "success"
        assert len(result.steps) == 1
        assert result.steps[0].status == "ok"


@pytest.mark.asyncio
class TestMetricsRecording:
    """Test that metrics are recorded correctly."""

    async def test_metrics_recorded_on_success(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Verify metrics are recorded for sequential plan."""
        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout='{"overall_status": "success", "steps_completed": [], "step_summaries": {}}',
                stderr="",
                exit_code=0,
            )
        )

        # Patch _record_metrics to verify it's called
        with patch.object(executor, "_record_metrics") as mock_record:
            await executor.execute_plan_sequential(sample_sequential_request)

            # Verify metrics were recorded
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args.kwargs

            assert call_kwargs["tool_name"] == "coder_execute_plan_sequential"
            assert call_kwargs["success"] is True
            assert call_kwargs["execution_mode"] == "quick"
            assert "3 steps" in call_kwargs["task_description"]

    async def test_metrics_recorded_on_failure(
        self,
        executor: ToolExecutor,
        sample_sequential_request: SequentialPlanRequest,
    ):
        """Verify metrics are recorded even on failure."""
        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=False,
                summary="Failed",
                stdout="",
                stderr="Error",
                exit_code=1,
            )
        )

        with patch.object(executor, "_record_metrics") as mock_record:
            await executor.execute_plan_sequential(sample_sequential_request)

            # Verify metrics were recorded for failure
            mock_record.assert_called_once()
            call_kwargs = mock_record.call_args.kwargs
            assert call_kwargs["success"] is False


@pytest.mark.asyncio
class TestContextFlowBetweenSteps:
    """Test that context flows between sequential steps."""

    async def test_step2_references_step1_output(
        self,
        executor: ToolExecutor,
        temp_repo: Path,
    ):
        """Test that step 2 can reference files created in step 1."""
        request = SequentialPlanRequest(
            repo_root=str(temp_repo),
            steps=[
                PlanStep(
                    id="step1",
                    title="Create Model",
                    task="Create User model in src/models.py",
                ),
                PlanStep(
                    id="step2",
                    title="Create Service",
                    task="Create UserService that imports User model from src/models.py",
                    context_paths=["src/models.py"],  # References step1 output
                ),
            ],
        )

        mock_stdout = """
```json
{
  "overall_status": "success",
  "steps_completed": ["step1", "step2"],
  "steps_failed": [],
  "step_summaries": {
    "step1": "Created User model in src/models.py",
    "step2": "Created UserService successfully importing User model"
  },
  "files_modified": ["src/models.py", "src/services.py"],
  "notes": "Step 2 successfully used output from step 1"
}
```
        """

        executor.driver.execute_async = AsyncMock(
            return_value=NinjaResult(
                success=True,
                summary="Success",
                stdout=mock_stdout,
                stderr="",
                exit_code=0,
                suspected_touched_paths=["src/models.py", "src/services.py"],
            )
        )

        result = await executor.execute_plan_sequential(request)

        # Verify both steps completed
        assert result.overall_status == "success"
        assert len(result.steps) == 2
        assert result.steps[0].status == "ok"
        assert result.steps[1].status == "ok"

        # Verify files from both steps were modified
        assert "src/models.py" in result.files_modified
        assert "src/services.py" in result.files_modified


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
