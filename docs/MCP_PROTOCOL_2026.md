# MCP 2026-07-28 Surface

Task-oriented guide to what the ninja servers speak on the wire in 2.0.0. Every
JSON fragment below was copied from the running servers, not from the upstream
specification; the test suite in `tests/test_mcp_protocol_extensions.py` and
`tests/test_common/mcp_ext/` asserts the same shapes.

- **SDK floor**: `mcp>=2.3.0,<3.0.0` (`pyproject.toml`).
- **Modern era**: protocol revision `2026-07-28`.
- **Legacy era**: `2024-11-05` … `2025-11-25`, served by the *same* server
  object, without the extension methods.

## 1. Connecting

One process serves one server over any transport; the protocol era is
negotiated per connection, not per process.

| Transport | How | Era |
| --- | --- | --- |
| stdio | `ninja-coder` / `python -m ninja_coder.server` (default) | negotiated |
| Streamable HTTP | `ninja-coder --http --port 8100`, endpoint `POST /mcp` | `2026-07-28` |
| Legacy HTTP+SSE | same process, `GET /sse` + `POST /messages` | pre-2026 |

HTTP mode binds one port and serves **both** transports from the same app
(`src/ninja_common/mcp_http.py`), so a modern client uses `/mcp` while an older
host keeps dialing `/sse`. Default ports: coder `8100`, researcher `8101`,
secretary `8102`, agent `8103`.

```bash
# Modern client: point the host at the streamable endpoint
ninja-coder --http --port 8100
#   -> http://127.0.0.1:8100/mcp   (2026-07-28)

# Legacy host: same process, SSE transport
#   -> GET  http://127.0.0.1:8100/sse
#   -> POST http://127.0.0.1:8100/messages
```

A `2026-07-28` client sees the extension blocks in the server capabilities; a
legacy client sees the plain surface only:

```json
{
  "resources": { "subscribe": false, "listChanged": false },
  "tools": { "listChanged": false },
  "extensions": {
    "io.modelcontextprotocol/skills": {},
    "io.modelcontextprotocol/tasks": {}
  }
}
```

## 2. Capability matrix

| Server | `skills` | `tasks` | `files` | Resources | Prompts |
| --- | --- | --- | --- | --- | --- |
| `ninja-coder` | yes (4 bundles) | yes (4 tools) | no | skill files | not implemented |
| `ninja-researcher` | yes (3 bundles) | yes (3 tools) | no | skill files | not implemented |
| `ninja-secretary` | yes (2 bundles) | yes (2 tools) | opt-in (1 tool) | skill files | not implemented |
| `ninja-agent` | yes (2 bundles) | yes (2 tools) | no | skill files | not implemented |

Extensions are advertised only to modern clients, i.e. they never appear in a
legacy connection's capabilities. Server-initiated push requests are not used
on `2026-07-28` at all — see §6.

## 3. Skills (`io.modelcontextprotocol/skills`)

Advertised by all four servers with empty settings. Three methods exist, all
bound at `2026-07-28` only; a legacy connection gets
`-32601 METHOD_NOT_FOUND`.

| Method | Purpose |
| --- | --- |
| `skills/list` | Page through the skill catalog |
| `skills/get` | One skill by the URI of its `SKILL.md` |
| `resources/directory/read` | Optional; **not enabled** by the ninja servers today |

Skill *content* is never inlined in `skills/list`; every file is a base
resource served through `resources/list` / `resources/read` (see
[RESOURCES_API.md](RESOURCES_API.md)).

### 3.1 `skills/list`

Request (empty params, optional cursor):

```json
{ "method": "skills/list", "params": {} }
```

Result, truncated to one skill:

```json
{
  "resultType": "complete",
  "skills": [
    {
      "uri": "skill://sequential-plan-authoring/SKILL.md",
      "frontmatter": {
        "name": "sequential-plan-authoring",
        "description": "Write coder_execute_plan_sequential steps that actually succeed, covering step granularity, context_paths, allowed_globs and deny_globs, test_plan and ordering."
      },
      "resources": [
        {
          "uri": "skill://sequential-plan-authoring/SKILL.md",
          "digest": "sha256:88f217ff9708c7ac4748c2c8b82f21a95ff8960e5d887fafb7ba1644aff01b71",
          "size": 3931
        }
      ]
    }
  ],
  "ttlMs": 0,
  "cacheScope": "private"
}
```

