"""In-process runner sub-agent: routine ops for the central model.

The runner executes low-risk routine work that would otherwise burn central
model attention: guarded shell commands, log tails, daemon/process status,
and read-only job overviews. It is a plain library (no port, no MCP server)
living next to the agent orchestrator — it becomes a separate
``ninja_runner`` package with its own server only if/when isolation or
independent scaling is needed.

Rationale for placement (``src/ninja_agent/runner.py`` vs ``src/ninja_runner/``):
secretary/coder/researcher each live in their own top-level package because
they each run a dedicated MCP server/daemon on its own port. The runner must
NOT get a port on this stage (explicit task constraint), so creating a new
top-level distribution unit would add packaging surface (pyproject packages,
entry points, daemon wiring) for zero benefit. Co-location keeps imports
lazy (no cycle: runner imports only ``ninja_common``) and lets
``AgentToolExecutor`` share one in-process runner instance.

When to call the runner (guidance for the central model):
  CALL for routine ops: shell commands (tests, git status, ls, builds),
  tails of coder/daemon logs, daemon/process health, pending-job overviews,
  light file reconciliations (diff --stat, checksums, line counts).
  DO NOT call for: writing new code (→ coder), web research (→ researcher),
  codebase analysis/reviews (→ secretary / agent review).

Guards (enforced in code, not just docs):
  - ``run_command``: default timeout 120 s, stdout+stderr cap, stdin=DEVNULL
    (no interactivity), denylist of destructive patterns, read-only by
    default — write-looking commands require ``allow_write=True`` plus an
    opt-in ``check_safety`` dry-run note (``create_tag=False``, never mutates).
  - ``tail_logs``: capped at 200 lines/entries, secrets redacted with the same
    patterns as ``TaskLogger._redact_sensitive_data``.
  - ``processes`` / ``jobs_overview``: strictly read-only.
"""

from __future__ import annotations

import asyncio
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable

from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored


logger = get_logger(__name__)

#: Default shell timeout (seconds) when the caller does not specify one.
DEFAULT_COMMAND_TIMEOUT = 120

#: Hard cap for captured command output (chars) — the rest is truncated.
MAX_OUTPUT_CHARS = 20_000

#: Hard cap for log tails (lines/entries).
MAX_LOG_LINES = 200

#: Minimal denylist of unambiguously destructive shell patterns.
#: This is defense-in-depth, not a sandbox: the runner is in-process and the
#: caller is the trusted orchestrator, so the list blocks accidents, not APTs.
DENY_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\brm\s+[^|;&]*-r\s*f?\s*/(\s|$|;)"),  # rm -rf /
    re.compile(r"\brm\s+[^|;&]*-f\s+r?\s*/(\s|$|;)"),  # rm -fr /
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;?\s*:"),  # fork bomb
    re.compile(r"\bmkfs(\.|s?\s)"),  # mkfs.*
    re.compile(r"\bdd\b[^|;&]*\bof=/dev/"),  # dd of=/dev/...
    re.compile(r">\s*/dev/(sd|hd|nvme|vd)[a-z]*"),  # raw disk overwrite
    re.compile(r"\b(shutdown|reboot|halt|poweroff|init\s+0|init\s+6)\b"),
)

#: Heuristic for "this command probably mutates files/state". Anything
#: matching requires ``allow_write=True``; everything else runs freely.
WRITE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(^|[|;&\s])(mkdir|touch|rm |rmdir|mv |cp |ln |tee\b|install\b)"),
    re.compile(
        r"(^|[|;&\s])git\s+(add|commit|push|checkout|switch|restore|apply|"
        r"clean|reset|revert|rebase|merge|tag|branch|stash)"
    ),
    re.compile(r"(^|[|;&\s])(sed\s+[^|;&]*-i|awk\s+[^|;&]*>\s*\S|chmod|chown)"),
    re.compile(r"(>>?)\s*\S"),  # shell redirection into a file
    re.compile(
        r"(^|[|;&\s])(pip|pip3|uv|npm|yarn|pnpm|poetry)\s+(install|add|"
        r"remove|uninstall)"
    ),
    re.compile(
        r"(^|[|;&\s])(docker|podman)\s+(run|exec|build|push|rm|rmi|"
        r"compose)"
    ),
)

