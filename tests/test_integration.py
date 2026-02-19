from __future__ import annotations
import pytest


"""
Integration tests that verify end-to-end functionality with real API calls.

These tests require:
- OpenCode binary with authorized operators
- OPENROUTER_API_KEY or OPENAI_API_KEY in environment
- NINJA_MODEL configured
- Perplexity API key for researcher (optional)

Run with: pytest tests/test_integration.py -v -s
"""


import os
from pathlib import Path

import pytest

from ninja_coder.driver import NinjaConfig, NinjaDriver
from ninja_coder.models import TaskComplexity


pytestmark = pytest.mark.integration


@pytest.fixture
def skip_if_no_api_key():
    """Skip test if no API key is configured."""
    has_key = bool(
        os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    )
    if not has_key:
        pytest.skip("No API key configured - set OPENROUTER_API_KEY or OPENAI_API_KEY")


@pytest.fixture
def skip_if_no_opencode():
    """Skip test if OpenCode binary not found."""
    import shutil

    opencode_path = os.environ.get("NINJA_CODE_BIN") or shutil.which("opencode")
    if not opencode_path:
        pytest.skip("OpenCode binary not found - install or set NINJA_CODE_BIN")


@pytest.fixture
def real_driver():
    """Create NinjaDriver with real configuration from environment."""
    config = NinjaConfig.from_env()

    # Verify config is valid
    if not config.openai_api_key:
        pytest.skip("No API key found in environment")

    if not config.model:
        pytest.skip("No model configured - set NINJA_MODEL")

    return NinjaDriver(config)


@pytest.fixture
def test_repo():
    """Create a temporary test repository within current repo to avoid permission prompts."""
    import shutil

    # Use a temp directory within the current repo to avoid OpenCode permission prompts
    # /tmp requires external_directory permission which causes interactive prompts
    repo = Path.cwd() / ".test_repos" / f"integration_test_{os.getpid()}"
    repo.mkdir(parents=True, exist_ok=True)

    # Create a simple Python file to work with
    (repo / "example.py").write_text("""
def hello(name):
    print(f"Hello {name}")

if __name__ == "__main__":
    hello("World")
""")

    # Initialize git repo
    import subprocess
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "test@test.com"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial commit"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    yield repo

    # Cleanup
    shutil.rmtree(repo, ignore_errors=True)


def test_driver_config_from_env(skip_if_no_api_key):
    """Test that driver can be configured from environment."""
    config = NinjaConfig.from_env()

    assert config.bin_path is not None
    assert config.openai_api_key is not None
    assert config.model is not None

    print("\n✓ Config loaded:")
    print(f"  Binary: {config.bin_path}")
    print(f"  Model: {config.model}")
    print(f"  Base URL: {config.openai_base_url}")


def test_driver_initialization(skip_if_no_api_key, real_driver):
    """Test that driver initializes correctly with real config."""
    assert real_driver.config is not None
    assert real_driver._strategy is not None
    assert real_driver.session_manager is not None
    assert real_driver.structured_logger is not None

    print("\n✓ Driver initialized:")
    print(f"  Strategy: {real_driver._strategy.name}")
    print(f"  Model: {real_driver.config.model}")


def test_model_selection_for_task_types(skip_if_no_api_key, real_driver):
    """Test model selection for different task types."""
    from ninja_coder.model_selector import ModelSelector

    selector = ModelSelector.from_env()

    # Test each complexity level
    quick_rec = selector.select_model(TaskComplexity.QUICK)
    seq_rec = selector.select_model(TaskComplexity.SEQUENTIAL)
    parallel_rec = selector.select_model(TaskComplexity.PARALLEL, fanout=5)

    print("\n✓ Model recommendations:")
    print(f"  QUICK: {quick_rec.model} ({quick_rec.reason})")
    print(f"  SEQUENTIAL: {seq_rec.model} ({seq_rec.reason})")
    print(f"  PARALLEL: {parallel_rec.model} ({parallel_rec.reason})")

    assert quick_rec.model is not None
    assert seq_rec.model is not None
    assert parallel_rec.model is not None