- `resources` is the complete manifest (`SKILL.md` included), or the literal
  `"dynamic"` for a generated skill. Per skill: at most 512 entries and 16 MiB.
- `nextCursor` is absent on the last page; page size is 50.
- Cursors are opaque and server-minted (`offset:<n>`); anything else is
  `-32602 INVALID_PARAMS`.
- `ttlMs`, `cacheScope` and `resultType` are 2026-only envelope fields and are
  stripped for a legacy peer.

### 3.2 `skills/get`

```json
{ "method": "skills/get", "params": { "uri": "skill://submit-and-poll/SKILL.md" } }
```

```json
{
  "resultType": "complete",
  "skill": {
    "uri": "skill://submit-and-poll/SKILL.md",
    "frontmatter": { "name": "submit-and-poll", "description": "Run ninja-coder work in the background with coder_submit_* and the coder_job_status / coder_job_result loop instead of blocking on a synchronous tool call." },
    "resources": [
      { "uri": "skill://submit-and-poll/SKILL.md", "digest": "sha256:ee06…678d", "size": 3591 }
    ]
  },
  "ttlMs": 0,
  "cacheScope": "private"
}
```

An unknown URI is `-32602` with `unknown resource: <uri>`.

### 3.3 Reading a skill file

```json
{ "method": "resources/read", "params": { "uri": "skill://submit-and-poll/SKILL.md" } }
```

```json
{
  "contents": [
    {
      "uri": "skill://submit-and-poll/SKILL.md",
      "mimeType": "text/markdown",
      "text": "---\nname: submit-and-poll\ndescription: Run ninja-coder work ..."
    }
  ]
}
```

### 3.4 Bundles shipped in 2.0.0

Bundles live in `src/ninja_common/dist/skills/<module>/`; `NINJA_SKILLS_DIR`
overrides the directory a server serves (a missing directory yields an empty
catalog, not a startup failure).

**coder (4)**

| Skill | What it covers |
| --- | --- |
| `sequential-plan-authoring` | Writing `coder_execute_plan_sequential` steps that succeed: granularity, `context_paths`, `allowed_globs`/`deny_globs`, `test_plan`, ordering. |
| `submit-and-poll` | Running work in the background via `coder_submit_*` + `coder_job_status`/`coder_job_result` instead of blocking a sync call. |
| `tasks-vs-jobs` | Choosing between the Tasks extension (`resultType: "task"`, `tasks/get`, `tasks/cancel`) and the always-available submit/poll job tools. |
| `worktree-review-merge` | Reviewing, merging or discarding the `ninja/*` isolation branches plans leave behind. |

**researcher (3)**

| Skill | What it covers |
| --- | --- |
| `arxiv-and-papers` | `researcher_arxiv_search` plus section/number extraction from a paper with `researcher_paper_fetch`, paced. |
| `citation-fact-check` | Verifying a claim with `researcher_fact_check` and reporting verified/disputed/uncertain honestly. |
| `deep-research-playbook` | Sequencing `quick_research` → `deep_research` → `deep_research_batch` → `summarize_sources` → `generate_report`, including typed rate-limit errors. |

**secretary (2)**

| Skill | What it covers |
| --- | --- |
| `codebase-orientation` | Orienting in an unfamiliar repo with `secretary_codebase_report`, narrowing with `secretary_file_search`, reading one file with `secretary_analyse_file`. |
| `session-handoff` | Closing a session with `secretary_session_report` and `secretary_update_documentation` so decisions survive. |

**agent (2)**

| Skill | What it covers |
| --- | --- |
| `guarded-shell-operations` | Single guarded commands with `agent_exec_command`, triage with `agent_tail_logs`/`agent_processes`/`agent_jobs_overview`. |
| `pipeline-diagnosis` | Choosing between `agent_run_and_diagnose` and `agent_exec_pipeline`, reading distilled failures, escalating at the right point. |

## 4. Tasks (`io.modelcontextprotocol/tasks`)

Advertised by all four servers with empty settings. The extension is **not**
the 1.x experimental Tasks API: there is no `tasks/result` and no
`tasks/list`. The result travels inside `tasks/get`.

