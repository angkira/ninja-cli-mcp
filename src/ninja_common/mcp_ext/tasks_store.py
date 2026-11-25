"""Durable, process-shared task store for the MCP Tasks extension.

This is the SDK-free replacement for the in-memory task store that the MCP
experimental task support used to provide. It stores tasks in SQLite (WAL mode,
thread-safe, shared across sessions and processes that point at the same file)
and exposes the same behaviours the servers rely on: creation, status
transitions with a terminal-state guard, result storage, pagination,
cancellation wake-ups and stale-owner reconciliation.

Tasks are returned as :class:`ninja_common.mcp_ext.models.Task` objects; the
database keeps snake_case columns and the models serialize to camelCase.
"""

from __future__ import annotations

import json
import logging
import math
import os
import sqlite3
import threading
import time
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol, cast

import anyio
import psutil

from ninja_common.mcp_ext.models import (
    TASK_STATUS_FAILED,
    TASK_STATUS_WORKING,
    StoredResult,
    Task,
    TaskStatus,
    is_terminal,
)


if TYPE_CHECKING:
    from mcp_types import Result


logger = logging.getLogger(__name__)

#: Default on-disk location for durable task state.
DEFAULT_TASKS_DB: Final[str] = "~/.ninja/tasks.db"


def get_process_start_time(pid: int) -> float | None:
    """Return the start time (epoch timestamp) of *pid*, or None if unavailable."""
    try:
        proc = psutil.Process(pid)
        return float(proc.create_time())
    except (psutil.NoSuchProcess, psutil.ZombieProcess):
        return None
    except Exception as exc:
        logger.debug("Failed to inspect process %d: %s", pid, exc)
        return None


def get_current_process_identity() -> tuple[int, str]:
    """Return (pid, start_token) for the current process."""
    pid = os.getpid()
    create_time = get_process_start_time(pid)
    token = f"{create_time:.6f}" if create_time is not None else "unknown"
    return pid, token


