import pytest


"""
Test to verify that ninja MCP servers are running correctly after the fix.

This test checks that all ninja servers have been restarted with the new code
after fixing the --attach bug in opencode_strategy.py.
"""

import subprocess
from pathlib import Path


def test_servers_restarted():
    """Test that all ninja servers are running from the correct location (.venv)."""
    # Get list of running ninja server processes
    result = subprocess.run(
        ["ps", "aux"],
        capture_output=True,
        text=True,
        check=True,
    )

    # Filter for ninja server processes running from .venv
    ninja_servers = [
        line for line in result.stdout.splitlines()
        if "ninja_" in line
        and "server" in line
        and ".venv" in line
        and "grep" not in line
    ]

    # Should have at least 4 servers: coder, researcher, secretary, prompts
    assert len(ninja_servers) >= 4, (
        f"Expected at least 4 ninja servers running from .venv, "
        f"but found {len(ninja_servers)}: {ninja_servers}"
    )

    # Verify specific servers are running
    server_types = ["ninja_coder", "ninja_researcher", "ninja_secretary", "ninja_prompts"]
    for server_type in server_types:
        matching = [s for s in ninja_servers if server_type in s]
        assert len(matching) > 0, f"Server {server_type} not found in running processes"


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
        line for line in result.stdout.splitlines()
        if "ninja_" in line
        and "server" in line
        and "uv/tools" in line
        and "grep" not in line
    ]

    assert len(old_servers) == 0, (
        f"Found {len(old_servers)} old servers still running from uv/tools: {old_servers}"
    )


def test_daemon_pid_files_exist():
    """Test that daemon PID files exist so Claude Code can connect."""
    daemon_dir = Path.home() / ".cache" / "ninja-mcp" / "daemons"

    # Expected daemon modules
    expected_daemons = ["coder", "researcher", "secretary", "prompts"]

    missing_pids = []
    for daemon in expected_daemons:
        pid_file = daemon_dir / f"{daemon}.pid"
        if not pid_file.exists():
            missing_pids.append(daemon)

    assert len(missing_pids) == 0, (
        f"Missing PID files for daemons: {missing_pids}. "
        f"Claude Code won't be able to connect without PID files. "
        f"Run 'ninja-daemon start' to create them."
    )
