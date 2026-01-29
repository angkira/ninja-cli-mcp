# 🥷 Ninja MCP - Quick Start Guide

## Installation

### New Installation
```bash
# One-line install (interactive)
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash

# Non-interactive (for CI/automation)
OPENROUTER_API_KEY='sk-or-v1-xxx' curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash -s -- --auto
```

### Update Existing Installation
```bash
# Automatically migrates ALL old configs
./update.sh

# Or remote:
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/update.sh | bash
```

**Migration is automatic!** Your API keys, models, and settings are preserved from:
- Old config files (`~/.config/ninja/*`, etc.)
- Shell RC files (`.bashrc`, `.zshrc`)
- Environment variables
- Old variable names automatically converted

---

## Configuration

### Interactive Setup (Recommended)
```bash
# Select operator (OpenRouter/Anthropic) and model
ninja-config select-model

# Set API key
ninja-config api-key openrouter

# Diagnose issues
ninja-config doctor
ninja-config doctor --fix
```

### Manual Configuration
```bash
# View all settings
ninja-config list

# Set individual values
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5
ninja-config set NINJA_SEARCH_PROVIDER serper
ninja-config model coder anthropic/claude-opus-4-5

# Get specific value
ninja-config get NINJA_MODEL
```

### Config File Location
All settings in one place:
```bash
~/.ninja-mcp.env
```

---

## Daemon Management

```bash
# Start all daemons
ninja-daemon start

# Check status
ninja-daemon status

# Restart (after config changes)
ninja-daemon restart

# View logs
ninja-daemon logs coder
ninja-daemon logs researcher --tail 50

# Stop all
ninja-daemon stop
```

---

## MCP Server Registration

### Claude Code (Automatic)
```bash
# Daemons register automatically on start
ninja-daemon start

# Verify registration
claude mcp list

# Manual re-registration if needed
claude mcp remove ninja-coder -s user
claude mcp add --scope user --transport stdio ninja-coder -- ninja-daemon connect coder
```

### VS Code / Cursor / Windsurf
MCP servers auto-configured during installation. Restart your editor if needed.

### Zed
Auto-configured in `~/.config/zed/settings.json`. Restart Zed.

---

## Using Ninja

### From Claude Code
```python
# Code writing
"Create a REST API with FastAPI that validates emails"

# Research
"Research the latest AI developments in 2026"

# Codebase analysis
"Analyze the authentication system in this project"
```

### From Python
```python
from ninja_coder import execute_simple_task

result = execute_simple_task(
    repo_root="/path/to/project",
    task="Add user authentication with JWT",
    context_paths=["src/api/"],
    allowed_globs=["src/**/*.py"]
)

print(result.summary)
```

### Via MCP Protocol
```json
{
  "method": "tools/call",
  "params": {
    "name": "coder_simple_task",
    "arguments": {
      "repo_root": "/path/to/project",
      "task": "Create a User class with email validation"
    }
  }
}
```

---

## Troubleshooting

### Daemons Not Starting
```bash
# Check Python version (need 3.11+)
python3 --version

# Check if ports are free
ninja-config doctor

# View detailed logs
ninja-daemon logs coder --tail 100
```

### Claude Code Not Seeing Servers
```bash
# Re-register MCP servers
ninja-daemon stop
ninja-daemon start

# Check registration
claude mcp list

# Check if daemon is reachable
curl http://localhost:8100/health
```

### API Keys Not Working
```bash
# Verify keys are set
ninja-config list | grep API_KEY

# Test with diagnostic
ninja-config doctor

# Check config file
cat ~/.ninja-mcp.env | grep API_KEY
```

### Config Migration Issues
```bash
# Check backups
ls -lh ~/.ninja-mcp-backups/

# Restore from backup
cp ~/.ninja-mcp-backups/backup_20260129_*.env ~/.ninja-mcp.env
ninja-daemon restart

# See full migration guide
cat MIGRATION.md
```

---

## Common Tasks

### Change Model
```bash
# Interactive
ninja-config select-model

# Direct
ninja-config set NINJA_MODEL anthropic/claude-opus-4-5
```

### Change API Key
```bash
ninja-config api-key openrouter
# Enter new key when prompted
```

### Change Search Provider
```bash
# DuckDuckGo (free, no key needed)
ninja-config set NINJA_SEARCH_PROVIDER duckduckgo

# Serper (requires API key)
ninja-config set NINJA_SEARCH_PROVIDER serper
ninja-config api-key serper

# Perplexity (requires API key)
ninja-config set NINJA_SEARCH_PROVIDER perplexity
ninja-config api-key perplexity
```

### Switch Code CLI
```bash
# Use OpenCode
ninja-config set NINJA_CODE_BIN opencode

# Use Aider
ninja-config set NINJA_CODE_BIN aider

# Restart daemons
ninja-daemon restart
```

### View Logs
```bash
# All logs
ninja-daemon logs coder

# Last 50 lines
ninja-daemon logs coder --tail 50

# Follow in real-time
ninja-daemon logs coder --follow

# All modules
for module in coder researcher secretary resources prompts; do
    echo "=== $module ==="
    ninja-daemon logs $module --tail 10
done
```

---

## Files & Directories

```
~/.ninja-mcp.env              # Main config (centralized)
~/.ninja-mcp-backups/         # Automatic backups
~/.cache/ninja-mcp/           # Logs and cache
~/.local/bin/ninja-*          # Installed binaries
~/.config/claude/             # Claude Code MCP config
```

---

## Next Steps

1. **Configure:** `ninja-config select-model`
2. **Verify:** `ninja-config doctor`
3. **Start coding:** Open Claude Code and try:
   - "Create a Python function that validates emails"
   - "Research the best practices for REST API design"
   - "Analyze the database schema in this project"

---

## Documentation

- [Full README](README.md) - Overview and features
- [Migration Guide](MIGRATION.md) - Upgrading from old versions
- [Coder Module](docs/CODER.md) - Code writing agent
- [Researcher Module](docs/RESEARCHER.md) - Web intelligence
- [Architecture](ARCHITECTURE.md) - System design

---

## Support

**Issues:** https://github.com/angkira/ninja-cli-mcp/issues

Include when reporting:
```bash
ninja-config doctor
ninja-daemon status
cat ~/.ninja-mcp.env
```
