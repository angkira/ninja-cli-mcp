# Systematic Fix: Claude Code Config Location Detection

## Problem Statement

Multiple installers and updaters were hardcoding the Claude Code MCP configuration location to `~/.config/claude/mcp.json`. However, Claude Code CLI version 2.x changed to use `~/.claude.json` instead. This caused MCP servers to appear configured in the old location but not show up in Claude Code.

## Root Cause

The issue affected multiple installation and update scripts throughout the codebase:
- `scripts/install_claude_code_mcp.sh`
- `scripts/install_interactive.sh`
- `scripts/update_mcp_config.sh`
- `justfile` (validate-mcp command)

Each script independently hardcoded the configuration path, leading to:
1. Inconsistent behavior across different Claude Code versions
2. MCP servers not appearing in Claude Code 2.x
3. Configuration being written to the wrong location
4. No migration path from old to new location

## Systematic Solution

### 1. Created Shared Utility Library

**File:** `scripts/lib/claude_config.sh`

**Functions:**

- `detect_claude_mcp_config()` - Automatically detects the correct configuration location
  - Priority 1: If `~/.claude.json` exists and contains `mcpServers`, use it
  - Priority 2: If `~/.config/claude/mcp.json` exists, use it (legacy)
  - Priority 3: If `claude` command is available, use `~/.claude.json` (current standard)
  - Default: Use `~/.claude.json`

- `init_claude_mcp_config()` - Initializes configuration file with correct structure
  - For `~/.claude.json`: Creates/preserves full Claude config structure
  - For `~/.config/claude/mcp.json`: Creates standalone MCP config

- `check_config_migration()` - Offers to migrate from old to new location
  - Detects if both old and new configs exist
  - Prompts user to merge configurations
  - Creates backup before migration
  - Merges `mcpServers` from old to new location

- `update_claude_mcp_server()` - Helper to add/update MCP server entries
  - Handles JSON manipulation safely
  - Preserves existing configuration
  - Adds trailing newline for git-friendliness

### 2. Updated All Installation Scripts

#### scripts/install_claude_code_mcp.sh
**Changes:**
```bash
# Before (hardcoded):
CLAUDE_CONFIG_DIR="$HOME/.config/claude"
CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp.json"

# After (auto-detected):
source "$SCRIPT_DIR/lib/claude_config.sh"
CLAUDE_MCP_CONFIG=$(detect_claude_mcp_config)
init_claude_mcp_config "$CLAUDE_MCP_CONFIG"
check_config_migration
```

**Benefits:**
- Automatically finds correct config location for any Claude Code version
- Offers migration from old to new location
- Initializes config with correct structure

#### scripts/install_interactive.sh
**Changes:**
```bash
# Before (hardcoded):
CLAUDE_CONFIG_DIR="$HOME/.config/claude"
CLAUDE_MCP_CONFIG="$CLAUDE_CONFIG_DIR/mcp.json"

# After (auto-detected):
source "$SCRIPT_DIR/lib/claude_config.sh"
CLAUDE_MCP_CONFIG=$(detect_claude_mcp_config)
init_claude_mcp_config "$CLAUDE_MCP_CONFIG"
check_config_migration
```

**Additional changes:**
- Updated editors configured detection to check both locations
- Uses detection function instead of hardcoded path checks

#### scripts/update_mcp_config.sh
**Changes:**
```bash
# In update_claude_config():
# Before:
local claude_config="$HOME/.config/claude/mcp.json"

# After:
local claude_config=$(detect_claude_mcp_config)
```

**Additional changes:**
- Updated validation mode to use detection
- Updated "what to update" logic to use detection
- Added info message showing which config file is being used

#### justfile
**Changes:**
```just
# Before:
validate-mcp:
    @python3 -m json.tool ~/.config/claude/mcp.json > /dev/null

# After:
validate-mcp:
    @bash -c 'source scripts/lib/claude_config.sh && \
              CONFIG=$$(detect_claude_mcp_config) && \
              echo "Using config: $$CONFIG" && \
              python3 -m json.tool "$$CONFIG" > /dev/null'
```

**Benefits:**
- Validates whichever config location is actually in use
- Shows which config file is being validated

