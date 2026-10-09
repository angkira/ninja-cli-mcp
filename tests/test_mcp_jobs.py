"""End-to-end tests for the always-available submit/poll background-job API.

These spawn the real ninja-coder server over stdio via ``tests._task_stub_server``
(which swaps only the ``ToolExecutor`` for a deterministic stub), so no model or
network is required. The tests exercise the plain ``coder_submit_*`` /
``coder_job_*`` tools without advertising the standard MCP Tasks capability,
proving background work is reachable across separate tool calls in any host.

Covered:
* submit returns ``working`` immediately; polling reaches ``completed`` and the
  payload is fetched via ``coder_job_result``.
* cancelling a slow job actually interrupts the work, reports ``cancelled`` and
  leaves the server able to serve other calls.
* a job created in one server session is visible from a fresh server sharing the
  same ``NINJA_TASKS_DB``.
* ``coder_jobs_list`` returns the job.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from ninja_coder.server import _make_job_progress_factory
from ninja_common.jobs import JobManager
from ninja_common.mcp_tasks import SqliteTaskStore, TaskCancelledError, get_task_cancellation


if TYPE_CHECKING:
    from collections.abc import AsyncIterator


REPO_ROOT = Path(__file__).resolve().parent.parent
SLOW_TASK = "slow: keep running until cancelled"
SIMPLE_TASK = "hello from the job test"
MARKER_ENV = "NINJA_TASK_TEST_MARKER"


def _text_of(result: types.CallToolResult) -> str:
    """Return the first text block payload of a tool result."""
    assert result.content, "expected at least one content block"
    block = result.content[0]
    assert isinstance(block, types.TextContent)
    return block.text


def _payload(result: types.CallToolResult) -> dict:
    """Parse the JSON payload of a tool result."""
    return json.loads(_text_of(result))


@asynccontextmanager
async def _connected(
    db_path: Path,
    *,
    extra_env: dict[str, str] | None = None,
) -> AsyncIterator[ClientSession]:
    """Connect to the deterministic coder stub server over stdio.

    The client does *not* advertise the MCP Tasks capability: the submit/poll
    API must work regardless.
    """
    env = {
        "PYTHONPATH": os.pathsep.join([str(REPO_ROOT), str(REPO_ROOT / "src")]),
        "NINJA_LOG_LEVEL": "WARNING",
        "NINJA_TASKS_DB": str(db_path),
    }
    if extra_env:
        env.update(extra_env)
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "tests._task_stub_server"],
        env=env,
        cwd=str(REPO_ROOT),
    )
    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


async def _poll_status(session: ClientSession, job_id: str, *, timeout: float = 15.0) -> dict:
    """Poll ``coder_job_status`` until the job leaves the ``working`` state."""
    deadline = time.monotonic() + timeout
    payload: dict = {}
    while time.monotonic() < deadline:
        payload = _payload(await session.call_tool("coder_job_status", {"job_id": job_id}))
        if payload.get("status") != "working":
            return payload
        await asyncio.sleep(0.05)
    raise AssertionError(f"job {job_id} did not finish in time: {payload}")


async def _wait_for_marker(marker: Path, needle: str, *, timeout: float = 15.0) -> bool:
    """Poll *marker* until it contains *needle* (or the timeout elapses)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if marker.exists() and needle in marker.read_text():
            return True
        await asyncio.sleep(0.05)
    return False


