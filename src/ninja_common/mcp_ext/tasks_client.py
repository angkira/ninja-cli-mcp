"""Client side of the MCP Tasks extension (``io.modelcontextprotocol/tasks``).

A client that declares the extension receives a claimed ``resultType: "task"``
envelope instead of the tool's ordinary result. :class:`TasksClient` teaches
``Client(extensions=[...])`` how to finish that call: the resolver polls
``tasks/get`` at the advertised ``pollIntervalMs`` until the task is terminal
and then hands back the stored ``CallToolResult``.

The request models below carry ``name_param = "taskId"`` because SEP-2663
requires the task id in the ``Mcp-Name`` header; the SDK mirrors that parameter
into the header on send.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Final, Literal

from mcp.client.extension import ClaimContext, ClientExtension, ResultClaim
from mcp.shared.exceptions import MCPError
from mcp_types import CallToolResult, Request, Result
from pydantic import ConfigDict
from pydantic.alias_generators import to_camel

from ninja_common.mcp_ext.models import (
    CancelTaskParams,
    CreateTaskResult,
    GetTaskParams,
    GetTaskResult,
    TaskStatus,
    UpdateTaskParams,
    is_terminal,
)
from ninja_common.mcp_ext.protocol import PROTOCOL_2026, TASKS_EXTENSION_ID


if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcp.client.session import ClientSession


#: Poll interval used when the server does not advertise one.
DEFAULT_POLL_INTERVAL_MS: Final[int] = 500

#: The claimed ``resultType`` tag carrying a task handle.
TASK_RESULT_TYPE: Final[str] = "task"

#: Wire revisions that can carry a claimed result; pinned for the same reason
#: the extension's methods are.
SUPPORTED_PROTOCOL_VERSIONS: Final[frozenset[str]] = frozenset({PROTOCOL_2026})


class TaskClaimedResult(CreateTaskResult):
    """The ``resultType: "task"`` claim model for a task-augmented ``tools/call``.

    Wire-identical to the server's :class:`~ninja_common.mcp_ext.models.CreateTaskResult`;
    subclassing it keeps a single definition of the task fields.
    """


class GetTaskRequest(Request[GetTaskParams, Literal["tasks/get"]]):
    """``tasks/get`` request, name-bearing for the ``Mcp-Name`` header."""

    method: Literal["tasks/get"] = "tasks/get"
    params: GetTaskParams

    name_param = "taskId"


class UpdateTaskRequest(Request[UpdateTaskParams, Literal["tasks/update"]]):
    """``tasks/update`` request carrying client input responses."""

    method: Literal["tasks/update"] = "tasks/update"
    params: UpdateTaskParams

    name_param = "taskId"


class CancelTaskRequest(Request[CancelTaskParams, Literal["tasks/cancel"]]):
    """``tasks/cancel`` request."""

    method: Literal["tasks/cancel"] = "tasks/cancel"
    params: CancelTaskParams

    name_param = "taskId"


class _AckResult(Result):
    """Server acknowledgement, tolerant of the terminal task state a cancel returns."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="allow")

    result_type: Literal["complete"] = "complete"


class TasksClientError(RuntimeError):
    """Base class for client-side task failures."""

    def __init__(self, task_id: str, message: str) -> None:
        super().__init__(f"Task {task_id}: {message}")
        self.task_id = task_id


class RemoteTaskFailedError(TasksClientError):
    """The task failed with a payload that is not a usable JSON-RPC error object."""

    def __init__(self, task_id: str, error: dict[str, Any]) -> None:
        super().__init__(task_id, str(error.get("message") or "task failed"))
        self.error = error


class RemoteTaskCancelledError(TasksClientError):
    """The task ended ``cancelled`` before it produced a result."""

    def __init__(self, task_id: str) -> None:
        super().__init__(task_id, "task was cancelled")


class RemoteTaskTimeoutError(TasksClientError):
    """The task did not reach a terminal state within the client's budget."""

    def __init__(self, task_id: str, timeout_seconds: float, status: TaskStatus) -> None:
        super().__init__(
            task_id, f"still {status!r} after {timeout_seconds:g}s (polling timed out)"
        )
        self.status = status


async def fetch_task(
    session: ClientSession,
    task_id: str,
    *,
    read_timeout_seconds: float | None = None,
) -> GetTaskResult:
    """Send one ``tasks/get`` for *task_id*."""
    return await session.send_request(
        GetTaskRequest(params=GetTaskParams(task_id=task_id)),
        GetTaskResult,
        request_read_timeout_seconds=read_timeout_seconds,
    )


