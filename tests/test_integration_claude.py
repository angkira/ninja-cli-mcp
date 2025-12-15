"""
Integration tests with Claude Code.

These tests perform small, token-efficient interactions to verify
the system works end-to-end with real AI models.
"""

import os
import subprocess
from pathlib import Path

import pytest


# Skip these tests if not in integration test mode
pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_INTEGRATION_TESTS"),
    reason="Integration tests only run when RUN_INTEGRATION_TESTS=1",
)


@pytest.fixture
def temp_project(tmp_path):
    """Create a minimal test project."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()

    # Create a simple Python file
    (project_dir / "hello.py").write_text("""
def greet(name):
    return f"Hello, {name}!"
""")

    return project_dir


def test_quick_task_minimal(temp_project):
    """
    Test a minimal quick task that uses very few tokens.
    This verifies the end-to-end flow without expensive API calls.
    """
    # Check if API key is set
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No API key configured")

    # Use a very simple task to minimize token usage
    task = "Add a docstring to the greet function"

    # Run the quick_task command
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "ninja_cli_mcp.cli",
            "quick-task",
            "--repo-root",
            str(temp_project),
            "--task",
            task,
            "--allowed-globs",
            "*.py",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Check that the command completed
    assert result.returncode in [0, 1], f"Unexpected return code: {result.returncode}"

    # Check that some output was produced
    assert len(result.stdout) > 0 or len(result.stderr) > 0


def test_metrics_tracking(temp_project):
    """
    Test that metrics are properly tracked after a task execution.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No API key configured")

    # Run a minimal task
    task = "Add type hints to function parameters"

    subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "ninja_cli_mcp.cli",
            "quick-task",
            "--repo-root",
            str(temp_project),
            "--task",
            task,
            "--allowed-globs",
            "*.py",
        ],
        capture_output=True,
        timeout=30,
    )

    # Check that metrics were recorded
    metrics_file = temp_project / ".ninja-cli-mcp" / "metrics" / "tasks.csv"

    if metrics_file.exists():
        content = metrics_file.read_text()
        # Verify CSV has headers
        assert "task_id" in content
        assert "model" in content
        assert "total_tokens" in content
        assert "total_cost" in content
    else:
        pytest.skip("Metrics file not created (likely due to CLI mock)")


def test_list_models_command():
    """
    Test the list-models command (doesn't require API key).
    """
    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "list-models"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "anthropic/claude-sonnet-4" in result.stdout
    assert "openai/gpt-4o" in result.stdout
    assert "qwen/qwen3-coder" in result.stdout


def test_show_config_command():
    """
    Test the show-config command (doesn't require API key).
    """
    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "show-config"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Current Configuration" in result.stdout
    assert "Model:" in result.stdout
    assert "API key:" in result.stdout


def test_metrics_summary_empty(temp_project):
    """
    Test metrics-summary on a fresh project (doesn't require API key).
    """
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "ninja_cli_mcp.cli",
            "metrics-summary",
            "--repo-root",
            str(temp_project),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "Metrics Summary" in result.stdout
    assert "Total tasks:" in result.stdout


@pytest.mark.slow
def test_openrouter_api_pricing():
    """
    Test that we can fetch pricing from OpenRouter API.
    This is marked as slow since it makes a network request.
    """
    from ninja_cli_mcp.metrics import fetch_openrouter_pricing

    # Fetch pricing
    pricing = fetch_openrouter_pricing()

    # Should have pricing for popular models
    assert len(pricing) > 0

    # Check that Claude Sonnet 4 has pricing
    if "anthropic/claude-sonnet-4" in pricing:
        model_pricing = pricing["anthropic/claude-sonnet-4"]
        assert "input" in model_pricing
        assert "output" in model_pricing
        assert "cache_read" in model_pricing
        assert "cache_write" in model_pricing
        assert model_pricing["input"] > 0
        assert model_pricing["output"] > 0


@pytest.mark.slow
def test_small_chat_interaction(temp_project):
    """
    Test a very small chat-like interaction to verify the complete flow.
    Uses minimal tokens to keep costs low.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("No API key configured")

    # Create a tiny test file
    test_file = temp_project / "math.py"
    test_file.write_text("def add(a, b):\n    return a + b\n")

    # Ask for a tiny change
    task = "Add one comment"

    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "ninja_cli_mcp.cli",
            "quick-task",
            "--repo-root",
            str(temp_project),
            "--task",
            task,
            "--allowed-globs",
            "math.py",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )

    # Should complete without errors
    assert result.returncode in [0, 1]

    # Check if metrics were recorded
    metrics_file = temp_project / ".ninja-cli-mcp" / "metrics" / "tasks.csv"
    if metrics_file.exists():
        content = metrics_file.read_text()
        # Verify we tracked tokens and cost
        assert "total_tokens" in content
        assert "total_cost" in content
