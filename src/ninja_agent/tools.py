"""
MCP tool implementations for the Agent module.

The agent is AUTONOMOUS: it owns routine ops (guarded shell, log tails,
daemon/process snapshots, read-only job overviews) plus its own file
analysis and heuristic review. It knows nothing about coder / researcher /
secretary — no imports, no delegation. Code-writing is invoked directly via
coder_* tools by the central model, never through the agent.

One tool per capability (all ``agent_*``, no ``delegate_*``):

- ``agent_exec_command`` — guarded shell via the in-process runner
- ``agent_tail_logs`` — capped, redacted log tails
- ``agent_processes`` — read-only daemon + resource snapshot
- ``agent_jobs_overview`` — read-only job summary
- ``agent_analyze`` — own analysis: direct file reads + ast/grep
- ``agent_review`` — own heuristic static review (never writes)
"""

from __future__ import annotations

import ast
import fnmatch
from pathlib import Path
from typing import Any

from ninja_agent.models import (
    AgentAnalyzeRequest,
    AgentAnalyzeResult,
    AgentExecCommandRequest,
    AgentExecCommandResult,
    AgentJobsOverviewRequest,
    AgentJobsOverviewResult,
    AgentProcessesRequest,
    AgentProcessesResult,
    AgentReviewFinding,
    AgentReviewRequest,
    AgentReviewResult,
    AgentTailLogsRequest,
    AgentTailLogsResult,
)
from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored


logger = get_logger(__name__)

#: Cap on files inspected by :meth:`AgentToolExecutor.analyze`.
_MAX_ANALYZE_FILES = 200

#: Per-file read cap (chars) for analysis.
_MAX_ANALYZE_CHARS_PER_FILE = 20_000


