"""
CLI interface for ninja-cli-mcp.

This module provides a command-line interface for testing the MCP tools
directly without going through the MCP protocol.

Usage:
    python -m ninja_cli_mcp.cli quick-task --repo-root /path/to/repo --task "Add a hello world function"
    python -m ninja_cli_mcp.cli run-tests --repo-root /path/to/repo --commands "pytest tests/"
    python -m ninja_cli_mcp.cli list-models  # Show available models
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from ninja_cli_mcp.logging_utils import get_logger, setup_logging
from ninja_cli_mcp.metrics import MetricsTracker
from ninja_cli_mcp.models import (
    ExecutionMode,
    PlanStep,
    QuickTaskRequest,
    RunTestsRequest,
    SequentialPlanRequest,
    TestPlan,
)
from ninja_cli_mcp.ninja_driver import DEFAULT_MODEL, RECOMMENDED_MODELS, NinjaConfig
from ninja_cli_mcp.path_utils import safe_resolve
from ninja_cli_mcp.tools import get_executor


setup_logging()
logger = get_logger(__name__)


def print_result(result: Any) -> None:
    """Print a result as formatted JSON."""
    if hasattr(result, "model_dump"):
        data = result.model_dump()
    else:
        data = result
    print(json.dumps(data, indent=2))


async def cmd_quick_task(args: argparse.Namespace) -> int:
    """Execute a quick task."""
    request = QuickTaskRequest(
        task=args.task,
        repo_root=args.repo_root,
        context_paths=args.context_paths or [],
        allowed_globs=args.allowed_globs or [],
        deny_globs=args.deny_globs or [],
    )

    executor = get_executor()
    result = await executor.quick_task(request)
    print_result(result)

    return 0 if result.status == "ok" else 1


async def cmd_run_tests(args: argparse.Namespace) -> int:
    """Run tests."""
    request = RunTestsRequest(
        repo_root=args.repo_root,
        commands=args.commands,
        timeout_sec=args.timeout,
    )

    executor = get_executor()
    result = await executor.run_tests(request)
    print_result(result)

    return 0 if result.status == "ok" else 1


async def cmd_execute_plan(args: argparse.Namespace) -> int:
    """Execute a plan from a JSON file."""
    with open(args.plan_file) as f:
        plan_data = json.load(f)

    # Parse steps
    steps = []
    for step_data in plan_data.get("steps", []):
        test_plan_data = step_data.get("test_plan", {})
        test_plan = TestPlan(
            unit=test_plan_data.get("unit", []),
            e2e=test_plan_data.get("e2e", []),
        )

        step = PlanStep(
            id=step_data["id"],
            title=step_data["title"],
            task=step_data["task"],
            context_paths=step_data.get("context_paths", []),
            allowed_globs=step_data.get("allowed_globs", []),
            deny_globs=step_data.get("deny_globs", []),
            max_iterations=step_data.get("max_iterations", 3),
            test_plan=test_plan,
        )
        steps.append(step)

    mode = ExecutionMode.FULL if args.full else ExecutionMode.QUICK

    request = SequentialPlanRequest(
        repo_root=args.repo_root,
        mode=mode,
        global_allowed_globs=plan_data.get("global_allowed_globs", []),
        global_deny_globs=plan_data.get("global_deny_globs", []),
        steps=steps,
    )

    executor = get_executor()
    result = await executor.execute_plan_sequential(request)
    print_result(result)

    return 0 if result.status == "ok" else 1


def cmd_list_models(_args: argparse.Namespace) -> int:
    """List available models."""
    print("Recommended OpenRouter Models for Code Tasks")
    print("=" * 60)
    print()

    # Get current config
    config = NinjaConfig.from_env()
    current_model = config.model

    print(f"Current model: {current_model}")
    print(f"Default model: {DEFAULT_MODEL}")
    print()
    print("Available models:")
    print("-" * 60)

    for model_id, description in RECOMMENDED_MODELS.items():
        marker = " *" if model_id == current_model else ""
        print(f"  {model_id}{marker}")
        print(f"    {description}")
        print()

    print("To change the model, set one of these environment variables:")
    print("  NINJA_MODEL=<model-id>")
    print("  OPENROUTER_MODEL=<model-id>")
    print("  OPENAI_MODEL=<model-id>")
    print()
    print("You can use any model available on OpenRouter.")
    print("See https://openrouter.ai/models for the full list.")

    return 0


def cmd_show_config(_args: argparse.Namespace) -> int:
    """Show current configuration."""
    config = NinjaConfig.from_env()

    print("Current Configuration")
    print("=" * 60)
    print(f"  Binary path:    {config.bin_path}")
    print(f"  API base URL:   {config.openai_base_url}")
    print(
        f"  API key:        {'****' + config.openai_api_key[-4:] if config.openai_api_key else '(not set)'}"
    )
    print(f"  Model:          {config.model}")
    print(f"  Timeout:        {config.timeout_sec}s")
    print()
    print("Environment Variables:")
    print("  NINJA_CODE_BIN      - Path to the AI code CLI binary")
    print("  OPENROUTER_API_KEY  - OpenRouter API key")
    print("  NINJA_MODEL         - Model to use (highest priority)")
    print("  OPENROUTER_MODEL    - Model to use (medium priority)")
    print("  OPENAI_MODEL        - Model to use (lowest priority)")
    print("  NINJA_TIMEOUT_SEC   - Execution timeout in seconds")

    return 0


def cmd_metrics_summary(args: argparse.Namespace) -> int:
    """Show metrics summary."""
    from pathlib import Path

    repo_root = Path(args.repo_root).resolve()
    tracker = MetricsTracker(repo_root)

    summary = tracker.get_summary()

    print("Metrics Summary")
    print("=" * 60)
    print(f"  Total tasks:        {summary['total_tasks']}")
    print(f"  Successful tasks:   {summary['successful_tasks']}")
    print(f"  Failed tasks:       {summary['failed_tasks']}")
    print(f"  Total tokens:       {summary['total_tokens']:,}")
    print(f"  Total cost:         ${summary['total_cost']:.4f}")
    print()

    if summary["model_usage"]:
        print("Model Usage:")
        print("-" * 60)
        for model, count in sorted(
            summary["model_usage"].items(), key=lambda x: x[1], reverse=True
        ):
            print(f"  {model}: {count} tasks")
        print()

    return 0


def cmd_metrics_recent(args: argparse.Namespace) -> int:
    """Show recent tasks."""
    from pathlib import Path

    repo_root = Path(args.repo_root).resolve()
    tracker = MetricsTracker(repo_root)

    limit = args.limit if hasattr(args, "limit") else 10
    tasks = tracker.get_recent_tasks(limit=limit)

    if not tasks:
        print("No tasks recorded yet.")
        return 0

    print(f"Recent Tasks (last {len(tasks)})")
    print("=" * 80)
    print()

    for task in tasks:
        status_emoji = "✓" if task.get("success", "").lower() == "true" else "✗"
        print(f"{status_emoji} {task.get('timestamp', 'N/A')[:19]}")
        print(f"  Tool:     {task.get('tool_name', 'N/A')}")
        print(f"  Model:    {task.get('model', 'N/A')}")
        print(
            f"  Tokens:   {task.get('total_tokens', '0')} ({task.get('input_tokens', '0')} in, {task.get('output_tokens', '0')} out)"
        )
        print(f"  Cost:     ${float(task.get('total_cost', 0)):.6f}")
        print(f"  Duration: {float(task.get('duration_sec', 0)):.2f}s")
        print(
            f"  Task:     {task.get('task_description', 'N/A')[:70]}{'...' if len(task.get('task_description', '')) > 70 else ''}"
        )
        if task.get("error_message"):
            print(
                f"  Error:    {task.get('error_message', '')[:70]}{'...' if len(task.get('error_message', '')) > 70 else ''}"
            )
        print()

    return 0


def cmd_metrics_export(args: argparse.Namespace) -> int:
    """Export metrics to a file."""
    import shutil
    from pathlib import Path

    repo_root = Path(args.repo_root).resolve()
    tracker = MetricsTracker(repo_root)

    if not tracker.metrics_file.exists():
        print("No metrics data available.")
        return 1

    output_file = (
        Path(args.output) if hasattr(args, "output") and args.output else Path("ninja_metrics.csv")
    )

    # Copy the metrics file
    shutil.copy(tracker.metrics_file, output_file)

    print(f"Metrics exported to: {output_file}")
    print(f"Total size: {output_file.stat().st_size} bytes")

    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(
        prog="ninja-cli-mcp",
        description="CLI interface for ninja-cli-mcp MCP tools. Supports any OpenRouter model.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # quick-task command
    quick = subparsers.add_parser(
        "quick-task",
        help="Execute a quick single-pass task",
    )
    quick.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    quick.add_argument(
        "--task",
        required=True,
        help="Task description",
    )
    quick.add_argument(
        "--context-paths",
        nargs="*",
        help="Paths to focus on",
    )
    quick.add_argument(
        "--allowed-globs",
        nargs="*",
        help="Allowed glob patterns",
    )
    quick.add_argument(
        "--deny-globs",
        nargs="*",
        help="Denied glob patterns",
    )
    quick.set_defaults(func=cmd_quick_task)

    # run-tests command
    tests = subparsers.add_parser(
        "run-tests",
        help="Run test commands",
    )
    tests.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    tests.add_argument(
        "--commands",
        nargs="+",
        required=True,
        help="Test commands to run",
    )
    tests.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout in seconds (default: 600)",
    )
    tests.set_defaults(func=cmd_run_tests)

    # execute-plan command
    plan = subparsers.add_parser(
        "execute-plan",
        help="Execute a plan from a JSON file",
    )
    plan.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    plan.add_argument(
        "--plan-file",
        required=True,
        help="Path to the plan JSON file",
    )
    plan.add_argument(
        "--full",
        action="store_true",
        help="Use full mode with review/test loops",
    )
    plan.set_defaults(func=cmd_execute_plan)

    # list-models command
    models = subparsers.add_parser(
        "list-models",
        help="List recommended OpenRouter models",
    )
    models.set_defaults(func=lambda args: cmd_list_models(args))

    # show-config command
    config = subparsers.add_parser(
        "show-config",
        help="Show current configuration",
    )
    config.set_defaults(func=lambda args: cmd_show_config(args))

    # metrics-summary command
    metrics_summary = subparsers.add_parser(
        "metrics-summary",
        help="Show metrics summary for a repository",
    )
    metrics_summary.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    metrics_summary.set_defaults(func=lambda args: cmd_metrics_summary(args))

    # metrics-recent command
    metrics_recent = subparsers.add_parser(
        "metrics-recent",
        help="Show recent task metrics",
    )
    metrics_recent.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    metrics_recent.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of recent tasks to show (default: 10)",
    )
    metrics_recent.set_defaults(func=lambda args: cmd_metrics_recent(args))

    # metrics-export command
    metrics_export = subparsers.add_parser(
        "metrics-export",
        help="Export metrics to a CSV file",
    )
    metrics_export.add_argument(
        "--repo-root",
        required=True,
        help="Absolute path to the repository root",
    )
    metrics_export.add_argument(
        "--output",
        help="Output file path (default: ninja_metrics.csv)",
    )
    metrics_export.set_defaults(func=lambda args: cmd_metrics_export(args))

    return parser


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        # Check if the function is async or sync
        func = args.func
        if asyncio.iscoroutinefunction(func):
            return asyncio.run(func(args))
        else:
            return func(args)
    except KeyboardInterrupt:
        print("\nInterrupted", file=sys.stderr)
        return 130
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
