"""Submit/poll background jobs layered on the shared MCP task store.

Standard MCP Tasks (:func:`ninja_common.mcp_tasks.install_tasks`) let a client
start a long tool call in the background and poll it, but only clients that
advertise the experimental ``tasks`` capability can use it. This module provides
an always-available alternative that works in *any* MCP host:

* :class:`JobManager` creates a durable task record in the shared
  :class:`~ninja_common.mcp_tasks.SqliteTaskStore`, then runs the work as an
  asyncio task bound to :func:`~ninja_common.mcp_tasks.task_scope`. That makes
  cancellation (:func:`~ninja_common.mcp_tasks.request_cancel`) and progress
  reach the running work exactly like the standard task path.
* On completion the payload is stored as the task result and the task is marked
  terminal. Failures mark the task ``failed`` with the error message, and
  cancellations mark it ``cancelled`` (guarding the same stale-complete race the
  task store already guards).
* The manager keeps strong references to running asyncio tasks so they are not
  garbage collected, and is safe to construct once per server.

The servers expose thin ``coder_submit_*`` / ``coder_job_status`` /
``coder_job_result`` / ``coder_job_cancel`` / ``coder_jobs_list`` tools over
this manager, reusing the same store as standard Tasks so both views agree.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from mcp.shared.experimental.tasks.helpers import is_terminal
from mcp.types import (
    TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED,
    TASK_STATUS_WORKING,
    Result,
    Task,
    TaskMetadata,
)

from ninja_common.mcp_tasks import TaskCancelledError, request_cancel, task_scope


if TYPE_CHECKING:
    from mcp.shared.experimental.tasks.store import TaskStore
    from mcp.types import TaskStatus


logger = logging.getLogger(__name__)

#: Task status values used by the job API (mirrors the MCP task statuses).
JOB_STATUS_WORKING: TaskStatus = TASK_STATUS_WORKING
JOB_STATUS_COMPLETED: TaskStatus = TASK_STATUS_COMPLETED
JOB_STATUS_FAILED: TaskStatus = TASK_STATUS_FAILED
JOB_STATUS_CANCELLED: TaskStatus = TASK_STATUS_CANCELLED

#: How long a finished job (and its result) is kept before lazy expiry.
DEFAULT_JOB_TTL_MS = 7 * 24 * 60 * 60 * 1000

#: Suggested client poll interval for jobs, in milliseconds.
DEFAULT_POLL_INTERVAL_MS = 500

#: How long ``cancel`` waits for the running work to wind down.
DEFAULT_CANCEL_WAIT_SECONDS = 15.0

#: A background job body: an awaitable returning the storable result payload.
JobWork = Callable[[], Awaitable[Result]]


class JobManager:
    """Run tool work in the background and expose it through a durable store.

    A single instance lives for the lifetime of a server. It shares one
    :class:`~ninja_common.mcp_tasks.SqliteTaskStore` with the standard MCP Tasks
    support, so ``coder_jobs_list`` / ``coder_job_status`` see both jobs created
    through this manager and tasks created by the standard path.
    """

    def __init__(
        self,
        store: TaskStore,
        *,
        ttl_ms: int = DEFAULT_JOB_TTL_MS,
        poll_interval_ms: int = DEFAULT_POLL_INTERVAL_MS,
        cancel_wait_seconds: float = DEFAULT_CANCEL_WAIT_SECONDS,
    ) -> None:
        """Create a job manager bound to *store*.

        Args:
            store: Durable task store shared with the server's tasks support.
            ttl_ms: Retention for finished jobs, in milliseconds.
            poll_interval_ms: Suggested client poll interval.
            cancel_wait_seconds: How long ``cancel`` waits for work to stop.
        """
        self._store = store
        self._ttl_ms = ttl_ms
        self._poll_interval_ms = poll_interval_ms
        self._cancel_wait_seconds = cancel_wait_seconds
        # Strong references so running work is never garbage collected. The
        # done callback removes entries once the work is finished.
        self._running: dict[str, asyncio.Task[None]] = {}
        self._pending_cancel: set[str] = set()

    @property
    def poll_interval_ms(self) -> int:
        """Suggested client poll interval in milliseconds."""
        return self._poll_interval_ms

    async def submit(self, work: JobWork, *, status_message: str | None = None) -> Task:
        """Create a durable job record and start *work* in the background.

        Args:
            work: Zero-argument coroutine factory returning the result payload.
            status_message: Optional human-readable status message stored on the
                job record.

        Returns:
            The freshly created (``working``) task record.
        """
        task = await self._store.create_task(TaskMetadata(ttl=self._ttl_ms))
        job_id = task.taskId
        if status_message is not None:
            task = await self._store.update_task(job_id, status_message=status_message)

        runner = asyncio.create_task(self._run(job_id, work), name=f"ninja-job-{job_id}")
        self._running[job_id] = runner

        def _on_done(_task: asyncio.Task[None], finished_id: str = job_id) -> None:
            self._forget(finished_id)

        runner.add_done_callback(_on_done)
        return task

    async def status(self, job_id: str) -> Task | None:
        """Return the current task record for *job_id*, or ``None``."""
        return await self._store.get_task(job_id)

    async def result(self, job_id: str) -> Result | None:
        """Return the stored result payload for *job_id*, or ``None``."""
        return await self._store.get_result(job_id)

    async def list_jobs(
        self,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> tuple[list[Task], str | None]:
        """List known jobs, honouring *limit* and page boundaries.

        The shared store pages at a fixed size, so when *limit* spans or cuts a
        page this walks pages and returns a cursor pointing at the last included
        job. A ``None`` limit returns the store's default page.
        """
        if limit is None or limit <= 0:
            return await self._store.list_tasks(cursor)

        collected: list[Task] = []
        page_cursor = cursor
        next_cursor: str | None = None
        while len(collected) < limit:
            page, page_next = await self._store.list_tasks(page_cursor)
            if not page:
                next_cursor = page_next
                break
            remaining = limit - len(collected)
            collected.extend(page[:remaining])
            if len(page) > remaining:
                # The limit lands inside this page: resume from the last item.
                next_cursor = collected[-1].taskId
                break
            page_cursor = page_next
            next_cursor = page_next
            if page_next is None:
                break
        return collected, next_cursor

    async def cancel(self, job_id: str) -> Task | None:
        """Interrupt *job_id* and return its final record.

        Idempotent and safe for unknown or already-terminal ids: a terminal job
        is returned unchanged and an unknown id yields ``None``. Cancellation is
        requested through :func:`request_cancel` so the running work (including a
        CLI subprocess group) is actually interrupted.
        """
        task = await self._store.get_task(job_id)
        if task is None or is_terminal(task.status):
            return task

        interrupted = request_cancel(job_id)
        runner = self._running.get(job_id)
        if not interrupted and runner is not None:
            # The runner has not entered ``task_scope`` yet; make it observe the
            # cancellation as soon as it does.
            self._pending_cancel.add(job_id)
        if runner is not None:
            try:
                await asyncio.wait_for(asyncio.shield(runner), timeout=self._cancel_wait_seconds)
            except TimeoutError:
                logger.warning("Timed out waiting for job %s to stop", job_id)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("Job %s runner ended with an error", job_id, exc_info=True)
        return await self._set_terminal(job_id, JOB_STATUS_CANCELLED)

    # -- internals ----------------------------------------------------------

    def _forget(self, job_id: str) -> None:
        """Drop bookkeeping for a finished runner."""
        self._running.pop(job_id, None)
        self._pending_cancel.discard(job_id)

    async def _run(self, job_id: str, work: JobWork) -> None:
        """Execute *work* under a task scope and record its outcome."""
        try:
            async with task_scope(job_id) as cancellation:
                if self._take_pending_cancel(job_id):
                    cancellation.cancel()
                if cancellation.is_set():
                    await self._set_terminal(job_id, JOB_STATUS_CANCELLED)
                    return

                result = await work()

                if cancellation.is_set():
                    await self._set_terminal(job_id, JOB_STATUS_CANCELLED)
                    return
                await self._store.store_result(job_id, result)
                await self._store.update_task(job_id, status=JOB_STATUS_COMPLETED)
        except TaskCancelledError:
            await self._set_terminal(job_id, JOB_STATUS_CANCELLED)
        except asyncio.CancelledError:
            await self._set_terminal(job_id, JOB_STATUS_CANCELLED)
            raise
        except Exception as exc:
            logger.warning("Background job %s failed: %s", job_id, exc, exc_info=True)
            await self._set_terminal(job_id, JOB_STATUS_FAILED, f"{type(exc).__name__}: {exc}")

    def _take_pending_cancel(self, job_id: str) -> bool:
        """Consume the pre-start cancellation flag for *job_id*, if set."""
        if job_id in self._pending_cancel:
            self._pending_cancel.discard(job_id)
            return True
        return False

    async def _set_terminal(
        self,
        job_id: str,
        status: TaskStatus,
        message: str | None = None,
    ) -> Task | None:
        """Transition *job_id* to *status* unless it is already terminal.

        The existence and terminal checks mirror :class:`SqliteTaskStore`'s
        stale-complete guard, so a cancellation racing with completion can never
        raise or overwrite a terminal state.
        """
        try:
            current = await self._store.get_task(job_id)
            if current is None or is_terminal(current.status):
                return current
            return await self._store.update_task(job_id, status=status, status_message=message)
        except BaseException:
            logger.warning("Could not mark job %s as %s", job_id, status, exc_info=True)
            return None


__all__ = [
    "DEFAULT_CANCEL_WAIT_SECONDS",
    "DEFAULT_JOB_TTL_MS",
    "DEFAULT_POLL_INTERVAL_MS",
    "JOB_STATUS_CANCELLED",
    "JOB_STATUS_COMPLETED",
    "JOB_STATUS_FAILED",
    "JOB_STATUS_WORKING",
    "JobManager",
    "JobWork",
]
