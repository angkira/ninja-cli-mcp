"""Daemon management for Ninja MCP modules."""

import argparse
import asyncio
import json
import os
import signal
import sys
from pathlib import Path
from typing import Any

from ninja_common.defaults import AVAILABLE_MODULES, DEFAULT_ENABLED_MODULES, DEFAULT_PORTS
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
                        line = await asyncio.to_thread(sys.stdin.readline)
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
            _done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

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
        """Get HTTP port for module from config or use default."""
        # Try to read from config file
        config_file = Path.home() / ".ninja-mcp.env"
        env_key = f"NINJA_{module.upper()}_PORT"

        # Check environment variable first
        if env_key in os.environ:
            try:
                return int(os.environ[env_key])
            except ValueError:
                pass

        # Check config file
        if config_file.exists():
            try:
                content = config_file.read_text()
                for line in content.splitlines():
                    if line.startswith(f"{env_key}="):
                        return int(line.split("=", 1)[1].strip().strip("'\""))
            except (ValueError, OSError):
                pass

        return DEFAULT_PORTS.get(module, 8100)

    def _get_enabled_modules(self) -> list[str]:
        """Get enabled modules from config or environment.

        Resolution order:
        1. NINJA_ENABLED_MODULES environment variable
        2. NINJA_ENABLED_MODULES in config file (~/.ninja-mcp.env)
        3. DEFAULT_ENABLED_MODULES

        Returns:
            List of enabled module names.
        """
        config_file = Path.home() / ".ninja-mcp.env"

        if "NINJA_ENABLED_MODULES" in os.environ:
            modules = [m.strip() for m in os.environ["NINJA_ENABLED_MODULES"].split(",")]
            if modules:
                return modules

        if config_file.exists():
            try:
                content = config_file.read_text()
                for line in content.splitlines():
                    if line.startswith("NINJA_ENABLED_MODULES="):
                        value = line.split("=", 1)[1].strip().strip("'\"")
                        modules = [m.strip() for m in value.split(",")]
                        if modules:
                            return modules
            except OSError:
                pass

        return list(DEFAULT_ENABLED_MODULES)

    def _find_free_port(self, start_port: int = 8100, max_attempts: int = 100) -> int:
        """Find a free port starting from start_port."""
        import socket

        for port in range(start_port, start_port + max_attempts):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind(("127.0.0.1", port))
                    return port
            except OSError:
                continue

        raise RuntimeError(
            f"Could not find free port in range {start_port}-{start_port + max_attempts}"
        )

    def _save_port_to_config(self, module: str, port: int) -> None:
        """Save port to config file."""
        config_file = Path.home() / ".ninja-mcp.env"
        env_key = f"NINJA_{module.upper()}_PORT"

        # Read existing config
        lines = []
        if config_file.exists():
            lines = config_file.read_text().splitlines()

        # Update or add the port
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{env_key}="):
                lines[i] = f"{env_key}={port}"
                found = True
                break

        if not found:
            lines.append(f"{env_key}={port}")

        config_file.write_text("\n".join(lines) + "\n")

    def _save_enabled_modules(self, modules: list[str]) -> None:
        """Save enabled modules to config file."""
        config_file = Path.home() / ".ninja-mcp.env"
        env_key = "NINJA_ENABLED_MODULES"
        value = ",".join(modules)

        lines = []
        if config_file.exists():
            lines = config_file.read_text().splitlines()

        found = False
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith(f"{env_key}="):
                lines[i] = f"{env_key}={value}"
                found = True
                break
            if stripped.startswith(f"export {env_key}="):
                lines[i] = f"export {env_key}='{value}'"
                found = True
                break

        if not found:
            lines.append(f"{env_key}={value}")

        config_file.write_text("\n".join(lines) + "\n")

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

        # Check if port is in use by another process
        if self._is_port_in_use(port):
            port_pid = self._find_process_using_port(port)
            if port_pid and port_pid != pid:
                # Port is used by something else - find a free port instead
                logger.warning(f"Port {port} in use by another process (PID {port_pid})")
                try:
                    port = self._find_free_port(start_port=port + 1)
                    self._save_port_to_config(module, port)
                    logger.info(f"Found free port {port} for {module}, saved to config")
                except RuntimeError as e:
                    logger.error(f"Could not find free port for {module}: {e}")
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

                # Wait for daemon to start (retry up to 5 seconds)
                import time

                for attempt in range(10):
                    time.sleep(0.5)
                    if self._is_running(new_pid) and self._is_port_in_use(port):
                        logger.info(f"Started {module} daemon (PID {new_pid}) on port {port}")
                        return True

                # Final check - process might be running but port binding is slow
                if self._is_running(new_pid):
                    logger.warning(
                        f"{module} daemon running (PID {new_pid}) but port {port} not ready yet, assuming success"
                    )
                    return True

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

        # Get version
        version = self._get_module_version(module)

        if not pid:
            return {
                "running": False,
                "pid": None,
                "port": port,
                "url": f"http://127.0.0.1:{port}/sse",
                "log": str(self._get_log_file(module)),
                "version": version,
            }

        running = self._is_running(pid)
        return {
            "running": running,
            "pid": pid if running else None,
            "port": port,
            "url": f"http://127.0.0.1:{port}/sse" if running else None,
            "log": str(self._get_log_file(module)),
            "version": version,
        }

    def _get_module_version(self, module: str) -> str:
        """Get version of a module.

        Args:
            module: Module name

        Returns:
            Version string or "unknown"
        """
        module_map = {
            "coder": "ninja_coder",
            "researcher": "ninja_researcher",
            "secretary": "ninja_secretary",
            "agent": "ninja_agent",
        }

        module_name = module_map.get(module)
        if not module_name:
            return "unknown"

        try:
            mod = __import__(module_name)
            return getattr(mod, "__version__", "unknown")
        except (ImportError, AttributeError):
            return "not installed"

    def restart(self, module: str) -> bool:
        """Restart daemon for module.

        Args:
            module: Module name

        Returns:
            True if restarted successfully
        """
        self.stop(module)
        return self.start(module)

    def upgrade(self, version: str | None = None) -> bool:
        """Upgrade ninja-mcp from GitLab PyPI registry."""
        import subprocess as sp

        registry_url = os.environ.get(
            "NINJA_REGISTRY_URL",
            "https://git.mcp-test.dev/api/v4/projects/hars%2Fninja-cli-mcp/packages/pypi/simple",
        )
        token = os.environ.get("NINJA_REGISTRY_TOKEN", "")

        if token:
            registry_url = registry_url.replace("https://", f"https://__token__:{token}@")

        pkg_spec = f"ninja-mcp=={version}" if version else "ninja-mcp"

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "--break-system-packages",
            "--upgrade",
            "--extra-index-url",
            registry_url,
            pkg_spec,
        ]

        logger.info(f"Installing {pkg_spec}...")
        result = sp.run(cmd, check=False, capture_output=True, text=True, timeout=120)

        if result.returncode != 0:
            logger.error(f"Upgrade failed: {result.stderr}")
            return False

        logger.info("Package upgraded, restarting running daemons...")
        for name in self.list_modules():
            status = self.status(name)
            if status.get("running"):
                logger.info(f"Restarting {name}...")
                self.restart(name)

        return True

    def list_modules(self) -> list[str]:
        """List enabled modules.

        Returns:
            List of enabled module names (from NINJA_ENABLED_MODULES config).
        """
        return self._get_enabled_modules()

    def status_all(self) -> dict[str, dict[str, Any]]:
        """Get status for all modules.

        Returns:
            Dictionary mapping module names to status
        """
        return {module: self.status(module) for module in self.list_modules()}


