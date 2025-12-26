# Proxy Architecture: Stdio ↔ HTTP/SSE Bridge

**Date**: December 25, 2024
**Status**: ✅ Implemented

## Architecture

```
Claude Code → stdio → Proxy → HTTP/SSE → Daemon (persistent)
```

## Components

### 1. HTTP/SSE Daemons (Persistent)
- **Ports**: 8100 (coder), 8101 (researcher), 8102 (secretary)
- **URLs**: http://127.0.0.1:8100/sse
- **Status**: All running ✅

### 2. Stdio Proxy (Ephemeral)
- **Command**: `ninja-daemon connect <module>`
- **Function**: Bridges stdio ↔ HTTP/SSE
- **Location**: `src/ninja_common/daemon.py:stdio_to_http_proxy()`

### 3. MCP Config
- **File**: `~/.config/claude/mcp.json`
- **Command**: `uv run ninja-daemon connect coder`

## Usage

**Start daemons**:
```bash
ninja-daemon start coder
ninja-daemon start researcher  
ninja-daemon start secretary
```

**Check status**:
```bash
ninja-daemon status
```

**Restart Claude Code** to connect via proxy!

## Status
1. ✅ Daemons running on ports 8100, 8101, 8102
2. ✅ Proxy implemented and tested
3. ✅ MCP config updated
4. ✅ Proxy successfully communicates with daemons
5. ⏳ **Ready for Claude Code restart to test integration**

## Testing

Manual proxy test successful:
```bash
./test_proxy.sh
# Successfully initialized MCP connection
# Received server info from ninja-coder daemon
```
