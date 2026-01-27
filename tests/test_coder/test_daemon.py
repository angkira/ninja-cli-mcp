"""
Tests for OpenCode server daemon management.

Tests server lifecycle, port allocation, registry persistence, and cleanup.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ninja_coder.daemon import OpenCodeDaemon, get_daemon


@pytest.fixture
def temp_cache_dir():
    """Create temporary cache directory for tests."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def mock_psutil():
    """Mock psutil module."""
    with patch("ninja_coder.daemon.psutil") as mock:
        # Create mock Process class
        mock_process = Mock()
        mock_process.is_running.return_value = True
        mock_process.terminate.return_value = None
        mock_process.wait.return_value = None

        mock.Process.return_value = mock_process
        mock.pid_exists.return_value = True
        mock.NoSuchProcess = Exception
        mock.AccessDenied = Exception
        mock.TimeoutExpired = Exception

        yield mock


def test_daemon_initialization(temp_cache_dir):
    """Test OpenCodeDaemon initialization."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        assert daemon.cache_dir == temp_cache_dir
        assert daemon.servers_file == temp_cache_dir / "opencode_servers.json"
        assert isinstance(daemon._servers, dict)
        assert len(daemon._servers) == 0


def test_daemon_load_existing_servers(temp_cache_dir):
    """Test loading existing server registry from disk."""
    # Create a server registry file
    servers_data = {
        "/tmp/repo1": {
            "pid": 12345,
            "port": 4096,
            "url": "http://localhost:4096",
            "log_file": "/tmp/log1.log",
            "started_at": 1234567890.0,
        }
    }

    servers_file = temp_cache_dir / "opencode_servers.json"
    with open(servers_file, "w") as f:
        json.dump(servers_data, f)

    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        assert len(daemon._servers) == 1
        assert "/tmp/repo1" in daemon._servers
        assert daemon._servers["/tmp/repo1"]["pid"] == 12345
        assert daemon._servers["/tmp/repo1"]["port"] == 4096


def test_daemon_load_invalid_registry(temp_cache_dir):
    """Test handling of corrupted server registry."""
    # Create an invalid JSON file
    servers_file = temp_cache_dir / "opencode_servers.json"
    servers_file.write_text("invalid json{{{")

    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Should handle gracefully and start with empty registry
        assert len(daemon._servers) == 0


def test_save_servers(temp_cache_dir):
    """Test saving server registry to disk."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        daemon._servers["/tmp/repo1"] = {
            "pid": 12345,
            "port": 4096,
            "url": "http://localhost:4096",
        }

        daemon._save_servers()

        # Verify file was created
        assert daemon.servers_file.exists()

        # Verify content
        with open(daemon.servers_file) as f:
            data = json.load(f)

        assert "/tmp/repo1" in data
        assert data["/tmp/repo1"]["pid"] == 12345


def test_is_port_available():
    """Test port availability checking."""
    daemon = OpenCodeDaemon()

    # Test with a likely available port
    assert daemon._is_port_available(50000) is True

    # Test with a port that's likely in use (or at least more commonly used)
    # This is a best-effort test since we can't guarantee port state
    # Just verify the method doesn't crash
    result = daemon._is_port_available(80)
    assert isinstance(result, bool)


def test_find_available_port():
    """Test finding an available port."""
    daemon = OpenCodeDaemon()

    # Should find a port in the range
    port = daemon._find_available_port(start_port=50000)

    assert 50000 <= port < 50100
    assert daemon._is_port_available(port) is True


def test_find_available_port_exhausted():
    """Test handling when no ports are available."""
    daemon = OpenCodeDaemon()

    # Mock all ports as unavailable
    with patch.object(daemon, "_is_port_available", return_value=False):
        with pytest.raises(RuntimeError, match="No available ports found"):
            daemon._find_available_port()


