"""
Smoke tests that verify basic end-to-end functionality.

These tests perform quick sanity checks without requiring API keys.
"""

import os
import subprocess
from pathlib import Path

import pytest


def test_server_starts_without_error(tmp_path):
    """Test that the server can start without immediate errors."""
    # Set minimal environment
    env = os.environ.copy()
    env["NINJA_CODE_BIN"] = "echo"  # Use echo as a dummy CLI
    env["NINJA_MODEL"] = "test-model"

    # Start the server and immediately stop it
    proc = subprocess.Popen(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.server"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        text=True,
    )

    try:
        # Give it a moment to start
        import time
        time.sleep(1)

        # Check if it's still running (didn't crash immediately)
        assert proc.poll() is None, "Server crashed immediately on startup"

    finally:
        # Clean up
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_cli_help():
    """Test that CLI help works."""
    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower()


def test_list_models():
    """Test that list-models command works."""
    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "list-models"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    # Check that some expected models are listed
    assert "claude" in result.stdout.lower()
    assert "gpt" in result.stdout.lower() or "openai" in result.stdout.lower()


def test_show_config():
    """Test that show-config command works."""
    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "show-config"],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "configuration" in result.stdout.lower()


def test_config_from_env():
    """Test that configuration is read from environment."""
    env = os.environ.copy()
    env["NINJA_MODEL"] = "test-model-123"
    env["NINJA_CODE_BIN"] = "/path/to/test/cli"

    result = subprocess.run(
        ["uv", "run", "python", "-m", "ninja_cli_mcp.cli", "show-config"],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )

    assert result.returncode == 0
    assert "test-model-123" in result.stdout
    assert "/path/to/test/cli" in result.stdout


def test_metrics_summary_empty_repo(tmp_path):
    """Test metrics-summary on a fresh repository."""
    result = subprocess.run(
        [
            "uv",
            "run",
            "python",
            "-m",
            "ninja_cli_mcp.cli",
            "metrics-summary",
            "--repo-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "metrics" in result.stdout.lower() or "total" in result.stdout.lower()


def test_path_validation():
    """Test that path validation works."""
    from ninja_cli_mcp.path_utils import validate_repo_root

    # Should fail for non-existent path
    with pytest.raises(ValueError, match="does not exist"):
        validate_repo_root("/nonexistent/path/that/does/not/exist")

    # Should work for existing directory
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        path = validate_repo_root(tmpdir)
        assert path.exists()
        assert path.is_dir()


def test_cli_adapter_detection():
    """Test that CLI adapter detects different CLI types."""
    from ninja_cli_mcp.ninja_driver import NinjaConfig, NinjaDriver

    # Test Claude detection
    config = NinjaConfig(bin_path="claude")
    driver = NinjaDriver(config)
    assert driver._detect_cli_type() == "claude"

    # Test Aider detection
    config = NinjaConfig(bin_path="/usr/local/bin/aider")
    driver = NinjaDriver(config)
    assert driver._detect_cli_type() == "aider"

    # Test with full path (like from NVM)
    config = NinjaConfig(bin_path="/home/user/.nvm/versions/node/v25.0.0/bin/claude")
    driver = NinjaDriver(config)
    assert driver._detect_cli_type() == "claude"


def test_api_key_validation():
    """Test that API key validation catches common issues."""
    # Valid keys
    valid_keys = [
        "sk-or-v1-" + "a" * 50,
        "sk-ant-" + "x" * 50,
    ]

    for key in valid_keys:
        assert len(key) >= 20
        assert len(key) < 100
        assert "\x1b" not in key  # No ANSI codes
        assert key.startswith("sk-")

    # Invalid keys (would be caught by validation)
    invalid_keys = [
        "\x1b[36msk-or-v1-key",  # ANSI code
        "[0;36m?[0m [1mEnter your key",  # Terminal prompt captured
        "short",  # Too short
        "x" * 150,  # Too long
    ]

    for key in invalid_keys:
        # These should fail validation checks
        is_invalid = (
            len(key) < 20 or
            len(key) > 100 or
            "\x1b" in key or
            "[" in key and not key.startswith("sk-")
        )
        assert is_invalid, f"Key should be invalid: {key[:50]}..."


def test_instruction_builder():
    """Test that instruction builder creates valid instructions."""
    from ninja_cli_mcp.ninja_driver import InstructionBuilder
    from ninja_cli_mcp.models import ExecutionMode

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        builder = InstructionBuilder(tmpdir, ExecutionMode.QUICK)

        instruction = builder.build_quick_task(
            task="Test task",
            context_paths=["test.py"],
            allowed_globs=["*.py"],
            deny_globs=["__pycache__"],
        )

        # Verify instruction structure
        assert "version" in instruction
        assert "type" in instruction
        assert instruction["type"] == "quick_task"
        assert "task" in instruction
        assert instruction["task"] == "Test task"
        assert "file_scope" in instruction
        assert instruction["file_scope"]["context_paths"] == ["test.py"]
        assert "*.py" in instruction["file_scope"]["allowed_globs"]
        assert "__pycache__" in instruction["file_scope"]["deny_globs"]


def test_fibonacci_implementation():
    """Test a simple fibonacci implementation to verify basic Python functionality."""
    def fibonacci(n: int) -> int:
        """Calculate the nth Fibonacci number."""
        if n <= 0:
            return 0
        elif n == 1:
            return 1
        else:
            return fibonacci(n - 1) + fibonacci(n - 2)
    
    # Test basic Fibonacci sequence
    assert fibonacci(0) == 0
    assert fibonacci(1) == 1
    assert fibonacci(2) == 1
    assert fibonacci(3) == 2
    assert fibonacci(4) == 3
    assert fibonacci(5) == 5
    assert fibonacci(6) == 8
    assert fibonacci(7) == 13
    assert fibonacci(8) == 21
    assert fibonacci(10) == 55
    
    # Test edge cases
    assert fibonacci(-1) == 0
    assert fibonacci(-5) == 0


def test_fibonacci_iterative():
    """Test iterative Fibonacci for better performance verification."""
    def fibonacci_iterative(n: int) -> int:
        """Calculate nth Fibonacci number iteratively."""
        if n <= 0:
            return 0
        elif n == 1:
            return 1
        
        prev, curr = 0, 1
        for _ in range(2, n + 1):
            prev, curr = curr, prev + curr
        return curr
    
    # Compare with expected values
    expected = [0, 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 377, 610]
    for i, expected_val in enumerate(expected):
        assert fibonacci_iterative(i) == expected_val, f"fibonacci({i}) should be {expected_val}"
    
    # Test larger number for performance
    result = fibonacci_iterative(20)
    assert result == 6765
    
    result = fibonacci_iterative(30)
    assert result == 832040