@pytest.mark.slow
@pytest.mark.asyncio
async def test_quick_task_execution(skip_if_no_api_key, real_driver, test_repo):
    """Test executing a quick task with real API call using direct execute_async."""
    print(f"\n✓ Running quick task in {test_repo}")
    print("  Task: Add a docstring")
    print(f"  Model: {real_driver.config.model}")

    # Build minimal instruction to avoid ARG_MAX limit
    instruction = {
        "version": "1.0",
        "type": "quick_task",
        "repo_root": str(test_repo),
        "task": "Add a docstring to the hello function",
        "mode": "quick",
        "file_scope": {
            "context_paths": ["example.py"],
            "allowed_globs": ["*.py"],
            "deny_globs": [],
        },
        "instructions": "Add a docstring to the hello function",  # Short prompt
    }

    # Execute task directly with minimal prompt
    result = await real_driver.execute_async(
        repo_root=str(test_repo),
        step_id="integration-test-quick",
        instruction=instruction,
        task_type="quick",
    )

    print("\n✓ Task completed:")
    print(f"  Success: {result.success}")
    print(f"  Summary: {result.summary}")
    print(f"  Model used: {result.model_used}")
    print(f"  Exit code: {result.exit_code}")
    print(f"  Files touched: {result.suspected_touched_paths}")

    if result.notes:
        print(f"  Notes: {result.notes}")

    # Verify result structure
    assert result.success is True, f"Task failed: {result.summary}"
    assert result.model_used is not None
    assert len(result.suspected_touched_paths) > 0, "No files were modified"
    assert "example.py" in result.suspected_touched_paths

    # Check that file was actually modified
    example_content = (test_repo / "example.py").read_text()
    assert '"""' in example_content, "Docstring not found in file"
    print("\n✓ File content after task:")
    print(example_content)


@pytest.mark.slow
@pytest.mark.asyncio
async def test_multi_agent_task_execution(
    skip_if_no_api_key, skip_if_no_opencode, real_driver, test_repo
):
    """Test executing a multi-agent task with OpenCode operators."""
    # Check if we're using OpenCode
    if "opencode" not in real_driver.config.bin_path.lower():
        pytest.skip("Multi-agent test requires OpenCode binary")

    print(f"\n✓ Running multi-agent task in {test_repo}")
    print("  Task: Create calculator module")
    print(f"  Model: {real_driver.config.model}")

    # Execute task with multi-agent orchestration
    # The strategy will automatically enable multi-agent for complex tasks
    result = await real_driver.execute_with_session(
        task="Create a calculator.py module with add, subtract, multiply, and divide functions. Include proper error handling for division by zero and comprehensive docstrings.",
        repo_root=str(test_repo),
        step_id="integration-test-multi-agent",
        context_paths=[],
        allowed_globs=["*.py"],
        deny_globs=["tests/**"],
        task_type="sequential",
    )

    print("\n✓ Multi-agent task completed:")
    print(f"  Success: {result.success}")
    print(f"  Summary: {result.summary}")
    print(f"  Model used: {result.model_used}")
    print(f"  Exit code: {result.exit_code}")
    print(f"  Files touched: {result.suspected_touched_paths}")

    # Verify result
    assert result.success is True, f"Task failed: {result.summary}"
    assert result.model_used is not None
    assert len(result.suspected_touched_paths) >= 1, "No files were created"
    assert "calculator.py" in result.suspected_touched_paths

    # Verify the calculator module was created
    calc_file = test_repo / "calculator.py"
    assert calc_file.exists(), "calculator.py was not created"

    # Verify it has the required functions
    calc_content = calc_file.read_text()
    assert "def add(" in calc_content
    assert "def subtract(" in calc_content
    assert "def multiply(" in calc_content
    assert "def divide(" in calc_content
    assert "ZeroDivisionError" in calc_content or "division by zero" in calc_content.lower()

    print("\n✓ Calculator module created with all required functions")
    print("  Functions: add, subtract, multiply, divide")
    print("  Error handling: division by zero implemented")


