"""Deterministic stdio MCP server used by ``tests/test_mcp_tasks.py``.

This runs the *real* ninja-coder MCP server wiring — including standard MCP
Tasks via ``ninja_common.mcp_tasks.install_tasks`` — but swaps the
``ToolExecutor`` for a stub that never touches a model, subprocess, or the
network. That makes the task lifecycle (create -> poll -> result / cancel)
fully deterministic.

The stub's ``slow:`` task loops on a short tick so it can observe a real
cancellation through the task contextvar, emit progress through the progress
bridge, and record what happened to ``NINJA_TASK_TEST_MARKER`` (a plain file)
for the test process to assert on.

Run directly: ``python -m tests._task_stub_server``.
"""

from __future__ import annotations

import asyncio
import os
import time
from typing import Any

from ninja_coder import server as _server
from ninja_coder.models import (
    GetAgentsResult,
    MultiAgentTaskResult,
    PlanExecutionResult,
    QueryLogsResult,
    SimpleTaskResult,
)
from ninja_common.mcp_tasks import emit_progress, get_progress_callback, get_task_cancellation


SLOW_PREFIX = "slow:"
SLOW_DELAY_SECONDS = 30.0
SLOW_POLL_SECONDS = 0.05
#: ``timed:<seconds>`` runs for that many seconds on a short timer tick, so the
#: tests can simulate a long task deterministically and measure how long it ran.
TIMED_PREFIX = "timed:"
TIMED_TICK_SECONDS = 0.05
TIMED_PROGRESS_EVERY_TICKS = 10
MARKER_ENV = "NINJA_TASK_TEST_MARKER"


def _mark(line: str) -> None:
    """Append a marker line for the test process (best-effort, never fatal)."""
    path = os.environ.get(MARKER_ENV)
    if not path:
        return
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{line}\n")
    except OSError:
        pass


class StubExecutor:
    """Executor that returns fixed results without any external dependency."""

    async def simple_task(self, request: Any, *, client_id: str = "default") -> SimpleTaskResult:
        task = str(request.task)
        if task.startswith(SLOW_PREFIX):
            await self._run_slow_task()
            return SimpleTaskResult(status="ok", summary=f"stub: {task}")
        if task.startswith(TIMED_PREFIX):
            elapsed = await self._run_timed_task(task[len(TIMED_PREFIX) :].strip())
            return SimpleTaskResult(status="ok", summary=f"stub timed: ran {elapsed:.2f}s")
        return SimpleTaskResult(status="ok", summary=f"stub: {task}")

    async def _run_timed_task(self, spec: str) -> float:
        """Run for ``spec`` seconds on a timer tick, honoring cancellation.

        Simulates a long task with asyncio timers. Records ``timed-completed`` /
        ``timed-interrupted`` plus the elapsed seconds and tick count to the
        marker file, and returns the seconds actually run.
        """
        try:
            duration = max(0.0, float(spec or "1"))
        except ValueError:
            duration = 1.0

        start = time.monotonic()
        ticks = 0
        while True:
            elapsed = time.monotonic() - start
            if elapsed >= duration:
                break
            cancellation = get_task_cancellation()
            if cancellation is not None and cancellation.is_set():
                _mark(f"timed-interrupted spec={spec} elapsed={elapsed:.2f} ticks={ticks}")
                return elapsed
            ticks += 1
            if get_progress_callback() is not None and ticks % TIMED_PROGRESS_EVERY_TICKS == 0:
                await emit_progress(elapsed, duration, f"tick {ticks}")
            await asyncio.sleep(TIMED_TICK_SECONDS)

        elapsed = time.monotonic() - start
        _mark(f"timed-completed spec={spec} elapsed={elapsed:.2f} ticks={ticks}")
        return elapsed

    async def _run_slow_task(self) -> None:
        """Loop until cancelled, proving the progress bridge and cancellation."""
        if get_progress_callback() is not None:
            emitted = await emit_progress(1.0, 3.0, "slow task started")
            _mark("progress=1" if emitted else "progress=0")
        else:
            _mark("progress=0")

        cancellation = get_task_cancellation()
        deadline = time.monotonic() + SLOW_DELAY_SECONDS
        while time.monotonic() < deadline:
            if cancellation is not None and cancellation.is_set():
                _mark("interrupted")
                return
            await asyncio.sleep(SLOW_POLL_SECONDS)
        _mark("completed")

    async def execute_plan_sequential(
        self, request: Any, *, client_id: str = "default"
    ) -> PlanExecutionResult:
        return PlanExecutionResult(overall_status="success", steps=[], execution_time=0.0)

    async def execute_plan_parallel(
        self, request: Any, *, client_id: str = "default"
    ) -> PlanExecutionResult:
        return PlanExecutionResult(overall_status="success", steps=[], execution_time=0.0)

    async def get_agents(self, request: Any, *, client_id: str = "default") -> GetAgentsResult:
        return GetAgentsResult(status="ok", total_agents=0, agents=[])

    async def multi_agent_task(
        self, request: Any, *, client_id: str = "default"
    ) -> MultiAgentTaskResult:
        return MultiAgentTaskResult(
            status="ok",
            summary=f"stub: {request.task}",
            agents_used=[],
            session_id=None,
            message="stub",
        )

    async def query_logs(self, request: Any, *, client_id: str = "default") -> QueryLogsResult:
        return QueryLogsResult(
            status="ok",
            entries=[],
            total_count=0,
            returned_count=0,
            message="stub",
        )


def build_stub_executor() -> StubExecutor:
    """Return a fresh stub executor instance."""
    return StubExecutor()


def main() -> None:
    """Patch the module-level executor factory, then serve over stdio."""
    _server.get_executor = build_stub_executor  # type: ignore[assignment]
    asyncio.run(_server.main_stdio())


if __name__ == "__main__":
    main()
