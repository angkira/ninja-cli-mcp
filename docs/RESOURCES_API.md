# Resources API

Ninja servers implement the base MCP **Resources** primitive for one purpose
only: **serving skill files**. There is no "load a codebase as a resource" tool
and no resource-backed project cache — earlier versions of this document
described tools (`resource_codebase`, …) that were never implemented.

| Implemented | Not implemented |
| --- | --- |
| `resources/list` | `resources/subscribe` / `unsubscribe` (`subscribe: false`) |
| `resources/read` (text and binary) | resource templates (`resources/templates/list`) |
| `resources/directory/read` (SKILLS extension, opt-in, off today) | `listChanged` notifications |
| `skill://` URIs for every skill file | mutable resources / change events |

## Where resources come from

The catalog is the skill bundle each server ships (`src/ninja_common/dist/skills/<module>/`),
or the directory named by `NINJA_SKILLS_DIR`. One file is one resource:

```
skill://<skill-name>/SKILL.md          the skill's entry point (text/markdown)
skill://<skill-name>/<relative-path>   any other file in the bundle
```

`SKILL.md` carries the frontmatter's `name` and `description`; other files are
listed by their relative path. Skills themselves are advertised through the
`io.modelcontextprotocol/skills` extension (`skills/list`, `skills/get`) — see
[MCP_PROTOCOL_2026.md](MCP_PROTOCOL_2026.md#3-skills-iomodelcontextprotocolskills).

## `resources/list`

```json
{ "method": "resources/list", "params": {} }
```

```json
{
  "resources": [
    {
      "name": "submit-and-poll",
      "uri": "skill://submit-and-poll/SKILL.md",
      "description": "Run ninja-coder work in the background with coder_submit_* and the coder_job_status / coder_job_result loop instead of blocking on a synchronous tool call.",
      "mimeType": "text/markdown",
      "size": 3591
    },
    {
      "name": "references/checklist.md",
      "uri": "skill://submit-and-poll/references/checklist.md",
      "mimeType": "text/markdown",
      "size": 128
    }
  ]
}
```

The list is complete (not paginated) and sorted by skill name, then by path.
An empty catalog — a checkout without packaged skills, or a `NINJA_SKILLS_DIR`
that does not exist — returns `{"resources": []}` instead of failing.

## `resources/read`

Text file:

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

Binary file — the bytes are base64 in `blob`, with the type from the file
extension (or `application/octet-stream` when unknown):

```json
{
  "contents": [
    {
      "uri": "skill://alpha/assets/logo.bin",
      "mimeType": "application/octet-stream",
      "blob": "AAECAwQ="
    }
  ]
}
```

An unknown URI, a non-`skill://` URI, or a path that escapes its skill
directory is `-32602 INVALID_PARAMS` with `unknown resource: <uri>`. A missing
resource is never a crash and never an empty result.

## MIME types

| Extension | Type |
| --- | --- |
| `.md`, `.mdx`, `.markdown` | `text/markdown` |
| `.json`, `.toml`, `.yaml`, `.xml`, `.svg` | the corresponding text type |
| other | the system guess, else `application/octet-stream` |

Text types are returned in `text`; everything else is returned as a base64
`blob`.

## `resources/directory/read`

Defined by the Skills extension for listing the direct children of a directory
resource (subdirectories carry `inode/directory`). The ninja servers do **not**
enable it: `SkillsExtension(read_directory=True)` is the opt-in, and no server
passes it. A client must not assume the method exists.

## Limits

- 512 files and 16 MiB per skill; a bundle that exceeds either fails validation
  at host startup rather than being truncated.
- Reading is path-safe: `..` traversal and absolute paths are rejected.

## Verifying

```bash
uv run python -c "import ninja_coder.server"         # catalog loads
uv run pytest tests/test_common/mcp_ext/test_skills.py -q --no-cov
```
