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

    CRITICAL: This proxy is a BRIDGE, not the daemon itself. Multiple proxies can
    connect to the same singleton daemon. The proxy should be resilient and not
    close the daemon connection when stdin closes.

    Args:
        url: HTTP/SSE endpoint URL (e.g., http://127.0.0.1:8100/sse)
    """
    import sys

    import aiohttp

    # Extract base URL
    base_url = url.rsplit("/sse", 1)[0]
    messages_url = None
    stdin_closed = False

    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=None, sock_read=None)
    ) as session:
        # Connect to SSE stream for server messages
        async with session.get(url) as sse_response:
            # Task to read from SSE and write to stdout
            async def forward_from_daemon():
                nonlocal messages_url
                buffer = b""

                try:
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
                                    try:
                                        sys.stdout.write(data + "\n")
                                        sys.stdout.flush()
                                    except (BrokenPipeError, OSError):
                                        # stdout closed, but keep listening for daemon
                                        logger.debug(
                                            "stdout closed, but keeping SSE connection alive"
                                        )
                except Exception as e:
                    logger.error(f"SSE connection error: {e}")
                    raise

            # Task to read from stdin and POST to daemon
            async def forward_to_daemon():
                nonlocal stdin_closed
                loop = asyncio.get_event_loop()

                # Wait for session endpoint to be set
                max_wait = 100  # 10 seconds
                wait_count = 0
                while messages_url is None and wait_count < max_wait:
                    await asyncio.sleep(0.1)
                    wait_count += 1

                if messages_url is None:
                    logger.error("Timeout waiting for session endpoint")
                    return

                while True:
                    try:
                        # Read line from stdin (non-blocking)
                        line = await loop.run_in_executor(None, sys.stdin.readline)
                        if not line:
                            # stdin closed - this is NORMAL when client disconnects
                            logger.debug("stdin closed, proxy finishing input forwarding")
                            stdin_closed = True
                            # Don't break the SSE connection - let it continue receiving
                            return

                        # POST message to daemon (fire-and-forget, response comes via SSE)
                        async with session.post(
                            messages_url,
                            json=json.loads(line),
                            headers={"Content-Type": "application/json"},
                        ) as resp:
                            # Accept 200 or 202 (Accepted)
                            if resp.status not in (200, 202):
                                logger.error(f"HTTP error: {resp.status}")
                                text = await resp.text()
                                logger.error(f"Error response: {text}")
                            # Don't wait for body - response comes through SSE

                    except json.JSONDecodeError as e:
                        logger.error(f"Invalid JSON from stdin: {e}")
                        continue
                    except (BrokenPipeError, ConnectionError, OSError) as e:
                        logger.debug(f"Connection error (expected when client disconnects): {e}")
                        stdin_closed = True
                        return
                    except Exception as e:
                        logger.error(f"Error forwarding to daemon: {e}")
                        stdin_closed = True
                        return

            # Run both directions concurrently
            # Use return_exceptions to prevent one task failure from killing the other
            tasks = [
                asyncio.create_task(forward_from_daemon()),
                asyncio.create_task(forward_to_daemon()),
            ]

            # Wait for both tasks, but don't let stdin closure kill SSE
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

            # If stdin task finished but SSE is still running, let SSE finish gracefully
            if stdin_closed and pending:
                logger.debug("stdin closed, waiting for SSE to finish gracefully")
                # Give SSE a moment to finish any pending messages
                await asyncio.sleep(0.5)

            # Cancel remaining tasks
            for task in pending:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass


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

    def _is_port_in_use(self, port: int) -> bool:
        """Check if port is already in use."""
        import socket

        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                result = s.connect_ex(("127.0.0.1", port))
                return result == 0
        except Exception:
            return False

    def _find_process_using_port(self, port: int) -> int | None:
        """Find PID of process using the given port."""
        import subprocess

        try:
            # Try lsof first
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                return int(result.stdout.strip().split()[0])
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        try:
            # Fallback to ss
            result = subprocess.run(
                ["ss", "-tlnp", f"sport = :{port}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0:
                import re

                match = re.search(r"pid=(\d+)", result.stdout)
                if match:
                    return int(match.group(1))
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        return None

    def _cleanup_zombies(self, module: str) -> None:
        """Clean up zombie processes for a module."""
        port = self._get_port(module)

        # Check if port is in use
        if not self._is_port_in_use(port):
            return

        # Find and kill process using the port
        pid = self._find_process_using_port(port)
        if pid:
            logger.info(f"Found process {pid} using port {port}, attempting cleanup")
            try:
                os.kill(pid, signal.SIGTERM)
                import time

                time.sleep(0.5)
                if self._is_running(pid):
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(0.2)
            except OSError as e:
                logger.warning(f"Could not kill process {pid}: {e}")

    def start(self, module: str) -> bool:
        """Start daemon for module.

        SINGLETON ENFORCEMENT: Ensures only one daemon per module is running.
        If a daemon is already running (by PID or port check), returns success.
        Cleans up zombie processes before starting.

        Args:
            module: Module name (coder, researcher, secretary)

        Returns:
            True if started successfully
        """
        port = self._get_port(module)

        # Check if already running by PID
        pid = self._read_pid(module)
        if pid and self._is_running(pid):
            # Verify it's actually listening on the port
            if self._is_port_in_use(port):
                logger.info(f"{module} daemon already running (PID {pid}) on port {port}")
                return True
            else:
                logger.warning(f"{module} daemon PID {pid} exists but not listening, cleaning up")
                self._get_pid_file(module).unlink(missing_ok=True)

        # Check if port is in use by another process (zombie)
        if self._is_port_in_use(port):
            port_pid = self._find_process_using_port(port)
            if port_pid and port_pid != pid:
                logger.warning(
                    f"Port {port} in use by PID {port_pid} (not our daemon), cleaning up"
                )
                self._cleanup_zombies(module)
                # Wait a moment for cleanup
                import time

                time.sleep(1)

                # Verify port is now free
                if self._is_port_in_use(port):
                    logger.error(f"Port {port} still in use after cleanup, cannot start {module}")
                    return False
            elif port_pid == pid:
                logger.info(f"{module} daemon already running (PID {pid}) on port {port}")
                return True

        # Clean up stale PID file
        if pid:
            self._get_pid_file(module).unlink(missing_ok=True)

        # Start daemon process
        log_file = self._get_log_file(module)

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
            new_pid = os.fork()
            if new_pid == 0:
                # Child process
                # Detach from parent session
                os.setsid()

                # Redirect stdout/stderr to log file
                log_fd = os.open(str(log_file), os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                os.dup2(log_fd, sys.stdout.fileno())
                os.dup2(log_fd, sys.stderr.fileno())
                os.close(log_fd)

                # Close stdin
                null_fd = os.open(os.devnull, os.O_RDONLY)
                os.dup2(null_fd, sys.stdin.fileno())
                os.close(null_fd)

                # Execute server
                os.execvp(cmd[0], cmd)
            else:
                # Parent process
                self._write_pid(module, new_pid)

                # Wait a moment and verify it started
                import time

                time.sleep(1)

                if self._is_running(new_pid) and self._is_port_in_use(port):
                    logger.info(f"Started {module} daemon (PID {new_pid}) on port {port}")
                    return True
                else:
                    logger.error(f"{module} daemon failed to start properly")
                    self._get_pid_file(module).unlink(missing_ok=True)
                    return False
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
            import time

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
    start_parser = subparsers.add_parser("start", help="Start daemon(s)")
    start_parser.add_argument(
        "module",
        nargs="?",
        choices=["coder", "researcher", "secretary"],
        help="Module name (omit to start all)",
    )

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop daemon(s)")
    stop_parser.add_argument(
        "module",
        nargs="?",
        choices=["coder", "researcher", "secretary"],
        help="Module name (omit to stop all)",
    )

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart daemon(s)")
    restart_parser.add_argument(
        "module",
        nargs="?",
        choices=["coder", "researcher", "secretary"],
        help="Module name (omit to restart all)",
    )

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
        if args.module:
            # Start single module
            success = manager.start(args.module)
            return 0 if success else 1
        else:
            # Start all modules
            print("Starting all daemons...")
            all_success = True
            for module in manager.list_modules():
                print(f"  Starting {module}...", end=" ", flush=True)
                if manager.start(module):
                    print("✓")
                else:
                    print("✗")
                    all_success = False
            return 0 if all_success else 1

    elif args.command == "stop":
        if args.module:
            # Stop single module
            success = manager.stop(args.module)
            return 0 if success else 1
        else:
            # Stop all modules
            print("Stopping all daemons...")
            all_success = True
            for module in manager.list_modules():
                print(f"  Stopping {module}...", end=" ", flush=True)
                if manager.stop(module):
                    print("✓")
                else:
                    print("✗")
                    all_success = False
            return 0 if all_success else 1

    elif args.command == "restart":
        if args.module:
            # Restart single module
            success = manager.restart(args.module)
            return 0 if success else 1
        else:
            # Restart all modules
            print("Restarting all daemons...")
            all_success = True
            for module in manager.list_modules():
                print(f"  Restarting {module}...", end=" ", flush=True)
                if manager.restart(module):
                    print("✓")
                else:
                    print("✗")
                    all_success = False
            return 0 if all_success else 1

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
