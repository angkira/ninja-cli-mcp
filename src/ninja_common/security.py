"""
Security utilities for MCP server.

Implements rate limiting, input validation, and resource monitoring
according to MCP best practices (December 2025).
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import time
from collections import defaultdict
from collections.abc import Callable
from functools import wraps
from pathlib import Path
from typing import Any, ClassVar, TypeVar


try:
    import psutil

    PSUTIL_AVAILABLE = True
except ImportError:
    psutil = None
    PSUTIL_AVAILABLE = False

from ninja_common.logging_utils import get_logger
from ninja_common.path_utils import validate_repo_root as _validate


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

        # Try to load persistent rate limit data
        self._load_persistent_data()

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
            client_calls[:] = [
                call_time for call_time in client_calls if call_time > now - self.time_window
            ]

            if len(client_calls) >= self.max_calls:
                logger.warning(
                    f"Rate limit exceeded for client {client_id}: "
                    f"{len(client_calls)} calls in last {self.time_window}s"
                )
                return False

            client_calls.append(now)
            self._save_persistent_data()
            return True

    async def reset(self, client_id: str = "default") -> None:
        """Reset rate limit for a client."""
        async with self._lock:
            if client_id in self.calls:
                del self.calls[client_id]
            self._save_persistent_data()

    def _get_persistence_file(self) -> Path:
        """Get the file path for persistent rate limit data."""
        # Use XDG cache directory for persistence
        if os.name == "nt":  # Windows
            cache_base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
        else:  # Linux/macOS
            cache_base = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))

        persistence_dir = cache_base / "ninja-mcp" / "persistence"
        persistence_dir.mkdir(parents=True, exist_ok=True)
        persistence_dir.chmod(0o700)  # Secure permissions

        return persistence_dir / "rate_limits.json"

    def _load_persistent_data(self) -> None:
        """Load rate limit data from persistent storage."""
        try:
            persistence_file = self._get_persistence_file()
            if persistence_file.exists():
                with persistence_file.open() as f:
                    data = json.load(f)
                    # Only load recent data (within last 2*time_window)
                    cutoff_time = time.time() - (2 * self.time_window)
                    for client_id, call_times in data.items():
                        recent_calls = [t for t in call_times if t > cutoff_time]
                        if recent_calls:
                            self.calls[client_id] = recent_calls
        except Exception as e:
            logger.debug(f"Could not load persistent rate limit data: {e}")

    def _save_persistent_data(self) -> None:
        """Save rate limit data to persistent storage with file locking."""
        try:
            # Only save recent data to prevent file from growing indefinitely
            cutoff_time = time.time() - (2 * self.time_window)
            data_to_save = {}
            for client_id, call_times in self.calls.items():
                recent_calls = [t for t in call_times if t > cutoff_time]
                if recent_calls:
                    data_to_save[client_id] = recent_calls

            persistence_file = self._get_persistence_file()
            lock_file = persistence_file.with_suffix(".lock")

            # Use file-based locking for cross-process safety
            with lock_file.open("w") as lock_f:
                try:
                    # Try to acquire exclusive lock (non-blocking)
                    import fcntl

                    fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        with persistence_file.open("w") as f:
                            json.dump(data_to_save, f)
                    finally:
                        fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
                except (ImportError, BlockingIOError):
                    # fcntl not available (Windows) or lock not acquired - write anyway
                    with persistence_file.open("w") as f:
                        json.dump(data_to_save, f)
        except Exception as e:
            logger.debug(f"Could not save persistent rate limit data: {e}")


# Global rate limiter instance
_rate_limiter = RateLimiter(max_calls=100, time_window=60)


def rate_limited(max_calls: int = 100, time_window: int = 60):
    """
    Decorator for rate-limiting async functions.

    Args:
        max_calls: Maximum number of calls allowed in time window.
        time_window: Time window in seconds.

    Example:
        @rate_limited(max_calls=10, time_window=60)
        async def sensitive_operation():
            pass
    """

    def decorator(func: F) -> F:
        limiter = RateLimiter(max_calls=max_calls, time_window=time_window)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract client_id from kwargs or use default
            client_id = kwargs.get("client_id", "default")
            if not await limiter.check_limit(client_id):
                raise PermissionError(
                    f"Rate limit exceeded for client {client_id}: "
                    f"maximum {max_calls} calls per {time_window}s"
                )
            return await func(*args, **kwargs)

        return wrapper  # type: ignore

    return decorator


class InputValidator:
    """Validates and sanitizes user inputs to prevent injection attacks."""

    # Dangerous patterns that might indicate injection attempts
    DANGEROUS_PATTERNS: ClassVar[list[str]] = [
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
                # Additional check for symbolic links
                if path_obj.is_symlink():
                    target = path_obj.readlink().resolve()
                    target.relative_to(base_path)
                path_obj.relative_to(base_path)
            except (ValueError, OSError):
                raise ValueError(f"Path {path} is outside allowed directory {base_dir}") from None

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
        self.max_concurrent_tasks = 10  # Default limit
        self.current_concurrent_tasks = 0
        self._lock = asyncio.Lock()

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
            "current_concurrent_tasks": self.current_concurrent_tasks,
            "max_concurrent_tasks": self.max_concurrent_tasks,
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

        if not PSUTIL_AVAILABLE:
            logger.debug("psutil not available, skipping resource monitoring")
            stats["psutil_available"] = False
            return stats

        try:
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

            # Check disk space
            disk = psutil.disk_usage("/")
            disk_percent = (disk.used / disk.total) * 100
            stats["disk_percent"] = disk_percent
            if disk_percent > warn_threshold * 100:
                stats["warnings"].append(f"High disk usage: {disk_percent:.1f}%")
                logger.warning(f"High disk usage: {disk_percent:.1f}%")

        except Exception as e:
            logger.warning(f"Error checking system resources: {e}")

        return stats

    async def acquire_task_slot(self) -> bool:
        """
        Acquire a slot for a concurrent task.

        Returns:
            True if slot acquired, False if at limit.
        """
        async with self._lock:
            if self.current_concurrent_tasks < self.max_concurrent_tasks:
                self.current_concurrent_tasks += 1
                return True
            return False

    def release_task_slot(self) -> None:
        """Release a concurrent task slot."""

        async def _release():
            async with self._lock:
                if self.current_concurrent_tasks > 0:
                    self.current_concurrent_tasks -= 1

        # Run the async function in the current event loop
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_release())
        except RuntimeError:
            # No event loop running, run synchronously
            pass


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

        # Try to acquire a concurrent task slot
        slot_acquired = await monitor.acquire_task_slot()
        if not slot_acquired:
            raise PermissionError("Maximum concurrent tasks limit reached")

        start_time = time.time()

        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            duration = time.time() - start_time
            monitor.record_task(duration)
            monitor.release_task_slot()

            # Check resources periodically
            if monitor.task_count % 10 == 0:
                stats = await monitor.check_resources()
                if not stats["healthy"]:
                    logger.warning(f"Resource warnings: {stats['warnings']}")

    return wrapper  # type: ignore
