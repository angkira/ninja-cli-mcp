"""SDK-free task cancellation and progress plumbing shared by all ninja servers.

MCP 2.3.0 removed the experimental task support (``mcp.shared.experimental`` and
``mcp.server.experimental``) that this module used to extend, and moved Tasks to
an opt-in protocol extension. What remains here is the part that never depended
on the SDK and that the drivers, servers and job manager still use:

* :class:`TaskCancellation` -- real interruption of running work, wired down to
  CLI subprocess groups via a contextvar.
* :func:`task_scope` -- binds a running task's cancellation and progress bridge
  to the current asyncio context.
* :func:`emit_progress` -- best-effort progress callbacks that never break a run.
* :func:`make_session_progress_callback` -- bridge those callbacks to the MCP
  ``notifications/progress`` wire notifications of a server session.

Durable task state lives in :mod:`ninja_common.mcp_ext.tasks_store`; the
extension wire models live in :mod:`ninja_common.mcp_ext.models`. For backwards
compatibility this module still re-exports the store and the process-identity
helpers.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Final

from ninja_common.mcp_ext.tasks_store import (
    DEFAULT_TASKS_DB,
    SqliteTaskStore,
    TaskStore,
    get_current_process_identity,
    get_process_start_time,
    is_process_demonstrably_dead,
)


if TYPE_CHECKING:
    from mcp.server.session import ServerSession


logger = logging.getLogger(__name__)

#: Milliseconds between progress notifications emitted from the streaming loop.
PROGRESS_INTERVAL_SECONDS: Final[float] = 10.0

#: TTL used for synthesized cancel results.
#:
#: Kept for callers that still fabricate a cancelled record for an unknown
#: task id; the Tasks extension models make ``ttl_ms`` optional, so new code
#: does not need it.
SYNTHETIC_TASK_TTL_MS: Final[int] = 60000

#: Type of a progress callback installed for a running task.
ProgressCallback = Callable[[float, float | None, str | None], Awaitable[None]]


class TaskCancelledError(Exception):
    """Raised when a task-augmented run observes a cancellation request."""


# ---------------------------------------------------------------------------
# Cancellation plumbing
# ---------------------------------------------------------------------------


def _signal_process_group(process: asyncio.subprocess.Process, sig: int) -> None:
    """Send *sig* to the process group of *process*, safely.

    Falls back to signalling only the direct child when the process shares our
    own process group (which must never be killed wholesale).
    """
    pid = process.pid
    if not pid:
        return
    try:
        pgid = os.getpgid(pid)
    except ProcessLookupError:
        return
    try:
        if pgid != os.getpgid(0):
            os.killpg(pgid, sig)
            return
    except (ProcessLookupError, PermissionError):
        pass
    try:
        process.send_signal(sig)
    except (ProcessLookupError, PermissionError, ValueError):
        pass


class TaskCancellation:
    """Cancellation state for a single running task.

    Holds an :class:`asyncio.Event` that the tool work (and the CLI subprocess
    streaming loop) observes, plus an optional handle to the subprocess so a
    cancellation can terminate the whole process group.
    """

    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self._event = asyncio.Event()
        self._process: asyncio.subprocess.Process | None = None

    @property
    def is_cancelled(self) -> bool:
        """Whether a cancellation has been requested."""
        return self._event.is_set()

    def is_set(self) -> bool:
        """Whether a cancellation has been requested (event semantics)."""
        return self._event.is_set()

    def cancel(self) -> None:
        """Mark this task as cancelled."""
        self._event.set()

    async def wait(self) -> None:
        """Block until a cancellation is requested."""
        await self._event.wait()

    def bind_process(self, process: asyncio.subprocess.Process) -> None:
        """Associate the subprocess whose group should die on cancellation."""
        self._process = process

    def unbind_process(self) -> None:
        """Forget the associated subprocess (called once the run has ended)."""
        self._process = None

    async def terminate_process(self) -> None:
        """Terminate the bound subprocess group (SIGTERM, then SIGKILL)."""
        process = self._process
        if process is None or process.returncode is not None:
            return
        logger.info("Terminating process group for cancelled task %s", self.task_id)
        _signal_process_group(process, signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), timeout=5.0)
            return
        except (TimeoutError, asyncio.CancelledError):
            pass
        logger.warning("Task %s process group ignored SIGTERM, sending SIGKILL", self.task_id)
        _signal_process_group(process, signal.SIGKILL)
        try:
            await asyncio.wait_for(process.wait(), timeout=2.0)
        except (TimeoutError, asyncio.CancelledError):
            pass


_registry_lock = threading.Lock()
_cancellations: dict[str, TaskCancellation] = {}

_current_cancellation: ContextVar[TaskCancellation | None] = ContextVar(
    "ninja_current_task_cancellation", default=None
)
_current_progress: ContextVar[ProgressCallback | None] = ContextVar(
    "ninja_current_task_progress", default=None
)


def get_task_cancellation() -> TaskCancellation | None:
    """Return the :class:`TaskCancellation` for the task in this context."""
    return _current_cancellation.get()


def get_progress_callback() -> ProgressCallback | None:
    """Return the progress callback installed for the task in this context."""
    return _current_progress.get()


def request_cancel(task_id: str) -> bool:
    """Request cancellation of a running task.

    Returns ``True`` when a live task was found and signalled, ``False`` when
    the task is unknown to this process (e.g. already finished or owned by a
    different worker).
    """
    with _registry_lock:
        cancellation = _cancellations.get(task_id)
    if cancellation is None:
        return False
    cancellation.cancel()
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return True
    loop.create_task(cancellation.terminate_process())
    return True


@asynccontextmanager
async def task_scope(
    task_id: str,
    *,
    progress: ProgressCallback | None = None,
) -> AsyncIterator[TaskCancellation]:
    """Register *task_id* for cancellation and install its progress bridge.

    While the scope is active, :func:`get_task_cancellation` and
    :func:`get_progress_callback` resolve for the current asyncio context, so
    downstream code (including the CLI driver) can observe cancellation and
    emit progress without being passed the task explicitly.
    """
    cancellation = TaskCancellation(task_id)
    with _registry_lock:
        _cancellations[task_id] = cancellation
    cancel_token = _current_cancellation.set(cancellation)
    progress_token = _current_progress.set(progress)
    try:
        yield cancellation
    finally:
        with _registry_lock:
            _cancellations.pop(task_id, None)
        _current_cancellation.reset(cancel_token)
        _current_progress.reset(progress_token)


async def emit_progress(
    current: float,
    total: float | None = None,
    message: str | None = None,
) -> bool:
    """Emit a progress notification for the current task.

    Returns ``True`` when a callback was present and completed successfully.
    Progress is strictly best-effort: failures are swallowed and never affect
    the tool run. The callback itself is installed by the caller (see
    :func:`task_scope` and :func:`make_session_progress_callback`); this module
    does not send ``notifications/progress`` on its own.
    """
    callback = _current_progress.get()
    if callback is None:
        return False
    try:
        await callback(current, total, message)
    except Exception:
        logger.debug("Task progress emission failed", exc_info=True)
        return False
    return True


def make_session_progress_callback(
    session: ServerSession, progress_token: str | int
) -> ProgressCallback:
    """Bridge :func:`emit_progress` calls to MCP ``notifications/progress``.

    The returned callback is installed through :func:`task_scope`, so any
    ``emit_progress`` call made inside the tool run reaches the client. It
    forwards to the session's ``send_progress_notification``, which exists on
    both protocol eras the SDK supports, so the same bridge works whether or not
    the client negotiated the Tasks extension.
    """

    async def _callback(
        current: float,
        total: float | None = None,
        message: str | None = None,
    ) -> None:
        await session.send_progress_notification(
            progress_token=progress_token,
            progress=current,
            total=total,
            message=message,
        )

    return _callback


__all__ = [
    "DEFAULT_TASKS_DB",
    "PROGRESS_INTERVAL_SECONDS",
    "SYNTHETIC_TASK_TTL_MS",
    "ProgressCallback",
    "SqliteTaskStore",
    "TaskCancellation",
    "TaskCancelledError",
    "TaskStore",
    "emit_progress",
    "get_current_process_identity",
    "get_process_start_time",
    "get_progress_callback",
    "get_task_cancellation",
    "is_process_demonstrably_dead",
    "make_session_progress_callback",
    "request_cancel",
    "task_scope",
]
