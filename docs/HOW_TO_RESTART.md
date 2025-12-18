# How to Restart ninja-cli-mcp MCP Server

## Quick Answer

**No reinstallation needed!** The MCP server runs directly from your source directory:
```
/home/angkira/Project/software/ninja-cli-mcp
```

**To restart the MCP server:**

### Option 1: Kill Old Processes (RECOMMENDED)
```bash
# Kill all old MCP server processes
pkill -f "ninja_cli_mcp.server"

# Verify they're stopped
ps aux | grep ninja_cli_mcp.server | grep -v grep

# Restart will happen automatically when you use GitHub Copilot CLI next time
```

### Option 2: Restart GitHub Copilot CLI
Simply close and reopen your terminal or IDE. GitHub Copilot CLI will automatically start the MCP server when needed.

### Option 3: Manual Restart
```bash
# Kill old processes
pkill -f "ninja_cli_mcp.server"

# Start manually for testing
cd /home/angkira/Project/software/ninja-cli-mcp
bash scripts/run_server.sh
```

## How It Works

### Installation Type: **Development Mode** (No System Installation)

Your MCP server is **NOT** installed to system directories like:
- ❌ `/opt/`
- ❌ `/usr/bin/`
- ❌ `/usr/local/`

Instead, it runs directly from:
- ✅ `/home/angkira/Project/software/ninja-cli-mcp/`

### Configuration Location

GitHub Copilot CLI reads the MCP configuration from:
```
~/.copilot/mcp-config.json
```

Which points to:
```json
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "/home/angkira/Project/software/ninja-cli-mcp/scripts/run_server.sh",
      ...
    }
  }
}
```

So when Copilot CLI needs the MCP server, it runs the script from your **source directory**.

## Current Running Processes

You have several old MCP server processes running (started yesterday):
```
PID      Started  Command
3087385  Dec17    uv run python -m ninja_cli_mcp.server
3087409  Dec17    python3 -m ninja_cli_mcp.server
3087432  Dec17    uv run python -m ninja_cli_mcp.server
3087438  Dec17    python3 -m ninja_cli_mcp.server
...
```

These are the **OLD** processes (before fixes). They need to be killed.

## Step-by-Step Restart Process

### Step 1: Kill Old Processes
```bash
pkill -f "ninja_cli_mcp.server"
```

### Step 2: Verify Configuration
```bash
# Check environment is correct
cat ~/.ninja-cli-mcp.env

# Should show:
# export OPENROUTER_API_KEY='sk-or-v1-...'
# export NINJA_MODEL='qwen/qwen3-coder-30b-a3b-instruct'
# export NINJA_CODE_BIN='aider'
```

### Step 3: Test Server Startup
```bash
cd /home/angkira/Project/software/ninja-cli-mcp

# Quick test (5 seconds)
timeout 5 bash scripts/run_server.sh &
sleep 2
ps aux | grep ninja_cli_mcp.server | grep -v grep
pkill -f ninja_cli_mcp.server
```

### Step 4: Use GitHub Copilot CLI
```bash
# In your project directory
gh copilot

# The MCP server will start automatically
# You can now use ninja_quick_task and other tools
```

## Verification Commands

### Check if old processes are still running
```bash
ps aux | grep ninja_cli_mcp.server | grep -v grep
```

Expected: **No output** (all killed)

### Check configuration is loaded
```bash
source ~/.ninja-cli-mcp.env
echo "NINJA_CODE_BIN: $NINJA_CODE_BIN"
echo "NINJA_MODEL: $NINJA_MODEL"
```

Expected:
```
NINJA_CODE_BIN: aider
NINJA_MODEL: qwen/qwen3-coder-30b-a3b-instruct
```

### Check Aider is available
```bash
cd /home/angkira/Project/software/ninja-cli-mcp
uv run aider --version
```

Expected: `aider 0.86.1`

### Test MCP server starts correctly
```bash
cd /home/angkira/Project/software/ninja-cli-mcp
timeout 3 bash scripts/run_server.sh 2>&1 | head -5
```