def main() -> int:
    """CLI entry point for daemon management."""
    parser = argparse.ArgumentParser(description="Ninja MCP Daemon Manager")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Start command
    start_parser = subparsers.add_parser("start", help="Start daemon(s)")
    start_parser.add_argument(
        "module",
        nargs="?",
        help="Module name (omit to start all enabled). See 'module list'.",
    )

    # Stop command
    stop_parser = subparsers.add_parser("stop", help="Stop daemon(s)")
    stop_parser.add_argument(
        "module",
        nargs="?",
        help="Module name (omit to stop all enabled). See 'module list'.",
    )

    # Restart command
    restart_parser = subparsers.add_parser("restart", help="Restart daemon(s)")
    restart_parser.add_argument(
        "module",
        nargs="?",
        help="Module name (omit to restart all enabled). See 'module list'.",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Get daemon status")
    status_parser.add_argument(
        "module",
        nargs="?",
        help="Module name (omit for all enabled). See 'module list'.",
    )

    # Module management subcommand
    module_parser = subparsers.add_parser("module", help="Manage enabled modules")
    module_sub = module_parser.add_subparsers(dest="module_action", help="Module action")

    module_list_parser = module_sub.add_parser("list", help="List enabled modules and their status")
    module_list_parser.set_defaults(module_action="list")

    module_enable_parser = module_sub.add_parser("enable", help="Enable and start a module")
    module_enable_parser.add_argument("name", help="Module name to enable")
    module_enable_parser.set_defaults(module_action="enable")

    module_disable_parser = module_sub.add_parser("disable", help="Disable and stop a module")
    module_disable_parser.add_argument("name", help="Module name to disable")
    module_disable_parser.set_defaults(module_action="disable")

    # Upgrade command
    upgrade_parser = subparsers.add_parser("upgrade", help="Upgrade ninja-mcp package")
    upgrade_parser.add_argument("--version", "-v", help="Specific version (for rollback)")

    # Version command
    subparsers.add_parser("version", help="Show installed version")

    # Connect command (for MCP clients)
    connect_parser = subparsers.add_parser("connect", help="Connect to daemon socket")
    connect_parser.add_argument("module", help="Module name to connect to")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    manager = DaemonManager()

    # ── module subcommand ───────────────────────────────────────────────────
    if args.command == "module":
        if not hasattr(args, "module_action") or not args.module_action:
            module_parser.print_help()
            return 1

        if args.module_action == "list":
            enabled = manager.list_modules()
            print(f"Enabled modules ({len(enabled)}):")
            print()
            for module in AVAILABLE_MODULES:
                running = manager.status(module).get("running", False)
                enabled_mark = "✓" if module in enabled else " "
                status_str = "running" if running else "stopped"
                color = "\033[32m" if running else "\033[90m"
                reset = "\033[0m"
                print(f"  [{enabled_mark}] {module:15s} {color}{status_str}{reset}")
            print()
            print("Use 'module enable <name>' or 'module disable <name>' to change.")
            return 0

        elif args.module_action == "enable":
            name = args.name
            if name not in AVAILABLE_MODULES:
                print(f"Error: unknown module '{name}'. Available: {', '.join(AVAILABLE_MODULES)}")
                return 1
            enabled = manager.list_modules()
            if name in enabled:
                print(f"Module '{name}' is already enabled.")
                return 0
            enabled.append(name)
            manager._save_enabled_modules(enabled)
            print(f"✓ Enabled module '{name}'")
            print(f"  Starting {name} daemon...")
            manager.start(name)
            return 0

        elif args.module_action == "disable":
            name = args.name
            if name not in AVAILABLE_MODULES:
                print(f"Error: unknown module '{name}'. Available: {', '.join(AVAILABLE_MODULES)}")
                return 1
            enabled = manager.list_modules()
            if name not in enabled:
                print(f"Module '{name}' is not enabled.")
                return 0
            enabled.remove(name)
            manager._save_enabled_modules(enabled)
            print(f"✓ Disabled module '{name}'")
            print(f"  Stopping {name} daemon...")
            manager.stop(name)
            return 0

        return 1

    # ── module validation helper ────────────────────────────────────────────
    def _validate_module(mod: str) -> bool:
        """Check if module name is valid (enabled or an available module)."""
        enabled = manager.list_modules()
        if mod not in AVAILABLE_MODULES:
            print(
                f"Error: unknown module '{mod}'. Available: {', '.join(AVAILABLE_MODULES)}",
                file=sys.stderr,
            )
            return False
        if mod not in enabled:
            print(
                f"Warning: module '{mod}' is not enabled (NINJA_ENABLED_MODULES). "
                f"Use 'module enable {mod}' first.",
                file=sys.stderr,
            )
        return True

    if args.command == "start":
        if args.module:
            if not _validate_module(args.module):
                return 1
            success = manager.start(args.module)
            return 0 if success else 1
        else:
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
            if not _validate_module(args.module):
                return 1
            success = manager.stop(args.module)
            return 0 if success else 1
        else:
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
            if not _validate_module(args.module):
                return 1
            success = manager.restart(args.module)
            return 0 if success else 1
        else:
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
            if not _validate_module(args.module):
                return 1
            status = manager.status(args.module)
            print(json.dumps(status, indent=2))
        else:
            status_all = manager.status_all()
            print(json.dumps(status_all, indent=2))
        return 0

    elif args.command == "upgrade":
        print("Upgrading ninja-mcp...")
        if manager.upgrade(version=getattr(args, "version", None)):
            print("✅ Upgrade complete!")
        else:
            print("❌ Upgrade failed.", file=sys.stderr)
            sys.exit(1)

    elif args.command == "version":
        from importlib.metadata import version as get_version

        try:
            v = get_version("ninja-mcp")
            print(f"ninja-mcp {v}")
        except Exception:
            print("ninja-mcp (version unknown)")

    elif args.command == "connect":
        if not _validate_module(args.module):
            return 1
        status = manager.status(args.module)
        if not status["running"]:
            print(f"Error: {args.module} daemon not running", file=sys.stderr)
            return 1

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
