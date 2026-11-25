"""Tests for the MCP Tasks extension server half (``io.modelcontextprotocol/tasks``)."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.client.extension import ClaimContext
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolRequestParams, CallToolResult, TextContent

from ninja_common.mcp_ext import tasks as tasks_module
from ninja_common.mcp_ext.models import (
    CancelTaskParams,
    GetTaskParams,
    GetTaskResult,
    UpdateTaskParams,
)
from ninja_common.mcp_ext.tasks import TasksExtension
from ninja_common.mcp_ext.tasks_client import (
    CancelTaskRequest,
    GetTaskRequest,
    RemoteTaskCancelledError,
    TaskClaimedResult,
    TasksClient,
    UpdateTaskRequest,
)
from ninja_common.mcp_ext.tasks_store import SqliteTaskStore


PROTOCOL_2026 = "2026-07-28"
PROTOCOL_LEGACY = "2025-11-25"
TASKS_EXTENSION = "io.modelcontextprotocol/tasks"
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603
MISSING_REQUIRED_CLIENT_CAPABILITY = -32021


class _FakeCapabilities:
    """Stand-in for ``ClientCapabilities`` (only ``extensions`` is read)."""

    def __init__(self, extensions: dict[str, dict[str, Any]]) -> None:
        self.extensions = extensions


class _FakeSession:
    """Stand-in for ``ServerSession`` (only ``client_capabilities`` is read)."""

    def __init__(self, declared: bool) -> None:
        self.client_capabilities = _FakeCapabilities({TASKS_EXTENSION: {}} if declared else {})


class FakeContext:
    """Minimal ``ServerRequestContext``: session capabilities + protocol version."""

    def __init__(self, *, declared: bool = True, protocol_version: str = PROTOCOL_2026) -> None:
        self.session = _FakeSession(declared)
        self.protocol_version = protocol_version


def handler(ext: TasksExtension, method: str) -> Any:
    """Return the bound handler the SDK installs for *method*."""
    for binding in ext.methods():
        if binding.method == method:
            return binding.handler
    raise AssertionError(f"no binding for {method}")


def tool_params(name: str = "slow_tool") -> CallToolRequestParams:
    return CallToolRequestParams(name=name, arguments={"delay": 1})


def completed(content: str = "done") -> CallToolResult:
    return CallToolResult(content=[TextContent(type="text", text=content)])


@pytest.fixture
def store() -> SqliteTaskStore:
    return SqliteTaskStore(":memory:")


# -- 1. client without the extension -----------------------------------------


async def test_interceptor_passes_through_without_extension(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)
    seen: list[Any] = []

    async def call_next(ctx: Any) -> CallToolResult:
        seen.append(ctx)
        return completed("inline")

    result = await ext.intercept_tool_call(tool_params(), FakeContext(declared=False), call_next)

    assert isinstance(result, CallToolResult)
    assert result.result_type == "complete"
    assert result.content[0].text == "inline"  # type: ignore[union-attr]
    assert len(seen) == 1
    tasks, cursor = await store.list_tasks()
    assert tasks == []
    assert cursor is None


async def test_interceptor_passes_through_for_unlisted_tool(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store, task_tools=["long_running"])

    async def call_next(ctx: Any) -> CallToolResult:
        return completed()

    result = await ext.intercept_tool_call(tool_params("other_tool"), FakeContext(), call_next)

    assert isinstance(result, CallToolResult)
    assert (await store.list_tasks())[0] == []


# -- 2. client with the extension --------------------------------------------


async def test_interceptor_creates_durable_task(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)

    async def call_next(ctx: Any) -> CallToolResult:
        return completed()

    result = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)

    assert result.result_type == "task"  # type: ignore[union-attr]
    assert result.status == "working"  # type: ignore[union-attr]
    assert result.poll_interval_ms == 500  # type: ignore[union-attr]

    stored = await store.get_task(result.task_id)  # type: ignore[union-attr]
    assert stored is not None
    assert stored.status == "working"

    await ext.wait_for(result.task_id, timeout=5)  # type: ignore[union-attr]


# -- 3. background completion ------------------------------------------------


async def test_get_returns_completed_payload(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)

    async def call_next(ctx: Any) -> CallToolResult:
        return CallToolResult(
            content=[TextContent(type="text", text="done")],
            structured_content={"answer": 42},
        )

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    task = await ext.wait_for(created.task_id, timeout=5)  # type: ignore[union-attr]
    assert task.status == "completed"

    got = await handler(ext, "tasks/get")(
        FakeContext(),
        GetTaskParams(task_id=created.task_id),  # type: ignore[union-attr]
    )

    assert isinstance(got, GetTaskResult)
    assert got.status == "completed"
    assert got.error is None
    assert got.result is not None
    assert got.result["content"][0]["text"] == "done"
    assert got.result["structuredContent"] == {"answer": 42}
    assert got.result["resultType"] == "complete"


async def test_get_reports_working_task_without_payload(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)
    release = asyncio.Event()

    async def call_next(ctx: Any) -> CallToolResult:
        await release.wait()
        return completed()

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    got = await handler(ext, "tasks/get")(
        FakeContext(),
        GetTaskParams(task_id=created.task_id),  # type: ignore[union-attr]
    )

    assert got.status == "working"
    assert got.result is None
    assert got.error is None

    release.set()
    await ext.wait_for(created.task_id, timeout=5)  # type: ignore[union-attr]


# -- 4. background failure ---------------------------------------------------


async def test_get_returns_mcp_error_with_original_code(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)

    async def call_next(ctx: Any) -> CallToolResult:
        raise MCPError(code=INVALID_PARAMS, message="bad input", data="delay")

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    task = await ext.wait_for(created.task_id, timeout=5)  # type: ignore[union-attr]
    assert task.status == "failed"

    got = await handler(ext, "tasks/get")(
        FakeContext(),
        GetTaskParams(task_id=created.task_id),  # type: ignore[union-attr]
    )

    assert got.status == "failed"
    assert got.error == {"code": INVALID_PARAMS, "message": "bad input", "data": "delay"}
    assert got.result is None


async def test_unexpected_exception_maps_to_internal_error(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)

    async def call_next(ctx: Any) -> CallToolResult:
        raise RuntimeError("kaboom")

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    await ext.wait_for(created.task_id, timeout=5)  # type: ignore[union-attr]

    got = await handler(ext, "tasks/get")(
        FakeContext(),
        GetTaskParams(task_id=created.task_id),  # type: ignore[union-attr]
    )

    assert got.status == "failed"
    assert got.error is not None
    assert got.error["code"] == INTERNAL_ERROR
    assert "kaboom" in got.error["message"]


# -- 5. unknown task ids -----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("tasks/get", GetTaskParams(task_id="missing")),
        ("tasks/update", UpdateTaskParams(task_id="missing", input_responses={})),
        ("tasks/cancel", CancelTaskParams(task_id="missing")),
    ],
)
async def test_unknown_task_is_invalid_params(
    store: SqliteTaskStore, method: str, params: Any
) -> None:
    ext = TasksExtension(store)

    with pytest.raises(MCPError) as excinfo:
        await handler(ext, method)(FakeContext(), params)

    assert excinfo.value.code == INVALID_PARAMS
    assert "missing" in excinfo.value.message


# -- 6. cancelling a working task --------------------------------------------


async def test_cancel_working_task_is_cooperative_and_idempotent(
    store: SqliteTaskStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    requested: list[str] = []

    def fake_request_cancel(task_id: str) -> bool:
        requested.append(task_id)
        return True

    monkeypatch.setattr(tasks_module, "request_cancel", fake_request_cancel)

    ext = TasksExtension(store, cancel_wait_seconds=0.05)
    release = asyncio.Event()

    async def call_next(ctx: Any) -> CallToolResult:
        await release.wait()
        return completed()

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    task_id = created.task_id  # type: ignore[union-attr]
    await asyncio.sleep(0)  # let the background run start

    first = await handler(ext, "tasks/cancel")(FakeContext(), CancelTaskParams(task_id=task_id))

    assert first.result_type == "complete"
    assert requested == [task_id]
    cancelled = await store.get_task(task_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    second = await handler(ext, "tasks/cancel")(FakeContext(), CancelTaskParams(task_id=task_id))

    assert isinstance(second, GetTaskResult)
    assert second.status == "cancelled"
    assert requested == [task_id]  # no second request_cancel for a terminal task
    release.set()


# -- 7. cancelling a completed task ------------------------------------------


async def test_cancel_completed_task_returns_existing_state(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)

    async def call_next(ctx: Any) -> CallToolResult:
        return completed("already done")

    created = await ext.intercept_tool_call(tool_params(), FakeContext(), call_next)
    await ext.wait_for(created.task_id, timeout=5)  # type: ignore[union-attr]

    got = await handler(ext, "tasks/cancel")(
        FakeContext(),
        CancelTaskParams(task_id=created.task_id),  # type: ignore[union-attr]
    )

    assert isinstance(got, GetTaskResult)
    assert got.status == "completed"
    assert got.result is not None
    assert got.result["content"][0]["text"] == "already done"
    assert (await store.get_task(created.task_id)).status == "completed"  # type: ignore[union-attr]


# -- 8. version gating -------------------------------------------------------


async def test_tasks_get_rejected_on_legacy_protocol(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)
    task = await store.create_task()

    with pytest.raises(MCPError) as excinfo:
        await handler(ext, "tasks/get")(
            FakeContext(protocol_version=PROTOCOL_LEGACY), GetTaskParams(task_id=task.task_id)
        )

    assert excinfo.value.code == METHOD_NOT_FOUND
    assert all(binding.protocol_versions == frozenset({PROTOCOL_2026}) for binding in ext.methods())


async def test_tasks_methods_require_client_extension(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)
    task = await store.create_task()

    with pytest.raises(MCPError) as excinfo:
        await handler(ext, "tasks/get")(
            FakeContext(declared=False), GetTaskParams(task_id=task.task_id)
        )

    assert excinfo.value.code == MISSING_REQUIRED_CLIENT_CAPABILITY


# -- 9. tasks/update ---------------------------------------------------------


async def test_update_acknowledges_and_ignores_unknown_keys(store: SqliteTaskStore) -> None:
    ext = TasksExtension(store)
    task = await store.create_task()

    ack = await handler(ext, "tasks/update")(
        FakeContext(),
        UpdateTaskParams(
            task_id=task.task_id,
            input_responses={"unknown-key": {"action": "accept", "content": {"x": 1}}},
        ),
    )

    assert ack.result_type == "complete"
    unchanged = await store.get_task(task.task_id)
    assert unchanged is not None
    assert unchanged.status == "working"


# -- client half -------------------------------------------------------------


def claimed(status: str = "working", **kwargs: Any) -> TaskClaimedResult:
    return TaskClaimedResult(
        task_id="task-1",
        status=status,  # type: ignore[arg-type]
        created_at="2026-07-28T00:00:00+00:00",
        last_updated_at="2026-07-28T00:00:00+00:00",
        poll_interval_ms=1,
        **kwargs,
    )


class _FakeClientSession:
    """Stand-in for ``ClientSession``: replays queued ``tasks/get`` results."""

    def __init__(self, responses: list[GetTaskResult]) -> None:
        self.responses = responses
        self.requests: list[Any] = []

    async def send_request(
        self, request: Any, result_type: Any, request_read_timeout_seconds: float | None = None
    ) -> Any:
        self.requests.append(request)
        return self.responses.pop(0)


def test_task_requests_carry_the_task_id_as_the_name_param() -> None:
    assert GetTaskRequest.name_param == "taskId"
    assert UpdateTaskRequest.name_param == "taskId"
    assert CancelTaskRequest.name_param == "taskId"
    client = TasksClient()
    claim = client.claims()[0]
    assert claim.result_type == "task"
    assert claim.model is TaskClaimedResult
    assert claim.protocol_versions == frozenset({PROTOCOL_2026})


async def test_client_resolves_a_task_by_polling_tasks_get() -> None:
    session = _FakeClientSession(
        [
            GetTaskResult(
                task_id="task-1",
                status="working",
                created_at="2026-07-28T00:00:00+00:00",
                last_updated_at="2026-07-28T00:00:01+00:00",
                poll_interval_ms=1,
            ),
            GetTaskResult(
                task_id="task-1",
                status="completed",
                created_at="2026-07-28T00:00:00+00:00",
                last_updated_at="2026-07-28T00:00:02+00:00",
                poll_interval_ms=1,
                result={
                    "content": [{"type": "text", "text": "finished"}],
                    "resultType": "complete",
                },
            ),
        ]
    )
    ctx = ClaimContext(session=session, tool_name="slow_tool", read_timeout_seconds=None)  # type: ignore[arg-type]

    result = await TasksClient().resolve(claimed(), ctx)

    assert result.content[0].text == "finished"  # type: ignore[union-attr]
    assert len(session.requests) == 2
    assert isinstance(session.requests[0], GetTaskRequest)
    assert session.requests[0].params.task_id == "task-1"


async def test_client_raises_the_task_error_code() -> None:
    session = _FakeClientSession(
        [
            GetTaskResult(
                task_id="task-1",
                status="failed",
                created_at="2026-07-28T00:00:00+00:00",
                last_updated_at="2026-07-28T00:00:01+00:00",
                error={"code": INVALID_PARAMS, "message": "bad input"},
            )
        ]
    )
    ctx = ClaimContext(session=session, tool_name="slow_tool", read_timeout_seconds=None)  # type: ignore[arg-type]

    with pytest.raises(MCPError) as excinfo:
        await TasksClient().resolve(claimed(), ctx)

    assert excinfo.value.code == INVALID_PARAMS


async def test_client_raises_when_the_task_is_cancelled() -> None:
    session = _FakeClientSession(
        [
            GetTaskResult(
                task_id="task-1",
                status="cancelled",
                created_at="2026-07-28T00:00:00+00:00",
                last_updated_at="2026-07-28T00:00:01+00:00",
            )
        ]
    )
    ctx = ClaimContext(session=session, tool_name="slow_tool", read_timeout_seconds=None)  # type: ignore[arg-type]

    with pytest.raises(RemoteTaskCancelledError):
        await TasksClient().resolve(claimed(), ctx)
