# Ninja Secretary Module

📋 Codebase reports, file analysis, search, and session tracking via MCP.

## Overview

The Secretary module serves **six** MCP tools. It reads and reports; it never
writes source code. Documentation edits are the one write it performs, and only
inside `docs/`.

> Earlier versions of this page advertised `secretary_read_file`,
> `secretary_grep`, `secretary_file_tree` and git tools (`secretary_git_status`,
> `secretary_git_diff`, …). Those tools are **not served** — the request models
> still exist in `models.py`, but no server method exposes them. Use
> `secretary_analyse_file` (whole file) and `secretary_file_search` (glob +
> optional content regex) instead.

## Installation

```bash
pip install -e ".[secretary]"     # secretary dependencies
pip install -e ".[all]"           # everything
```

## Usage

```bash
# stdio (default)
ninja-secretary

# HTTP: streamable at /mcp, legacy SSE at /sse + /messages
ninja-secretary --http --port 8102
```

## MCP Tools

### 1. `secretary_analyse_file`

Analyse one file: language, line count, structure (functions, classes, imports),
a preview, and a short model-written summary.

```json
{ "file_path": "/path/to/project/src/app.py" }
```

```json
{
  "status": "ok",
  "message": "File analysis completed successfully",
  "result": {
    "file": "/path/to/project/src/app.py",
    "language": "python",
    "lines_total": 7,
    "structure": {
      "functions": [{ "name": "add" }, { "name": "hello" }],
      "classes": [{ "name": "Greeter" }],
      "imports": []
    },
    "summary": "{\"status\":\"ok\",\"summary\":\"A 7-line Python module providing …\",\"touched_paths\":[]}",
    "preview": "def add(a, b):\n    return a + b\n…"
  }
}
```

- `file_path` must exist and be a file; otherwise `status: "error"` with the
  reason and an empty `result`.
- Reads UTF-8 with replacement, so a binary file does not crash the call.
- Task-enabled for 2026-07-28 clients that declared
  `io.modelcontextprotocol/tasks` (see [MCP_PROTOCOL_2026.md](../MCP_PROTOCOL_2026.md)).

### 2. `secretary_file_search`

Find files by glob, optionally filtered by a content regex.

```json
{
  "pattern": "**/*.py",
  "repo_root": "/path/to/project",
  "content_regex": "async def \\w+"
}
```

```json
{
  "status": "ok",
  "matches": [
    { "path": "src/app.py", "size": 90, "modified": "2026-11-25T17:16:32.119644" }
  ],
  "total_count": 1,
  "truncated": false,
  "message": ""
}
```

- `repo_root` is **required** by the implementation even though the advertised
  schema lists only `pattern` as required; omitting it returns
  `{"success": false, "error": "1 validation error … repo_root Field required"}`.
- Paths in `matches` are relative to `repo_root`.
- `.git`, `node_modules`, `__pycache__`, `venv` and `.venv` are skipped, as are
  files over 5 MiB.
- An invalid `content_regex` returns `status: "error"` with the regex problem in
  `message`; it never raises.

### 3. `secretary_codebase_report`

Project structure, file counts, language mix, metrics, and a model-written
architecture summary in Markdown.

```json
{ "repo_root": "/path/to/project" }
```

```json
{
  "status": "ok",
  "report": "# Codebase Report: project\n\n**Generated:** …\n\n## Project Structure\n…",
  "metrics": {
    "file_count": 2,
    "dir_count": 0,
    "total_size_mb": 2.57e-05,
    "total_lines": 2,
    "extensions": { "md": 1, "py": 1 },
    "dependencies": []
  },
  "file_count": 2
}
```

- The tool schema also advertises `include_patterns` / `exclude_patterns`; the
  executor ignores both (the request model has no such fields). Use
  `secretary_file_search` to scope a subset.
- Task-enabled on 2026-07-28 for declaring clients.

### 4. `secretary_document_summary`

Summarise documentation: per-file headings/first paragraphs plus a combined
overview.

```json
{
  "repo_root": "/path/to/project",
  "doc_patterns": ["**/*.md", "**/README*", "**/CONTRIBUTING*"]
}
```

