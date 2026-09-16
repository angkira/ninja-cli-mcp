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
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable

from ninja_agent.models import (
    AgentDistillLogsRequest,
    AgentDistillLogsResult,
    AgentExecPipelineRequest,
    AgentExecPipelineResult,
    AgentRunAndDiagnoseRequest,
    AgentRunAndDiagnoseResult,
    FailureDetail,
    LogCluster,
    PipelineStepResult,
)
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


# ============================================================================
# DiagnosticsDistiller — parse test/compiler diagnostics & condense output
# ============================================================================


class DiagnosticsDistiller:
    """Distills raw command output into clean, structured diagnostics and condensed text."""

    ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

    PYTEST_SUMMARY_RE = re.compile(
        r"=+\s*(?:(?P<failed>\d+)\s+failed)?(?:,\s*)?"
        r"(?:(?P<passed>\d+)\s+passed)?(?:,\s*)?"
        r"(?:(?P<skipped>\d+)\s+skipped)?(?:,\s*)?"
        r"(?:(?P<deselected>\d+)\s+deselected)?(?:,\s*)?"
        r"(?:(?P<xfailed>\d+)\s+xfailed)?(?:,\s*)?"
        r"(?:(?P<xpassed>\d+)\s+xpassed)?(?:,\s*)?"
        r"(?:(?P<warnings>\d+)\s+warnings?)?(?:,\s*)?"
        r"(?:(?P<errors>\d+)\s+errors?)?.*in\s+[\d\.]+s\s*=+",
        re.IGNORECASE,
    )

    PYTEST_SHORT_FAILED_RE = re.compile(
        r"^(?:FAILED|ERROR)\s+([^\s:]+::[^\s]+)(?:\s*-\s*(.*))?$"
    )

    DIAGNOSTIC_RE = re.compile(
        r"^([^\s:]+\.[a-zA-Z0-9_]+):(\d+)(?::(\d+))?:\s*(?:([a-zA-Z0-9_\-\[\]]+):\s*)?(.*)$"
    )

    PYTEST_FAILURE_HEADER_RE = re.compile(r"^_{3,}\s*(.+?)\s*_{3,}$")

    NOISE_PATTERNS = (
        re.compile(r"^=+\s*test session starts\s*=+", re.IGNORECASE),
        re.compile(r"^(platform|rootdir|configfile|plugins|cachedir|asyncio):\s+", re.IGNORECASE),
        re.compile(r"^collecting \.\.\.", re.IGNORECASE),
        re.compile(r"^collected \d+ items", re.IGNORECASE),
        re.compile(r"\bPASSED\s*\[\s*\d+%\]"),
        re.compile(r"^\.+$"),
    )

    @classmethod
    def clean_ansi(cls, text: str) -> str:
        """Strip ANSI escape sequences from text."""
        if not text:
            return ""
        return cls.ANSI_ESCAPE.sub("", text)

    @classmethod
    def parse_test_runner(cls, text: str) -> dict[str, Any]:
        """Parse pytest/test runner output for counts, failed test names, line numbers, and tracebacks."""
        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        failures: list[FailureDetail] = []

        summary_m = cls.PYTEST_SUMMARY_RE.search(text)
        if summary_m:
            groups = summary_m.groupdict()
            failed = int(groups.get("failed") or 0)
            passed = int(groups.get("passed") or 0)
            skipped = int(groups.get("skipped") or 0)
            errors = int(groups.get("errors") or 0)
        else:
            m_pass = re.search(r"\b(\d+)\s+passed\b", text)
            if m_pass:
                passed = int(m_pass.group(1))
            m_fail = re.search(r"\b(\d+)\s+failed\b", text)
            if m_fail:
                failed = int(m_fail.group(1))
            m_skip = re.search(r"\b(\d+)\s+skipped\b", text)
            if m_skip:
                skipped = int(m_skip.group(1))
            m_err = re.search(r"\b(\d+)\s+errors?\b", text)
            if m_err:
                errors = int(m_err.group(1))

        short_failures: dict[str, dict[str, Any]] = {}
        in_short_summary = False
        for line in text.splitlines():
            line_clean = line.strip()
            if "short test summary info" in line_clean:
                in_short_summary = True
                continue
            if in_short_summary and line_clean.startswith("="):
                in_short_summary = False
                continue
            if in_short_summary or line_clean.startswith(("FAILED ", "ERROR ")):
                m_short = cls.PYTEST_SHORT_FAILED_RE.match(line_clean)
                if m_short:
                    test_id = m_short.group(1)
                    err_msg = m_short.group(2) or ""
                    file_path = test_id.split("::")[0] if "::" in test_id else None
                    short_failures[test_id] = {
                        "test_name": test_id,
                        "file_path": file_path,
                        "error_message": err_msg,
                    }

        failure_blocks = cls._extract_pytest_failure_blocks(text)
        for block in failure_blocks:
            test_name = block["test_name"]
            matched_key = None
            for key in short_failures:
                if test_name == key or key.endswith(f"::{test_name}") or test_name in key:
                    matched_key = key
                    break

            file_path = block.get("file_path")
            line_no = block.get("line_number")
            error_msg = block.get("error_message") or ""
            tb = block.get("traceback")

            if matched_key:
                short_info = short_failures.pop(matched_key)
                if not error_msg or error_msg == "Failure":
                    error_msg = short_info["error_message"] or error_msg
                if not file_path:
                    file_path = short_info["file_path"]
                test_name = short_info["test_name"]

            failures.append(
                FailureDetail(
                    test_name=test_name,
                    file_path=file_path,
                    line_number=line_no,
                    error_message=error_msg or "Test failed",
                    traceback=tb,
                )
            )

        for short_info in short_failures.values():
            failures.append(
                FailureDetail(
                    test_name=short_info["test_name"],
                    file_path=short_info["file_path"],
                    line_number=None,
                    error_message=short_info["error_message"] or "Test failed",
                    traceback=None,
                )
            )

        if not failed and failures:
            failed = len(failures)

        return {
            "passed_count": passed,
            "failed_count": failed,
            "skipped_count": skipped,
            "error_count": errors,
            "failures": failures,
        }

    @classmethod
    def _extract_pytest_failure_blocks(cls, text: str) -> list[dict[str, Any]]:
        blocks: list[dict[str, Any]] = []
        lines = text.splitlines()
        in_failures = False
        current_name: str | None = None
        current_lines: list[str] = []

        for line in lines:
            if re.match(r"^=+\s*(FAILURES|ERRORS)\s*=+", line):
                in_failures = True
                continue
            if in_failures and re.match(
                r"^=+\s*(short test summary info|warnings summary|\d+\s+failed|\d+\s+passed)",
                line,
            ):
                if current_name and current_lines:
                    blocks.append(cls._parse_single_failure_block(current_name, current_lines))
                    current_name = None
                    current_lines = []
                in_failures = False
                continue

            if in_failures:
                m_header = cls.PYTEST_FAILURE_HEADER_RE.match(line)
                if m_header:
                    if current_name and current_lines:
                        blocks.append(cls._parse_single_failure_block(current_name, current_lines))
                    current_name = m_header.group(1).strip()
                    current_lines = []
                elif current_name is not None:
                    current_lines.append(line)

        if current_name and current_lines:
            blocks.append(cls._parse_single_failure_block(current_name, current_lines))

        return blocks

    @classmethod
    def _parse_single_failure_block(cls, name: str, lines: list[str]) -> dict[str, Any]:
        file_path: str | None = None
        line_number: int | None = None
        error_message: str | None = None
        tb_lines: list[str] = []
        e_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            if line.startswith("E   ") or line.startswith("E  "):
                e_lines.append(line[4:].strip())
            m_fl = re.match(
                r"^([^\s:]+\.[a-zA-Z0-9_]+):(\d+):\s*(?:in\s+.*|([A-Za-z0-9_]+Error.*|AssertionError.*))?$",
                stripped,
            )
            if m_fl:
                file_path = m_fl.group(1)
                line_number = int(m_fl.group(2))
                if m_fl.group(3) and not error_message:
                    error_message = m_fl.group(3).strip()
            if line.startswith(("    ", ">   ", "E   ", "E  ")):
                tb_lines.append(line)

        if e_lines and not error_message:
            error_message = "\n".join(e_lines)

        if not file_path:
            for line in lines:
                m_file = re.search(r'File ["\']([^"\']+)["\'], line (\d+)', line)
                if m_file:
                    file_path = m_file.group(1)
                    line_number = int(m_file.group(2))
                    break

        stripped_tb = "\n".join(tb_lines).strip() if tb_lines else "\n".join(lines[:30]).strip()

        return {
            "test_name": name,
            "file_path": file_path,
            "line_number": line_number,
            "error_message": error_message or "Failure",
            "traceback": stripped_tb or None,
        }

    @classmethod
    def parse_diagnostics(cls, text: str) -> list[FailureDetail]:
        """Parse linter / compiler diagnostics (ruff, mypy, flake8, gcc)."""
        diagnostics: list[FailureDetail] = []
        for line in text.splitlines():
            line_str = line.strip()
            if ": in " in line_str or line_str.startswith(("Traceback", "FAILED ", "===")):
                continue
            m = cls.DIAGNOSTIC_RE.match(line_str)
            if m:
                file_path = m.group(1)
                line_no = int(m.group(2))
                rule_or_sev = m.group(4) or ""
                msg = m.group(5).strip()
                full_msg = f"{rule_or_sev}: {msg}".strip(": ") if rule_or_sev else msg
                diagnostics.append(
                    FailureDetail(
                        file_path=file_path,
                        line_number=line_no,
                        error_message=full_msg,
                    )
                )
        return diagnostics

    @classmethod
    def parse_traceback(cls, text: str) -> list[FailureDetail]:
        """Parse standalone Python or runtime tracebacks in command output."""
        failures: list[FailureDetail] = []
        tb_blocks = LogDistiller.extract_isolated_errors(text.splitlines())
        for tb in tb_blocks:
            file_path = None
            line_number = None
            err_msg = ""
            for line in tb.splitlines():
                m = re.search(r'File "([^"]+)", line (\d+)', line)
                if m:
                    file_path = m.group(1)
                    line_number = int(m.group(2))
                if re.match(r"^[A-Za-z0-9_.]*(?:Error|Exception|Fail):\s*.*", line.strip()):
                    err_msg = line.strip()
            failures.append(
                FailureDetail(
                    file_path=file_path,
                    line_number=line_number,
                    error_message=err_msg or tb.splitlines()[-1].strip(),
                    traceback=tb,
                )
            )
        return failures

    @classmethod
    def condense_output(cls, stdout: str, stderr: str, max_chars: int = 8000) -> str:
        """Condense output by stripping passing test spam, ANSI sequences, and noise."""
        raw = cls.clean_ansi((stdout or "") + ("\n" + stderr if stderr else "")).strip()
        if not raw:
            return ""

        lines = raw.splitlines()
        is_test_output = any(
            "=== test session starts" in line or "== FAILURES ==" in line or " passed in " in line
            for line in lines
        )

        truncation_marker = "\n...[condensed output truncated]"
        if is_test_output:
            all_passed = not any(
                "FAILED" in line or "=== FAILURES ===" in line or "=== ERRORS ===" in line for line in lines
            )
            if all_passed:
                for line in reversed(lines):
                    m = re.search(r"=\s*(\d+\s+passed.*in\s+[\d\.]+s)\s*=", line)
                    if m:
                        return f"OK, {m.group(1)}"
                return "OK, all tests passed."

            filtered_lines: list[str] = []
            for line in lines:
                if any(pat.search(line) for pat in cls.NOISE_PATTERNS):
                    continue
                filtered_lines.append(line)

            condensed = "\n".join(filtered_lines).strip()
            if len(condensed) > max_chars:
                return (
                    condensed[: max_chars - len(truncation_marker)]
                    + truncation_marker
                )
            return condensed

        filtered = [line for line in lines if line.strip()]
        condensed = "\n".join(filtered)
        if len(condensed) > max_chars:
            return (
                condensed[: max_chars - len(truncation_marker)]
                + truncation_marker
            )
        return condensed

    @classmethod
    def distill(
        cls,
        stdout: str,
        stderr: str,
        returncode: int | None = 0,
        framework_hint: str | None = None,
    ) -> dict[str, Any]:
        """Distill raw output and return structured metrics, failures, condensed output, and summary."""
        clean_out = cls.clean_ansi(stdout or "")
        clean_err = cls.clean_ansi(stderr or "")
        combined = (clean_out + "\n" + clean_err).strip()

        passed = 0
        failed = 0
        skipped = 0
        errors = 0
        failures: list[FailureDetail] = []

        is_pytest = (
            framework_hint == "pytest"
            or "pytest" in combined
            or "=== FAILURES ===" in combined
            or "short test summary info" in combined
            or bool(cls.PYTEST_SUMMARY_RE.search(combined))
        )

        if is_pytest:
            parsed = cls.parse_test_runner(combined)
            passed = parsed["passed_count"]
            failed = parsed["failed_count"]
            skipped = parsed["skipped_count"]
            errors = parsed["error_count"]
            failures = parsed["failures"]

            if returncode == 0 and failed == 0 and errors == 0:
                summary = f"OK, {passed} passed"
                if skipped:
                    summary += f", {skipped} skipped"
            else:
                summary = f"Test run failed: {failed} failed, {passed} passed"
                if errors:
                    summary += f", {errors} errors"
                if skipped:
                    summary += f", {skipped} skipped"

        elif framework_hint in ("ruff", "mypy") or (
            not framework_hint and bool(cls.parse_diagnostics(combined))
        ):
            diags = cls.parse_diagnostics(combined)
            failures = diags
            error_count = len(diags)
            failed_count = sum(
                1
                for d in diags
                if "error" in d.error_message.lower()
                or not any(k in d.error_message.lower() for k in ("warning", "note", "info"))
            )
            failed = failed_count
            errors = error_count

            if returncode == 0:
                summary = (
                    f"Completed cleanly with {errors} notices"
                    if errors
                    else "All checks passed cleanly."
                )
            else:
                summary = f"Diagnostics found: {errors} issues reported."

        else:
            tb_failures = cls.parse_traceback(combined)
            if tb_failures:
                failures = tb_failures
                failed = len(tb_failures)
                errors = len(tb_failures)
            else:
                failed = 0 if returncode == 0 else 1
                errors = 0

            if returncode == 0:
                summary = "Command completed successfully."
            else:
                summary = f"Command failed with exit code {returncode}."

        condensed = cls.condense_output(clean_out, clean_err)

        return {
            "passed_count": passed,
            "failed_count": failed,
            "skipped_count": skipped,
            "error_count": errors,
            "failures": failures,
            "condensed_output": condensed,
            "summary": summary,
        }


