# MCP Architecture Guide

## Overview

The Model Context Protocol (MCP) is a standardized protocol for AI assistants to communicate with external tools and services. This document explains how Ninja MCP modules work with Claude Code and other MCP-compatible clients.

## MCP Protocol Basics

### Communication Model

MCP uses **stdio (standard input/output)** for communication:

```
┌─────────────────┐         stdio          ┌──────────────────┐
│                 │◄──────────────────────►│                  │
│  Claude Code    │    JSON-RPC over       │   MCP Server     │
│   (Client)      │      stdin/stdout      │ (ninja-researcher)│
│                 │                        │                  │
└─────────────────┘                        └──────────────────┘
```

- **Client** (Claude Code, Cursor, VS Code): Launches MCP servers and sends tool requests
- **Server** (ninja-researcher, ninja-secretary): Processes requests and returns results
- **Protocol**: JSON-RPC 2.0 over stdio

### Server Lifecycle

1. **Launch**: Client spawns server process with configured command
2. **Initialize**: Handshake to exchange capabilities
3. **Request/Response**: Client sends tool calls, server responds
4. **Shutdown**: Server terminates when client disconnects

## Ninja MCP Architecture

### Module Structure

Each Ninja module is an **independent MCP server**:

```
ninja-mcp/
├── src/
│   ├── ninja_common/        # Shared utilities
│   │   ├── logging_utils.py
│   │   ├── security.py
│   │   ├── metrics.py
│   │   └── daemon.py
│   │
│   ├── ninja_coder/         # Coder MCP Server
│   │   ├── server.py        # MCP stdio server
│   │   ├── tools.py         # Tool implementations
│   │   └── models.py        # Pydantic models
│   │
│   ├── ninja_researcher/    # Researcher MCP Server
│   │   ├── server.py
│   │   ├── tools.py
│   │   └── models.py
│   │
│   └── ninja_secretary/     # Secretary MCP Server
│       ├── server.py
│       ├── tools.py
│       └── models.py
```

### Server Implementation

Each MCP server follows this pattern:

```python
# server.py
from mcp.server import Server
from mcp.server.stdio import stdio_server

def create_server() -> Server:
    server = Server("ninja-researcher", version="0.2.0")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> Sequence[TextContent]:
        # Execute tool and return result
        pass

    return server

async def main():
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, ...)

def run():
    asyncio.run(main())
```

## Claude Code Integration

### Configuration

Claude Code reads MCP servers from `~/.config/claude/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"],
      "env": {
        "OPENROUTER_API_KEY": "...",
        "SERPER_API_KEY": "..."
      }
    },
    "ninja-secretary": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_secretary.server"]
    }
  }
}
```

### Server Execution Modes

#### Mode 1: On-Demand (Default)

Claude Code **starts servers when needed**:

```
User sends message → Claude decides to use tool →
  Launch server → Send request → Get response → Kill server
```

**Pros:**
- No background processes
- Clean startup/shutdown
- No resource usage when idle

**Cons:**
- Startup latency (~1-2 seconds per request)
- No state persistence between requests

#### Mode 2: Daemon (Optional)

Servers run as **background daemons**:

```bash
# Start daemon
ninja-daemon start researcher

# Server runs in background
ps aux | grep ninja-researcher

# Claude Code connects to running daemon
```

**Pros:**
- Instant response (no startup time)
- State persistence (e.g., session tracking)
- Faster for repeated requests

**Cons:**
- Background resource usage
- Need to manage daemon lifecycle
- More complex setup

### How Claude Code Uses MCP

1. **Tool Discovery**:
   ```
   Claude Code → list_tools() → Server returns available tools
   ```

2. **Tool Execution**:
   ```
   User: "Search for Python tutorials"
   Claude: Uses researcher_web_search tool
   Client → call_tool(name="researcher_web_search", args={...})
   Server → processes → returns results
   Claude: Synthesizes results into response
   ```

3. **Error Handling**:
   - Servers return errors as JSON: `{"status": "error", "error": "..."}`
   - Claude Code shows errors to user or retries

## Daemon Architecture

### Daemon Manager

```python
# ninja_common/daemon.py
class DaemonManager:
    """Manage MCP server daemons."""

    def start(self, module: str):
        """Start a module as daemon."""
        # Fork process, redirect stdio, save PID

    def stop(self, module: str):
        """Stop running daemon."""
        # Read PID, send SIGTERM

    def status(self):
        """Check daemon status."""
        # Read PIDs, check if alive
```

### Usage

```bash
# Start all daemons
ninja-daemon start coder
ninja-daemon start researcher
ninja-daemon start secretary

# Check status
ninja-daemon status
# → coder: running (PID 12345)
# → researcher: running (PID 12346)
# → secretary: running (PID 12347)

# Stop a daemon
ninja-daemon stop researcher

# Restart
ninja-daemon restart coder
```

## Request/Response Flow

### Example: Web Search

```
┌──────────────┐
│ Claude Code  │
└───────┬──────┘
        │
        │ 1. User: "Search for Python tutorials"
        │
        ▼
    ┌────────────────┐
    │ Claude decides │
    │ to use tool    │
    └───────┬────────┘
            │
            │ 2. call_tool(
            │      name="researcher_web_search",
            │      args={"query": "Python tutorials", ...}
            │    )
            ▼
    ┌─────────────────────┐
    │ ninja-researcher    │
    │ server.py           │
    └──────────┬──────────┘
               │
               │ 3. Validate request
               ▼
    ┌─────────────────────┐
    │ tools.py            │
    │ - Rate limiting     │
    │ - Search provider   │
    │ - Fetch results     │
    └──────────┬──────────┘
               │
               │ 4. Return JSON result
               ▼
    ┌─────────────────────┐
    │ Claude synthesizes  │
    │ results             │
    └──────────┬──────────┘
               │
               │ 5. Show to user
               ▼
        "I found 10 tutorials..."
```