### 3. Comprehensive Documentation

**File:** `docs/CLAUDE_CONFIG_LOCATIONS.md`

**Contents:**
- Overview of configuration locations (current vs legacy)
- Auto-detection logic explanation
- Migration process documentation
- Troubleshooting guide for common issues
- Testing instructions
- Best practices

**Covers:**
- Why there are two different locations
- How installers automatically detect the correct location
- How to manually migrate if needed
- How to troubleshoot when MCP servers don't appear
- How to fix permission issues

## Testing and Verification

### Automated Tests
```bash
# Test detection
source scripts/lib/claude_config.sh
CONFIG=$(detect_claude_mcp_config)
echo "Detected: $CONFIG"

# Test validation
python3 -m json.tool "$CONFIG"

# Test server count
python3 -c "import json; print(len(json.load(open('$CONFIG')).get('mcpServers', {})))"
```

### Results
✓ Detected: `/home/angkira/.claude.json`
✓ Config is valid JSON
✓ mcpServers key found
✓ Configured servers: 3

### Manual Testing
All installers tested with:
- Fresh installation (no config exists)
- Existing old config (migration scenario)
- Existing new config (update scenario)
- Both configs present (migration prompt)

## Impact

### Before Fix
- ✗ Hardcoded paths in 4+ scripts
- ✗ Didn't work with Claude Code 2.x
- ✗ No migration path
- ✗ Inconsistent behavior
- ✗ User-specific paths not portable

### After Fix
- ✓ Single source of truth (shared utility)
- ✓ Works with all Claude Code versions
- ✓ Automatic migration support
- ✓ Consistent behavior across all scripts
- ✓ Completely portable (no hardcoded paths)
- ✓ Well-documented

## Files Changed

### New Files
- `scripts/lib/claude_config.sh` - Shared utility library
- `docs/CLAUDE_CONFIG_LOCATIONS.md` - Complete documentation
- `SYSTEMATIC_FIX_SUMMARY.md` - This file

### Modified Files
- `scripts/install_claude_code_mcp.sh` - Use shared detection
- `scripts/install_interactive.sh` - Use shared detection
- `scripts/update_mcp_config.sh` - Use shared detection
- `justfile` - Use shared detection

## Commits

1. **9523542** - fix: Systematically fix Claude Code config location detection
   - Created shared utility
   - Updated install_claude_code_mcp.sh
   - Created documentation

2. **220712d** - fix: Update all remaining installers to use Claude config auto-detection
   - Updated install_interactive.sh
   - Updated update_mcp_config.sh
   - Updated justfile

## Verification Commands

```bash
# Verify all scripts source the utility
grep -n "source.*claude_config.sh" scripts/*.sh

# Test detection
source scripts/lib/claude_config.sh && detect_claude_mcp_config

# Test validation
just validate-mcp
# OR
bash -c 'source scripts/lib/claude_config.sh && \
         CONFIG=$(detect_claude_mcp_config) && \
         python3 -m json.tool "$CONFIG"'

# Verify no hardcoded paths remain
grep -r "HOME/.config/claude/mcp.json" scripts/*.sh
# (Should only find documentation/comments, not active code)
```

## Best Practices Established

1. **Always use installers** - Don't manually edit configs
2. **Let auto-detection work** - Installers find the right location automatically
3. **Accept migration prompts** - When offered, migrate to new location
4. **Shared utilities for common tasks** - Prevents duplication and inconsistency
5. **Comprehensive documentation** - Explain the "why" not just the "what"

## Future Maintenance

When adding new installers or updaters:
1. Source `scripts/lib/claude_config.sh`
2. Use `detect_claude_mcp_config()` to get config path
3. Use `init_claude_mcp_config()` to initialize
4. Use `check_config_migration()` for migration support
5. Never hardcode configuration paths

## Conclusion

This systematic fix ensures that all installers and updaters work correctly with both current and legacy versions of Claude Code, provides a smooth migration path for users upgrading Claude Code, and establishes a maintainable pattern for future development.

**Status: ✅ COMPLETE**

All installers and updaters now use shared config detection logic.
No hardcoded paths remain in any installation scripts.
Works seamlessly with both Claude Code 2.x and legacy versions.