# ============================================================================
# LogDistiller — clustering, deduplication, and error extraction
# ============================================================================


class LogDistiller:
    """Distills, clusters, and deduplicates log lines and isolates error blocks."""

    TIMESTAMP_PATTERNS = (
        re.compile(
            r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"
        ),
        re.compile(r"\b\d{2}:\d{2}:\d{2}(?:[.,]\d+)?\b"),
    )
    HEX_PATTERN = re.compile(r"\b0x[0-9a-fA-F]+\b")
    UUID_PATTERN = re.compile(
        r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
    )
    NUM_ID_PATTERN = re.compile(r"\b\d{4,}\b")
    ID_KEY_PATTERN = re.compile(r"(?<=[=:_/#])\d+\b")
    LEVEL_PATTERN = re.compile(
        r"\b(DEBUG|INFO|WARNING|WARN|ERROR|CRITICAL|FATAL)\b", re.IGNORECASE
    )

    @classmethod
    def extract_timestamp(cls, line: str) -> str | None:
        """Extract first timestamp seen in log line."""
        for pat in cls.TIMESTAMP_PATTERNS:
            m = pat.search(line)
            if m:
                return m.group(0)
        return None

    @classmethod
    def extract_level(cls, line: str) -> str:
        """Extract and normalize log level from line."""
        m = cls.LEVEL_PATTERN.search(line)
        if m:
            lvl = m.group(1).upper()
            if lvl == "WARN":
                return "WARNING"
            if lvl == "FATAL":
                return "CRITICAL"
            return lvl
        return "UNKNOWN"

    @classmethod
    def normalize_message(cls, line: str) -> str:
        """Mask timestamps, hex addresses, UUIDs, numeric IDs to reveal repeating patterns."""
        norm = line
        for pat in cls.TIMESTAMP_PATTERNS:
            norm = pat.sub("<TIMESTAMP>", norm)
        norm = cls.UUID_PATTERN.sub("<UUID>", norm)
        norm = cls.HEX_PATTERN.sub("<HEX>", norm)
        norm = cls.NUM_ID_PATTERN.sub("<NUM>", norm)
        norm = cls.ID_KEY_PATTERN.sub("<ID>", norm)
        return " ".join(norm.split())

    @classmethod
    def extract_isolated_errors(cls, lines: list[str]) -> list[str]:
        """Extract multi-line tracebacks and isolate distinct error blocks."""
        errors: list[str] = []
        current_tb: list[str] = []
        in_tb = False

        tb_start_re = re.compile(
            r"^\s*(Traceback \(most recent call last\):|Exception in thread |Error: )"
        )
        for line in lines:
            if tb_start_re.search(line):
                if current_tb:
                    errors.append("\n".join(current_tb))
                    current_tb = []
                in_tb = True
                current_tb.append(line)
            elif in_tb:
                if line.startswith((" ", "\t")) or "File " in line:
                    current_tb.append(line)
                elif re.match(r"^[A-Za-z0-9_.]*(?:Error|Exception|Fail):\s*.*", line):
                    current_tb.append(line)
                    errors.append("\n".join(current_tb))
                    current_tb = []
                    in_tb = False
                elif not line.strip():
                    current_tb.append(line)
                else:
                    errors.append("\n".join(current_tb))
                    current_tb = []
                    in_tb = False
        if current_tb:
            errors.append("\n".join(current_tb))
        return errors

    @classmethod
    def distill(cls, entries: list[str]) -> dict[str, Any]:
        """Cluster repeating log lines and extract errors."""
        if not entries:
            return {
                "clusters": [],
                "isolated_errors": [],
                "summary": "No log entries to distill.",
            }

        clusters_map: dict[tuple[str, str], dict[str, Any]] = {}
        for line in entries:
            ts = cls.extract_timestamp(line)
            lvl = cls.extract_level(line)
            norm = cls.normalize_message(line)
            key = (norm, lvl)
            if key not in clusters_map:
                clusters_map[key] = {
                    "pattern": norm,
                    "count": 1,
                    "level": lvl,
                    "first_seen": ts,
                    "last_seen": ts,
                    "sample_line": line,
                }
            else:
                clusters_map[key]["count"] += 1
                if ts:
                    if not clusters_map[key]["first_seen"]:
                        clusters_map[key]["first_seen"] = ts
                    clusters_map[key]["last_seen"] = ts

        sorted_clusters = sorted(clusters_map.values(), key=lambda c: c["count"], reverse=True)
        log_clusters = [LogCluster(**c) for c in sorted_clusters]
        isolated_errors = cls.extract_isolated_errors(entries)

        summary = (
            f"Distilled {len(entries)} log lines into {len(log_clusters)} unique cluster(s) "
            f"with {len(isolated_errors)} isolated error block(s)."
        )
        return {
            "clusters": log_clusters,
            "isolated_errors": isolated_errors,
            "summary": summary,
        }


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

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def run_and_diagnose(
        self, request: AgentRunAndDiagnoseRequest
    ) -> AgentRunAndDiagnoseResult:
        """Execute command and distill structured failure details and condensed summary.

        Args:
            request: Command and execution parameters.

        Returns:
            Structured diagnostic outcome.
        """
        cmd_result = await self.run_command(
            request.command,
            cwd=request.cwd,
            repo_root=request.repo_root,
            timeout=request.timeout,
            allow_write=request.allow_write,
        )
        distilled = DiagnosticsDistiller.distill(
            stdout=cmd_result.stdout,
            stderr=cmd_result.stderr,
            returncode=cmd_result.returncode,
            framework_hint=request.framework_hint,
        )
        summary = distilled["summary"]
        if (
            not cmd_result.success
            and not distilled["failures"]
            and ("Refused" in cmd_result.summary or "timed out" in cmd_result.summary)
        ):
            summary = cmd_result.summary

        return AgentRunAndDiagnoseResult(
            success=cmd_result.success,
            summary=summary,
            returncode=cmd_result.returncode,
            passed_count=distilled["passed_count"],
            failed_count=distilled["failed_count"],
            skipped_count=distilled["skipped_count"],
            error_count=distilled["error_count"],
            failures=distilled["failures"],
            condensed_output=distilled["condensed_output"],
            truncated=cmd_result.truncated,
            safety_warnings=list(cmd_result.safety_warnings),
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def exec_pipeline(
        self, request: AgentExecPipelineRequest
    ) -> AgentExecPipelineResult:
        """Execute an ordered sequence of shell commands with fail-fast logic.

        Args:
            request: Pipeline steps and execution parameters.

        Returns:
            Overall pipeline result with per-step outcomes.
        """
        step_results: list[PipelineStepResult] = []
        halt = False
        overall_success = True

        for step in request.steps:
            if halt:
                step_results.append(
                    PipelineStepResult(
                        command=step.command,
                        name=step.name,
                        success=False,
                        returncode=None,
                        duration_seconds=0.0,
                        skipped=True,
                        summary="Skipped due to earlier pipeline failure.",
                        condensed_output="",
                    )
                )
                continue

            step_cwd = step.cwd or request.cwd
            t0 = time.monotonic()
            cmd_res = await self.run_command(
                cmd=step.command,
                cwd=step_cwd,
                repo_root=request.repo_root,
                timeout=step.timeout,
                allow_write=step.allow_write,
            )
            duration = round(time.monotonic() - t0, 3)
            condensed = DiagnosticsDistiller.condense_output(cmd_res.stdout, cmd_res.stderr)

            step_success = cmd_res.success
            step_results.append(
                PipelineStepResult(
                    command=step.command,
                    name=step.name,
                    success=step_success,
                    returncode=cmd_res.returncode,
                    duration_seconds=duration,
                    skipped=False,
                    summary=cmd_res.summary,
                    condensed_output=condensed,
                )
            )

            if not step_success:
                if not step.continue_on_error:
                    overall_success = False
                    if request.fail_fast:
                        halt = True

        total_duration = round(sum(s.duration_seconds for s in step_results), 3)
        completed_count = sum(1 for s in step_results if not s.skipped and s.success)
        total_count = len(step_results)

        summary = (
            f"Pipeline {'succeeded' if overall_success else 'failed'}: "
            f"{completed_count}/{total_count} steps succeeded in {total_duration:.2f}s."
        )

        return AgentExecPipelineResult(
            success=overall_success,
            summary=summary,
            total_duration_seconds=total_duration,
            steps=step_results,
        )

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def distill_logs(
        self, request: AgentDistillLogsRequest
    ) -> AgentDistillLogsResult:
        """Fetch and distill logs into clusters and isolated errors.

        Args:
            request: Log query parameters and limit.

        Returns:
            Distilled log results with pattern clusters and tracebacks.
        """
        logs_res = await self.tail_logs(
            module=request.module,
            level=request.level,
            limit=request.limit,
            session_id=request.session_id,
        )
        distilled = LogDistiller.distill(logs_res.entries)
        return AgentDistillLogsResult(
            success=logs_res.success,
            summary=distilled["summary"] if logs_res.success else logs_res.summary,
            total_lines_analyzed=len(logs_res.entries),
            clusters=distilled["clusters"],
            isolated_errors=distilled["isolated_errors"],
            source=logs_res.source,
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
