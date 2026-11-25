"""Tests for cancel-aware, process-group-based subprocess execution."""

from __future__ import annotations

import asyncio
import importlib
from typing import TYPE_CHECKING, Any

import psutil
import pytest
from mcp import Client, types
from mcp.client import advertise
from pydantic import Field, TypeAdapter

from ninja_common.mcp_ext.protocol import TASKS_EXTENSION_ID
from ninja_common.mcp_tasks import request_cancel, task_scope
from ninja_common.subprocess_runner import run_cancellable


if TYPE_CHECKING:
    from pathlib import Path

    from pytest import MonkeyPatch


_DICT_ADAPTER: TypeAdapter[dict[str, Any]] = TypeAdapter(dict[str, Any])


class _RawRequest(types.Request[dict[str, Any], str]):
    """A request for a method the client SDK has no typed helper for."""

    params: dict[str, Any] = Field(default_factory=dict)


def _alive(pid: int) -> bool:
    """Whether *pid* names a live (non-zombie) process."""
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
    except psutil.AccessDenied:
        return True


async def _wait_dead(pid: int, *, timeout: float = 10.0) -> None:
    """Poll until *pid* is gone, failing the test after *timeout* seconds."""
    deadline = asyncio.get_running_loop().time() + timeout
    while _alive(pid):
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"process {pid} is still alive after {timeout}s")
        await asyncio.sleep(0.05)


async def _wait_path(path: Path, *, timeout: float = 10.0) -> str:
    """Poll until *path* exists and return its stripped content."""
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        if path.exists():
            content = path.read_text(encoding="utf-8").strip()
            if content:
                return content
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError(f"{path} was not written within {timeout}s")
        await asyncio.sleep(0.05)


def _pid_file_command(shell_pid_file: Path, child_pid_file: Path) -> str:
    """A shell command that records its own pid and its child's pid, then waits."""
    return f"sleep 30 & child=$!; echo $child > {child_pid_file}; echo $$ > {shell_pid_file}; wait"


# --------------------------------------------------------------------------- #
# 1. Normal command
# --------------------------------------------------------------------------- #


async def test_run_cancellable_returns_stdout_and_returncode() -> None:
    completed = await run_cancellable(["sh", "-c", "echo hello; echo warn >&2; exit 3"])

    assert completed.returncode == 3
    assert completed.stdout.strip() == "hello"
    assert completed.stderr.strip() == "warn"


async def test_run_cancellable_shell_mode_uses_own_process_group() -> None:
    completed = await run_cancellable("echo shell-ok", shell=True)

    assert completed.returncode == 0
    assert completed.stdout.strip() == "shell-ok"


# --------------------------------------------------------------------------- #
# 2. Timeout kills the whole group
# --------------------------------------------------------------------------- #


async def test_timeout_kills_the_whole_process_group(tmp_path: Path) -> None:
    shell_pid_file = tmp_path / "shell.pid"
    child_pid_file = tmp_path / "child.pid"

    with pytest.raises(TimeoutError):
        await run_cancellable(
            _pid_file_command(shell_pid_file, child_pid_file),
            shell=True,
            timeout=1,
        )

    shell_pid = int(await _wait_path(shell_pid_file))
    child_pid = int(await _wait_path(child_pid_file))
    await _wait_dead(shell_pid)
    await _wait_dead(child_pid)

    assert not _alive(shell_pid)
    assert not _alive(child_pid)


# --------------------------------------------------------------------------- #
# 3. Task cancellation kills the whole group
# --------------------------------------------------------------------------- #


