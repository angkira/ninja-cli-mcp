"""
Security utilities for MCP server.

Implements rate limiting, input validation, and resource monitoring
according to MCP best practices (December 2025).
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import defaultdict
from functools import wraps
from pathlib import Path
from typing import Any, Callable, TypeVar

from ninja_cli_mcp.logging_utils import get_logger


logger = get_logger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


class RateLimiter:
    """
    Rate limiter for API calls.

    Implements sliding window rate limiting to prevent abuse.
    """

    def __init__(self, max_calls: int = 100, time_window: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in time window.
            time_window: Time window in seconds.
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check_limit(self, client_id: str = "default") -> bool:
        """
        Check if request is within rate limit.

        Args:
            client_id: Identifier for the client (for per-client limits).

        Returns:
            True if within limit, False if exceeded.
        """
        async with self._lock:
            now = time.time()
            client_calls = self.calls[client_id]

            # Remove calls outside the time window
            client_calls[:] = [call_time for call_time in client_calls if call_time > now - self.time_window]

            if len(client_calls) >= self.max_calls:
                logger.warning(
                    f"Rate limit exceeded for client {client_id}: "
                    f"{len(client_calls)} calls in last {self.time_window}s"
                )
                return False

            client_calls.append(now)
            return True

    def reset(self, client_id: str = "default") -> None:
        """Reset rate limit for a client."""
        if client_id in self.calls:
            del self.calls[client_id]


# Global rate limiter instance
_rate_limiter = RateLimiter(max_calls=100, time_window=60)


def rate_limited(max_calls: int = 100, time_window: int = 60, client_id: str = "default"):
    """
    Decorator for rate-limiting async functions.

    Args:
        max_calls: Maximum number of calls allowed in time window.
        time_window: Time window in seconds.
        client_id: Identifier for the client.

    Example:
        @rate_limited(max_calls=10, time_window=60)
        async def sensitive_operation():
            pass
    """

    def decorator(func: F) -> F:
        limiter = RateLimiter(max_calls=max_calls, time_window=time_window)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not await limiter.check_limit(client_id):
                raise PermissionError(
                    f"Rate limit exceeded: maximum {max_calls} calls per {time_window}s"
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


class InputValidator:
    """Validates and sanitizes user inputs to prevent injection attacks."""

    # Dangerous patterns that might indicate injection attempts
    DANGEROUS_PATTERNS = [
        r"(\||;|&|`|\$\(|\$\{)",  # Shell metacharacters
        r"(\.\.\/|\.\.\\)",  # Path traversal
        r"(<script|javascript:|on\w+=)",  # XSS attempts
        r"(--|\#|\/\*|\*\/)",  # SQL comment indicators
    ]

    @staticmethod
    def sanitize_path(path: str, base_dir: str | Path | None = None) -> Path:
        """
        Sanitize a file path to prevent path traversal attacks.

        Args:
            path: Path to sanitize.
            base_dir: Optional base directory to constrain path to.

        Returns:
            Sanitized Path object.

        Raises:
            ValueError: If path contains dangerous patterns or escapes base_dir.
        """
        # Convert to Path and resolve
        path_obj = Path(path).resolve()

        # Check for dangerous patterns
        path_str = str(path_obj)
        for pattern in InputValidator.DANGEROUS_PATTERNS[:2]:  # Check path-specific patterns
            if re.search(pattern, path_str):
                raise ValueError(f"Path contains potentially dangerous pattern: {path}")

        # If base_dir is provided, ensure path is within it
        if base_dir:
            base_path = Path(base_dir).resolve()
            try:
                path_obj.relative_to(base_path)
            except ValueError:
                raise ValueError(f"Path {path} is outside allowed directory {base_dir}")

        return path_obj

    @staticmethod
    def sanitize_string(value: str, max_length: int = 10000) -> str:
        """
        Sanitize a string input.

        Args:
            value: String to sanitize.
            max_length: Maximum allowed length.

        Returns:
            Sanitized string.

        Raises:
            ValueError: If string contains dangerous patterns or exceeds max length.
        """
        if len(value) > max_length:
            raise ValueError(f"Input exceeds maximum length of {max_length} characters")

        # Check for dangerous patterns
        for pattern in InputValidator.DANGEROUS_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                logger.warning(f"Input contains potentially dangerous pattern: {pattern}")
                # Don't raise here, just log - might be legitimate code

        return value

    @staticmethod
    def validate_repo_root(repo_root: str) -> Path:
        """
        Validate that a repository root is safe to use.

        Args:
            repo_root: Path to repository root.

        Returns:
            Validated Path object.

        Raises:
            ValueError: If path is not safe.
        """
        from ninja_cli_mcp.path_utils import validate_repo_root as _validate

        # Use existing validation
        path = _validate(repo_root)

        # Additional security checks
        path_str = str(path)

        # Don't allow certain sensitive directories
        sensitive_dirs = ["/etc", "/bin", "/sbin", "/usr/bin", "/usr/sbin", "/root", "/boot"]
        for sensitive in sensitive_dirs:
            if path_str.startswith(sensitive):
                raise ValueError(f"Repository root cannot be in sensitive directory: {sensitive}")

        return path


class ResourceMonitor:
    """Monitor resource usage to prevent abuse."""

    def __init__(self):
        """Initialize resource monitor."""
        self.task_count = 0
        self.total_duration = 0.0
        self.start_time = time.time()

    def record_task(self, duration: float) -> None:
        """Record a task execution."""
        self.task_count += 1
        self.total_duration += duration

    def get_stats(self) -> dict[str, Any]:
        """Get current resource stats."""
        uptime = time.time() - self.start_time
        avg_duration = self.total_duration / max(self.task_count, 1)

        return {
            "uptime_seconds": uptime,
            "total_tasks": self.task_count,
            "total_duration": self.total_duration,
            "average_task_duration": avg_duration,
            "tasks_per_minute": (self.task_count / uptime) * 60 if uptime > 0 else 0,
        }

    async def check_resources(self, warn_threshold: float = 0.8) -> dict[str, Any]:
        """
        Check system resources.

        Args:
            warn_threshold: Threshold for warning (0.0-1.0).

        Returns:
            Dictionary with resource information.
        """
        stats = {
            "healthy": True,
            "warnings": [],
        }

        try:
            import psutil

            # Check memory
            memory = psutil.virtual_memory()
            stats["memory_percent"] = memory.percent
            if memory.percent > warn_threshold * 100:
                stats["healthy"] = False
                stats["warnings"].append(f"High memory usage: {memory.percent:.1f}%")
                logger.warning(f"High memory usage: {memory.percent:.1f}%")

            # Check CPU
            cpu_percent = psutil.cpu_percent(interval=0.1)
            stats["cpu_percent"] = cpu_percent
            if cpu_percent > warn_threshold * 100:
                stats["warnings"].append(f"High CPU usage: {cpu_percent:.1f}%")
                logger.warning(f"High CPU usage: {cpu_percent:.1f}%")

        except ImportError:
            logger.debug("psutil not available, skipping resource monitoring")
            stats["psutil_available"] = False

        return stats


# Global resource monitor
_resource_monitor = ResourceMonitor()


def get_resource_monitor() -> ResourceMonitor:
    """Get the global resource monitor instance."""
    return _resource_monitor


def monitored(func: F) -> F:
    """
    Decorator to monitor resource usage of async functions.

    Example:
        @monitored
        async def expensive_operation():
            pass
    """

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        monitor = get_resource_monitor()
        start_time = time.time()

        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            monitor.record_task(duration)

            # Check resources periodically
            if monitor.task_count % 10 == 0:
                stats = await monitor.check_resources()
                if not stats["healthy"]:
                    logger.warning(f"Resource warnings: {stats['warnings']}")

    return wrapper  # type: ignore
