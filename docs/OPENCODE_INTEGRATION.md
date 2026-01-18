# OpenCode MCP Integration for Ninja CLI-MCP

## Overview

This integration allows Ninja MCP servers to be registered with the OpenCode CLI, enabling AI agents to use Ninja tools (coder, researcher, secretary, resources, prompts).

## Important Limitation ⚠️

**OpenCode CLI v1.1.25 does NOT support non-interactive MCP server registration.**

The `opencode mcp add` command is purely interactive and must be run manually by users. There is no `--json`, `--silent`, or other flag to bypass the TUI interface.

## Installation Options

### Option 1: Standalone Script

```bash
# Register all 5 modules
./scripts/install_opencode_mcp.sh --all

# Register specific modules
./scripts/install_opencode_mcp.sh --coder --researcher --secretary
```

### Option 2: Auto Installer

```bash
# Full installation (auto-detects OpenCode)
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash

# Interactive installer
./scripts/install_interactive.sh
```

### Option 3: Interactive Installer

The interactive installer will:
1. Detect OpenCode CLI (Step 9: IDE Integration)
2. Prompt to register modules with OpenCode
3. Generate configuration files

## Configuration Files Generated

The installation creates/updates configuration at:

1. **`~/.config/opencode/.opencode.json`** (global config)
2. **`./.opencode.json`** (project-local config, optional)

### Configuration Format

```json
{
  "ninja-coder": {
    "type": "stdio",
    "command": "ninja-coder",
    "disabled": false,
    "env": [
      "OPENROUTER_API_KEY=sk-or-...",
      "NINJA_CODER_MODEL=anthropic/claude-haiku-4.5-20250929",
      "NINJA_CODE_BIN=aider",
      "NINJA_CODER_TIMEOUT=600"
    ]
  },
  "ninja-researcher": {
    "type": "stdio",
    "command": "ninja-researcher",
    "disabled": false,
    "env": [
      "OPENROUTER_API_KEY=...",
      "NINJA_RESEARCHER_MODEL=anthropic/claude-sonnet-4",
      "NINJA_RESEARCHER_MAX_SOURCES=20",
      "NINJA_RESEARCHER_PARALLEL_AGENTS=4"
    ]
  },
  "ninja-secretary": {
    "type": "stdio",
    "command": "ninja-secretary",
    "disabled": false,
    "env": [
      "NINJA_SECRETARY_MODEL=anthropic/claude-haiku-4.5-20250929",
      "NINJA_SECRETARY_MAX_FILE_SIZE=1048576"
    ]
  }
}
```

**Important Notes:**
- Config is stored at root level (without `mcpServers` wrapper) OR with `mcpServers` wrapper
- OpenCode may require specific format
- `env` must be an array of strings
- `disabled` must be boolean `false` (JSON false)

## Manual Registration Required ⚠️

After running installation scripts, you MUST complete the setup manually:

```bash
# Run this command to open interactive MCP registration
opencode mcp add
```

### Interactive Flow

When you run `opencode mcp add`, you will:

1. **Select Location**
   - Choose "Global" (recommended)
   - Config will be saved to `~/.config/opencode/.opencode.json`

2. **Add Each Server**
   - Enter server name: `ninja-coder`
   - Select type: `stdio`
   - Enter command: `ninja-coder`
   - Add environment variables (as array entries):
     - `OPENROUTER_API_KEY=your-key-here`
     - `NINJA_CODER_MODEL=anthropic/claude-haiku-4.5-20250929`
     - `NINJA_CODE_BIN=aider`
   - Repeat for each module

3. **Exit and Verify**
   - Exit the interactive interface
   - Run `opencode mcp list` to verify registration

### Server Registration Details

#### ninja-coder
```
Server Name: ninja-coder
Type: stdio
Command: ninja-coder (or: uv --directory /path/to/project run ninja-coder)
Environment Variables:
  - OPENROUTER_API_KEY=sk-or-...
  - NINJA_CODER_MODEL=anthropic/claude-haiku-4.5-20250929
  - NINJA_CODE_BIN=aider
  - NINJA_CODER_TIMEOUT=600
```

#### ninja-researcher
```
Server Name: ninja-researcher
Type: stdio
Command: ninja-researcher
Environment Variables:
  - OPENROUTER_API_KEY=sk-or-...
  - NINJA_RESEARCHER_MODEL=anthropic/claude-sonnet-4
  - NINJA_RESEARCHER_MAX_SOURCES=20
  - NINJA_RESEARCHER_PARALLEL_AGENTS=4
```

#### ninja-secretary
```
Server Name: ninja-secretary
Type: stdio
Command: ninja-secretary
Environment Variables:
  - NINJA_SECRETARY_MODEL=anthropic/claude-haiku-4.5-20250929
  - NINJA_SECRETARY_MAX_FILE_SIZE=1048576
```