async def test_task_cancellation_kills_the_whole_process_group(tmp_path: Path) -> None:
    task_id = "runner-cancel-test"
    shell_pid_file = tmp_path / "shell.pid"
    child_pid_file = tmp_path / "child.pid"

    async with task_scope(task_id):
        running = asyncio.create_task(
            run_cancellable(
                _pid_file_command(shell_pid_file, child_pid_file),
                shell=True,
                timeout=120,
            )
        )

        shell_pid = int(await _wait_path(shell_pid_file))
        child_pid = int(await _wait_path(child_pid_file))
        assert _alive(shell_pid) and _alive(child_pid)

        assert request_cancel(task_id) is True

        with pytest.raises(asyncio.CancelledError):
            await running

        # Give the registry's terminate task a chance to finish too.
        await asyncio.sleep(0.05)

    await _wait_dead(shell_pid)
    await _wait_dead(child_pid)

    assert not _alive(shell_pid), "the shell survived task cancellation"
    assert not _alive(child_pid), "the sleep child survived task cancellation"


# --------------------------------------------------------------------------- #
# 4. Regression: tasks/cancel through a real in-memory agent MCP client
# --------------------------------------------------------------------------- #


@pytest.fixture(autouse=True)
def _task_store_path(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Keep the durable task store out of the developer's ``~/.ninja``."""
    monkeypatch.setenv("NINJA_TASKS_DB", str(tmp_path / "tasks.db"))


async def test_agent_task_cancel_stops_the_subprocess_group(tmp_path: Path) -> None:
    """The exact battle-test failure: ``sleep`` keeps running after cancel."""
    shell_pid_file = tmp_path / "shell.pid"
    child_pid_file = tmp_path / "child.pid"
    arguments = {
        "steps": [
            {
                "command": _pid_file_command(shell_pid_file, child_pid_file),
                "allow_write": True,
            }
        ],
        "repo_root": str(tmp_path),
    }

    server = importlib.import_module("ninja_agent.server").create_server()
    async with Client(server, extensions=[advertise(TASKS_EXTENSION_ID)]) as client:
        created = await client.session.send_request(
            _RawRequest(
                method="tools/call",
                params={"name": "agent_exec_pipeline", "arguments": arguments},
            ),
            _DICT_ADAPTER,
        )
        assert created["resultType"] == "task"
        task_id = created["taskId"]

        # The pipeline runs asynchronously; wait until the shell is really up
        # before asking for cancellation.
        shell_pid = int(await _wait_path(shell_pid_file))
        child_pid = int(await _wait_path(child_pid_file))
        assert _alive(shell_pid) and _alive(child_pid)

        acknowledgement = await client.session.send_request(
            _RawRequest(method="tasks/cancel", params={"taskId": task_id}),
            _DICT_ADAPTER,
        )
        assert acknowledgement["resultType"] == "complete"

        fetched = await client.session.send_request(
            _RawRequest(method="tasks/get", params={"taskId": task_id}),
            _DICT_ADAPTER,
        )
        assert fetched["status"] == "cancelled"

        await _wait_dead(shell_pid)
        await _wait_dead(child_pid)

        assert not _alive(shell_pid), "the pipeline shell survived tasks/cancel"
        assert not _alive(child_pid), "the pipeline child survived tasks/cancel"


# --------------------------------------------------------------------------- #
# 5. No leaked asyncio tasks after a cancellation
# --------------------------------------------------------------------------- #


async def test_no_pending_tasks_after_cancellation(tmp_path: Path) -> None:
    """Cancellation must not leave watcher tasks behind."""
    task_id = "runner-cancel-no-leak"
    pid_file = tmp_path / "shell.pid"

    before = {task for task in asyncio.all_tasks() if task is not asyncio.current_task()}
    async with task_scope(task_id):
        running = asyncio.create_task(
            run_cancellable(f"sleep 30; echo $$ > {pid_file}", shell=True, timeout=120)
        )
        await asyncio.sleep(0.1)
        request_cancel(task_id)
        with pytest.raises(asyncio.CancelledError):
            await running

    await asyncio.sleep(0.05)
    leftover = {
        task
        for task in asyncio.all_tasks()
        if task is not asyncio.current_task() and task not in before
    }
    assert leftover == set()
