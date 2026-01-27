"""
Structured logging system with JSONL output and query interface.

Provides comprehensive logging for debugging, analysis, and monitoring
with rich metadata and fast query capabilities.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from pathlib import Path


logger = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Structured log entry with rich metadata."""

    timestamp: str
    level: str
    logger_name: str
    message: str
    session_id: str | None = None
    task_id: str | None = None
    cli_name: str | None = None
    model: str | None = None
    extra: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict, excluding None values.

        Returns:
            Dict with non-None fields only.
        """
        data = asdict(self)
        return {k: v for k, v in data.items() if v is not None}


class StructuredLogger:
    """Logger with structured JSONL output for debugging and analysis."""

    def __init__(self, name: str, log_dir: Path):
        """Initialize structured logger.

        Args:
            name: Logger name.
            log_dir: Directory for log files.
        """
        self.name = name
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create daily log file
        today = datetime.now(UTC).strftime("%Y%m%d")
        self.log_file = log_dir / f"ninja-{today}.jsonl"

        # Standard logger for console output
        self.console_logger = logging.getLogger(name)

        logger.info(f"StructuredLogger initialized: {self.log_file}")

    def log(
        self,
        level: str,
        message: str,
        session_id: str | None = None,
        task_id: str | None = None,
        cli_name: str | None = None,
        model: str | None = None,
        **extra,
    ):
        """Log structured entry.

        Args:
            level: Log level (INFO, DEBUG, WARNING, ERROR).
            message: Log message.
            session_id: Optional session identifier.
            task_id: Optional task identifier.
            cli_name: Optional CLI name.
            model: Optional model name.
            **extra: Additional fields to log.
        """
        entry = LogEntry(
            timestamp=datetime.now(UTC).isoformat(),
            level=level,
            logger_name=self.name,
            message=message,
            session_id=session_id,
            task_id=task_id,
            cli_name=cli_name,
            model=model,
            extra=extra if extra else None,
        )

        # Write to JSONL file
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry.to_dict()) + "\n")
        except Exception as e:
            logger.error(f"Failed to write log entry: {e}")

        # Also log to console
        console_level = getattr(logging, level, logging.INFO)
        self.console_logger.log(console_level, message)

    def info(self, message: str, **kwargs):
        """Log INFO level.

        Args:
            message: Log message.
            **kwargs: Additional fields.
        """
        self.log("INFO", message, **kwargs)

    def debug(self, message: str, **kwargs):
        """Log DEBUG level.

        Args:
            message: Log message.
            **kwargs: Additional fields.
        """
        self.log("DEBUG", message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log WARNING level.

        Args:
            message: Log message.
            **kwargs: Additional fields.
        """
        self.log("WARNING", message, **kwargs)

    def error(self, message: str, **kwargs):
        """Log ERROR level.

        Args:
            message: Log message.
            **kwargs: Additional fields.
        """
        self.log("ERROR", message, **kwargs)

    def log_command(
        self,
        command: list[str],
        session_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ):
        """Log CLI command execution.

        Args:
            command: Command list.
            session_id: Optional session identifier.
            task_id: Optional task identifier.
            **kwargs: Additional fields.
        """
        # Redact sensitive data
        safe_cmd = self._redact_command(command)

        self.log(
            "INFO",
            f"Executing: {' '.join(safe_cmd[:3])}...",
            session_id=session_id,
            task_id=task_id,
            command=safe_cmd,
            **kwargs,
        )

    def log_result(
        self,
        success: bool,
        summary: str,
        session_id: str | None = None,
        task_id: str | None = None,
        **kwargs,
    ):
        """Log task result.

        Args:
            success: Whether task succeeded.
            summary: Result summary.
            session_id: Optional session identifier.
            task_id: Optional task identifier.
            **kwargs: Additional fields.
        """
        level = "INFO" if success else "ERROR"
        self.log(
            level,
            summary,
            session_id=session_id,
            task_id=task_id,
            success=success,
            **kwargs,
        )

    def log_multi_agent(
        self,
        agents: list[str],
        task_id: str | None = None,
        session_id: str | None = None,
        **kwargs,
    ):
        """Log multi-agent activation.

        Args:
            agents: List of agent names.
            task_id: Optional task identifier.
            session_id: Optional session identifier.
            **kwargs: Additional fields.
        """
        self.log(
            "INFO",
            f"🤖 Multi-agent activated: {', '.join(agents)}",
            task_id=task_id,
            session_id=session_id,
            agents=agents,
            agent_count=len(agents),
            **kwargs,
        )

    def log_session(
        self,
        action: str,
        session_id: str,
        **kwargs,
    ):
        """Log session action.

        Args:
            action: Action type (created, loaded, saved, deleted).
            session_id: Session identifier.
            **kwargs: Additional fields.
        """
        self.log(
            "INFO",
            f"Session {action}: {session_id}",
            session_id=session_id,
            action=action,
            **kwargs,
        )

    def query_logs(
        self,
        session_id: str | None = None,
        task_id: str | None = None,
        cli_name: str | None = None,
        level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query logs with filters.

        Args:
            session_id: Filter by session ID.
            task_id: Filter by task ID.
            cli_name: Filter by CLI name.
            level: Filter by log level.
            limit: Maximum number of entries to return.
            offset: Number of entries to skip.

        Returns:
            List of log entries as dicts.
        """
        if not self.log_file.exists():
            return []

        results = []
        skipped = 0

        try:
            with open(self.log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        # Apply filters
                        if session_id and entry.get("session_id") != session_id:
                            continue
                        if task_id and entry.get("task_id") != task_id:
                            continue
                        if cli_name and entry.get("cli_name") != cli_name:
                            continue
                        if level and entry.get("level") != level:
                            continue

                        # Apply offset
                        if skipped < offset:
                            skipped += 1
                            continue

                        results.append(entry)

                        if len(results) >= limit:
                            break
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to query logs: {e}")

        return results

    def count_logs(
        self,
        session_id: str | None = None,
        task_id: str | None = None,
        cli_name: str | None = None,
        level: str | None = None,
    ) -> int:
        """Count logs matching filters.

        Args:
            session_id: Filter by session ID.
            task_id: Filter by task ID.
            cli_name: Filter by CLI name.
            level: Filter by log level.

        Returns:
            Count of matching entries.
        """
        if not self.log_file.exists():
            return 0

        count = 0

        try:
            with open(self.log_file) as f:
                for line in f:
                    try:
                        entry = json.loads(line)

                        # Apply filters
                        if session_id and entry.get("session_id") != session_id:
                            continue
                        if task_id and entry.get("task_id") != task_id:
                            continue
                        if cli_name and entry.get("cli_name") != cli_name:
                            continue
                        if level and entry.get("level") != level:
                            continue

                        count += 1
                    except json.JSONDecodeError:
                        continue
        except Exception as e:
            logger.error(f"Failed to count logs: {e}")

        return count

    def get_recent_errors(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent error log entries.

        Args:
            limit: Maximum number of errors to return.

        Returns:
            List of error log entries.
        """
        return self.query_logs(level="ERROR", limit=limit)

    def get_session_logs(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Get all logs for a specific session.

        Args:
            session_id: Session identifier.
            limit: Maximum number of entries.

        Returns:
            List of log entries for the session.
        """
        return self.query_logs(session_id=session_id, limit=limit)

    def _redact_command(self, command: list[str]) -> list[str]:
        """Redact sensitive information from command.

        Args:
            command: Command list.

        Returns:
            Command with sensitive data redacted.
        """
        redacted = []
        redact_next = False

        for arg in command:
            if redact_next:
                redacted.append("***REDACTED***")
                redact_next = False
            elif any(
                sensitive in arg.lower() for sensitive in ["api-key", "password", "token", "secret"]
            ):
                if "=" in arg:
                    # Handle --api-key=value format
                    key = arg.split("=")[0]
                    redacted.append(f"{key}=***REDACTED***")
                else:
                    # Handle --api-key value format
                    redacted.append(arg)
                    redact_next = True
            else:
                redacted.append(arg)

        return redacted
