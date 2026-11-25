#!/usr/bin/env python3
"""Live battle test: MCP Tasks extension + elicitation / MRTR (2026-07-28).

Drives already-running ninja-mcp daemons over streamable HTTP:

* agent     ``NINJA_AGENT_PORT``      (default 8106) A lifecycle, B cancel, C legacy, E concurrency
* coder     ``NINJA_CODER_PORT``      (default 8100) D elicitation / MRTR, decline only
* secretary ``NINJA_SECRETARY_PORT``  (default 8107) F advertised-contract probes

Safety: nothing in the repository is touched. The only filesystem work is a
throwaway git repo created with ``tempfile.mkdtemp()``. `coder_branch_discard`
is only ever called with force=false and with a client that declines, so no
branch is deleted. No daemon is stopped or restarted, and the suite never
signals a process it did not create: cancellation is verified by PID against
the process group captured for the task itself.

The suite is opt-in: it needs running daemons and is intentionally not wired
into the default pytest run. Exit code is 0 only when every check passed.

Usage:
    python scripts/e2e/battle_tasks.py
    python scripts/e2e/battle_tasks.py --json /tmp/tasks.json
    python scripts/e2e/battle_tasks.py --ports agent=8106,coder=8100
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psutil
from mcp import Client, types
from mcp.client import advertise
from mcp.shared.exceptions import MCPError
from pydantic import Field, TypeAdapter


#: Deployed defaults; override with NINJA_<MODULE>_PORT or ``--ports``.
DEFAULT_PORTS: dict[str, int] = {
    "coder": 8100,
    "researcher": 8101,
    "agent": 8106,
    "secretary": 8107,
}
PORT_ENV: dict[str, str] = {
    "coder": "NINJA_CODER_PORT",
    "researcher": "NINJA_RESEARCHER_PORT",
    "agent": "NINJA_AGENT_PORT",
    "secretary": "NINJA_SECRETARY_PORT",
}


def resolve_ports(override: str | None) -> dict[str, int]:
    """Resolve module ports: CLI override > environment > deployed default."""
    ports = {}
    for key, default in DEFAULT_PORTS.items():
        raw = os.environ.get(PORT_ENV[key], "").strip()
        try:
            ports[key] = int(raw) if raw else default
        except ValueError:
            raise SystemExit(f"{PORT_ENV[key]} must be an integer, got {raw!r}") from None
    if override:
        for item in override.split(","):
            if not item.strip():
                continue
            try:
                key, value = item.split("=", 1)
            except ValueError:
                raise SystemExit(f"--ports expects module=port pairs, got {item!r}") from None
            key = key.strip().lower()
            if key not in ports:
                raise SystemExit(f"unknown module {key!r}; expected one of {sorted(ports)}")
            try:
                ports[key] = int(value)
            except ValueError:
                raise SystemExit(f"port for {key!r} must be an integer, got {value!r}") from None
    return ports


PORTS: dict[str, int] = resolve_ports(None)
AGENT_URL = f"http://127.0.0.1:{PORTS['agent']}/mcp"
CODER_URL = f"http://127.0.0.1:{PORTS['coder']}/mcp"
SECRETARY_URL = f"http://127.0.0.1:{PORTS['secretary']}/mcp"
TASKS_EXT = "io.modelcontextprotocol/tasks"

#: Unique prefix keeps concurrent runs from sharing a scratch directory or
#: branch namespace.
RUN_ID = uuid.uuid4().hex[:12]
WORK_ROOT = Path(tempfile.mkdtemp(prefix=f"ninja-battle-work-{RUN_ID}-"))
TS = int(time.time())
BRANCH_A = f"ninja/battle-{TS}-{RUN_ID}"
BRANCH_B = f"ninja/battle-{TS}-{RUN_ID}-b"

READ_TIMEOUT = 120.0
DICT: TypeAdapter[dict[str, Any]] = TypeAdapter(dict)


class Raw(types.Request[dict[str, Any], str]):
    """A request for a method the typed client SDK helper does not model."""

    params: dict[str, Any] = Field(default_factory=dict)


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #


@dataclass
class Check:
    phase: str
    ident: str
    desc: str
    ok: bool
    observed: Any


@dataclass
class Report:
    checks: list[Check] = field(default_factory=list)
    payloads: dict[str, Any] = field(default_factory=dict)
    timings: dict[str, float] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def check(self, phase: str, ident: str, desc: str, ok: bool, observed: Any) -> bool:
        self.checks.append(Check(phase, ident, desc, bool(ok), observed))
        return bool(ok)

    def phase_failed(self, phase: str, exc: BaseException) -> None:
        self.checks.append(
            Check(phase, f"{phase}.ERR", f"phase aborted: {exc!r}", False, repr(exc))
        )

    def dump(self) -> str:
        lines: list[str] = []
        lines.append("=" * 78)
        lines.append("RESULTS")
        lines.append("=" * 78)
        current = None
        for c in self.checks:
            if c.phase != current:
                current = c.phase
                lines.append("")
                lines.append(f"--- {current} ---")
            mark = "PASS" if c.ok else "FAIL"
            obs = c.observed
            if not isinstance(obs, str):
                obs = json.dumps(obs, default=str)
            if len(obs) > 700:
                obs = obs[:700] + " …"
            lines.append(f"[{mark}] {c.ident}: {c.desc}")
            lines.append(f"        observed: {obs}")

        lines.append("")
        lines.append("=" * 78)
        lines.append("TIMINGS (seconds)")
        lines.append("=" * 78)
        for name, secs in self.timings.items():
            lines.append(f"  {name:24s} {secs:8.2f}")
        if self.notes:
            lines.append("")
            lines.append("NOTES")
            for note in self.notes:
                lines.append(f"  - {note}")
        passed = sum(1 for c in self.checks if c.ok)
        lines.append("")
        lines.append(
            f"TOTAL: {passed}/{len(self.checks)} checks passed, {len(self.checks) - passed} failed"
        )
        return "\n".join(lines)


REPORT = Report()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def raw(client: Client, method: str, params: dict[str, Any]) -> dict[str, Any]:
    """Send one untyped JSON-RPC request through an established session."""
    return await client.session.send_request(Raw(method=method, params=params), DICT)


def rpc_error(exc: BaseException) -> dict[str, Any]:
    """Normalise an exception into {code, message} when it is an MCP error."""
    if isinstance(exc, MCPError):
        return {"code": exc.code, "message": exc.message, "data": exc.data}
    return {"code": None, "message": repr(exc)}


def shape(value: Any) -> Any:
    """Structural fingerprint: keys and types, ignoring scalar values."""
    if isinstance(value, dict):
        return {k: shape(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


def pretty(payload: Any, limit: int = 0) -> str:
    text = json.dumps(payload, indent=2, default=str)
    return text if limit <= 0 else text[:limit]


async def poll_until_terminal(
    client: Client, task_id: str, *, interval_ms: int, timeout_s: float = 120.0
) -> dict[str, Any]:
    """Poll tasks/get until the task is terminal or the ceiling expires."""
    deadline = time.monotonic() + timeout_s
    interval = max(interval_ms, 50) / 1000
    last: dict[str, Any] = {}
    while True:
        last = await raw(client, "tasks/get", {"taskId": task_id})
        if last.get("status") in {"completed", "failed", "cancelled"}:
            return last
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"task {task_id} not terminal after {timeout_s}s; last status="
                f"{last.get('status')!r}"
            )
        await asyncio.sleep(interval)


@dataclass(frozen=True)
class ProcRef:
    """Identity of a process that outlives PID reuse (pid + start time)."""

    pid: int
    ppid: int
    pgid: int
    create_time: float
    cmdline: str


#: Processes captured for the cancellable task, kept for the end-of-run sweep.
TASK_REFS: dict[int, ProcRef] = {}
TASK_REPO: Path | None = None


def _proc_ref(pid: int) -> ProcRef | None:
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            return ProcRef(
                pid=proc.pid,
                ppid=proc.ppid(),
                pgid=os.getpgid(proc.pid),
                create_time=proc.create_time(),
                cmdline=" ".join(proc.cmdline()),
            )
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
        return None


def daemon_pid(port: int, module: str) -> int | None:
    """PID listening on *port*, preferring the daemon module over port forwarders."""

    def score(pid: int) -> int:
        ref = _proc_ref(pid)
        return 0 if ref and module in ref.cmdline else 1

    candidates: set[int] = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN or not conn.pid or not conn.laddr:
            continue
        if conn.laddr.port != port:
            continue
        if conn.laddr.ip not in {"127.0.0.1", "::1", "0.0.0.0", "::"}:
            continue
        candidates.add(conn.pid)
    if not candidates:
        return None
    return sorted(candidates, key=score)[0]


def is_descendant(pid: int, root_pid: int) -> bool:
    """True when *pid* descends from *root_pid* (never treats the root as one)."""
    seen: set[int] = set()
    current = pid
    while current and current not in seen:
        if current == root_pid:
            return pid != root_pid
        seen.add(current)
        ref = _proc_ref(current)
        if ref is None:
            return False
        current = ref.ppid
    return False


def capture_task_group(token: str, root_pid: int) -> dict[int, ProcRef]:
    """Capture the process group(s) created for the command carrying *token*.

    The command runs through ``sh -c`` with ``start_new_session=True``, so the
    shell is a session/group leader and every descendant of the command shares
    its PGID. Matching the unique token only *finds* that leader; membership is
    then decided by PGID, and the returned PIDs (with their start times) are
    the only processes the cancellation assertion ever looks at.
    """
    leaders: set[int] = set()
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if token not in cmdline or proc.pid == os.getpid():
            continue
        if not is_descendant(proc.pid, root_pid):
            continue
        try:
            leaders.add(os.getpgid(proc.pid))
        except (ProcessLookupError, PermissionError):
            continue
    captured: dict[int, ProcRef] = {}
    if not leaders:
        return captured
    for proc in psutil.process_iter(["pid"]):
        try:
            pgid = os.getpgid(proc.pid)
        except (ProcessLookupError, PermissionError):
            continue
        if pgid in leaders:
            ref = _proc_ref(proc.pid)
            if ref is not None:
                captured[ref.pid] = ref
    return captured


def alive(ref: ProcRef) -> bool:
    """True while the exact process (pid *and* start time) is still running."""
    current = _proc_ref(ref.pid)
    return current is not None and abs(current.create_time - ref.create_time) < 0.01


async def wait_until_gone(refs: dict[int, ProcRef], timeout_s: float) -> list[ProcRef]:
    """Poll until every captured process is gone; return any survivors."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        survivors = [ref for ref in refs.values() if alive(ref)]
        if not survivors:
            return []
        await asyncio.sleep(0.25)
    return [ref for ref in refs.values() if alive(ref)]


