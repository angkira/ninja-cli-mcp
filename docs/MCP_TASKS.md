# Background Execution with MCP Tasks

Ninja's long-running tools can run **in the background**: the call returns a task
handle immediately, the host keeps working, and the result is fetched later.
This uses the standard **MCP Tasks** capability — no custom job API.

## Why

A coder plan (sequential/parallel) can run for minutes. Without tasks, the MCP
host blocks on `tools/call` until the model finishes. With tasks, you start the
run, get an id, and continue; the run proceeds in the server.

## How it works

- Servers enable tasks at startup (`server.experimental.enable_tasks`, wired via
  `ninja_common.mcp_tasks.install_tasks`).
- Long tools advertise `execution.taskSupport = "optional"` in `tools/list`.
- If the client sends a task-augmented `tools/call` (a `task` field with a TTL),
  the tool runs in the background and the response is a **task handle**
  (`CreateTaskResult`). Otherwise the tool runs **synchronously**, exactly as
  before — clients without the Tasks capability are unaffected.

### Task-capable tools

| Server | Tools |
| --- | --- |
| coder | `coder_simple_task`, `coder_execute_plan_sequential`, `coder_execute_plan_parallel`, `coder_multi_agent_task` |
| agent | `agent_plan`, `agent_analyze`, `agent_delegate`, `agent_review` |
| researcher | `researcher_deep_research`, `researcher_generate_report`, `researcher_fact_check`, `researcher_summarize_sources` |

### Task lifecycle

| Request | Purpose |
| --- | --- |
| `tools/call` (+ `task: {ttl}`) | Start the work; returns a task handle |
| `tasks/get` | Poll status (`working` → `completed` / `failed` / `cancelled`) |
| `tasks/result` | Fetch the final `CallToolResult` payload |
| `tasks/list` | List known tasks |
| `tasks/cancel` | Cancel; **actually interrupts** the running work |

The server also emits `notifications/tasks/status` (from the SDK) and
`notifications/progress` (see below).

## Client usage

### OpenCode / MCP TS clients

Tools with `execution.taskSupport` of `optional`/`required` are called through
the task API (`client.experimental.tasks.callToolStream()`), then polled via
`tasks/get` / `tasks/result`.

### Python client

```python
from mcp import types
from mcp.client.experimental.task_handlers import ExperimentalTaskHandlers
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

params = StdioServerParameters(command="ninja-coder", args=[])
handlers = ExperimentalTaskHandlers()  # declares the client tasks capability

async with stdio_client(params) as (read, write):
    async with ClientSession(read, write, experimental_task_handlers=handlers) as session:
        await session.initialize()

        create = await session.experimental.call_tool_as_task(
            "coder_execute_plan_sequential",
            {"repo_root": ".", "steps": [{"id": "s1", "task": "Add a docstring"}]},
            ttl=600_000,
        )
        task_id = create.task.taskId            # handle returned immediately

        async for task in session.experimental.poll_task(task_id):
            ...                                  # working → completed

        result = await session.experimental.get_task_result(task_id, types.CallToolResult)
        print(result.content[0].text)
```

## Cancellation interrupts work

`tasks/cancel` is not just a status flag. The server terminates the running CLI
subprocess **group** (SIGTERM, then SIGKILL after a short grace), so the model
run stops and resources are freed. Cancelling an unknown or already-terminal
task is a safe no-op.

## Durable task state

Tasks are stored in SQLite so they survive a server restart and are visible
across sessions (servers, daemons, `--http`).

| Env var | Default | Meaning |
| --- | --- | --- |
| `NINJA_TASKS_DB` | `~/.ninja/tasks.db` | SQLite path for task state (`:memory:` / `file::memory:` supported) |

State uses WAL, a busy timeout, and lazy TTL expiry. A task created with a TTL
expires automatically after it becomes terminal.

## Progress notifications

While a CLI streams, the driver emits `notifications/progress` (about every 10s
of activity) using the request's `progressToken` (falling back to the task id).
Emission is best-effort: without a token or session it is a no-op and never
affects the run.

## Configuration reference

| Env var | Default | Notes |
| --- | --- | --- |
| `NINJA_TASKS_DB` | `~/.ninja/tasks.db` | Durable task store path |
| `NINJA_INACTIVITY_TIMEOUT[_QUICK/_SEQUENTIAL/_PARALLEL]` | 90/180/180s | Watchdog; independent of tasks |

## Limitations

- Task store is local SQLite; it is not a distributed queue.
- Live `tasks/result` waiters are in-process (`InMemoryTaskMessageQueue`);
  durability is shared via SQLite, live wake-ups are not.
- The MCP Tasks capability is *experimental* in the SDK/protocol; capability
  detection is per client. Servers keep the synchronous path for clients that do
  not advertise it.

## Reference

- `src/ninja_common/mcp_tasks.py` — `install_tasks`, `SqliteTaskStore`,
  `task_scope`, `request_cancel`, `emit_progress`.
- `tests/test_mcp_tasks.py` — create/poll/result, cancel-interrupts-work,
  persistence across restart, progress, synchronous fallback.
