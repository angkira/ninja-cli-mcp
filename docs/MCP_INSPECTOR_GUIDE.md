# MCP Inspector Testing Guide

The MCP Inspector is an essential tool for testing and debugging MCP servers locally before deploying them to production. This guide shows you how to use it with ninja-cli-mcp.

## What is MCP Inspector?

MCP Inspector is a local testing tool that:
- Connects to your MCP server via stdio/SSE/HTTP
- Lists available tools and resources
- Allows you to test tool invocations
- Shows server logs and debug information
- Validates your server implementation

Think of it as a local development environment for your MCP server, similar to Postman for APIs.

## Installation

No installation needed - run via `npx`:

```bash
npx @modelcontextprotocol/inspector
```

## Testing ninja-cli-mcp

### Method 1: Direct Python Module

```bash
# From the project root
cd /home/angkira/Project/software/ninja-cli-mcp

# Set up environment
source ~/.ninja-cli-mcp.env

# Run inspector
npx @modelcontextprotocol/inspector uv run python -m ninja_cli_mcp.server
```

### Method 2: Using Run Script

```bash
npx @modelcontextprotocol/inspector /home/angkira/Project/software/ninja-cli-mcp/scripts/run_server.sh
```

### Method 3: Test Without API Key

If you don't have an API key yet or want to test the connection:

```bash
# Set a dummy API key
export OPENROUTER_API_KEY="sk-dummy-key-for-testing"
export NINJA_CODE_BIN="echo"

# Run inspector
npx @modelcontextprotocol/inspector uv run python -m ninja_cli_mcp.server
```

This will let you test tool schemas and invocation without actually executing tasks.

## Inspector UI Overview

When you run the inspector, a web UI opens at `http://localhost:5173`:

```
┌─────────────────────────────────────────────────────────┐
│  MCP Inspector                                          │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [Connection Status: Connected ✓]                      │
│                                                         │
│  ┌─ Tools ───────────────────────┐                     │
│  │ • ninja_quick_task            │                     │
│  │ • execute_plan_sequential     │                     │
│  │ • execute_plan_parallel       │                     │
│  │ • run_tests                   │                     │
│  │ • apply_patch                 │                     │
│  └───────────────────────────────┘                     │
│                                                         │
│  ┌─ Notifications ───────────────┐                     │
│  │ [INFO] Server started         │                     │
│  │ [DEBUG] Tool registered: ...  │                     │
│  └───────────────────────────────┘                     │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

## Testing Checklist

### 1. Connection Test

**Expected:** Server connects successfully

**Verify:**
- [ ] Connection status shows "Connected ✓"
- [ ] No errors in the Notifications pane
- [ ] Server logs appear (e.g., "Server started")

**Troubleshooting:**
```bash
# Check logs
tail -f ~/.claude/logs/mcp*.log

