"""
Pi CLI strategy implementation (pi.dev coding agent).

Pi is an autonomous coding assistant CLI from pi.dev. It operates on the host
environment, using configured models and providers (via ~/.pi/agent/settings.json,
auth.json, or environment variables).
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
from ninja_common.operator_models import normalize_pi_model, resolve_pi_thinking


if TYPE_CHECKING:
    from ninja_coder.driver import NinjaConfig

logger = get_logger(__name__)

DEFAULT_PI_MODEL = "deepseek-v4.1-flash"
DEFAULT_PI_TIMEOUT = 600


def check_pi_auth(bin_path: str | None = None) -> bool:
    """Check if Pi CLI is available on the host.

    Lightweight check only: binary in PATH + ``--help`` exits 0.
    No network calls.

    Args:
        bin_path: Optional explicit path to the pi binary.

    Returns:
        True if pi looks usable, False otherwise.
    """
    binary = bin_path or shutil.which("pi")
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


class PiStrategy:
    """Strategy for Pi CLI (pi.dev).

    Command shape:
        pi -p --mode json [--model <model>] [--thinking <level>] "<prompt>"
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Pi strategy.

        Args:
            bin_path: Path to the Pi binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config

        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,
            supports_native_zai=False,
            supports_dialogue_mode=False,
            max_context_files=50,
            preferred_task_types=["sequential", "quick", "parallel"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "pi"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Pi CLI."""
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
        """Build Pi command.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context (folded into prompt).
            model: Model to use.
            additional_flags: Additional flags (supports ``thinking`` override).
            session_id: Session ID for conversation continuity.
            continue_last: Resume last session.

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        raw_model = model or self.config.model or DEFAULT_PI_MODEL
        model_name = normalize_pi_model(raw_model) or DEFAULT_PI_MODEL

        extra = additional_flags or {}
        thinking_raw = extra.get("thinking")
        thinking = resolve_pi_thinking(
            explicit=str(thinking_raw) if thinking_raw is not None else None
        )

        cmd = [
            self.bin_path,
            "-p",
            "--mode",
            "json",
        ]

        if model_name:
            cmd.extend(["--model", model_name])

        if thinking:
            cmd.extend(["--thinking", thinking])

        final_prompt = prompt
        if file_paths:
            files_text = ", ".join(file_paths)
            final_prompt = f"{prompt}\n\nFocus on these files: {files_text}"

        cmd.append(final_prompt)

        env = subprocess_env()
        base_timeout = int(os.environ.get("NINJA_PI_TIMEOUT", str(DEFAULT_PI_TIMEOUT)))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "pi",
                "model": model_name,
                "thinking": thinking,
                "timeout": base_timeout,
                "session_id": session_id,
                "continue_last": continue_last,
            },
        )

    @staticmethod
    def _extract_touched_paths(stdout: str) -> list[str]:
        """Extract file paths touched during Pi execution.

        Parses JSONL event stream looking for tool executions of write and edit tools,
        with a regex fallback for text outputs.

        Args:
            stdout: Standard output from Pi execution.

        Returns:
            Sorted list of touched file paths.
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

            ev_type = event.get("type")
            if ev_type in ("tool_execution_start", "tool_execution_end"):
                tool_name = event.get("toolName")
                if tool_name in ("write", "edit"):
                    args = event.get("args") or {}
                    path = args.get("path")
                    if path and not event.get("isError", False):
                        touched.append(path)

        if not touched:
            file_patterns = [
                r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
                r"Successfully (?:wrote to|replaced \d+ block\(s\) in)\s+([^\s]+)",
                r"file:\s*['\"]?([^\s'\"]+)['\"]?",
            ]
            for pattern in file_patterns:
                matches = re.findall(pattern, stdout, re.IGNORECASE)
                for match in matches:
                    if match and ("/" in match or "." in match):
                        touched.append(match.rstrip(".,;:\"')]}"))

        return sorted(set(touched))

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
    ) -> ParsedResult:
        """Parse Pi output.

        Args:
            stdout: Standard output from Pi execution.
            stderr: Standard error from Pi execution.
            exit_code: Exit code from Pi execution.
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
            r"login\s+required",
            r"invalid\s+api\s+key",
            r"rate\s+limit",
            r"429",
            r"503",
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
                    retry_pat in pattern
                    for retry_pat in [
                        r"rate\s+limit",
                        "429",
                        "503",
                        "timeout",
                        r"connection\s+refused",
                    ]
                ):
                    retryable_error = True

                start = max(0, match.start() - 60)
                end = min(len(combined_output), match.end() + 60)
                error_msg = combined_output[start:end].strip()
                error_msg = " ".join(error_msg.split())
                break

        touched_paths = self._extract_touched_paths(stdout)

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
            summary = f"❌ Pi failed: {error_msg[:100]}"
        else:
            summary = "❌ Task failed"

        notes = ""
        if not success:
            lowered = combined_output.lower()
            if (
                "not authenticated" in lowered
                or "authentication" in lowered
                or "login required" in lowered
            ):
                notes = (
                    "❌ Pi authentication error. Check credentials or run 'pi auth' interactively."
                )
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
        """Determine if Pi execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Exit code from execution.

        Returns:
            True if the error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code, repo_root=None)
        return result.retryable_error

    def get_timeout(self, task_type: str | None = None) -> int:
        """Get timeout in seconds for Pi task.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base = int(os.environ.get("NINJA_PI_TIMEOUT", str(DEFAULT_PI_TIMEOUT)))
        if not task_type:
            return base

        normalized_type = task_type.removesuffix("_plan").upper()
        env_key = f"NINJA_PI_TIMEOUT_{normalized_type}"
        return int(os.environ.get(env_key, str(base)))
