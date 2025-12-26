# Migration Guide: v0.1 → v0.2

This guide helps you migrate from the monolithic `ninja-cli-mcp` (v0.1) to the new multi-module architecture (v0.2).

## What Changed

### Module Structure

**Before (v0.1):**
```
src/ninja_cli_mcp/
├── server.py
├── tools.py
├── models.py
├── ninja_driver.py
├── logging_utils.py
├── metrics.py
├── path_utils.py
└── security.py
```

**After (v0.2):**
```
src/
├── ninja_common/          # Shared infrastructure
│   ├── logging_utils.py
│   ├── metrics.py
│   ├── path_utils.py
│   ├── security.py
│   └── daemon.py
├── ninja_coder/           # Code execution module
│   ├── server.py
│   ├── tools.py
│   ├── models.py
│   └── driver.py
├── ninja_researcher/      # Research module (new)
│   └── server.py
└── ninja_secretary/       # Documentation module (new)
    └── server.py
```

### Tool Names

Tool names are now prefixed with the module name:

| Old Name (v0.1) | New Name (v0.2) | Module |
|-----------------|-----------------|--------|
| `ninja_quick_task` | `coder_quick_task` | Coder |
| `execute_plan_sequential` | `coder_execute_plan_sequential` | Coder |
| `execute_plan_parallel` | `coder_execute_plan_parallel` | Coder |
| `run_tests` | `coder_run_tests` | Coder |
| `apply_patch` | `coder_apply_patch` | Coder |

### Environment Variables

**Before (v0.1):**
```bash
export OPENROUTER_API_KEY='...'
export NINJA_MODEL='anthropic/claude-sonnet-4'
export NINJA_CODE_BIN='aider'
```

**After (v0.2):**
```bash
# Common
export OPENROUTER_API_KEY='...'

# Coder module
export NINJA_CODER_MODEL='anthropic/claude-haiku-4.5-20250929'
export NINJA_CODE_BIN='aider'
export NINJA_CODER_TIMEOUT=600

# Researcher module
export NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'
export NINJA_TAVILY_API_KEY='...'

# Secretary module
export NINJA_SECRETARY_MODEL='anthropic/claude-haiku-4.5-20250929'
```

### Configuration Files

**Before (v0.1):**
- `~/.ninja-cli-mcp.env`

**After (v0.2):**
- `~/.ninja-mcp.env` (unified config for all modules)

### Cache Directories

**Before (v0.1):**
- `~/.cache/ninja-cli-mcp/<repo>/`

**After (v0.2):**
- `~/.cache/ninja-mcp/<repo>/` (unified cache)

## Migration Steps

### Step 1: Backup Your Configuration

```bash
# Backup old config
cp ~/.ninja-cli-mcp.env ~/.ninja-cli-mcp.env.backup

# Backup old cache (optional)
cp -r ~/.cache/ninja-cli-mcp ~/.cache/ninja-cli-mcp.backup
```

### Step 2: Update the Repository

```bash
cd /path/to/ninja-mcp
git pull origin main
```

### Step 3: Reinstall Dependencies

```bash
# Install with selected modules
uv sync --extra coder

# Or install all modules
uv sync --all-extras
```

### Step 4: Run the New Installer

```bash
./scripts/install_interactive.sh
```

The installer will:
- Detect your existing configuration
- Offer to migrate settings
- Set up the new multi-module structure
- Update IDE integrations

### Step 5: Update IDE Configurations

#### Claude Code

**Before:**
```json
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "/path/to/scripts/run_server.sh"
    }
  }
}
```

**After:**
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-daemon",
      "args": ["connect", "coder"]
    },
    "ninja-researcher": {
      "command": "ninja-daemon",
      "args": ["connect", "researcher"]
    },
    "ninja-secretary": {
      "command": "ninja-daemon",
      "args": ["connect", "secretary"]
    }
  }
}
```

Or without daemon:
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    }
  }
}
```