def host_sleep60_scan(exclude: dict[int, ProcRef]) -> list[str]:
    """Informational host-wide view; never used for an assertion."""
    matches: list[str] = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if "sleep 60" in cmdline and proc.pid not in exclude:
            matches.append(f"{proc.pid} {cmdline}")
    return matches


def git(*args: str, cwd: Path | str | None = None) -> str:
    """Run a harmless git command inside the throwaway repo."""
    target = Path(cwd) if cwd is not None else TASK_REPO
    if target is None:
        raise RuntimeError("battle repo has not been created yet")
    proc = subprocess.run(["git", *args], cwd=target, capture_output=True, text=True, check=True)
    return proc.stdout.strip()


def branch_exists(branch: str) -> bool:
    return branch in git("branch", "--list", branch)


def setup_battle_repo() -> dict[str, Any]:
    """Create a unique throwaway repo with two unmerged ninja/* branches."""
    global TASK_REPO
    repo = Path(tempfile.mkdtemp(prefix=f"ninja-battle-repo-{RUN_ID}-"))
    TASK_REPO = repo
    git("init", "-q")
    git("symbolic-ref", "HEAD", "refs/heads/master")
    git("config", "user.email", "battle@example.invalid")
    git("config", "user.name", "Battle Test")

    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    git("add", "base.txt")
    git("commit", "-q", "-m", "base commit")

    made: list[str] = []
    for idx, branch in enumerate((BRANCH_A, BRANCH_B)):
        git("checkout", "-q", "-b", branch, "master")
        (repo / f"feature-{idx}.txt").write_text(f"unmerged work {idx}\n", encoding="utf-8")
        git("add", f"feature-{idx}.txt")
        git("commit", "-q", "-m", f"unmerged commit on {branch}")
        made.append(branch)
    git("checkout", "-q", "master")
    return {
        "repo": str(repo),
        "branches": made,
        "head": git("rev-parse", "--abbrev-ref", "HEAD"),
        "log": git("log", "--oneline", "--all", "--decorate"),
    }


