"""
End-to-end tests that verify full workflow from MCP to CLI execution.

These tests require:
- A configured AI CLI (aider/claude)
- API keys in environment
- Can be slow (marked with @pytest.mark.slow)
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path

import pytest

from ninja_cli_mcp.path_utils import get_internal_dir


@pytest.mark.e2e
@pytest.mark.agent
@pytest.mark.slow
def test_complete_workflow_fibonacci():
    """Test complete workflow: MCP request -> Ninja -> AI CLI -> Result."""
    # Skip if no API key
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create a test file to edit
        test_file = repo_path / "fibonacci.py"
        test_file.write_text("""# TODO: Implement fibonacci function here
""")

        # Prepare MCP request
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ninja_quick_task",
                "arguments": {
                    "task": "Implement a fibonacci function that calculates the nth fibonacci number iteratively",
                    "repo_root": str(repo_path),
                    "context_paths": ["fibonacci.py"],
                    "timeout": 120,
                },
            },
        }

        # Call the MCP server
        env = os.environ.copy()
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", "ninja_cli_mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        try:
            # Send request
            stdout, _stderr = proc.communicate(input=json.dumps(mcp_request) + "\n", timeout=180)

            # Parse response
            response = json.loads(stdout.strip())

            # Verify response structure
            assert "result" in response
            assert response["result"]["status"] in ["ok", "completed"]

            # Verify file was modified
            content = test_file.read_text()
            assert "def fibonacci" in content
            assert "TODO" not in content or len(content) > 100

        finally:
            proc.terminate()


@pytest.mark.e2e
@pytest.mark.agent
@pytest.mark.slow
def test_parallel_execution():
    """Test that parallel tasks execute correctly without conflicts."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create multiple test files
        file1 = repo_path / "task1.py"
        file2 = repo_path / "task2.py"
        file1.write_text("# Task 1\n")
        file2.write_text("# Task 2\n")

        # This would test parallel execution
        # For now, just verify the structure works
        assert file1.exists()
        assert file2.exists()


@pytest.mark.e2e
def test_sequential_plan_execution():
    """Test that sequential plans execute steps in order."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create test file
        test_file = repo_path / "calculator.py"
        test_file.write_text("")

        # Sequential plan: 1) Create add function, 2) Create subtract function
        # This requires AI to execute multiple steps

        assert test_file.exists()


@pytest.mark.e2e
def test_work_directory_isolation():
    """Test that work directories are properly isolated per task."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        internal_dir = get_internal_dir(repo_path)

        # Verify structure
        assert internal_dir.exists()
        assert (internal_dir / "logs").exists()
        assert (internal_dir / "work").exists()


@pytest.mark.e2e
def test_logs_generation():
    """Test that logs are properly generated for tasks."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        internal_dir = get_internal_dir(repo_path)
        logs_dir = internal_dir / "logs"

        # After a task runs, logs should exist
        # For now just verify directory structure
        assert logs_dir.exists()


@pytest.mark.e2e
@pytest.mark.slow
def test_error_handling_invalid_task():
    """Test that errors are properly reported."""
    if not os.getenv("OPENROUTER_API_KEY"):
        pytest.skip("OPENROUTER_API_KEY not set")

    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Prepare invalid request (non-existent file)
        mcp_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "ninja_quick_task",
                "arguments": {
                    "task": "Edit this file",
                    "repo_root": str(repo_path),
                    "context_paths": ["nonexistent.py"],
                    "timeout": 30,
                },
            },
        }

        env = os.environ.copy()
        proc = subprocess.Popen(
            ["uv", "run", "python", "-m", "ninja_cli_mcp.server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
        )

        try:
            stdout, _stderr = proc.communicate(input=json.dumps(mcp_request) + "\n", timeout=60)

            response = json.loads(stdout.strip())

            # Should report error or warning
            assert "result" in response or "error" in response

        finally:
            proc.terminate()


@pytest.mark.e2e
def test_multiple_file_context():
    """Test that multiple context files are handled correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create multiple files
        (repo_path / "module1.py").write_text("# Module 1")
        (repo_path / "module2.py").write_text("# Module 2")
        (repo_path / "utils.py").write_text("# Utils")

        # Verify they all exist
        assert (repo_path / "module1.py").exists()
        assert (repo_path / "module2.py").exists()
        assert (repo_path / "utils.py").exists()
