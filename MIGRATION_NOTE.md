# MCP Server Migration Status

## Issue

Claude Code CLI auto-discovers MCP servers in the project directory and runs them directly, bypassing the global MCP config at `~/.config/claude/mcp.json`.

**Current behavior:**
- Claude Code finds `ninja_cli_mcp.server` module in the project
- Runs: `uv run python -m ninja_cli_mcp.server`
- Ignores global MCP config that specifies the three new servers (ninja-coder, ninja-researcher, ninja-secretary)

## Architecture

**New daemon-based architecture** (intended):
```
Claude Code → Proxy (ninja-daemon connect) → HTTP/SSE → Persistent Daemons
- ninja-coder (port 8100)
- ninja-researcher (port 8101)
- ninja-secretary (port 8102)
```

**Current auto-discovered setup** (what's happening):
```
Claude Code → ninja_cli_mcp.server (stdio, auto-discovered)
```

## Solutions

### Option 1: Remove old module (breaking)
```bash
rm -rf src/ninja_cli_mcp/
# Update pyproject.toml to remove ninja_cli_mcp references
```

### Option 2: Make old server proxy to new daemons (backward compatible)
Modify `src/ninja_cli_mcp/server.py` to:
- Detect which tools are being called
- Route to appropriate daemon (coder/researcher/secretary)
- Act as a multiplexer/router

### Option 3: Disable auto-discovery
- Check if Claude Code has a flag to disable auto-discovery
- Or move the project to use only the global MCP config

## Recommendation

Implement **Option 2** - make the old server act as a router. This provides:
- Backward compatibility for existing users
- Seamless transition to new architecture
- No breaking changes

The old `ninja_cli_mcp.server` becomes a thin routing layer that forwards requests to the appropriate daemon.