async def test_submit_immediately_working_then_completes() -> None:
    """Submit returns a handle instantly; polling reaches the stored payload."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
                )
            )
            assert submitted["status"] == "working"
            assert submitted["job_id"]
            assert submitted["poll_interval_ms"] >= 1
            job_id = submitted["job_id"]

            terminal = await _poll_status(session, job_id)
            assert terminal["status"] == "completed"
            assert terminal["job_id"] == job_id

            result = _payload(await session.call_tool("coder_job_result", {"job_id": job_id}))
            assert result["status"] == "ok"
            assert f"stub: {SIMPLE_TASK}" in result["summary"]


async def test_cancel_interrupts_slow_job_and_server_survives() -> None:
    """Cancelling a running job interrupts the work without tearing down tasks."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        marker = Path(tmp) / "marker.txt"
        async with _connected(db_path, extra_env={MARKER_ENV: str(marker)}) as session:
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": SLOW_TASK, "repo_root": str(REPO_ROOT)},
                )
            )
            job_id = submitted["job_id"]
            assert await _wait_for_marker(marker, "progress=", timeout=10), "job never started"

            cancelled = _payload(await session.call_tool("coder_job_cancel", {"job_id": job_id}))
            assert cancelled["status"] == "cancelled"

            # The stub loop observes the cancellation and exits early.
            assert await _wait_for_marker(marker, "interrupted", timeout=10)
            assert "completed" not in marker.read_text()

            status = _payload(await session.call_tool("coder_job_status", {"job_id": job_id}))
            assert status["status"] == "cancelled"

            # Cancellation is idempotent and the server still serves calls.
            again = _payload(await session.call_tool("coder_job_cancel", {"job_id": job_id}))
            assert again["status"] == "cancelled"

            other = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
                )
            )
            assert (await _poll_status(session, other["job_id"]))["status"] == "completed"


async def test_cancel_unknown_job_is_idempotent() -> None:
    """Cancelling an unknown job id never raises."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            payload = _payload(
                await session.call_tool("coder_job_cancel", {"job_id": "no-such-job-id"})
            )
            assert payload["status"] == "cancelled"


async def test_job_visible_in_fresh_server_with_same_db() -> None:
    """A job created in one server session is visible from a fresh server."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
                )
            )
            job_id = submitted["job_id"]
            assert (await _poll_status(session, job_id))["status"] == "completed"

        async with _connected(db_path) as fresh:
            status = _payload(await fresh.call_tool("coder_job_status", {"job_id": job_id}))
            assert status["status"] == "completed"

            result = _payload(await fresh.call_tool("coder_job_result", {"job_id": job_id}))
            assert result["status"] == "ok"
            assert f"stub: {SIMPLE_TASK}" in result["summary"]


async def test_jobs_list_returns_submitted_job() -> None:
    """``coder_jobs_list`` exposes the job through the shared store."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": SIMPLE_TASK, "repo_root": str(REPO_ROOT)},
                )
            )
            job_id = submitted["job_id"]
            await _poll_status(session, job_id)

            listing = _payload(await session.call_tool("coder_jobs_list", {}))
            entries = {job["job_id"]: job for job in listing["jobs"]}
            assert job_id in entries
            assert entries[job_id]["status"] == "completed"


TIMED_TASK = "timed:"  # timed:<seconds> — a long task simulated with asyncio timers


def _marker_elapsed(marker: Path, needle: str) -> float:
    """Return the ``elapsed=`` seconds recorded on the marker line starting with *needle*."""
    for line in marker.read_text().splitlines():
        if line.startswith(needle):
            for part in line.split():
                if part.startswith("elapsed="):
                    return float(part.split("=", 1)[1])
    raise AssertionError(f"no {needle!r} line in marker: {marker.read_text()!r}")


async def test_submit_is_immediate_and_timed_job_runs_in_background() -> None:
    """A long (timer) job returns a handle instantly and runs in the background."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            started = time.monotonic()
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": f"{TIMED_TASK}2.0", "repo_root": str(REPO_ROOT)},
                )
            )
            submit_latency = time.monotonic() - started
            assert submitted["status"] == "working"
            assert submit_latency < 0.5, f"submit blocked for {submit_latency:.2f}s"
            job_id = submitted["job_id"]

            # Still working right after submit, and the caller can keep calling.
            immediate = _payload(await session.call_tool("coder_job_status", {"job_id": job_id}))
            assert immediate["status"] == "working"
            listing = _payload(await session.call_tool("coder_jobs_list", {}))
            assert job_id in {job["job_id"] for job in listing["jobs"]}

            # It finishes only after roughly the timer duration.
            poll_started = time.monotonic()
            terminal = await _poll_status(session, job_id, timeout=15)
            ran = time.monotonic() - poll_started
            assert terminal["status"] == "completed"
            assert ran >= 1.0, f"job finished too fast ({ran:.2f}s); timer did not run"

            result = _payload(await session.call_tool("coder_job_result", {"job_id": job_id}))
            assert "stub timed" in result["summary"]


