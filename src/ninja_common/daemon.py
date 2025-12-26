"""Daemon management for Ninja MCP modules."""

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)


async def stdio_to_http_proxy(url: str) -> None:
    """Forward stdio to HTTP/SSE daemon.

    This acts as a proxy that bridges stdio (used by MCP clients like Claude Code)
    to HTTP/SSE (used by persistent daemons).

    Args:
        url: HTTP/SSE endpoint URL (e.g., http://127.0.0.1:8100/sse)
    """
    import sys  # noqa: PLC0415

    import aiohttp  # noqa: PLC0415

    # Extract base URL
    base_url = url.rsplit("/sse", 1)[0]
    messages_url = None

    async with aiohttp.ClientSession() as session:  # noqa: SIM117
        # Connect to SSE stream for server messages
        async with session.get(url) as sse_response:
            # Task to read from SSE and write to stdout
            async def forward_from_daemon():
                nonlocal messages_url
                buffer = b""

                async for chunk in sse_response.content.iter_any():
                    buffer += chunk

                    # Process complete lines
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        line_str = line.decode("utf-8").strip()

                        if not line_str:
                            continue

                        # Extract session endpoint from SSE
                        if line_str.startswith("data: ") and messages_url is None:
                            endpoint = line_str[6:].strip()
                            if endpoint.startswith("/messages"):
                                messages_url = f"{base_url}{endpoint}"
                                logger.debug(f"Session endpoint: {messages_url}")
                                continue

                        # Forward data messages to stdout (skip pings and endpoint events)
                        if line_str.startswith("data: "):
                            data = line_str[6:].strip()
                            if data and data != "[DONE]" and not data.startswith(": ping"):
                                sys.stdout.write(data + "\n")
                                sys.stdout.flush()

            # Task to read from stdin and POST to daemon
            async def forward_to_daemon():
                loop = asyncio.get_event_loop()

                # Wait for session endpoint to be set
                while messages_url is None:
                    await asyncio.sleep(0.1)

                while True:
                    try:
                        # Read line from stdin (non-blocking)
                        line = await loop.run_in_executor(None, sys.stdin.readline)
                        if not line:
                            break

                        # POST message to daemon (fire-and-forget, response comes via SSE)
                        async with session.post(
                            messages_url,
                            json=json.loads(line),
                            headers={"Content-Type": "application/json"},
                        ) as resp:
                            # Accept 200 or 202 (Accepted)
                            if resp.status not in (200, 202):
                                logger.error(f"HTTP error: {resp.status}")
                            # Don't wait for body - response comes through SSE

                    except Exception as e:
                        logger.error(f"Error forwarding to daemon: {e}")
                        break

            # Run both directions concurrently
            await asyncio.gather(
                forward_from_daemon(),
                forward_to_daemon(),
            )


