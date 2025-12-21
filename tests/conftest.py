"""Pytest configuration and fixtures."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def temp_repo() -> Generator[Path, None, None]:
    """Create a temporary repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create basic repo structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()

        # Create some sample files
        (repo_path / "src" / "main.py").write_text('print("Hello World")\n')
        (repo_path / "src" / "utils.py").write_text("def helper(): pass\n")
        (repo_path / "tests" / "test_main.py").write_text("def test_example(): pass\n")
        (repo_path / "README.md").write_text("# Test Project\n")
        (repo_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        yield repo_path


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Set up mock environment variables for testing."""
    env_vars = {
        "OPENROUTER_API_KEY": "test-api-key-12345",
        "NINJA_MODEL": "anthropic/claude-sonnet-4",
        "OPENAI_BASE_URL": "https://openrouter.ai/api/v1",
        "NINJA_CODE_BIN": "echo",  # Use echo as a mock command
    }

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    return env_vars


@pytest.fixture
def sample_plan_step() -> dict:
    """Create a sample plan step for testing."""
    return {
        "id": "step-001",
        "title": "Add hello function",
        "task": "Create a function called hello() that prints 'Hello World'",
        "context_paths": ["src/"],
        "allowed_globs": ["src/**/*.py"],
        "deny_globs": ["**/__pycache__/**"],
        "max_iterations": 3,
        "test_plan": {
            "unit": ["pytest tests/"],
            "e2e": [],
        },
        "constraints": {
            "max_tokens": 0,
            "time_budget_sec": 60,
        },
    }


@pytest.fixture
def sample_plan(sample_plan_step: dict) -> dict:
    """Create a sample execution plan for testing."""
    return {
        "repo_root": "/tmp/test-repo",
        "mode": "quick",
        "global_allowed_globs": ["**/*.py", "**/*.md"],
        "global_deny_globs": ["**/node_modules/**", "**/.git/**"],
        "steps": [
            sample_plan_step,
            {
                "id": "step-002",
                "title": "Add tests",
                "task": "Write tests for the hello function",
                "context_paths": ["tests/"],
                "allowed_globs": ["tests/**/*.py"],
                "deny_globs": [],
            },
        ],
    }
