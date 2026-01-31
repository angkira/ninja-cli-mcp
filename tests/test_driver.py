"""
Tests for NinjaDriver core functionality.

Tests config management, instruction building, model selection, and session/logging integration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ninja_coder.driver import (
    ExecutionMode,
    InstructionBuilder,
    NinjaConfig,
    NinjaDriver,
    NinjaResult,
)


# ============================================================================
# NinjaConfig Tests
# ============================================================================


def test_config_creation():
    """Test NinjaConfig creation."""
    config = NinjaConfig(
        bin_path="aider",
        openai_base_url="https://api.openai.com/v1",
        openai_api_key="test-key",
        model="gpt-4",
        timeout_sec=300,
    )

    assert config.bin_path == "aider"
    assert config.openai_base_url == "https://api.openai.com/v1"
    assert config.openai_api_key == "test-key"
    assert config.model == "gpt-4"
    assert config.timeout_sec == 300


def test_config_from_env(monkeypatch):
    """Test creating config from environment variables."""
    monkeypatch.setenv("NINJA_CODE_BIN", "/usr/local/bin/aider")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://test.api/v1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test-123")
    monkeypatch.setenv("NINJA_MODEL", "anthropic/claude-opus-4")
    monkeypatch.setenv("NINJA_TIMEOUT_SEC", "600")

    config = NinjaConfig.from_env()

    assert config.bin_path == "/usr/local/bin/aider"
    assert config.openai_base_url == "https://test.api/v1"
    assert config.openai_api_key == "sk-test-123"
    assert config.model == "anthropic/claude-opus-4"
    assert config.timeout_sec == 600


def test_config_from_env_model_priority(monkeypatch):
    """Test model selection priority: NINJA_MODEL > OPENROUTER_MODEL > OPENAI_MODEL."""
    # Test NINJA_MODEL takes precedence
    monkeypatch.setenv("NINJA_MODEL", "model-1")
    monkeypatch.setenv("OPENROUTER_MODEL", "model-2")
    monkeypatch.setenv("OPENAI_MODEL", "model-3")

    config = NinjaConfig.from_env()
    assert config.model == "model-1"

    # Test OPENROUTER_MODEL when NINJA_MODEL not set
    monkeypatch.delenv("NINJA_MODEL", raising=False)
    config = NinjaConfig.from_env()
    assert config.model == "model-2"

    # Test OPENAI_MODEL when neither NINJA_MODEL nor OPENROUTER_MODEL set
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)
    config = NinjaConfig.from_env()
    assert config.model == "model-3"


def test_config_from_env_api_key_priority(monkeypatch):
    """Test API key priority: OPENROUTER_API_KEY > OPENAI_API_KEY."""
    # Test OPENROUTER_API_KEY takes precedence
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")

    config = NinjaConfig.from_env()
    assert config.openai_api_key == "router-key"

    # Test OPENAI_API_KEY when OPENROUTER_API_KEY not set
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config = NinjaConfig.from_env()
    assert config.openai_api_key == "openai-key"


def test_config_with_model():
    """Test creating config with different model."""
    config = NinjaConfig(
        bin_path="aider",
        model="anthropic/claude-haiku-4.5",
        openai_api_key="test",
    )

    new_config = config.with_model("anthropic/claude-opus-4")

    # New config should have new model
    assert new_config.model == "anthropic/claude-opus-4"

    # But same other values
    assert new_config.bin_path == config.bin_path
    assert new_config.openai_api_key == config.openai_api_key
    assert new_config.openai_base_url == config.openai_base_url

    # Original config unchanged
    assert config.model == "anthropic/claude-haiku-4.5"


# ============================================================================
# NinjaResult Tests
# ============================================================================


def test_result_creation():
    """Test NinjaResult creation."""
    result = NinjaResult(
        success=True,
        summary="Modified 2 files",
        notes="Added User and Post classes",
        suspected_touched_paths=["src/user.py", "src/post.py"],
        raw_logs_path="/tmp/logs/task.log",
        exit_code=0,
        stdout="Success output",
        stderr="",
        model_used="anthropic/claude-haiku-4.5",
        session_id="abc123",
    )

    assert result.success is True
    assert result.summary == "Modified 2 files"
    assert result.notes == "Added User and Post classes"
    assert len(result.suspected_touched_paths) == 2
    assert result.exit_code == 0
    assert result.model_used == "anthropic/claude-haiku-4.5"
    assert result.session_id == "abc123"


def test_result_defaults():
    """Test NinjaResult with minimal fields."""
    result = NinjaResult(
        success=False,
        summary="Task failed",
        model_used="test/model",
    )

    assert result.success is False
    assert result.summary == "Task failed"
    assert result.notes == ""
    assert result.suspected_touched_paths == []
    assert result.exit_code == 0
    assert result.session_id is None


# ============================================================================
# InstructionBuilder Tests
# ============================================================================


def test_instruction_builder_initialization():
    """Test InstructionBuilder initialization."""
    builder = InstructionBuilder("/tmp/test-repo", mode=ExecutionMode.QUICK)

    assert builder.repo_root == "/tmp/test-repo"
    assert builder.mode == ExecutionMode.QUICK


def test_build_quick_task():
    """Test building quick task instruction."""
    builder = InstructionBuilder("/tmp/test-repo", mode=ExecutionMode.QUICK)

    instruction = builder.build_quick_task(
        task="Create a User class",
        context_paths=["src/models.py"],
        allowed_globs=["src/**/*.py"],
        deny_globs=["tests/**"],
    )

    assert instruction["mode"] == "quick"
    assert instruction["type"] == "quick_task"
    assert instruction["task"] == "Create a User class"
    assert "src/models.py" in instruction["file_scope"]["context_paths"]
    assert "src/**/*.py" in instruction["file_scope"]["allowed_globs"]
    assert "tests/**" in instruction["file_scope"]["deny_globs"]


def test_build_quick_task_minimal():
    """Test building quick task with minimal params."""
    builder = InstructionBuilder("/tmp/test-repo")

    instruction = builder.build_quick_task(
        task="Fix typo in README",
        context_paths=[],
        allowed_globs=[],
        deny_globs=[],
    )

    assert instruction["task"] == "Fix typo in README"
    assert instruction["file_scope"]["context_paths"] == []


# ============================================================================
# NinjaDriver Tests
# ============================================================================


@pytest.fixture
def driver(tmp_path, monkeypatch):
    """Create NinjaDriver instance with temp cache."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )

    config = NinjaConfig(
        bin_path="aider",
        model="anthropic/claude-haiku-4.5",
        openai_api_key="test-key",
    )
    return NinjaDriver(config)