```json
{
  "status": "ok",
  "summaries": [
    { "path": "README.md", "title": "README.md", "summary": "# Demo", "size": 43 }
  ],
  "combined_summary": "**README.md**: # Demo",
  "doc_count": 1
}
```

### 5. `secretary_session_report`

Read the tracked session state: start time, last update, tools used, files
accessed, summary, metadata.

```json
{ "session_id": "my-session" }
```

```json
{
  "session_id": "my-session",
  "started_at": "2026-11-25T17:18:28.889640",
  "last_updated": "2026-11-25T17:18:28.889647",
  "tools_used": [],
  "files_accessed": [],
  "summary": "No session data",
  "metadata": {}
}
```

- Omitting `session_id` returns an index of known sessions.
- The request model also accepts `action` (`get` | `update` | `create`, default
  `get`) and `updates`, but the advertised schema exposes only `session_id`;
  treat those as internal.

### 6. `secretary_update_documentation`

Write documentation under `docs/<module_name>/`: `README.md`, `API.md` or
`CHANGELOG.md`, with `mode` = `replace` | `append` | `prepend`.

```json
{
  "module_name": "coder",
  "doc_type": "readme",
  "content": "# New Content\n",
  "mode": "replace"
}
```

```json
{
  "status": "ok",
  "doc_path": "docs/coder/README.md",
  "changes_made": "Replaced entire document"
}
```

This is the only tool in the module that mutates the filesystem, and it is
marked destructive in its annotations.

### Opt-in: `secretary_ingest_file`

Available only with `NINJA_MCP_ENABLE_FILE_UPLOADS=1`. Validates one inline
file upload (≤ 8 MiB) and returns its name, MIME type, size, SHA-256 digest and
first 32 bytes in hex — the content is never echoed. See
[MCP_PROTOCOL_2026.md](../MCP_PROTOCOL_2026.md#6-file-uploads-iomodelcontextprotocolfiles-opt-in).

## Resources and extensions

- **Skills**: 2 bundles (`codebase-orientation`, `session-handoff`) served via
  `skills/list` / `skills/get`; the files are readable through
  `resources/read`.
- **Tasks**: `secretary_codebase_report` and `secretary_analyse_file` become
  durable tasks for 2026-07-28 clients that declared the extension.
- **Files**: off by default, secretary only.

## Architecture

```
ninja_secretary/
├── __init__.py     # Module exports
├── models.py       # Pydantic request/result models (some unused, see above)
├── server.py       # Lowlevel Server: tool list, dispatch, extensions
├── tools.py        # SecretaryToolExecutor: the actual implementations
└── hooks_cli.py    # Hook entry points used by hosts
```

- `SecretaryToolExecutor` owns every implementation; `server.py` only validates
  arguments and shapes results.
- Session state is an in-process dict keyed by `session_id`; it does not survive
  a restart.
- Tree-sitter dependencies are installed but not used by the current
  implementation.

## Examples

### Orient in an unfamiliar repo

```python
report = await client.call_tool("secretary_codebase_report", {
    "repo_root": "/path/to/project",
})
files = await client.call_tool("secretary_file_search", {
    "pattern": "**/main.*", "repo_root": "/path/to/project",
})
detail = await client.call_tool("secretary_analyse_file", {
    "file_path": "/path/to/project/" + files.structured_content["matches"][0]["path"],
})
```

### Close a session

```python
await client.call_tool("secretary_session_report", {
    "session_id": "code-review-123",
    "action": "update",
    "updates": {"summary": "Reviewed authentication", "files_accessed": ["src/auth.py"]},
})
final = await client.call_tool("secretary_session_report", {"session_id": "code-review-123"})
await client.call_tool("secretary_update_documentation", {
    "module_name": "auth",
    "doc_type": "readme",
    "content": "# Auth module\n",
})
```

## Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| `status: "error"`, "File not found" | `file_path` is resolved relative to the server's cwd; pass an absolute path or a path relative to `repo_root` |
| `truncated: true` in a search | Narrow the glob, add `content_regex`, or search a subtree |
| Empty `matches` | The pattern is glob-style (`**/*.py`), not a shell expansion; check `repo_root` |
| Report has no "AI Insights" | The report is still valid; the model summary is best-effort |

## License

MIT License - see the main project LICENSE file.
