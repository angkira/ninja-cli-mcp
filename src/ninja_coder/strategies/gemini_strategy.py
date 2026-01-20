"""
Gemini CLI strategy implementation.

This module implements the CLI strategy for Google Gemini,
which provides fast, accurate code completion and editing.
"""

from __future__ import annotations

import os
import re
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


class GeminiStrategy:
    """Strategy for Google Gemini CLI tool.

    Gemini provides fast code completion and editing capabilities.
    Key features:
    - Fast response times (Google infrastructure)
    - Strong code comprehension
    - Multi-language support
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Gemini strategy.

        Args:
            bin_path: Path to Gemini binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config
        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=True,  # Supports model selection
            supports_native_zai=False,
            supports_dialogue_mode=False,  # Gemini uses atomic mode
            max_context_files=50,
            preferred_task_types=["quick", "sequential"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "gemini"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Gemini CLI."""
        return self._capabilities

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        """Build Gemini command with model and context support.

        Args:
            prompt: The instruction prompt for the CLI.
            repo_root: Repository root path (used for working directory context).
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: Additional CLI-specific flags (unused for Gemini).

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model

        cmd = [
            self.bin_path,
            "--model",
            model_name,
        ]

        # Add API key if configured
        if self.config.openai_api_key:
            cmd.extend(["--api-key", self.config.openai_api_key])

        # Add file paths for context
        if file_paths:
            for file_path in file_paths:
                cmd.extend(["--file", file_path])

        # Add prompt
        cmd.extend(["--message", prompt])

        # Build environment
        env = os.environ.copy()

        # Set model for Gemini
        if self.config.openai_base_url:
            env["OPENAI_BASE_URL"] = self.config.openai_base_url
        if self.config.openai_api_key:
            env["OPENAI_API_KEY"] = self.config.openai_api_key
        env["OPENAI_MODEL"] = model_name

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "model": model_name,
                "provider": "gemini",
                "timeout": self.get_timeout("quick"),
            },
        )

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> ParsedResult:
        """Parse Gemini output to extract results.

        Args:
            stdout: Standard output from Gemini execution.
            stderr: Standard error from Gemini execution.
            exit_code: Process exit code.

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

        # Detect Gemini-specific errors
        gemini_error_patterns = [
            r"api\s+error",
            r"rate\s+limit",
            r"quota\s+exceeded",
            r"context\s+limit",
            r"timeout",
            r"authentication\s+failed",
            r"model\s+not\s+found",
            r"invalid\s+api\s+key",
        ]

        retryable_error = False
        error_msg = ""

        for pattern in gemini_error_patterns:
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
        if not success and error_msg:
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
        """Determine if Gemini execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Process exit code.

        Returns:
            True if error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code)
        return result.retryable_error

    def get_timeout(self, task_type: str) -> int:
        """Get timeout for Gemini based on task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        base_timeout = int(os.environ.get("NINJA_GEMINI_TIMEOUT", "300"))

        if task_type == "parallel":
            # Gemini is fast, can handle parallel efficiently
            return base_timeout
        elif task_type == "quick":
            # Quick tasks can be faster
            return base_timeout // 2

        return base_timeout