# Verify environment
echo $OPENROUTER_API_KEY
echo $NINJA_MODEL
echo $NINJA_CODE_BIN
```

### 2. Tool Discovery

**Expected:** All 5 tools are listed

**Verify:**
- [ ] `ninja_quick_task`
- [ ] `execute_plan_sequential`
- [ ] `execute_plan_parallel`
- [ ] `run_tests`
- [ ] `apply_patch`

**Troubleshooting:**
- Tools missing? Check server.py TOOLS list
- Tool descriptions unclear? Update descriptions in server.py

### 3. Tool Schema Validation

Click each tool to view its schema.

**For ninja_quick_task:**

**Expected Schema:**
```json
{
  "type": "object",
  "properties": {
    "task": {
      "type": "string",
      "description": "Task description..."
    },
    "repo_root": {
      "type": "string",
      "description": "Absolute path to the repository root"
    },
    "context_paths": {
      "type": "array",
      "items": {"type": "string"}
    },
    "allowed_globs": {
      "type": "array",
      "items": {"type": "string"}
    },
    "deny_globs": {
      "type": "array",
      "items": {"type": "string"}
    }
  },
  "required": ["task", "repo_root"]
}
```

**Verify:**
- [ ] All properties are listed
- [ ] Types are correct
- [ ] Descriptions are helpful
- [ ] Required fields are marked

### 4. Tool Invocation Test

Test `ninja_quick_task` with minimal input:

**Input:**
```json
{
  "task": "Echo 'hello world'",
  "repo_root": "/tmp"
}
```

**Expected Response:**
```json
{
  "status": "ok",
  "summary": "Task completed successfully",
  "notes": "...",
  "logs_ref": "/tmp/.ninja-cli-mcp/logs/...",
  "suspected_touched_paths": []
}
```

**Or (if validation fails):**
```json
{
  "status": "error",
  "summary": "Repository root does not exist: /tmp",
  "notes": "Repository root validation failed"
}
```

**Verify:**
- [ ] Tool responds (doesn't hang)
- [ ] Response has correct structure
- [ ] Status is "ok" or "error" (not "unknown")
- [ ] Error messages are helpful
- [ ] Logs appear in Notifications pane

### 5. Error Handling Test

Test with invalid input:

**Test 1: Missing required field**
```json
{
  "task": "Test"
}
```

**Expected:** Validation error about missing `repo_root`

**Test 2: Invalid repo_root**
```json
{
  "task": "Test",
  "repo_root": "/nonexistent/path/12345"
}
```

**Expected:**
```json
{
  "status": "error",
  "summary": "Repository root does not exist: /nonexistent/path/12345",
  "notes": "Repository root validation failed"
}
```

**Test 3: Dangerous path traversal**
```json
{
  "task": "Test",
  "repo_root": "/tmp",
  "context_paths": ["../../etc/passwd"]
}
```

**Expected:** Input validation error

**Verify:**
- [ ] All error cases are handled gracefully
- [ ] Error messages are informative
- [ ] Server doesn't crash
- [ ] Logs show the error details

### 6. Rate Limiting Test

Rapidly invoke the same tool 60+ times.

**Expected:**
- First 50 calls succeed
- Subsequent calls return:
```json
{
  "status": "error",
  "summary": "Rate limit exceeded: maximum 50 calls per 60s",
  "notes": "Too many requests - please slow down"
}
```

**Verify:**
- [ ] Rate limiting activates after threshold
- [ ] Error message is clear
- [ ] Rate limit resets after time window

### 7. Logging Test

Monitor the Notifications pane during tool invocation.

**Expected logs:**
```
[INFO] ninja_cli_mcp.tools: Executing quick task in /tmp
[DEBUG] ninja_cli_mcp.ninja_driver: Built command: ['claude', '--print', ...]
[INFO] ninja_cli_mcp.tools: Task completed successfully
```

**Verify:**
- [ ] Logs appear in real-time
- [ ] Log levels are appropriate (INFO for events, DEBUG for details, ERROR for failures)
- [ ] No logs pollute stdout (would break JSON-RPC)
- [ ] Task-specific logs are saved to files

### 8. Performance Test

Test with a realistic workload:

```json
{
  "task": "List all Python files",
  "repo_root": "/home/angkira/Project/software/ninja-cli-mcp",
  "allowed_globs": ["**/*.py"]
}
```

**Verify:**
- [ ] Response time < 30s (for quick tasks)
- [ ] Memory usage stays reasonable
- [ ] No memory leaks after multiple invocations
- [ ] Server remains responsive

**Monitor resources:**
```bash
# In another terminal
watch -n 1 'ps aux | grep python | grep ninja'
```

## Common Issues and Solutions

### Issue: "Connection refused"

**Cause:** Server failed to start

**Solution:**
```bash
# Check for Python errors
uv run python -m ninja_cli_mcp.server

# Verify dependencies
uv sync

