"""
Logging utilities for ninja-cli-mcp.

Provides structured logging with file output for debugging and audit trails.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ninja_cli_mcp.path_utils import ensure_internal_dirs


# Configure root logger
def setup_logging(
    level: int = logging.INFO,
    log_to_stderr: bool = True,
) -> logging.Logger:
    """
    Set up logging for the MCP server.

    Args:
        level: Logging level.
        log_to_stderr: Whether to also log to stderr.

    Returns:
        Configured logger instance.
    """
    logger = logging.getLogger("ninja_cli_mcp")
    logger.setLevel(level)

    # Clear existing handlers
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    if log_to_stderr:
        # Log to stderr (stdout is reserved for MCP protocol)
        stderr_handler = logging.StreamHandler(sys.stderr)
        stderr_handler.setLevel(level)
        stderr_handler.setFormatter(formatter)
        logger.addHandler(stderr_handler)

    return logger


def get_logger(name: str = "ninja_cli_mcp") -> logging.Logger:
    """Get a logger instance."""
    return logging.getLogger(name)


class TaskLogger:
    """
    Logger for individual task executions.

    Writes detailed logs to centralized cache directory:
    ~/.cache/ninja-cli-mcp/<repo_hash>-<repo_name>/logs/
    
    This prevents polluting project directories with log files.
    """

    def __init__(self, repo_root: str | Path, step_id: str):
        """
        Initialize task logger.

        Args:
            repo_root: Repository root path.
            step_id: Step identifier for the log file.
        """
        self.repo_root = Path(repo_root)
        self.step_id = step_id
        self.timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

        # Ensure directories exist
        dirs = ensure_internal_dirs(repo_root)
        self.logs_dir = dirs["logs"]

        # Create log file path
        safe_step_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in step_id)
        self.log_file = self.logs_dir / f"{self.timestamp}_{safe_step_id}.log"

        # Also create a JSON metadata file
        self.metadata_file = self.logs_dir / f"{self.timestamp}_{safe_step_id}.json"

        self._entries: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {
            "step_id": step_id,
            "timestamp": self.timestamp,
            "repo_root": str(self.repo_root),
        }

    def log(self, level: str, message: str, **extra: Any) -> None:
        """
        Log a message.

        Args:
            level: Log level (INFO, WARNING, ERROR, DEBUG).
            message: Log message.
            **extra: Additional context to include.
        """
        entry = {
            "time": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "message": message,
            **extra,
        }
        self._entries.append(entry)

        # Also log to the main logger
        logger = get_logger()
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"[{self.step_id}] {message}")

    def info(self, message: str, **extra: Any) -> None:
        """Log an info message."""
        self.log("INFO", message, **extra)

    def warning(self, message: str, **extra: Any) -> None:
        """Log a warning message."""
        self.log("WARNING", message, **extra)

    def error(self, message: str, **extra: Any) -> None:
        """Log an error message."""
        self.log("ERROR", message, **extra)

    def debug(self, message: str, **extra: Any) -> None:
        """Log a debug message."""
        self.log("DEBUG", message, **extra)

    def set_metadata(self, key: str, value: Any) -> None:
        """Set metadata for this task."""
        self._metadata[key] = value

    def log_subprocess(
        self,
        command: list[str],
        exit_code: int,
        stdout: str,
        stderr: str,
    ) -> None:
        """
        Log subprocess execution details.

        Args:
            command: Command that was run.
            exit_code: Process exit code.
            stdout: Standard output.
            stderr: Standard error.
        """
        self.info(
            "Subprocess completed",
            command=command,
            exit_code=exit_code,
            stdout_length=len(stdout),
            stderr_length=len(stderr),
        )

        # Store full output in metadata
        self._metadata["subprocess"] = {
            "command": command,
            "exit_code": exit_code,
            "stdout": stdout,
            "stderr": stderr,
        }

    def save(self) -> str:
        """
        Save logs to files.

        Returns:
            Path to the log file.
        """
        # Write human-readable log
        with open(self.log_file, "w") as f:
            for entry in self._entries:
                ts = entry.get("time", "")
                level = entry.get("level", "INFO")
                msg = entry.get("message", "")
                f.write(f"[{ts}] {level}: {msg}\n")

                # Write extra fields
                for key, value in entry.items():
                    if key not in ("time", "level", "message"):
                        f.write(f"  {key}: {value}\n")

        # Write JSON metadata
        self._metadata["entries"] = self._entries
        with open(self.metadata_file, "w") as f:
            json.dump(self._metadata, f, indent=2, default=str)

        return str(self.log_file)

    @property
    def log_path(self) -> str:
        """Get the log file path."""
        return str(self.log_file)


def create_task_logger(repo_root: str | Path, step_id: str) -> TaskLogger:
    """
    Create a task logger.

    Args:
        repo_root: Repository root path.
        step_id: Step identifier.

    Returns:
        TaskLogger instance.
    """
    return TaskLogger(repo_root, step_id)
