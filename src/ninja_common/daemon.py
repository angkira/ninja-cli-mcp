"""Daemon management for Ninja MCP modules."""

import argparse
import asyncio
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from ninja_common.defaults import AVAILABLE_MODULES, DEFAULT_ENABLED_MODULES, DEFAULT_PORTS
from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)

#: Template for the per-module systemd *user* unit. The only unit this module
#: is ever allowed to act on.
SYSTEMD_UNIT_TEMPLATE = "ninja-mcp@{module}.service"

#: How long `systemctl restart` may take to produce a new MainPID.
SYSTEMD_RESTART_TIMEOUT_S = 30.0

#: How long `systemctl stop` may take to deactivate the unit.
SYSTEMD_STOP_TIMEOUT_S = 10.0

#: How long the module's port may take to answer after a restart/start.
PORT_READY_TIMEOUT_S = 10.0

#: Poll interval used by every bounded wait above.
SYSTEMD_POLL_INTERVAL_S = 0.25

#: Per-invocation subprocess timeout for `systemctl`.
SYSTEMCTL_TIMEOUT_S = 10.0


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

        # Encrypted-store password: prompted at most once per launch and handed
        # to each forked daemon through an inherited fd (never via env/argv).
        self._store_password: str | None = None
        self._store_prompted = False

        # Bounded waits for systemd supervision (tests shrink these).
        self.systemd_restart_timeout = SYSTEMD_RESTART_TIMEOUT_S
        self.systemd_stop_timeout = SYSTEMD_STOP_TIMEOUT_S
        self.port_ready_timeout = PORT_READY_TIMEOUT_S
        self.poll_interval = SYSTEMD_POLL_INTERVAL_S

        self.daemon_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _unlock_store_once(self) -> str | None:
        """Resolve the encrypted-store password once for this launch.

        Order: already-known (this process) → env var → interactive prompt.
        Returns None when there is no store DB or no way to get the password
        (headless), in which case daemons fall back to env/file secrets.
        """
        if self._store_prompted:
            return self._store_password
        self._store_prompted = True

        try:
            from ninja_config import secrets_store
            from ninja_config.credentials import default_db_path
        except Exception:
            return None

        if not default_db_path().exists():
            return None

        # Passwordless store: try the empty password FIRST. A non-empty value
        # (typed, keyring, env) would be piped to the daemons and break
        # decryption, so never prompt or forward anything for such a store.
        try:
            if secrets_store.CredentialManager(password="").can_decrypt():
                self._store_password = ""
                return self._store_password
        except Exception:
            pass

        existing = secrets_store.get_store_password()
        if existing is not None:
            self._store_password = existing
            return self._store_password

        env_password = os.getenv("NINJA_CREDENTIAL_PASSWORD")
        if env_password:
            self._store_password = env_password
            return self._store_password

        if sys.stdin.isatty():
            try:
                self._store_password = secrets_store.prompt_store_password()
            except Exception:
                self._store_password = None
        return self._store_password

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

        # Present-but-empty is authoritative ("none enabled"); only an absent
        # value falls back to the defaults.
        if "NINJA_ENABLED_MODULES" in os.environ:
            return [m.strip() for m in os.environ["NINJA_ENABLED_MODULES"].split(",") if m.strip()]

        if config_file.exists():
            try:
                content = config_file.read_text()
                for line in content.splitlines():
                    if line.startswith("NINJA_ENABLED_MODULES="):
                        value = line.split("=", 1)[1].strip().strip("'\"")
                        return [m.strip() for m in value.split(",") if m.strip()]
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
            if stripped.startswith(f"export {env_key}="):
                lines[i] = f"export {env_key}='{value}'"
                found = True

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

    def _systemd_unit(self, module: str) -> str:
        """Return the module-scoped systemd user unit name."""
        return SYSTEMD_UNIT_TEMPLATE.format(module=module)

    def _run_systemctl(
        self, *args: str, timeout: float = SYSTEMCTL_TIMEOUT_S
    ) -> subprocess.CompletedProcess[str] | None:
        """Run ``systemctl --user <args>`` with captured output and a timeout.

        Always user scope; callers pass exactly one unit-scoped verb (e.g.
        ``("restart", "ninja-mcp@coder.service")``). This helper never adds
        ``--all``, never omits the unit, and never disables the shell.
        Returns ``None`` when systemctl is unavailable or times out.
        """
        argv = ["systemctl", "--user", *args]
        try:
            return subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError, ValueError) as e:
            logger.debug(f"Command failed ({' '.join(argv)}): {e}")
            return None

    def _is_systemd_active(self, module: str) -> bool:
        """Check if the systemd singleton unit for *module* is active.

        Best-effort: returns False when systemctl is missing, the user
        bus is unreachable, or the unit does not exist. Never raises.
        """
        result = self._run_systemctl("is-active", self._systemd_unit(module), timeout=2)
        return result is not None and result.returncode == 0 and result.stdout.strip() == "active"

    def _systemd_main_pid(self, module: str) -> int | None:
        """Return the MainPID reported by the module's user unit, if any."""
        result = self._run_systemctl("show", "-p", "MainPID", "--value", self._systemd_unit(module))
        if result is None or result.returncode != 0:
            return None
        raw = result.stdout.strip()
        if not raw.isdigit():
            return None
        pid = int(raw)
        return pid if pid > 0 else None

    def _systemd_owns(self, module: str) -> bool:
        """True when an active unit with a live MainPID supervises *module*."""
        if not self._is_systemd_active(module):
            return False
        pid = self._systemd_main_pid(module)
        return pid is not None and self._is_running(pid)

    def _systemd_active_enter_time(self, module: str) -> float | None:
        """Return the unit's ActiveEnterTimestamp as epoch seconds, if parseable."""
        result = self._run_systemctl(
            "show",
            "-p",
            "ActiveEnterTimestamp",
            "--value",
            "--timestamp=unix",
            self._systemd_unit(module),
        )
        if result is None or result.returncode != 0:
            return None
        return self._parse_systemd_timestamp(result.stdout)

    @staticmethod
    def _parse_systemd_timestamp(raw: str) -> float | None:
        """Parse ``--timestamp=unix`` output; reject empty/non-positive values."""
        value = raw.strip()
        if not value:
            return None
        try:
            timestamp = float(value)
        except ValueError:
            return None
        return timestamp if timestamp > 0 else None

    def _wait_for_new_main_pid(
        self,
        module: str,
        previous_pid: int | None,
        timeout: float,
        interval: float,
    ) -> int | None:
        """Poll MainPID until it changes from *previous_pid* (bounded)."""
        deadline = time.monotonic() + timeout
        while True:
            pid = self._systemd_main_pid(module)
            if pid is not None and pid != previous_pid:
                return pid
            if time.monotonic() >= deadline:
                return None
            time.sleep(interval)

    def _wait_for_port(self, module: str, timeout: float, interval: float) -> bool:
        """Poll the module's TCP port until it answers (bounded)."""
        port = self._get_port(module)
        deadline = time.monotonic() + timeout
        while True:
            if self._is_port_in_use(port):
                return True
            if time.monotonic() >= deadline:
                return False
            time.sleep(interval)

    def _find_ninja_owner_pid(self, module: str, port: int) -> int | None:
        """Return the PID serving *port* when it looks like our module server.

        ``lsof -ti`` lists every socket endpoint on the port — including
        connected *clients* (claude/opencode proxies) — so the first PID is
        often not the server. Scan all candidates and return the one whose
        command line contains ``ninja_<module>.server``.
        """
        for pid in self._find_pids_using_port(port):
            try:
                import psutil

                cmdline = " ".join(psutil.Process(pid).cmdline())
                if f"ninja_{module}.server" in cmdline:
                    return pid
            except Exception:
                continue
        return None

    def _find_pids_using_port(self, port: int) -> list[int]:
        """Return all PIDs with a socket on *port* (listeners and clients)."""
        import re
        import subprocess

        pids: list[int] = []
        try:
            result = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
            if result.returncode == 0 and result.stdout.strip():
                for part in result.stdout.strip().split():
                    try:
                        candidate = int(part.strip().strip(","))
                    except ValueError:
                        continue
                    if candidate not in pids:
                        pids.append(candidate)
        except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
            pass

        if not pids:
            try:
                result = subprocess.run(
                    ["ss", "-tlnp", f"sport = :{port}"],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                if result.returncode == 0:
                    for match in re.finditer(r"pid=(\d+)", result.stdout):
                        try:
                            candidate = int(match.group(1))
                        except ValueError:
                            continue
                        if candidate not in pids:
                            pids.append(candidate)
            except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
                pass
        return pids

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

        # Only ever signal our own server, never a connected client:
        # lsof/ss list clients too, so resolve the ninja owner explicitly.
        pid = self._find_ninja_owner_pid(module, port)
        if pid:
            logger.info(f"Found process {pid} using port {port}, attempting cleanup")
            try:
                os.kill(pid, signal.SIGTERM)
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
            owner_pid = self._find_ninja_owner_pid(module, port)
            if owner_pid is not None:
                # Our server (PID-file daemon or systemd singleton) already
                # serves this port — treat as running, never reallocate.
                logger.info(f"{module} daemon already serving port {port} (PID {owner_pid})")
                return True
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

        # Hand the encrypted-store password to the child through a pipe fd so it
        # never lands in the environment or argv. The server reads it once at
        # startup (see secrets_store._read_fd_password).
        child_env = os.environ.copy()
        # Never hand the store password to the daemon via env: it is passed
        # through the inherited fd below (NINJA_CREDENTIAL_FD).
        child_env.pop("NINJA_CREDENTIAL_PASSWORD", None)
        password_fd: int | None = None
        password = self._unlock_store_once()
        # An empty password means "passwordless store": daemons open it with the
        # empty-password fallback, so nothing is passed through the fd.
        if password:
            read_fd, write_fd = os.pipe()
            try:
                os.write(write_fd, password.encode("utf-8"))
            finally:
                os.close(write_fd)
            os.set_inheritable(read_fd, True)
            password_fd = read_fd
            child_env["NINJA_CREDENTIAL_FD"] = str(read_fd)

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

                # Execute server (child_env carries only the fd number)
                os.execvpe(cmd[0], cmd, child_env)
            else:
                if password_fd is not None:
                    try:
                        os.close(password_fd)
                    except OSError:
                        pass
                # Parent process
                self._write_pid(module, new_pid)

                # Wait for daemon to start (retry up to 5 seconds)
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

        Honours systemd ownership: when the module's user unit is active the
        stop is delegated to ``systemctl --user stop`` and verified. The legacy
        PID-file path is kept for daemons started by ``daemon start``.

        Args:
            module: Module name

        Returns:
            True only when the daemon is genuinely no longer running
        """
        # An explicit live PID file means a `daemon start` process owns the
        # module; systemd never writes PID files, so take the legacy path
        # without even probing systemctl.
        pid = self._read_pid(module)
        if pid and self._is_running(pid):
            return self._stop_pidfile(module, pid)

        # Otherwise an active unit owns the module (units have no PID file),
        # so never claim success without stopping it.
        if self._is_systemd_active(module):
            return self._stop_systemd(module)

        port = self._get_port(module)
        if self._is_port_in_use(port) and self._find_ninja_owner_pid(module, port) is not None:
            logger.error(
                f"{module} daemon is serving port {port} but is neither supervised by an "
                f"active {self._systemd_unit(module)} nor tracked by a PID file; "
                "refusing to report it stopped"
            )
            return False

        if pid:
            logger.info(f"{module} daemon not running (stale PID file)")
            self._get_pid_file(module).unlink(missing_ok=True)
        else:
            logger.info(f"{module} daemon not running")
        return True

    def _stop_pidfile(self, module: str, pid: int) -> bool:
        """Stop a PID-tracked daemon with SIGTERM, escalating to SIGKILL."""
        try:
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

    def _stop_systemd(self, module: str) -> bool:
        """Stop an active unit via systemctl and verify it went inactive."""
        unit = self._systemd_unit(module)
        old_pid = self._systemd_main_pid(module)

        result = self._run_systemctl("stop", unit)
        if result is None or result.returncode != 0:
            detail = result.stderr.strip() if result is not None else "systemctl unavailable"
            logger.error(f"systemctl --user stop {unit} failed for {module}: {detail}")
            return False

        deadline = time.monotonic() + self.systemd_stop_timeout
        while True:
            still_active = self._is_systemd_active(module)
            pid_alive = old_pid is not None and self._is_running(old_pid)
            if not still_active and not pid_alive:
                self._get_pid_file(module).unlink(missing_ok=True)
                logger.info(f"Stopped {module} daemon via systemd ({unit})")
                return True
            if time.monotonic() >= deadline:
                logger.error(
                    f"{module} is still active {self.systemd_stop_timeout:.0f}s after "
                    f"systemctl --user stop {unit}"
                )
                return False
            time.sleep(self.poll_interval)

    def status(self, module: str) -> dict[str, Any]:
        """Get daemon status for module.

        Detects both PID-file daemons (``daemon start``) and systemd
        singletons (``ninja-mcp@<module>.service``): when no live PID file
        exists but *port* is served by a matching ``ninja_<module>.server``
        process — in particular with an active systemd unit — the daemon
        counts as running so ``daemon connect`` works.

        Version reporting is deliberately honest: ``installed_version`` is
        the package on disk (all a CLI process can know), ``running_since``
        is the process/unit start time and ``stale_code`` compares the two.
        The daemon's in-memory version is never claimed.

        Args:
            module: Module name

        Returns:
            Status dictionary
        """
        pid = self._read_pid(module)
        port = self._get_port(module)

        if pid and self._is_running(pid):
            return self._running_status(module, pid, port, "pid")

        # No live PID file — fall back to port owner + systemd unit.
        # This is the normal state on machines supervised by systemd,
        # where PID files were never written.
        if self._is_port_in_use(port):
            owner_pid = self._find_ninja_owner_pid(module, port)
            if owner_pid is not None:
                source = "systemd" if self._is_systemd_active(module) else "port"
                return self._running_status(module, owner_pid, port, source)

        return self._stopped_status(module, port)

    def _stopped_status(self, module: str, port: int) -> dict[str, Any]:
        """Status payload for a module that is not running."""
        return {
            "running": False,
            "pid": None,
            "port": port,
            "url": f"http://127.0.0.1:{port}/sse",
            "log": str(self._get_log_file(module)),
            "installed_version": self._installed_version(),
            "running_since": None,
            "stale_code": None,
            "source": "none",
        }

    def _running_status(self, module: str, pid: int, port: int, source: str) -> dict[str, Any]:
        """Status payload for a running daemon, with freshness verdict."""
        started = self._process_start_time(module, pid, source)
        return {
            "running": True,
            "pid": pid,
            "port": port,
            "url": f"http://127.0.0.1:{port}/sse",
            "log": str(self._get_log_file(module)),
            "installed_version": self._installed_version(),
            "running_since": self._format_timestamp(started),
            "stale_code": self._is_stale_code(started, self._install_mtime()),
            "source": source,
        }

    @staticmethod
    def _format_timestamp(timestamp: float | None) -> str | None:
        """Render epoch seconds as a local ISO-8601 string."""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp).astimezone().isoformat(timespec="seconds")

    def _installed_version(self) -> str:
        """Version of the package on disk.

        This is all a CLI process can honestly know: the daemon may still be
        running older code, which ``stale_code`` reports separately.

        Returns:
            Version string or "unknown"
        """
        try:
            from importlib.metadata import version as get_version

            return get_version("ninja-mcp")
        except Exception:
            return "unknown"

    def _install_mtime(self) -> float | None:
        """Modification time of the installed package.

        Uses the ``dist-info`` directory for regular installs and
        ``pyproject.toml`` for editable installs (where dist-info does not
        change when the code does).

        Returns:
            Epoch seconds, or None when it cannot be determined
        """
        try:
            from importlib.metadata import distribution

            dist = distribution("ninja-mcp")
        except Exception:
            return None

        try:
            direct_url = dist.read_text("direct_url.json")
        except Exception:
            direct_url = None

        if direct_url:
            try:
                data = json.loads(direct_url)
                if data.get("dir_info", {}).get("editable"):
                    url = str(data.get("url", ""))
                    if url.startswith("file://"):
                        pyproject = Path(url[len("file://") :]) / "pyproject.toml"
                        return pyproject.stat().st_mtime
            except (json.JSONDecodeError, OSError, TypeError):
                pass

        dist_path = getattr(dist, "_path", None)
        if not dist_path:
            return None
        try:
            return Path(dist_path).stat().st_mtime
        except OSError:
            return None

    def _process_start_time(self, module: str, pid: int, source: str) -> float | None:
        """Start time of a daemon process (systemd unit timestamp or psutil)."""
        if source == "systemd":
            timestamp = self._systemd_active_enter_time(module)
            if timestamp is not None:
                return timestamp
        try:
            import psutil

            return float(psutil.Process(pid).create_time())
        except Exception:
            return None

    @staticmethod
    def _is_stale_code(running_since: float | None, installed_mtime: float | None) -> bool | None:
        """True when the daemon started before the installed package changed.

        Returns None when either timestamp is unknown (never guess).
        """
        if running_since is None or installed_mtime is None:
            return None
        return running_since < installed_mtime

    def restart(self, module: str) -> bool:
        """Restart daemon for module.

        systemd-supervised modules are restarted through their own user unit
        and verified by observing a new MainPID plus a listening port; PID-file
        daemons keep the legacy stop+start path. Never reports success without
        evidence that the daemon actually restarted.

        Args:
            module: Module name

        Returns:
            True if restart was observed to succeed
        """
        pid = self._read_pid(module)
        if pid and self._is_running(pid):
            # PID-file daemon (started by `daemon start`): legacy path, and
            # systemd is never consulted.
            self.stop(module)
            return self.start(module)

        if self._systemd_owns(module):
            return self._restart_systemd(module)

        # Active unit without a live MainPID (e.g. failed start): systemctl
        # restart is still the only module-scoped recovery; verification
        # accepts the first live MainPID it observes.
        if self._is_systemd_active(module):
            return self._restart_systemd(module, previous_pid_unknown=True)

        self.stop(module)
        return self.start(module)

    def _restart_systemd(self, module: str, previous_pid_unknown: bool = False) -> bool:
        """Restart the module's unit and verify a new MainPID plus a live port."""
        unit = self._systemd_unit(module)
        old_pid = None if previous_pid_unknown else self._systemd_main_pid(module)
        if old_pid is None and not previous_pid_unknown:
            logger.error(f"Cannot restart {module}: {unit} reports no MainPID")
            return False

        result = self._run_systemctl("restart", unit)
        if result is None or result.returncode != 0:
            detail = result.stderr.strip() if result is not None else "systemctl unavailable"
            logger.error(f"systemctl --user restart {unit} failed for {module}: {detail}")
            return False

        new_pid = self._wait_for_new_main_pid(
            module, old_pid, self.systemd_restart_timeout, self.poll_interval
        )
        if new_pid is None:
            logger.error(
                f"{module} was NOT restarted: {unit} reported no new MainPID within "
                f"{self.systemd_restart_timeout:.0f}s (previous MainPID: {old_pid})"
            )
            return False

        if not self._wait_for_port(module, self.port_ready_timeout, self.poll_interval):
            logger.error(
                f"{module} restarted (PID {new_pid}) but port {self._get_port(module)} "
                "is not answering; not reporting success"
            )
            return False

        logger.info(f"Restarted {module} via systemd ({unit}): PID {old_pid} → {new_pid}")
        return True

    def upgrade(self, version: str | None = None) -> bool:
        """Upgrade ninja-mcp from PyPI."""
        import subprocess as sp

        pkg_spec = f"ninja-mcp=={version}" if version else "ninja-mcp"

        cmd = [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "--break-system-packages",
            "--upgrade",
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


def describe_daemon_versions(manager: DaemonManager | None = None) -> list[str]:
    """Return one honest line per running daemon.

    Never claims an in-memory version: reports the process start time and
    whether that predates the installed package (``stale_code``).
    """
    mgr = manager or DaemonManager()
    lines: list[str] = []
    for module in mgr.list_modules():
        try:
            status = mgr.status(module)
        except Exception:
            continue
        if not status.get("running"):
            continue
        stale = status.get("stale_code")
        if stale is True:
            verdict = "STALE: started before the installed package changed"
        elif stale is False:
            verdict = "fresh"
        else:
            verdict = "staleness unknown"
        lines.append(
            f"  {module:12s} pid {status['pid']}  since {status['running_since']}  {verdict}"
        )
    return lines


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
        print(f"ninja-mcp {manager._installed_version()} (installed on disk)")
        for line in describe_daemon_versions(manager):
            print(line)

    elif args.command == "connect":
        if not _validate_module(args.module):
            return 1
        status = manager.status(args.module)
        if not status["running"]:
            # Belt-and-braces: status() already falls back to port-owner
            # detection, but re-check here so a race between status and
            # connect still dials a live ninja server instead of exiting 1
            # (the opencode "daemon not running" disconnects).
            port = manager._get_port(args.module)
            owner = manager._find_ninja_owner_pid(args.module, port)
            if owner is None:
                print(f"Error: {args.module} daemon not running", file=sys.stderr)
                return 1
            print(
                f"Warning: {args.module} daemon has no PID file; "
                f"connecting to port owner pid {owner}",
                file=sys.stderr,
            )
        else:
            port = status["port"]

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
