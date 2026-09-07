"""
OpenCode server pool — long-running `opencode serve` instances, one per project directory.

Replaces per-task subprocess spawning with a persistent HTTP server, eliminating:
- Process spawn overhead on every task
- Pyright/tsserver re-initialization on every task
- Zombie processes and process group management

Architecture:
    pool[repo_root] -> ServerInstance(port, process, sse_listener)
    execute(repo_root, prompt, model) ->
        1. GET or START server for repo_root
        2. POST /session  (fresh session per task)
        3. POST /session/{id}/prompt_async
        4. Wait for session.idle via shared SSE listener
        5. Return result with files changed

SSE multiplexing: one SSE connection per server instance, shared across all
concurrent tasks. Events are routed to per-session asyncio.Queue waiters.
This avoids the race condition where multiple SSE connections compete for events.
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


class SSEListener:
    """Shared SSE listener for a single opencode serve instance.

    Maintains one persistent SSE connection and routes events to
    per-session asyncio.Queue subscribers. This ensures parallel tasks
    on the same server all receive their events correctly.
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url
        self._subscribers: dict[str, asyncio.Queue] = {}
        self._lock = asyncio.Lock()
        self._task: asyncio.Task | None = None
        self._http: aiohttp.ClientSession | None = None

    async def start(self) -> None:
        """Start the background SSE reader loop."""
        if self._task and not self._task.done():
            return
        self._http = aiohttp.ClientSession()
        self._task = asyncio.create_task(self._reader_loop())

    async def stop(self) -> None:
        """Stop the SSE reader and close the HTTP session."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
        if self._http:
            await self._http.close()
            self._http = None

    async def subscribe(self, session_id: str) -> asyncio.Queue:
        """Register a queue for receiving events for the given session_id."""
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue()
            self._subscribers[session_id] = q
            return q

    async def unsubscribe(self, session_id: str) -> None:
        """Remove a session subscriber."""
        async with self._lock:
            self._subscribers.pop(session_id, None)

    async def _reader_loop(self) -> None:
        """Persistent SSE reader — reconnects on failure."""
        while True:
            try:
                await self._read_stream()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.warning(f"[sse] reader loop error: {exc}, reconnecting in 1s")
                await asyncio.sleep(1)

    async def _read_stream(self) -> None:
        """Read SSE events and dispatch to subscribers."""
        assert self._http is not None
        async with self._http.get(
            f"{self._base_url}/event",
            timeout=aiohttp.ClientTimeout(total=0),  # no timeout — persistent
        ) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data:"):
                    continue

                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue

                await self._dispatch_event(event)

    async def _dispatch_event(self, event: dict) -> None:
        """Route an OpenCode event to the right session queue."""
        props = event.get("properties", {})
        part = event.get("part", {})
        event_sid = props.get("sessionID") or event.get("sessionID") or part.get("sessionID")

        if event_sid:
            async with self._lock:
                q = self._subscribers.get(event_sid)
            if q:
                await q.put(event)
            return

        # Broadcast file events without a session id so each task can track changes.
        etype = event.get("type", "")
        if etype in ("file.edited", "file.watcher.updated"):
            async with self._lock:
                for q in self._subscribers.values():
                    await q.put(event)


class OpenCodeServerPool:
    """Pool of `opencode serve` instances — one per project directory.

    Thread/coroutine safe via asyncio.Lock per repo_root.
    Instances are started lazily on first request and kept alive.
    Each instance has a shared SSE listener for event multiplexing.
    Call `stop_all()` on daemon shutdown.
    """

    def __init__(self, bin_path: str = "opencode") -> None:
        self._bin_path = bin_path
        self._instances: dict[str, ServerInstance] = {}
        self._listeners: dict[str, SSEListener] = {}
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
        listener = self._listeners[repo_root]

        async with aiohttp.ClientSession() as http:
            session_id = await self._create_session(http, instance, model=model)
            logger.info(f"[pool] session {session_id} created for {repo_root}")

            # Subscribe BEFORE sending prompt to avoid race
            queue = await listener.subscribe(session_id)
            try:
                await self._send_prompt(http, instance, session_id, prompt, model=model)
                logger.info(f"[pool] prompt sent to session {session_id}")

                result = await self._wait_for_idle(
                    queue,
                    instance,
                    session_id,
                    timeout=timeout,
                )
            except asyncio.CancelledError:
                await self._abort_session(http, instance, session_id)
                raise
            except Exception:
                await self._abort_session(http, instance, session_id)
                raise
            finally:
                await listener.unsubscribe(session_id)

            # Augment with authoritative VCS diff to catch anything SSE missed.
            vcs_files, raw_diff = await self._fetch_vcs_diff(http, instance)
            for f in vcs_files:
                if f not in result.files_changed:
                    result.files_changed.append(f)
            if raw_diff:
                result.raw_diff = raw_diff
            if result.files_changed:
                result.summary = self._build_summary(result.files_changed)

            logger.info(f"[pool] session {session_id} completed: {result.summary}")
            return result

    async def stop_all(self) -> None:
        """Terminate all server instances. Call on daemon shutdown."""
        async with self._pool_lock:
            for key, listener in self._listeners.items():
                await listener.stop()
            self._listeners.clear()
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
                # Stop old listener
                old_listener = self._listeners.pop(repo_root, None)
                if old_listener:
                    await old_listener.stop()

            inst = await self._start_server(repo_root, model=model)
            self._instances[repo_root] = inst

            # Start shared SSE listener for this instance
            listener = SSEListener(inst.base_url)
            await listener.start()
            self._listeners[repo_root] = listener

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
            env["OPENCODE_MODEL"] = model
        return env

    # ------------------------------------------------------------------
    # REST API helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_model(model: str | None) -> tuple[str, str] | None:
        """Split 'provider/model-id' into (providerID, modelID).

        Example: ``openrouter/deepseek/deepseek-v4-flash-0731`` ->
        ``("openrouter", "deepseek/deepseek-v4-flash-0731")``.
        Returns None when the model string has no slash separation.
        """
        if not model:
            return None
        parts = model.split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            return None
        return parts[0], parts[1]

    async def _create_session(
        self, http: aiohttp.ClientSession, inst: ServerInstance, model: str | None = None
    ) -> str:
        """Create a session, preferring the v2 ``/api/session`` endpoint.

        Falls back to the legacy ``/session`` endpoint when ``/api/session``
        is not available on the running opencode version.
        """
        body: dict = {}
        split = self._split_model(model)
        if split:
            body["model"] = {"providerID": split[0], "id": split[1]}
        async with http.post(f"{inst.base_url}/api/session", json=body) as resp:
            if resp.status in (200, 201):
                data = await resp.json()
                session_id = data.get("data", {}).get("id")
                if session_id:
                    return session_id
            # Fallback: legacy /session endpoint
            async with http.post(f"{inst.base_url}/session", json={}) as resp2:
                resp2.raise_for_status()
                data = await resp2.json()
                session_id = data.get("id") or data.get("data", {}).get("id", "")
                return session_id

    async def _send_prompt(
        self,
        http: aiohttp.ClientSession,
        inst: ServerInstance,
        session_id: str,
        prompt: str,
        model: str | None = None,
    ) -> None:
        body: dict = {"parts": [{"type": "text", "text": prompt}]}
        split = self._split_model(model)
        if split:
            body["model"] = {"providerID": split[0], "modelID": split[1]}
        async with http.post(
            f"{inst.base_url}/session/{session_id}/prompt_async", json=body
        ) as resp:
            if resp.status not in (200, 204):
                text = await resp.text()
                raise RuntimeError(f"prompt_async failed ({resp.status}): {text}")

    async def _abort_session(
        self,
        http: aiohttp.ClientSession,
        inst: ServerInstance,
        session_id: str,
    ) -> None:
        """Best-effort abort of a session. Used on timeout/cancellation/error."""
        try:
            async with http.post(
                f"{inst.base_url}/session/{session_id}/abort",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status < 400:
                    logger.info(f"[pool] aborted session {session_id}")
                else:
                    logger.warning(f"[pool] abort session {session_id} returned {resp.status}")
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(f"[pool] failed to abort session {session_id}: {exc}")

    async def _fetch_vcs_diff(
        self, http: aiohttp.ClientSession, inst: ServerInstance
    ) -> tuple[list[str], list[dict] | None]:
        """Fetch the authoritative VCS diff for the working tree.

        Returns ``(files_changed, raw_diff)``. ``raw_diff`` is ``None`` when
        the diff is unavailable (not a git repo, old server, or API error) —
        callers then rely on SSE-collected file events.
        """
        try:
            async with http.get(
                f"{inst.base_url}/vcs/diff",
                params={"mode": "git"},
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status >= 400:
                    return [], []
                data = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            logger.warning(f"[pool] vcs/diff unavailable: {exc}")
            return [], []
        except Exception as exc:
            logger.warning(f"[pool] vcs/diff parse failed: {exc}")
            return [], []

        files: list[str] = []
        if not isinstance(data, list):
            return [], []
        for entry in data:
            if not isinstance(entry, dict):
                continue
            fpath = entry.get("file") or ""
            if not fpath:
                continue
            try:
                rel = str(Path(fpath).relative_to(inst.repo_root))
            except ValueError:
                rel = fpath
            if rel not in files:
                files.append(rel)
        return files, data

    @staticmethod
    def _build_summary(files_changed: list[str]) -> str:
        if not files_changed:
            return "Task completed (no file changes detected)"
        flist = ", ".join(files_changed[:5])
        if len(files_changed) > 5:
            flist += f" and {len(files_changed) - 5} more"
        return f"Modified {len(files_changed)} file(s): {flist}"

    async def _wait_for_idle(
        self,
        queue: asyncio.Queue,
        inst: ServerInstance,
        session_id: str,
        timeout: int,
    ) -> ExecutionResult:
        """Consume events from the per-session queue until session.idle."""
        files_changed: list[str] = []
        diff: list[dict] = []
        deadline = time.time() + timeout

        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise TimeoutError(
                    f"Task in session {session_id} did not complete within {timeout}s"
                )

            try:
                event = await asyncio.wait_for(queue.get(), timeout=remaining)
            except TimeoutError:
                raise TimeoutError(
                    f"Task in session {session_id} did not complete within {timeout}s"
                ) from None

            etype = event.get("type", "")
            props = event.get("properties", {})
            part = event.get("part", {})

            if etype == "file.edited":
                fpath = props.get("file", "")
                if fpath:
                    try:
                        rel = str(Path(fpath).relative_to(inst.repo_root))
                    except ValueError:
                        rel = fpath
                    if rel not in files_changed:
                        files_changed.append(rel)

            elif etype == "session.diff":
                diff = props.get("diff", [])

            elif etype == "tool_use" or part.get("type") == "tool":
                state = part.get("state", {})
                input_data = state.get("input", {})
                metadata = state.get("metadata", {})
                fpath = input_data.get("filePath") or metadata.get("filepath")
                if fpath:
                    try:
                        rel = str(Path(fpath).relative_to(inst.repo_root))
                    except ValueError:
                        rel = fpath
                    if rel not in files_changed:
                        files_changed.append(rel)

            elif etype == "step_finish":
                if part.get("reason") == "stop":
                    break

            elif etype == "session.idle":
                break

            elif etype == "session.status":
                status_type = props.get("status", {}).get("type", "")
                if status_type == "idle":
                    break

        # Build result
        if not files_changed and diff:
            files_changed = [d["file"] for d in diff if d.get("file")]

        return ExecutionResult(
            success=True,
            files_changed=files_changed,
            summary=self._build_summary(files_changed),
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
