# Ninja MCP — TODO

## In Progress

### Testing sequential/parallel plans
- [ ] reconnect MCP and run sequential test in /tmp
- [ ] run parallel test in /tmp
- [ ] confirm no multi-agent false trigger, no hangs, process group cleanup works

---

## Backlog

### 1. Tool descriptions: atomic task clarity
Make it crystal clear in MCP tool descriptions that tasks must be small and atomic.
- `coder_simple_task`: emphasize "one file / one function / one concern"
- `coder_execute_plan_sequential`: emphasize "each step = one atomic change"
- `coder_execute_plan_parallel`: same, plus "steps must not touch same files"
- Add bad/good examples in description
- Files: `src/ninja_coder/server.py` (TOOLS list), `src/ninja_coder/strategies/opencode_strategy.py` (system prompt)

### 2. Claude Skills from MCP tools
Package ninja-coder tools as Claude Code skills (.md files in `.claude/commands/`).
- Investigate Claude skill format: `/help`, test locally that Claude parses them
- Create skills for: `simple_task`, `sequential_plan`, `parallel_plan`
- On `ninja-config install` — copy skills to `~/.claude/commands/ninja/`
- On `ninja-config uninstall` — remove them
- Test locally first before shipping
- Skills format: markdown with `$ARGUMENTS` placeholder
- Reference: `~/.claude/` directory structure

### 3. opencode serve / ACP mode investigation
Replace `opencode run` (spawn-and-kill per task) with long-running server:
- **opencode serve**: HTTP server with SSE, web UI. API is SPA-based, likely tRPC or WebSocket
- **opencode acp**: Agent Client Protocol server — designed for programmatic access
- Benefits: no process spawn overhead, no pyright re-init per task, persistent sessions
- Action: find ACP API spec (check opencode source on GitHub), prototype a client
- If viable: replace `OpenCodeStrategy.build_command()` + subprocess with HTTP client
- This eliminates ALL process management issues (zombies, process groups, LSP hangs)

### 4. Remove ninja-prompts
Currently unclear what ninja-prompts does that isn't covered by Claude skills.
- [ ] Read `src/ninja_prompts/` — understand what it actually provides
- [ ] Check if anything depends on it
- [ ] Propose removal or consolidation to user
- Files: `src/ninja_prompts/`

### 5. Cleanup obsolete components on update
When `ninja-config update` runs, detect and offer to remove outdated daemons/components.
- Detect: daemons registered in config but no longer in current install
- Prompt user: "Found obsolete component X. Remove? [y/N]"
- Stop daemon, remove config entry, optionally remove binary
- File: `src/ninja_config/` (update command)

---

## Done

- [x] MCP request deduplication (RequestDeduplicator) — `3b840b3`
- [x] Activity-based subprocess timeout with CPU health check — `19b80b5`
- [x] Process group (start_new_session + killpg) — `8776399`
- [x] Child process watchdog (kill stuck pyright/tsserver) — `8776399`
- [x] Project-aware LSP config via XDG_CONFIG_HOME — `8776399`
- [x] Fix multi-agent auto-trigger on sequential/parallel steps — `587517e`
- [x] Fix analyze_task using system prompt instead of raw task text — `587517e`
