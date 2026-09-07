"""CLI for ninja-agent orchestrator (plan, analyze, delegate, review, run).

Usage::

    ninja-mcp agent plan --task "..." --repo-root .
    ninja-mcp agent analyze --repo-root . [--focus auth]
    ninja-mcp agent delegate --to coder --subtask "..." --repo-root .
    ninja-mcp agent review --repo-root . --files a.py b.py
    ninja-mcp agent run --task "..." --repo-root .

``run`` composes plan -> delegate -> review via :class:`AgentToolExecutor`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import TYPE_CHECKING, Any, cast


if TYPE_CHECKING:
    from collections.abc import Coroutine

from pydantic import ValidationError

from ninja_agent.models import (
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentDelegateRequest,
    AgentDelegateResult,
    AgentPlanRequest,
    AgentPlanResult,
    AgentReviewRequest,
    AgentReviewResult,
)
from ninja_agent.tools import AgentToolExecutor


def build_parser() -> argparse.ArgumentParser:
    """Build the agent CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="ninja-mcp agent",
        description="Ninja Agent orchestrator: plan, analyze, delegate, review.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # plan
    plan_p = subparsers.add_parser("plan", help="Decompose a task into an execution plan")
    plan_p.add_argument("--task", required=True, help="High-level task description")
    plan_p.add_argument("--repo-root", required=True, help="Repository root path")
    plan_p.add_argument(
        "--context",
        nargs="*",
        default=[],
        help="Paths relevant to the task (repeatable / space-separated)",
    )
    plan_p.add_argument("--steps", type=int, default=None, help="Optional hint for number of steps")
    plan_p.add_argument("--json", action="store_true", help="Output JSON format")

    # analyze
    analyze_p = subparsers.add_parser("analyze", help="Analyze a codebase")
    analyze_p.add_argument("--repo-root", required=True, help="Repository root path")
    analyze_p.add_argument("--focus", default=None, help="Focus area or search term")
    analyze_p.add_argument("--json", action="store_true", help="Output JSON format")

    # delegate
    delegate_p = subparsers.add_parser("delegate", help="Delegate a subtask to a sub-agent")
    delegate_p.add_argument(
        "--to",
        dest="delegate_to",
        required=True,
        choices=["coder", "researcher", "secretary"],
        help="Sub-agent to invoke",
    )
    delegate_p.add_argument("--subtask", required=True, help="Subtask description")
    delegate_p.add_argument("--repo-root", required=True, help="Repository root path")
    delegate_p.add_argument(
        "--context",
        nargs="*",
        default=[],
        help="Paths relevant to the subtask",
    )
    delegate_p.add_argument(
        "--model-class",
        dest="model_class",
        default=None,
        choices=["smart", "balanced", "fast"],
        help="Model tier for the coder sub-agent (default: smart)",
    )
    delegate_p.add_argument("--json", action="store_true", help="Output JSON format")

    # review
    review_p = subparsers.add_parser("review", help="Review files without modifying them")
    review_p.add_argument("--repo-root", required=True, help="Repository root path")
    review_p.add_argument(
        "--files", nargs="+", required=True, help="Files to review (relative to repo_root)"
    )
    review_p.add_argument("--focus", default=None, help="Optional area to focus review on")
    review_p.add_argument("--json", action="store_true", help="Output JSON format")

    # Task runner: composition of plan, delegate, and review steps.
    run_p = subparsers.add_parser("run", help="Compose plan -> delegate -> review for a task")
    run_p.add_argument("--task", required=True, help="High-level task description")
    run_p.add_argument("--repo-root", required=True, help="Repository root path")
    run_p.add_argument(
        "--context",
        nargs="*",
        default=[],
        help="Paths relevant to the task (also used as review targets)",
    )
    run_p.add_argument("--steps", type=int, default=None, help="Optional hint for number of steps")
    run_p.add_argument("--json", action="store_true", help="Output JSON format")

    return parser


def _wants_json(args: argparse.Namespace) -> bool:
    """Return True if --json was passed globally or per-subcommand."""
    return bool(getattr(args, "json", False))


def _fail(message: str) -> int:
    print(f"ninja-mcp agent: error: {message}", file=sys.stderr)
    return 1


def _print_plan(result: object, as_json: bool) -> None:
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if as_json:
        print(json.dumps(data, indent=2))
        return
    steps = data.get("plan", []) if isinstance(data, dict) else []
    print(
        f"Plan ({len(steps)} steps): {data.get('reasoning', '') if isinstance(data, dict) else ''}"
    )
    for i, step in enumerate(steps):
        deps = ",".join(str(d) for d in step.get("dependencies", []))
        suffix = f" [depends on {deps}]" if deps else ""
        print(f"  {i}. [{step.get('delegate_to')}] {step.get('title')}{suffix}")
        print(f"     {step.get('description')}")


def _print_analyze(result: object, as_json: bool) -> None:
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", "") if isinstance(data, dict) else "")
    for finding in data.get("findings", []) if isinstance(data, dict) else []:
        print(f"  - {finding}")
    touched = data.get("touched_paths", []) if isinstance(data, dict) else []
    if touched:
        print(f"Touched paths ({len(touched)}):")
        for path in touched:
            print(f"  - {path}")


def _print_delegate(result: object, as_json: bool) -> None:
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(f"[{data.get('delegate_to')}] {data.get('summary')}" if isinstance(data, dict) else "")
    if isinstance(data, dict) and data.get("raw_output"):
        print(data["raw_output"])