def test_is_server_running_with_psutil(mock_psutil):
    """Test checking if server is running using psutil."""
    daemon = OpenCodeDaemon()

    # Test running process
    mock_psutil.pid_exists.return_value = True
    mock_psutil.Process.return_value.is_running.return_value = True

    assert daemon._is_server_running(12345) is True
    mock_psutil.pid_exists.assert_called_once_with(12345)
    mock_psutil.Process.assert_called_once_with(12345)


def test_is_server_running_process_not_exists(mock_psutil):
    """Test checking non-existent process."""
    daemon = OpenCodeDaemon()

    mock_psutil.pid_exists.return_value = False

    assert daemon._is_server_running(99999) is False


def test_is_server_running_no_psutil():
    """Test handling when psutil is not available."""
    with patch("ninja_coder.daemon.psutil", None):
        daemon = OpenCodeDaemon()

        # Should return False gracefully
        assert daemon._is_server_running(12345) is False


def test_start_server(temp_cache_dir, mock_psutil):
    """Test starting a new OpenCode server."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Mock subprocess.Popen
        mock_process = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process) as mock_popen:
            # Mock port checking
            with patch.object(daemon, "_is_port_available") as mock_port_check:
                # First call returns available port, subsequent calls show it's in use
                mock_port_check.side_effect = [True, False]

                url = daemon._start_server("/tmp/test-repo")

                # Verify server was started
                assert url.startswith("http://localhost:")
                assert "/tmp/test-repo" in daemon._servers

                # Verify Popen was called correctly
                mock_popen.assert_called_once()
                call_args = mock_popen.call_args

                assert call_args[0][0] == [
                    "opencode",
                    "serve",
                    "--port",
                    str(daemon._servers["/tmp/test-repo"]["port"]),
                ]
                assert call_args[1]["cwd"] == "/tmp/test-repo"
                assert call_args[1]["start_new_session"] is True

                # Verify registry was saved
                assert daemon.servers_file.exists()


def test_start_server_fails_to_start(temp_cache_dir, mock_psutil):
    """Test handling when server fails to start."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        mock_process = Mock()
        mock_process.pid = 12345
        mock_process.kill = Mock()

        with patch("subprocess.Popen", return_value=mock_process):
            # Mock port as always available (server never starts)
            with patch.object(daemon, "_is_port_available", return_value=True):
                with pytest.raises(RuntimeError, match="Failed to start OpenCode server"):
                    daemon._start_server("/tmp/test-repo")

                # Verify process was killed
                mock_process.kill.assert_called_once()


def test_start_server_subprocess_error(temp_cache_dir):
    """Test handling subprocess errors."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        with patch("subprocess.Popen", side_effect=Exception("Command not found")):
            with pytest.raises(RuntimeError, match="Failed to start OpenCode server"):
                daemon._start_server("/tmp/test-repo")


def test_get_or_start_server_new(temp_cache_dir, mock_psutil):
    """Test getting or starting a server when none exists."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        with patch.object(
            daemon, "_start_server", return_value="http://localhost:4096"
        ) as mock_start:
            url = daemon.get_or_start_server("/tmp/test-repo")

            assert url == "http://localhost:4096"
            mock_start.assert_called_once()


def test_get_or_start_server_existing_running(temp_cache_dir, mock_psutil):
    """Test getting existing running server."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add existing server
        daemon._servers[str(Path("/tmp/test-repo").resolve())] = {
            "pid": 12345,
            "port": 4096,
            "url": "http://localhost:4096",
        }

        # Mock server as running
        mock_psutil.pid_exists.return_value = True
        mock_psutil.Process.return_value.is_running.return_value = True

        with patch.object(daemon, "_start_server") as mock_start:
            url = daemon.get_or_start_server("/tmp/test-repo")

            # Should reuse existing server
            assert url == "http://localhost:4096"
            mock_start.assert_not_called()


def test_get_or_start_server_existing_dead(temp_cache_dir, mock_psutil):
    """Test handling when existing server is dead."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add existing server
        daemon._servers[str(Path("/tmp/test-repo").resolve())] = {
            "pid": 12345,
            "port": 4096,
            "url": "http://localhost:4096",
        }

        # Mock server as NOT running
        mock_psutil.pid_exists.return_value = False

        with patch.object(
            daemon, "_start_server", return_value="http://localhost:4097"
        ) as mock_start:
            url = daemon.get_or_start_server("/tmp/test-repo")

            # Should start new server
            assert url == "http://localhost:4097"
            mock_start.assert_called_once()