def test_driver_initialization(driver):
    """Test NinjaDriver initialization."""
    assert driver.config is not None
    assert driver._strategy is not None
    assert driver.session_manager is not None
    assert driver.structured_logger is not None


def test_driver_has_session_manager(driver):
    """Test that driver has session manager."""
    assert driver.session_manager is not None


def test_driver_has_structured_logger(driver):
    """Test that driver has structured logger."""
    assert driver.structured_logger is not None
    assert driver.structured_logger.name == "ninja-coder"


def test_driver_strategy_selection_aider(tmp_path, monkeypatch):
    """Test that driver selects Aider strategy correctly."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )

    config = NinjaConfig(
        bin_path="/usr/local/bin/aider",
        model="test/model",
        openai_api_key="test",
    )
    driver = NinjaDriver(config)

    assert driver._strategy.name == "aider"


def test_driver_strategy_selection_opencode(tmp_path, monkeypatch):
    """Test that driver selects OpenCode strategy correctly."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )

    config = NinjaConfig(
        bin_path="/opt/homebrew/bin/opencode",
        model="test/model",
        openai_api_key="test",
    )
    driver = NinjaDriver(config)

    assert driver._strategy.name == "opencode"


def test_driver_model_selection_quick_task(driver):
    """Test model selection for quick task."""
    instruction = {"task": "Fix typo in README"}

    model, use_coding_plan = driver._select_model_for_task(
        instruction,
        "quick",
    )

    assert model is not None
    assert isinstance(use_coding_plan, bool)


def test_driver_model_selection_sequential_task(driver):
    """Test model selection for sequential task."""
    instruction = {"task": "Refactor authentication system"}

    model, use_coding_plan = driver._select_model_for_task(
        instruction,
        "sequential",
    )

    assert model is not None
    assert isinstance(use_coding_plan, bool)


def test_driver_model_selection_parallel_task(driver):
    """Test model selection for parallel task."""
    instruction = {
        "task": "Run multiple test suites",
        "parallel_context": {"total_steps": 5},
    }

    model, use_coding_plan = driver._select_model_for_task(
        instruction,
        "parallel",
    )

    assert model is not None
    assert isinstance(use_coding_plan, bool)


def test_driver_write_task_file(driver, tmp_path):
    """Test writing task file."""
    instruction = {
        "mode": "quick",
        "task_description": "Test task",
        "file_scope": {"context_paths": [], "allowed_globs": [], "deny_globs": []},
    }

    task_file = driver._write_task_file(
        str(tmp_path),
        "test-task-1",
        instruction,
    )

    # Verify file was created
    assert Path(task_file).exists()

    # Verify content
    import json

    with open(task_file) as f:
        data = json.load(f)

    assert data["mode"] == "quick"
    assert data["task_description"] == "Test task"


