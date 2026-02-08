"""
Claude Code CLI strategy implementation with native Anthropic support.

This module implements the CLI strategy for Claude Code, providing native
support for Anthropic's official Claude CLI tool.
"""

from __future__ import annotations

import os
import re
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


# Claude Code models (Anthropic only)
CLAUDE_CODE_MODELS = [
    ("claude-sonnet-4", "Claude Sonnet 4", "Latest Claude - Balanced performance"),
    ("claude-opus-4", "Claude Opus 4", "Most powerful Claude model"),
    ("claude-haiku-4", "Claude Haiku 4", "Fast & cost-effective"),
]


def check_claude_auth() -> bool:
    """Check if Claude Code is authenticated.

    Returns:
        True if authenticated, False otherwise.
    """
    try:
        result = subprocess.run(
            ["claude", "auth", "status"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # Claude auth status returns 0 when authenticated
        return result.returncode == 0
    except Exception:
        return False


class ClaudeStrategy:
    """Strategy for Claude Code CLI with native Anthropic support.

    Claude Code is Anthropic's official CLI tool that provides direct access
    to Claude models without requiring OpenRouter or other intermediaries.

    This strategy uses Claude Code in non-interactive mode for code generation
    and modification tasks.
    """

    def __init__(self, bin_path: str, config: NinjaConfig):
        """Initialize Claude Code strategy.

        Args:
            bin_path: Path to the Claude Code binary.
            config: Ninja configuration object.
        """
        self.bin_path = bin_path
        self.config = config

        self._capabilities = CLICapabilities(
            supports_streaming=True,
            supports_file_context=True,
            supports_model_routing=False,  # Anthropic only
            supports_native_zai=False,  # Claude Code doesn't support z.ai
            supports_dialogue_mode=True,  # Supports conversation continuity
            max_context_files=100,
            preferred_task_types=["sequential", "quick"],
        )

    @property
    def name(self) -> str:
        """CLI tool name."""
        return "claude"

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of Claude Code CLI."""
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
        """Build Claude Code command.

        Args:
            prompt: The instruction prompt.
            repo_root: Repository root path.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: Additional flags.
            session_id: Session ID to continue (for conversation continuity).
            continue_last: Continue last session.

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        model_name = model or self.config.model or "claude-sonnet-4"

        # Map short model names to full model names if needed
        model_mapping = {
            "claude-sonnet-4": "claude-sonnet-4-20250514",
            "claude-opus-4": "claude-opus-4-20250514",
            "claude-haiku-4": "claude-haiku-4-20250514",
            "sonnet": "claude-sonnet-4-20250514",
            "opus": "claude-opus-4-20250514",
            "haiku": "claude-haiku-4-20250514",
        }

        # Use mapping if available, otherwise use as-is
        full_model = model_mapping.get(model_name, model_name)

        # Build command using claude CLI
        # Format: claude --model MODEL --print "PROMPT"
        # The --print flag outputs the response directly without interactive UI
        cmd = [
            self.bin_path,
            "--model",
            full_model,
            "--print",  # Non-interactive output
            "--dangerously-skip-permissions",  # Allow file modifications
        ]

        # Add file context if provided
        if file_paths:
            for file_path in file_paths:
                cmd.extend(["--allowedTools", f"Read:{file_path}"])
                cmd.extend(["--allowedTools", f"Edit:{file_path}"])
                cmd.extend(["--allowedTools", f"Write:{file_path}"])

        # Add working directory context
        cmd.extend(["--allowedTools", "Bash"])

        # Build enhanced prompt with file context
        final_prompt = prompt
        if file_paths:
            files_text = ", ".join(file_paths)
            final_prompt = f"{prompt}\n\nFocus on these files: {files_text}"

        # Add prompt as the final argument
        cmd.append(final_prompt)

        # Build environment (inherit current environment)
        env = os.environ.copy()

        # Claude Code timeout
        base_timeout = int(os.environ.get("NINJA_CLAUDE_TIMEOUT", "600"))

        return CLICommandResult(
            command=cmd,
            env=env,
            working_dir=Path(repo_root),
            metadata={
                "provider": "anthropic",
                "model": full_model,
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
        """Parse Claude Code output.

        Args:
            stdout: Standard output from Claude Code execution.
            stderr: Standard error from Claude Code execution.
            exit_code: Exit code from Claude Code execution.

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        success = exit_code == 0
        combined_output = stdout + "\n" + stderr

        # Claude Code error patterns
        error_patterns = [
            r"AuthenticationError",
            r"authentication\s+failed",
            r"not\s+authenticated",
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
                # Rate limits and timeouts are retryable
                if any(
                    retry_pattern in pattern
                    for retry_pattern in [r"rate\s+limit", "timeout", r"connection\s+refused"]
                ):
                    retryable_error = True

                # Extract context around the error
                start = max(0, match.start() - 60)
                end = min(len(combined_output), match.end() + 60)
                error_msg = combined_output[start:end].strip()
                error_msg = " ".join(error_msg.split())
                break

        # Extract file changes
        # Strip ANSI color codes for easier pattern matching
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        clean_output = ansi_escape.sub("", combined_output)

        suspected_paths: list[str] = []
        file_patterns = [
            r"(?:wrote|created|modified|updated|edited)\s+['\"]?([^\s'\"]+)['\"]?",
            r"(?:writing|creating|modifying|updating|editing)\s+['\"]?([^\s'\"]+)['\"]?",
            r"file:\s*['\"]?([^\s'\"]+)['\"]?",
            # Claude Code tool call format
            r"\|\s+(?:Edit|Write)\s+([^\s]+)",
            r"Edited:\s+([^\s]+)",
            r"Created:\s+([^\s]+)",
        ]
        for pattern in file_patterns:
            matches = re.findall(pattern, clean_output, re.IGNORECASE)
            for match in matches:
                if match and ("/" in match or "." in match):
                    suspected_paths.append(match)

        # Deduplicate paths
        suspected_paths = list(set(suspected_paths))

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
        elif error_msg:
            summary = f"❌ Claude Code failed: {error_msg[:100]}"
        else:
            summary = "❌ Task failed"

        # Build notes from error messages
        notes = ""
        if not success:
            if (
                "not authenticated" in combined_output.lower()
                or "authentication" in combined_output.lower()
            ):
                notes = "❌ Authentication failed. Run 'claude auth' to authenticate."
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
        """Determine if Claude Code execution should be retried.

        Args:
            stdout: Standard output from execution.
            stderr: Standard error from execution.
            exit_code: Exit code from execution.

        Returns:
            True if the error is retryable, False otherwise.
        """
        result = self.parse_output(stdout, stderr, exit_code)
        return result.retryable_error

    def get_timeout(self, task_type: str) -> int:
        """Get recommended timeout for task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        return {
            "quick": 300,  # 5 minutes
            "sequential": 900,  # 15 minutes
            "parallel": 600,  # 10 minutes (Claude Code is single-threaded)
        }.get(task_type, 600)
