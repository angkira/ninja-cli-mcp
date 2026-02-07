"""
Unit tests for tools.py focusing on code path coverage.

Tests the core logic paths without complex async execution.
"""

from __future__ import annotations

from unittest.mock import Mock

import pytest

from ninja_coder.driver import NinjaResult
from ninja_coder.tools import ToolExecutor


class TestResultConversion:
    """Test _result_to_step_result method."""

    @pytest.fixture
    def executor(self):
        """Create ToolExecutor with mock driver."""
        driver = Mock()
        driver.config = Mock()
        driver.config.model = "test-model"
        return ToolExecutor(driver=driver)

    def test_result_to_step_result_success(self, executor):
        """Test converting successful NinjaResult."""
        result = NinjaResult(
            success=True,
            exit_code=0,
            summary="Task completed",
            notes="All good",
            raw_logs_path="/logs/task.log",
            suspected_touched_paths=["file1.py", "file2.py"],
        )

        step_result = executor._result_to_step_result("step1", result)

        assert step_result.id == "step1"
        assert step_result.status == "ok"
        assert step_result.summary == "Task completed"
        assert step_result.notes == "All good"
        assert len(step_result.suspected_touched_paths) == 2

    def test_result_to_step_result_failure(self, executor):
        """Test converting failed NinjaResult."""
        result = NinjaResult(
            success=False,
            exit_code=1,
            summary="Task failed",
            notes="Error occurred",
            raw_logs_path="/logs/task.log",
            suspected_touched_paths=[],
        )

        step_result = executor._result_to_step_result("step1", result)

        assert step_result.id == "step1"
        assert step_result.status == "fail"
        assert "failed" in step_result.summary.lower()

    def test_result_to_step_result_error(self, executor):
        """Test converting error NinjaResult (exit code -1)."""
        result = NinjaResult(
            success=False,
            exit_code=-1,  # Special error indicator
            summary="Internal error",
            notes="Exception raised",
            raw_logs_path="/logs/task.log",
            suspected_touched_paths=[],
        )

        step_result = executor._result_to_step_result("step1", result)

        assert step_result.id == "step1"
        assert step_result.status == "error"

    def test_result_truncates_long_summary(self, executor):
        """Test that very long summaries are truncated."""
        result = NinjaResult(
            success=True,
            exit_code=0,
            summary="x" * 1000,  # Very long
            notes="y" * 500,  # Very long
            raw_logs_path="/logs/task.log",
            suspected_touched_paths=[],
        )

        step_result = executor._result_to_step_result("step1", result)

        # Should be truncated to max 500 chars
        assert len(step_result.summary) <= 500
        assert len(step_result.notes) <= 300

    def test_result_limits_touched_paths(self, executor):
        """Test that touched paths list is limited."""
        result = NinjaResult(
            success=True,
            exit_code=0,
            summary="Success",
            notes="",
            raw_logs_path="/logs/task.log",
            suspected_touched_paths=[f"file{i}.py" for i in range(50)],  # 50 files
        )

        step_result = executor._result_to_step_result("step1", result)

        # Should be limited to max 10 paths
        assert len(step_result.suspected_touched_paths) == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
