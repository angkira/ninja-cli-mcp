# Legacy Scripts Archive

This directory contains old installation scripts that have been replaced by the new unified installer.

## ⚠️ DO NOT USE THESE SCRIPTS

These scripts are kept for reference only and may not work with current versions.

## What Replaced Them

### Old → New

| Old Script | New Solution |
|-----------|--------------|
| `install_interactive.sh` | `ninja-config select-model` |
| `configure-opencode.sh` | `ninja-config` CLI |
| `install_claude_code_mcp.sh` | `./install.sh` (auto-detects) |
| `install_opencode_mcp.sh` | `./install.sh` (auto-detects) |
| `install_vscode_mcp.sh` | `./install.sh` (auto-detects) |
| `install_zed_mcp.sh` | `./install.sh` (auto-detects) |
| `install_daemon.sh` | `./install.sh` (included) |
| `install_ide_integrations.sh` | `./install.sh` (included) |
| `install_coding_cli.sh` | `./install.sh` (included) |
| `install.sh` (this dir) | `./install.sh` (root) |

### Use Instead

**Fresh installation:**
```bash
./install.sh
```

**Update existing installation:**
```bash
./update.sh
```

**Configure after installation:**
```bash
ninja-config select-model
ninja-config doctor
```

## Why These Were Archived

1. **Redundancy** - Multiple scripts doing similar things
2. **Maintenance burden** - Hard to keep 12+ scripts in sync
3. **User confusion** - Too many options, unclear which to use
4. **Better alternatives** - New unified installer with migration
5. **Code quality** - Old scripts had inconsistent error handling

## If You Need Old Functionality

The new installer includes all functionality from these scripts:

- ✅ Auto-detection of IDEs (Claude Code, VS Code, Zed)
- ✅ Auto-installation of coding CLIs (aider, opencode)
- ✅ Daemon setup
- ✅ MCP server registration
- ✅ Interactive configuration
- ✅ Migration from old configs

## Can These Be Deleted?

Yes, once you verify the new installer works for your use case.

To delete:
```bash
rm -rf scripts/legacy_archive/
```