async def test_cancel_stops_timed_job_mid_flight() -> None:
    """Cancelling a timed job stops the timer early (work actually interrupted)."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        marker = Path(tmp) / "marker.txt"
        async with _connected(db_path, extra_env={MARKER_ENV: str(marker)}) as session:
            submitted = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": f"{TIMED_TASK}10.0", "repo_root": str(REPO_ROOT)},
                )
            )
            job_id = submitted["job_id"]

            await asyncio.sleep(0.3)  # let the timer tick a few times
            cancelled = _payload(await session.call_tool("coder_job_cancel", {"job_id": job_id}))
            assert cancelled["status"] == "cancelled"

            assert await _wait_for_marker(marker, "timed-interrupted", timeout=10)
            elapsed = _marker_elapsed(marker, "timed-interrupted")
            assert elapsed < 5.0, f"timer ran {elapsed:.2f}s despite cancellation"
            assert "timed-completed" not in marker.read_text()

            status = _payload(await session.call_tool("coder_job_status", {"job_id": job_id}))
            assert status["status"] == "cancelled"


async def test_concurrent_timed_jobs_do_not_interfere() -> None:
    """Several timer jobs run in parallel without trampling each other's timers.

    Three jobs with different durations must each finish after (roughly) their
    own duration — shortest first — and cancelling a fourth, long job must not
    disturb the others (independent cancellation contexts).
    """
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        marker = Path(tmp) / "marker.txt"
        async with _connected(db_path, extra_env={MARKER_ENV: str(marker)}) as session:
            specs = (0.8, 1.6, 2.4)
            jobs: dict[float, str] = {}
            for spec in specs:
                payload = _payload(
                    await session.call_tool(
                        "coder_submit_simple",
                        {"task": f"{TIMED_TASK}{spec}", "repo_root": str(REPO_ROOT)},
                    )
                )
                assert payload["status"] == "working"
                jobs[spec] = payload["job_id"]

            # A separate long job that we cancel; it must not affect the others.
            doomed = _payload(
                await session.call_tool(
                    "coder_submit_simple",
                    {"task": f"{TIMED_TASK}30.0", "repo_root": str(REPO_ROOT)},
                )
            )["job_id"]
            await asyncio.sleep(0.3)
            assert (
                _payload(await session.call_tool("coder_job_cancel", {"job_id": doomed}))["status"]
                == "cancelled"
            )

            for spec, job_id in jobs.items():
                terminal = await _poll_status(session, job_id, timeout=15)
                assert terminal["status"] == "completed", f"{spec}s job: {terminal}"

            lines = marker.read_text().splitlines()
            completed = [line for line in lines if line.startswith("timed-completed")]
            interrupted = [line for line in lines if line.startswith("timed-interrupted")]
            assert len(completed) == len(specs), lines
            assert len(interrupted) == 1, lines

            # Each job ran for ~its own duration: its timer was independent.
            elapsed_by_spec: dict[float, float] = {}
            for line in completed:
                spec = float(line.split("spec=")[1].split()[0])
                elapsed = float(line.split("elapsed=")[1].split()[0])
                elapsed_by_spec[spec] = elapsed
            assert set(elapsed_by_spec) == set(specs)
            for spec in specs:
                assert spec * 0.7 <= elapsed_by_spec[spec] <= spec + 1.5, elapsed_by_spec
            # Longer durations took longer (no shared/looped timer).
            assert elapsed_by_spec[0.8] < elapsed_by_spec[1.6] < elapsed_by_spec[2.4], (
                elapsed_by_spec
            )


# --- fix1: durable rows for inline/sync execution --------------------------


def _result_text(result: types.Result) -> str:
    """Return the first text block of a stored ``CallToolResult`` payload."""
    dumped = result.model_dump(by_alias=True)
    return str(dumped["content"][0]["text"])


async def test_run_tracked_records_completion_and_result(tmp_path: Path) -> None:
    """``run_tracked`` persists a durable row that reaches ``completed``."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="done")], isError=False
        )

    await jobs.run_tracked(work, status_message="unit-task")

    listed, _ = await jobs.list_jobs()
    assert len(listed) == 1
    assert listed[0].status == "completed"
    stored = await jobs.result(listed[0].taskId)
    assert stored is not None
    assert _result_text(stored) == "done"


