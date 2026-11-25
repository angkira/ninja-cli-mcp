---
name: tasks-vs-jobs
description: Decide between the standard MCP Tasks extension (resultType task, tasks/get, tasks/cancel) and the always-available coder submit/poll job tools.
---

# Tasks or jobs: pick the background path

The servers expose two ways to run long work in the background. They share one
durable SQLite store, so a job row and a task row are the same row seen through
two interfaces.

## The two paths

| Path | Requirement | Surface |
| --- | --- | --- |
| MCP Tasks | client declares `io.modelcontextprotocol/tasks`, protocol 2026-07-28 | `tools/call` → `resultType: "task"`, then `tasks/get` / `tasks/update` / `tasks/cancel` |
| submit/poll jobs | none — ordinary tool calls | `coder_submit_*` → `coder_job_status` / `coder_job_result` / `coder_job_cancel` / `coder_jobs_list` |

## When the server returns a task handle

Only on a connection negotiating 2026-07-28 that advertised the tasks
extension. The server then answers `tools/call` for a task-enabled tool with

```
{"resultType": "task", "taskId": "...", "status": "working", "statusMessage": ..., "pollIntervalMs": ...}
```

instead of blocking. On any older revision the same call runs synchronously and
returns the ordinary `CallToolResult`; the extension's methods do not exist
there and answer METHOD_NOT_FOUND. A client that advertised the extension but
does not want to claim results still gets the raw envelope — drop the
declaration to keep the synchronous path.

Task-enabled tools per server:

| Server | Tools |
| --- | --- |
| coder | `coder_simple_task`, `coder_execute_plan_sequential`, `coder_execute_plan_parallel`, `coder_multi_agent_task` |
| researcher | `researcher_deep_research`, `researcher_deep_research_batch`, `researcher_paper_fetch` |
| secretary | `secretary_codebase_report`, `secretary_analyse_file` |
| agent | `agent_run_and_diagnose`, `agent_exec_pipeline` |

Every other tool is synchronous even for a declaring client.

## Driving a task

1. Send `tools/call` with the tool's normal arguments and a `task` field
   carrying a TTL. Keep the returned `taskId`.
2. Poll `tasks/get` with `{"taskId": "..."}` no faster than `pollIntervalMs`.
   The result carries `status` (`working`, `completed`, `failed`, `cancelled`,
   `input_required`), `statusMessage`, timestamps and the advertised interval.
   A completed task also carries the stored `result` payload; a failed one
   carries an `error` object with `code` and `message`.
3. Stop polling at `completed`, `failed` or `cancelled`.
4. To stop the work, call `tasks/cancel` with the same `taskId`. It interrupts
   the run rather than only marking the row, and cancelling an unknown or
   terminal task is a safe no-op. `tasks/update` is available for a task that is
   `input_required`.

Do not build against `tasks/result` or `tasks/list`. Older docs mention them,
but this extension binds only `tasks/get`, `tasks/update` and `tasks/cancel`;
the result comes back inside `tasks/get`.

## When to prefer submit/poll

- The host does not declare the tasks extension (the common case today).
- You need the job to be visible from a different session, process or the
  `--http` server: `coder_jobs_list` works with no extension at all.
- Only coder has job tools. For researcher, secretary and agent long tools your
  choices are the synchronous call or `tasks/get`.

## Rules

- Use exactly one path per unit of work. Submitting a job and then also calling
  the synchronous tool duplicates the run and the spend.
- Never poll in a tight loop; honour `poll_interval_ms` / `pollIntervalMs`.
- Report a failed task from its `error.message` and `statusMessage`, not from
  your memory of what the run was doing.
