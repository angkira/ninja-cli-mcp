"""CLI for the autonomous ninja-agent (exec-command, tail-logs, processes, jobs, analyze, review).

Usage::

    ninja-mcp agent exec-command --command "pytest -q" --repo-root .
    ninja-mcp agent tail-logs --module coder --limit 50
    ninja-mcp agent processes
    ninja-mcp agent jobs-overview --limit 20
    ninja-mcp agent analyze --repo-root . [--focus auth]
    ninja-mcp agent review --repo-root . --files a.py b.py

The agent is autonomous: it never delegates to coder/researcher/secretary.
For code-writing call coder directly via coder_* tools, not through the agent.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, cast

from pydantic import BaseModel, ValidationError

from ninja_agent.models import (
    DELEGATE_MIGRATION,
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentDistillLogsRequest,
    AgentDistillLogsResult,
    AgentExecCommandRequest,
    AgentExecCommandResult,
    AgentExecPipelineRequest,
    AgentExecPipelineResult,
    AgentJobsOverviewRequest,
    AgentJobsOverviewResult,
    AgentProcessesRequest,
    AgentProcessesResult,
    AgentReviewRequest,
    AgentReviewResult,
    AgentRunAndDiagnoseRequest,
    AgentRunAndDiagnoseResult,
    AgentTailLogsRequest,
    AgentTailLogsResult,
    PipelineStep,
)
from ninja_agent.tools import AgentToolExecutor


if TYPE_CHECKING:
    from collections.abc import Coroutine


#: Removed commands that now map to the migration hint.
_REMOVED_COMMANDS = frozenset(
    {
        "delegate",
        "delegate-coder",
        "delegate-researcher",
        "delegate-secretary",
        "delegate-runner",
        "delegate-git",
        "runner",
        "plan",
        "run",
    }
)


class _AgentParser(argparse.ArgumentParser):
    """Argument parser that maps removed commands to migration hints."""

    def error(self, message: str) -> NoReturn:
        for removed in sorted(_REMOVED_COMMANDS):
            if f"'{removed}'" in message:
                self.exit(2, f"ninja-mcp agent: error: {DELEGATE_MIGRATION}\n{message}\n")
        super().error(message)


def build_parser() -> argparse.ArgumentParser:
    """Build the agent CLI argument parser."""
    parser = _AgentParser(
        prog="ninja-mcp agent",
        description=(
            "Autonomous Ninja Agent: shell, logs, processes, jobs, analyze, review. "
            "Never delegates to coder/researcher/secretary."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--json", action="store_true", help="Output JSON format")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # exec-command
    exec_p = subparsers.add_parser("exec-command", help="Run a guarded shell command")
    exec_p.add_argument(
        "--command", dest="shell_command", required=True, help="Shell command to execute"
    )
    exec_p.add_argument("--repo-root", required=True, help="Repository root path")
    exec_p.add_argument("--cwd", default=None, help="Working directory (defaults to repo_root)")
    exec_p.add_argument("--timeout", type=int, default=120, help="Timeout in seconds")
    exec_p.add_argument("--allow-write", action="store_true", help="Allow file-mutating commands")
    exec_p.add_argument("--json", action="store_true", help="Output JSON format")

    # tail-logs
    logs_p = subparsers.add_parser("tail-logs", help="Show capped, redacted log tails")
    logs_p.add_argument("--module", default=None, help="Daemon/module name (e.g. 'coder')")
    logs_p.add_argument("--level", default=None, help="Level filter (INFO/ERROR/...)")
    logs_p.add_argument("--limit", type=int, default=50, help="Max entries (capped at 200)")
    logs_p.add_argument("--session-id", dest="session_id", default=None)
    logs_p.add_argument("--json", action="store_true", help="Output JSON format")

    # processes
    procs_p = subparsers.add_parser("processes", help="Daemon + resource snapshot (read-only)")
    procs_p.add_argument("--json", action="store_true", help="Output JSON format")

    # jobs-overview
    jobs_p = subparsers.add_parser("jobs-overview", help="Background-job overview (read-only)")
    jobs_p.add_argument("--limit", type=int, default=20, help="Max jobs to include")
    jobs_p.add_argument("--json", action="store_true", help="Output JSON format")

    # analyze
    analyze_p = subparsers.add_parser("analyze", help="Analyze a codebase")
    analyze_p.add_argument("--repo-root", required=True, help="Repository root path")
    analyze_p.add_argument("--focus", default=None, help="Focus area or search term")
    analyze_p.add_argument(
        "--include-patterns",
        nargs="*",
        default=None,
        help="Glob patterns of files to include",
    )
    analyze_p.add_argument("--json", action="store_true", help="Output JSON format")

    # review
    review_p = subparsers.add_parser("review", help="Review files without modifying them")
    review_p.add_argument("--repo-root", required=True, help="Repository root path")
    review_p.add_argument(
        "--files", nargs="+", required=True, help="Files to review (relative to repo_root)"
    )
    review_p.add_argument("--focus", default=None, help="Optional area to focus review on")
    review_p.add_argument("--json", action="store_true", help="Output JSON format")

    # run-and-diagnose
    diag_p = subparsers.add_parser(
        "run-and-diagnose", help="Run a command and distill diagnostic outcomes"
    )
    diag_p.add_argument(
        "--command", dest="shell_command", required=True, help="Shell command to execute"
    )
    diag_p.add_argument("--repo-root", default=".", help="Repository root path")
    diag_p.add_argument("--cwd", default=None, help="Working directory (defaults to repo_root)")
    diag_p.add_argument("--timeout", type=int, default=300, help="Timeout in seconds")
    diag_p.add_argument("--allow-write", action="store_true", help="Allow file-mutating commands")
    diag_p.add_argument(
        "--framework-hint", default="auto", help="Optional framework hint (default: 'auto')"
    )
    diag_p.add_argument("--json", action="store_true", help="Output JSON format")

    # pipeline
    pipe_p = subparsers.add_parser("pipeline", help="Execute an ordered sequence of shell commands")
    pipe_p.add_argument(
        "--steps",
        required=True,
        help="JSON string or path to JSON file containing list of step dicts",
    )
    pipe_p.add_argument("--repo-root", default=".", help="Repository root path")
    pipe_p.add_argument("--cwd", default=None, help="Working directory (defaults to repo_root)")
    pipe_p.add_argument(
        "--fail-fast",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Halt on first failing step (default: True)",
    )
    pipe_p.add_argument("--json", action="store_true", help="Output JSON format")

    # distill-logs
    distill_p = subparsers.add_parser(
        "distill-logs", help="Tail and distill logs into clusters and tracebacks"
    )
    distill_p.add_argument("--module", default=None, help="Daemon/module name (e.g. 'coder')")
    distill_p.add_argument("--level", default=None, help="Level filter (INFO/ERROR/...)")
    distill_p.add_argument("--limit", type=int, default=200, help="Max entries (capped at 200)")
    distill_p.add_argument(
        "--session-id", dest="session_id", default=None, help="Optional session filter"
    )
    distill_p.add_argument("--json", action="store_true", help="Output JSON format")

    return parser


def _wants_json(args: argparse.Namespace) -> bool:
    """Return True if --json was passed globally or per-subcommand."""
    return bool(getattr(args, "json", False))


def _fail(message: str) -> int:
    print(f"ninja-mcp agent: error: {message}", file=sys.stderr)
    return 1


def _dump(result: object) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        return result.model_dump()
    if isinstance(result, dict):
        return result
    return dict(cast("Any", result))


def _print_exec_command(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    if data.get("stdout"):
        print(data["stdout"])
    if data.get("stderr"):
        print(data["stderr"], file=sys.stderr)


def _print_tail_logs(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for entry in data.get("entries", []):
        print(f"  {entry}")


def _print_processes(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for name, info in (data.get("daemons", {}) or {}).items():
        print(f"  - {name}: {info}")


def _print_jobs(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for job in data.get("jobs", []):
        print(f"  - {job}")


def _print_analyze(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for finding in data.get("findings", []):
        print(f"  - {finding}")
    touched = data.get("touched_paths", [])
    if touched:
        print(f"Touched paths ({len(touched)}):")
        for path in touched:
            print(f"  - {path}")


def _print_review(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for finding in data.get("findings", []):
        line = f":{finding.get('line')}" if finding.get("line") is not None else ""
        print(
            f"  [{finding.get('severity')}] {finding.get('file_path')}{line}: {finding.get('message')}"
        )


def _print_run_and_diagnose(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    failures = data.get("failures", [])
    if failures:
        print(f"Failures / Diagnostics ({len(failures)}):")
        for f in failures:
            loc = ""
            if f.get("file_path"):
                loc = f.get("file_path")
                if f.get("line_number") is not None:
                    loc += f":{f.get('line_number')}"
            target = f.get("test_name") or loc or "Diagnostic"
            msg = f.get("error_message", "")
            print(f"  - [{target}] {msg}")
            if f.get("traceback"):
                for tb_line in f["traceback"].strip().splitlines():
                    print(f"      {tb_line}")
    condensed = data.get("condensed_output", "")
    if condensed and not failures:
        print(condensed)


def _print_pipeline(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    for idx, s in enumerate(data.get("steps", []), start=1):
        if s.get("skipped"):
            status = "[SKIPPED]"
        elif s.get("success"):
            status = "[PASS]"
        else:
            status = "[FAIL]"
        name = s.get("name") or s.get("command") or f"step {idx}"
        duration = s.get("duration_seconds", 0.0)
        print(f"  {status} {name} ({duration:.2f}s)")
        if not s.get("success") and not s.get("skipped") and s.get("summary"):
            print(f"         {s.get('summary')}")


def _print_distill_logs(result: object, as_json: bool) -> None:
    data = _dump(result)
    if as_json:
        print(json.dumps(data, indent=2))
        return
    print(data.get("summary", ""))
    clusters = data.get("clusters", [])
    if clusters:
        print(f"Log Clusters ({len(clusters)}):")
        for c in clusters:
            count = c.get("count", 0)
            level = c.get("level", "UNKNOWN")
            pattern = c.get("pattern", "")
            sample = c.get("sample_line", "")
            print(f"  [{count}x] [{level}] {pattern}")
            if sample and sample != pattern:
                print(f"       Sample: {sample}")
    isolated_errors = data.get("isolated_errors", [])
    if isolated_errors:
        print(f"Isolated Error Blocks ({len(isolated_errors)}):")
        for idx, err in enumerate(isolated_errors, start=1):
            print(f"  --- Error Block #{idx} ---")
            for line in err.strip().splitlines():
                print(f"  {line}")


def _cmd_exec_command(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentExecCommandRequest(
            command=args.shell_command,
            repo_root=args.repo_root,
            cwd=args.cwd,
            timeout=int(args.timeout or 120),
            allow_write=bool(args.allow_write),
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentExecCommandResult]",
                AgentToolExecutor().exec_command(request),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_exec_command(result, as_json)
        return _fail(result.summary)
    _print_exec_command(result, as_json)
    return 0


def _cmd_tail_logs(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentTailLogsRequest(
            module=args.module,
            level=args.level,
            limit=int(args.limit or 50),
            session_id=args.session_id,
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast("Coroutine[Any, Any, AgentTailLogsResult]", AgentToolExecutor().tail_logs(request))
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_tail_logs(result, as_json)
        return _fail(result.summary)
    _print_tail_logs(result, as_json)
    return 0


def _cmd_processes(args: argparse.Namespace, as_json: bool) -> int:
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentProcessesResult]",
                AgentToolExecutor().processes(AgentProcessesRequest()),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_processes(result, as_json)
        return _fail(result.summary)
    _print_processes(result, as_json)
    return 0


def _cmd_jobs_overview(args: argparse.Namespace, as_json: bool) -> int:
    try:
        request = AgentJobsOverviewRequest(limit=int(args.limit or 20))
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentJobsOverviewResult]",
                AgentToolExecutor().jobs_overview(request),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    if not result.success:
        _print_jobs(result, as_json)
        return _fail(result.summary)
    _print_jobs(result, as_json)
    return 0


def _cmd_analyze(args: argparse.Namespace, as_json: bool) -> int:
    try:
        kwargs: dict[str, Any] = {"repo_root": args.repo_root, "focus": args.focus}
        if args.include_patterns:
            kwargs["include_patterns"] = list(args.include_patterns)
        request = AgentAnalyzeRequest(**kwargs)
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


def _cmd_run_and_diagnose(executor: Any, args: Any = None) -> int:
    if isinstance(executor, argparse.Namespace):
        args = executor
        executor = AgentToolExecutor()
    as_json = _wants_json(args)
    hint = (
        args.framework_hint
        if getattr(args, "framework_hint", None) and args.framework_hint != "auto"
        else None
    )
    cmd = (
        getattr(args, "shell_command", None)
        or (args.command if getattr(args, "command", None) != "run-and-diagnose" else None)
        or ""
    )
    try:
        request = AgentRunAndDiagnoseRequest(
            command=cmd,
            repo_root=getattr(args, "repo_root", ".") or ".",
            cwd=getattr(args, "cwd", None),
            timeout=int(getattr(args, "timeout", 300) or 300),
            allow_write=bool(getattr(args, "allow_write", False)),
            framework_hint=hint,
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentRunAndDiagnoseResult]",
                executor.run_and_diagnose(request),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    _print_run_and_diagnose(result, as_json)
    return 0 if result.success else 1


def _cmd_pipeline(executor: Any, args: Any = None) -> int:
    if isinstance(executor, argparse.Namespace):
        args = executor
        executor = AgentToolExecutor()
    as_json = _wants_json(args)
    steps_raw = (getattr(args, "steps", None) or "").strip()
    steps_data = None
    steps_path = Path(steps_raw)
    if steps_path.is_file():
        try:
            steps_data = json.loads(steps_path.read_text(encoding="utf-8"))
        except Exception as exc:
            return _fail(f"Failed to read steps file: {exc}")
    else:
        try:
            steps_data = json.loads(steps_raw)
        except json.JSONDecodeError as exc:
            return _fail(f"Invalid JSON for --steps: {exc}")
    if not isinstance(steps_data, list):
        return _fail("--steps must be a JSON list of step objects")
    try:
        steps = [
            PipelineStep(**s) if isinstance(s, dict) else PipelineStep(command=str(s))
            for s in steps_data
        ]
        request = AgentExecPipelineRequest(
            steps=steps,
            repo_root=getattr(args, "repo_root", ".") or ".",
            cwd=getattr(args, "cwd", None),
            fail_fast=bool(getattr(args, "fail_fast", True)),
        )
    except (ValidationError, TypeError, ValueError) as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentExecPipelineResult]",
                executor.exec_pipeline(request),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    _print_pipeline(result, as_json)
    return 0 if result.success else 1


def _cmd_distill_logs(executor: Any, args: Any = None) -> int:
    if isinstance(executor, argparse.Namespace):
        args = executor
        executor = AgentToolExecutor()
    as_json = _wants_json(args)
    try:
        request = AgentDistillLogsRequest(
            module=getattr(args, "module", None),
            level=getattr(args, "level", None),
            limit=int(getattr(args, "limit", 200) or 200),
            session_id=getattr(args, "session_id", None),
        )
    except ValidationError as exc:
        return _fail(str(exc))
    try:
        result = asyncio.run(
            cast(
                "Coroutine[Any, Any, AgentDistillLogsResult]",
                executor.distill_logs(request),
            )
        )
    except Exception as exc:
        return _fail(str(exc))
    _print_distill_logs(result, as_json)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point for the agent CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = _wants_json(args)
    executor = AgentToolExecutor()

    if args.command == "exec-command":
        return _cmd_exec_command(args, as_json)
    if args.command == "tail-logs":
        return _cmd_tail_logs(args, as_json)
    if args.command == "processes":
        return _cmd_processes(args, as_json)
    if args.command == "jobs-overview":
        return _cmd_jobs_overview(args, as_json)
    if args.command == "analyze":
        return _cmd_analyze(args, as_json)
    if args.command == "review":
        return _cmd_review(args, as_json)
    if args.command == "run-and-diagnose":
        return _cmd_run_and_diagnose(executor, args)
    if args.command == "pipeline":
        return _cmd_pipeline(executor, args)
    if args.command == "distill-logs":
        return _cmd_distill_logs(executor, args)

    print(f"ninja-mcp agent: unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
