"""Cancel-aware subprocess execution shared by the ninja servers.

``subprocess.run`` (and any ``asyncio.to_thread`` wrapper around it) cannot be
interrupted: cancelling the awaiting asyncio task leaves the OS process and its
children running. Every tool that executes a shell command inside an MCP task
therefore has to spawn the command in its own process group, bind it to the
ambient :class:`~ninja_common.mcp_tasks.TaskCancellation`, and tear the whole
group down when the task is cancelled or times out.

:func:`run_cancellable` is that primitive. It is a drop-in replacement for the
subset of ``subprocess.run`` the runners use: it returns an object exposing
``returncode``, ``stdout`` and ``stderr`` (text), raises :class:`TimeoutError`
on timeout, and raises :class:`asyncio.CancelledError` when the task in the
current context is cancelled.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import subprocess
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

from ninja_common.mcp_tasks import get_task_cancellation


if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path


logger = logging.getLogger(__name__)

#: Seconds a process group gets to exit after SIGTERM before SIGKILL.
TERMINATION_GRACE_SECONDS: Final[float] = 5.0

#: Seconds to wait for a SIGKILLed process to be reaped.
_KILL_GRACE_SECONDS: Final[float] = 2.0


@dataclass(frozen=True)
class CompletedProcessLike:
    """The ``subprocess.CompletedProcess`` fields callers actually consume."""

    returncode: int
    stdout: str
    stderr: str


def _signal_group(process: asyncio.subprocess.Process, sig: int) -> None:
    """Send *sig* to *process*'s group, never to our own process group.

    ``run_cancellable`` always spawns with ``start_new_session=True``, so the
    child leads its own group and ``killpg(pid)`` reaches every descendant.
    The guard against our own pgid is belt-and-braces for a process that was
    handed in by a future caller.
    """
    pid = process.pid
    if process.returncode is not None or not pid:
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
    with suppress(ProcessLookupError, PermissionError, ValueError):
        process.send_signal(sig)


async def _terminate_group(
    process: asyncio.subprocess.Process,
    *,
    grace: float = TERMINATION_GRACE_SECONDS,
) -> None:
    """SIGTERM the process group, then SIGKILL it if it outlives *grace*."""
    if process.returncode is not None:
        return
    logger.debug("SIGTERM to process group %s", process.pid)
    _signal_group(process, signal.SIGTERM)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace)
        return
    except TimeoutError:
        pass
    except asyncio.CancelledError:
        # The caller is already unwinding; still make sure nothing survives.
        _signal_group(process, signal.SIGKILL)
        raise
    logger.warning("Process group %s ignored SIGTERM, sending SIGKILL", process.pid)
    _signal_group(process, signal.SIGKILL)
    with suppress(TimeoutError):
        await asyncio.wait_for(process.wait(), timeout=_KILL_GRACE_SECONDS)


async def _drain(process: asyncio.subprocess.Process, task: asyncio.Task[Any]) -> None:
    """Reap a torn-down process and its communicate task without raising."""
    if not task.done():
        with suppress(BaseException):
            await asyncio.wait_for(task, timeout=_KILL_GRACE_SECONDS)
    if not task.done():
        task.cancel()
        with suppress(BaseException):
            await task
    if process.returncode is None:
        with suppress(BaseException):
            await asyncio.wait_for(process.wait(), timeout=_KILL_GRACE_SECONDS)


def _spawn_kwargs(
    cwd: Path | str | None,
    env: Mapping[str, str] | None,
    stdin: Any,
    capture_output: bool,
) -> dict[str, Any]:
    """Build the common ``create_subprocess_*`` keyword arguments."""
    kwargs: dict[str, Any] = {
        "cwd": str(cwd) if cwd is not None else None,
        "env": dict(env) if env is not None else None,
        "stdin": stdin,
        # Own process group: cancellation can kill the whole tree, and a
        # terminal Ctrl-C aimed at the server never reaches the child.
        "start_new_session": True,
    }
    if capture_output:
        kwargs["stdout"] = asyncio.subprocess.PIPE
        kwargs["stderr"] = asyncio.subprocess.PIPE
    return kwargs


async def run_cancellable(
    argv: list[str] | str,
    *,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    shell: bool = False,
    env: Mapping[str, str] | None = None,
    capture_output: bool = True,
    stdin: Any = subprocess.DEVNULL,
) -> CompletedProcessLike:
    """Run a command in its own process group, cancellable as a unit.

    Args:
        argv: Argument vector, or a command line when ``shell`` is true.
        cwd: Working directory for the child.
        timeout: Wall-clock limit in seconds; ``None`` waits forever.
        shell: Run through the shell (``argv`` must then be a string).
        env: Complete environment for the child (replaces the inherited one).
        capture_output: Pipe stdout/stderr and return them as text.
        stdin: Passed to ``create_subprocess_*``; defaults to ``DEVNULL`` so a
            daemonised MCP server's transport stdin is never inherited.

    Returns:
        A :class:`CompletedProcessLike` with text ``stdout``/``stderr``.

    Raises:
        TimeoutError: The command outlived ``timeout``; its whole group was
            terminated first.
        asyncio.CancelledError: The ambient task was cancelled; its whole
            group was terminated before the exception propagated.
    """
    kwargs = _spawn_kwargs(cwd, env, stdin, capture_output)
    if shell:
        if not isinstance(argv, str):
            raise TypeError("argv must be a string when shell=True")
        process = await asyncio.create_subprocess_shell(argv, **kwargs)
    else:
        if isinstance(argv, str):
            raise TypeError("argv must be a sequence when shell=False")
        process = await asyncio.create_subprocess_exec(*argv, **kwargs)

    cancellation = get_task_cancellation()
    if cancellation is not None:
        cancellation.bind_process(process)

    communicate: asyncio.Task[tuple[bytes | None, bytes | None]] = asyncio.create_task(
        process.communicate()
    )
    cancel_waiter: asyncio.Task[None] | None = None
    if cancellation is not None:
        cancel_waiter = asyncio.create_task(cancellation.wait())
    waiters: set[asyncio.Task[Any]] = {communicate}
    if cancel_waiter is not None:
        waiters.add(cancel_waiter)

    try:
        done, _pending = await asyncio.wait(
            waiters,
            timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if communicate in done:
            stdout_raw, stderr_raw = communicate.result()
            return CompletedProcessLike(
                returncode=process.returncode if process.returncode is not None else -1,
                stdout=_decode(stdout_raw),
                stderr=_decode(stderr_raw),
            )
        if not done:
            raise TimeoutError(f"Command timed out after {timeout}s: {_display(argv)}")
        # A cancellation was requested while the command was still running.
        raise asyncio.CancelledError
    finally:
        for waiter in waiters:
            if waiter is not communicate and not waiter.done():
                waiter.cancel()
        if process.returncode is None:
            with suppress(BaseException):
                await _terminate_group(process)
        with suppress(BaseException):
            await _drain(process, communicate)
        if cancellation is not None:
            cancellation.unbind_process()


def _decode(raw: bytes | None) -> str:
    """Decode captured output as UTF-8, replacing invalid bytes."""
    if raw is None:
        return ""
    return raw.decode("utf-8", errors="replace")


def _display(argv: list[str] | str) -> str:
    """Short, log-safe rendering of the command."""
    text = argv if isinstance(argv, str) else " ".join(argv)
    return text[:200]


__all__ = [
    "TERMINATION_GRACE_SECONDS",
    "CompletedProcessLike",
    "run_cancellable",
]
