"""
Integration tests for OpenCode daemon (requires actual opencode installation).

These tests are marked with @pytest.mark.integration and will be skipped
unless explicitly run with: pytest -m integration
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from ninja_coder.daemon import get_daemon


# Skip if opencode CLI is not installed
OPENCODE_AVAILABLE = shutil.which("opencode") is not None


@pytest.mark.integration
@pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
@pytest.mark.skip(reason="Flaky - needs investigation")
def test_daemon_real_server():
    """
    Test starting a real OpenCode server.

    This test requires:
    - opencode CLI to be installed and in PATH
    - A valid repository directory

    Run with: pytest -m integration tests/test_coder/test_daemon_integration.py
    """
    daemon = get_daemon()

    with tempfile.TemporaryDirectory() as tmp_dir:
        repo_root = Path(tmp_dir).resolve()  # Resolve symlinks for macOS

        # Create a simple repo structure
        (repo_root / "README.md").write_text("# Test Project\n")

        try:
            # Start server
            url = daemon.get_or_start_server(str(repo_root))

            assert url.startswith("http://localhost:")
            assert str(repo_root) in daemon.list_servers()

            # Verify we can reuse the same server
            url2 = daemon.get_or_start_server(str(repo_root))
            assert url == url2

        finally:
            # Clean up
            daemon.stop_server(str(repo_root))

            # Verify cleanup
            servers = daemon.list_servers()
            assert str(repo_root) not in servers


@pytest.mark.integration
@pytest.mark.skipif(not OPENCODE_AVAILABLE, reason="opencode CLI not installed")
@pytest.mark.skip(reason="Flaky - needs investigation")
def test_daemon_multiple_repos():
    """
    Test managing servers for multiple repositories.

    Run with: pytest -m integration tests/test_coder/test_daemon_integration.py
    """
    daemon = get_daemon()

    with tempfile.TemporaryDirectory() as tmp_dir1:
        with tempfile.TemporaryDirectory() as tmp_dir2:
            repo1 = Path(tmp_dir1).resolve()  # Resolve symlinks for macOS
            repo2 = Path(tmp_dir2).resolve()  # Resolve symlinks for macOS

            # Create simple repo structures
            (repo1 / "README.md").write_text("# Repo 1\n")
            (repo2 / "README.md").write_text("# Repo 2\n")

            try:
                # Start servers for both repos
                url1 = daemon.get_or_start_server(str(repo1))
                url2 = daemon.get_or_start_server(str(repo2))

                # Should have different URLs (different ports)
                assert url1 != url2

                # Both should be in the list
                servers = daemon.list_servers()
                assert str(repo1) in servers
                assert str(repo2) in servers
                assert len(servers) >= 2

            finally:
                # Clean up both
                daemon.stop_server(str(repo1))
                daemon.stop_server(str(repo2))


if __name__ == "__main__":
    # Run integration tests
    pytest.main([__file__, "-v", "-m", "integration"])