#: Redaction patterns — mirrors ``TaskLogger._redact_sensitive_data`` so log
#: tails and command output redact the same secret shapes.
REDACT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(sk-[a-zA-Z0-9_-]{20,})"), "[REDACTED_API_KEY]"),
    (re.compile(r"(api[_-]key[a-zA-Z0-9]{10,})", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"(token[a-zA-Z0-9]{10,})", re.IGNORECASE), "[REDACTED_TOKEN]"),
    (
        re.compile(
            r'(["\']?(password|passwd|pwd)["\']?\s*[:=]\s*["\'][^"\']{3,}["\'])',
            re.IGNORECASE,
        ),
        "[REDACTED_PASSWORD]",
    ),
    (
        re.compile(
            r'(["\']?(secret|key)["\']?\s*[:=]\s*["\'][^"\']{3,}["\'])',
            re.IGNORECASE,
        ),
        "[REDACTED_SECRET]",
    ),
    (
        re.compile(r"([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})"),
        "[REDACTED_EMAIL]",
    ),
)


def redact_text(text: str) -> str:
    """Redact secret-like shapes from free text.

    Args:
        text: Raw text (log line, command output).

    Returns:
        Text with secrets replaced by ``[REDACTED_*]`` markers.
    """
    redacted = text
    for pattern, replacement in REDACT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def looks_like_write(cmd: str) -> bool:
    """Heuristically decide whether a shell command mutates state.

    Args:
        cmd: Shell command string.

    Returns:
        True when the command looks like it writes files/state.
    """
    lowered = cmd.lower()
    return any(p.search(cmd) or p.search(lowered) for p in WRITE_PATTERNS)


def find_denied(cmd: str) -> str | None:
    """Return the reason a command is denied, or None when it is allowed.

    Args:
        cmd: Shell command string.

    Returns:
        Human-readable denial reason, or None if no denylist pattern hits.
    """
    for pattern in DENY_PATTERNS:
        if pattern.search(cmd):
            return f"denylisted destructive pattern: `{pattern.pattern}`"
    return None


@dataclass
class RunnerCommandResult:
    """Outcome of a guarded shell invocation."""

    success: bool
    summary: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    truncated: bool = False
    safety_warnings: list[str] = field(default_factory=list)


@dataclass
class RunnerLogsResult:
    """Outcome of a log-tail query."""

    success: bool
    summary: str
    entries: list[str] = field(default_factory=list)
    source: str = ""


@dataclass
class RunnerProcessesResult:
    """Read-only daemon + host resource snapshot."""

    success: bool
    summary: str
    daemons: dict[str, Any] = field(default_factory=dict)
    resources: dict[str, Any] = field(default_factory=dict)


@dataclass
class RunnerJobsResult:
    """Read-only overview of pending background jobs/tasks."""

    success: bool
    summary: str
    jobs: list[dict[str, Any]] = field(default_factory=list)


