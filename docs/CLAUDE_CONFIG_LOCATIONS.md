# Claude Code MCP Configuration Locations

## Overview

Claude Code has changed its MCP configuration location between versions. This document explains the correct location and how our installers handle it.

## Configuration Locations

### Current (Claude Code 2.x+)

**Location:** `~/.claude.json`

**Structure:**
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {...}
    }
  },
  "other": "settings..."
}
```

The `mcpServers` key is embedded within the main Claude Code configuration file.

### Legacy (Old versions)

**Location:** `~/.config/claude/mcp.json`

**Structure:**
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {...}
    }
  }
}
```

Standalone MCP configuration file.

## Auto-Detection

Our installers automatically detect the correct location using this logic:

1. **Priority 1:** If `~/.claude.json` exists and contains `mcpServers`, use it
2. **Priority 2:** If `~/.config/claude/mcp.json` exists, use it (legacy)
3. **Priority 3:** If `claude` command is available, use `~/.claude.json` (current standard)
4. **Default:** Use `~/.claude.json`

## Migration

If you have configuration in the old location, our installers will:

1. Detect both files exist
2. Offer to migrate MCP servers from old → new location
3. Backup the old file
4. Merge configurations

### Manual Migration

If you need to migrate manually:

```bash
# 1. Check current location
ls -la ~/.claude.json ~/.config/claude/mcp.json

# 2. Merge configurations
python3 << 'EOF'
import json
from pathlib import Path

old = Path.home() / '.config/claude/mcp.json'
new = Path.home() / '.claude.json'

# Load both
old_data = json.loads(old.read_text())
new_data = json.loads(new.read_text()) if new.exists() else {}

# Merge
if 'mcpServers' not in new_data:
    new_data['mcpServers'] = {}
new_data['mcpServers'].update(old_data.get('mcpServers', {}))

# Save
new.write_text(json.dumps(new_data, indent=2) + '\n')
print(f"✓ Migrated to {new}")
EOF

# 3. Backup old config
cp ~/.config/claude/mcp.json ~/.config/claude/mcp.json.backup
```

## Installer Behavior

### `install_claude_code_mcp.sh`

```bash
# Automatically detects correct location
./scripts/install_claude_code_mcp.sh --all
```

Output:
```
Using Claude Code config: /home/user/.claude.json
✓ ninja-coder configured
✓ ninja-researcher configured
✓ ninja-secretary configured
```

### `install_interactive.sh`

```bash
# Interactive installer also auto-detects
./scripts/install_interactive.sh
```

Will prompt for migration if needed.

## Troubleshooting

### "MCP servers not showing up"

**Symptom:** Servers configured but not appearing in Claude Code

**Solution:**
```bash
# 1. Check which config Claude is using
claude mcp list

# 2. Verify config location
cat ~/.claude.json | jq '.mcpServers'

# 3. If empty, check legacy location
cat ~/.config/claude/mcp.json

# 4. Re-run installer
./scripts/install_claude_code_mcp.sh --all
```

### "Two different configs"

**Symptom:** Configs in both locations, unsure which is used

**Solution:**
```bash
# Claude Code 2.x always uses ~/.claude.json
# Check your version
claude --version

# If 2.x, delete old config after backing up
cp ~/.config/claude/mcp.json ~/.config/claude/mcp.json.backup
# Then re-run installer
./scripts/install_claude_code_mcp.sh --all
```

### "Permission denied" errors

**Symptom:** Can't write to config

**Solution:**
```bash
# Fix permissions
chmod 600 ~/.claude.json

# Recreate if corrupted
rm ~/.claude.json
echo '{}' > ~/.claude.json
chmod 600 ~/.claude.json

# Re-run installer
./scripts/install_claude_code_mcp.sh --all
```

## Shared Utility

All installers use a shared utility for consistent behavior:

**File:** `scripts/lib/claude_config.sh`

**Functions:**
- `detect_claude_mcp_config()` - Auto-detect correct location
- `init_claude_mcp_config()` - Initialize config file
- `update_claude_mcp_server()` - Add/update MCP server
- `check_config_migration()` - Offer migration if needed

## Testing

To test config detection:

```bash
# Source the utility
source scripts/lib/claude_config.sh

# Detect location
CONFIG=$(detect_claude_mcp_config)
echo "Config location: $CONFIG"

# Check if migration needed
check_config_migration
```

## Best Practices

1. **Always use installers** - Don't manually edit configs
2. **Let auto-detection work** - Installers will find the right location
3. **Accept migration prompts** - When offered, migrate to new location
4. **Backup before changes** - Installers create backups automatically
5. **Verify after install** - Run `claude mcp list` to confirm

## Summary

| Version | Location | Auto-Detected | Supported |
|---------|----------|---------------|-----------|
| Claude Code 2.x | `~/.claude.json` | ✅ Yes | ✅ Primary |
| Legacy | `~/.config/claude/mcp.json` | ✅ Yes | ✅ Legacy |

**Recommendation:** Use latest installers, they handle everything automatically!
