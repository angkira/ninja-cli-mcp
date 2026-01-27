"""
Core benchmark framework for comparing CLI tools and models.

This module provides the infrastructure for running benchmarks and
generating comparison reports.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ninja_coder.driver import InstructionBuilder, NinjaConfig, NinjaDriver
from ninja_coder.models import ExecutionMode
from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)


@dataclass
class BenchmarkTask:
    """A single benchmark task definition."""

    id: str
    """Unique task identifier."""

    name: str
    """Human-readable task name."""

    description: str
    """Task description."""

    task_spec: str
    """Task specification for the CLI."""

    expected_files: list[str] = field(default_factory=list)
    """Files expected to be created/modified."""

    validation_criteria: dict[str, Any] = field(default_factory=dict)
    """Additional validation criteria."""

    complexity: str = "quick"
    """Task complexity ('quick', 'sequential', 'parallel')."""


@dataclass
class BenchmarkResult:
    """Result of running a benchmark task."""

    task_id: str
    """Task identifier."""

    cli_tool: str
    """CLI tool used (aider, opencode, etc.)."""

    model: str
    """Model used."""

    success: bool
    """Whether the task completed successfully."""

    duration_sec: float
    """Duration in seconds."""

    tokens_used: int = 0
    """Tokens used (estimated)."""

    cost_estimate: float = 0.0
    """Estimated cost in USD."""

    files_created: list[str] = field(default_factory=list)
    """Files created/modified."""

    validation_passed: bool = False
    """Whether validation passed."""

    error_message: str = ""
    """Error message if failed."""


class BenchmarkRunner:
    """Runner for executing benchmarks and generating reports.

    This class orchestrates benchmark execution across different CLI tools
    and models, collecting performance metrics and generating comparison reports.
    """

    def __init__(self, output_dir: Path):
        """Initialize benchmark runner.

        Args:
            output_dir: Directory for benchmark outputs and reports.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def run_benchmark(
        self,
        task: BenchmarkTask,
        cli_bin: str,
        model: str,
        repo_root: str,
    ) -> BenchmarkResult:
        """Run a single benchmark task.

        Args:
            task: Benchmark task to run.
            cli_bin: CLI binary name (e.g., 'aider', 'opencode-cli').
            model: Model to use.
            repo_root: Repository root path.

        Returns:
            BenchmarkResult with performance metrics.
        """
        start_time = time.time()

        try:
            # Create driver with specific CLI and model
            config = NinjaConfig(
                bin_path=cli_bin,
                model=model,
            )
            driver = NinjaDriver(config)

            # Build instruction
            builder = InstructionBuilder(repo_root, ExecutionMode.QUICK)
            instruction = builder.build_quick_task(
                task=task.task_spec,
                context_paths=[],
                allowed_globs=["**/*"],
                deny_globs=[],
            )

            # Execute
            result = await driver.execute_async(
                repo_root=repo_root,
                step_id=f"benchmark_{task.id}",
                instruction=instruction,
                task_type=task.complexity,
            )

            duration = time.time() - start_time

            # Validate result
            validation_passed = self._validate_result(
                result,
                task.expected_files,
                task.validation_criteria,
                repo_root,
            )

            # Estimate cost (placeholder - would need actual token counts)
            cost_estimate = self._estimate_cost(model, duration)

            return BenchmarkResult(
                task_id=task.id,
                cli_tool=driver.strategy.name,
                model=model,
                success=result.success,
                duration_sec=duration,
                tokens_used=0,  # Would need actual token tracking
                cost_estimate=cost_estimate,
                files_created=result.suspected_touched_paths,
                validation_passed=validation_passed,
                error_message=result.notes if not result.success else "",
            )

        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"Benchmark failed for {task.id}: {e}")

            return BenchmarkResult(
                task_id=task.id,
                cli_tool=cli_bin,
                model=model,
                success=False,
                duration_sec=duration,
                error_message=str(e),
            )

    async def run_comparison(
        self,
        tasks: list[BenchmarkTask],
        cli_tools: list[str],
        models: list[str],
        repo_root: str,
    ) -> dict[str, list[BenchmarkResult]]:
        """Run full comparison across tasks, tools, and models.

        Args:
            tasks: List of benchmark tasks.
            cli_tools: List of CLI tools to test.
            models: List of models to test.
            repo_root: Repository root path.

        Returns:
            Dictionary mapping task IDs to lists of results.
        """
        results = {}

        for task in tasks:
            logger.info(f"Running benchmark task: {task.name}")
            task_results = []

            for cli_tool in cli_tools:
                for model in models:
                    logger.info(f"  Testing {cli_tool} with {model}")
                    result = await self.run_benchmark(task, cli_tool, model, repo_root)
                    task_results.append(result)

            results[task.id] = task_results

        # Generate comparison report
        self._generate_report(results, tasks)

        return results

    def _validate_result(
        self,
        result: Any,
        expected_files: list[str],
        criteria: dict[str, Any],
        repo_root: str,
    ) -> bool:
        """Validate benchmark result.

        Args:
            result: Execution result.
            expected_files: Expected files.
            criteria: Additional validation criteria.
            repo_root: Repository root.

        Returns:
            True if validation passed.
        """
        if not result.success:
            return False

        # Check expected files exist
        for file_path in expected_files:
            full_path = Path(repo_root) / file_path
            if not full_path.exists():
                logger.warning(f"Expected file not found: {file_path}")
                return False

        # Additional validation criteria could be checked here
        # (e.g., check file content, run tests, etc.)

        return True

    def _estimate_cost(self, model: str, duration: float) -> float:
        """Estimate cost based on model and duration.

        This is a rough estimate. Real cost tracking would require
        actual token counts from the API.

        Args:
            model: Model name.
            duration: Duration in seconds.

        Returns:
            Estimated cost in USD.
        """
        # Rough cost estimates per second of execution
        cost_per_second = {
            "glm-4.6v": 0.0001,
            "glm-4.7": 0.0005,
            "glm-4.0": 0.0002,
            "anthropic/claude-haiku-4.5": 0.0003,
            "anthropic/claude-sonnet-4": 0.0008,
            "anthropic/claude-opus-4": 0.0015,
        }.get(model, 0.0002)

        return duration * cost_per_second

    def _generate_report(
        self,
        results: dict[str, list[BenchmarkResult]],
        tasks: list[BenchmarkTask],
    ) -> None:
        """Generate markdown comparison report.

        Args:
            results: Benchmark results.
            tasks: Benchmark tasks.
        """
        report_path = self.output_dir / "benchmark_report.md"

        with open(report_path, "w") as f:
            f.write("# Ninja Coder Benchmark Report\n\n")
            f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            for task in tasks:
                task_results = results.get(task.id, [])
                if not task_results:
                    continue

                f.write(f"## Task: {task.name}\n\n")
                f.write(f"**Description:** {task.description}\n\n")
                f.write(f"**Complexity:** {task.complexity}\n\n")

                f.write("| CLI Tool | Model | Success | Duration | Cost | Validation |\n")
                f.write("|----------|-------|---------|----------|------|------------|\n")

                for result in task_results:
                    success_icon = "✅" if result.success else "❌"
                    validation_icon = "✅" if result.validation_passed else "❌"

                    f.write(
                        f"| {result.cli_tool} | {result.model} | "
                        f"{success_icon} | "
                        f"{result.duration_sec:.2f}s | "
                        f"${result.cost_estimate:.4f} | "
                        f"{validation_icon} |\n"
                    )

                f.write("\n")

                # Add summary statistics
                successful = [r for r in task_results if r.success]
                if successful:
                    avg_duration = sum(r.duration_sec for r in successful) / len(successful)
                    f.write(f"**Average Duration (successful):** {avg_duration:.2f}s\n\n")

        logger.info(f"Generated benchmark report: {report_path}")
