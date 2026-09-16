"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest


# Add src directory to Python path for imports
_root = Path(__file__).parent.parent
if str(_root / "src") not in sys.path:
    sys.path.insert(0, str(_root / "src"))


if TYPE_CHECKING:
    from collections.abc import Generator

    from pytest import MonkeyPatch


@pytest.fixture(autouse=True)
def _isolate_environ() -> Generator[None, None, None]:
    """Snapshot/restore ``os.environ`` around every test.

    ``monkeypatch.setenv/delenv`` already rolls back its own changes, but
    production code such as ``ConfigManager.export_env()`` (which loads the
    developer's real ``~/.ninja-mcp.env`` into the process env) writes to
    ``os.environ`` directly. Without this guard those values
    (``NINJA_CODER_MODEL``, ``NINJA_MODEL_QUICK``, ...) leak into all
    subsequently collected tests and make model-resolution tests order
    dependent. The real ``~/.ninja-mcp.env`` file itself is never touched.
    """
    saved = os.environ.copy()
    yield
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture(autouse=True)
def _isolate_secret_store(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> Generator[None, None, None]:
    """Keep the encrypted store (and its password) out of the real HOME.

    Without this, any test that writes a secret via ``ConfigManager.set`` /
    ``set_secret`` would clobber the developer's real ``~/.ninja/credentials.db``.
    """
    monkeypatch.setenv("NINJA_CREDENTIALS_DB", str(tmp_path / "credentials.db"))
    for var in (
        "NINJA_CREDENTIAL_PASSWORD",
        "NINJA_CREDENTIAL_FD",
        "CREDENTIALS_DIRECTORY",
        "NINJA_STORE_PASSWORD_FILE",
    ):
        monkeypatch.delenv(var, raising=False)
    ss = None
    try:
        import ninja_config.secrets_store as ss

        ss._reset_singletons()
    except Exception:
        ss = None
    yield
    if ss is not None:
        ss._reset_singletons()


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


@pytest.fixture
def temp_test_repo() -> Generator[Path, None, None]:
    """Create a temporary repository specifically for coder evaluation tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)

        # Create basic repo structure
        (repo_path / "src").mkdir()
        (repo_path / "tests").mkdir()
        (repo_path / "docs").mkdir()

        # Create some sample files
        (repo_path / "src" / "main.py").write_text('print("Hello World")\n')
        (repo_path / "src" / "utils.py").write_text("def helper(): pass\n")
        (repo_path / "tests" / "test_main.py").write_text("def test_example(): pass\n")
        (repo_path / "README.md").write_text("# Test Project\n")
        (repo_path / "pyproject.toml").write_text('[project]\nname = "test"\n')

        yield repo_path


@pytest.fixture
def mock_ninja_result():
    """Create a mock NinjaResult for testing."""
    from ninja_coder.driver import NinjaResult
    return NinjaResult(
        success=True,
        summary="✅ Modified 1 file(s): src/new_function.py",
        notes="",
        suspected_touched_paths=["src/new_function.py"],
        raw_logs_path="/tmp/logs/test.log",
        exit_code=0,
        stdout="Created src/new_function.py with hello_world function",
        stderr="",
        model_used="anthropic/claude-sonnet-4"
    )
