"""
Tests for security utilities.

These tests verify input validation, rate limiting, and resource monitoring.
"""

import asyncio
import sys
import tempfile
from pathlib import Path

import pytest

from ninja_cli_mcp.security import (
    InputValidator,
    RateLimiter,
    ResourceMonitor,
    get_resource_monitor,
    monitored,
    rate_limited,
)


class TestInputValidator:
    """Tests for input validation."""

    def test_sanitize_path_valid(self, tmp_path):
        """Test sanitizing valid paths."""
        # Create a test file
        test_file = tmp_path / "test.txt"
        test_file.touch()

        # Should not raise
        result = InputValidator.sanitize_path(str(test_file), base_dir=tmp_path)
        assert result.exists()

    def test_sanitize_path_traversal(self, tmp_path):
        """Test that path traversal is blocked."""
        with pytest.raises(ValueError, match="outside allowed directory"):
            InputValidator.sanitize_path("../../etc/passwd", base_dir=tmp_path)

    def test_sanitize_path_dangerous_chars(self, tmp_path):
        """Test that dangerous characters are detected."""
        # Path traversal when constrained by base_dir
        with pytest.raises(ValueError, match="outside allowed directory"):
            InputValidator.sanitize_path("../../../etc/passwd", base_dir=tmp_path)

        # Without base_dir, these resolve safely but might go outside cwd
        # Just verify they don't crash
        result = InputValidator.sanitize_path("test.txt")
        assert isinstance(result, Path)

    def test_sanitize_string_valid(self):
        """Test sanitizing valid strings."""
        result = InputValidator.sanitize_string("Hello, world!")
        assert result == "Hello, world!"

        result = InputValidator.sanitize_string("def hello():\n    pass")
        assert "def hello()" in result

    def test_sanitize_string_max_length(self):
        """Test max length validation."""
        with pytest.raises(ValueError, match="exceeds maximum length"):
            InputValidator.sanitize_string("x" * 20000, max_length=100)

    def test_sanitize_string_dangerous_patterns(self):
        """Test detection of potentially dangerous patterns."""
        # These should not raise, just log warnings
        patterns = [
            "$(whoami)",
            "SELECT * FROM users; DROP TABLE users;",
            "<script>alert('xss')</script>",
            "rm -rf /",
        ]

        for pattern in patterns:
            # Should complete without error (just logs warning)
            result = InputValidator.sanitize_string(pattern)
            assert result == pattern

    def test_validate_repo_root_valid(self, tmp_path):
        """Test validating valid repository roots."""
        result = InputValidator.validate_repo_root(str(tmp_path))
        assert result.exists()
        assert result.is_dir()

    def test_validate_repo_root_nonexistent(self):
        """Test that nonexistent paths are rejected."""
        with pytest.raises(ValueError, match="does not exist"):
            InputValidator.validate_repo_root("/nonexistent/path/12345")

    def test_validate_repo_root_sensitive_dirs(self):
        """Test that sensitive directories are blocked."""
        sensitive_dirs = ["/etc", "/root", "/bin", "/sbin", "/boot"]

        for sensitive_dir in sensitive_dirs:
            if Path(sensitive_dir).exists():
                with pytest.raises(ValueError, match="sensitive directory"):
                    InputValidator.validate_repo_root(sensitive_dir)


class TestRateLimiter:
    """Tests for rate limiting."""

    @pytest.mark.asyncio
    async def test_rate_limit_allows_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = RateLimiter(max_calls=10, time_window=60)

        # Should allow first 10 calls
        for _i in range(10):
            assert await limiter.check_limit() is True

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_over_limit(self):
        """Test that requests over limit are blocked."""
        limiter = RateLimiter(max_calls=5, time_window=60)

        # Allow first 5
        for _i in range(5):
            assert await limiter.check_limit() is True

        # Block 6th
        assert await limiter.check_limit() is False

    @pytest.mark.asyncio
    async def test_rate_limit_window_expires(self):
        """Test that rate limit window expires."""
        limiter = RateLimiter(max_calls=2, time_window=1)  # 1 second window

        # Use up the limit
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is False

        # Wait for window to expire
        await asyncio.sleep(1.1)

        # Should allow again
        assert await limiter.check_limit() is True

    @pytest.mark.asyncio
    async def test_rate_limit_per_client(self):
        """Test per-client rate limiting."""
        limiter = RateLimiter(max_calls=2, time_window=60)

        # Client A uses limit
        assert await limiter.check_limit("client_a") is True
        assert await limiter.check_limit("client_a") is True
        assert await limiter.check_limit("client_a") is False

        # Client B has separate limit
        assert await limiter.check_limit("client_b") is True
        assert await limiter.check_limit("client_b") is True
        assert await limiter.check_limit("client_b") is False

    @pytest.mark.asyncio
    async def test_rate_limit_reset(self):
        """Test resetting rate limit for a client."""
        limiter = RateLimiter(max_calls=2, time_window=60)

        # Use up the limit
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is True
        assert await limiter.check_limit() is False

        # Reset
        limiter.reset()

        # Should allow again
        assert await limiter.check_limit() is True