| Method | Purpose |
| --- | --- |
| `tasks/get` | Poll one task; returns status plus `result`, `error` or `inputRequests` |
| `tasks/update` | Answer outstanding `inputRequests` (acknowledgement only) |
| `tasks/cancel` | Cooperative cancel; idempotent on terminal tasks |

### 4.1 When a task handle is returned

A handle is returned **only** when both hold:

1. the client declared `io.modelcontextprotocol/tasks` in
   `ClientCapabilities.extensions`, and
2. the connection negotiated `2026-07-28`.

Otherwise the tool runs synchronously and returns its ordinary result — the
surface pre-2026 clients already know.

Task-enabled tools (`TASK_TOOLS` in each `server.py`):

| Server | Tools |
| --- | --- |
| coder | `coder_simple_task`, `coder_execute_plan_sequential`, `coder_execute_plan_parallel`, `coder_multi_agent_task` |
| researcher | `researcher_deep_research`, `researcher_deep_research_batch`, `researcher_paper_fetch` |
| secretary | `secretary_codebase_report`, `secretary_analyse_file` |
| agent | `agent_run_and_diagnose`, `agent_exec_pipeline` |

Every other tool — including `coder_submit_*`, `coder_job_*`, `researcher_quick_research`,
`secretary_file_search`, `secretary_session_report`, `agent_exec_command` — is
always synchronous.

### 4.2 Worked lifecycle

**Start** (an ordinary `tools/call` for a task-enabled tool):

```json
{
  "method": "tools/call",
  "params": {
    "name": "agent_exec_pipeline",
    "arguments": { "repo_root": "/tmp", "steps": [{ "command": "true" }] }
  }
}
```

The call returns a task handle instead of the pipeline result:

```json
{
  "taskId": "8c5144e5-25e6-44e2-bfb7-b95f093e1ffd",
  "status": "working",
  "createdAt": "2026-11-25T16:15:45.868690+00:00",
  "lastUpdatedAt": "2026-11-25T16:15:45.868690+00:00",
  "pollIntervalMs": 500,
  "resultType": "task"
}
```

**Poll** at `pollIntervalMs`:

```json
{ "method": "tasks/get", "params": { "taskId": "8c5144e5-25e6-44e2-bfb7-b95f093e1ffd" } }
```

```json
{
  "taskId": "8231e14f-fb1b-451b-9636-7403b80321c8",
  "status": "completed",
  "createdAt": "2026-11-25T16:15:39.485761+00:00",
  "lastUpdatedAt": "2026-11-25T16:15:39.497371+00:00",
  "pollIntervalMs": 500,
  "resultType": "complete",
  "result": {
    "content": [{ "type": "text", "text": "{ \"success\": true, … }" }],
    "structuredContent": {
      "success": true,
      "summary": "Pipeline succeeded: 1/1 steps succeeded in 0.01s.",
      "total_duration_seconds": 0.006,
      "steps": [{ "command": "true", "success": true, "returncode": 0, "skipped": false }]
    },
    "isError": false,
    "resultType": "complete"
  }
}
```

`status` is `working`, `input_required`, `completed`, `failed` or `cancelled`.
Depending on it, `tasks/get` carries exactly one of:

- `result` — the stored `CallToolResult` (the same payload the synchronous call
  returns), when `completed`;
- `error` — a JSON-RPC error object (`code`, `message`, optional `data`), when
  `failed`;
- `inputRequests` — the outstanding structured requests, when `input_required`
  (the ninja servers do not raise this today; the field exists for parity).

**Answer** outstanding input (only if `inputRequests` was returned):

```json
{
  "method": "tasks/update",
  "params": {
    "taskId": "…",
    "inputResponses": { "<key>": { "…": "…" } }
  }
}
```

The result is an acknowledgement, `{"resultType": "complete"}`. Responses for
keys the server never asked about are ignored, not rejected.

**Cancel**:

```json
{ "method": "tasks/cancel", "params": { "taskId": "…" } }
```

Cancellation is cooperative: the running work is signalled, and the server waits
up to 15 s for it to observe the cancellation before recording `cancelled` and
stopping the detached work. On an already-terminal task it is **not** an error —
you get the current `tasks/get`-shaped state back, so you can see why nothing
was cancelled. An unknown id is `-32602`.

