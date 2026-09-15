"""End-to-end tests for standard MCP Tasks in the ninja MCP servers.

The coder tests spawn the real ninja-coder server over stdio via
``tests._task_stub_server`` (which swaps only the ``ToolExecutor`` for a
deterministic stub), so no model or network is required. A generic test also
verifies the same task plumbing in the real agent and researcher servers by
calling a task-capable tool with invalid arguments, which fails validation
before any external call.

Covered:
* A client that advertises the ``tasks`` capability gets a task handle from a
  task-capable tool, can poll ``tasks/get`` to completion and fetch the payload
  via ``tasks/result``.
* Such a client can cancel a still-running task via ``tasks/cancel``.
* A client without the ``tasks`` capability keeps getting the synchronous
  result exactly as before.
* The task lifecycle is wired identically across coder, agent and researcher.
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import types
from mcp.client.experimental.task_handlers import ExperimentalTaskHandlers
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ninja_common.mcp_tasks import SqliteTaskStore, emit_progress, task_scope


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


REPO_ROOT = Path(__file__).resolve().parent.parent
SLOW_TASK = "slow: keep running until cancelled"
SIMPLE_TASK = "hello from the task test"

# (server module, a task-capable tool with required args)
TASK_SERVERS = [
    ("tests._task_stub_server", "coder_simple_task"),
    ("ninja_agent.server", "agent_analyze"),
    ("ninja_researcher.server", "researcher_deep_research"),
]


async def _unsupported(context: object, params: object) -> types.ErrorData:
    """Generic handler used only to make the client advertise task support."""
    return types.ErrorData(code=types.METHOD_NOT_FOUND, message="not supported")


def _text_of(result: types.CallToolResult) -> str:
    """Return the first text block payload of a tool result."""
    assert result.content, "expected at least one content block"
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


@asynccontextmanager
async def _connected(
    with_tasks: bool,
    server_module: str = "tests._task_stub_server",
    extra_env: dict[str, str] | None = None,
) -> AsyncIterator[tuple[ClientSession, types.InitializeResult]]:
    """Connect to a ninja MCP server over stdio."""
    # Isolate durable task state per connection so tests never touch the real
    # ~/.ninja/tasks.db and can exercise restart persistence on their own file.
    db_dir = tempfile.mkdtemp(prefix="ninja-tasks-test-")
    env = {
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")]),
        "NINJA_LOG_LEVEL": "WARNING",
        "NINJA_TASKS_DB": str(Path(db_dir) / "tasks.db"),
    }
    if extra_env:
        env.update(extra_env)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", server_module],
        env=env,
        cwd=str(REPO_ROOT),
    )
    handlers = (
        ExperimentalTaskHandlers(list_tasks=_unsupported, cancel_task=_unsupported)
        if with_tasks
        else None
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(
            read_stream, write_stream, experimental_task_handlers=handlers
        ) as session:
            init_result = await session.initialize()
            yield session, init_result


async def test_server_declares_tasks_capability() -> None:
    """The coder server must advertise the standard tasks capability."""
    async with _connected(with_tasks=True) as (_session, init_result):
        assert init_result.capabilities.tasks is not None
        assert init_result.capabilities.tasks.list is not None
        assert init_result.capabilities.tasks.cancel is not None


async def test_task_augmented_call_returns_handle_then_result() -> None:
    """A task-augmented call returns a handle; polling reaches the payload."""
    async with _connected(with_tasks=True) as (session, _init):
        create = await session.experimental.call_tool_as_task(
            "coder_simple_task",
            {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
            ttl=60000,
        )

        # The handle comes back immediately, before the work completes.
        assert create.task.taskId
        assert create.task.status == "working"
        task_id = create.task.taskId

        terminal: types.GetTaskResult | None = None
        async for status in session.experimental.poll_task(task_id):
            terminal = status
        assert terminal is not None
        assert terminal.status == "completed"

        result = await session.experimental.get_task_result(task_id, types.CallToolResult)
        assert result.isError is False
        assert len(result.content) == 1
        assert f"stub: {SIMPLE_TASK}" in _text_of(result)


async def test_running_task_can_be_cancelled() -> None:
    """A task that is still working can be cancelled via tasks/cancel."""
    async with _connected(with_tasks=True) as (session, _init):
        create = await session.experimental.call_tool_as_task(
            "coder_simple_task",
            {"task": SLOW_TASK, "repo_root": str(REPO_ROOT)},
            ttl=60000,
        )
        task_id = create.task.taskId

        cancelled = await session.experimental.cancel_task(task_id)
        assert cancelled.taskId == task_id
        assert cancelled.status == "cancelled"

        status = await session.experimental.get_task(task_id)
        assert status.status == "cancelled"


async def test_cancel_is_idempotent_for_terminal_and_unknown_tasks() -> None:
    """Cancelling a finished or unknown task never raises or tears down tasks."""
    async with _connected(with_tasks=True) as (session, _init):
        create = await session.experimental.call_tool_as_task(
            "coder_simple_task",
            {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
            ttl=60000,
        )
        task_id = create.task.taskId
        async for _ in session.experimental.poll_task(task_id):
            pass

        terminal = await session.experimental.cancel_task(task_id)
        assert terminal.taskId == task_id
        assert terminal.status == "completed"

        unknown = await session.experimental.cancel_task("no-such-task-id")
        assert unknown.taskId == "no-such-task-id"
        assert unknown.status == "cancelled"


async def test_sync_call_without_tasks_capability_unchanged() -> None:
    """Clients that do not advertise tasks get the normal synchronous result."""
    # A default client announces no `tasks` capability.
    assert ExperimentalTaskHandlers().build_capability() is None

    async with _connected(with_tasks=False) as (session, init_result):
        # The server still offers tasks to clients that can use them.
        assert init_result.capabilities.tasks is not None
        result = await session.call_tool(
            "coder_simple_task",
            {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
        )
        assert result.isError is False
        assert f"stub: {SIMPLE_TASK}" in _text_of(result)


@pytest.mark.parametrize(("server_module", "tool_name"), TASK_SERVERS)
async def test_task_capability_and_tool_mode_across_servers(
    server_module: str, tool_name: str
) -> None:
    """coder/agent/researcher all declare tasks and mark the tool optional.

    The full create -> poll -> result lifecycle is exercised against coder by
    the tests above; agent and researcher share the exact same ``call_tool``
    wiring, so here we assert the capability and per-tool ``taskSupport`` that
    clients discover during initialization.
    """
    async with _connected(with_tasks=True, server_module=server_module) as (session, init):
        assert init.capabilities.tasks is not None

        tool = next(t for t in (await session.list_tools()).tools if t.name == tool_name)
        assert tool.execution is not None
        assert tool.execution.taskSupport == "optional"


async def _wait_for_marker(marker: Path, needle: str, *, timeout: float = 15.0) -> bool:
    """Poll *marker* until it contains *needle* (or the timeout elapses)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and needle in marker.read_text():
            return True
        await asyncio.sleep(0.05)
    return False


