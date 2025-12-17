# MCP Best Practices (December 2025)

This document describes the MCP best practices implemented in ninja-cli-mcp based on the latest MCP specification (2025-11-25).

## Table of Contents

- [Architecture](#architecture)
- [Security](#security)
- [Tool Design](#tool-design)
- [Error Handling](#error-handling)
- [Logging](#logging)
- [Testing](#testing)
- [Performance](#performance)
- [Deployment Checklist](#deployment-checklist)

## Architecture

### Transport: Stdio

ninja-cli-mcp uses stdio transport for optimal performance with local Claude Code instances.

**Configuration:**
```json
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "/absolute/path/to/scripts/run_server.sh",
      "transport": "stdio"
    }
  }
}
```

### Async/Await Pattern

All I/O operations use async/await to prevent blocking:

```python
@mcp.tool()
async def ninja_quick_task(params: QuickTaskRequest) -> QuickTaskResult:
    result = await driver.execute_async(...)
    return result
```

### Protocol Version

Using MCP protocol version 2025-11-25 with proper capability negotiation during initialization.

## Security

### 1. Rate Limiting

All tools are rate-limited to prevent abuse:

```python
@rate_limited(max_calls=50, time_window=60)
async def quick_task(self, request: QuickTaskRequest) -> QuickTaskResult:
    # Implementation
    pass
```

**Configuration:**
- quick_task: 50 calls/minute
- execute_plan_*: 20 calls/minute
- run_tests: 30 calls/minute

### 2. Input Validation

All user inputs are validated and sanitized:

```python
# Validate repo root
repo_path = InputValidator.validate_repo_root(request.repo_root)

# Sanitize task description
task = InputValidator.sanitize_string(request.task, max_length=50000)

# Validate paths
for path in context_paths:
    InputValidator.sanitize_path(path, base_dir=repo_path)
```

**Protections:**
- Path traversal prevention
- Shell injection prevention
- XSS/SQL injection detection
- Sensitive directory blocking (/etc, /root, etc.)

### 3. Resource Quotas

Resource monitoring prevents system overload:

```python
@monitored
async def quick_task(...):
    # Automatically monitors:
    # - Memory usage
    # - CPU usage
    # - Task duration
    # - Request rate
    pass
```

Warnings are logged when:
- Memory usage > 80%
- CPU usage > 80%
- Task duration > 300s

### 4. User Consent Model

Following MCP security principles:

1. **Tool Invocation Requires Consent** - Claude must ask user before calling tools
2. **Data Privacy** - Only expose data explicitly requested
3. **Least Privilege** - Tools only access files within `allowed_globs`
4. **Clear UIs** - Users can review operations via logs and metrics

## Tool Design

### 1. Clear Descriptions

All tools have comprehensive descriptions:

```python
Tool(
    name="ninja_quick_task",
    description=(
        "Execute a quick single-pass task using the AI code CLI. "
        "The CLI has full read/write access to files within the specified scope. "
        "Returns only summary and metadata - no raw file contents. "
        "Supports any OpenRouter model (Claude, GPT, Qwen, DeepSeek, etc.)"
    ),
    inputSchema={...}
)
```

### 2. JSON Schema Validation

All parameters use strict JSON Schema:

```python
{
    "type": "object",
    "properties": {
        "task": {
            "type": "string",
            "description": "Task description for the AI code CLI to execute"
        },
        "repo_root": {
            "type": "string",
            "description": "Absolute path to the repository root"
        }
    },
    "required": ["task", "repo_root"]
}
```

### 3. Consistent Naming

- Use lowercase with underscores: `ninja_quick_task`
- Verb + noun pattern: `execute_plan_sequential`, `run_tests`
- Namespacing: `ninja_` prefix for all tools

### 4. Separation of Concerns

- **Read operations**: Return only metadata and summaries
- **Write operations**: Delegated to AI code CLI with scoped access
- **Test operations**: Separate `run_tests` tool

## Error Handling

### 1. Structured Error Responses

All errors return helpful information:

```python
return QuickTaskResult(
    status="error",
    summary=f"Input validation failed: {str(e)}",
    notes="Invalid or potentially unsafe input detected"
)
```

### 2. Error Categories

- **Validation Errors**: Input doesn't meet requirements
- **Permission Errors**: Rate limit or access denied
- **System Errors**: CLI execution failed
- **Timeout Errors**: Operation exceeded time limit

### 3. Contextual Information

Errors include:
- What went wrong
- Why it happened
- How to fix it (if applicable)
- Relevant file paths or parameters

### 4. Graceful Degradation

Operations never crash the server:

```python
try:
    result = await driver.execute_async(...)
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    return QuickTaskResult(
        status="error",
        summary=f"Unexpected error: {str(e)}"
    )
```

## Logging

### 1. Critical Rule: Never Write to Stdout

**Stdout is reserved exclusively for JSON-RPC messages.**

All logging uses stderr:

```python
# ✅ Good
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    stream=sys.stderr  # stderr only!
)

# ❌ Bad - breaks the server!
print("This message corrupts JSON-RPC")
```

### 2. Structured Logging

Use appropriate log levels:

```python
logger.debug("Detailed flow information")
logger.info("Key events")
logger.warning("Issues that don't prevent execution")
logger.error("Failures", exc_info=True)
```

### 3. File Logging

Task-specific logs saved to `.ninja-cli-mcp/logs/`:

```python
task_logger = TaskLogger(repo_root, step_id)
task_logger.info("Starting task")
task_logger.log_subprocess(cmd, exit_code, stdout, stderr)
log_path = task_logger.save()
```

### 4. Log Monitoring

During development:
```bash
# Monitor server logs
tail -f ~/.claude/logs/mcp-ninja-cli-mcp.log

# Monitor task logs
tail -f .ninja-cli-mcp/logs/*.log
```

## Testing

### 1. MCP Inspector

Test locally before deployment:

```bash
# Test the server
npx @modelcontextprotocol/inspector uv run python -m ninja_cli_mcp.server

# Or use the run script
npx @modelcontextprotocol/inspector /path/to/scripts/run_server.sh
```

**Inspector checklist:**
- [ ] Server connects successfully
- [ ] All tools are listed
- [ ] Tool schemas are valid
- [ ] Tools execute without errors
- [ ] Error handling works correctly
- [ ] Rate limiting activates
- [ ] Logs appear in notifications pane

### 2. Unit Tests

```bash
# Run unit tests
uv run pytest tests/test_smoke.py tests/test_cli_adapter.py -v

# Run with coverage
uv run pytest --cov=ninja_cli_mcp --cov-report=html
```

### 3. Integration Tests

```bash
# Run integration tests (requires API key)
RUN_INTEGRATION_TESTS=1 uv run pytest tests/test_integration_openrouter.py -v
```

### 4. Security Tests

Test input validation:

```bash
uv run pytest tests/test_security.py -v
```

## Performance

### 1. Connection Pooling

Reuse HTTP connections for OpenRouter:

```python
# In NinjaDriver
self.client = httpx.AsyncClient(timeout=timeout)
```

### 2. Async Operations

All I/O is non-blocking:

```python
async def execute_plan_parallel(self, request):
    # Execute steps concurrently
    tasks = [execute_step(step) for step in request.steps]
    results = await asyncio.gather(*tasks)
```

### 3. Caching

Cache frequently accessed data:

```python
# Cache OpenRouter pricing
@lru_cache(maxsize=1)
def fetch_openrouter_pricing() -> dict[str, PricingInfo]:
    # Fetches once, then cached
    pass
```

### 4. Resource Limits

Prevent resource exhaustion:

```python
# Limit concurrent tasks
semaphore = asyncio.Semaphore(request.fanout)

# Set timeouts
result = await asyncio.wait_for(
    driver.execute_async(...),
    timeout=timeout_sec
)
```

## Deployment Checklist

### Pre-Deployment

- [ ] All tests pass
- [ ] MCP Inspector verification complete
- [ ] Logs go to stderr only (no `print()` statements)
- [ ] Rate limiting configured
- [ ] Input validation implemented
- [ ] Error handling comprehensive
- [ ] Documentation updated

### Configuration

- [ ] Use absolute paths in `.claude.json`
- [ ] API key set in environment
- [ ] Model configured correctly
- [ ] Timeout values appropriate
- [ ] Resource limits set

### Security

- [ ] Input validation enabled
- [ ] Rate limiting active
- [ ] Sensitive directories blocked
- [ ] Path traversal prevention
- [ ] Resource monitoring enabled

### Monitoring

- [ ] Logging configured
- [ ] Metrics collection enabled
- [ ] Error tracking setup
- [ ] Performance monitoring active

### Documentation

- [ ] README.md updated
- [ ] Tool descriptions accurate
- [ ] Configuration examples provided
- [ ] Troubleshooting guide available

## Implementation Status

### ✅ Implemented

- [x] Stdio transport with proper logging
- [x] Async/await for all operations
- [x] JSON Schema for all tools
- [x] Rate limiting decorators
- [x] Input validation and sanitization
- [x] Resource monitoring
- [x] Comprehensive error handling
- [x] Structured logging to stderr
- [x] Task-specific log files
- [x] Metrics tracking
- [x] CLI adapter pattern for multiple AI assistants
- [x] Integration tests
- [x] Smoke tests
- [x] Security tests

### 🔄 Recommended Improvements

- [ ] Migrate to FastMCP for simpler implementation (optional)
- [ ] Add OpenTelemetry integration for distributed tracing
- [ ] Implement caching for repeated operations
- [ ] Add webhook notifications for long-running tasks
- [ ] Create dashboard for metrics visualization

### 📚 Documentation Status

- [x] MCP best practices documented
- [x] Security implementation documented
- [x] Testing guide created
- [x] Linux fixes documented
- [x] Deployment checklist created
- [ ] Video walkthrough (pending)
- [ ] Architecture diagrams (pending)

## References

- [MCP Specification 2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25)
- [MCP Build Server Documentation](https://modelcontextprotocol.io/docs/develop/build-server)
- [MCP Inspector Tool](https://modelcontextprotocol.io/docs/tools/inspector)
- [Security Considerations](https://modelcontextprotocol.io/specification/2025-11-25#security)

## Getting Help

- Issues: https://github.com/angkira/ninja-cli-mcp/issues
- MCP Community: https://github.com/modelcontextprotocol
- Claude Code Docs: https://code.claude.com/docs