class RunnerToolExecutor:
    """In-process executor for routine ops (the "runner" guy).

    All collaborators are injectable for unit tests; defaults wire the real
    ``ninja_common`` bricks lazily so importing this module stays cheap and
    cycle-free.
    """

    def __init__(
        self,
        *,
        daemon_factory: Callable[[], Any] | None = None,
        resource_monitor_factory: Callable[[], Any] | None = None,
        structured_log_query: Callable[..., list[dict[str, Any]]] | None = None,
        jobs_lister: Callable[..., Any] | None = None,
        safety_checker: Callable[..., dict[str, Any]] | None = None,
        subprocess_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    ) -> None:
        """Initialize with injectable collaborators.

        Args:
            daemon_factory: Builds a ``DaemonManager`` (default: real one).
            resource_monitor_factory: Builds a resource monitor.
            structured_log_query: ``(module, level, limit, session_id)`` query fn.
            jobs_lister: Async ``(limit)`` fn returning job summaries.
            safety_checker: ``check_safety``-compatible callable for dry-runs.
            subprocess_runner: ``subprocess.run``-compatible callable (tests).
        """
        self._daemon_factory = daemon_factory
        self._resource_monitor_factory = resource_monitor_factory
        self._structured_log_query = structured_log_query
        self._jobs_lister = jobs_lister
        self._safety_checker = safety_checker
        self._subprocess_runner = subprocess_runner or (
            lambda *a, **k: subprocess.run(*a, check=False, **k)  # type: ignore[call-arg]
        )

    def _get_daemon_manager(self) -> Any:
        if self._daemon_factory is not None:
            return self._daemon_factory()
        from ninja_common.daemon import DaemonManager

        return DaemonManager()

    def _get_resource_monitor(self) -> Any:
        if self._resource_monitor_factory is not None:
            return self._resource_monitor_factory()
        from ninja_common.security import get_resource_monitor

        return get_resource_monitor()

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def run_command(
        self,
        cmd: str,
        cwd: str | None = None,
        repo_root: str | None = None,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        allow_write: bool = False,
    ) -> RunnerCommandResult:
        """Run a guarded, non-interactive shell command.

        Args:
            cmd: Shell command to execute.
            cwd: Working directory (defaults to ``repo_root``).
            repo_root: Repository root used as default cwd and safety scope.
            timeout: Kill the command after this many seconds.
            allow_write: Must be True for commands that look like they mutate
                files/state; read-only commands run freely.

        Returns:
            Guarded execution result with capped, redacted output.
        """
        from ninja_common.security import InputValidator

        if not cmd or not cmd.strip():
            return RunnerCommandResult(success=False, summary="Empty command refused.")
        if len(cmd) > 8000:
            return RunnerCommandResult(success=False, summary="Command exceeds 8000-char limit.")
        denied = find_denied(cmd)
        if denied is not None:
            logger.warning("Runner refused dangerous command: %s", denied)
            return RunnerCommandResult(success=False, summary=f"Refused: {denied}.")
        if looks_like_write(cmd) and not allow_write:
            return RunnerCommandResult(
                success=False,
                summary=(
                    "Refused: command looks like it mutates files/state. "
                    "Re-run with allow_write=True."
                ),
            )

        workdir = cwd or repo_root or "."
        try:
            root = InputValidator.validate_repo_root(repo_root) if repo_root else None
            target = (Path(workdir)).resolve()
            if root is not None:
                try:
                    target.relative_to(root.resolve())
                except ValueError:
                    return RunnerCommandResult(
                        success=False,
                        summary=f"Refused: cwd {target} escapes repo_root {root}.",
                    )
            if not target.exists() or not target.is_dir():
                return RunnerCommandResult(
                    success=False, summary=f"Refused: cwd does not exist: {target}."
                )
        except ValueError as exc:
            return RunnerCommandResult(success=False, summary=f"Refused: {exc}.")

        safety_warnings: list[str] = []
        if allow_write and repo_root and self._safety_checker is not None:
            try:
                info = self._safety_checker(repo_root, allow_dirty=True, create_tag=False)
                safety_warnings = [str(w) for w in info.get("warnings", [])]
            except Exception as exc:
                logger.debug("runner safety dry-run skipped: %s", exc)

        timeout = max(1, min(int(timeout or DEFAULT_COMMAND_TIMEOUT), 600))
        try:
            completed = await asyncio.to_thread(
                self._subprocess_runner,
                cmd,
                shell=True,
                cwd=str(target),
                capture_output=True,
                text=True,
                timeout=timeout,
                stdin=subprocess.DEVNULL,
            )
        except subprocess.TimeoutExpired:
            return RunnerCommandResult(
                success=False,
                summary=f"Command timed out after {timeout}s: {cmd[:200]}",
                safety_warnings=safety_warnings,
            )
        except Exception as exc:
            logger.error("Runner command failed: %s", exc, exc_info=True)
            return RunnerCommandResult(
                success=False,
                summary=f"Command failed to start: {exc}",
                safety_warnings=safety_warnings,
            )

        stdout = redact_text(completed.stdout or "")
        stderr = redact_text(completed.stderr or "")
        truncated = False
        if len(stdout) + len(stderr) > MAX_OUTPUT_CHARS:
            budget = MAX_OUTPUT_CHARS - len("...[truncated]")
            stdout = (stdout + "\n" + stderr)[:budget] + "\n...[truncated]"
            stderr = ""
            truncated = True
        ok = completed.returncode == 0
        head = "succeeded" if ok else f"exited with code {completed.returncode}"
        return RunnerCommandResult(
            success=ok,
            summary=f"Command {head}: {cmd[:200]}",
            returncode=completed.returncode,
            stdout=stdout,
            stderr=stderr,
            truncated=truncated,
            safety_warnings=safety_warnings,
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def tail_logs(
        self,
        module: str | None = None,
        level: str | None = None,
        limit: int = 50,
        session_id: str | None = None,
    ) -> RunnerLogsResult:
        """Return capped, redacted log tails.

        Combines structured JSONL logs (when available) with daemon ``.log``
        tails. Never returns more than 200 lines/entries.

        Args:
            module: Daemon/module name (e.g. ``coder``); None = structured log.
            level: Optional level filter (INFO/ERROR/...).
            limit: Max entries (capped at 200).
            session_id: Optional session filter for structured logs.

        Returns:
            Redacted tail result.
        """
        limit = max(1, min(int(limit or 50), MAX_LOG_LINES))
        entries: list[str] = []
        sources: list[str] = []

        if self._structured_log_query is not None:
            try:
                raw = self._structured_log_query(
                    module=module, level=level, limit=limit, session_id=session_id
                )
                for item in raw[:limit]:
                    if isinstance(item, dict):
                        line = (
                            f"{item.get('timestamp', '')} "
                            f"[{item.get('level', '')}] "
                            f"{item.get('message', item)}"
                        )
                    else:
                        line = str(item)
                    entries.append(redact_text(line))
                if entries:
                    sources.append("structured")
            except Exception as exc:
                logger.debug("runner structured log query failed: %s", exc)
        elif module:
            # Default: best-effort daemon .log tail; structured JSONL needs a
            # driver-owned logger instance, so without injection we document
            # the gap instead of fabricating entries.
            try:
                manager = self._get_daemon_manager()
                log_path = Path(manager._get_log_file(module))
                if log_path.exists():
                    lines = log_path.read_text(encoding="utf-8", errors="ignore").splitlines()[
                        -limit:
                    ]
                    entries.extend(redact_text(line) for line in lines)
                    sources.append(str(log_path))
            except Exception as exc:
                logger.debug("runner daemon log tail failed: %s", exc)

        if not entries:
            hint = f" for module '{module}'" if module else ""
            return RunnerLogsResult(
                success=True,
                summary=f"No log entries found{hint}.",
                entries=[],
                source=",".join(sources),
            )
        return RunnerLogsResult(
            success=True,
            summary=f"Tailed {len(entries)} log line(s){' from ' + ','.join(sources) if sources else ''}.",
            entries=entries[-limit:],
            source=",".join(sources),
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def processes(self) -> RunnerProcessesResult:
        """Snapshot daemon statuses plus host resource stats (read-only).

        Returns:
            Daemon map + resource stats; never mutates anything.
        """
        try:
            manager = self._get_daemon_manager()
            daemons = dict(manager.status_all())
        except Exception as exc:
            logger.error("Runner processes failed: %s", exc, exc_info=True)
            return RunnerProcessesResult(success=False, summary=f"Failed to query daemons: {exc}")
        try:
            monitor = self._get_resource_monitor()
            resources = dict(monitor.get_stats())
            try:
                health = await monitor.check_resources()
                resources["health"] = health
            except Exception as exc:
                logger.debug("runner resource health check skipped: %s", exc)
        except Exception as exc:
            resources = {"error": str(exc)}
        running = sum(1 for d in daemons.values() if d.get("running"))
        return RunnerProcessesResult(
            success=True,
            summary=f"{running}/{len(daemons)} daemon(s) running.",
            daemons=daemons,
            resources=resources,
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def jobs_overview(self, limit: int = 20) -> RunnerJobsResult:
        """Summarize pending background jobs/tasks (read-only).

        Args:
            limit: Max jobs to include.

        Returns:
            Read-only job summary list.
        """
        limit = max(1, min(int(limit or 20), 100))
        if self._jobs_lister is not None:
            jobs = await self._jobs_lister(limit)
            jobs = list(jobs)[:limit]
            return RunnerJobsResult(
                success=True,
                summary=f"{len(jobs)} job(s) listed.",
                jobs=jobs,
            )
        try:
            from ninja_common.mcp_tasks import SqliteTaskStore

            store = SqliteTaskStore()
            tasks, _cursor = await store.list_tasks(None)
            jobs: list[dict[str, Any]] = []
            for task in tasks[:limit]:
                jobs.append(
                    {
                        "taskId": getattr(task, "taskId", ""),
                        "status": str(getattr(task, "status", "")),
                        "status_message": getattr(task, "statusMessage", None),
                    }
                )
            try:
                store._conn.close()
            except Exception:
                pass
            pending = [j for j in jobs if "working" in j["status"]]
            return RunnerJobsResult(
                success=True,
                summary=f"{len(pending)} pending / {len(jobs)} total job(s).",
                jobs=jobs,
            )
        except Exception as exc:
            logger.debug("runner jobs overview unavailable: %s", exc)
            return RunnerJobsResult(
                success=True,
                summary="Job store unavailable; no jobs listed.",
                jobs=[],
            )

    async def handle(
        self,
        subtask: str,
        repo_root: str,
        *,
        command: str | None = None,
        allow_write: bool = False,
        timeout: int = DEFAULT_COMMAND_TIMEOUT,
        log_module: str | None = None,
        log_level: str | None = None,
        log_limit: int = 50,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        """Route one free-text runner subtask to the right primitive.

        Routing heuristic (structured fields win over text sniffing):
          - explicit ``command`` → :meth:`run_command`;
          - explicit ``log_module``/``log_level``/``session_id`` → tail_logs;
          - text mentioning daemon/process/cpu/memory/disk/status → processes;
          - text mentioning job/queue/pending/background → jobs_overview;
          - text mentioning log/error/tail → tail_logs;
          - otherwise, if the text looks like a shell command (starts with a
            known binary or contains shell operators) → run_command;
          - fallback → tail_logs (recent errors) + processes snapshot combo.

        Args:
            subtask: Free-text routine task from the central model.
            repo_root: Repository root (default cwd / safety scope).
            command: Optional explicit shell command (structured path).
            allow_write: Allow file-mutating commands.
            timeout: Shell timeout seconds.
            log_module: Optional explicit log module (structured path).
            log_level: Optional explicit log level.
            log_limit: Max log lines.
            session_id: Optional session filter.

        Returns:
            Dict with ``success``, ``summary`` and raw payload sections.
        """
        text = (subtask or "").lower()
        structured_log = bool(log_module or log_level or session_id)

        def _is_shellish(s: str) -> bool:
            bins = (
                "pytest ",
                "ruff ",
                "git ",
                "ls ",
                "cat ",
                "grep ",
                "rg ",
                "find ",
                "diff ",
                "wc ",
                "head ",
                "tail ",
                "df ",
                "du ",
                "ps ",
                "python ",
                "uv ",
                "make ",
                "npm ",
                "ls",
            )
            return s.strip().startswith(bins) or any(
                op in s for op in (" | ", " && ", " > ", ">>", "$(")
            )

        if command:
            result = await self.run_command(
                command, repo_root=repo_root, timeout=timeout, allow_write=allow_write
            )
            return {
                "success": result.success,
                "summary": result.summary,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "safety_warnings": result.safety_warnings,
            }
        if structured_log or any(k in text for k in ("log", "error", "tail", "traceback")):
            logs = await self.tail_logs(
                module=log_module,
                level=log_level,
                limit=log_limit,
                session_id=session_id,
            )
            if structured_log or ("process" not in text and "daemon" not in text):
                return {
                    "success": logs.success,
                    "summary": logs.summary,
                    "entries": logs.entries,
                }
        if any(
            k in text for k in ("daemon", "process", "cpu", "memory", "disk", "status", "health")
        ):
            procs = await self.processes()
            return {
                "success": procs.success,
                "summary": procs.summary,
                "daemons": procs.daemons,
                "resources": procs.resources,
            }
        if any(k in text for k in ("job", "queue", "pending", "background")):
            jobs = await self.jobs_overview()
            return {
                "success": jobs.success,
                "summary": jobs.summary,
                "jobs": jobs.jobs,
            }
        if _is_shellish(text):
            result = await self.run_command(
                subtask, repo_root=repo_root, timeout=timeout, allow_write=allow_write
            )
            return {
                "success": result.success,
                "summary": result.summary,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "safety_warnings": result.safety_warnings,
            }
        logs = await self.tail_logs(module=log_module, level="ERROR", limit=log_limit)
        procs = await self.processes()
        return {
            "success": True,
            "summary": f"{logs.summary} {procs.summary}",
            "entries": logs.entries,
            "daemons": procs.daemons,
        }


def shlex_split_hint(cmd: str) -> list[str]:
    """Best-effort tokenization hint for logging (never executed directly).

    Args:
        cmd: Shell command string.

    Returns:
        Token list (falls back to ``[cmd]`` on parse errors).
    """
    try:
        return shlex.split(cmd)
    except ValueError:
        return [cmd]
