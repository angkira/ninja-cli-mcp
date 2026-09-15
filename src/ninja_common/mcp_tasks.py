"""Production-grade MCP Tasks infrastructure shared by all ninja MCP servers.

The MCP SDK (``mcp==1.24.x``) ships experimental task support with an
in-memory store and a status helper. This module closes the gaps needed to run
the feature in production:

* :class:`SqliteTaskStore` -- durable, process-shared task state (WAL,
  thread-safe) that survives restarts and is visible across sessions.
* :class:`TaskCancellation` -- real interruption of running work, wired down to
  CLI subprocess groups via a contextvar.
* :func:`task_scope` -- binds a running task's cancellation and progress bridge
  to the current asyncio context.
* :func:`install_tasks` -- one-call server wiring with a robust cancel handler
  that also interrupts the in-flight work.
* :func:`emit_progress` -- best-effort ``notifications/progress`` emission that
  never breaks a run.

Nothing in this module patches the installed SDK; it only extends the public
experimental ``TaskStore`` / ``TaskMessageQueue`` protocols and the
``server.experimental`` handler decorators.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sqlite3
import threading
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

import anyio
from mcp.shared.exceptions import McpError
from mcp.shared.experimental.tasks.helpers import cancel_task, create_task_state, is_terminal
from mcp.shared.experimental.tasks.message_queue import InMemoryTaskMessageQueue
from mcp.shared.experimental.tasks.store import TaskStore
from mcp.types import (
    TASK_STATUS_CANCELLED,
    CancelTaskRequest,
    CancelTaskResult,
    Result,
    Task,
)


if TYPE_CHECKING:
    from mcp.server.experimental.task_context import ServerTaskContext
    from mcp.server.experimental.task_support import TaskSupport
    from mcp.server.lowlevel.server import Server
    from mcp.server.session import ServerSession
    from mcp.shared.experimental.tasks.message_queue import TaskMessageQueue
    from mcp.types import TaskMetadata, TaskStatus


logger = logging.getLogger(__name__)

#: Default on-disk location for durable task state.
DEFAULT_TASKS_DB: Final[str] = "~/.ninja/tasks.db"

#: Milliseconds between progress notifications emitted from the streaming loop.
PROGRESS_INTERVAL_SECONDS: Final[float] = 10.0

#: TTL used for synthesized cancel results. The SDK serializes responses with
#: ``exclude_none=True`` while ``Task.ttl`` is required on the client, so a
#: response carrying a null TTL fails client-side validation. A concrete value
#: keeps idempotent cancels of unknown tasks valid.
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
    the tool run.
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
    session: ServerSession,
    progress_token: str | int,
) -> ProgressCallback:
    """Build a callback that sends ``notifications/progress`` via *session*."""

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


@asynccontextmanager
async def server_task_scope(
    task: ServerTaskContext,
    *,
    session: ServerSession,
    progress_token: str | int | None = None,
) -> AsyncIterator[TaskCancellation]:
    """Bind a :class:`ServerTaskContext` to cancellation and progress.

    The session and progress token are captured by the caller while the request
    context is still active, so this never depends on request-context
    propagation into the SDK's background task group.
    """
    token = progress_token if progress_token is not None else task.task_id
    callback = make_session_progress_callback(session, token)
    async with task_scope(task.task_id, progress=callback) as cancellation:
        yield cancellation


async def refresh_task_after_cancel(task: ServerTaskContext) -> None:
    """Synchronise the task context with a terminal ``cancelled`` store state.

    The SDK's ``run_task`` auto-completes work by inspecting its locally cached
    ``Task`` object. When a cancellation raced with the work, that cache is
    stale and the SDK would try to transition a terminal task, raising and
    tearing down task support. Refreshing the cached status from the store makes
    the SDK skip the completion. Best-effort and never fatal.
    """
    try:
        await task.update_status("cancelled")
    except Exception:
        logger.debug("Failed to refresh cancelled task %s", task.task_id, exc_info=True)


# ---------------------------------------------------------------------------
# Durable task store
# ---------------------------------------------------------------------------


def _resolve_db_path(db_path: str | Path | None) -> str:
    """Resolve the SQLite path, honouring ``NINJA_TASKS_DB`` and ``:memory:``."""
    raw = (
        str(db_path) if db_path is not None else os.environ.get("NINJA_TASKS_DB", DEFAULT_TASKS_DB)
    )
    if raw == ":memory:" or raw.startswith("file::memory:"):
        return raw
    return str(Path(raw).expanduser())


def _expiry_iso(ttl_ms: int | None) -> str | None:
    """Return the ISO expiry timestamp for a TTL in milliseconds."""
    if ttl_ms is None:
        return None
    return (datetime.now(UTC) + timedelta(milliseconds=ttl_ms)).isoformat()


_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS tasks (
    task_id         TEXT PRIMARY KEY,
    status          TEXT NOT NULL,
    status_message  TEXT,
    created_at      TEXT NOT NULL,
    last_updated_at TEXT NOT NULL,
    ttl             INTEGER,
    poll_interval   INTEGER,
    result_json     TEXT,
    expires_at      TEXT
)
"""