def test_stop_server(temp_cache_dir, mock_psutil):
    """Test stopping a server."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        repo_root = str(Path("/tmp/test-repo").resolve())

        # Add server
        daemon._servers[repo_root] = {
            "pid": 12345,
            "port": 4096,
            "url": "http://localhost:4096",
        }

        # Stop server
        result = daemon.stop_server("/tmp/test-repo")

        assert result is True
        assert repo_root not in daemon._servers

        # Verify process was terminated
        mock_psutil.Process.assert_called_once_with(12345)
        mock_psutil.Process.return_value.terminate.assert_called_once()


def test_stop_server_not_found(temp_cache_dir):
    """Test stopping non-existent server."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        result = daemon.stop_server("/tmp/nonexistent")

        assert result is False


def test_stop_all_servers(temp_cache_dir, mock_psutil):
    """Test stopping all servers."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add multiple servers with resolved paths
        repo1 = str(Path("/tmp/repo1").resolve())
        repo2 = str(Path("/tmp/repo2").resolve())
        repo3 = str(Path("/tmp/repo3").resolve())

        daemon._servers[repo1] = {"pid": 12345, "port": 4096}
        daemon._servers[repo2] = {"pid": 12346, "port": 4097}
        daemon._servers[repo3] = {"pid": 12347, "port": 4098}

        daemon.stop_all_servers()

        assert len(daemon._servers) == 0


def test_list_servers(temp_cache_dir, mock_psutil):
    """Test listing servers."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add servers
        daemon._servers["/tmp/repo1"] = {"pid": 12345, "port": 4096}
        daemon._servers["/tmp/repo2"] = {"pid": 12346, "port": 4097}

        # Mock all as running
        mock_psutil.pid_exists.return_value = True
        mock_psutil.Process.return_value.is_running.return_value = True

        servers = daemon.list_servers()

        assert len(servers) == 2
        assert "/tmp/repo1" in servers
        assert "/tmp/repo2" in servers


def test_list_servers_cleans_dead_servers(temp_cache_dir, mock_psutil):
    """Test that list_servers cleans up dead servers."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add servers
        daemon._servers["/tmp/repo1"] = {"pid": 12345, "port": 4096}
        daemon._servers["/tmp/repo2"] = {"pid": 12346, "port": 4097}

        # Mock first server as dead, second as alive
        def mock_is_running(pid):
            return pid == 12346

        with patch.object(daemon, "_is_server_running", side_effect=mock_is_running):
            servers = daemon.list_servers()

            # Only alive server should remain
            assert len(servers) == 1
            assert "/tmp/repo2" in servers
            assert "/tmp/repo1" not in servers


def test_get_daemon_singleton():
    """Test that get_daemon returns singleton instance."""
    daemon1 = get_daemon()
    daemon2 = get_daemon()

    assert daemon1 is daemon2


def test_path_normalization(temp_cache_dir, mock_psutil):
    """Test that paths are normalized correctly."""
    with patch("ninja_coder.daemon.get_cache_dir", return_value=temp_cache_dir):
        daemon = OpenCodeDaemon()

        # Add server with absolute path
        abs_path = str(Path("/tmp/test-repo").resolve())
        daemon._servers[abs_path] = {"pid": 12345, "port": 4096, "url": "http://localhost:4096"}

        # Mock server as running
        mock_psutil.pid_exists.return_value = True
        mock_psutil.Process.return_value.is_running.return_value = True

        # Try to get with different path formats (should normalize)
        url = daemon.get_or_start_server("/tmp/test-repo")

        assert url == "http://localhost:4096"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