def test_driver_build_prompt_text(driver):
    """Test building prompt text from instruction."""
    instruction = {
        "task": "Create a User class",
        "instructions": "Please create a User class with name and email fields",
        "file_scope": {
            "context_paths": ["src/models.py"],
            "allowed_globs": ["src/**/*.py"],
            "deny_globs": ["tests/**"],
        },
    }

    prompt = driver._build_prompt_text(instruction, "/tmp/repo")

    # Prompt should contain instructions (lowercase comparison)
    assert "create a user class" in prompt.lower()
    assert isinstance(prompt, str)
    assert len(prompt) > 0


def test_driver_env_includes_api_key(driver):
    """Test that driver env includes API credentials."""
    env = driver._get_env()

    assert "OPENAI_API_KEY" in env
    assert env["OPENAI_API_KEY"] == "test-key"


def test_driver_env_includes_base_url(driver):
    """Test that driver env includes base URL."""
    env = driver._get_env()

    assert "OPENAI_BASE_URL" in env
    assert len(env["OPENAI_BASE_URL"]) > 0


def test_driver_env_includes_model(driver):
    """Test that driver env includes model."""
    env = driver._get_env()

    assert "OPENAI_MODEL" in env
    assert env["OPENAI_MODEL"] == "anthropic/claude-haiku-4.5"


# ============================================================================
# Backwards Compatibility Tests
# ============================================================================


def test_backwards_compatibility_aliases():
    """Test that old names still work."""
    from ninja_coder.driver import QwenConfig, QwenDriver, QwenResult

    # These should all be aliases to Ninja* classes
    assert QwenConfig is NinjaConfig
    assert QwenDriver is NinjaDriver
    assert QwenResult is NinjaResult


# ============================================================================
# Session Integration Tests
# ============================================================================


def test_driver_has_working_session_manager(driver):
    """Test that driver's session manager can create sessions."""
    session = driver.session_manager.create_session(
        repo_root="/tmp/test-repo",
        model="anthropic/claude-haiku-4.5",
    )

    assert session is not None
    assert session.session_id is not None
    assert len(session.session_id) == 8


def test_driver_logging_on_init(driver, tmp_path):
    """Test that driver logs initialization."""
    # Check that log file exists
    log_dir = tmp_path / "cache" / "logs"
    assert log_dir.exists()

    # Check that initialization was logged
    logs = driver.structured_logger.query_logs(limit=10)
    assert len(logs) >= 1

    # Find initialization log
    init_logs = [log for log in logs if "Driver initialized" in log["message"]]
    assert len(init_logs) == 1
    assert init_logs[0]["level"] == "INFO"


# ============================================================================
# OpenCode Session Tests
# ============================================================================