# Check environment
source ~/.ninja-cli-mcp.env
env | grep NINJA
```

### Issue: "Tools not appearing"

**Cause:** Server started but tools not registered

**Solution:**
```bash
# Check server.py TOOLS list
grep -A 5 "TOOLS:" src/ninja_cli_mcp/server.py

# Verify tool handler registration
grep "request_tool_call" src/ninja_cli_mcp/server.py
```

### Issue: "Invalid JSON response"

**Cause:** stdout pollution (print() statements)

**Solution:**
```bash
# Search for print() in server code
grep -r "print(" src/ninja_cli_mcp/*.py | grep -v test | grep -v cli

# Verify logging configuration
grep "StreamHandler(sys.stderr)" src/ninja_cli_mcp/logging_utils.py
```

### Issue: "Tool execution hangs"

**Cause:** Blocking operation or missing timeout

**Solution:**
```python
# All operations should use async/await
async def tool_handler(...):
    result = await driver.execute_async(...)  # ✓
    # NOT: result = driver.execute_sync(...)  # ✗

# Add timeouts
result = await asyncio.wait_for(
    driver.execute_async(...),
    timeout=300
)
```

## Advanced Testing

### Test with Multiple Concurrent Calls

Use the browser's network tab to send multiple requests simultaneously.

**Expected:**
- Server handles concurrent requests
- No race conditions
- Rate limiting works correctly

### Test Edge Cases

1. **Very long task descriptions** (50KB+)
2. **Many context paths** (100+)
3. **Complex glob patterns**
4. **Unicode in task descriptions**
5. **Nested directory structures**

### Test Security

1. **Path traversal:** `../../etc/passwd`
2. **Shell injection:** `$(whoami)`, `; rm -rf /`
3. **Large inputs:** >1MB task descriptions
4. **Rapid requests:** >100 calls/second

## Inspector Keyboard Shortcuts

- `Cmd/Ctrl + K` - Clear logs
- `Cmd/Ctrl + R` - Reconnect to server
- `Cmd/Ctrl + /` - Toggle dark mode

## Comparing with Production

After testing with Inspector, compare with actual Claude Code usage:

```bash
# 1. Test with Inspector
npx @modelcontextprotocol/inspector uv run python -m ninja_cli_mcp.server

# 2. Test with Claude Code
claude
```

In Claude:
```
/mcp
Use ninja_quick_task to echo hello world in /tmp
```

**Verify:**
- Same tools appear
- Same behavior
- Same error messages
- Same performance

## Automated Inspector Tests

Create a test script:

```bash
#!/bin/bash
# test_mcp_inspector.sh

set -e

echo "Starting MCP Inspector test..."

# Start inspector in background
npx @modelcontextprotocol/inspector uv run python -m ninja_cli_mcp.server &
INSPECTOR_PID=$!

# Wait for startup
sleep 5

# Test API endpoint
curl http://localhost:5173/health || {
    echo "Inspector not responding"
    kill $INSPECTOR_PID
    exit 1
}

echo "✓ Inspector responding"

# Cleanup
kill $INSPECTOR_PID

echo "✓ All tests passed"
```

## Next Steps

After successful Inspector testing:

1. **Register with Claude Code**
   ```bash
   claude mcp add --scope user --transport stdio ninja-cli-mcp -- \
     /path/to/scripts/run_server.sh
   ```

2. **Test in Claude Code**
   ```bash
   claude
   /mcp
   ```

3. **Monitor production logs**
   ```bash
   tail -f ~/.claude/logs/mcp-ninja-cli-mcp.log
   ```

4. **Collect metrics**
   ```bash
   uv run python -m ninja_cli_mcp.cli metrics-summary --repo-root .
   ```

## Resources

- [Official MCP Inspector Docs](https://modelcontextprotocol.io/docs/tools/inspector)
- [MCP Debugging Guide](https://modelcontextprotocol.io/docs/develop/debugging)
- [Example Servers](https://github.com/modelcontextprotocol/servers)
