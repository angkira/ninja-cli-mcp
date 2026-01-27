"""
OpenCode Server Daemon Manager.

Manages persistent OpenCode servers per repository for 50x performance improvement.
Each repo gets its own server instance on a unique port.

Example usage:
    ```python
    from ninja_coder.daemon import get_daemon

    # Get or start a server for a repository
    daemon = get_daemon()
    url = daemon.get_or_start_server("/path/to/repo")
    # url will be something like "http://localhost:4096"

    # List all running servers
    servers = daemon.list_servers()
    for repo_root, info in servers.items():
        print(f"{repo_root}: {info['url']} (PID {info['pid']})")

    # Stop a specific server
    daemon.stop_server("/path/to/repo")

    # Stop all servers
    daemon.stop_all_servers()
    ```
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from pathlib import Path
from typing import Any

try:
    import psutil
except ImportError:
    psutil = None  # type: ignore

from ninja_common.logging_utils import get_logger
from ninja_common.path_utils import get_cache_dir

logger = get_logger(__name__)


class OpenCodeDaemon:
    """Manages OpenCode server instances per repository."""

    def __init__(self) -> None:
        """Initialize daemon manager."""
        self.cache_dir = get_cache_dir()
        self.servers_file = self.cache_dir / "opencode_servers.json"
        self._servers: dict[str, dict[str, Any]] = self._load_servers()

    def _load_servers(self) -> dict[str, dict[str, Any]]:
        """Load server registry from disk.

        Returns:
            Dict mapping repo_root to server info.
        """
        if self.servers_file.exists():
            try:
                with open(self.servers_file) as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load server registry: {e}")
        return {}

    def _save_servers(self) -> None:
        """Save server registry to disk."""
        try:
            self.servers_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.servers_file, "w") as f:
                json.dump(self._servers, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save server registry: {e}")

    def _is_port_available(self, port: int) -> bool:
        """Check if port is available.

        Args:
            port: Port number to check.

        Returns:
            True if port is available (not listening), False otherwise.
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) != 0

    def _find_available_port(self, start_port: int = 4096) -> int:
        """Find an available port starting from start_port.

        Args:
            start_port: Starting port number to search from.

        Returns:
            Available port number.

        Raises:
            RuntimeError: If no available ports found in range.
        """
        for port in range(start_port, start_port + 100):
            if self._is_port_available(port):
                return port
        raise RuntimeError("No available ports found")

    def _is_server_running(self, pid: int) -> bool:
        """Check if server process is still running.

        Args:
            pid: Process ID to check.

        Returns:
            True if process exists and is running, False otherwise.
        """
        if psutil is None:
            logger.warning("psutil not available, cannot check if server is running")
            return False

        try:
            return psutil.pid_exists(pid) and psutil.Process(pid).is_running()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return False

    def get_or_start_server(self, repo_root: str) -> str:
        """Get existing server URL or start a new server for this repo.

        Args:
            repo_root: Absolute path to repository root.

        Returns:
            Server URL (e.g., "http://localhost:4096")
        """
        repo_root = str(Path(repo_root).resolve())

        # Check if we have a server for this repo
        if repo_root in self._servers:
            server_info = self._servers[repo_root]
            pid = server_info.get("pid")
            port = server_info.get("port")

            # Check if server is still running
            if pid and self._is_server_running(pid):
                url = f"http://localhost:{port}"
                logger.debug(f"Using existing OpenCode server: {url} (PID {pid})")
                return url
            else:
                logger.info(f"Server for {repo_root} is not running, starting new one")
                del self._servers[repo_root]

        # Start new server
        return self._start_server(repo_root)

    def _start_server(self, repo_root: str) -> str:
        """Start OpenCode server in the specified directory.

        Args:
            repo_root: Absolute path to repository root.

        Returns:
            Server URL.

        Raises:
            RuntimeError: If server fails to start.
        """
        port = self._find_available_port()
        log_file = self.cache_dir / f"opencode_server_{port}.log"

        # Start server process in the repo directory
        cmd = ["opencode", "serve", "--port", str(port)]

        try:
            with open(log_file, "w") as f:
                process = subprocess.Popen(
                    cmd,
                    cwd=repo_root,
                    stdout=f,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,  # Detach from parent
                )
        except Exception as e:
            logger.error(f"Failed to start OpenCode server: {e}")
            raise RuntimeError(f"Failed to start OpenCode server: {e}") from e

        # Wait for server to start
        url = f"http://localhost:{port}"
        max_retries = 10
        for i in range(max_retries):
            time.sleep(0.5)
            if not self._is_port_available(port):
                # Server is listening
                break
        else:
            logger.error(f"Server failed to start on port {port}")
            process.kill()
            raise RuntimeError(f"Failed to start OpenCode server on port {port}")

        # Save server info
        self._servers[repo_root] = {
            "pid": process.pid,
            "port": port,
            "url": url,
            "log_file": str(log_file),
            "started_at": time.time(),
        }
        self._save_servers()

        logger.info(f"Started OpenCode server: {url} (PID {process.pid}) in {repo_root}")
        return url

    def stop_server(self, repo_root: str) -> bool:
        """Stop server for a specific repository.

        Args:
            repo_root: Absolute path to repository root.

        Returns:
            True if server was stopped, False if no server found.
        """
        repo_root = str(Path(repo_root).resolve())

        if repo_root not in self._servers:
            return False

        server_info = self._servers[repo_root]
        pid = server_info.get("pid")

        if pid and psutil is not None:
            try:
                process = psutil.Process(pid)
                process.terminate()
                process.wait(timeout=5)
                logger.info(f"Stopped OpenCode server (PID {pid}) for {repo_root}")
            except (psutil.NoSuchProcess, psutil.TimeoutExpired):
                logger.warning(f"Failed to stop server (PID {pid})")

        del self._servers[repo_root]
        self._save_servers()
        return True

    def stop_all_servers(self) -> None:
        """Stop all managed servers."""
        for repo_root in list(self._servers.keys()):
            self.stop_server(repo_root)

    def list_servers(self) -> dict[str, dict[str, Any]]:
        """List all managed servers.

        Automatically cleans up dead servers from the registry.

        Returns:
            Dict mapping repo_root to server info.
        """
        # Clean up dead servers
        for repo_root, info in list(self._servers.items()):
            pid = info.get("pid")
            if pid and not self._is_server_running(pid):
                del self._servers[repo_root]

        self._save_servers()
        return self._servers.copy()


# Global daemon instance
_daemon: OpenCodeDaemon | None = None


def get_daemon() -> OpenCodeDaemon:
    """Get or create the global daemon instance.

    Returns:
        Global OpenCodeDaemon instance.
    """
    global _daemon
    if _daemon is None:
        _daemon = OpenCodeDaemon()
    return _daemon