def is_process_demonstrably_dead(pid: int | None, token: str | None) -> bool:
    """Determine if a process is demonstrably dead.

    Returns True ONLY if we can prove the process is dead.
    Returns False if the process is alive, or if ownership is legacy/unknown,
    or if inspection is inconclusive.
    """
    if pid is None or pid <= 0 or not token or token == "unknown":
        # Legacy or unknown ownership: do not guess dead.
        return False

    try:
        proc = psutil.Process(pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return True
        create_time = proc.create_time()
    except (psutil.NoSuchProcess, ProcessLookupError):
        # Process does not exist in the OS -> demonstrably dead.
        return True
    except (psutil.AccessDenied, PermissionError):
        # Process exists but we lack permission to inspect create_time.
        # It is either a live system process or foreign process: never guess dead!
        return False
    except Exception as exc:
        logger.debug("Error probing process %d: %s", pid, exc)
        return False

    # Process exists. Check if PID was reused by comparing start token.
    try:
        expected_time = float(token)
        if not math.isfinite(expected_time):
            return False
    except (ValueError, TypeError):
        return False

    return bool(abs(create_time - expected_time) >= 0.05)


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
    expires_at      TEXT,
    owner_pid       INTEGER,
    owner_token     TEXT
)
"""

_SENTINEL_OWNER: Final[object] = object()


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


class TaskStore(Protocol):
    """Structural contract for durable task stores.

    Mirrors the store surface the servers and the job manager use. Retained as
    a protocol so tests and future backends (in-memory, remote) can substitute
    for :class:`SqliteTaskStore` without inheritance.
    """

    async def create_task(self, task_id: str | None = None, ttl_ms: int | None = None) -> Task:
        """Create and return a new ``working`` task."""
        ...

    async def get_task(self, task_id: str) -> Task | None:
        """Return the task record for *task_id*, or ``None``."""
        ...

    async def update_task(
        self,
        task_id: str,
        status: TaskStatus | None = None,
        status_message: str | None = None,
    ) -> Task:
        """Update and return *task_id* (no-op for terminal tasks)."""
        ...

    async def store_result(self, task_id: str, result: Result) -> None:
        """Persist the payload produced by *task_id*."""
        ...

    async def get_result(self, task_id: str) -> StoredResult | None:
        """Return the stored payload for *task_id*, or ``None``."""
        ...

    async def list_tasks(self, cursor: str | None = None) -> tuple[list[Task], str | None]:
        """Return one page of tasks plus the cursor for the next page."""
        ...

    async def delete_task(self, task_id: str) -> bool:
        """Delete *task_id*; return whether a row was removed."""
        ...

    def get_task_owner(self, task_id: str) -> tuple[int | None, str | None] | None:
        """Return ``(owner_pid, owner_token)`` for *task_id*, or ``None``."""
        ...

    def sweep_stale_working(self, marker: str) -> int:
        """Mark ``working`` tasks owned by dead processes as ``failed``."""
        ...

    async def wait_for_update(self, task_id: str) -> None:
        """Block until *task_id* changes status."""
        ...

    async def notify_update(self, task_id: str) -> None:
        """Wake waiters blocked in :meth:`wait_for_update`."""
        ...


class SqliteTaskStore:
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

    def _migrate_schema_locked(self) -> None:
        cursor = self._conn.execute("PRAGMA table_info(tasks)")
        columns = {row["name"] for row in cursor.fetchall()}
        if "owner_pid" not in columns:
            try:
                self._conn.execute("ALTER TABLE tasks ADD COLUMN owner_pid INTEGER")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    pass
                else:
                    raise
        if "owner_token" not in columns:
            try:
                self._conn.execute("ALTER TABLE tasks ADD COLUMN owner_token TEXT")
            except sqlite3.OperationalError as exc:
                if "duplicate column name" in str(exc).lower():
                    pass
                else:
                    raise

    def _set_journal_mode_locked(self) -> None:
        for _ in range(50):
            try:
                mode = self._conn.execute("PRAGMA journal_mode").fetchone()
                if mode and str(mode[0]).lower() == "wal":
                    return
                self._conn.execute("PRAGMA journal_mode=WAL")
                return
            except sqlite3.OperationalError as exc:
                if "locked" in str(exc).lower() or "busy" in str(exc).lower():
                    time.sleep(0.05)
                    continue
                raise
        self._conn.execute("PRAGMA journal_mode=WAL")

    def _init_schema(self) -> None:
        with self._lock:
            self._set_journal_mode_locked()
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                self._conn.execute(_SCHEMA)
                self._migrate_schema_locked()
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _purge_expired_locked(self) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "DELETE FROM tasks WHERE expires_at IS NOT NULL AND expires_at <= ?",
            (now,),
        )

    @staticmethod
    def _row_to_task(row: sqlite3.Row) -> Task:
        return Task(
            task_id=row["task_id"],
            status=cast("TaskStatus", row["status"]),
            status_message=row["status_message"],
            created_at=row["created_at"],
            last_updated_at=row["last_updated_at"],
            ttl_ms=row["ttl"],
            poll_interval_ms=row["poll_interval"],
        )

    def _fetch_locked(self, task_id: str) -> sqlite3.Row | None:
        self._purge_expired_locked()
        cursor = self._conn.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,))
        return cast("sqlite3.Row | None", cursor.fetchone())

    # -- TaskStore protocol -------------------------------------------------

    async def create_task(
        self,
        task_id: str | None = None,
        ttl_ms: int | None = None,
        *,
        owner_pid: int | None | object = _SENTINEL_OWNER,
        owner_token: str | None | object = _SENTINEL_OWNER,
    ) -> Task:
        """Create and persist a new ``working`` task.

        Args:
            task_id: Explicit identifier; a UUID4 is generated when omitted.
            ttl_ms: Retention once terminal, in milliseconds.
            owner_pid: Owning process id; defaults to the current process.
            owner_token: Owning process start token; defaults to the current
                process identity. Pass ``None`` explicitly for legacy rows.

        Returns:
            The persisted task record.
        """
        now = datetime.now(UTC)
        task = Task(
            task_id=task_id or str(uuid.uuid4()),
            status=TASK_STATUS_WORKING,
            status_message=None,
            created_at=now.isoformat(),
            last_updated_at=now.isoformat(),
            ttl_ms=ttl_ms,
            poll_interval_ms=None,
        )
        eff_owner_pid: int | None
        eff_owner_token: str | None
        if owner_pid is _SENTINEL_OWNER and owner_token is _SENTINEL_OWNER:
            eff_owner_pid, eff_owner_token = get_current_process_identity()
        else:
            eff_owner_pid = cast("int | None", None if owner_pid is _SENTINEL_OWNER else owner_pid)
            eff_owner_token = cast(
                "str | None", None if owner_token is _SENTINEL_OWNER else owner_token
            )

        with self._lock, self._conn:
            self._purge_expired_locked()
            try:
                self._conn.execute(
                    """
                    INSERT INTO tasks (
                        task_id, status, status_message, created_at,
                        last_updated_at, ttl, poll_interval, result_json, expires_at,
                        owner_pid, owner_token
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task.task_id,
                        task.status,
                        task.status_message,
                        task.created_at,
                        task.last_updated_at,
                        task.ttl_ms,
                        task.poll_interval_ms,
                        None,
                        _expiry_iso(task.ttl_ms),
                        eff_owner_pid,
                        eff_owner_token,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError(f"Task with ID {task.task_id} already exists") from exc
        return task

    def get_task_owner(self, task_id: str) -> tuple[int | None, str | None] | None:
        """Return (owner_pid, owner_token) for *task_id*, or None if task not found."""
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
        if row is None:
            return None
        return (row["owner_pid"], row["owner_token"])

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
        """Transition *task_id*, guarding against late updates to terminal rows."""
        status_changed = False
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
            if row is None:
                raise ValueError(f"Task with ID {task_id} not found")
            current = self._row_to_task(row)

            if is_terminal(current.status):
                # Terminal records are immutable against progress/status-message-only updates
                # or any late status transitions.
                logger.warning(
                    "Ignoring update of terminal task %s (%s, requested status=%s, status_message=%s)",
                    task_id,
                    current.status,
                    status,
                    status_message,
                )
                return current

            new_status = current.status
            if status is not None and status != current.status:
                new_status = status
                status_changed = True

            new_message = status_message if status_message is not None else current.status_message
            now = datetime.now(UTC)
            expires_at = row["expires_at"]
            if is_terminal(new_status) and current.ttl_ms is not None:
                expires_at = _expiry_iso(current.ttl_ms)
            cursor = self._conn.execute(
                """
                UPDATE tasks
                SET status = ?, status_message = ?, last_updated_at = ?, expires_at = ?
                WHERE task_id = ? AND status = ?
                """,
                (new_status, new_message, now.isoformat(), expires_at, task_id, current.status),
            )
            if cursor.rowcount == 0:
                # Concurrent update occurred. Re-fetch current state.
                row = self._fetch_locked(task_id)
                if row is None:
                    raise ValueError(f"Task with ID {task_id} not found")
                current = self._row_to_task(row)
                if is_terminal(current.status):
                    logger.warning(
                        "Concurrent update to terminal task %s (%s)",
                        task_id,
                        current.status,
                    )
                return current

            updated = Task(
                task_id=task_id,
                status=new_status,
                status_message=new_message,
                created_at=current.created_at,
                last_updated_at=now.isoformat(),
                ttl_ms=current.ttl_ms,
                poll_interval_ms=current.poll_interval_ms,
            )
        if status_changed:
            await self.notify_update(task_id)
        return updated

    async def store_result(self, task_id: str, result: Result) -> None:
        """Persist *result* as the payload of *task_id*."""
        payload = json.dumps(result.model_dump(mode="json", by_alias=True))
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
            if row is None:
                raise ValueError(f"Task with ID {task_id} not found")
            self._conn.execute(
                "UPDATE tasks SET result_json = ? WHERE task_id = ?",
                (payload, task_id),
            )

    async def get_result(self, task_id: str) -> StoredResult | None:
        """Return the payload stored for *task_id*, or ``None``."""
        with self._lock, self._conn:
            row = self._fetch_locked(task_id)
        if row is None:
            return None
        raw = row["result_json"]
        if raw is None:
            return None
        return StoredResult.model_validate(json.loads(raw))

    async def list_tasks(
        self,
        cursor: str | None = None,
    ) -> tuple[list[Task], str | None]:
        """Return one page of task records plus the cursor for the next page."""
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
        """Delete *task_id*; return whether a row was removed."""
        with self._lock, self._conn:
            cursor = self._conn.execute("DELETE FROM tasks WHERE task_id = ?", (task_id,))
            return cursor.rowcount > 0

    def sweep_stale_working(self, marker: str) -> int:
        """Reconcile stale ``working`` tasks belonging to dead owners to terminal ``failed``.

        Only tasks whose owner process is demonstrably dead are swept. Foreign
        live owners and legacy tasks with unknown ownership are preserved.

        Args:
            marker: Human-readable status message recorded on swept rows.

        Returns:
            The number of rows swept (0 when there is nothing to reconcile).
        """
        # Step 1: Fetch candidate working tasks without holding a long transaction.
        with self._lock, self._conn:
            self._purge_expired_locked()
            cursor = self._conn.execute(
                "SELECT task_id, owner_pid, owner_token FROM tasks WHERE status = ?",
                (TASK_STATUS_WORKING,),
            )
            candidates = [
                (str(row["task_id"]), row["owner_pid"], row["owner_token"])
                for row in cursor.fetchall()
            ]

        if not candidates:
            return 0

        # Step 2: Probe candidate processes OUTSIDE database locks/transactions.
        dead_candidates: list[tuple[str, int | None, str | None]] = []
        for task_id, owner_pid, owner_token in candidates:
            if is_process_demonstrably_dead(owner_pid, owner_token):
                dead_candidates.append((task_id, owner_pid, owner_token))

        if not dead_candidates:
            return 0

        # Step 3: Optimistically sweep confirmed dead tasks.
        now = datetime.now(UTC).isoformat()
        total_swept = 0
        with self._lock, self._conn:
            for task_id, owner_pid, owner_token in dead_candidates:
                cursor = self._conn.execute(
                    """
                    UPDATE tasks
                    SET status = ?,
                        status_message = ?,
                        last_updated_at = ?,
                        expires_at = CASE
                            WHEN ttl IS NOT NULL
                            THEN strftime('%Y-%m-%dT%H:%M:%fZ', 'now', '+' || ttl || ' milliseconds')
                            ELSE expires_at
                        END
                    WHERE task_id = ? AND status = ? AND owner_pid IS ? AND owner_token IS ?
                    """,
                    (
                        TASK_STATUS_FAILED,
                        marker,
                        now,
                        task_id,
                        TASK_STATUS_WORKING,
                        owner_pid,
                        owner_token,
                    ),
                )
                total_swept += cursor.rowcount

        return total_swept

    async def wait_for_update(self, task_id: str) -> None:
        """Block until *task_id* next changes status."""
        if await self.get_task(task_id) is None:
            raise ValueError(f"Task with ID {task_id} not found")
        event = anyio.Event()
        self._update_events[task_id] = event
        await event.wait()

    async def notify_update(self, task_id: str) -> None:
        """Wake anyone blocked in :meth:`wait_for_update` for *task_id*."""
        event = self._update_events.get(task_id)
        if event is not None:
            event.set()


__all__ = [
    "DEFAULT_TASKS_DB",
    "SqliteTaskStore",
    "TaskStore",
    "get_current_process_identity",
    "get_process_start_time",
    "is_process_demonstrably_dead",
]
