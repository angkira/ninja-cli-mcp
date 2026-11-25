# Prompts: not implemented

Ninja servers do **not** implement the MCP Prompts primitive.

A `2026-07-28` client sees no `prompts` block in the server capabilities, and
these methods all answer `-32601 METHOD_NOT_FOUND`:

- `prompts/list`
- `prompts/get`

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

> This document previously described `prompt_registry`, `prompt_suggest` and
> `prompt_chain` tools. Those tools never existed in the published servers and
> have been removed from the documentation in 2.0.0.

## What to use instead

| Need | Use |
| --- | --- |
| Reusable, versioned guidance for the model | **Skills** — `skills/list`, `skills/get`, and `resources/read` for the file bodies. See [MCP_PROTOCOL_2026.md](MCP_PROTOCOL_2026.md#3-skills-iomodelcontextprotocolskills). |
| Server-provided instructions | The `instructions` string the server returns in its initialize result |
| Parameterized work | Ordinary tool calls with arguments (for example `researcher_deep_research`) |
| Long-form playbooks | The bundled skills under `src/ninja_common/dist/skills/` |

If you need prompt templates today, keep them in the host (custom commands,
snippets, or a system prompt) — the server will not serve them.