# --------------------------------------------------------------------------- #
# A. Task lifecycle (agent)
# --------------------------------------------------------------------------- #


async def phase_a() -> None:
    phase = "A"
    started = time.perf_counter()
    args = {"command": "echo battle-ok", "repo_root": str(WORK_ROOT)}

    # Baseline: a client that does NOT declare the extension.
    async with Client(AGENT_URL, read_timeout_seconds=READ_TIMEOUT) as plain:
        sync = await plain.call_tool("agent_run_and_diagnose", args)
        baseline = {
            "type": type(sync).__name__,
            "is_error": sync.is_error,
            "structured": sync.structured_content,
            "text": sync.content[0].text if sync.content else None,
        }
    REPORT.payloads["A.sync_baseline"] = baseline
    REPORT.check(
        phase,
        "A.5a",
        "non-declaring client got a plain CallToolResult (never a task handle)",
        isinstance(sync, types.CallToolResult)
        and not isinstance(sync, types.InputRequiredResult)
        and getattr(sync, "result_type", None) != "task",
        {"class": type(sync).__name__, "is_error": sync.is_error},
    )
    REPORT.check(
        phase,
        "A.0",
        "synchronous baseline returned a structured result",
        bool(baseline["structured"]) and sync.is_error is False,
        {"structured_keys": sorted((baseline["structured"] or {}).keys())},
    )

    # Declaring client: the tools/call must answer with a task handle.
    async with Client(
        AGENT_URL,
        extensions=[advertise(TASKS_EXT)],
        read_timeout_seconds=READ_TIMEOUT,
    ) as client:
        extensions = client.server_capabilities.extensions or {}
        REPORT.check(
            phase,
            "A.1",
            "server advertises io.modelcontextprotocol/tasks",
            TASKS_EXT in extensions,
            {"protocol": client.protocol_version, "extensions": sorted(extensions)},
        )

        handle = await raw(
            client, "tools/call", {"name": "agent_run_and_diagnose", "arguments": args}
        )
        REPORT.payloads["A.task_handle"] = handle
        REPORT.check(
            phase,
            "A.2a",
            'response is a task handle: resultType == "task"',
            handle.get("resultType") == "task",
            {"resultType": handle.get("resultType"), "keys": sorted(handle)},
        )
        REPORT.check(
            phase,
            "A.2b",
            "taskId is a non-empty string",
            isinstance(handle.get("taskId"), str) and len(handle.get("taskId", "")) > 0,
            {"taskId": handle.get("taskId")},
        )
        REPORT.check(
            phase,
            "A.2c",
            "status in {working, completed}",
            handle.get("status") in {"working", "completed"},
            {"status": handle.get("status")},
        )
        ttl = handle.get("ttlMs")
        poll = handle.get("pollIntervalMs")
        REPORT.check(
            phase,
            "A.2d",
            "ttlMs or pollIntervalMs present and positive",
            (isinstance(ttl, int) and ttl > 0) or (isinstance(poll, int) and poll > 0),
            {"ttlMs": ttl, "pollIntervalMs": poll},
        )

        interval = poll if isinstance(poll, int) and poll > 0 else 500
        final = await poll_until_terminal(client, handle["taskId"], interval_ms=interval)
        REPORT.payloads["A.tasks_get_completed"] = final
        REPORT.check(
            phase,
            "A.3a",
            "polled task reached status == completed",
            final.get("status") == "completed",
            {"status": final.get("status"), "statusMessage": final.get("statusMessage")},
        )
        task_result = final.get("result") or {}
        sync_struct = baseline["structured"] or {}
        task_struct = task_result.get("structuredContent") or {}
        REPORT.check(
            phase,
            "A.3b",
            "completed result carries content + structuredContent like the sync call",
            bool(task_result.get("content")) and shape(task_struct) == shape(sync_struct),
            {
                "task_result_keys": sorted(task_result),
                "shape_match": shape(task_struct) == shape(sync_struct),
                "sync_shape": shape(sync_struct),
                "task_shape": shape(task_struct),
            },
        )
        sync_text = baseline["text"] or ""
        task_text = (task_result.get("content") or [{}])[0].get("text") or ""
        try:
            sync_json = json.loads(sync_text)
            task_json = json.loads(task_text)
        except (TypeError, ValueError):
            sync_json = task_json = None
        REPORT.check(
            phase,
            "A.3c",
            "text payload has the same JSON keys as the synchronous call",
            sync_json is not None
            and task_json is not None
            and sorted(sync_json) == sorted(task_json),
            {
                "sync_keys": sorted(sync_json) if isinstance(sync_json, dict) else None,
                "task_keys": sorted(task_json) if isinstance(task_json, dict) else None,
                "task_is_error": task_result.get("isError"),
            },
        )

        unknown = None
        try:
            await raw(client, "tasks/get", {"taskId": "no-such-task-battle"})
        except BaseException as exc:
            unknown = rpc_error(exc)
        REPORT.payloads["A.unknown_task_error"] = unknown
        REPORT.check(
            phase,
            "A.4",
            "tasks/get on an unknown task id -> -32602",
            isinstance(unknown, dict) and unknown.get("code") == -32602,
            unknown,
        )

    REPORT.timings["A lifecycle (agent)"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# Phase B: cancellation (agent)
# --------------------------------------------------------------------------- #


async def phase_b() -> None:
    phase = "B"
    started = time.perf_counter()
    # ``; : token`` keeps ``sh`` alive instead of exec-ing ``sleep``, so the
    # unique token stays in the shell's argv and identifies the exact process
    # group created for this task. Cancellation is then asserted by PID.
    token = f"battle-cancel-{RUN_ID}-{uuid.uuid4().hex[:8]}"
    command = f"sleep 60; : {token}"
    args = {"steps": [{"command": command}], "repo_root": str(WORK_ROOT)}

    agent_root = daemon_pid(PORTS["agent"], "ninja_agent")
    REPORT.check(
        phase,
        "B.0",
        "agent daemon PID resolved for PID-scoped cancellation",
        agent_root is not None,
        {"port": PORTS["agent"], "pid": agent_root},
    )

    captured: dict[int, ProcRef] = {}
    async with Client(
        AGENT_URL,
        extensions=[advertise(TASKS_EXT)],
        read_timeout_seconds=READ_TIMEOUT,
    ) as client:
        handle = await raw(client, "tools/call", {"name": "agent_exec_pipeline", "arguments": args})
        REPORT.payloads["B.task_handle"] = handle
        REPORT.check(
            phase,
            "B.1a",
            'long tool answered with a task handle (resultType == "task")',
            handle.get("resultType") == "task" and isinstance(handle.get("taskId"), str),
            {
                "resultType": handle.get("resultType"),
                "taskId": handle.get("taskId"),
                "status": handle.get("status"),
            },
        )

        # Confirm it is genuinely long-running before cancelling.
        await asyncio.sleep(2.0)
        mid = await raw(client, "tasks/get", {"taskId": handle["taskId"]})
        REPORT.check(
            phase,
            "B.1b",
            "task is still working after 2 s",
            mid.get("status") == "working",
            {"status": mid.get("status")},
        )

        if agent_root is not None:
            for _ in range(20):  # up to 5 s for the group to appear
                captured = capture_task_group(token, agent_root)
                if captured:
                    break
                await asyncio.sleep(0.25)
        TASK_REFS.update(captured)
        REPORT.payloads["B.task_processes"] = {
            str(pid): asdict(ref) for pid, ref in captured.items()
        }
        REPORT.check(
            phase,
            "B.1c",
            "the task's own process group is live before cancellation (PID-scoped)",
            bool(captured),
            {
                "daemon_pid": agent_root,
                "pids": sorted(captured),
                "processes": [ref.cmdline for ref in captured.values()],
            },
        )

        cancel_ack: dict[str, Any] | None = None
        cancel_error = None
        try:
            cancel_ack = await raw(client, "tasks/cancel", {"taskId": handle["taskId"]})
        except BaseException as exc:
            cancel_error = rpc_error(exc)
        REPORT.payloads["B.cancel_ack"] = cancel_ack
        REPORT.check(
            phase,
            "B.3",
            'tasks/cancel ack is resultType == "complete"',
            cancel_ack is not None
            and cancel_ack.get("resultType") == "complete"
            and cancel_error is None,
            cancel_ack if cancel_error is None else {"error": cancel_error},
        )

        final = await poll_until_terminal(
            client,
            handle["taskId"],
            interval_ms=handle.get("pollIntervalMs") or 500,
            timeout_s=120.0,
        )
        REPORT.payloads["B.tasks_get_cancelled"] = final
        REPORT.check(
            phase,
            "B.4",
            "polled task is terminal after cancel (cancelled preferred)",
            final.get("status") in {"cancelled", "failed"},
            {"status": final.get("status"), "statusMessage": final.get("statusMessage")},
        )
        REPORT.notes.append(
            f"B.4 cancel outcome: status={final.get('status')!r} "
            f"statusMessage={final.get('statusMessage')!r}"
        )

        second = None
        second_error = None
        try:
            second = await raw(client, "tasks/cancel", {"taskId": handle["taskId"]})
        except BaseException as exc:
            second_error = rpc_error(exc)
        REPORT.check(
            phase,
            "B.5",
            "second tasks/cancel is idempotent (no error)",
            second_error is None and isinstance(second, dict),
            second if second_error is None else {"error": second_error},
        )

    # PID-scoped: only the group captured for this task is asserted gone.
    survivors = await wait_until_gone(captured, timeout_s=15.0)
    REPORT.payloads["B.survivors"] = [asdict(ref) for ref in survivors]
    REPORT.check(
        phase,
        "B.6",
        "every PID captured for the task is gone after cancellation",
        bool(captured) and not survivors,
        {
            "captured_pids": sorted(captured),
            "survivors": [f"{ref.pid} {ref.cmdline}" for ref in survivors],
        },
    )
    # Host-wide view, informational only: unrelated `sleep 60` processes are
    # expected on a shared host and must not influence any assertion.
    unrelated = host_sleep60_scan(captured)
    REPORT.payloads["B.unrelated_sleep60_hostwide"] = unrelated
    REPORT.notes.append(
        f"B.6 ignored {len(unrelated)} unrelated host process(es) matching 'sleep 60' "
        "(PID scoping); they are reported here, never asserted on."
    )

    REPORT.timings["B cancellation (agent)"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# C. Legacy isolation (agent)
# --------------------------------------------------------------------------- #


async def phase_c() -> None:
    phase = "C"
    started = time.perf_counter()
    args = {"command": "echo battle-legacy", "repo_root": str(WORK_ROOT)}

    async with Client(AGENT_URL, mode="legacy", read_timeout_seconds=READ_TIMEOUT) as client:
        result = await client.call_tool("agent_run_and_diagnose", args)
        REPORT.check(
            phase,
            "C.1",
            "legacy client gets a synchronous CallToolResult, never a task handle",
            isinstance(result, types.CallToolResult)
            and not isinstance(result, types.InputRequiredResult)
            and getattr(result, "result_type", None) != "task",
            {
                "protocol": client.protocol_version,
                "class": type(result).__name__,
                "is_error": result.is_error,
                "text_head": (result.content[0].text or "")[:160] if result.content else None,
            },
        )

        legacy_get = None
        try:
            await raw(client, "tasks/get", {"taskId": "anything"})
        except BaseException as exc:
            legacy_get = rpc_error(exc)
        REPORT.check(
            phase,
            "C.2",
            "tasks/get over a legacy connection -> -32601",
            isinstance(legacy_get, dict) and legacy_get.get("code") == -32601,
            legacy_get,
        )

    REPORT.timings["C legacy isolation (agent)"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# D. Elicitation / MRTR (coder) -- DECLINE ONLY
# --------------------------------------------------------------------------- #


def _decode_state_parts(token: str) -> dict[str, Any]:
    """Inspect a sealed requestState without ever writing it back."""
    info: dict[str, Any] = {
        "prefix": token[:20],
        "length": len(token),
        "format": token.split(".", 1)[0] if "." in token else "<none>",
    }
    body = token.split(".", 1)[1] if "." in token else token
    padded = body + "=" * (-len(body) % 4)
    try:
        raw_bytes = base64.urlsafe_b64decode(padded)
    except Exception as exc:
        info["base64url_decode"] = f"failed: {exc!r}"
        return info
    info["decoded_bytes"] = len(raw_bytes)
    info["decoded_hex_prefix"] = raw_bytes[:16].hex()
    try:
        info["decoded_utf8"] = raw_bytes.decode("utf-8")
    except UnicodeDecodeError:
        info["decoded_utf8"] = "<not utf-8: sealed ciphertext>"
    return info


async def phase_d() -> None:
    phase = "D"
    started = time.perf_counter()

    setup_started = time.perf_counter()
    repo_info = setup_battle_repo()
    REPORT.payloads["D.repo_setup"] = repo_info
    REPORT.timings["D0 repo setup"] = time.perf_counter() - setup_started
    REPORT.check(
        phase,
        "D.0",
        "throwaway repo has two unmerged ninja/* branches on master",
        branch_exists(BRANCH_A) and branch_exists(BRANCH_B) and repo_info["head"] == "master",
        repo_info,
    )

    confirm_key = "confirm_branch_delete"

    # -- D.1/D.2/D.3: the first (input_required) round -----------------------
    async with Client(CODER_URL, read_timeout_seconds=READ_TIMEOUT) as client:
        first = await raw(
            client,
            "tools/call",
            {
                "name": "coder_branch_discard",
                "arguments": {"repo_root": str(TASK_REPO), "branch": BRANCH_A},
            },
        )
        REPORT.payloads["D.input_required"] = first
        REPORT.check(
            phase,
            "D.1",
            'first response is resultType == "input_required"',
            first.get("resultType") == "input_required",
            {"resultType": first.get("resultType"), "keys": sorted(first)},
        )

        requests = first.get("inputRequests") or {}
        REPORT.check(
            phase,
            "D.2a",
            "exactly one inputRequests key",
            isinstance(requests, dict) and len(requests) == 1,
            {"keys": sorted(requests) if isinstance(requests, dict) else requests},
        )
        REPORT.check(
            phase,
            "D.2b",
            f"input request key is {confirm_key!r}",
            list(requests) == [confirm_key],
            {"keys": sorted(requests)},
        )
        state = first.get("requestState")
        REPORT.check(
            phase,
            "D.2c",
            "requestState is a non-empty sealed string",
            isinstance(state, str) and len(state) > 0,
            {"requestState_prefix": (state or "")[:20], "length": len(state or "")},
        )

        elicit = requests.get(confirm_key) or {}
        params = elicit.get("params") or {}
        schema = params.get("requestedSchema") or {}
        props = schema.get("properties") or {}
        REPORT.check(
            phase,
            "D.2d",
            "requestedSchema requires a boolean `confirm`",
            elicit.get("method") == "elicitation/create"
            and (props.get("confirm") or {}).get("type") == "boolean"
            and "confirm" in (schema.get("required") or []),
            {
                "method": elicit.get("method"),
                "message": params.get("message"),
                "schema": schema,
            },
        )

        decode = _decode_state_parts(state or "")
        REPORT.payloads["D.request_state_inspection"] = decode
        REPORT.check(
            phase,
            "D.3a",
            "sealed requestState leaks neither branch name nor repo path in cleartext",
            BRANCH_A not in (state or "")
            and str(TASK_REPO) not in (state or "")
            and BRANCH_A not in str(decode.get("decoded_utf8", ""))
            and str(TASK_REPO) not in str(decode.get("decoded_utf8", "")),
            decode,
        )
        REPORT.check(
            phase,
            "D.3b",
            "sealed requestState is not plaintext JSON (decoded body is ciphertext)",
            not str(decode.get("decoded_utf8", "")).lstrip().startswith("{"),
            {"utf8": decode.get("decoded_utf8"), "bytes": decode.get("decoded_bytes")},
        )

        # Obtain a second, different operation's state for the tamper test.
        other = await raw(
            client,
            "tools/call",
            {
                "name": "coder_branch_discard",
                "arguments": {"repo_root": str(TASK_REPO), "branch": BRANCH_B},
            },
        )
        other_state = other.get("requestState")
        REPORT.check(
            phase,
            "D.5a",
            "a second branch produced its own distinct requestState",
            isinstance(other_state, str) and bool(other_state) and other_state != state,
            {
                "other_prefix": (other_state or "")[:20],
                "distinct": other_state != state,
            },
        )

    # -- D.4: real client declines through the SDK MRTR driver ---------------
    declined: list[dict[str, Any]] = []

    async def decline_callback(_context: Any, elicit_params: Any) -> types.ElicitResult:
        declined.append(
            {
                "message": elicit_params.message,
                "requested_schema": elicit_params.requested_schema,
                "action": "decline",
            }
        )
        return types.ElicitResult(action="decline")

    async with Client(
        CODER_URL,
        elicitation_callback=decline_callback,
        read_timeout_seconds=READ_TIMEOUT,
    ) as client:
        refusal = await client.call_tool(
            "coder_branch_discard",
            {"repo_root": str(TASK_REPO), "branch": BRANCH_A},
        )
        text = refusal.content[0].text if refusal.content else None
        REPORT.payloads["D.decline_refusal"] = {
            "class": type(refusal).__name__,
            "is_error": refusal.is_error,
            "text": text,
            "structured": refusal.structured_content,
            "callbacks": declined,
        }
        REPORT.check(
            phase,
            "D.4a",
            "decline resolved to a terminal CallToolResult, not another input_required",
            isinstance(refusal, types.CallToolResult)
            and not isinstance(refusal, types.InputRequiredResult),
            {"class": type(refusal).__name__, "is_error": refusal.is_error},
        )
        REPORT.check(
            phase,
            "D.4b",
            "decline produced the normal unmerged-branch refusal",
            "not fully merged" in (text or "").lower()
            or (refusal.structured_content or {}).get("status") == "error",
            {"text": (text or "")[:400], "structured": refusal.structured_content},
        )
        REPORT.check(
            phase,
            "D.4c",
            "the elicitation callback actually ran with the confirm form",
            len(declined) == 1 and "confirm" in json.dumps(declined[0]),
            {"callbacks": declined},
        )

    REPORT.check(
        phase,
        "D.4d",
        "branch still exists after the decline",
        branch_exists(BRANCH_A),
        {"branches": git("branch", "--list", "ninja/*").splitlines()},
    )

    # -- D.5: replay with another branch's sealed state -> -32602 ------------
    tamper = None
    async with Client(CODER_URL, read_timeout_seconds=READ_TIMEOUT) as client:
        try:
            await client.call_tool(
                "coder_branch_discard",
                {"repo_root": str(TASK_REPO), "branch": BRANCH_A},
                input_responses={confirm_key: types.ElicitResult(action="decline")},
                request_state=other_state,
            )
        except BaseException as exc:
            tamper = rpc_error(exc)
    REPORT.payloads["D.tamper_error"] = tamper
    REPORT.check(
        phase,
        "D.5b",
        "replaying a foreign requestState raises -32602",
        isinstance(tamper, dict) and tamper.get("code") == -32602,
        tamper,
    )
    branches_after_tamper = git("branch", "--list", "ninja/*").splitlines()
    REPORT.check(
        phase,
        "D.5c",
        "nothing was deleted by the tampered replay",
        branch_exists(BRANCH_A) and branch_exists(BRANCH_B),
        {"branches": branches_after_tamper},
    )

    # -- D.6: legacy client must use the old push path ------------------------
    legacy_elicit: list[dict[str, Any]] = []

    async def legacy_decline(_context: Any, elicit_params: Any) -> types.ElicitResult:
        legacy_elicit.append(
            {
                "message": elicit_params.message,
                "requested_schema": elicit_params.requested_schema,
            }
        )
        return types.ElicitResult(action="decline")

    legacy_text = None
    legacy_error = None
    legacy_class = None
    try:
        async with Client(
            CODER_URL,
            mode="legacy",
            elicitation_callback=legacy_decline,
            read_timeout_seconds=READ_TIMEOUT,
        ) as client:
            legacy_result = await client.call_tool(
                "coder_branch_discard",
                {"repo_root": str(TASK_REPO), "branch": BRANCH_A},
            )
            legacy_class = type(legacy_result).__name__
            legacy_text = legacy_result.content[0].text if legacy_result.content else None
            REPORT.payloads["D.legacy"] = {
                "protocol": client.protocol_version,
                "class": legacy_class,
                "is_error": legacy_result.is_error,
                "text": legacy_text,
                "structured": legacy_result.structured_content,
                "elicitations": legacy_elicit,
            }
    except BaseException as exc:
        legacy_error = rpc_error(exc)
        legacy_class = f"raised {type(exc).__name__}"
        REPORT.payloads["D.legacy"] = {"error": legacy_error, "elicitations": legacy_elicit}

    REPORT.check(
        phase,
        "D.6a",
        "legacy client never receives input_required (push path or plain result)",
        legacy_class != "InputRequiredResult",
        REPORT.payloads["D.legacy"],
    )
    REPORT.check(
        phase,
        "D.6b",
        "legacy branch-discard did not delete the branch",
        branch_exists(BRANCH_A),
        {
            "branches": git("branch", "--list", "ninja/*").splitlines(),
            "text": (legacy_text or "")[:300],
            "error": legacy_error,
        },
    )

    REPORT.timings["D elicitation/MRTR (coder)"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# Phase E: concurrency (agent)
# --------------------------------------------------------------------------- #


async def phase_e() -> None:
    phase = "E"
    started = time.perf_counter()
    count = 5
    args_list = [
        {"command": f"echo battle-{idx}", "repo_root": str(WORK_ROOT)} for idx in range(count)
    ]

    async with Client(
        AGENT_URL,
        extensions=[advertise(TASKS_EXT)],
        read_timeout_seconds=READ_TIMEOUT,
    ) as client:
        handles = await asyncio.gather(
            *[
                raw(
                    client,
                    "tools/call",
                    {"name": "agent_run_and_diagnose", "arguments": args},
                )
                for args in args_list
            ]
        )
        REPORT.payloads["E.handles"] = handles
        ids = [h.get("taskId") for h in handles]
        REPORT.check(
            phase,
            "E.1",
            f"{count} concurrent submissions each returned a task handle",
            len(handles) == count and all(h.get("resultType") == "task" for h in handles),
            {"resultTypes": [h.get("resultType") for h in handles], "ids": ids},
        )
        REPORT.check(
            phase,
            "E.2",
            "all taskIds are distinct",
            len(set(ids)) == count,
            {"ids": ids},
        )

        finals = await asyncio.gather(
            *[
                poll_until_terminal(client, h["taskId"], interval_ms=h.get("pollIntervalMs") or 500)
                for h in handles
            ]
        )
        REPORT.payloads["E.finals"] = finals
        statuses = [f.get("status") for f in finals]
        REPORT.check(
            phase,
            "E.3",
            "all 5 tasks reached completed",
            all(status == "completed" for status in statuses),
            {"statuses": statuses},
        )
        outputs = []
        for idx, final in enumerate(finals):
            struct = (final.get("result") or {}).get("structuredContent") or {}
            outputs.append(struct.get("condensed_output"))
        REPORT.check(
            phase,
            "E.4",
            "each completed task carries its own correct result",
            outputs == [f"battle-{idx}" for idx in range(count)],
            {"outputs": outputs},
        )

    REPORT.timings["E concurrency (agent)"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# F. Advertised contracts verified live (read-only)
# --------------------------------------------------------------------------- #


async def phase_f() -> None:
    phase = "F"
    started = time.perf_counter()

    async with Client(CODER_URL, read_timeout_seconds=READ_TIMEOUT) as client:
        unknown = await client.call_tool("this_tool_does_not_exist", {})
        unknown_text = " ".join(c.text for c in unknown.content if isinstance(c, types.TextContent))
        REPORT.check(
            phase,
            "F.1",
            "unknown tool -> is_error=True",
            unknown.is_error is True,
            {"is_error": unknown.is_error, "text": unknown_text[:200]},
        )

        wrong_job = await client.call_tool("coder_job_status", {"job_id": 12345})
        wrong_text = " ".join(c.text for c in wrong_job.content if isinstance(c, types.TextContent))
        REPORT.check(
            phase,
            "F.2",
            'coder_job_status {"job_id": 12345} -> is_error=True, "job_id must be a string"',
            wrong_job.is_error is True and "job_id must be a string" in wrong_text,
            {"is_error": wrong_job.is_error, "text": wrong_text[:300]},
        )

    async with Client(SECRETARY_URL, read_timeout_seconds=READ_TIMEOUT) as client:
        listing = await client.list_tools()
        search = next(t for t in listing.tools if t.name == "secretary_file_search")
        required = (search.input_schema or {}).get("required") or []
        REPORT.check(
            phase,
            "F.3",
            "secretary_file_search schema requires both pattern and repo_root",
            "pattern" in required and "repo_root" in required,
            {"required": required},
        )

    REPORT.timings["F advertised contracts"] = time.perf_counter() - started


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #


def report_payload(exit_code: int) -> dict[str, Any]:
    """Machine-readable rendering of everything the suite observed."""
    passed = sum(1 for c in REPORT.checks if c.ok)
    return {
        "suite": "tasks",
        "generated_at": datetime.now(UTC).isoformat(),
        "mcp_protocol": "2026-07-28",
        "run_id": RUN_ID,
        "servers": {
            key: {"port": port, "url": f"http://127.0.0.1:{port}/mcp"}
            for key, port in PORTS.items()
        },
        "work_root": str(WORK_ROOT),
        "repo": str(TASK_REPO) if TASK_REPO is not None else None,
        "summary": {
            "total": len(REPORT.checks),
            "passed": passed,
            "failed": len(REPORT.checks) - passed,
            "exit_code": exit_code,
        },
        "checks": [asdict(c) for c in REPORT.checks],
        "payloads": REPORT.payloads,
        "timings": REPORT.timings,
        "notes": REPORT.notes,
        "captured_task_processes": {str(pid): asdict(ref) for pid, ref in TASK_REFS.items()},
    }


async def main(ports: dict[str, int], json_path: str | None) -> int:
    global PORTS, AGENT_URL, CODER_URL, SECRETARY_URL
    grand_start = time.perf_counter()
    PORTS = ports
    AGENT_URL = f"http://127.0.0.1:{PORTS['agent']}/mcp"
    CODER_URL = f"http://127.0.0.1:{PORTS['coder']}/mcp"
    SECRETARY_URL = f"http://127.0.0.1:{PORTS['secretary']}/mcp"

    print("=" * 78)
    print("ninja-mcp live tasks / elicitation battle suite")
    print("protocol=2026-07-28  " + "  ".join(f"{k}:{v}" for k, v in PORTS.items()))
    print(f"work_root={WORK_ROOT}")
    print("=" * 78)

    for phase, coro in (
        ("A", phase_a),
        ("B", phase_b),
        ("C", phase_c),
        ("D", phase_d),
        ("E", phase_e),
        ("F", phase_f),
    ):
        try:
            await coro()
        except BaseException as exc:
            REPORT.phase_failed(phase, exc)
            import traceback

            REPORT.notes.append(
                f"{phase} traceback: " + traceback.format_exc().replace("\n", " | ")[:1500]
            )

    # Final safety sweep, independent of the phases.
    branch_list = (
        git("branch", "--list", "ninja/*").splitlines()
        if TASK_REPO is not None and (TASK_REPO / ".git").is_dir()
        else []
    )
    survivors = await wait_until_gone(TASK_REFS, timeout_s=10.0)
    unrelated = host_sleep60_scan(TASK_REFS)
    REPORT.payloads["final.branches"] = branch_list
    REPORT.payloads["final.task_pids"] = {str(pid): asdict(ref) for pid, ref in TASK_REFS.items()}
    REPORT.payloads["final.task_survivors"] = [asdict(ref) for ref in survivors]
    REPORT.payloads["final.unrelated_sleep60_hostwide"] = unrelated
    REPORT.check(
        "SAFETY", "S.1", "no battle branch was deleted", len(branch_list) == 2, branch_list
    )
    REPORT.check(
        "SAFETY",
        "S.2",
        "no PID captured for a cancelled task remains (PID-scoped)",
        not survivors,
        {
            "captured_pids": sorted(TASK_REFS),
            "survivors": [f"{ref.pid} {ref.cmdline}" for ref in survivors],
            "unrelated_host_sleep60_ignored": unrelated,
        },
    )
    REPORT.notes.append(
        f"S.2 re-checked only the {len(TASK_REFS)} PID(s) captured from this run's task; "
        f"{len(unrelated)} unrelated 'sleep 60' host process(es) were ignored."
    )

    REPORT.timings["TOTAL"] = time.perf_counter() - grand_start
    REPORT.notes.append(f"throwaway repo: {TASK_REPO}  work_root: {WORK_ROOT}")
    print(REPORT.dump())

    failed = [c for c in REPORT.checks if not c.ok]
    exit_code = 0 if not failed else 1
    if json_path:
        payload = report_payload(exit_code)
        Path(json_path).parent.mkdir(parents=True, exist_ok=True)
        Path(json_path).write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        print(f"\nJSON report written to {json_path}")
    return exit_code


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Live MCP tasks / elicitation battle suite for running ninja-mcp daemons.",
    )
    parser.add_argument(
        "--ports",
        metavar="MODULE=PORT,...",
        help="Override daemon ports, e.g. agent=8106,coder=8100 "
        "(defaults: NINJA_AGENT_PORT etc., then 8100/8101/8106/8107)",
    )
    parser.add_argument(
        "--json",
        metavar="PATH",
        help="Write a machine-readable JSON report to PATH",
    )
    args = parser.parse_args(argv)
    return asyncio.run(main(resolve_ports(args.ports), args.json))


if __name__ == "__main__":
    sys.exit(cli())
