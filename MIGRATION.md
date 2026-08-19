# 🔄 Ninja MCP - Configuration Migration Guide

## Overview

The `ninja-mcp update` command automatically migrates your existing configuration from any old format to the new centralized `~/.ninja-mcp.env` format.

**All your settings are preserved**: API keys, models, providers, ports, and custom settings.

---

## What Gets Migrated

### ✅ API Keys
- `OPENROUTER_API_KEY`
- `SERPER_API_KEY`
- `PERPLEXITY_API_KEY`
- `ANTHROPIC_API_KEY`
- `OPENAI_API_KEY` (migrated to OPENROUTER_API_KEY if it's an OpenRouter key)

### ✅ Model Settings
- `NINJA_MODEL` (global model)
- `NINJA_CODER_MODEL`
- `NINJA_RESEARCHER_MODEL`
- `NINJA_SECRETARY_MODEL`
- `NINJA_RESOURCES_MODEL`
- `NINJA_PROMPTS_MODEL`

### ✅ Provider Settings
- `NINJA_SEARCH_PROVIDER`
- `NINJA_CODE_BIN` (aider/opencode path)
- `OPENAI_BASE_URL`

### ✅ Daemon Configuration
- `NINJA_CODER_PORT`
- `NINJA_RESEARCHER_PORT`
- `NINJA_SECRETARY_PORT`
- `NINJA_RESOURCES_PORT`
- `NINJA_PROMPTS_PORT`
- `OPENCODE_DISABLE_DAEMON`

---

## Where Migration Searches

The update script searches for your old configuration in multiple locations:

### 1. Current Config
```
~/.ninja-mcp.env
```

### 2. Legacy Config Locations
```
~/.config/ninja/config.env
~/.ninja/config.env
~/.ninja-config.env
```

### 3. Environment Variables
All `NINJA_*`, `OPENROUTER_*`, `OPENAI_*`, `SERPER_*`, `PERPLEXITY_*` variables in your current shell.

### 4. Shell RC Files
```
~/.bashrc
~/.zshrc
~/.profile
~/.bash_profile
```

### 5. Old Variable Names
The script automatically migrates old variable names:
- `OPENAI_API_KEY` → `OPENROUTER_API_KEY` (if it's an OpenRouter key)
- `OPENROUTER_MODEL` → `NINJA_MODEL`
- `OPENAI_MODEL` → `NINJA_MODEL`

---

## Migration Process

### Step 1: Update
```bash
ninja-mcp update
```

### Step 2: What Happens

1. **Search Phase**
   ```
   ▸ Detecting and migrating configuration...
   ▸ Searching for existing configurations...
   ✓ Found legacy config: ~/.config/ninja/config.env
   ✓ Migrated OPENROUTER_API_KEY from ~/.config/ninja/config.env
   ✓ Found NINJA_MODEL in environment
   ```

2. **Backup Phase**
   ```
   ✓ Backed up current config to ~/.ninja-mcp-backups/backup_20260129_123456.env
   ```

3. **Migration Summary**
   ```
   ▸ Configuration migration summary:
   ✓ OPENROUTER_API_KEY (67 chars)
   ✓ SERPER_API_KEY (32 chars)
   ✓ NINJA_MODEL = anthropic/claude-sonnet-4-5
   ✓ NINJA_SEARCH_PROVIDER = duckduckgo
   ✓ NINJA_CODE_BIN = opencode
   ```

4. **Update Package**
   ```
   ▸ Updating ninja-mcp...
   ✓ Updated from PyPI
   ```

5. **Write New Config**
   ```
   ▸ Writing migrated configuration...
   ✓ Configuration migrated to ~/.ninja-mcp.env
   ```

6. **Restart Services**
   ```
   ▸ Starting ninja daemons...
   ✓ All daemons started

   ▸ Updating Claude Code MCP servers...
   ✓ ninja-coder registered (daemon proxy mode)
   ✓ ninja-researcher registered (daemon proxy mode)
   ...
   ```

---

## Manual Migration

If you need to manually migrate settings:

### View Current Config
```bash
ninja-config list
```

### Set Individual Values
```bash
# API Keys
ninja-config api-key openrouter
ninja-config api-key serper

# Models
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5
ninja-config model coder anthropic/claude-opus-4-5

# Provider
ninja-config set NINJA_SEARCH_PROVIDER serper
```

### Interactive Model Selection
```bash
ninja-config select-model
```

---

## Backup & Recovery

### Automatic Backups
Every update creates a timestamped backup:
```
~/.ninja-mcp-backups/
├── backup_20260129_123456.env
├── backup_20260128_091122.env
└── ...
```

### Restore from Backup
```bash
# List backups
ls -lh ~/.ninja-mcp-backups/

# Restore a specific backup
cp ~/.ninja-mcp-backups/backup_20260129_123456.env ~/.ninja-mcp.env

# Restart daemons
ninja-daemon restart
```

### Manual Backup
```bash
# Before making changes
cp ~/.ninja-mcp.env ~/.ninja-mcp.env.backup

# Restore if needed
cp ~/.ninja-mcp.env.backup ~/.ninja-mcp.env
```

---

## Troubleshooting

### Issue: API Keys Not Migrated

**Check where your keys are stored:**
```bash
# Check environment
env | grep -E "OPENROUTER|SERPER|PERPLEXITY"

# Check shell RC files
grep -E "OPENROUTER|SERPER|PERPLEXITY" ~/.bashrc ~/.zshrc ~/.profile

# Check old configs
cat ~/.config/ninja/config.env 2>/dev/null
```

**Manual fix:**
```bash
ninja-config api-key openrouter
# Enter your key when prompted
```

### Issue: Models Not Migrated

**Check old model settings:**
```bash
# Check environment
env | grep -E "MODEL|NINJA"

# Check backups
cat ~/.ninja-mcp-backups/backup_*.env | grep MODEL
```

**Manual fix:**
```bash
ninja-config select-model
# Or
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5
```

### Issue: Ports Conflict

**Find which ports are used:**
```bash
ninja-config get NINJA_CODER_PORT
ninja-config get NINJA_RESEARCHER_PORT
```

**Change to free ports:**
```bash
ninja-config set NINJA_CODER_PORT 8200
ninja-daemon restart
```

### Issue: Config File Corrupted

**Restore from backup:**
```bash
# Find latest backup
ls -lt ~/.ninja-mcp-backups/ | head -5

# Restore it
cp ~/.ninja-mcp-backups/backup_20260129_123456.env ~/.ninja-mcp.env

# Verify
ninja-config list
```

---

## Verification

After migration, verify everything works:

### 1. Check Configuration
```bash
ninja-config doctor
```

Expected output:
```
✓ Configuration file exists
✓ OpenRouter API key configured
✓ Model configured: anthropic/claude-sonnet-4-5
✓ Code CLI configured: opencode
✓ All daemons running
```

### 2. Check Daemons
```bash
ninja-daemon status
```

Expected output:
```
✓ ninja-coder running on port 8100
✓ ninja-researcher running on port 8101
✓ ninja-secretary running on port 8102
```

### 3. Check MCP Servers
```bash
claude mcp list
```

Expected output:
```
ninja-coder
ninja-researcher
ninja-secretary
```

---

## New vs Old Config Format

### Old Format (Multiple Locations)
```
# ~/.config/ninja/config.env
OPENROUTER_API_KEY=sk-or-v1-xxx

# ~/.bashrc
export NINJA_MODEL=anthropic/claude-sonnet-4-5

# Separate MCP server configs
# ~/.config/claude/mcp_settings.json
```

### New Format (Centralized)
```bash
# ~/.ninja-mcp.env (single source of truth)

# API Keys
OPENROUTER_API_KEY=sk-or-v1-xxx
SERPER_API_KEY=xxx

# Models
NINJA_MODEL=anthropic/claude-sonnet-4-5
NINJA_CODER_MODEL=anthropic/claude-opus-4-5

# Providers
NINJA_SEARCH_PROVIDER=duckduckgo
NINJA_CODE_BIN=opencode
OPENAI_BASE_URL=https://openrouter.ai/api/v1

# Daemon Ports
NINJA_CODER_PORT=8100
NINJA_RESEARCHER_PORT=8101
...
```

**Benefits:**
- ✅ Single file to manage
- ✅ All MCP servers read from same config
- ✅ Easy backup/restore
- ✅ No shell conflicts
- ✅ Version controlled

---

## FAQ

### Q: Will my API keys be lost during update?
**A:** No. The update script backs up ALL keys before updating and restores them after. Backups are saved to `~/.ninja-mcp-backups/`.

### Q: What if I have keys in multiple places?
**A:** The script searches all locations and uses the first valid key found. Priority: current config > legacy configs > environment > shell RC files.

### Q: Can I keep my old config location?
**A:** No, the new version uses only `~/.ninja-mcp.env`. But your old configs are backed up and can be restored if needed.

### Q: What if update fails mid-way?
**A:** Your original config is backed up before any changes. Restore with:
```bash
cp ~/.ninja-mcp-backups/backup_*.env ~/.ninja-mcp.env
```

### Q: Do I need to reconfigure Claude Code?
**A:** No, the update script automatically re-registers all MCP servers with Claude Code.

---

## Support

If migration fails or you lose settings:

1. **Check backups**: `ls ~/.ninja-mcp-backups/`
2. **Run diagnostics**: `ninja-config doctor --fix`
3. **Check logs**: `ninja-daemon logs coder`
4. **Report issue**: https://github.com/angkira/ninja-cli-mcp/issues

Include:
- Content of backup file: `cat ~/.ninja-mcp-backups/backup_*.env`
- Current config: `cat ~/.ninja-mcp.env`
- Diagnostic output: `ninja-config doctor`