async def update_task(
    session: ClientSession,
    task_id: str,
    input_responses: dict[str, Any],
    *,
    read_timeout_seconds: float | None = None,
) -> None:
    """Send one ``tasks/update`` carrying *input_responses*."""
    await session.send_request(
        UpdateTaskRequest(
            params=UpdateTaskParams(task_id=task_id, input_responses=input_responses)
        ),
        _AckResult,
        request_read_timeout_seconds=read_timeout_seconds,
    )


async def cancel_task(
    session: ClientSession,
    task_id: str,
    *,
    read_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Send one ``tasks/cancel``.

    Returns the acknowledgement as a plain dict. For a task that was already
    terminal the server mirrors its state back, so ``status`` is present.
    """
    ack = await session.send_request(
        CancelTaskRequest(params=CancelTaskParams(task_id=task_id)),
        _AckResult,
        request_read_timeout_seconds=read_timeout_seconds,
    )
    return ack.model_dump(by_alias=True, mode="json", exclude_none=True)


def _raise_task_error(task_id: str, error: dict[str, Any]) -> None:
    """Raise the client-side failure for a task's stored JSON-RPC error object."""
    code = error.get("code")
    message = error.get("message")
    if isinstance(code, int) and isinstance(message, str):
        raise MCPError(code=code, message=message, data=error.get("data"))
    raise RemoteTaskFailedError(task_id, error)


class TasksClient(ClientExtension):
    """Resolve task handles into real tool results by polling ``tasks/get``.

    Args:
        poll_interval_ms: Override the server's advertised ``pollIntervalMs``.
        timeout_seconds: Give up after this long; ``None`` polls until the task
            reaches a terminal state.
    """

    identifier = TASKS_EXTENSION_ID

    def __init__(
        self,
        *,
        poll_interval_ms: int | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        if poll_interval_ms is not None and poll_interval_ms <= 0:
            raise ValueError(f"poll_interval_ms must be positive, got {poll_interval_ms}")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError(f"timeout_seconds must be positive, got {timeout_seconds}")
        self._poll_interval_ms = poll_interval_ms
        self._timeout_seconds = timeout_seconds

    def claims(self) -> Sequence[ResultClaim[TaskClaimedResult]]:
        """Claim ``resultType: "task"`` on ``tools/call``."""
        claim: ResultClaim[TaskClaimedResult] = ResultClaim(
            result_type=TASK_RESULT_TYPE,
            model=TaskClaimedResult,
            resolve=self.resolve,
            protocol_versions=SUPPORTED_PROTOCOL_VERSIONS,
        )
        return (claim,)

    async def resolve(self, claimed: TaskClaimedResult, ctx: ClaimContext) -> CallToolResult:
        """Poll *claimed* until terminal and return the stored tool result.

        Raises:
            MCPError: The task failed and its ``error`` object is JSON-RPC shaped.
            RemoteTaskFailedError: The task failed with a malformed error object.
            RemoteTaskCancelledError: The task was cancelled before completing.
            RemoteTaskTimeoutError: ``timeout_seconds`` elapsed while polling.
        """
        # The claim carries ``resultType: "task"``; ``tasks/get`` answers with
        # ``"complete"``, so drop the tag and map the shared task fields across.
        fields = claimed.model_dump(by_alias=True, mode="json")
        fields.pop("resultType", None)
        state = GetTaskResult.model_validate(fields)
        loop = asyncio.get_running_loop()
        deadline = None if self._timeout_seconds is None else loop.time() + self._timeout_seconds

        while not is_terminal(state.status):
            if deadline is not None and loop.time() >= deadline:
                raise RemoteTaskTimeoutError(
                    state.task_id, self._timeout_seconds or 0.0, state.status
                )
            advertised = self._poll_interval_ms or state.poll_interval_ms
            interval = (advertised or DEFAULT_POLL_INTERVAL_MS) / 1000
            if deadline is not None:
                interval = min(interval, max(deadline - loop.time(), 0.0))
            await asyncio.sleep(interval)
            state = await fetch_task(
                ctx.session,
                state.task_id,
                read_timeout_seconds=ctx.read_timeout_seconds,
            )

        if state.status == "completed":
            payload = state.result or {}
            if not payload:
                return CallToolResult(content=[])
            return CallToolResult.model_validate(payload)
        if state.status == "failed":
            _raise_task_error(state.task_id, state.error or {})
        raise RemoteTaskCancelledError(state.task_id)


__all__ = [
    "DEFAULT_POLL_INTERVAL_MS",
    "SUPPORTED_PROTOCOL_VERSIONS",
    "TASK_RESULT_TYPE",
    "CancelTaskRequest",
    "GetTaskRequest",
    "RemoteTaskCancelledError",
    "RemoteTaskFailedError",
    "RemoteTaskTimeoutError",
    "TaskClaimedResult",
    "TasksClient",
    "TasksClientError",
    "UpdateTaskRequest",
    "cancel_task",
    "fetch_task",
    "update_task",
]
