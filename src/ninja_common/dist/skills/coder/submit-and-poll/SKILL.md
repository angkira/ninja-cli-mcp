---
name: submit-and-poll
description: Run ninja-coder work in the background with coder_submit_* and the coder_job_status / coder_job_result loop instead of blocking on a synchronous tool call.
---

# Submit and poll a coder job

A coder run can take minutes. The synchronous tools keep the `tools/call`
request open for that whole time; the submit/poll tools return a handle in
well under a second.

## When to use

- The work is expected to exceed roughly 60 seconds (a plan, a refactor, a
  multi-file feature).
- You want to keep working — or answer the user — while the code is written.
- The host has no standard MCP Tasks support. submit/poll only uses ordinary
  tool calls, so it works everywhere.

Stay synchronous with `coder_simple_task` when the change is one or two lines in
one file and you need the answer immediately.

## Pick the submit tool that matches the work

| Work | Tool |
| --- | --- |
| 1-2 line fix in one file | `coder_submit_simple` |
| Ordered multi-step plan | `coder_submit_sequential` |
| Independent atomic steps | `coder_submit_parallel` |

Each submit tool takes the same arguments as its synchronous twin
(`repo_root`, `task`, `steps`, `complexity`, `allowed_globs`, ...), so a
specification can be moved between them unchanged.

## The loop

1. Call the submit tool with the full specification. It returns
   `{job_id, status, poll_interval_ms}` — `status` is `working` and
   `poll_interval_ms` is the cadence the server wants you to use.
2. Do other work. Do not poll faster than `poll_interval_ms`.
3. Call `coder_job_status` with `{"job_id": "<id>"}`. It returns
   `{job_id, status, created_at, last_updated_at, status_message}`.
4. Repeat step 3 until `status` is one of `completed`, `failed`, `cancelled`.
5. Call `coder_job_result` with the same `job_id` to fetch the payload. On a
   completed job this is the same JSON the synchronous tool returns; while the
   job is still `working` it returns a `poll_interval_ms` hint instead.

`coder_job_cancel` stops a run: it terminates the CLI process group. Cancelling
an unknown or already-terminal job is a safe no-op. `coder_jobs_list` takes
`cursor` and `limit` and returns older jobs with a `next_cursor`.

## Use request_key for retries

Every submit tool accepts `request_key`. Supply the same key when retrying after
a timeout, a dropped connection or a host restart: the retry joins the in-flight
run and returns the same `job_id` instead of starting a second CLI process.
Generate a fresh key per logical unit of work — reusing a key for different
arguments returns the earlier job, not the new work.

## Reading status_message

`status_message` is the server's progress channel, not a result. It starts as
the tool name (`coder_execute_plan_sequential`) and is replaced on each progress
tick with `<tool>: <detail>`, or `<tool>: heartbeat N` when the driver reported
no message. Treat it as evidence of liveness:

- it advances → the run is alive; keep waiting;
- it stops advancing for several polls → the watchdog may be about to fire;
- the job reaches `failed` → read `status_message` last, then
  `coder_query_logs` with the `task_id`/`session_id` for the CLI output.

## Failure handling

- `failed`: report `status_message` to the user and stop. Do not resubmit the
  same specification without changing it — a deterministic failure repeats.
- `cancelled`: the result payload is empty by design; nothing to read.
- `UnknownJob` from `coder_job_status`: the id was never minted by this store.
  Check `NINJA_TASKS_DB` or use `coder_jobs_list` before resubmitting.
