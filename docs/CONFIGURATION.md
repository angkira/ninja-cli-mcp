# Ninja MCP - Centralized Configuration

## ⚠️ Important: Single Source of Truth

**ALL configuration is centralized in `~/.ninja-mcp.env`**

DO NOT put env variables in:
- ❌ `~/.claude.json` (MCP server definitions)
- ❌ `~/.opencode.json`
- ❌ Individual MCP server configs
- ❌ Shell rc files (`.bashrc`, `.zshrc`)

## ✅ Correct Architecture

```
┌─────────────────────────────────────────┐
│  ~/.ninja-mcp.env                       │
│  (SINGLE SOURCE OF TRUTH)               │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│  NINJA_CODE_BIN=opencode                │
│  NINJA_MODEL=anthropic/claude-sonnet-4  │
│  OPENROUTER_API_KEY=sk-or-...           │
│  PERPLEXITY_API_KEY=pplx-...            │
└─────────────────────────────────────────┘
                    ▲
                    │ (reads from)
        ┌───────────┴───────────┐
        │                       │
┌───────▼─────────┐    ┌────────▼────────┐
│ ninja-coder     │    │ ninja-researcher│
│ (MCP Server)    │    │ (MCP Server)    │
│                 │    │                 │
│ No env vars!    │    │ No env vars!    │
└─────────────────┘    └─────────────────┘
```

## 📁 Configuration File

### `~/.ninja-mcp.env`

```bash
# Ninja MCP Centralized Configuration

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# OPERATOR CONFIGURATION
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NINJA_CODE_BIN=opencode  # or: aider, gemini
NINJA_MODEL=anthropic/claude-sonnet-4-5

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# API KEYS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OPENROUTER_API_KEY=sk-or-...
PERPLEXITY_API_KEY=pplx-...
SERPER_API_KEY=...
GEMINI_API_KEY=...

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEARCH PROVIDER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NINJA_SEARCH_PROVIDER=perplexity  # or: duckduckgo, serper

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DAEMON PORTS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NINJA_CODER_PORT=8100
NINJA_RESEARCHER_PORT=8101
NINJA_SECRETARY_PORT=8102
NINJA_RESOURCES_PORT=8106
NINJA_PROMPTS_PORT=8107
```

## 🚫 Incorrect: Env in .claude.json

**NEVER DO THIS:**

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {
        "NINJA_CODE_BIN": "opencode",  // ❌ WRONG!
        "NINJA_MODEL": "..."            // ❌ WRONG!
      }
    }
  }
}
```

**WHY THIS IS BAD:**
1. ❌ Configuration in multiple places
2. ❌ Hard to change (requires editing JSON)
3. ❌ Overrides centralized config
4. ❌ Not picked up by CLI tools
5. ❌ Requires Claude Code restart

## ✅ Correct: Clean .claude.json

**DO THIS:**

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder"
    },
    "ninja-researcher": {
      "command": "ninja-researcher"
    }
  }
}
```

**WHY THIS IS GOOD:**
1. ✅ Single source of truth
2. ✅ Easy to change with CLI tools
3. ✅ Consistent across all tools
4. ✅ No restarts needed (just reload MCP)

## 🛠️ Managing Configuration

### Using CLI Tools

```bash
# Interactive configuration manager
ninja-config configure

# Quick API key setup
ninja-config auth

# Select operator and model
ninja-config select-model

# View current config
ninja-config show

# Edit specific values
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5
```

### Manual Edit

```bash
# Edit config file directly
nano ~/.ninja-mcp.env

# After changes, reload MCP servers:
# - Claude Code: > Developer: Reload MCP Servers
# - Or restart the application
```

## 🔄 Updating Configuration

When you change `~/.ninja-mcp.env`:

1. **MCP servers will pick up changes automatically** on next call
2. **No need to restart** daemon-mode servers
3. **No need to edit** `.claude.json`

### Example: Switching Operators

```bash
# Method 1: CLI
ninja-config select-model
# Select: OpenCode → anthropic/claude-sonnet-4-5

# Method 2: Direct edit
echo "NINJA_CODE_BIN=opencode" > ~/.ninja-mcp.env
echo "NINJA_MODEL=anthropic/claude-sonnet-4-5" >> ~/.ninja-mcp.env

# Method 3: Using ninja-config set
ninja-config set NINJA_CODE_BIN opencode
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5
```

No `.claude.json` edit needed! ✨

## 🧹 Cleaning Up Old Configs

If you have old configs with env in `.claude.json`:

```bash
# Run cleanup script
./scripts/clean_claude_env.sh

# Or manually with ninja-config
ninja-config setup-claude --force --all
```

## 🔧 How It Works

### MCP Server Startup

1. Server starts (e.g., `ninja-coder`)
2. Loads config from `~/.ninja-mcp.env`
3. Creates `ConfigManager` instance
4. All tools read from this config

### Config Change Detection

```python
# In ninja-coder tools.py
def get_executor() -> ToolExecutor:
    global _executor, _executor_config_hash

    # Compute config hash from ~/.ninja-mcp.env
    current_hash = _get_config_hash()

    # Recreate if changed
    if _executor_config_hash != current_hash:
        _executor = ToolExecutor()
        _executor_config_hash = current_hash

    return _executor
```

### Result

- ✅ Config changes detected automatically
- ✅ No restarts needed
- ✅ Works across all tools
- ✅ Single source of truth

## 📋 Configuration Priority

If multiple sources exist (should not happen):

1. **~/.ninja-mcp.env** (highest priority)
2. Environment variables
3. Default values

But you should **ONLY use ~/.ninja-mcp.env**!

## 🐛 Troubleshooting

### Problem: Config not updating

```bash
# Check if .claude.json has env overrides
cat ~/.claude.json | grep -A 5 ninja-coder

# If env exists, clean it:
./scripts/clean_claude_env.sh

# Restart Claude Code
```

### Problem: Old operator still being used

```bash
# Check current config
ninja-config show

# Check what's actually running
ps aux | grep ninja-coder

# Reload MCP servers in Claude Code:
# > Developer: Reload MCP Servers
```

### Problem: API key not working

```bash
# Verify key is in centralized config
grep OPENROUTER_API_KEY ~/.ninja-mcp.env

# Test with CLI
ninja-config doctor

# Check if .claude.json overrides it (it shouldn't!)
cat ~/.claude.json | grep -i api_key
```

## 📚 Related Documentation

- [Installer Guide](INSTALLER_GUIDE.md) - Setup and installation
- [Model Selector](INTERACTIVE_MODEL_SELECTOR.md) - Choosing models
- [OpenCode Setup](OPENCODE_SETUP.md) - OpenCode integration

## 🤝 Contributing

When adding new configuration options:

1. ✅ Add to `~/.ninja-mcp.env` ONLY
2. ✅ Update `ConfigManager` to read it
3. ✅ Document in this file
4. ✅ Update CLI tools (`ninja-config`)
5. ❌ DO NOT add to `.claude.json` env
6. ❌ DO NOT add to individual servers

## 🎯 Summary

**Remember:**
- **ONE file**: `~/.ninja-mcp.env`
- **ZERO env** in `.claude.json`
- **ALL tools** read from centralized config
- **EASY changes** via CLI or direct edit
- **NO restarts** needed (just reload MCP)

Keep it simple, keep it centralized! 🚀
