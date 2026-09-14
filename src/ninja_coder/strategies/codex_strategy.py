"""
Codex CLI strategy implementation (OpenAI Codex host-auth).

Codex is OpenAI's coding agent CLI. It is already authorized on the host via
the ChatGPT login (``codex login status``) — just launch it, never require
API keys. Subagents are spawned natively when the prompt asks for them.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ninja_coder.strategies.base import (
    CLICapabilities,
    CLICommandResult,
    ParsedResult,
    subprocess_env,
)
from ninja_common.logging_utils import get_logger


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig

logger = get_logger(__name__)

DEFAULT_CODEX_MODEL = "gpt-5.6-luna"

#: Sandbox policy used for autonomous runs. ``workspace-write`` lets Codex
#: edit the repo without interactive approvals while staying sandboxed.
DEFAULT_CODEX_SANDBOX = "workspace-write"


def check_codex_auth(bin_path: str | None = None) -> bool:
    """Check if Codex CLI is available (host-auth via ChatGPT login).

    Lightweight check only: binary in PATH + ``--help`` exits 0.
    No network calls (never run a probe ``exec`` here).

    Args:
        bin_path: Optional explicit path to the codex binary.

    Returns:
        True if codex looks usable, False otherwise.
    """
    binary = bin_path or shutil.which("codex")
    if not binary:
        return False
    try:
        result = subprocess.run(
            [binary, "--help"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


class CodexStrategy:
    """Strategy for OpenAI Codex CLI.

    Command shape (verified locally, codex-cli 0.154.0):
        codex exec -m <model> -s <sandbox> -C <repo_root> --skip-git-repo-check
              --json [--json-output-last] "<prompt>"
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Codex strategy.

        Args:
            bin_path: Path to the Codex binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config

        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,
            supports_native_zai=False,
            supports_dialogue_mode=True,
            max_context_files=50,
            preferred_task_types=["sequential", "quick", "parallel"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "codex"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Codex CLI."""
        return self._capabilities

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
        session_id: str | None = None,
        continue_last: bool = False,
    ) -> CLICommandResult:
        """Build Codex command.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context (folded into prompt).
            model: Model to use (flat id, e.g. ``gpt-5.6-luna``).
            additional_flags: Additional flags (supports ``sandbox`` override
                and ``enable_multi_agent``).
            session_id: Session ID for conversation continuity (unused for
                one-shot ``exec`` runs; kept for interface).
            continue_last: Resume last session (unused for one-shot runs).

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model or DEFAULT_CODEX_MODEL

        extra = additional_flags or {}
        sandbox = str(extra.get("sandbox") or DEFAULT_CODEX_SANDBOX)

        cmd = [
            self.bin_path,
            "exec",
            "-m",
            model_name,
            "-s",
            sandbox,
            "-C",
            repo_root,
            "--skip-git-repo-check",
            "--json",
        ]

        final_prompt = prompt
        if file_paths:
            files_text = ", ".join(file_paths)
            final_prompt = f"{prompt}\n\nFocus on these files: {files_text}"

        if extra.get("enable_multi_agent"):
            final_prompt = (
                f"{final_prompt}\n\nUse Codex subagents to parallelize this "
                f"task: spawn specialized subagents, collect their results, "
                f"then produce the final consolidated answer."
            )

        cmd.append(final_prompt)

        # Inherit host environment (ChatGPT login auth lives here); never
        # inject API keys.
        env = subprocess_env()

        base_timeout = int(os.environ.get("NINJA_CODEX_TIMEOUT", "600"))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "codex",
                "model": model_name,
                "sandbox": sandbox,
                "timeout": base_timeout,
                "session_id": session_id,
                "continue_last": continue_last,
                "multi_agent": bool(extra.get("enable_multi_agent")),
            },
        )

    def build_command_with_multi_agent(
        self,
        prompt: str,
        repo_root: str,
        agents: list[str],
        context: dict[str, Any] | None = None,
        file_paths: list[str] | None = None,
        model: str | None = None,
    ) -> CLICommandResult:
        """Build Codex command with subagent orchestration.

        Codex spawns subagents natively when the prompt requests them, so
        multi-agent mode just appends a subagent directive and delegates to
        ``build_command``.

        Args:
            prompt: The original task description.
            repo_root: Repository root path.
            agents: List of agent names to activate.
            context: Additional context for agents.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).

        Returns:
            CLICommandResult with enhanced subagent prompt.
        """
        agents_text = ", ".join(agents) if agents else "specialized subagents"
        enhanced_prompt = (
            f"{prompt}\n\nOrchestrate this task with Codex subagents "
            f"({agents_text}). Coordinate the work, collect their results, "
            f"and return the final consolidated output."
        )

        return self.build_command(
            prompt=enhanced_prompt,
            repo_root=repo_root,
            file_paths=file_paths,
            model=model,
            additional_flags={"enable_multi_agent": True},
        )

    @staticmethod
    def _extract_touched_paths(stdout: str) -> list[str]:
        """Extract file paths from Codex JSONL event stream.

        When run with ``--json`` Codex emits newline-delimited JSON events.
        File edits arrive as ``item.completed`` events with ``item.type ==
        "file_change"`` and ``changes[].path`` / ``changes[].kind``.

        Args:
            stdout: Full stdout of the Codex run.

        Returns:
            List of file paths touched by the run.
        """
        touched: list[str] = []
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") != "item.completed":
                continue
            item = event.get("item", {})
            if item.get("type") != "file_change":
                continue
            for change in item.get("changes", []):
                path = change.get("path")
                if path:
                    touched.append(path)
        return sorted(set(touched))

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
    ) -> ParsedResult:
        """Parse Codex output.

        Args:
            stdout: Standard output from Codex execution.
            stderr: Standard error from Codex execution.
            exit_code: Exit code from Codex execution.
            repo_root: Repository root path (unused, kept for interface).

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        error_patterns = [
            r"authentication\s+failed",
            r"not\s+authenticated",
            r"login\s+required",
            r"invalid\s+api\s+key",
            r"rate\s+limit",
            r"timeout",
            r"connection\s+refused",
            r"model\s+not\s+found",
            r"permission\s+denied",
            r"Error:",
        ]

        retryable_error = False
        error_msg = ""

        for pattern in error_patterns:
            match = re.search(pattern, combined_output, re.IGNORECASE)
            if match:
                if any(
                    retry_pattern in pattern
                    for retry_pattern in [r"rate\s+limit", "timeout", r"connection\s+refused"]
                ):
                    retryable_error = True

                start = max(0, match.start() - 60)
                end = min(len(combined_output), match.end() + 60)
                error_msg = combined_output[start:end].strip()
                error_msg = " ".join(error_msg.split())
                break

        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_output = ansi_escape.sub("", combined_output)

        touched_paths = self._extract_touched_paths(stdout)

        # Fallback: scrape "path/to/file" mentions from the final text when
        # no structured file_change events are present.
        if not touched_paths:
            for pattern in [
                r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
                r"\[([^\]]+\.\w+)\]",
            ]:
                for match in re.findall(pattern, clean_output):
                    candidate = match.strip("`'\"()")
                    if candidate and ("/" in candidate or "." in candidate):
                        touched_paths.append(candidate)
            touched_paths = sorted(set(touched_paths))

        if success:
            if touched_paths:
                file_count = len(touched_paths)
                file_list = ", ".join(touched_paths[:5])
                if file_count > 5:
                    file_list += f" and {file_count - 5} more"
                summary = f"✅ Modified {file_count} file(s): {file_list}"
            else:
                summary = "✅ Task completed successfully"
        elif error_msg:
            summary = f"❌ Codex failed: {error_msg[:100]}"
        else:
            summary = "❌ Task failed"

        notes = ""
        if not success:
            lowered = combined_output.lower()
            if (
                "not authenticated" in lowered
                or "login required" in lowered
                or "authentication" in lowered
            ):
                notes = "❌ Codex is not authenticated. Run 'codex login' to log in."
                summary = "❌ Authentication error"
            elif error_msg:
                notes = error_msg[:200]
            elif stderr:
                error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
                if error_lines:
                    notes = error_lines[-1][:200]

        return ParsedResult(
            success=success,
            summary=summary,
            notes=notes,
            touched_paths=touched_paths,
            retryable_error=retryable_error,
        )

    def should_retry(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> bool:
        """Determine if Codex execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Exit code from execution.

        Returns:
            True if the error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code, repo_root=None)
        return result.retryable_error

    def get_timeout(self, task_type: str) -> int:
        """Get recommended timeout for task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base_timeout = int(os.environ.get("NINJA_CODEX_TIMEOUT", "600"))

        base_task_type = task_type.removesuffix("_plan")
        if base_task_type == "quick":
            return base_timeout // 2

        return base_timeout
