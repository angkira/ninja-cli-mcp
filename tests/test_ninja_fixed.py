"""Integration tests for the Ninja MCP daemon lifecycle."""

import os
import re
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from ninja_common.daemon import DaemonManager


SERVER_MODULES = ("coder", "researcher", "secretary")

#: Matches the module name in a ``ninja_<module>.server`` / ``ninja_<module>`` cmdline.
_SERVER_MODULE_RE = re.compile(r"ninja_(coder|researcher|secretary|agent)\b")

#: Matches a systemd user unit name (without the ``.service`` suffix) in a cgroup.
_SYSTEMD_UNIT_RE = re.compile(r"(ninja-mcp@[A-Za-z0-9_.-]+)\.service")


def _uses_current_python_environment(process: psutil.Process) -> bool:
    """Return whether a daemon uses this test's interpreter or virtualenv."""
    daemon_executable = process.exe()
    try:
        if Path(daemon_executable).samefile(sys.executable):
            return True
    except FileNotFoundError:
        return False

    current_virtual_env = os.environ.get("VIRTUAL_ENV")
    daemon_virtual_env = process.environ().get("VIRTUAL_ENV")
    return bool(
        current_virtual_env
        and daemon_virtual_env
        and Path(current_virtual_env).resolve() == Path(daemon_virtual_env).resolve()
        and Path(current_virtual_env).resolve() == Path(sys.prefix).resolve()
    )


@pytest.fixture
def running_daemons(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[DaemonManager]:
    """Start the server daemons in an isolated cache and stop them after the test."""
    isolated_home = tmp_path / "home"
    isolated_home.mkdir()
    monkeypatch.setenv("HOME", str(isolated_home))
    manager = DaemonManager(cache_dir=isolated_home / ".cache" / "ninja-mcp")
    ports = {
        module: manager._find_free_port(start_port=10000 + index * 100)
        for index, module in enumerate(SERVER_MODULES)
    }
    for module, port in ports.items():
        monkeypatch.setenv(f"NINJA_{module.upper()}_PORT", str(port))

    started: list[str] = []
    try:
        for module in SERVER_MODULES:
            result = subprocess.run(
                [sys.executable, "-m", "ninja_common.daemon", "start", module],
                check=False,
                capture_output=True,
                text=True,
                env=None,
            )
            if result.returncode != 0:
                pytest.fail(f"Could not start {module} daemon")
            started.append(module)
        yield manager
    finally:
        for module in reversed(started):
            subprocess.run(
                [sys.executable, "-m", "ninja_common.daemon", "stop", module],
                check=False,
                capture_output=True,
                text=True,
            )


def test_servers_restarted(running_daemons: DaemonManager):
    """Restart each server and verify it runs under the test environment."""
    for module in SERVER_MODULES:
        result = subprocess.run(
            [sys.executable, "-m", "ninja_common.daemon", "restart", module],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, f"Could not restart {module} daemon: {result.stderr}"
        status = running_daemons.status(module)
        assert status["running"] is True

        process = psutil.Process(status["pid"])
        assert _uses_current_python_environment(process)
        assert f"ninja_{module}.server" in " ".join(process.cmdline())


def _systemd_unit_active(unit: str) -> bool:
    """Return whether a user systemd unit is active (read-only query)."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "is-active", unit],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.stdout.strip() == "active"


def _process_cgroup_units(pid: int) -> set[str]:
    """Return the ``ninja-mcp@*`` user units named in a process's cgroup chain."""
    try:
        cgroup = Path(f"/proc/{pid}/cgroup").read_text()
    except OSError:
        return set()
    return set(_SYSTEMD_UNIT_RE.findall(cgroup))


def _owned_by_active_systemd_unit(process: psutil.Process, module: str | None) -> bool:
    """Return whether a server runs under an active ``ninja-mcp@<module>`` unit.

    The server started by a unit may run in a child process (wrappers, shells),
    so every ancestor's cgroup is inspected as well: children inherit the unit
    cgroup. Purely read-only — no process is ever signalled.
    """
    if module and _systemd_unit_active(f"ninja-mcp@{module}.service"):
        return True
    ancestors = [process, *process.parents()]
    for ancestor in ancestors:
        for unit in _process_cgroup_units(ancestor.pid):
            if _systemd_unit_active(f"{unit}.service"):
                return True
    return False


def test_no_old_servers_running():
    """Test that no stale servers from uv/tools are still running.

    A server installed by ``uv tool install`` and started by an active
    ``ninja-mcp@<module>.service`` user unit is the intended production state,
    not a stale leftover, so those are skipped. Servers with no active unit
    behind them are genuinely orphaned and still fail the test.
    """
    stale_servers: list[str] = []
    managed_servers: list[str] = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(process.info["cmdline"] or ())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if not ("ninja_" in cmdline and "server" in cmdline and "uv/tools" in cmdline):
            continue
        module_match = _SERVER_MODULE_RE.search(cmdline)
        module = module_match.group(1) if module_match else None
        entry = f"pid {process.pid}: {cmdline}"
        try:
            managed = _owned_by_active_systemd_unit(process, module)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            managed = False
        (managed_servers if managed else stale_servers).append(entry)

    if stale_servers:
        raise AssertionError(
            f"Found {len(stale_servers)} stale servers still running from uv/tools "
            f"with no active systemd unit: {stale_servers}"
        )

    if managed_servers:
        pytest.skip(
            f"{len(managed_servers)} server(s) from uv/tools run under an active "
            f"ninja-mcp systemd user unit: {managed_servers}"
        )


def test_daemon_pid_files_exist(running_daemons: DaemonManager):
    """Test that started daemons create PID files for client connections."""
    missing_pids = [
        module
        for module in SERVER_MODULES
        if not (running_daemons.daemon_dir / f"{module}.pid").exists()
    ]

    assert not missing_pids, f"Missing PID files for daemons: {missing_pids}"