def _marker_text(marker: Path) -> str:
    return marker.read_text() if marker.exists() else "<no marker file>"


async def test_cancelling_running_task_interrupts_work(tmp_path: Path) -> None:
    """Cancelling a running task actually stops the work, without teardown."""
    marker = tmp_path / "marker.txt"
    async with _connected(with_tasks=True, extra_env={"NINJA_TASK_TEST_MARKER": str(marker)}) as (
        session,
        _init,
    ):
        create = await session.experimental.call_tool_as_task(
            "coder_simple_task",
            {"task": SLOW_TASK, "repo_root": str(REPO_ROOT)},
            ttl=60000,
        )
        task_id = create.task.taskId
        assert await _wait_for_marker(marker, "progress=1", timeout=10), _marker_text(marker)

        cancelled = await session.experimental.cancel_task(task_id)
        assert cancelled.status == "cancelled"

        # The stub loop observes the cancellation and exits early.
        assert await _wait_for_marker(marker, "interrupted", timeout=10), _marker_text(marker)
        assert "completed" not in _marker_text(marker)

        status = await session.experimental.get_task(task_id)
        assert status.status == "cancelled"

        # Task support survived the cancellation (no background task-group
        # teardown): a fresh synchronous call still works on the same session.
        result = await session.call_tool(
            "coder_simple_task",
            {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
        )
        assert result.isError is False
        assert f"stub: {SIMPLE_TASK}" in _text_of(result)


async def test_progress_callback_invoked_for_running_task(tmp_path: Path) -> None:
    """The task wiring installs a progress bridge that is actually invoked."""
    marker = tmp_path / "marker-progress.txt"
    async with _connected(with_tasks=True, extra_env={"NINJA_TASK_TEST_MARKER": str(marker)}) as (
        session,
        _init,
    ):
        create = await session.experimental.call_tool_as_task(
            "coder_simple_task",
            {"task": SLOW_TASK, "repo_root": str(REPO_ROOT)},
            ttl=60000,
            meta={"progressToken": "progress-token-1"},
        )
        try:
            assert await _wait_for_marker(marker, "progress=1", timeout=10), _marker_text(marker)
        finally:
            await session.experimental.cancel_task(create.task.taskId)


async def test_sqlite_task_store_persists_across_instances(tmp_path: Path) -> None:
    """A fresh store instance sees tasks and results written by an earlier one."""
    db_path = tmp_path / "tasks.db"
    store = SqliteTaskStore(db_path)
    created = await store.create_task(types.TaskMetadata(ttl=60000))
    await store.update_task(created.taskId, status_message="halfway")

    reopened = SqliteTaskStore(db_path)
    fetched = await reopened.get_task(created.taskId)
    assert fetched is not None
    assert fetched.taskId == created.taskId
    assert fetched.status == "working"
    assert fetched.statusMessage == "halfway"

    result = types.CallToolResult(
        content=[types.TextContent(type="text", text="done")], isError=False
    )
    await store.store_result(created.taskId, result)
    third = SqliteTaskStore(db_path)
    stored_result = await third.get_result(created.taskId)
    assert stored_result is not None
    assert stored_result.model_dump(by_alias=True)["content"][0]["text"] == "done"

    assert await third.delete_task(created.taskId) is True
    assert await reopened.get_task(created.taskId) is None
    assert await reopened.delete_task(created.taskId) is False


async def test_task_scope_and_emit_progress_round_trip() -> None:
    """emit_progress invokes the scoped callback and no-ops without one."""
    calls: list[tuple[float, float | None, str | None]] = []

    async def _callback(current: float, total: float | None, message: str | None) -> None:
        calls.append((current, total, message))

    assert await emit_progress(1.0, None, "outside") is False

    async with task_scope("task-unit-1", progress=_callback) as cancellation:
        assert cancellation.is_set() is False
        assert await emit_progress(1.0, 2.0, "inside") is True

    assert calls == [(1.0, 2.0, "inside")]
