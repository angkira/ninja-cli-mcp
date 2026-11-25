# Background Execution (MCP Tasks extension + submit/poll)

Ninja's long-running tools can run **in the background**: the call returns a
handle immediately, the host keeps working, and the result is fetched later.

Two independent paths exist, and the servers provide both:

| Path | Works in | API |
| --- | --- | --- |
| **Tasks extension** | clients that declare `io.modelcontextprotocol/tasks` on protocol `2026-07-28` | `tools/call` → `resultType: "task"` → `tasks/get` / `tasks/cancel` |
| **submit/poll jobs** | **every** MCP host, every protocol revision | `coder_submit_*` → `coder_job_status` / `coder_job_result` / `coder_job_cancel` |

> Host support for the extension is opt-in: most hosts today still initialize
> without the extension, so **use submit/poll for background work unless your
> client declares it**. Tasks light up automatically once a host does.

Wire-level detail (request shapes, polling envelope, cancel semantics) lives in
[MCP_PROTOCOL_2026.md](MCP_PROTOCOL_2026.md#4-tasks-iomodelcontextprotocoltasks).

## How the extension works

- All four servers advertise `io.modelcontextprotocol/tasks` in
  `capabilities.extensions` on `2026-07-28`. There is no startup switch and no
  `install_tasks` hook: the extension is built by
  `ninja_common.mcp_ext.wiring.build_protocol_extensions()` and applied with
  `ninja_common.mcp_ext.apply.apply_extensions()`.
- A task handle is returned **only** when the client declared the extension
  *and* the connection negotiated `2026-07-28`. Every other call runs
  synchronously, exactly as before.
- The extension's methods are `tasks/get`, `tasks/update` and `tasks/cancel`.
  There is **no** `tasks/result` and **no** `tasks/list`: the result is returned
  inside `tasks/get` when the task is `completed`.

### Task-enabled tools

Exactly these tools run as tasks (`TASK_TOOLS` in each `server.py`):

| Server | Tools |
| --- | --- |
| coder | `coder_simple_task`, `coder_execute_plan_sequential`, `coder_execute_plan_parallel`, `coder_multi_agent_task` |
| researcher | `researcher_deep_research`, `researcher_deep_research_batch`, `researcher_paper_fetch` |
| secretary | `secretary_codebase_report`, `secretary_analyse_file` |
| agent | `agent_run_and_diagnose`, `agent_exec_pipeline` |

Everything else — `researcher_quick_research`, `researcher_generate_report`,
`researcher_fact_check`, `researcher_summarize_sources`,
`researcher_arxiv_search`, `secretary_file_search`,
`secretary_document_summary`, `secretary_session_report`,
`secretary_update_documentation`, `agent_exec_command`, `agent_tail_logs`,
`agent_processes`, `agent_jobs_overview`, `agent_analyze`, `agent_review`,
`agent_distill_logs`, and the whole `coder_submit_*` / `coder_job_*` family — is
always synchronous.

### Task lifecycle

| Request | Purpose |
| --- | --- |
| `tools/call` (task-enabled tool) | Start the work; a declaring client gets `resultType: "task"` + `taskId` |
| `tasks/get` | Poll status; on `completed` carries `result`, on `failed` carries `error` |
| `tasks/update` | Answer `inputRequests`; acknowledgement only |
| `tasks/cancel` | Cooperative cancel; **interrupts the running work** |

Statuses: `working` → `completed` / `failed` / `cancelled` (plus
`input_required`, which the ninja servers do not raise today). A cancel of an
already-terminal task returns its current state instead of failing; an unknown
id is `-32602 INVALID_PARAMS`.

## Background without the extension: submit/poll (all hosts)

This is the portable way to run in the background from opencode, Claude Code,
Codex, Antigravity, or any other host — it only uses ordinary tool calls.

| Tool | Purpose |
| --- | --- |
| `coder_submit_simple` / `coder_submit_sequential` / `coder_submit_parallel` | Start work; returns `{job_id, status:"working", poll_interval_ms}` immediately |
| `coder_job_status` | `{job_id, status, created_at, last_updated_at, status_message}` |
| `coder_job_result` | Final payload (or a `working` hint with `poll_interval_ms`) |
| `coder_job_cancel` | Cancel; **interrupts** the running work (CLI process group) |
| `coder_jobs_list` | List known jobs, cursor pagination |

```
1. coder_submit_sequential {repo_root, steps}   -> {job_id, status:"working"}
2. ... keep working ...
3. coder_job_status {job_id}                     -> working | completed | failed | cancelled
4. coder_job_result {job_id}                     -> the same JSON the sync tool returns
   (or coder_job_cancel {job_id} to stop it)
```

`coder_job_cancel` terminates the CLI subprocess group (SIGTERM → SIGKILL), so a
cancelled job actually stops; cancelling an unknown or finished job is a no-op.
Job state is durable (`NINJA_TASKS_DB`), so jobs survive restarts.

## Client usage (Tasks extension)

### Python

```python
from mcp import Client

from ninja_common.mcp_ext.tasks_client import TasksClient
from ninja_coder.server import create_server

tasks = TasksClient()  # declares io.modelcontextprotocol/tasks and polls tasks/get
async with Client(create_server(), extensions=[tasks]) as client:
    result = await client.call_tool(
        "coder_execute_plan_sequential",
        {"repo_root": ".", "steps": [{"id": "s1", "task": "Add a docstring"}]},
    )
    print(result.structured_content)
```

`TasksClient` hides the polling loop. To drive it by hand, declare the extension
with `mcp.client.advertise("io.modelcontextprotocol/tasks")` and send
`tasks/get` yourself; the raw envelopes are documented in
[MCP_PROTOCOL_2026.md](MCP_PROTOCOL_2026.md).

### TypeScript / OpenCode

Hosts with extension support call the tool normally and resolve the
`resultType: "task"` claim through `tasks/get`; there is no separate task API to
migrate to. If your host used the 1.x experimental Tasks API
(`client.experimental.tasks…`, `tasks/result`, `tasks/list`), that API no longer
exists — poll `tasks/get` instead.

## Cancellation interrupts work

`tasks/cancel` and `coder_job_cancel` are not status flags. The server
terminates the running CLI subprocess **group** (SIGTERM, then SIGKILL after a
short grace), so the model run stops and resources are freed.

## Durable task state

Tasks and jobs share one SQLite store, so state survives a server restart and is
visible across sessions (servers, daemons, `--http`).

| Env var | Default | Meaning |
| --- | --- | --- |
| `NINJA_TASKS_DB` | `~/.ninja/tasks.db` | SQLite path for task/job state (`:memory:` / `file::memory:` supported) |

State uses WAL, a busy timeout, and lazy TTL expiry. A task created with a TTL
expires automatically after it becomes terminal.

### Owner tracking & stale reconciliation

Each record stores owner identity metadata (`owner_pid` and `owner_token`,
derived from the creating process PID and its OS process start timestamp via
`psutil`). On startup a server calls `sweep_stale_working()`:

- Only records whose owner process is **demonstrably dead** (the process is
  gone, or its PID was recycled by a different process with a newer creation
  timestamp) are transitioned to `failed`.
- Records belonging to live concurrent sibling processes (coexisting stdio
  servers or background daemons) stay `working` and are never swept.
- Legacy rows with unknown or missing ownership are never guessed dead.
- Terminal records are immutable against progress and status-message updates,
  so a late heartbeat cannot overwrite the recorded failure reason.

## Progress notifications

While a CLI streams, the driver emits `notifications/progress` (about every 10s
of activity) using the request's `progressToken` (falling back to the task id).
Emission is best-effort: without a token or session it is a no-op and never
affects the run.

## Configuration reference

| Env var | Default | Notes |
| --- | --- | --- |
| `NINJA_TASKS_DB` | `~/.ninja/tasks.db` | Durable task/job store path |
| `NINJA_INACTIVITY_TIMEOUT[_QUICK/_SEQUENTIAL/_PARALLEL]` | 90/180/180s | Watchdog; independent of tasks |

## Limitations

- The store is local SQLite; it is not a distributed queue.
- Live wake-ups are in-process; durability is shared through SQLite.
- **Owner-based reconciliation limits**: liveness inspection is valid only
  within the local host's PID namespace. If `NINJA_TASKS_DB` is mounted across
  machines or container boundaries without a shared PID namespace, foreign
  process liveness cannot be inspected and those records are never guessed dead.
- Extension support is per client and per connection: on a legacy connection,
  or from a client that did not declare `io.modelcontextprotocol/tasks`, the
  same tool runs synchronously.

## Reference

- `src/ninja_common/mcp_ext/tasks.py` — `TasksExtension` (`tasks/get`,
  `tasks/update`, `tasks/cancel`, `tools/call` interception).
- `src/ninja_common/mcp_ext/tasks_store.py` — `SqliteTaskStore`, TTL expiry,
  stale-owner reconciliation.
- `src/ninja_common/mcp_ext/tasks_client.py` — `TasksClient` (client-side
  polling).
- `src/ninja_common/mcp_tasks.py` — cancellation scope, progress bridging,
  re-exports of the store.
- `tests/test_mcp_protocol_extensions.py`, `tests/test_common/mcp_ext/` —
  task lifecycle on the wire.
