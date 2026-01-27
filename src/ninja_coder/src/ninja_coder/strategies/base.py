"""
Base classes for CLI strategy pattern.

Defines the protocol and data classes for implementing different CLI strategies.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol


if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class CLICapabilities:
    """
    Represents the capabilities of a CLI tool.

    Attributes:
        supports_streaming: Whether the CLI supports streaming output
        supports_file_context: Whether the CLI supports file context
        supports_model_routing: Whether the CLI supports model routing
        supports_native_zai: Whether the CLI has native ZAI support
        max_context_files: Maximum number of context files supported
        preferred_task_types: List of preferred task types for this CLI
    """

    supports_streaming: bool
    supports_file_context: bool
    supports_model_routing: bool
    supports_native_zai: bool
    max_context_files: int
    preferred_task_types: list[str]


@dataclass
class CLICommandResult:
    """
    Result of building a CLI command.

    Attributes:
        command: The command to execute as a list of strings
        env: Environment variables for the command
        working_dir: Working directory path
        metadata: CLI-specific metadata
    """

    command: list[str]
    env: dict[str, str]
    working_dir: Path
    metadata: dict[str, Any]


@dataclass
class ParsedResult:
    """
    Parsed result from CLI output.

    Attributes:
        success: Whether the task was successful
        summary: Brief summary of what was done
        notes: Additional notes
        touched_paths: File paths that were modified
        retryable_error: Whether the error is retryable
    """

    success: bool
    summary: str
    notes: str
    touched_paths: list[str]
    retryable_error: bool


class CLIStrategy(Protocol):
    """
    Protocol defining the interface for CLI strategies.
    """

    @property
    def name(self) -> str:
        """Get the CLI tool name."""
        ...

    @property
    def capabilities(self) -> CLICapabilities:
        """Get the CLI capabilities."""
        ...

    def build_command(
        self,
        prompt: str,
        repo_root: str,
        file_paths: list[str] | None = None,
        model: str | None = None,
        additional_flags: dict[str, Any] | None = None,
    ) -> CLICommandResult:
        """
        Build a CLI command for the given parameters.

        Args:
            prompt: The prompt or task description
            repo_root: Absolute path to repository root
            file_paths: Optional list of file paths to include as context
            model: Optional model to use
            additional_flags: Optional additional CLI flags

        Returns:
            CLICommandResult with the built command
        """
        ...

    def parse_output(self, stdout: str, stderr: str, exit_code: int) -> ParsedResult:
        """
        Parse CLI output into a structured result.

        Args:
            stdout: Standard output from CLI
            stderr: Standard error from CLI
            exit_code: Exit code from CLI

        Returns:
            ParsedResult with structured output
        """
        ...

    def should_retry(self, stdout: str, stderr: str, exit_code: int) -> bool:
        """
        Determine if the command should be retried based on output.

        Args:
            stdout: Standard output from CLI
            stderr: Standard error from CLI
            exit_code: Exit code from CLI

        Returns:
            True if command should be retried, False otherwise
        """
        ...

    def get_timeout(self, task_type: str) -> int:
        """
        Get timeout for a specific task type.

        Args:
            task_type: Type of task (e.g., "parallel", "sequential", "quick")

        Returns:
            Timeout in seconds
        """
        ...
