"""
Tests for CLI adapter pattern.

These tests verify that different AI CLIs are properly detected and
configured with the correct command-line arguments.
"""

import json
import os

from ninja_cli_mcp.ninja_driver import NinjaConfig, NinjaDriver


def test_detect_cli_type_claude():
    """Test Claude CLI detection."""
    config = NinjaConfig(bin_path="/usr/bin/claude")
    driver = NinjaDriver(config)

    assert driver._detect_cli_type() == "claude"


def test_detect_cli_type_aider():
    """Test Aider CLI detection."""
    config = NinjaConfig(bin_path="/usr/local/bin/aider")
    driver = NinjaDriver(config)

    assert driver._detect_cli_type() == "aider"


def test_detect_cli_type_cursor():
    """Test Cursor CLI detection."""
    config = NinjaConfig(bin_path="/opt/cursor/cursor")
    driver = NinjaDriver(config)

    assert driver._detect_cli_type() == "cursor"


def test_detect_cli_type_generic():
    """Test generic CLI detection."""
    config = NinjaConfig(bin_path="/usr/bin/some-unknown-cli")
    driver = NinjaDriver(config)

    assert driver._detect_cli_type() == "generic"


def test_build_command_claude(tmp_path):
    """Test Claude CLI command building."""
    # Create a minimal instruction file
    task_file = tmp_path / "task.json"
    instruction = {
        "version": "1.0",
        "type": "quick_task",
        "repo_root": str(tmp_path),
        "instructions": "Test instruction",
        "file_scope": {
            "context_paths": ["test.py"],
            "allowed_globs": ["*.py"],
            "deny_globs": [],
        },
    }

    task_file.write_text(json.dumps(instruction))

    config = NinjaConfig(bin_path="claude")
    driver = NinjaDriver(config)

    cmd = driver._build_command(task_file, str(tmp_path))

    # Claude should use --print and --dangerously-skip-permissions
    assert cmd[0] == "claude"
    assert "--print" in cmd
    assert "--dangerously-skip-permissions" in cmd

    # Should not have the old --prompt, --cwd, --yes flags
    assert "--prompt" not in cmd
    assert "--cwd" not in cmd
    assert "--yes" not in cmd


def test_build_command_aider(tmp_path):
    """Test Aider CLI command building."""
    task_file = tmp_path / "task.json"
    instruction = {
        "version": "1.0",
        "type": "quick_task",
        "repo_root": str(tmp_path),
        "instructions": "Test instruction",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    task_file.write_text(json.dumps(instruction))

    config = NinjaConfig(bin_path="aider")
    driver = NinjaDriver(config)

    cmd = driver._build_command(task_file, str(tmp_path))

    # Aider should use --yes and --message
    assert cmd[0] == "aider"
    assert "--yes" in cmd
    assert "--message" in cmd


def test_build_prompt_text(tmp_path):
    """Test prompt text building from instruction."""
    config = NinjaConfig(bin_path="claude")
    driver = NinjaDriver(config)

    instruction = {
        "instructions": "This is a test task.",
        "repo_root": str(tmp_path),
        "file_scope": {
            "context_paths": ["src/main.py", "tests/test_main.py"],
            "allowed_globs": ["src/**/*.py", "tests/**/*.py"],
            "deny_globs": ["**/__pycache__/**"],
        },
        "test_plan": {
            "unit": ["pytest tests/test_main.py"],
            "e2e": ["pytest tests/integration/"],
        },
    }

    prompt = driver._build_prompt_text(instruction, str(tmp_path))

    # Check that all important elements are included
    assert "This is a test task." in prompt
    assert "FILE SCOPE" in prompt
    assert str(tmp_path) in prompt
    assert "src/main.py" in prompt
    assert "tests/test_main.py" in prompt
    assert "src/**/*.py" in prompt
    assert "**/__pycache__/**" in prompt
    assert "TEST PLAN" in prompt
    assert "pytest tests/test_main.py" in prompt
    assert "pytest tests/integration/" in prompt


def test_claude_cli_detection_with_path():
    """Test Claude CLI detection with full path."""
    config = NinjaConfig(bin_path="/home/user/.nvm/versions/node/v25.0.0/bin/claude")
    driver = NinjaDriver(config)

    assert driver._detect_cli_type() == "claude"


def test_cli_command_format_without_invalid_flags(tmp_path):
    """Test that commands don't use flags that don't exist."""
    task_file = tmp_path / "task.json"
    instruction = {
        "version": "1.0",
        "type": "quick_task",
        "repo_root": str(tmp_path),
        "instructions": "Test",
        "file_scope": {
            "context_paths": [],
            "allowed_globs": ["**/*"],
            "deny_globs": [],
        },
    }

    task_file.write_text(json.dumps(instruction))

    # Test all supported CLI types
    cli_types = ["claude", "aider", "cursor"]

    for cli_name in cli_types:
        config = NinjaConfig(bin_path=cli_name)
        driver = NinjaDriver(config)

        cmd = driver._build_command(task_file, str(tmp_path))

        # Verify command is a list
        assert isinstance(cmd, list)
        assert len(cmd) > 0

        # First element should be the binary name
        assert cli_name in cmd[0].lower()


def test_config_model_priority():
    """Test that model selection follows correct priority."""
    # Save original env
    original_ninja = os.environ.get("NINJA_MODEL")
    original_openrouter = os.environ.get("OPENROUTER_MODEL")
    original_openai = os.environ.get("OPENAI_MODEL")

    try:
        # Test NINJA_MODEL has highest priority
        os.environ["NINJA_MODEL"] = "model-from-ninja"
        os.environ["OPENROUTER_MODEL"] = "model-from-openrouter"
        os.environ["OPENAI_MODEL"] = "model-from-openai"

        config = NinjaConfig.from_env()
        assert config.model == "model-from-ninja"

        # Test OPENROUTER_MODEL is second priority
        del os.environ["NINJA_MODEL"]
        config = NinjaConfig.from_env()
        assert config.model == "model-from-openrouter"

        # Test OPENAI_MODEL is third priority
        del os.environ["OPENROUTER_MODEL"]
        config = NinjaConfig.from_env()
        assert config.model == "model-from-openai"

        # Test default when none set
        del os.environ["OPENAI_MODEL"]
        config = NinjaConfig.from_env()
        assert config.model == "anthropic/claude-haiku-4.5-20250929"

    finally:
        # Restore original env
        for key, value in [
            ("NINJA_MODEL", original_ninja),
            ("OPENROUTER_MODEL", original_openrouter),
            ("OPENAI_MODEL", original_openai),
        ]:
            if value is not None:
                os.environ[key] = value
            else:
                os.environ.pop(key, None)
