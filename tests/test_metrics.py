"""
Tests for metrics tracking functionality.
"""

import csv
from pathlib import Path

import pytest

from ninja_cli_mcp.metrics import (
    MODEL_PRICING,
    MetricsTracker,
    TaskMetrics,
    create_task_metrics,
    extract_token_usage,
)


def test_model_pricing_structure():
    """Test that model pricing data has the correct structure."""
    assert len(MODEL_PRICING) > 0

    for model_id, pricing in MODEL_PRICING.items():
        assert "input" in pricing
        assert "output" in pricing
        assert isinstance(pricing["input"], (int, float))
        assert isinstance(pricing["output"], (int, float))
        assert pricing["input"] >= 0
        assert pricing["output"] >= 0


def test_task_metrics_creation():
    """Test TaskMetrics dataclass creation."""
    metrics = TaskMetrics(
        task_id="test-123",
        timestamp="2024-01-01T12:00:00",
        model="anthropic/claude-sonnet-4",
        tool_name="ninja_quick_task",
        task_description="Test task",
        input_tokens=1000,
        output_tokens=500,
        total_tokens=1500,
        input_cost=0.003,
        output_cost=0.0075,
        total_cost=0.0105,
        duration_sec=10.5,
        success=True,
        execution_mode="quick",
        repo_root="/tmp/test",
    )

    assert metrics.task_id == "test-123"
    assert metrics.total_tokens == 1500
    assert metrics.total_cost == 0.0105
    assert metrics.success is True


