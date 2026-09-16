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
from typing import TYPE_CHECKING, Any, cast

from pydantic import ValidationError

from ninja_agent.models import (
    DELEGATE_MIGRATION,
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentExecCommandRequest,
    AgentExecCommandResult,
    AgentJobsOverviewRequest,
    AgentJobsOverviewResult,
    AgentProcessesRequest,
    AgentProcessesResult,
    AgentReviewRequest,
    AgentReviewResult,
    AgentTailLogsRequest,
    AgentTailLogsResult,
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

    def error(self, message: str) -> None:
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

    return parser


def _wants_json(args: argparse.Namespace) -> bool:
    """Return True if --json was passed globally or per-subcommand."""
    return bool(getattr(args, "json", False))


def _fail(message: str) -> int:
    print(f"ninja-mcp agent: error: {message}", file=sys.stderr)
    return 1


def _dump(result: object) -> dict:
    return result.model_dump() if hasattr(result, "model_dump") else dict(result)  # type: ignore[arg-type]


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


def main(argv: list[str] | None = None) -> int:
    """Entry point for the agent CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    as_json = _wants_json(args)

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

    print(f"ninja-mcp agent: unknown command: {args.command}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