async def test_run_tracked_marks_failed_on_exception(tmp_path: Path) -> None:
    """A work exception marks the durable row ``failed`` and is re-raised."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        await jobs.run_tracked(work, status_message="unit-task")

    listed, _ = await jobs.list_jobs()
    assert len(listed) == 1
    assert listed[0].status == "failed"
    assert "boom" in (listed[0].statusMessage or "")


async def test_run_tracked_is_visible_and_cancellable_mid_flight(tmp_path: Path) -> None:
    """A running inline job is visible as ``working`` and can be cancelled."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)
    started = asyncio.Event()

    async def work() -> types.CallToolResult:
        started.set()
        cancellation = get_task_cancellation()
        while cancellation is not None and not cancellation.is_set():
            await asyncio.sleep(0.02)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="unreachable")], isError=False
        )

    runner = asyncio.create_task(jobs.run_tracked(work, status_message="slow"))
    await asyncio.wait_for(started.wait(), timeout=5)

    listed, _ = await jobs.list_jobs()
    assert len(listed) == 1
    assert listed[0].status == "working"
    job_id = listed[0].taskId

    cancelled = await jobs.cancel(job_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    with pytest.raises(TaskCancelledError):
        await runner


async def test_sync_tool_registers_durable_job_and_returns_full_payload() -> None:
    """A sync tool still returns its full payload *and* leaves a terminal row."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            result = _payload(
                await session.call_tool(
                    "coder_simple_task",
                    {"task": "timed:0.3", "repo_root": str(REPO_ROOT)},
                )
            )
            assert result["status"] == "ok"
            assert "stub timed" in result["summary"]

            listing = _payload(await session.call_tool("coder_jobs_list", {}))
            assert len(listing["jobs"]) == 1
            entry = listing["jobs"][0]
            assert entry["status"] == "completed"

            stored = _payload(
                await session.call_tool("coder_job_result", {"job_id": entry["job_id"]})
            )
            assert "stub timed" in stored["summary"]


# --- fix2: request_key idempotency -----------------------------------------


async def test_request_key_coalesces_concurrent_submits() -> None:
    """Same request_key => same job id and a single job, even concurrently."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            args = {
                "repo_root": str(REPO_ROOT),
                "steps": [{"task": "hello"}],
                "request_key": "rk-coalesce",
            }
            first, second = await asyncio.gather(
                session.call_tool("coder_submit_sequential", dict(args)),
                session.call_tool("coder_submit_sequential", dict(args)),
            )
            assert _payload(first)["job_id"] == _payload(second)["job_id"]

            listing = _payload(await session.call_tool("coder_jobs_list", {}))
            assert len(listing["jobs"]) == 1


async def test_request_key_returns_same_job_after_completion() -> None:
    """A retry with the same key after completion returns the cached job."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            args = {
                "repo_root": str(REPO_ROOT),
                "steps": [{"task": "hello"}],
                "request_key": "rk-replay",
            }
            first = _payload(await session.call_tool("coder_submit_sequential", dict(args)))
            await _poll_status(session, first["job_id"])
            second = _payload(await session.call_tool("coder_submit_sequential", dict(args)))
            assert first["job_id"] == second["job_id"]

            listing = _payload(await session.call_tool("coder_jobs_list", {}))
            assert len(listing["jobs"]) == 1


async def test_distinct_request_keys_create_distinct_jobs() -> None:
    """Different request_keys are independent submissions."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            base = {"repo_root": str(REPO_ROOT), "steps": [{"task": "hello"}]}
            first = _payload(
                await session.call_tool("coder_submit_sequential", {**base, "request_key": "rk-a"})
            )
            second = _payload(
                await session.call_tool("coder_submit_sequential", {**base, "request_key": "rk-b"})
            )
            assert first["job_id"] != second["job_id"]


async def test_missing_request_key_keeps_submit_behavior() -> None:
    """Without a request_key, every submit creates a fresh job (as today)."""
    with tempfile.TemporaryDirectory(prefix="ninja-jobs-test-") as tmp:
        db_path = Path(tmp) / "tasks.db"
        async with _connected(db_path) as session:
            args = {"repo_root": str(REPO_ROOT), "steps": [{"task": "hello"}]}
            first = _payload(await session.call_tool("coder_submit_sequential", dict(args)))
            second = _payload(await session.call_tool("coder_submit_sequential", dict(args)))
            assert first["job_id"] != second["job_id"]