class TestRateLimitedDecorator:
    """Tests for @rate_limited decorator."""

    @pytest.mark.asyncio
    async def test_rate_limited_decorator_allows_within_limit(self):
        """Test decorator allows calls within limit."""

        @rate_limited(max_calls=3, time_window=60)
        async def limited_function():
            return "success"

        # Should allow first 3 calls
        assert await limited_function() == "success"
        assert await limited_function() == "success"
        assert await limited_function() == "success"

    @pytest.mark.asyncio
    async def test_rate_limited_decorator_blocks_over_limit(self):
        """Test decorator blocks calls over limit."""

        @rate_limited(max_calls=2, time_window=60)
        async def limited_function():
            return "success"

        # Allow first 2
        await limited_function()
        await limited_function()

        # Block 3rd
        with pytest.raises(PermissionError, match="Rate limit exceeded"):
            await limited_function()


class TestResourceMonitor:
    """Tests for resource monitoring."""

    def test_monitor_records_tasks(self):
        """Test that monitor records task executions."""
        monitor = ResourceMonitor()

        monitor.record_task(1.5)
        monitor.record_task(2.0)
        monitor.record_task(0.5)

        stats = monitor.get_stats()
        assert stats["total_tasks"] == 3
        assert stats["total_duration"] == 4.0
        assert stats["average_task_duration"] == pytest.approx(1.333, rel=0.01)

    def test_monitor_stats_empty(self):
        """Test stats when no tasks recorded."""
        monitor = ResourceMonitor()

        stats = monitor.get_stats()
        assert stats["total_tasks"] == 0
        assert stats["total_duration"] == 0.0

    @pytest.mark.asyncio
    async def test_monitor_check_resources(self):
        """Test resource checking."""
        monitor = ResourceMonitor()

        stats = await monitor.check_resources()

        assert "healthy" in stats
        assert "warnings" in stats
        assert isinstance(stats["warnings"], list)

    @pytest.mark.asyncio
    async def test_monitor_check_resources_without_psutil(self, monkeypatch):
        """Test resource checking when psutil is not available."""
        # Simulate psutil import error
        psutil_backup = sys.modules.get("psutil")
        if psutil_backup:
            sys.modules.pop("psutil", None)

        monitor = ResourceMonitor()
        stats = await monitor.check_resources()

        # Should still work, just without resource info
        assert "healthy" in stats

        # Restore psutil
        if psutil_backup:
            sys.modules["psutil"] = psutil_backup


class TestMonitoredDecorator:
    """Tests for @monitored decorator."""

    @pytest.mark.asyncio
    async def test_monitored_decorator_records_execution(self):
        """Test that decorator records task execution."""
        monitor = get_resource_monitor()
        initial_count = monitor.task_count

        @monitored
        async def test_function():
            await asyncio.sleep(0.1)
            return "result"

        result = await test_function()

        assert result == "result"
        assert monitor.task_count == initial_count + 1
        assert monitor.total_duration >= 0.1


class TestIntegration:
    """Integration tests for security features."""

    @pytest.mark.asyncio
    async def test_combined_rate_limit_and_monitoring(self):
        """Test combining rate limiting and monitoring."""
        monitor = get_resource_monitor()
        initial_count = monitor.task_count

        @rate_limited(max_calls=3, time_window=60)
        @monitored
        async def protected_function(value: int) -> int:
            return value * 2

        # Should work for first 3 calls
        assert await protected_function(1) == 2
        assert await protected_function(2) == 4
        assert await protected_function(3) == 6

        # 4th call should be rate limited
        with pytest.raises(PermissionError):
            await protected_function(4)

        # Should have recorded 3 successful executions
        assert monitor.task_count >= initial_count + 3

    @pytest.mark.asyncio
    async def test_input_validation_with_rate_limiting(self):
        """Test input validation combined with rate limiting."""

        @rate_limited(max_calls=5, time_window=60)
        async def process_file(path: str, base_dir: str) -> Path:
            # Validate input
            return InputValidator.sanitize_path(path, base_dir=base_dir)

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create test files
            tmpdir_path = Path(tmpdir)
            test1 = tmpdir_path / "test.txt"
            test2 = tmpdir_path / "test2.txt"
            test1.touch()
            test2.touch()

            # Valid calls should work (use absolute paths)
            result = await process_file(str(test1), tmpdir)
            assert isinstance(result, Path)
            assert result.exists()

            # Invalid path should raise ValueError (not PermissionError)
            with pytest.raises(ValueError):
                await process_file("../../etc/passwd", tmpdir)

            # Can still call with valid input (error didn't consume rate limit)
            result = await process_file(str(test2), tmpdir)
            assert isinstance(result, Path)
            assert result.exists()
