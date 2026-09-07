"""
Junie CLI strategy implementation (JetBrains Junie host-auth).

Junie is JetBrains' coding agent CLI. It is already authorized on the host
via JetBrains Account (JB Central) — just launch it, never require API keys.
"""

from __future__ import annotations

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
)
from ninja_common.logging_utils import get_logger


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig

logger = get_logger(__name__)

DEFAULT_JUNIE_MODEL = "deepseek-v4-flash"


def check_junie_auth(bin_path: str | None = None) -> bool:
    """Check if Junie CLI is available (host-auth via JetBrains Account).

    Lightweight check only: binary in PATH + ``--help`` exits 0.
    No network calls (never run a probe ``--task`` here).

    Args:
        bin_path: Optional explicit path to the junie binary.

    Returns:
        True if junie looks usable, False otherwise.
    """
    binary = bin_path or shutil.which("junie")
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


class JunieStrategy:
    """Strategy for JetBrains Junie CLI.

    Command shape (verified locally, junie 26.9.7):
        junie --model <id> --output-format text -p <repo_root>
              --skip-update-check [--session-id ID] [--resume]
              --task "<prompt>"
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Junie strategy.

        Args:
            bin_path: Path to the Junie binary.
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
            preferred_task_types=["sequential", "quick"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "junie"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Junie CLI."""
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
        """Build Junie command.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context (folded into prompt).
            model: Model to use (flat id, e.g. ``deepseek-v4-flash``).
            additional_flags: Additional flags (supports ``auth`` key for CI
                ``--auth`` injection; never used for host-auth).
            session_id: Session ID for conversation continuity.
            continue_last: Resume last session via ``--resume``.

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model or DEFAULT_JUNIE_MODEL

        cmd = [
            self.bin_path,
            "--model",
            model_name,
            "--output-format",
            "text",
            "-p",
            repo_root,
            "--skip-update-check",
        ]

        if session_id:
            cmd.extend(["--session-id", session_id])
        if continue_last:
            cmd.append("--resume")

        # CI escape hatch: explicit --auth only when caller passes it.
        # Host-auth path never injects keys.
        extra = additional_flags or {}
        if extra.get("auth"):
            cmd.extend(["--auth", str(extra["auth"])])

        final_prompt = prompt
        if file_paths:
            files_text = ", ".join(file_paths)
            final_prompt = f"{prompt}\n\nFocus on these files: {files_text}"

        cmd.extend(["--task", final_prompt])

        # Inherit host environment (JetBrains Account auth lives here);
        # never inject API keys.
        env = os.environ.copy()

        base_timeout = int(os.environ.get("NINJA_JUNIE_TIMEOUT", "600"))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "junie",
                "model": model_name,
                "timeout": base_timeout,
                "session_id": session_id,
                "continue_last": continue_last,
            },
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
    ) -> ParsedResult:
        """Parse Junie output.

        Args:
            stdout: Standard output from Junie execution.
            stderr: Standard error from Junie execution.
            exit_code: Exit code from Junie execution.
            repo_root: Repository root path (unused, kept for interface).

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        error_patterns = [
            r"AuthenticationError",
            r"authentication\s+failed",
            r"not\s+authenticated",
            r"junie_api_key",
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

        suspected_paths: list[str] = []
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
            r"file:\s*['\"]?([^\s'\"]+)['\"]?",
            r"Edited:\s+([^\s]+)",
            r"Created:\s+([^\s]+)",
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, clean_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        suspected_paths = list(set(suspected_paths))

        if success:
            if suspected_paths:
                file_count = len(suspected_paths)
                file_list = ", ".join(suspected_paths[:5])
                if file_count > 5:
                    file_list += f" and {file_count - 5} more"
                summary = f"✅ Modified {file_count} file(s): {file_list}"
            else:
                summary = "✅ Task completed successfully"
        elif error_msg:
            summary = f"❌ Junie failed: {error_msg[:100]}"
        else:
            summary = "❌ Task failed"

        notes = ""
        if not success:
            lowered = combined_output.lower()
            if (
                "not authenticated" in lowered
                or "authentication" in lowered
                or "junie_api_key" in lowered
            ):
                notes = "❌ Junie is not authenticated. Run 'junie' interactively to log in."
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
            touched_paths=suspected_paths,
            retryable_error=retryable_error,
        )

    def should_retry(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> bool:
        """Determine if Junie execution should be retried.

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
        base_timeout = int(os.environ.get("NINJA_JUNIE_TIMEOUT", "600"))

        base_task_type = task_type.removesuffix("_plan")
        if base_task_type == "parallel":
            return base_timeout
        elif base_task_type == "quick":
            return base_timeout // 2

        return base_timeout