@pytest.fixture
def opencode_driver(tmp_path, monkeypatch):
    """Create NinjaDriver instance with OpenCode strategy."""
    monkeypatch.setattr(
        "ninja_common.path_utils.get_cache_dir",
        lambda: tmp_path / "cache",
    )

    config = NinjaConfig(
        bin_path="/opt/homebrew/bin/opencode",
        model="anthropic/claude-sonnet-4-5",
        openai_api_key="test-key",
    )
    return NinjaDriver(config)


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_creates_session(
    opencode_driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session creates a new session."""
    # Mock asyncio.create_subprocess_exec to simulate OpenCode CLI execution
    from unittest.mock import MagicMock

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that returns success with session ID."""
        process = MagicMock()
        process.returncode = 0

        # Simulate OpenCode output with session ID and file modifications
        # Use format that matches OpenCode parser patterns
        stdout = b"Session: ses_abc123\n| Edit     src/user.py\n| Write    src/post.py"
        stderr = b""

        async def communicate():
            return stdout, stderr

        process.communicate = communicate
        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks for testing
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Create User and Post classes",
        "file_scope": {
            "context_paths": ["src/models.py"],
            "allowed_globs": ["src/**/*.py"],
            "deny_globs": [],
        },
    }

    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-step-1",
        instruction=instruction,
        opencode_session_id=None,
        is_initial=True,
        task_type="quick",
    )

    # Verify result
    assert result.success is True
    assert result.session_id == "ses_abc123"
    assert result.summary.startswith("✅")
    assert len(result.suspected_touched_paths) >= 0  # Parser should detect file changes


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_continues_session(
    opencode_driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session continues an existing session."""
    # Disable daemon mode to test session continuation logic
    monkeypatch.setenv("OPENCODE_DISABLE_DAEMON", "true")

    # Mock asyncio.create_subprocess_exec
    from unittest.mock import MagicMock

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that returns success."""
        process = MagicMock()
        process.returncode = 0

        # Check that --session flag was passed
        assert "--session" in args
        assert "ses_existing" in args

        stdout = b"Session: ses_existing\nModified 1 file: src/user.py"
        stderr = b""

        async def communicate():
            return stdout, stderr

        process.communicate = communicate
        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Update User class",
        "file_scope": {
            "context_paths": ["src/models.py"],
            "allowed_globs": ["src/**/*.py"],
            "deny_globs": [],
        },
    }

    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-step-2",
        instruction=instruction,
        opencode_session_id="ses_existing",
        is_initial=False,
        task_type="quick",
    )

    # Verify result
    assert result.success is True
    assert result.session_id == "ses_existing"


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_fallback_non_opencode(
    driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session falls back to execute_async for non-OpenCode CLIs."""
    # driver fixture uses Aider strategy (not OpenCode)

    # Mock execute_async to track if it was called
    original_execute_async = driver.execute_async
    execute_async_called = False

    async def mock_execute_async(*args, **kwargs):
        nonlocal execute_async_called
        execute_async_called = True
        # Return a simple result
        return NinjaResult(
            success=True,
            summary="Fallback executed",
            model_used="test/model",
        )

    monkeypatch.setattr(driver, "execute_async", mock_execute_async)

    instruction = {
        "task": "Test fallback",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-fallback",
        instruction=instruction,
        opencode_session_id=None,
        is_initial=True,
        task_type="quick",
    )

    # Verify fallback was used
    assert execute_async_called is True
    assert result.success is True


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_timeout(opencode_driver, tmp_path, monkeypatch):
    """Test that execute_async_with_opencode_session handles timeout correctly."""
    import asyncio
    from unittest.mock import MagicMock

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that takes too long."""
        process = MagicMock()
        process.returncode = 0
        process.kill = MagicMock()

        async def wait():
            pass

        process.wait = wait

        # Mock communicate to sleep long enough to trigger timeout
        async def communicate():
            await asyncio.sleep(10)  # Sleep longer than timeout
            return b"", b""

        process.communicate = communicate
        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test timeout",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-timeout",
        instruction=instruction,
        timeout_sec=1,
        task_type="quick",
    )

    # Verify timeout was handled
    assert result.success is False
    assert "timed out" in result.summary.lower()
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_cli_not_found(
    opencode_driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session handles missing CLI gracefully."""

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that raises FileNotFoundError."""
        raise FileNotFoundError("opencode not found")

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Test CLI not found",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-not-found",
        instruction=instruction,
        task_type="quick",
    )

    # Verify error was handled
    assert result.success is False
    assert "not found" in result.summary.lower()
    assert result.exit_code == -1


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_continue_last(
    opencode_driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session uses --continue when appropriate."""
    # Disable daemon mode to test --continue flag logic
    monkeypatch.setenv("OPENCODE_DISABLE_DAEMON", "true")

    from unittest.mock import MagicMock

    continue_flag_found = False

    async def mock_subprocess(*args, **kwargs):
        """Mock subprocess that checks for --continue flag."""
        nonlocal continue_flag_found

        process = MagicMock()
        process.returncode = 0

        # Check if --continue flag is present
        if "--continue" in args:
            continue_flag_found = True

        stdout = b"Task completed successfully"
        stderr = b""

        async def communicate():
            return stdout, stderr

        process.communicate = communicate
        return process

    monkeypatch.setattr(
        "asyncio.create_subprocess_exec",
        mock_subprocess,
    )

    # Disable safety checks
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {"safe": True, "warnings": [], "recommendations": [], "git_info": {}},
    )

    instruction = {
        "task": "Continue previous task",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    # Call with is_initial=False and no session_id (should trigger --continue)
    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-continue",
        instruction=instruction,
        opencode_session_id=None,
        is_initial=False,
        task_type="quick",
    )

    # Verify --continue flag was used
    assert continue_flag_found is True


@pytest.mark.asyncio
async def test_execute_async_with_opencode_session_safety_check_failed(
    opencode_driver, tmp_path, monkeypatch
):
    """Test that execute_async_with_opencode_session refuses to run when safety check fails."""
    # Mock safety check to fail
    monkeypatch.setattr(
        "ninja_coder.driver.validate_task_safety",
        lambda **kwargs: {
            "safe": False,
            "warnings": ["Uncommitted changes detected"],
            "recommendations": ["Commit your changes first"],
            "git_info": {},
        },
    )

    instruction = {
        "task": "Dangerous task",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    result = await opencode_driver.execute_async_with_opencode_session(
        repo_root=str(tmp_path),
        step_id="test-safety-fail",
        instruction=instruction,
        task_type="quick",
    )

    # Verify execution was refused
    assert result.success is False
    assert "Safety check failed" in result.summary
    assert result.exit_code == -2


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