@pytest.mark.slow
@pytest.mark.asyncio
async def test_session_continuation(skip_if_no_api_key, real_driver, test_repo):
    """Test that sessions can be continued across multiple tasks."""
    print("\n✓ Task 1: Create greet function")
    result1 = await real_driver.execute_with_session(
        task="Create a function called greet() that takes a name parameter and prints a greeting",
        repo_root=str(test_repo),
        step_id="integration-test-session-1",
        context_paths=["example.py"],
        allowed_globs=["*.py"],
        deny_globs=[],
        create_session=True,
        task_type="quick",
    )

    session_id = result1.session_id
    print(f"  Session ID: {session_id}")
    print(f"  Success: {result1.success}")

    # Continue session with second task
    print(f"\n✓ Task 2: Add goodbye function (continuing session {session_id})")
    result2 = await real_driver.execute_with_session(
        task="Add a goodbye() function similar to greet() that prints a farewell message",
        repo_root=str(test_repo),
        step_id="integration-test-session-2",
        context_paths=["example.py"],
        allowed_globs=["*.py"],
        deny_globs=[],
        session_id=session_id,
        task_type="quick",
    )

    print(f"  Session ID: {result2.session_id}")
    print(f"  Success: {result2.success}")

    # Verify same session was used
    assert result2.session_id == session_id, "Session ID should be preserved"
    assert session_id is not None, "Session ID should not be None"

    # Verify both tasks succeeded
    assert result1.success is True, f"First task failed: {result1.summary}"
    assert result2.success is True, f"Second task failed: {result2.summary}"

    # Check that both functions were added
    example_content = (test_repo / "example.py").read_text()
    assert "def greet(" in example_content, "greet function not found"
    assert "def goodbye(" in example_content, "goodbye function not found"

    print("\n✓ Final file content:")
    print(example_content)
    print("\n✓ Session continuation successful!")


@pytest.mark.asyncio
async def test_structured_logging_integration(skip_if_no_api_key, real_driver, test_repo):
    """Test that structured logging works during task execution."""
    # Clear previous logs
    initial_log_count = len(real_driver.structured_logger.query_logs(limit=1000))

    print(f"\n✓ Initial log count: {initial_log_count}")

    # Execute task
    result = await real_driver.execute_with_session(
        task="Add a comment at the top of example.py explaining what the file does",
        repo_root=str(test_repo),
        step_id="integration-test-logging",
        context_paths=["example.py"],
        allowed_globs=["*.py"],
        deny_globs=[],
        task_type="quick",
    )

    print("\n✓ Task completed:")
    print(f"  Success: {result.success}")
    print(f"  Summary: {result.summary}")

    # Verify task succeeded
    assert result.success is True, f"Task failed: {result.summary}"

    # Check that logs were created
    final_log_count = len(real_driver.structured_logger.query_logs(limit=1000))
    new_logs = final_log_count - initial_log_count

    print(f"\n✓ Logs created during execution: {new_logs}")
    print(f"  Total logs: {final_log_count}")

    # Should have created at least a few log entries
    assert new_logs > 0, "No logs were created during task execution"

    # Query recent logs
    recent_logs = real_driver.structured_logger.query_logs(limit=5)
    for log in recent_logs:
        print(f"  [{log['level']}] {log['message']}")

    # Verify file was modified (OpenCode may add docstring instead of comment)
    example_content = (test_repo / "example.py").read_text()
    assert ('"""' in example_content or "#" in example_content or "comment" in example_content.lower())
    print("\n✓ File modified successfully")
    print("\n✓ Logging integration successful!")


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-s", "--tb=short"])