# --- fix5: progress refresh -------------------------------------------------


async def test_progress_factory_refreshes_status_message(tmp_path: Path) -> None:
    """The server progress factory writes the latest progress message."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    factory = _make_job_progress_factory(store, "unit")
    callback = factory("job-progress")
    await store.create_task(types.TaskMetadata(ttl=60000), task_id="job-progress")

    await callback(1.0, 3.0, "step 1")
    task = await store.get_task("job-progress")
    assert task is not None
    assert task.statusMessage == "unit: step 1"

    await callback(2.0, 3.0, "step 2")
    task = await store.get_task("job-progress")
    assert task is not None
    assert task.statusMessage == "unit: step 2"


async def test_progress_factory_swallows_store_failure(tmp_path: Path) -> None:
    """A store failure inside the progress callback never breaks the work."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    factory = _make_job_progress_factory(store, "unit")
    callback = factory("job-progress")

    async def boom(*args: object, **kwargs: object) -> types.Task:
        raise RuntimeError("db down")

    store.update_task = boom  # type: ignore[method-assign]
    await callback(1.0, None, "whatever")  # must not raise


# --- status fidelity: failed payloads mark the job failed ------------------


async def test_run_tracked_failed_payload_marks_status_failed_with_reason(
    tmp_path: Path,
) -> None:
    """A work payload reporting overall_status=failed marks the job ``failed``."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps({"overall_status": "failed", "error": "boom"}),
                )
            ],
            isError=False,
        )

    await jobs.run_tracked(work, status_message="unit-task")

    listed, _ = await jobs.list_jobs()
    assert len(listed) == 1
    assert listed[0].status == "failed"
    assert "boom" in (listed[0].statusMessage or "")
    # The payload is still stored for clients that read the result.
    assert await jobs.result(listed[0].taskId) is not None


async def test_run_tracked_failed_payload_uses_reason_fallback(tmp_path: Path) -> None:
    """overall_status=failed with no error uses the ``reason`` field."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[
                types.TextContent(
                    type="text",
                    text=json.dumps({"overall_status": "failed", "reason": "nope"}),
                )
            ],
            isError=False,
        )

    await jobs.run_tracked(work, status_message="unit-task")
    listed, _ = await jobs.list_jobs()
    assert listed[0].status == "failed"
    assert "nope" in (listed[0].statusMessage or "")


async def test_run_tracked_status_error_marks_failed(tmp_path: Path) -> None:
    """A payload with status=error marks the job ``failed``."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=json.dumps({"status": "error", "error": "bad"}))
            ],
            isError=False,
        )

    await jobs.run_tracked(work, status_message="unit-task")
    listed, _ = await jobs.list_jobs()
    assert listed[0].status == "failed"
    assert "bad" in (listed[0].statusMessage or "")


async def test_run_tracked_partial_payload_stays_completed(tmp_path: Path) -> None:
    """overall_status=partial is not a failure: the job completes."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[
                types.TextContent(type="text", text=json.dumps({"overall_status": "partial"}))
            ],
            isError=False,
        )

    await jobs.run_tracked(work, status_message="unit-task")
    listed, _ = await jobs.list_jobs()
    assert listed[0].status == "completed"


async def test_run_tracked_non_dict_payload_stays_completed(tmp_path: Path) -> None:
    """A non-dict (non-JSON) payload keeps the job ``completed``."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> types.CallToolResult:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="plain text output")],
            isError=False,
        )

    await jobs.run_tracked(work, status_message="unit-task")
    listed, _ = await jobs.list_jobs()
    assert listed[0].status == "completed"


async def test_run_tracked_dict_payload_failure_marks_failed(tmp_path: Path) -> None:
    """A plain dict failure payload is stored and marks the job ``failed``."""
    store = SqliteTaskStore(tmp_path / "tasks.db")
    jobs = JobManager(store)

    async def work() -> object:
        return {"overall_status": "failed", "reason": "dict-reason"}

    await jobs.run_tracked(work, status_message="unit-task")  # type: ignore[arg-type]

    listed, _ = await jobs.list_jobs()
    assert listed[0].status == "failed"
    assert "dict-reason" in (listed[0].statusMessage or "")
    assert await jobs.result(listed[0].taskId) is not None
