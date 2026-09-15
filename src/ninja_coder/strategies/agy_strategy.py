"""
Antigravity CLI (``agy``) strategy implementation.

This module implements the CLI strategy for Google's Antigravity CLI,
which provides fast, accurate code completion and editing.
"""

from __future__ import annotations

import os
import re
import time
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

#: Sentinel default model meaning "let the CLI pick" — no ``--model`` flag is
#: emitted when this (or an empty value) is configured.
DEFAULT_MODEL_SENTINEL = "default"


class AgyStrategy:
    """Strategy for the Antigravity CLI (``agy``) tool.

    Antigravity provides fast code completion and editing capabilities.
    Key features:
    - Host-authenticated (no API key injection)
    - Dynamic model catalogue (``agy models``) — arbitrary model ids accepted
    - Writes into an explicit workspace via ``--add-dir``
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Antigravity strategy.

        Args:
            bin_path: Path to the ``agy`` binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config
        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,  # Supports arbitrary model selection
            supports_native_zai=False,
            max_context_files=50,
            preferred_task_types=["quick", "sequential"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "agy"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of the Antigravity CLI."""
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
        """Build the Antigravity command with model and context support.

        Args:
            prompt: The instruction prompt for the CLI.
            repo_root: Repository root path (added as the CLI workspace via
                ``--add-dir`` and used as the working directory).
            file_paths: List of files to include in context (already embedded
                in the prompt by the instruction builder; unused here).
            model: Model to use. ``None``/``""``/``"default"`` omit ``--model``
                so the CLI uses its own default.
            additional_flags: Additional CLI-specific flags (unused).
            session_id: Session ID to continue (unused).
            continue_last: Continue last session (unused).

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model

        cmd = [
            self.bin_path,
            "--add-dir",
            repo_root,
            "--dangerously-skip-permissions",
            # Stream NDJSON progress events. In text mode agy buffers and stays
            # silent for minutes, which trips the inactivity watchdog; streaming
            # keeps it alive and yields a structured final "result" event.
            "--output-format",
            "stream-json",
        ]

        # Only pass --model for a real model id; "default"/empty means the CLI
        # picks its own (there is no static allow-list — ids are dynamic).
        if model_name and model_name != DEFAULT_MODEL_SENTINEL:
            cmd.extend(["--model", model_name])

        # Prompt in headless mode (`-p`/`--print`). File context is already
        # embedded in the prompt, so no explicit file flags are used.
        cmd.extend(["-p", prompt])

        # Antigravity is host-authenticated: never inject OPENAI_*/provider keys.
        env = subprocess_env()

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "model": model_name or DEFAULT_MODEL_SENTINEL,
                "provider": "agy",
                "timeout": self.get_timeout("quick"),
            },
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
    ) -> ParsedResult:
        """Parse Antigravity output to extract results.

        Args:
            stdout: Standard output from Antigravity execution.
            stderr: Standard error from Antigravity execution.
            exit_code: Process exit code.
            repo_root: Repository root path (optional, used for file verification).

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        # Extract file changes (similar to Aider pattern)
        suspected_paths: list[str] = []
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^'\"]+)['\"]?",
            r"file:\s*['\"]?([^'\"]+)['\"]?",
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, combined_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        # Deduplicate paths
        suspected_paths = list(set(suspected_paths))

        # FIX: File system verification to prevent false negatives
        # Regex patterns can fail to match all CLI output formats, so we verify
        # files actually exist on disk and fall back to filesystem scanning
        # Only perform verification if repo_root is provided
        if repo_root:
            verified_paths: list[str] = []
            for path in suspected_paths:
                full_path = Path(repo_root) / path
                try:
                    if full_path.exists():
                        verified_paths.append(path)
                    else:
                        logger.warning(f"Path mentioned in output but not found: {path}")
                except (OSError, ValueError) as e:
                    logger.warning(f"Error checking path {path}: {e}")

            suspected_paths = verified_paths

            # If regex found nothing and task succeeded, scan for recent file changes
            # This fallback catches files when regex pattern matching fails
            if not suspected_paths and success:
                cutoff_time = time.time() - 60  # Files modified in last 60 seconds
                recent_files: list[str] = []
                try:
                    for root, dirs, files in os.walk(repo_root):
                        # Skip hidden directories (including .git, .cache, etc.)
                        dirs[:] = [d for d in dirs if not d.startswith(".")]
                        for file in files:
                            file_path = Path(root) / file
                            try:
                                if file_path.stat().st_mtime > cutoff_time:
                                    recent_files.append(str(file_path.relative_to(repo_root)))
                            except (OSError, ValueError):
                                # Skip files we can't stat (permission errors, etc.)
                                continue

                    if recent_files:
                        suspected_paths = recent_files[:10]  # Limit to 10 most recent
                        logger.info(
                            f"Detected {len(recent_files)} recently modified files via filesystem scan"
                        )
                except Exception as e:
                    logger.warning(f"Filesystem scan failed: {e}")

        # Detect Antigravity-specific errors (comprehensive)
        agy_error_patterns = [
            # Authentication and authorization errors (HIGH PRIORITY)
            r"AuthenticationError",
            r"authentication\s+failed",
            r"User\s+not\s+found",
            r"Unauthorized",
            r"401",
            r"403\s+Forbidden",
            r"invalid\s+api\s+key",
            r"api\s+key.*?(not\s+found|invalid|missing)",
            # Credit and billing errors (HIGH PRIORITY)
            r"insufficient\s+credits",
            r"requires\s+more\s+credits",
            r"can\s+only\s+afford",
            r"credit\s+limit",
            r"billing\s+error",
            r"payment\s+required",
            # General API errors (HIGH PRIORITY)
            r"APIError",
            r"api\s+error",
            r"API\s+request\s+failed",
            # Rate limiting and quotas
            r"rate\s+limit",
            r"quota\s+exceeded",
            r"context\s+limit",
            r"timeout",
            # Model errors
            r"model\s+not\s+found",
            r"invalid\s+model",
        ]

        retryable_error = False
        error_msg = ""

        for pattern in agy_error_patterns:
            match = re.search(pattern, combined_output, re.IGNORECASE)
            if match:
                # Rate limits and timeouts are retryable
                if any(
                    retry_word in pattern.lower() for retry_word in ["rate", "timeout", "quota"]
                ):
                    retryable_error = True

                # Extract context around error
                start = max(0, match.start() - 80)
                end = min(len(combined_output), match.end() + 80)
                error_msg = combined_output[start:end].strip()
                error_msg = " ".join(error_msg.split())
                break

        # Build summary
        if success:
            if suspected_paths:
                file_count = len(suspected_paths)
                file_list = ", ".join(suspected_paths[:5])
                if file_count > 5:
                    file_list += f" and {file_count - 5} more"
                summary = f"✅ Modified {file_count} file(s): {file_list}"
            else:
                summary = "✅ Task completed successfully"
        else:
            summary = "❌ Task failed"

        # Build notes
        notes = ""
        if not success:
            # Priority 0: Authentication and credit errors (most critical)
            if any(
                pattern in combined_output
                for pattern in [
                    "AuthenticationError",
                    "User not found",
                    "Unauthorized",
                    "401",
                ]
            ):
                notes = "❌ Authentication failed. Check API key configuration or verify account status."
                summary = "❌ Authentication error"
            elif any(
                pattern in combined_output
                for pattern in ["insufficient credits", "requires more credits", "can only afford"]
            ):
                notes = "💰 Insufficient credits. Add credits or reduce max_tokens."
                summary = "❌ Insufficient credits"
            # Priority 1: Error message from pattern matching
            elif error_msg:
                notes = error_msg[:200]
            # Priority 2: Last line from stderr
            elif stderr:
                error_lines = [line.strip() for line in stderr.split("\n") if line.strip()]
                if error_lines:
                    notes = error_lines[-1][:200]

        # Final validation: If we claim success but no files were touched, it's suspicious
        # NOTE: This only triggers if BOTH regex pattern matching AND filesystem scan found nothing
        if success and not suspected_paths and len(combined_output) > 100:
            # Check if output suggests files should have been created/modified
            action_keywords = ["write", "creat", "modif", "updat", "edit", "add", "implement"]
            has_action_intent = any(
                keyword in combined_output.lower() for keyword in action_keywords
            )

            # If there was intent to modify files but none were touched (neither via
            # regex patterns nor filesystem scan), mark as failure
            if has_action_intent:
                success = False
                summary = "⚠️ Task completed but no files were modified"
                notes = (
                    "CLI exited successfully but no file changes detected. Check logs for details."
                )
                logger.warning("Suspicious success: exit_code=0 but no files touched")

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
        """Determine if Antigravity execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Process exit code.

        Returns:
            True if error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code, repo_root=None)
        return result.retryable_error

    def get_timeout(self, task_type: str) -> int:
        """Get timeout for Antigravity based on task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base_timeout = int(os.environ.get("NINJA_AGY_TIMEOUT", "300"))

        base_task_type = task_type.removesuffix("_plan")
        if base_task_type == "parallel":
            # Antigravity is fast, can handle parallel efficiently
            return base_timeout
        elif base_task_type == "quick":
            # Quick tasks can be faster
            return base_timeout // 2

        return base_timeout