#### VS Code

Update `~/.config/Code/User/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    }
  }
}
```

### Step 6: Update Your Scripts

If you have scripts that call MCP tools, update the tool names:

**Before:**
```python
result = await client.call_tool("ninja_quick_task", {
    "task": "Add hello function",
    "repo_root": "/path/to/repo"
})
```

**After:**
```python
result = await client.call_tool("coder_quick_task", {
    "task": "Add hello function",
    "repo_root": "/path/to/repo"
})
```

### Step 7: Test the Migration

```bash
# Test coder module
ninja-coder

# Or with daemon
ninja-daemon start coder
ninja-daemon status coder

# Test in Claude Code
claude
# Then use /mcp to see available tools
```

## Backward Compatibility

### Legacy Support

The old `ninja-cli-mcp` module is still available for backward compatibility:

```bash
# Install legacy support
uv sync --extra legacy

# Run old server
python -m ninja_cli_mcp.server
```

**Note:** Legacy support will be removed in v0.3.0 (estimated Q2 2025).

### Gradual Migration

You can run both old and new modules simultaneously:

```json
{
  "mcpServers": {
    "ninja-cli-mcp": {
      "command": "python",
      "args": ["-m", "ninja_cli_mcp.server"]
    },
    "ninja-coder": {
      "command": "python",
      "args": ["-m", "ninja_coder.server"]
    }
  }
}
```

This allows you to:
1. Test the new module
2. Gradually update your workflows
3. Fall back to the old module if needed

## Troubleshooting

### "Module not found" errors

```bash
# Reinstall dependencies
uv sync --all-extras

# Verify installation
python -c "import ninja_common; import ninja_coder"
```

### Tool names not recognized

Make sure you're using the new tool names with the `coder_` prefix:
- `ninja_quick_task` → `coder_quick_task`
- `execute_plan_sequential` → `coder_execute_plan_sequential`

### Configuration not loaded

```bash
# Source the new config file
source ~/.ninja-mcp.env

# Verify
echo $NINJA_CODER_MODEL
```

### Daemon not starting

```bash
# Check daemon status
ninja-daemon status coder

# View daemon logs
tail -f ~/.cache/ninja-mcp/logs/coder.log

# Restart daemon
ninja-daemon restart coder
```

## Rollback Procedure

If you need to rollback to v0.1:

```bash
# 1. Checkout v0.1
git checkout v0.1.0

# 2. Reinstall dependencies
uv sync

# 3. Restore old config
cp ~/.ninja-cli-mcp.env.backup ~/.ninja-cli-mcp.env
source ~/.ninja-cli-mcp.env

# 4. Update IDE configs to use old tool names
# (Restore your backed-up IDE configs)

# 5. Run old server
python -m ninja_cli_mcp.server
```

## Getting Help

If you encounter issues during migration:

1. Check the [Troubleshooting](#troubleshooting) section above
2. Review the [ARCHITECTURE.md](ARCHITECTURE.md) for the new structure
3. Open an issue: https://github.com/angkira/ninja-mcp/issues
4. Join discussions: https://github.com/angkira/ninja-mcp/discussions

## Timeline

- **v0.2.0** (Current): Multi-module architecture, Coder module complete
- **v0.2.1** (Q1 2025): Researcher module implementation
- **v0.2.2** (Q1 2025): Secretary module implementation
- **v0.3.0** (Q2 2025): Remove legacy `ninja-cli-mcp` support

## Benefits of Migrating

1. **Modularity**: Install only the modules you need
2. **Separation of Concerns**: Each module has a clear purpose
3. **Better Performance**: Modules can run as independent daemons
4. **Future Features**: New modules (Researcher, Secretary) only available in v0.2+
5. **Improved Security**: Better isolation between modules
6. **Easier Maintenance**: Cleaner codebase structure

## Questions?

See the [FAQ](docs/FAQ.md) or open a discussion on GitHub.
