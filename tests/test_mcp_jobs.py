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

from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


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
