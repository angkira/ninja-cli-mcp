"""
Base protocol and models for CLI strategy pattern.

This module defines the interface that all CLI strategies must implement,
along with shared data models used across strategies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class CLICapabilities:
    """Capabilities of a CLI tool."""

    supports_streaming: bool
    """Whether the CLI supports streaming output."""

    supports_file_context: bool
    """Whether the CLI supports explicit file context."""

    supports_model_routing: bool
    """Whether the CLI supports model routing/selection."""

    supports_native_zai: bool
    """Whether the CLI has native z.ai support."""

    supports_dialogue_mode: bool = False
    """Whether the CLI supports persistent dialogue sessions across multiple steps."""

    max_context_files: int = 50
    """Maximum number of files that can be in context."""

    preferred_task_types: list[str] = field(default_factory=list)
    """Preferred task types for this CLI (e.g., ['parallel', 'sequential', 'quick'])."""


@dataclass
class CLICommandResult:
    """Result from building a CLI command."""

    command: list[str]
    """The command to execute as a list of arguments."""

    env: dict[str, str]
    """Environment variables for the command."""

    working_dir: Path
    """Working directory path for command execution."""

    metadata: dict[str, Any] = field(default_factory=dict)
    """CLI-specific metadata (timeouts, flags, etc.)."""


@dataclass
class ParsedResult:
    """Parsed result from CLI output."""

    success: bool
    """Whether the task completed successfully."""

    summary: str
    """Brief summary of what was done."""

    notes: str
    """Additional notes or warnings."""

    touched_paths: list[str] = field(default_factory=list)
    """File paths that were likely modified."""

    retryable_error: bool = False
    """Whether the error is retryable."""

    session_id: str | None = None
    """OpenCode session ID extracted from output (if available)."""


class CLIStrategy(Protocol):
    """Protocol defining the interface for CLI strategies.

    All CLI implementations (Aider, OpenCode, etc.) must implement this interface.
    """

    @property
    def name(self) -> str:
        """CLI tool name (e.g., 'aider', 'opencode')."""
        ...

    @property
    def capabilities(self) -> CLICapabilities:
        """Return capabilities of this CLI."""
        ...

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
        """Build command for executing this CLI.

        Args:
            prompt: The instruction prompt for the CLI.
            repo_root: Repository root path.
            file_paths: List of files to include in context.
            model: Model to use (if None, use configured default).
            additional_flags: CLI-specific flags and options.
            session_id: Session ID to continue (OpenCode-specific).
            continue_last: Continue last session (OpenCode-specific).

        Returns:
            CLICommandResult with command, env, and metadata.
        """
        ...

    def parse_output(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
        repo_root: str | None = None,
    ) -> ParsedResult:
        """Parse CLI output to extract results.

        Args:
            stdout: Standard output from CLI execution.
            stderr: Standard error from CLI execution.
            exit_code: Exit code from CLI execution.
            repo_root: Optional repository root for resolving file paths.

        Returns:
            ParsedResult with success status, summary, and file changes.
        """
        ...

    def should_retry(
        self,
        stdout: str,
        stderr: str,
        exit_code: int,
    ) -> bool:
        """Determine if execution should be retried.

        Args:
            stdout: Standard output from CLI execution.
            stderr: Standard error from CLI execution.
            exit_code: Exit code from CLI execution.

        Returns:
            True if the error is retryable, False otherwise.
        """
        ...

    def get_timeout(self, task_type: str) -> int:
        """Get recommended timeout for task type.

        Args:
            task_type: Type of task ('quick', 'sequential', 'parallel').

        Returns:
            Timeout in seconds.
        """
        ...