**Client helpers**: `ninja_common.mcp_ext.tasks_client.TasksClient` plugs into
`Client(extensions=[...])` and polls `tasks/get` transparently, so `call_tool`
returns the final `CallToolResult`. `mcp.client.advertise(TASKS_EXTENSION_ID)`
declares the extension but leaves the raw envelope in your hands.

> **Warning — advertise is not enough.** Declaring
> `io.modelcontextprotocol/tasks` without also registering a claim resolver is a
> footgun: the server returns a task handle, the SDK tries to claim it, finds no
> resolver, and rejects the handle, so the call fails even though the task is
> running server-side and will complete. Advertising the extension only tells the
> server you understand task envelopes; the resolver is what turns one into a
> result. Either use `TasksClient` (which wires the resolver for you) or register
> the resolver yourself before the first task-returning call.


### 4.3 Durable state

Task rows live in SQLite (`NINJA_TASKS_DB`, default `~/.ninja/tasks.db`, WAL +
busy timeout + lazy TTL expiry) and are shared with the `coder_submit_*` job
API. On startup, rows still `working` whose owner process is demonstrably dead
are reconciled to `failed`; live sibling processes and rows with unknown
ownership are never touched.

### 4.4 Background work without the extension

Hosts that do not declare the Tasks extension still get background execution
through ordinary tools: `coder_submit_simple|sequential|parallel` →
`coder_job_status` → `coder_job_result` (or `coder_job_cancel`,
`coder_jobs_list`). See [MCP_TASKS.md](MCP_TASKS.md).

## 5. Elicitation

`2026-07-28` has no server-initiated requests mid-call, so a confirmation the
server needs is a **multi-round-trip** (MRTR) exchange: the tool call returns an
`input_required` result, the client collects the answer, and retries the same
call with the responses plus the server's sealed `requestState`.

`coder_branch_discard` is the one tool that asks. When the branch holds unmerged
commits and `force` is not set, the first call returns:

```json
{
  "resultType": "input_required",
  "inputRequests": {
    "confirm_branch_delete": {
      "method": "elicitation/create",
      "params": {
        "message": "Branch 'ninja/demo' has unmerged commits. Delete it anyway?",
        "mode": "form",
        "requestedSchema": {
          "type": "object",
          "properties": {
            "confirm": {
              "type": "boolean",
              "title": "Delete branch",
              "description": "Confirm: delete branch ninja/demo"
            }
          },
          "required": ["confirm"]
        }
      }
    }
  },
  "requestState": "v1.5M4ZRTJ66IpsALf8M6X8Jap4HNozb4YMUhaHqDFqyCum…"
}
```

`requestState` is sealed: the handler mints plain JSON naming the operation,
branch and repository, and the `RequestStateBoundary` encrypts it before it
reaches the wire. A client must echo it back **verbatim**; it is not readable
and not forgeable.

The client retries the same `tools/call` with both fields:

```json
{
  "method": "tools/call",
  "params": {
    "name": "coder_branch_discard",
    "arguments": { "repo_root": "/tmp", "branch": "ninja/demo" },
    "inputResponses": {
      "confirm_branch_delete": { "action": "accept", "content": { "confirm": true } }
    },
    "requestState": "v1.5M4ZRTJ66IpsALf8M6X8Jap4HNozb4YMUhaHqDFqyCum…"
  }
}
```

A confirmation now returns the ordinary result:

```json
{
  "structuredContent": {
    "status": "ok",
    "branch": "ninja/demo",
    "message": "Deleted branch ninja/demo (confirmed via elicitation)"
  },
  "isError": false,
  "resultType": "complete"
}
```

- Declining (`action` ≠ `accept`, or `confirm: false`) returns the original
  refusal unchanged; the branch stays.
- A retry without `requestState`, or with one minted for another operation,
  branch or repository, is `-32602 INVALID_PARAMS`.
- A retry that omits `inputResponses` re-asks, so a client can re-render the
  prompt safely.

On a **legacy** connection the same decision is still asked push-style (a
server-initiated `elicitation/create` mid-call, because pre-2026 revisions allow
it). Clients that cannot elicit keep the plain refusal — pass `force: true` to
skip the question.

## 6. File uploads (`io.modelcontextprotocol/files`, opt-in)