def test_metrics_tracker_initialization(tmp_path: Path):
    """Test MetricsTracker initialization and directory creation."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    assert tracker.metrics_dir.exists()
    assert tracker.metrics_file.exists()

    # Check that CSV has headers
    with open(tracker.metrics_file, "r") as f:
        reader = csv.reader(f)
        headers = next(reader)
        assert "task_id" in headers
        assert "model" in headers
        assert "input_tokens" in headers
        assert "output_tokens" in headers
        assert "total_cost" in headers


def test_calculate_cost():
    """Test cost calculation for different models."""
    tracker = MetricsTracker(Path("/tmp"))

    # Test with Claude Sonnet 4
    input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost = tracker.calculate_cost(
        "anthropic/claude-sonnet-4",
        1_000_000,  # 1M tokens
        1_000_000,  # 1M tokens
    )

    assert input_cost == 3.0  # $3 per 1M input tokens
    assert output_cost == 15.0  # $15 per 1M output tokens
    assert cache_read_cost == 0.0  # No cache tokens
    assert cache_write_cost == 0.0  # No cache tokens
    assert total_cost == 18.0

    # Test with cache tokens
    input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost = tracker.calculate_cost(
        "anthropic/claude-sonnet-4",
        1_000_000,  # 1M tokens
        1_000_000,  # 1M tokens
        500_000,  # 500K cache read tokens
        100_000,  # 100K cache write tokens
    )

    assert input_cost == 3.0
    assert output_cost == 15.0
    assert cache_read_cost > 0.0  # Should have cache read cost
    assert cache_write_cost > 0.0  # Should have cache write cost
    assert total_cost > 18.0  # Should be more than without cache

    # Test with unknown model (should use default pricing)
    input_cost, output_cost, cache_read_cost, cache_write_cost, total_cost = tracker.calculate_cost(
        "unknown/model",
        1_000_000,
        1_000_000,
    )

    assert input_cost == 1.0
    assert output_cost == 2.0
    assert total_cost == 3.0


def test_record_task(tmp_path: Path):
    """Test recording a task to CSV."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    metrics = TaskMetrics(
        task_id="test-456",
        timestamp="2024-01-01T12:00:00",
        model="openai/gpt-4o",
        tool_name="ninja_quick_task",
        task_description="Test recording",
        input_tokens=2000,
        output_tokens=1000,
        total_tokens=3000,
        input_cost=0.005,
        output_cost=0.010,
        total_cost=0.015,
        duration_sec=15.0,
        success=True,
        execution_mode="quick",
        repo_root=str(repo_root),
    )

    tracker.record_task(metrics)

    # Verify the task was recorded
    with open(tracker.metrics_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["task_id"] == "test-456"
        assert rows[0]["model"] == "openai/gpt-4o"
        assert rows[0]["total_tokens"] == "3000"
        assert rows[0]["success"] == "True"


def test_get_summary_empty(tmp_path: Path):
    """Test get_summary with no recorded tasks."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)
    summary = tracker.get_summary()

    assert summary["total_tasks"] == 0
    assert summary["total_tokens"] == 0
    assert summary["total_cost"] == 0.0
    assert summary["successful_tasks"] == 0
    assert summary["failed_tasks"] == 0


def test_get_summary_with_tasks(tmp_path: Path):
    """Test get_summary with recorded tasks."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    # Record multiple tasks
    for i in range(5):
        metrics = TaskMetrics(
            task_id=f"test-{i}",
            timestamp="2024-01-01T12:00:00",
            model="anthropic/claude-sonnet-4",
            tool_name="ninja_quick_task",
            task_description=f"Test task {i}",
            input_tokens=1000,
            output_tokens=500,
            total_tokens=1500,
            input_cost=0.003,
            output_cost=0.0075,
            total_cost=0.0105,
            duration_sec=10.0,
            success=i % 2 == 0,  # Alternate success/failure
            execution_mode="quick",
            repo_root=str(repo_root),
        )
        tracker.record_task(metrics)

    summary = tracker.get_summary()

    assert summary["total_tasks"] == 5
    assert summary["total_tokens"] == 7500  # 1500 * 5
    assert abs(summary["total_cost"] - 0.0525) < 0.0001  # 0.0105 * 5
    assert summary["successful_tasks"] == 3  # Tasks 0, 2, 4
    assert summary["failed_tasks"] == 2  # Tasks 1, 3
    assert summary["model_usage"]["anthropic/claude-sonnet-4"] == 5


def test_get_recent_tasks(tmp_path: Path):
    """Test retrieving recent tasks."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    # Record 15 tasks
    for i in range(15):
        metrics = TaskMetrics(
            task_id=f"test-{i}",
            timestamp=f"2024-01-01T12:{i:02d}:00",
            model="anthropic/claude-sonnet-4",
            tool_name="ninja_quick_task",
            task_description=f"Test task {i}",
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
            input_cost=0.0003,
            output_cost=0.00075,
            total_cost=0.00105,
            duration_sec=1.0,
            success=True,
            execution_mode="quick",
            repo_root=str(repo_root),
        )
        tracker.record_task(metrics)

    # Get last 10 tasks
    recent = tracker.get_recent_tasks(limit=10)

    assert len(recent) == 10
    # Most recent should be task-14
    assert recent[-1]["task_id"] == "test-14"
    # Oldest in this set should be task-5
    assert recent[0]["task_id"] == "test-5"


def test_extract_token_usage():
    """Test extracting token usage from output."""
    # Test with explicit token reporting
    output1 = """
    Task completed successfully.
    Input tokens: 1234
    Output tokens: 5678
    """
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = extract_token_usage(
        output1
    )
    assert input_tokens == 1234
    assert output_tokens == 5678
    assert cache_read_tokens == 0
    assert cache_write_tokens == 0

    # Test with cache tokens
    output2 = """
    Task completed.
    Input tokens: 1000
    Output tokens: 500
    cache_read_tokens: 100
    cache_write_tokens: 50
    """
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = extract_token_usage(
        output2
    )
    assert input_tokens == 1000
    assert output_tokens == 500
    assert cache_read_tokens == 100
    assert cache_write_tokens == 50

    # Test with no token info (should estimate)
    output3 = "This is some output without token information."
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = extract_token_usage(
        output3
    )
    assert output_tokens > 0  # Should estimate based on length
    assert cache_read_tokens == 0
    assert cache_write_tokens == 0

    # Test with partial info
    output4 = "Output tokens: 999"
    input_tokens, output_tokens, cache_read_tokens, cache_write_tokens = extract_token_usage(
        output4
    )
    assert output_tokens == 999


def test_create_task_metrics(tmp_path: Path):
    """Test creating TaskMetrics from task results."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    output = """
    Task completed.
    Input tokens: 500
    Output tokens: 250
    """

    metrics = create_task_metrics(
        task_id="test-789",
        model="anthropic/claude-sonnet-4",
        tool_name="ninja_quick_task",
        task_description="Test task",
        output=output,
        duration_sec=5.5,
        success=True,
        execution_mode="quick",
        repo_root=str(repo_root),
    )

    assert metrics.task_id == "test-789"
    assert metrics.model == "anthropic/claude-sonnet-4"
    assert metrics.input_tokens == 500
    assert metrics.output_tokens == 250
    assert metrics.total_tokens == 750
    assert metrics.duration_sec == 5.5
    assert metrics.success is True

    # Cost should be calculated
    assert metrics.input_cost > 0
    assert metrics.output_cost > 0
    assert metrics.total_cost > 0


def test_metrics_with_error(tmp_path: Path):
    """Test metrics recording for failed tasks."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    metrics = create_task_metrics(
        task_id="test-error",
        model="openai/gpt-4o",
        tool_name="ninja_quick_task",
        task_description="Test failing task",
        output="",
        duration_sec=2.0,
        success=False,
        execution_mode="quick",
        repo_root=str(repo_root),
        error_message="Task failed due to timeout",
    )

    tracker.record_task(metrics)

    # Verify error was recorded
    with open(tracker.metrics_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert rows[0]["success"] == "False"
        assert "timeout" in rows[0]["error_message"].lower()


def test_metrics_file_scope(tmp_path: Path):
    """Test recording file scope in metrics."""
    repo_root = tmp_path / "repo"
    repo_root.mkdir()

    tracker = MetricsTracker(repo_root)

    metrics = create_task_metrics(
        task_id="test-scope",
        model="anthropic/claude-sonnet-4",
        tool_name="ninja_quick_task",
        task_description="Test with file scope",
        output="",
        duration_sec=3.0,
        success=True,
        execution_mode="quick",
        repo_root=str(repo_root),
        file_scope="src/**/*.py,tests/**/*.py",
    )

    tracker.record_task(metrics)

    # Verify file scope was recorded
    with open(tracker.metrics_file, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        assert len(rows) == 1
        assert "src/**/*.py" in rows[0]["file_scope"]
        assert "tests/**/*.py" in rows[0]["file_scope"]