### Request Format (JSON-RPC)

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/call",
  "params": {
    "name": "researcher_web_search",
    "arguments": {
      "query": "Python tutorials",
      "max_results": 10,
      "search_provider": "duckduckgo"
    }
  }
}
```

### Response Format

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"status\": \"ok\", \"results\": [...]}"
      }
    ]
  }
}
```

## Security Considerations

### Rate Limiting

All tools use rate limiting to prevent abuse:

```python
@rate_limited(max_calls=30, time_window=60)
async def web_search(request, client_id):
    # Only 30 calls per minute per client
    pass
```

### Input Validation

All inputs are validated with Pydantic:

```python
class WebSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    max_results: int = Field(default=10, ge=1, le=50)
    search_provider: str = Field(default="duckduckgo")
```

### Path Safety

Secretary module validates file paths:

```python
# Prevent directory traversal
if ".." in file_path or file_path.startswith("/"):
    return error("Invalid path")
```

### API Key Management

API keys are stored in environment variables, not in code:

```bash
# ~/.ninja-mcp.env
export OPENROUTER_API_KEY="sk-..."
export SERPER_API_KEY="..."
```

## Performance Optimization

### Parallel Execution

Researcher uses asyncio for parallel operations:

```python
# Search 4 queries in parallel
async def deep_research(request):
    semaphore = asyncio.Semaphore(request.parallel_agents)

    async def search_query(query):
        async with semaphore:
            return await provider.search(query)

    results = await asyncio.gather(*[
        search_query(q) for q in queries
    ])
```

### Caching

- Search results: In-memory cache (15 min TTL)
- Session data: In-memory dict (Secretary)
- File reads: OS filesystem cache

### Resource Limits

- **Memory**: ~50MB per server idle, ~200MB under load
- **CPU**: Mostly I/O bound, minimal CPU usage
- **Network**: Depends on search/fetch operations

## Logging and Monitoring

### Logging Strategy

```python
# All output to stderr (stdout reserved for MCP protocol)
logger = get_logger(__name__)
logger.info("Processing request...")
logger.error("Failed to fetch: {e}")
```

### Log Locations

```bash
# Foreground mode: stderr (visible in terminal)
ninja-researcher 2>&1 | tee researcher.log

# Daemon mode: log files
~/.cache/ninja-mcp/logs/researcher.log
~/.cache/ninja-mcp/logs/secretary.log
```

### Metrics

```python
@monitored
async def web_search(request):
    # Automatically logs:
    # - Execution time
    # - Success/failure
    # - Token usage (if applicable)
    pass
```

## Testing

### Unit Tests

Test individual tools in isolation:

```python
@pytest.mark.asyncio
async def test_web_search():
    executor = get_executor()
    request = WebSearchRequest(query="test")
    result = await executor.web_search(request)
    assert result.status == "ok"
```

### Integration Tests

Test full MCP server:

```bash
# Start server
python -m ninja_researcher.server &

# Send MCP request
echo '{"jsonrpc":"2.0","method":"tools/call",...}' | python -m ninja_researcher.server

# Check response
```

### End-to-End Tests

Test with actual Claude Code:

```bash
# Configure in mcp.json
claude "Search for Python tutorials using researcher"
```

## Troubleshooting

### Server Won't Start

```bash
# Check Python version
python3 --version  # Need 3.11+

# Check dependencies
uv sync --extra researcher

# Test directly
python -m ninja_researcher.server
```

### Tools Not Showing in Claude

```bash
# Verify mcp.json
cat ~/.config/claude/mcp.json

# Check server can be launched
uv run python -m ninja_researcher.server

# Check Claude logs
tail -f ~/Library/Logs/Claude/mcp.log
```

### Rate Limit Errors

```python
# Increase rate limits (for testing only)
@rate_limited(max_calls=100, time_window=60)
```

### Performance Issues

```bash
# Check daemon status
ninja-daemon status

# Restart daemons
ninja-daemon restart all

# Check resource usage
ps aux | grep ninja
top -pid $(pgrep -f ninja-researcher)
```

## Best Practices

### For Users

1. **Use daemons for frequent use**: Start daemons if using tools repeatedly
2. **Configure API keys properly**: Store in environment, not in config files
3. **Monitor resource usage**: Check memory/CPU if running multiple daemons
4. **Keep modules updated**: `git pull && uv sync`

### For Developers

1. **Follow MCP protocol strictly**: Use official `mcp` library
2. **Validate all inputs**: Use Pydantic models
3. **Log to stderr only**: stdout reserved for MCP communication
4. **Handle errors gracefully**: Return error status, don't crash
5. **Rate limit appropriately**: Prevent abuse while allowing normal use
6. **Test thoroughly**: Unit, integration, and E2E tests

## Future Enhancements

### Planned Features

1. **WebSocket support**: For real-time updates (report generation progress)
2. **Persistent storage**: SQLite for session data, search cache
3. **Plugin system**: Allow custom search providers, report templates
4. **Multi-client support**: Handle multiple Claude instances
5. **Metrics dashboard**: Web UI for monitoring usage and performance

### MCP Protocol Evolution

- **Streaming responses**: For long-running operations
- **Bidirectional communication**: Server-initiated requests
- **Resource sharing**: Share data between servers

## References

- [Model Context Protocol Specification](https://modelcontextprotocol.io/)
- [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk)
- [Claude Code MCP Guide](https://docs.anthropic.com/claude/docs/mcp)
- [Ninja MCP Repository](https://github.com/your-repo/ninja-mcp)

---

**Last Updated**: 2024-12-24
**Version**: 0.2.0