Off by default. Set `NINJA_MCP_ENABLE_FILE_UPLOADS=1` (`true`, `yes` or `on`
also work) on **ninja-secretary** to advertise the extension and the one tool
that accepts files. With the flag off, neither the capability nor the tool
exists, so a client sees the pre-2.0 surface.

```bash
NINJA_MCP_ENABLE_FILE_UPLOADS=1 ninja-secretary
```

```json
{ "io.modelcontextprotocol/files": { "maxInlineBytes": 8388608 } }
```

- **Inline only.** 8 MiB (`8388608` bytes) of decoded payload per request. The
  server never advertises `upload` and never mints an upload target; a file
  argument without `data` is rejected.
- **No download targets.** Downloads are not served (an extension cannot
  contribute an HTTP route, and the lowlevel `custom_route` is unauthenticated).
  Tools that produce files return embedded resources instead.

The advertised tool is `secretary_ingest_file`, whose `file` argument is an
object carrying `x-mcp-file`:

```json
{
  "properties": {
    "file": {
      "type": "object",
      "properties": {
        "id": { "type": "string", "minLength": 1, "maxLength": 128 },
        "name": { "type": "string" },
        "mimeType": { "type": "string" },
        "size": { "type": "integer", "minimum": 0 },
        "digest": {
          "type": "object",
          "properties": {
            "algorithm": { "const": "sha-256" },
            "value": { "type": "string" }
          },
          "required": ["algorithm", "value"]
        },
        "data": { "type": "string" }
      },
      "required": ["id", "mimeType", "size"],
      "x-mcp-file": {
        "accept": ["application/pdf", "text/csv", "text/plain", "image/png", "image/jpeg"],
        "maxSize": 8388608
      }
    }
  },
  "required": ["file"]
}
```

Call it with base64 bytes (`data`) and, optionally, for integrity checking, the
base64url-encoded SHA-256 digest of the original bytes:

```json
{
  "method": "tools/call",
  "params": {
    "name": "secretary_ingest_file",
    "arguments": {
      "file": {
        "id": "file-1",
        "name": "greeting.txt",
        "mimeType": "text/plain",
        "size": 23,
        "digest": { "algorithm": "sha-256", "value": "CjhSX3ciiv50Zr7BoYoyLVtJ7k5xoeqoMFCMClurFg4" },
        "data": "aGVsbG8sIGZpbGVzIGV4dGVuc2lvbgo="
      }
    }
  }
}
```

```json
{
  "structuredContent": {
    "name": "greeting.txt",
    "mime_type": "text/plain",
    "size": 23,
    "digest": "CjhSX3ciiv50Zr7BoYoyLVtJ7k5xoeqoMFCMClurFg4",
    "first_bytes_hex": "68656c6c6f2c2066696c657320657874656e73696f6e0a"
  },
  "isError": false
}
```

A size over the limit, an out-of-band file (no `data`), a size or digest
mismatch, or invalid base64 is an error result (`isError: true`) that names the
problem and never echoes file content back into the transcript. `accept` is an
advisory hint for the host's file picker; the server does not reject a media
type outside it.

## 7. What these servers deliberately do not use

Removed or deprecated by the protocol, and therefore absent from every server
(each answers `-32601 METHOD_NOT_FOUND` when asked anyway):

| Removed surface | Status in 2.0.0 |
| --- | --- |
| `ping` | not implemented, `-32601` |
| `logging/setLevel` | not implemented, `-32601` (logs go to stderr / the log files) |
| `roots` | not used; tool arguments carry `repo_root` explicitly |
| `sampling` | not used; servers call their own models |
| `resources/subscribe` | advertised as `false`; resources are static skill files |
| server-initiated requests at `2026-07-28` | not used; replaced by MRTR (§5) |
| `tasks/result`, `tasks/list` | removed from the 1.x API; use `tasks/get` (§4) |
| `prompts` | not implemented at all |
| resource templates | not implemented; skill URIs are concrete |

## 8. Verifying a change to this document

```bash
# Every tool named here exists in some server
grep -rn 'name="coder_branch_discard"' src/

# The servers still import and build
uv run python -c "import ninja_coder.server, ninja_researcher.server, ninja_secretary.server, ninja_agent.server"

# The wire shapes above
uv run pytest tests/test_mcp_protocol_extensions.py tests/test_mcp_elicitation.py tests/test_common/mcp_ext/ -q --no-cov
```
