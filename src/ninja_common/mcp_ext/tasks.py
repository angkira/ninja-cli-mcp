"""MCP Tasks extension for 2026-07-28 servers (``io.modelcontextprotocol/tasks``).

The 2026-07-28 revision (SEP-2663) moved task-augmented execution out of the
core protocol into an opt-in extension: a client declares
``capabilities.extensions["io.modelcontextprotocol/tasks"]``, a server that
also supports it answers ``tools/call`` with a claimed ``resultType: "task"``
envelope, and the client drives the work through ``tasks/get`` /
``tasks/update`` / ``tasks/cancel``.

:class:`TasksExtension` implements the server half on top of
:class:`ninja_common.mcp_ext.tasks_store.TaskStore`:

* it intercepts ``tools/call`` and, for task-enabled tools, answers
  immediately with a durable task handle while the real handler runs in the
  background;
* it serves the three ``tasks/*`` request methods, pinned to ``2026-07-28``
  (a custom ``resultType`` cannot be delivered on an older wire, and the
  server would sieve the result away);
* it maps failures onto the extension's ``error`` field and ties cancellation
  into :func:`ninja_common.mcp_tasks.request_cancel` so a cancel actually
  reaches the running subprocess group.

Clients that never declared the extension are never handed a task handle:
the interceptor passes their calls straight through to the real handler.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from mcp.server.extension import Extension, MethodBinding
from mcp.server.mcpserver import require_client_extension
from mcp.shared.exceptions import MCPError
from mcp_types import INTERNAL_ERROR, INVALID_PARAMS, METHOD_NOT_FOUND, Result
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from ninja_common.mcp_ext.models import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_INPUT_REQUIRED,
    CancelTaskParams,
    CreateTaskResult,
    GetTaskParams,
    GetTaskResult,
    StoredResult,
    Task,
    UpdateTaskParams,
    is_terminal,
)
from ninja_common.mcp_ext.protocol import PROTOCOL_2026, TASKS_EXTENSION_ID, has_client_extension
from ninja_common.mcp_tasks import TaskCancelledError, request_cancel, task_scope


if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mcp.server.context import CallNext, HandlerResult, ServerRequestContext
    from mcp_types import CallToolRequestParams

    from ninja_common.mcp_ext.tasks_store import TaskStore


logger = logging.getLogger(__name__)

#: Wire revisions this extension serves. The claimed ``resultType`` shapes are
#: 2026-era vocabulary; on any older connection the server sieves the result and
#: the handler fails, so everything here is pinned rather than version-free.
SUPPORTED_PROTOCOL_VERSIONS: Final[frozenset[str]] = frozenset({PROTOCOL_2026})

#: Methods the extension contributes, in binding order.
TASKS_METHODS: Final[tuple[str, ...]] = ("tasks/get", "tasks/update", "tasks/cancel")


class _AckResult(Result):
    """Empty acknowledgement returned by ``tasks/update`` and ``tasks/cancel``."""

    result_type: Literal["complete"] = "complete"


class _TaskFailure(Result):
    """Persisted failure detail of a task (read back through ``tasks/get``)."""

    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)

    error: dict[str, Any]


def _jsonrpc_error(code: int, message: str, data: Any = None) -> dict[str, Any]:
    """Build the JSON-RPC error object stored on a failed task."""
    error: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return error


def _payload_of(stored: StoredResult | None) -> dict[str, Any]:
    """Return the persisted payload as a plain JSON dict."""
    if stored is None:
        return {}
    return stored.model_dump(by_alias=True, mode="json", exclude_none=True)


def _as_result_payload(result: HandlerResult) -> Result:
    """Normalise whatever ``call_next`` returned into a storable :class:`Result`."""
    if result is None:
        return StoredResult()
    if isinstance(result, BaseModel):
        # Compact wire form: the durable row keeps the payload a client would
        # see, without the nulls ``model_dump`` pads optional fields with.
        return StoredResult.model_validate(
            result.model_dump(by_alias=True, mode="json", exclude_none=True)
        )
    return StoredResult.model_validate(result)


class TasksExtension(Extension):
    """Server-side ``io.modelcontextprotocol/tasks`` implementation.

    Args:
        store: Durable task store shared with the job manager and other servers.
        task_tools: Tool names that run as tasks. ``None`` means every tool the
            server exposes runs as a task (subject to the client declaring the
            extension).
        poll_interval_ms: ``pollIntervalMs`` advertised to clients that did not
            have one persisted on the task row.
        ttl_ms: Retention of a terminal task record, in milliseconds.
        cancel_wait_seconds: How long ``tasks/cancel`` waits for the running
            work to observe the cancellation before recording ``cancelled``
            itself.
    """

    identifier = TASKS_EXTENSION_ID

    def __init__(
        self,
        store: TaskStore,
        *,
        task_tools: Iterable[str] | None = None,
        poll_interval_ms: int = 500,
        ttl_ms: int | None = None,
        cancel_wait_seconds: float = 15.0,
    ) -> None:
        if poll_interval_ms <= 0:
            raise ValueError(f"poll_interval_ms must be positive, got {poll_interval_ms}")
        if cancel_wait_seconds < 0:
            raise ValueError(f"cancel_wait_seconds must be non-negative, got {cancel_wait_seconds}")
        self._store = store
        self._task_tools = frozenset(task_tools) if task_tools is not None else None
        self._poll_interval_ms = poll_interval_ms
        self._ttl_ms = ttl_ms
        self._cancel_wait_seconds = cancel_wait_seconds
        # Strong references keep detached work alive; asyncio only holds weak ones.
        self._running: set[asyncio.Task[None]] = set()
        self._handles: dict[str, asyncio.Task[None]] = {}
        self._completed: dict[str, asyncio.Event] = {}
        # Keys a task is waiting on, and the responses accepted for them. No
        # flow in this revision raises ``input_required``, so both stay empty
        # and ``tasks/update`` ignores every supplied key (spec: unknown keys
        # are ignored).
        self._input_requests: dict[str, set[str]] = {}
        self._input_responses: dict[str, dict[str, Any]] = {}

    # -- Extension surface ---------------------------------------------------

    def settings(self) -> dict[str, Any]:
        """Advertise the extension with no settings."""
        return {}

    def methods(self) -> Sequence[MethodBinding]:
        """Bind ``tasks/get``, ``tasks/update`` and ``tasks/cancel`` at 2026-07-28."""
        return (
            MethodBinding(
                method="tasks/get",
                params_type=GetTaskParams,
                handler=self._handle_get,
                protocol_versions=SUPPORTED_PROTOCOL_VERSIONS,
            ),
            MethodBinding(
                method="tasks/update",
                params_type=UpdateTaskParams,
                handler=self._handle_update,
                protocol_versions=SUPPORTED_PROTOCOL_VERSIONS,
            ),
            MethodBinding(
                method="tasks/cancel",
                params_type=CancelTaskParams,
                handler=self._handle_cancel,
                protocol_versions=SUPPORTED_PROTOCOL_VERSIONS,
            ),
        )

    # -- tools/call interception ---------------------------------------------

    async def intercept_tool_call(
        self,
        params: CallToolRequestParams,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> HandlerResult:
        """Run an eligible tool as a durable task instead of inline.

        Ineligible calls (client did not declare the extension, the tool is not
        task-enabled, or the connection negotiated a revision that cannot carry
        a claimed ``resultType``) pass through untouched.
        """
        if not has_client_extension(ctx, self.identifier):
            return await call_next(ctx)
        if ctx.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            return await call_next(ctx)
        if self._task_tools is not None and params.name not in self._task_tools:
            return await call_next(ctx)

        task = await self._store.create_task(ttl_ms=self._ttl_ms)
        background = asyncio.create_task(
            self._execute(task.task_id, ctx, call_next),
            name=f"mcp-task-{task.task_id}",
        )
        self._running.add(background)
        self._handles[task.task_id] = background
        background.add_done_callback(self._running.discard)
        logger.info("Task %s created for tool %r", task.task_id, params.name)
        return await self.create_task_result(task)

    # -- method handlers -----------------------------------------------------

    async def _handle_get(
        self, ctx: ServerRequestContext[Any, Any], params: GetTaskParams
    ) -> GetTaskResult:
        """Return the state of one task, including its payload or failure."""
        self._require_support(ctx)
        task = await self._store.get_task(params.task_id)
        if task is None:
            raise self._unknown_task(params.task_id)
        return await self.get_task_result(task)

    async def _handle_update(
        self, ctx: ServerRequestContext[Any, Any], params: UpdateTaskParams
    ) -> _AckResult:
        """Accept client input responses; responses to unknown keys are ignored."""
        self._require_support(ctx)
        task = await self._store.get_task(params.task_id)
        if task is None:
            raise self._unknown_task(params.task_id)

        known = self._input_requests.get(task.task_id, set())
        accepted = {key: value for key, value in params.input_responses.items() if key in known}
        ignored = sorted(set(params.input_responses) - set(accepted))
        if accepted:
            pending = self._input_responses.setdefault(task.task_id, {})
            pending.update(accepted)
            self._input_requests[task.task_id] = known - set(accepted)
        if ignored:
            logger.debug("Task %s: ignoring responses for unknown keys %s", task.task_id, ignored)
        return _AckResult()

    async def _handle_cancel(
        self, ctx: ServerRequestContext[Any, Any], params: CancelTaskParams
    ) -> Result:
        """Cooperatively cancel a task; idempotent for terminal tasks.

        A terminal task is never an error: the current state is returned so the
        client sees *why* nothing was cancelled.
        """
        self._require_support(ctx)
        task = await self._store.get_task(params.task_id)
        if task is None:
            raise self._unknown_task(params.task_id)
        if is_terminal(task.status):
            return await self.get_task_result(task)

        request_cancel(task.task_id)
        current = await self._wait_terminal(task.task_id, self._cancel_wait_seconds)
        if current is None:
            raise self._unknown_task(params.task_id)
        if not is_terminal(current.status):
            current = await self._store.update_task(
                task.task_id,
                TASK_STATUS_CANCELLED,
                "Cancelled by client request",
            )
        # The cooperative signal was not observed in time; stop the detached
        # work so it cannot keep consuming the process after the client gave up.
        handle = self._handles.get(task.task_id)
        if handle is not None and not handle.done():
            handle.cancel()
        logger.info("Task %s cancelled (status=%s)", task.task_id, current.status)
        return _AckResult()

    # -- result shaping ------------------------------------------------------

    async def create_task_result(self, task: Task) -> CreateTaskResult:
        """Build the ``resultType: "task"`` envelope returned by ``tools/call``."""
        return CreateTaskResult(**self._task_fields(task))

    async def get_task_result(self, task: Task) -> GetTaskResult:
        """Build the ``tasks/get`` result for *task*, status field included."""
        fields = self._task_fields(task)
        payload = _payload_of(await self._store.get_result(task.task_id))

        if task.status == TASK_STATUS_COMPLETED:
            return GetTaskResult(**fields, result=payload)
        if task.status == TASK_STATUS_FAILED:
            raw_error = payload.get("error")
            error = (
                cast("dict[str, Any]", raw_error)
                if isinstance(raw_error, dict)
                else _jsonrpc_error(
                    INTERNAL_ERROR, task.status_message or "Task failed without an error object"
                )
            )
            return GetTaskResult(**fields, error=error)
        if task.status == TASK_STATUS_INPUT_REQUIRED:
            raw_requests = payload.get("inputRequests")
            input_requests = (
                cast("dict[str, Any]", raw_requests) if isinstance(raw_requests, dict) else {}
            )
            return GetTaskResult(**fields, input_requests=input_requests)
        return GetTaskResult(**fields)

    def _task_fields(self, task: Task) -> dict[str, Any]:
        """Task fields shaped for the wire, with the advertised poll interval."""
        return {
            "task_id": task.task_id,
            "status": task.status,
            "status_message": task.status_message,
            "created_at": task.created_at,
            "last_updated_at": task.last_updated_at,
            "ttl_ms": task.ttl_ms,
            "poll_interval_ms": (
                task.poll_interval_ms
                if task.poll_interval_ms is not None
                else self._poll_interval_ms
            ),
        }

    # -- background execution ------------------------------------------------

    async def _execute(
        self,
        task_id: str,
        ctx: ServerRequestContext[Any, Any],
        call_next: CallNext,
    ) -> None:
        """Run the real tool handler for *task_id* and record its outcome."""
        try:
            try:
                async with task_scope(task_id):
                    result = await call_next(ctx)
            except TaskCancelledError:
                logger.info("Task %s observed its cancellation", task_id)
                await self._mark_cancelled(task_id)
            except MCPError as exc:
                await self._fail(task_id, _jsonrpc_error(exc.code, exc.message, exc.data))
            except asyncio.CancelledError:
                await self._mark_cancelled(task_id)
                raise
            except Exception as exc:
                logger.exception("Task %s failed", task_id)
                await self._fail(
                    task_id,
                    _jsonrpc_error(INTERNAL_ERROR, str(exc) or type(exc).__name__),
                )
            else:
                await self._complete(task_id, result)
        finally:
            current = asyncio.current_task()
            if current is not None:
                self._running.discard(current)
            if self._handles.get(task_id) is current:
                self._handles.pop(task_id, None)
            self._signal_completion(task_id)

    async def _complete(self, task_id: str, result: HandlerResult) -> None:
        """Persist *result* and mark *task_id* ``completed``."""
        try:
            await self._store.store_result(task_id, _as_result_payload(result))
        except ValueError:
            logger.warning("Task %s vanished before its result was stored", task_id)
            return
        await self._store.update_task(task_id, TASK_STATUS_COMPLETED)
        logger.info("Task %s completed", task_id)

    async def _fail(self, task_id: str, error: dict[str, Any]) -> None:
        """Persist *error* (a JSON-RPC error object) and mark the task failed."""
        try:
            await self._store.store_result(task_id, _TaskFailure(error=error))
        except ValueError:
            logger.warning("Task %s vanished before its failure was stored", task_id)
            return
        message = error.get("message")
        await self._store.update_task(
            task_id,
            TASK_STATUS_FAILED,
            message if isinstance(message, str) else None,
        )
        logger.info("Task %s failed: %s", task_id, message)

    async def _mark_cancelled(self, task_id: str) -> None:
        """Mark *task_id* ``cancelled`` (no-op once terminal)."""
        task = await self._store.get_task(task_id)
        if task is None or is_terminal(task.status):
            return
        await self._store.update_task(task_id, TASK_STATUS_CANCELLED, "Cancelled")

    # -- helpers -------------------------------------------------------------

    def _require_support(self, ctx: ServerRequestContext[Any, Any]) -> None:
        """Gate a ``tasks/*`` handler on the wire revision and the client declaration."""
        if ctx.protocol_version not in SUPPORTED_PROTOCOL_VERSIONS:
            raise MCPError(code=METHOD_NOT_FOUND, message="Method not found")
        require_client_extension(ctx, self.identifier)

    @staticmethod
    def _unknown_task(task_id: str) -> MCPError:
        """The ``-32602`` error for an unknown or expired task id."""
        return MCPError(code=INVALID_PARAMS, message=f"Unknown task: {task_id}", data=task_id)

    async def _wait_terminal(self, task_id: str, timeout: float) -> Task | None:
        """Poll until *task_id* is terminal or *timeout* seconds elapsed."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        interval = self._poll_interval_ms / 1000
        while True:
            task = await self._store.get_task(task_id)
            if task is None or is_terminal(task.status):
                return task
            remaining = deadline - loop.time()
            if remaining <= 0:
                return task
            await asyncio.sleep(min(interval, remaining))

    def _signal_completion(self, task_id: str) -> None:
        """Wake :meth:`wait_for` waiters of *task_id*."""
        event = self._completed.pop(task_id, None)
        if event is not None:
            event.set()

    async def wait_for(self, task_id: str, timeout: float | None = None) -> Task:
        """Await the terminal record of *task_id* (tests and shutdown hooks).

        Raises:
            KeyError: No such task exists in the store.
            TimeoutError: The task did not reach a terminal state in time.
        """
        task = await self._store.get_task(task_id)
        if task is None:
            raise KeyError(f"Unknown task: {task_id}")
        if not is_terminal(task.status):
            event = self._completed.setdefault(task_id, asyncio.Event())
            # Re-check after registering: the run may have finished in between,
            # in which case its completion signal was already delivered.
            task = await self._store.get_task(task_id)
            if task is None:
                raise KeyError(f"Unknown task: {task_id}")
            if not is_terminal(task.status):
                await asyncio.wait_for(event.wait(), timeout)
        final = await self._store.get_task(task_id)
        if final is None:
            raise KeyError(f"Unknown task: {task_id}")
        return final


__all__ = [
    "SUPPORTED_PROTOCOL_VERSIONS",
    "TASKS_METHODS",
    "TasksExtension",
]