Expected:
```
2025-12-18 ... [INFO] Starting ninja-cli-mcp server
2025-12-18 ... [INFO] Server ready, waiting for requests
```

## What Gets Updated When You Edit Code

Since the server runs from source, when you edit files in:
```
/home/angkira/Project/software/ninja-cli-mcp/
```

The changes take effect **immediately on next server start**. No reinstallation needed.

### Files That Affect Runtime:
- `src/ninja_cli_mcp/*.py` - Python source code
- `scripts/run_server.sh` - Server startup script
- `~/.ninja-cli-mcp.env` - Environment configuration
- `pyproject.toml` - Dependencies (requires `uv sync` after changes)

### Files That DON'T Require Restart:
- Documentation files (`docs/*.md`)
- Test files (`tests/*.py`)
- Installation scripts (`scripts/install_*.sh`)

## Complete Restart Script

Save this as `restart_mcp.sh`:

```bash
#!/usr/bin/env bash
# Restart ninja-cli-mcp MCP server

set -euo pipefail

echo "🔄 Restarting ninja-cli-mcp MCP server..."
echo ""

# Kill old processes
echo "1. Killing old MCP server processes..."
pkill -f "ninja_cli_mcp.server" 2>/dev/null || true
sleep 1

# Check they're gone
if ps aux | grep -E "ninja_cli_mcp.server" | grep -v grep > /dev/null 2>&1; then
    echo "⚠️  Warning: Some processes still running. Force killing..."
    pkill -9 -f "ninja_cli_mcp.server" || true
    sleep 1
fi

echo "✅ Old processes killed"
echo ""

# Verify configuration
echo "2. Verifying configuration..."
if [[ -f ~/.ninja-cli-mcp.env ]]; then
    source ~/.ninja-cli-mcp.env
    echo "✅ Configuration loaded"
    echo "   NINJA_CODE_BIN: $NINJA_CODE_BIN"
    echo "   NINJA_MODEL: ${NINJA_MODEL:0:30}..."
else
    echo "❌ Configuration file not found: ~/.ninja-cli-mcp.env"
    exit 1
fi
echo ""

# Test server startup
echo "3. Testing server startup..."
cd /home/angkira/Project/software/ninja-cli-mcp
if timeout 3 bash scripts/run_server.sh > /tmp/mcp_test.log 2>&1 &
    TEST_PID=$!
    sleep 2
    if ps -p $TEST_PID > /dev/null 2>&1; then
        echo "✅ Server starts successfully"
        kill $TEST_PID 2>/dev/null || true
    else
        echo "❌ Server failed to start"
        cat /tmp/mcp_test.log
        exit 1
    fi
else
    echo "⚠️  Server test inconclusive (may need more time)"
fi
echo ""

echo "✅ Restart complete!"
echo ""
echo "Next steps:"
echo "  1. Close and reopen your terminal/IDE"
echo "  2. Use: gh copilot"
echo "  3. Try: 'Use ninja_quick_task to...'"
echo ""
```

Make it executable:
```bash
chmod +x restart_mcp.sh
```

## Troubleshooting

### Issue: Processes won't die
```bash
# Force kill
pkill -9 -f "ninja_cli_mcp.server"
```

### Issue: Server doesn't start
```bash
# Check logs
cd /home/angkira/Project/software/ninja-cli-mcp
bash scripts/run_server.sh 2>&1 | tee server.log
```

### Issue: Changes don't take effect
```bash
# Make sure you killed old processes
ps aux | grep ninja_cli_mcp.server

# Restart GitHub Copilot CLI
# Close terminal/IDE and reopen
```

### Issue: "Aider not found"
```bash
cd /home/angkira/Project/software/ninja-cli-mcp
uv sync --extra aider
```

## Summary

**To restart ninja-cli-mcp:**
1. ✅ Kill old processes: `pkill -f "ninja_cli_mcp.server"`
2. ✅ Restart GitHub Copilot CLI (close/reopen terminal)
3. ✅ Or use the restart script above

**No reinstallation needed** - the server runs from source at:
`/home/angkira/Project/software/ninja-cli-mcp/`

**Changes take effect immediately** on next server start.
