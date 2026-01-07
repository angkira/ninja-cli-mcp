"""
Smoke tests that verify basic end-to-end functionality.

These tests perform quick sanity checks without requiring API keys.
"""

import subprocess
import sys

import pytest


pytestmark = pytest.mark.unit


def test_import_ninja_coder():
    """Test that ninja_coder module can be imported."""
    try:
        import ninja_coder
        import ninja_coder.server
        import ninja_coder.tools

        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import ninja_coder: {e}")


def test_import_ninja_researcher():
    """Test that ninja_researcher module can be imported."""
    try:
        import ninja_researcher
        import ninja_researcher.search_providers
        import ninja_researcher.server
        import ninja_researcher.tools

        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import ninja_researcher: {e}")


def test_import_ninja_secretary():
    """Test that ninja_secretary module can be imported."""
    try:
        import ninja_secretary
        import ninja_secretary.server

        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import ninja_secretary: {e}")


def test_import_ninja_common():
    """Test that ninja_common module can be imported."""
    try:
        import ninja_common
        import ninja_common.config_manager
        import ninja_common.daemon

        assert True
    except ImportError as e:
        pytest.fail(f"Failed to import ninja_common: {e}")


def test_ninja_config_cli_help():
    """Test that ninja-config CLI help works."""
    result = subprocess.run(
        [sys.executable, "-m", "ninja_common.config_cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower() or "ninja-config" in result.stdout.lower()


def test_ninja_daemon_help():
    """Test that ninja-daemon CLI help works."""
    result = subprocess.run(
        [sys.executable, "-m", "ninja_common.daemon", "--help"],
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert "usage:" in result.stdout.lower() or "daemon" in result.stdout.lower()


def test_config_manager_basic():
    """Test that ConfigManager can be instantiated."""
    import tempfile
    from pathlib import Path

    from ninja_common.config_manager import ConfigManager

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "test.env"
        manager = ConfigManager(str(config_file))

        # Test basic operations
        manager.set("TEST_KEY", "test_value")
        value = manager.get("TEST_KEY")
        assert value == "test_value"

        # Test masking
        manager.set("TEST_API_KEY", "sk-1234567890abcdefghijklmnopqrstuvwxyz")
        masked = manager.get_masked("TEST_API_KEY")
        assert "..." in masked
        assert masked.startswith("sk-12345")


def test_search_provider_factory():
    """Test that SearchProviderFactory works."""
    from ninja_researcher.search_providers import SearchProviderFactory

    # Test getting DuckDuckGo provider (always available)
    provider = SearchProviderFactory.get_provider("duckduckgo")
    assert provider is not None
    assert provider.get_name() == "duckduckgo"

    # Test getting available providers
    available = SearchProviderFactory.get_available_providers()
    assert "duckduckgo" in available
    assert len(available) >= 1


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