def _print_review(result: object, as_json: bool) -> None:
    data = result.model_dump() if hasattr(result, "model_dump") else result
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", "") if isinstance(data, dict) else "")
    for finding in data.get("findings", []) if isinstance(data, dict) else []:
        line = f":{finding.get('line')}" if finding.get("line") is not None else ""
        print(
            f"  [{finding.get('severity')}] {finding.get('file_path')}{line}: {finding.get('message')}"
        )


def _cmd_plan(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentPlanRequest(
            task=args.task,
            repo_root=args.repo_root,
            context_paths=list(args.context or []),
            steps_requested=args.steps,
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast("Coroutine[Any, Any, AgentPlanResult]", AgentToolExecutor().plan(request))
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_plan(result, as_json)
        return _fail(result.reasoning or "planning failed")
    _print_plan(result, as_json)
    return 0


def _cmd_analyze(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentAnalyzeRequest(repo_root=args.repo_root, focus=args.focus)
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast("Coroutine[Any, Any, AgentAnalyzeResult]", AgentToolExecutor().analyze(request))
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_analyze(result, as_json)
        return _fail(result.summary)
    _print_analyze(result, as_json)
    return 0


def _cmd_delegate(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentDelegateRequest(
            subtask=args.subtask,
            repo_root=args.repo_root,
            delegate_to=args.delegate_to,
            context_paths=list(args.context or []),
            model_class=args.model_class,
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast("Coroutine[Any, Any, AgentDelegateResult]", AgentToolExecutor().delegate(request))
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_delegate(result, as_json)
        return _fail(result.summary)
    _print_delegate(result, as_json)
    return 0


def _cmd_review(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentReviewRequest(
            repo_root=args.repo_root,
            file_paths=list(args.files),
            review_focus=args.focus,
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast("Coroutine[Any, Any, AgentReviewResult]", AgentToolExecutor().review(request))
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_review(result, as_json)
        return _fail(result.summary)
    _print_review(result, as_json)
    return 0


async def _execute_run_pipeline(
    executor: AgentToolExecutor,
    task: str,
    repo_root: str,
    context: list[str],
    steps: int | None,
) -> tuple[object, list[object], object | None]:
    """Run plan -> delegate -> review composition. Fail-fast on plan failure."""
    plan_request = AgentPlanRequest(
        task=task,
        repo_root=repo_root,
        context_paths=list(context),
        steps_requested=steps,
    )
    plan_result = await executor.plan(plan_request)
    if not plan_result.success:
        raise RuntimeError(plan_result.reasoning or "planning failed")

    delegate_results: list[object] = []
    for step in plan_result.plan:
        if step.delegate_to in ("coder", "researcher", "secretary"):
            delegate_request = AgentDelegateRequest(
                subtask=f"{step.title}: {step.description}",
                repo_root=repo_root,
                delegate_to=step.delegate_to,  # type: ignore[arg-type]
                context_paths=list(context),
            )
            delegate_results.append(await executor.delegate(delegate_request))

    review_result: object | None = None
    if context:
        review_result = await executor.review(
            AgentReviewRequest(repo_root=repo_root, file_paths=list(context))
        )

    return plan_result, delegate_results, review_result


def _cmd_run(args: argparse.Namespace, as_json: bool) -> int:
    context = list(args.context or [])
    try:
        plan_result, delegate_results, review_result = asyncio.run(
            _execute_run_pipeline(
                AgentToolExecutor(),
                task=args.task,
                repo_root=args.repo_root,
                context=context,
                steps=args.steps,
            )
        )
    except ValidationError as exc:
        return _fail(str(exc))
    except Exception as exc:
        return _fail(str(exc))

    failed = [r for r in delegate_results if not getattr(r, "success", True)]
    if failed:
        _print_run(plan_result, delegate_results, review_result, as_json)
        details = "; ".join(getattr(r, "summary", "delegation failed") for r in failed)
        return _fail(details)

    _print_run(plan_result, delegate_results, review_result, as_json)
    return 0


def _print_run(
    plan_result: object,
    delegate_results: list[object],
    review_result: object | None,
    as_json: bool,
) -> None:
    if as_json:
        payload = {
            "plan": plan_result.model_dump() if hasattr(plan_result, "model_dump") else plan_result,
            "delegations": [
                r.model_dump() if hasattr(r, "model_dump") else r for r in delegate_results
            ],
            "review": (
                review_result.model_dump()
                if review_result is not None and hasattr(review_result, "model_dump")
                else review_result
            ),
        }
        print(json.dumps(payload, indent=2))
        return
    print("=== Plan ===")
    _print_plan(plan_result, False)
    print("=== Delegations ===")
    if not delegate_results:
        print("  (no delegatable steps)")
    for result in delegate_results:
        _print_delegate(result, False)
    print("=== Review ===")
    if review_result is None:
        print("  (skipped: no --context files to review)")
    else:
        _print_review(review_result, False)


def main(argv: list[str] | None = None) -> int:
    """Entry point for the agent CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = _wants_json(args)

    if args.command == "plan":
        return _cmd_plan(args, as_json)
    if args.command == "analyze":
        return _cmd_analyze(args, as_json)
    if args.command == "delegate":
        return _cmd_delegate(args, as_json)
    if args.command == "review":
        return _cmd_review(args, as_json)
    if args.command == "run":
        return _cmd_run(args, as_json)

    print(f"ninja-mcp agent: unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