class AgentToolExecutor:
    """Executor for autonomous agent MCP tools (no external agents)."""

    def __init__(self, runner: Any | None = None) -> None:
        """Initialize the agent tool executor.

        Args:
            runner: Injected runner executor (default: real ``RunnerToolExecutor``,
                imported lazily to keep module import cheap and cycle-free).
        """
        self._runner = runner

    def _get_runner(self) -> Any:
        """Lazily build and return the in-process runner executor."""
        if self._runner is None:
            from ninja_agent.runner import RunnerToolExecutor

            self._runner = RunnerToolExecutor()
        return self._runner

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def exec_command(
        self, request: AgentExecCommandRequest, client_id: str = "default"
    ) -> AgentExecCommandResult:
        """Run a guarded, non-interactive shell command via the runner.

        Args:
            request: Shell invocation request.
            client_id: Client identifier for rate limiting.

        Returns:
            Guarded execution result with capped, redacted output.
        """
        logger.info(f"Agent exec_command: {request.command[:80]} (client: {client_id})")
        result = await self._get_runner().run_command(
            request.command,
            cwd=request.cwd,
            repo_root=request.repo_root,
            timeout=request.timeout,
            allow_write=request.allow_write,
        )
        return AgentExecCommandResult(
            success=result.success,
            summary=result.summary,
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            truncated=result.truncated,
            safety_warnings=list(result.safety_warnings),
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def tail_logs(
        self, request: AgentTailLogsRequest, client_id: str = "default"
    ) -> AgentTailLogsResult:
        """Return capped, redacted log tails via the runner.

        Args:
            request: Log-tail request.
            client_id: Client identifier for rate limiting.

        Returns:
            Redacted tail result.
        """
        logger.info(f"Agent tail_logs: module={request.module} (client: {client_id})")
        result = await self._get_runner().tail_logs(
            module=request.module,
            level=request.level,
            limit=request.limit,
            session_id=request.session_id,
        )
        return AgentTailLogsResult(
            success=result.success,
            summary=result.summary,
            entries=list(result.entries),
            source=result.source,
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def processes(
        self, request: AgentProcessesRequest | None = None, client_id: str = "default"
    ) -> AgentProcessesResult:
        """Snapshot daemon statuses plus host resource stats (read-only).

        Args:
            request: Unused (no fields); kept for a uniform tool signature.
            client_id: Client identifier for rate limiting.

        Returns:
            Daemon map + resource stats; never mutates anything.
        """
        logger.info(f"Agent processes snapshot (client: {client_id})")
        result = await self._get_runner().processes()
        return AgentProcessesResult(
            success=result.success,
            summary=result.summary,
            daemons=dict(result.daemons),
            resources=dict(result.resources),
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def jobs_overview(
        self, request: AgentJobsOverviewRequest | None = None, client_id: str = "default"
    ) -> AgentJobsOverviewResult:
        """Summarize pending background jobs/tasks (read-only).

        Args:
            request: Job-overview request (limit).
            client_id: Client identifier for rate limiting.

        Returns:
            Read-only job summary list.
        """
        limit = request.limit if request is not None else 20
        logger.info(f"Agent jobs_overview (client: {client_id})")
        result = await self._get_runner().jobs_overview(limit=limit)
        return AgentJobsOverviewResult(
            success=result.success,
            summary=result.summary,
            jobs=list(result.jobs),
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def analyze(
        self, request: AgentAnalyzeRequest, client_id: str = "default"
    ) -> AgentAnalyzeResult:
        """Analyze a codebase with direct file reads + AST/grep heuristics.

        No secretary, no network: walks ``repo_root`` with ``include_patterns``,
        optionally narrows to ``focus`` matches, and summarizes Python files via
        ``ast`` (functions/classes/lines/syntax errors).

        Args:
            request: Analysis request.
            client_id: Client identifier for rate limiting.

        Returns:
            Aggregated analysis result.
        """
        logger.info(f"Analyzing codebase at {request.repo_root} (client: {client_id})")
        root = Path(request.repo_root)
        if not root.exists() or not root.is_dir():
            return AgentAnalyzeResult(
                success=False,
                summary=f"Analysis failed: repo_root does not exist: {request.repo_root}",
                findings=[],
                touched_paths=[],
            )
        try:
            candidates = self._collect_files(root, request.include_patterns)
            if request.focus:
                focus_lower = request.focus.lower()
                focused = [p for p in candidates if focus_lower in p.lower()]
                # Fall back to full candidate list when focus matches nothing,
                # but say so in the summary.
                narrowed = bool(focused)
                candidates = focused if focused else candidates
            else:
                narrowed = False

            candidates = candidates[:_MAX_ANALYZE_FILES]
            findings: list[str] = []
            touched: list[str] = []
            total_lines = 0
            total_funcs = 0
            total_classes = 0
            syntax_errors: list[str] = []

            for rel in candidates:
                touched.append(rel)
                path = root / rel
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")[
                        :_MAX_ANALYZE_CHARS_PER_FILE
                    ]
                except OSError:
                    continue
                total_lines += len(text.splitlines())
                if not rel.endswith(".py"):
                    continue
                try:
                    tree = ast.parse(text)
                except SyntaxError as e:
                    syntax_errors.append(f"{rel}:{e.lineno or '?'}: {e.msg}")
                    continue
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        total_funcs += 1
                    elif isinstance(node, ast.ClassDef):
                        total_classes += 1

            findings.append(f"Inspected {len(touched)} file(s), ~{total_lines} lines total.")
            py_count = sum(1 for p in touched if p.endswith(".py"))
            if py_count:
                findings.append(
                    f"Python: {py_count} file(s), {total_funcs} function(s), "
                    f"{total_classes} class(es)."
                )
            for err in syntax_errors[:10]:
                findings.append(f"Syntax error: {err}")

            summary = f"Codebase at {request.repo_root} analyzed."
            if request.focus:
                if narrowed:
                    summary += f" Focus '{request.focus}' matched {len(touched)} file(s)."
                else:
                    summary += f" Focus '{request.focus}' matched nothing; fell back to full scope."
            return AgentAnalyzeResult(
                success=True,
                summary=summary,
                findings=findings,
                touched_paths=touched[:50],
            )
        except Exception as e:
            logger.error(f"Agent analyze failed: {e}", exc_info=True)
            return AgentAnalyzeResult(
                success=False,
                summary=f"Analysis failed: {e}",
                findings=[],
                touched_paths=[],
            )

    def _collect_files(self, root: Path, patterns: list[str]) -> list[str]:
        """Collect repo-relative file paths matching any glob pattern.

        Args:
            root: Repository root.
            patterns: Glob patterns (``**``-style, matched with fnmatch).

        Returns:
            Sorted list of POSIX-style relative paths.
        """
        matched: set[str] = set()
        all_files: list[str] | None = None
        for pattern in patterns:
            # Fast path: pathlib glob handles ** patterns natively.
            try:
                for path in root.glob(pattern):
                    if path.is_file():
                        matched.add(path.relative_to(root).as_posix())
                continue
            except (OSError, ValueError):
                pass
            # Fallback: fnmatch over a full walk.
            if all_files is None:
                all_files = [p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()]
            matched.update(fnmatch.filter(all_files, pattern))
        return sorted(matched)

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def review(
        self, request: AgentReviewRequest, client_id: str = "default"
    ) -> AgentReviewResult:
        """Review files without modifying them.

        Deterministic heuristic static analysis only: long blocks, empty
        except handlers, missing top-level docstrings, syntax errors.
        No LLM enrichment — the agent must stay free of coder-package imports.

        Args:
            request: Review request.
            client_id: Client identifier for rate limiting.

        Returns:
            Review findings and a summary.
        """
        logger.info(f"Reviewing {len(request.file_paths)} files (client: {client_id})")
        findings: list[AgentReviewFinding] = []
        root = Path(request.repo_root)

        for rel in request.file_paths:
            if request.review_focus and request.review_focus.lower() not in rel.lower():
                findings.append(
                    AgentReviewFinding(
                        severity="info",
                        file_path=rel,
                        message=(f"Skipped: outside review focus '{request.review_focus}'."),
                    )
                )
                continue
            path = root / rel
            if not path.exists() or not path.is_file():
                findings.append(
                    AgentReviewFinding(
                        severity="warning",
                        file_path=rel,
                        message="File not found.",
                    )
                )
                continue

            text = path.read_text(encoding="utf-8", errors="ignore")

            # Basic line count
            lines = text.splitlines()
            findings.extend(self._check_long_lines(rel, lines))

            # Python-specific static checks
            if rel.endswith(".py"):
                findings.extend(self._check_python(rel, text))

        summary = (
            f"Reviewed {len(request.file_paths)} files, "
            f"found {len(findings)} finding(s). No files modified."
        )
        return AgentReviewResult(success=True, findings=findings, summary=summary)

    def _check_long_lines(self, rel: str, lines: list[str]) -> list[AgentReviewFinding]:
        """Flag functions that are too long (rough heuristic via line blocks)."""
        # Track blank-line-delimited function-ish blocks
        findings: list[AgentReviewFinding] = []
        block_start = 1
        for i, line in enumerate(lines, start=1):
            if not line.strip() or (i > block_start and line[:1].isalnum()):
                length = i - block_start
                if length > 80:
                    findings.append(
                        AgentReviewFinding(
                            severity="info",
                            file_path=rel,
                            line=block_start,
                            message=(
                                f"Long block of {length} lines (starting line {block_start}); "
                                "consider splitting for readability."
                            ),
                        )
                    )
                block_start = i + 1
        return findings

    def _check_python(self, rel: str, text: str) -> list[AgentReviewFinding]:
        """Run Python-specific heuristic checks."""
        findings: list[AgentReviewFinding] = []
        try:
            tree = ast.parse(text)
        except SyntaxError as e:
            findings.append(
                AgentReviewFinding(
                    severity="critical",
                    file_path=rel,
                    line=e.lineno,
                    message=f"Syntax error: {e.msg}",
                )
            )
            return findings

        for node in ast.walk(tree):
            # Empty except blocks
            if isinstance(node, ast.ExceptHandler):
                if not node.body:
                    findings.append(
                        AgentReviewFinding(
                            severity="warning",
                            file_path=rel,
                            line=getattr(node, "lineno", None),
                            message="Empty except block - hides errors silently.",
                        )
                    )
                elif isinstance(node.body[0], ast.Pass):
                    findings.append(
                        AgentReviewFinding(
                            severity="warning",
                            file_path=rel,
                            line=getattr(node, "lineno", None),
                            message="except block only contains 'pass' - consider logging.",
                        )
                    )

            # Top-level functions missing docstrings
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.body and not (
                    isinstance(node.body[0], ast.Expr)
                    and isinstance(node.body[0].value, ast.Constant)
                    and isinstance(node.body[0].value.value, str)
                ):
                    if not any(
                        isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                        for parent in _parents_of(tree, node)
                    ):
                        findings.append(
                            AgentReviewFinding(
                                severity="info",
                                file_path=rel,
                                line=node.lineno,
                                message=f"Function '{node.name}' has no docstring.",
                            )
                        )

        return findings


def _parents_of(tree: ast.AST, target: ast.AST) -> list[ast.AST]:
    """Return the parent nodes of a target within the tree."""
    parents: list[ast.AST] = []
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            if child is target:
                parents.append(node)
    return parents
