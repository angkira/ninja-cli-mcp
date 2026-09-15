# Plan: MCP Tasks (background execution) for ninja MCP servers

## Goal
Let long-running tools run in the background: `tools/call` returns a task handle
immediately; the client polls `tasks/get` / `tasks/result` / `tasks/list` and
cancels via `tasks/cancel`. Use the **standard** MCP Tasks capability (not a
bespoke job API), with a synchronous fallback for clients that don't advertise it.

## Facts (verified)
- SDK: `mcp==1.24.0` (`.venv`). Server side: `mcp.server.lowlevel.experimental`.
  - `server.experimental.enable_tasks(store=None, queue=None)` → `TaskSupport`
    (defaults to `InMemoryTaskStore` / `InMemoryTaskMessageQueue`); auto-registers
    `tasks/get|result|list|cancel` and declares `ServerTasksCapability` via
    `update_capabilities`.
  - `types.Tool(execution=types.ToolExecution(taskSupport="optional"|"required"|"forbidden"))`.
  - `create_call_wrapper(func, RequestType)`, `cancel_task(store, id)`, types in
    `mcp.shared.experimental.tasks.*` (`store`, `message_queue`, `context`,
    `polling`, `resolver`, `capabilities`, `in_memory_task_store`, `helpers`).
- Client: opencode's bundled MCP TS SDK supports tasks:
  `assertTaskCapability`, `isToolTask`, `isToolTaskRequired`,
  `cacheToolMetadata` (reads `tool.execution.taskSupport`), and
  `client.experimental.tasks.callToolStream()`; methods `tasks/get|list|result|cancel`.
  → declare `taskSupport="optional"` so non-task clients still call synchronously.

## Approach
1. Coder server (`src/ninja_coder/server.py`): call `server.experimental.enable_tasks()`
   at startup; mark `coder_execute_plan_sequential`, `coder_execute_plan_parallel`,
   `coder_simple_task`, `coder_multi_agent_task` with
   `execution=ToolExecution(taskSupport="optional")` in `@server.list_tools()`.
2. Verify the existing `@server.call_tool()` handler works in task mode; if the SDK
   requires the handler to be registered via `create_call_wrapper`/`server.experimental`,
   restructure minimally per SDK source (`mcp/server/lowlevel/server.py` task integration).
3. Emit `notifications/progress` from the driver's streaming loop if it is low-risk
   (optional; skip if it destabilizes).
4. Replicate for agent/researcher only if trivial; otherwise coder-first.
5. Keep synchronous behavior for clients without the tasks capability.

## Verification
- Unit: `ruff`/`mypy`; existing tests.
- New test: a Python MCP client that declares the `tasks` capability, calls a
  task-supporting tool, receives a task handle, polls `tasks/get` → completes,
  then `tasks/result`. Plus a client WITHOUT the capability → synchronous result.
- Manual: run the tool via a scripted client (no real LLM needed — mock/echo CLI).
- Do NOT commit.

## Out of scope
- Distributed task stores; per-task TTL tuning; progress for every tool.