class DaemonManager:
    """Manages daemon processes for Ninja MCP modules."""

    def __init__(self, cache_dir: Path | None = None):
        """Initialize daemon manager.

        Args:
            cache_dir: Cache directory for daemon files (default: ~/.cache/ninja-mcp)
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cache" / "ninja-mcp"
        self.cache_dir = cache_dir
        self.daemon_dir = cache_dir / "daemons"
        self.log_dir = cache_dir / "logs"

        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _get_pid_file(self, module: str) -> Path:
        """Get PID file path for module."""
        return self.daemon_dir / f"{module}.pid"

    def _get_sock_file(self, module: str) -> Path:
        """Get socket file path for module (deprecated, kept for compatibility)."""
        return self.daemon_dir / f"{module}.sock"

    def _get_port(self, module: str) -> int:
        """Get HTTP port for module."""
        ports = {
            "coder": 8100,
            "researcher": 8101,
            "secretary": 8102,
        }
        return ports.get(module, 8100)

    def _get_log_file(self, module: str) -> Path:
        """Get log file path for module."""
        return self.log_dir / f"{module}.log"

    def _read_pid(self, module: str) -> int | None:
        """Read PID from file."""
        pid_file = self._get_pid_file(module)
        if not pid_file.exists():
            return None
        try:
            return int(pid_file.read_text().strip())
        except (ValueError, OSError):
            return None

    def _write_pid(self, module: str, pid: int) -> None:
        """Write PID to file."""
        pid_file = self._get_pid_file(module)
        pid_file.write_text(str(pid))

    def _is_running(self, pid: int) -> bool:
        """Check if process is running."""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def start(self, module: str) -> bool:
        """Start daemon for module.

        Args:
            module: Module name (coder, researcher, secretary)

        Returns:
            True if started successfully
        """
        # Check if already running
        pid = self._read_pid(module)
        if pid and self._is_running(pid):
            logger.info(f"{module} daemon already running (PID {pid})")
            return True

        # Start daemon process
        log_file = self._get_log_file(module)
        port = self._get_port(module)

        # Start server process with HTTP mode
        cmd = [
            sys.executable,
            "-m",
            f"ninja_{module}.server",
            "--http",
            "--port",
            str(port),
        ]

        try:
            # Fork process
            pid = os.fork()
            if pid == 0:
                # Child process
                # Redirect stdout/stderr to log file
                log_fd = os.open(str(log_file), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
                os.dup2(log_fd, sys.stdout.fileno())
                os.dup2(log_fd, sys.stderr.fileno())
                os.close(log_fd)

                # Execute server
                os.execvp(cmd[0], cmd)
            else:
                # Parent process
                self._write_pid(module, pid)
                logger.info(f"Started {module} daemon (PID {pid}) on port {port}")
                return True
        except OSError as e:
            logger.error(f"Failed to start {module} daemon: {e}")
            return False

    def stop(self, module: str) -> bool:
        """Stop daemon for module.

        Args:
            module: Module name

        Returns:
            True if stopped successfully
        """
        pid = self._read_pid(module)
        if not pid:
            logger.info(f"{module} daemon not running")
            return True

        if not self._is_running(pid):
            logger.info(f"{module} daemon not running (stale PID file)")
            self._get_pid_file(module).unlink(missing_ok=True)
            return True

        # Send SIGTERM
        try:
            import time  # noqa: PLC0415
            os.kill(pid, signal.SIGTERM)
            # Wait for process to exit
            for _ in range(50):  # 5 seconds
                if not self._is_running(pid):
                    break
                time.sleep(0.1)
            else:
                # Force kill
                os.kill(pid, signal.SIGKILL)

            self._get_pid_file(module).unlink(missing_ok=True)
            self._get_sock_file(module).unlink(missing_ok=True)
            logger.info(f"Stopped {module} daemon")
            return True
        except OSError as e:
            logger.error(f"Failed to stop {module} daemon: {e}")
            return False

    def status(self, module: str) -> dict[str, Any]:
        """Get daemon status for module.

        Args:
            module: Module name

        Returns:
            Status dictionary
        """
        pid = self._read_pid(module)
        port = self._get_port(module)

        if not pid:
            return {
                "running": False,
                "pid": None,
                "port": port,
                "url": f"http://127.0.0.1:{port}/sse",
                "log": str(self._get_log_file(module)),
            }

        running = self._is_running(pid)
        return {
            "running": running,
            "pid": pid if running else None,
            "port": port,
            "url": f"http://127.0.0.1:{port}/sse" if running else None,
            "log": str(self._get_log_file(module)),
        }

    def restart(self, module: str) -> bool:
        """Restart daemon for module.

        Args:
            module: Module name

        Returns:
            True if restarted successfully
        """
        self.stop(module)
        return self.start(module)

    def list_modules(self) -> list[str]:
        """List all available modules.

        Returns:
            List of module names
        """
        return ["coder", "researcher", "secretary"]

    def status_all(self) -> dict[str, dict[str, Any]]:
        """Get status for all modules.

        Returns:
            Dictionary mapping module names to status
        """
        return {module: self.status(module) for module in self.list_modules()}


def main() -> int:  # noqa: PLR0911
    """CLI entry point for daemon management."""
    parser = argparse.ArgumentParser(description="Ninja MCP Daemon Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start daemon")
    start_parser.add_argument("module", choices=["coder", "researcher", "secretary"])

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop daemon")
    stop_parser.add_argument("module", choices=["coder", "researcher", "secretary"])

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart daemon")
    restart_parser.add_argument("module", choices=["coder", "researcher", "secretary"])

    # Status command
    status_parser = subparsers.add_parser("status", help="Get daemon status")
    status_parser.add_argument(
        "module",
        nargs="?",
        choices=["coder", "researcher", "secretary"],
        help="Module name (omit for all)",
    )

    # Connect command (for MCP clients)
    connect_parser = subparsers.add_parser("connect", help="Connect to daemon socket")
    connect_parser.add_argument("module", choices=["coder", "researcher", "secretary"])

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    manager = DaemonManager()

    if args.command == "start":
        success = manager.start(args.module)
        return 0 if success else 1

    elif args.command == "stop":
        success = manager.stop(args.module)
        return 0 if success else 1

    elif args.command == "restart":
        success = manager.restart(args.module)
        return 0 if success else 1

    elif args.command == "status":
        if args.module:
            status = manager.status(args.module)
            print(json.dumps(status, indent=2))
        else:
            status_all = manager.status_all()
            print(json.dumps(status_all, indent=2))
        return 0

    elif args.command == "connect":
        # For MCP clients - forward stdio to HTTP/SSE daemon
        status = manager.status(args.module)
        if not status["running"]:
            print(f"Error: {args.module} daemon not running", file=sys.stderr)
            return 1

        # Forward stdio to HTTP/SSE endpoint
        port = manager._get_port(args.module)
        url = f"http://127.0.0.1:{port}/sse"

        try:
            asyncio.run(stdio_to_http_proxy(url))
            return 0
        except Exception as e:
            print(f"Error connecting to daemon: {e}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