#### ninja-resources
```
Server Name: ninja-resources
Type: stdio
Command: ninja-resources
Environment Variables:
  - NINJA_RESOURCES_CACHE_TTL=3600
  - NINJA_RESOURCES_MAX_FILES=1000
```

#### ninja-prompts
```
Server Name: ninja-prompts
Type: stdio
Command: ninja-prompts
Environment Variables:
  - NINJA_PROMPTS_MAX_SUGGESTIONS=5
  - NINJA_PROMPTS_CACHE_TTL=3600
```

## Verification

After registration, verify the setup:

```bash
# List all MCP servers
opencode mcp list

# Expected output:
# ┌  MCP Servers
# │
# ▲  ninja-coder (running)
# ▲  ninja-researcher (running)
# ▲  ninja-secretary (running)
# ▲  ninja-resources (running)
# ▲  ninja-prompts (running)
# └
```

## Usage

Once registered, use in OpenCode:

1. Start OpenCode: `opencode`
2. Open a project: `opencode /path/to/project`
3. Ask OpenCode to use Ninja tools:
   - "Use ninja-coder to refactor this function"
   - "Search the web using ninja-researcher"
   - "Analyze the codebase using ninja-secretary"

## Troubleshooting

### Servers not showing in `opencode mcp list`

1. Check if config file exists:
   ```bash
   ls -la ~/.config/opencode/.opencode.json
   ```

2. Validate JSON syntax:
   ```bash
   python3 -m json.tool ~/.config/opencode/.opencode.json
   ```

3. Restart OpenCode:
   ```bash
   # Kill existing processes
   pkill -f opencode
   
   # Start fresh
   opencode
   ```

4. Manually run registration:
   ```bash
   opencode mcp add
   ```

### Servers not working

1. Check if ninja binaries are in PATH:
   ```bash
   which ninja-coder
   which ninja-researcher
   which ninja-secretary
   ```

2. Test each server independently:
   ```bash
   ninja-coder --help
   ninja-researcher --help
   ninja-secretary --help
   ```

3. Check OpenCode logs:
   - OpenCode logs location varies by OS
   - Use `opencode --print-logs` to see logs

## Alternative: Migrate to Crush

Since OpenCode is archived, consider migrating to **Crush** (by Charmbracelet):

- Repository: https://github.com/charmbracelet/crush
- Actively maintained and updated
- Uses similar MCP configuration
- Installation: `brew install charmbracelet/tap/crush`

## Integration Points in Codebase

1. **`scripts/install_opencode_mcp.sh`**: Standalone registration script
2. **`scripts/install_coding_cli.sh`**: Detects/installs OpenCode CLI
3. **`install.sh`**: Auto-detects OpenCode and runs registration script
4. **`scripts/install_interactive.sh`**: 
   - Step 6: Detects OpenCode as coding CLI option
   - Step 9: Interactive registration prompt
   - Step 10: Shows OpenCode in configured editors list
5. **`config/mcp-modules.json`**: Documents OpenCode installation option
6. **`docs/CLI_STRATEGIES.md`**: Documents OpenCode CLI usage

## Key Differences from Other IDEs

| Feature | Claude Code | VS Code | Zed | OpenCode |
|---------|-------------|---------|------|----------|
| Config File | `~/.claude.json` | `settings.json` | `settings.json` | `~/.config/opencode/.opencode.json` |
| Registration Method | `claude mcp add` | Manual JSON edit | Manual JSON edit | `opencode mcp add` (interactive) |
| Auto-Install Support | ✅ Yes | ❌ No | ❌ No | ❌ No* |
| Config Key | `mcpServers` | `mcpServers` | `context_servers` | `mcpServers` |
| Non-Interactive | ✅ Yes | ✅ Yes | ✅ Yes | ❌ No |

*OpenCode requires manual `opencode mcp add` interaction (no non-interactive flags)

## Future Considerations

1. **Crush Migration**: When OpenCode migration to Crush is complete, update integration to use Crush CLI
2. **Format Changes**: Monitor Crush for new configuration formats or command options
3. **Automation Support**: If future Crush versions add non-interactive registration, update scripts to use it

## Summary

The OpenCode integration infrastructure is complete and includes:

✅ Installation scripts that generate correct config files
✅ Detection in auto and interactive installers
✅ Configuration for all 5 Ninja modules
✅ Documentation and user guidance

⚠️ Manual registration step required (`opencode mcp add`)
⚠️ Interactive-only (no automation possible)
⚠️ Consider migrating to Crush for active maintenance

Users should run the installation scripts and then manually complete setup with `opencode mcp add`.