class SqliteTaskStore(TaskStore):
    """Durable :class:`TaskStore` backed by SQLite.

    Tasks survive process restarts and are shared across sessions and servers
    that point at the same database file (default ``~/.ninja/tasks.db``,
    overridable with ``NINJA_TASKS_DB``). Structured fields are JSON-encoded;
    WAL mode plus a threading lock make access safe from the event loop and
    worker threads. A ``:memory:`` path is supported for tests.
    """

    def __init__(self, db_path: str | Path | None = None, *, page_size: int = 10) -> None:
        self._db_path = _resolve_db_path(db_path)
        self._page_size = page_size
        self._lock = threading.Lock()
        self._update_events: dict[str, anyio.Event] = {}
        if self._db_path != ":memory:" and not self._db_path.startswith("file::memory:"):
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Wait out short write locks instead of failing when several store
        # instances (servers/sessions) share the same file.
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._init_schema()

    # -- internals ----------------------------------------------------------

    def _init_schema(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute(_SCHEMA)

    def _purge_expired_locked(self) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task.model_validate(
            {
                "taskId": row["task_id"],
                "status": row["status"],
                "statusMessage": row["status_message"],
                "createdAt": row["created_at"],
                "lastUpdatedAt": row["last_updated_at"],
                "ttl": row["ttl"],
                "pollInterval": row["poll_interval"],
            }
        )

    def _fetch_locked(self, task_id: str) -> sqlite3.Row | None:
        self._purge_expired_locked()
        cursor = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        return cast("sqlite3.Row | None", cursor.fetchone())

    # -- TaskStore protocol -------------------------------------------------

    async def create_task(
        self,
        metadata: TaskMetadata,
        task_id: str | None = None,
    ) -> Task:
        task = create_task_state(metadata, task_id)
        with self._lock, self._conn:
            self._purge_expired_locked()
            try:
                self._conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, status, status_message, created_at,
                        last_updated_at, ttl, poll_interval, result_json, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.taskId,
                        task.status,
                        task.statusMessage,
                        task.createdAt.isoformat(),
                        task.lastUpdatedAt.isoformat(),
                        task.ttl,
                        task.pollInterval,
                        None,
                        _expiry_iso(task.ttl),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Task with ID {task.taskId} already exists") from exc
        return task

    async def get_task(self, task_id: str) -> Task | None:
        # ``with self._conn`` commits the lazy-expiry DELETE so reads never
        # leave a write transaction open (which would lock other instances).
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
        if row is None:
            return None
        return self._row_to_task(row)

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        status_message: str | None = None,
    ) -> Task:
        status_changed = False
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
            if row is None:
                raise ValueError(f"Task with ID {task_id} not found")
            current = self._row_to_task(row)

            new_status = current.status
            if status is not None and status != current.status:
                if is_terminal(current.status):
                    # Terminal states MUST NOT transition. The SDK can race a
                    # cancellation against auto-completion; swallow that race
                    # (log it) instead of raising inside the background task
                    # group, which would tear down task support.
                    logger.warning(
                        "Ignoring transition of terminal task %s (%s -> %s)",
                        task_id,
                        current.status,
                        status,
                    )
                    return current
                new_status = status
                status_changed = True

            new_message = status_message if status_message is not None else current.statusMessage
            now = datetime.now(UTC)
            expires_at = row["expires_at"]
            if is_terminal(new_status) and current.ttl is not None:
                expires_at = _expiry_iso(current.ttl)
            self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, status_message = ?, last_updated_at = ?, expires_at = ?
                WHERE task_id = ?
                """,
                (new_status, new_message, now.isoformat(), expires_at, task_id),
            )
            updated = Task.model_validate(
                {
                    "taskId": task_id,
                    "status": new_status,
                    "statusMessage": new_message,
                    "createdAt": current.createdAt,
                    "lastUpdatedAt": now,
                    "ttl": current.ttl,
                    "pollInterval": current.pollInterval,
                }
            )
        if status_changed:
            await self.notify_update(task_id)
        return updated

    async def store_result(self, task_id: str, result: Result) -> None:
        payload = json.dumps(result.model_dump(mode="json", by_alias=True))
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
            if row is None:
                raise ValueError(f"Task with ID {task_id} not found")
            self._conn.execute(
                "UPDATE tasks SET result_json = ? WHERE task_id = ?",
                (payload, task_id),
            )

    async def get_result(self, task_id: str) -> Result | None:
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
        if row is None:
            return None
        raw = row["result_json"]
        if raw is None:
            return None
        return Result.model_validate(json.loads(raw))

    async def list_tasks(
        self,
        cursor: str | None = None,
    ) -> tuple[list[Task], str | None]:
        with self._lock, self._conn:
            self._purge_expired_locked()
            rows = self._conn.execute(
                "SELECT task_id FROM tasks ORDER BY created_at, rowid"
            ).fetchall()
        task_ids = [str(row["task_id"]) for row in rows]

        start_index = 0
        if cursor is not None:
            try:
                start_index = task_ids.index(cursor) + 1
            except ValueError as exc:
                raise ValueError(f"Invalid cursor: {cursor}") from exc

        page_ids = task_ids[start_index : start_index + self._page_size]
        tasks: list[Task] = []
        for task_id in page_ids:
            task = await self.get_task(task_id)
            if task is not None:
                tasks.append(task)

        next_cursor: str | None = None
        if page_ids and start_index + self._page_size < len(task_ids):
            next_cursor = page_ids[-1]
        return tasks, next_cursor

    async def delete_task(self, task_id: str) -> bool:
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            return cursor.rowcount > 0

    async def wait_for_update(self, task_id: str) -> None:
        if await self.get_task(task_id) is None:
            raise ValueError(f"Task with ID {task_id} not found")
        event = anyio.Event()
        self._update_events[task_id] = event
        await event.wait()

    async def notify_update(self, task_id: str) -> None:
        event = self._update_events.get(task_id)
        if event is not None:
            event.set()


# ---------------------------------------------------------------------------
# Server wiring
# ---------------------------------------------------------------------------


def install_tasks(
    server: Server,
    *,
    store: TaskStore | None = None,
    queue: TaskMessageQueue | None = None,
) -> TaskSupport:
    """Enable standard MCP Tasks with durable state and real cancellation.

    Wires the durable store and in-memory message queue into the SDK, then
    overrides the ``tasks/cancel`` handler so that cancelling a task both marks
    it cancelled in the store and interrupts the running work (including the
    CLI subprocess group).
    """
    task_store = store if store is not None else SqliteTaskStore()
    task_queue = queue if queue is not None else InMemoryTaskMessageQueue()
    support = server.experimental.enable_tasks(store=task_store, queue=task_queue)

    @server.experimental.cancel_task()
    async def _handle_cancel(request: CancelTaskRequest) -> CancelTaskResult:
        task_id = request.params.taskId
        # Always stop any live work for this id, even if the store says the
        # task is already terminal (the worker may still be winding down).
        request_cancel(task_id)
        try:
            return await cancel_task(task_store, task_id)
        except McpError:
            # Already-terminal or unknown task: cancellation is idempotent and
            # must never raise. Report the terminal state when we have it, and a
            # synthetic cancelled result otherwise.
            existing = await task_store.get_task(task_id)
            if existing is not None:
                data = existing.model_dump()
                if data.get("ttl") is None:
                    data["ttl"] = SYNTHETIC_TASK_TTL_MS
                return CancelTaskResult(**data)
            logger.info("Cancel requested for unknown task %s (no-op)", task_id)
            now = datetime.now(UTC)
            return CancelTaskResult(
                taskId=task_id,
                status=TASK_STATUS_CANCELLED,
                createdAt=now,
                lastUpdatedAt=now,
                ttl=SYNTHETIC_TASK_TTL_MS,
            )

    return support


__all__ = [
    "DEFAULT_TASKS_DB",
    "ProgressCallback",
    "SqliteTaskStore",
    "TaskCancellation",
    "TaskCancelledError",
    "emit_progress",
    "get_progress_callback",
    "get_task_cancellation",
    "install_tasks",
    "make_session_progress_callback",
    "refresh_task_after_cancel",
    "request_cancel",
    "server_task_scope",
    "task_scope",
]
