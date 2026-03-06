"""
OpenCode server pool — long-running `opencode serve` instances, one per project directory.

Replaces per-task subprocess spawning with a persistent HTTP server, eliminating:
- Process spawn overhead on every task
- Pyright/tsserver re-initialization on every task
- Zombie processes and process group management

Architecture:
    pool[repo_root] -> ServerInstance(port, process)
    execute(repo_root, prompt, model) ->
        1. GET or START server for repo_root
        2. POST /session  (fresh session per task)
        3. POST /session/{id}/prompt_async
        4. GET /event (SSE) — wait for session.idle
        5. Return result with files changed

Session reuse: fresh session per task to avoid growing context and cross-task pollution.
Server reuse: one serve process per project directory, kept alive across tasks.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path

import aiohttp

from ninja_common.logging_utils import get_logger


logger = get_logger(__name__)

# Port range for serve instances
_PORT_START = int(os.environ.get("NINJA_OPENCODE_SERVE_PORT_START", "20000"))
_PORT_END = int(os.environ.get("NINJA_OPENCODE_SERVE_PORT_END", "21000"))
_READY_TIMEOUT = 15  # seconds to wait for server to become ready
_SSE_TASK_TIMEOUT = int(os.environ.get("NINJA_OPENCODE_SERVE_TIMEOUT", "600"))  # per-task


@dataclass
class ServerInstance:
    port: int
    process: subprocess.Popen
    repo_root: str
    started_at: float = field(default_factory=time.time)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def is_alive(self) -> bool:
        return self.process.poll() is None


@dataclass
class ExecutionResult:
    success: bool
    files_changed: list[str]
    summary: str
    session_id: str | None = None
    raw_diff: list[dict] | None = None


class OpenCodeServerPool:
    """Pool of `opencode serve` instances — one per project directory.

    Thread/coroutine safe via asyncio.Lock per repo_root.
    Instances are started lazily on first request and kept alive.
    Call `stop_all()` on daemon shutdown.
    """

    def __init__(self, bin_path: str = "opencode") -> None:
        self._bin_path = bin_path
        self._instances: dict[str, ServerInstance] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._pool_lock = asyncio.Lock()
        self._next_port = _PORT_START

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        repo_root: str,
        prompt: str,
        model: str | None = None,
        timeout: int = _SSE_TASK_TIMEOUT,
    ) -> ExecutionResult:
        """Execute a task in the given repo via opencode serve REST API."""
        repo_root = str(Path(repo_root).resolve())
        instance = await self._get_or_start(repo_root, model=model)

        async with aiohttp.ClientSession() as http:
            session_id = await self._create_session(http, instance)
            logger.info(f"[pool] session {session_id} created for {repo_root}")

            await self._send_prompt(http, instance, session_id, prompt)
            logger.info(f"[pool] prompt sent to session {session_id}")

            result = await self._wait_for_idle(http, instance, session_id, timeout=timeout)
            logger.info(f"[pool] session {session_id} completed: {result.summary}")
            return result

    async def stop_all(self) -> None:
        """Terminate all server instances. Call on daemon shutdown."""
        async with self._pool_lock:
            for key, inst in list(self._instances.items()):
                logger.info(f"[pool] stopping server on port {inst.port} ({key})")
                try:
                    inst.process.terminate()
                    inst.process.wait(timeout=5)
                except Exception:
                    inst.process.kill()
            self._instances.clear()

    def instance_count(self) -> int:
        return len(self._instances)

    # ------------------------------------------------------------------
    # Server lifecycle
    # ------------------------------------------------------------------

    async def _get_or_start(self, repo_root: str, model: str | None = None) -> ServerInstance:
        async with self._pool_lock:
            if repo_root not in self._locks:
                self._locks[repo_root] = asyncio.Lock()

        async with self._locks[repo_root]:
            existing = self._instances.get(repo_root)
            if existing and existing.is_alive():
                return existing
            if existing:
                logger.warning(f"[pool] server for {repo_root} died, restarting")

            inst = await self._start_server(repo_root, model=model)
            self._instances[repo_root] = inst
            return inst

    async def _start_server(self, repo_root: str, model: str | None = None) -> ServerInstance:
        port = self._alloc_port()
        env = self._build_env(model)

        logger.info(f"[pool] starting opencode serve on port {port} in {repo_root}")
        process = subprocess.Popen(
            [self._bin_path, "serve", "--port", str(port), "--hostname", "127.0.0.1"],
            cwd=repo_root,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        inst = ServerInstance(port=port, process=process, repo_root=repo_root)
        await self._wait_ready(inst)
        logger.info(f"[pool] server ready on port {port}")
        return inst

    async def _wait_ready(self, inst: ServerInstance, timeout: float = _READY_TIMEOUT) -> None:
        deadline = time.time() + timeout
        url = f"{inst.base_url}/session"
        async with aiohttp.ClientSession() as http:
            while time.time() < deadline:
                if not inst.is_alive():
                    raise RuntimeError(
                        f"opencode serve (port {inst.port}) exited before becoming ready"
                    )
                try:
                    async with http.get(url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                        if resp.status < 500:
                            return
                except (TimeoutError, aiohttp.ClientError):
                    pass
                await asyncio.sleep(0.5)
        raise TimeoutError(
            f"opencode serve on port {inst.port} did not become ready within {timeout}s"
        )

    def _alloc_port(self) -> int:
        port = self._next_port
        self._next_port = port + 1
        if self._next_port > _PORT_END:
            self._next_port = _PORT_START
        return port

    @staticmethod
    def _build_env(model: str | None = None) -> dict[str, str]:
        env = os.environ.copy()
        if model:
            # opencode respects OPENCODE_MODEL env var for default model
            env["OPENCODE_MODEL"] = model
        return env

    # ------------------------------------------------------------------
    # REST API helpers
    # ------------------------------------------------------------------

    async def _create_session(self, http: aiohttp.ClientSession, inst: ServerInstance) -> str:
        async with http.post(f"{inst.base_url}/session", json={}) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["id"]

    async def _send_prompt(
        self,
        http: aiohttp.ClientSession,
        inst: ServerInstance,
        session_id: str,
        prompt: str,
    ) -> None:
        body = {"parts": [{"type": "text", "text": prompt}]}
        async with http.post(
            f"{inst.base_url}/session/{session_id}/prompt_async", json=body
        ) as resp:
            if resp.status not in (200, 204):
                text = await resp.text()
                raise RuntimeError(f"prompt_async failed ({resp.status}): {text}")

    async def _wait_for_idle(
        self,
        http: aiohttp.ClientSession,
        inst: ServerInstance,
        session_id: str,
        timeout: int,
    ) -> ExecutionResult:
        """Stream SSE events until session.idle for our session_id."""
        files_changed: list[str] = []
        diff: list[dict] = []
        deadline = time.time() + timeout

        async with http.get(
            f"{inst.base_url}/event",
            timeout=aiohttp.ClientTimeout(total=timeout + 10),
        ) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                if time.time() > deadline:
                    raise TimeoutError(
                        f"Task in session {session_id} did not complete within {timeout}s"
                    )

                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue

                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                etype = event.get("type", "")
                props = event.get("properties", {})

                # Only care about events for our session
                event_sid = props.get("sessionID")
                if event_sid and event_sid != session_id:
                    continue

                if etype == "file.edited":
                    fpath = props.get("file", "")
                    if fpath:
                        # Convert absolute path to relative to repo_root
                        try:
                            rel = str(Path(fpath).relative_to(inst.repo_root))
                        except ValueError:
                            rel = fpath
                        if rel not in files_changed:
                            files_changed.append(rel)

                elif etype == "session.diff":
                    diff = props.get("diff", [])

                elif etype == "session.idle":
                    # Task complete
                    break

                elif etype == "session.status":
                    status_type = props.get("status", {}).get("type", "")
                    if status_type == "idle":
                        break

        # Build result
        if not files_changed and diff:
            files_changed = [d["file"] for d in diff if d.get("file")]

        if files_changed:
            flist = ", ".join(files_changed[:5])
            if len(files_changed) > 5:
                flist += f" and {len(files_changed) - 5} more"
            summary = f"Modified {len(files_changed)} file(s): {flist}"
        else:
            summary = "Task completed (no file changes detected)"

        return ExecutionResult(
            success=True,
            files_changed=files_changed,
            summary=summary,
            session_id=session_id,
            raw_diff=diff if diff else None,
        )


# Singleton pool — shared across all driver invocations in this process
_pool: OpenCodeServerPool | None = None


def get_pool(bin_path: str = "opencode") -> OpenCodeServerPool:
    """Get or create the process-wide server pool."""
    global _pool
    if _pool is None:
        _pool = OpenCodeServerPool(bin_path=bin_path)
    return _pool
