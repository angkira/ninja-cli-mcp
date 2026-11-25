# Live end-to-end battle suites

Two standalone suites exercise **already-running** ninja-mcp daemons over
Streamable HTTP with the MCP `2026-07-28` protocol. They are opt-in: they are
not collected by the default pytest run and are not wired into CI, because they
require four live daemons and a real host process table.

```text
scripts/e2e/
├── battle_protocol.py   # discovery, skills, schemas, error paths, legacy era
├── battle_tasks.py      # tasks lifecycle/cancel, elicitation/MRTR, concurrency
└── README.md
```

## Prerequisites

* The project installed in a venv with its runtime dependencies. The examples
  below use the `uv tool` install:
  `~/.local/share/uv/tools/ninja-mcp/bin/python`.
* Four running daemons. The default ports are the deployed ones:

  | module     | env var                 | default |
  |------------|-------------------------|---------|
  | coder      | `NINJA_CODER_PORT`      | 8100    |
  | researcher | `NINJA_RESEARCHER_PORT` | 8101    |
  | agent      | `NINJA_AGENT_PORT`      | 8106    |
  | secretary  | `NINJA_SECRETARY_PORT`  | 8107    |

  Start them with `ninja-mcp daemon start` (or your service manager) and verify
  with `ninja-mcp daemon status`.
* Nothing else. No API keys are needed: every tool the suites call is
  read-only or performs a harmless `echo`/`sleep` in a scratch directory.

Ports may be overridden per run, either through the environment or with a
single flag:

```bash
NINJA_AGENT_PORT=9106 python scripts/e2e/battle_tasks.py
python scripts/e2e/battle_tasks.py --ports agent=9106,coder=9100
```

Precedence is `--ports` > `NINJA_<MODULE>_PORT` > the deployed default.

## Running

```bash
# protocol suite
~/.local/share/uv/tools/ninja-mcp/bin/python scripts/e2e/battle_protocol.py \
    --json /tmp/proto.json

# tasks / elicitation suite
~/.local/share/uv/tools/ninja-mcp/bin/python scripts/e2e/battle_tasks.py \
    --json /tmp/tasks.json
```

Both print a human-readable report and exit `0` only when every check passed.
`--json PATH` additionally writes a machine-readable report containing
`summary` (`total`, `passed`, `failed`, `exit_code`), every check with its
observed value, timings, and the raw protocol payloads where applicable.

These suites are **not** part of `pytest` and should not be added to CI. The
`live` pytest marker exists only to document the category; no test module uses
it by default.

## What `battle_protocol.py` asserts

Read-only calls only.

* **A. Discovery** — protocol version is `2026-07-28`; `skills` + `tasks`
  extensions are advertised; tools/resources are present and prompts are not;
  `server_info.name` is non-empty; `tools/list` is deterministic; every tool has
  an object input schema, a title, an annotation hint, and an object output
  schema; expected tool counts; `secretary_file_search` requires both `pattern`
  and `repo_root`; `_meta.serverInfo` is present on modern responses.
* **B. Skills** — expected skill counts; manifest entries carry a URI,
  frontmatter name/description and their `SKILL.md`; served bytes match the
  advertised SHA-256 digest and size; `skills/get` equals the `skills/list`
  entry; bogus `skills/get` / `resources/read` return `-32602` and the session
  survives them.
* **C. Error paths** (coder + agent) — unknown tool, missing required args and
  wrong-typed args all return `is_error=True`; the coder's wrong-typed
  `job_id` names the field (`job_id must be a string`); the session is healthy
  afterwards.
* **D. Legacy era** — a `2025-*` client negotiates, lists tools and calls a
  read-only tool; `skills/list` over legacy returns `-32601`; three concurrent
  modern clients per server show no cross-talk.
* **E. Output hygiene** — `_meta.serverInfo` on `resources/list` and
  `tools/call`; structured content is non-null; a scan reports absolute host
  paths found in skill text and payloads (informational).
* **T. Tasks round trip** — a task-enabled secretary tool resolves through
  `tasks/get`, and the tools/call task handle still carries
  `_meta.serverInfo`.

## What `battle_tasks.py` asserts

* **A. Tasks lifecycle (agent)** — a non-declaring client gets a plain
  `CallToolResult`; a declaring client gets a task handle (`resultType=task`,
  non-empty `taskId`, positive TTL/poll interval), resolves to `completed`, and
  its result matches the synchronous baseline; unknown task id returns
  `-32602`.
* **B. Cancellation (agent)** — a 60-second pipeline task is submitted,
  observed `working`, cancelled, reaches a terminal status, and a second
  cancel is idempotent. Cancellation is verified **by PID** (see below).
* **C. Legacy isolation (agent)** — a legacy client never receives a task
  handle; `tasks/get` over legacy returns `-32601`.
* **D. Elicitation / MRTR (coder, decline only)** — `coder_branch_discard`
  answers with `input_required` and a sealed `requestState`; the sealed state
  leaks neither the branch name nor the repo path in cleartext; declining
  through the SDK callback produces the normal unmerged-branch refusal; the
  branch survives; replaying another operation's `requestState` raises
  `-32602`; a legacy client never sees `input_required`. The suite only ever
  **declines** and only ever passes `force=false`, so no branch is deleted.
* **E. Concurrency (agent)** — five concurrent submissions get distinct task
  ids, all complete, and each carries its own output.
* **F. Advertised contracts** — unknown tool → `is_error=True`;
  `coder_job_status {"job_id": 12345}` → `is_error=True` with
  `job_id must be a string`; `secretary_file_search` schema requires both
  `pattern` and `repo_root`.
* **SAFETY** — both throwaway branches still exist, and every PID captured for
  the cancelled task is gone.

### PID-scoped cancellation (why it is not a host-wide `ps | grep`)

A naive orphan check greps the host for `sleep 60` and fails whenever an
unrelated process (another session, a CI poller, a log tail) happens to run one.
That is a false positive, not a cancellation bug.

`battle_tasks.py` therefore records the processes that actually belong to the
task:

1. The submitted command is `sleep 60; : <unique-token>`. The trailing
   `; :` keeps `sh` alive instead of `exec`-ing `sleep`, so the token stays in
   the shell's argv for the whole run.
2. The suite locates the process whose argv carries that token, verifies it is a
   descendant of the agent daemon, and captures its **process group** (the
   daemon spawns every command with `start_new_session=True`, so one command
   equals one PGID).
3. It records each member's PID **and start time** (so PID reuse cannot mask a
   survivor).
4. After `tasks/cancel`, it polls only those PIDs until they exit and asserts
   that none survive. The end-of-run sweep re-checks the same set.

Unrelated `sleep 60` processes found on the host are reported as
informational only — they never influence a check. The suite sends no signals
of its own: only the daemon terminates its task's process group.

## Safety notes

* Every tool invoked is read-only, except `agent_run_and_diagnose` /
  `agent_exec_pipeline`, which run `echo` and a cancellable `sleep` in a fresh
  temp directory.
* The coder confirmation test only ever **declines** (`action=decline`,
  `force=false`). It never confirms a branch deletion and never deletes a real
  branch.
* Nothing in the repository is modified. Two scratch paths are created under
  the system temp directory and are left in place for inspection; the paths are
  printed in the report and in the JSON payload.
* No daemon is restarted or stopped. No raw `kill`/`pkill`/`killall` is used.
* On a shared host, unrelated jobs may make the daemons busier, so timings and
  concurrency checks can be slower, but they remain scoped to this run's
  clients and PIDs.
