"""Integration tests for the Ninja MCP daemon lifecycle."""

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psutil
import pytest

from ninja_common.daemon import DaemonManager


SERVER_MODULES = ("coder", "researcher", "secretary")


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


def test_no_old_servers_running():
    """Test that no old servers from uv/tools are still running."""
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Check for old servers from uv/tools
    old_servers = [
        line
        for line in result.stdout.splitlines()
        if "ninja_" in line and "server" in line and "uv/tools" in line and "grep" not in line
    ]

    assert len(old_servers) == 0, (
        f"Found {len(old_servers)} old servers still running from uv/tools: {old_servers}"
    )


def test_daemon_pid_files_exist(running_daemons: DaemonManager):
    """Test that started daemons create PID files for client connections."""
    missing_pids = [
        module
        for module in SERVER_MODULES
        if not (running_daemons.daemon_dir / f"{module}.pid").exists()
    ]

    assert not missing_pids, f"Missing PID files for daemons: {missing_pids}"
