# Installation Modes for Ninja MCP

The Ninja MCP servers support multiple installation modes to accommodate different use cases. **This guide helps avoid hardcoded paths that break when others install the package.**

## Quick Summary

| Mode | Use Case | Command | MCP Config |
|------|----------|---------|------------|
| **Global** | Regular users | `uv tool install ninja-mcp[all]` | Uses `ninja-coder` directly |
| **Local Dev** | Contributors | `uv sync --all-extras` | Uses `uv --directory <path> run ninja-coder` |
| **One-off** | Quick testing | `uvx --from ninja-mcp[coder] ninja-coder` | Uses `uvx --from ninja-mcp[coder] ninja-coder` |

## Installation Modes

### 1. Global Installation (Recommended for Users)

**Best for**: Regular users who want to install once and use everywhere.

```bash
# Install all modules globally
uv tool install ninja-mcp[all]

# Or install specific modules
uv tool install ninja-mcp[coder]
uv tool install ninja-mcp[researcher]
uv tool install ninja-mcp[secretary]
```

**MCP Configuration** (`~/.config/claude/mcp.json`):

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
        "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929",
        "NINJA_CODE_BIN": "aider"
      }
    }
  }
}
```

**Advantages**:
- ✅ No hardcoded paths
- ✅ Works from any directory
- ✅ Easy to share configuration
- ✅ Simple updates: `uv tool upgrade ninja-mcp`

**Installation Script**:
```bash
./scripts/install_claude_code_mcp.sh --all
```
The script auto-detects global installation and configures accordingly.

### 2. Local Development Mode

**Best for**: Contributors developing Ninja MCP itself.

```bash
# Clone and install in editable mode
git clone https://github.com/yourusername/ninja-mcp
cd ninja-mcp
uv sync --all-extras

# Set environment variable pointing to project directory
export NINJA_MCP_PROJECT_DIR="$(pwd)"
```

**MCP Configuration** (`~/.config/claude/mcp.json`):

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "uv",
      "args": [
        "--directory",
        "${NINJA_MCP_PROJECT_DIR}",
        "run",
        "ninja-coder"
      ],
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}",
        "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929"
      }
    }
  }
}
```

**Important**: Set `NINJA_MCP_PROJECT_DIR` in your shell profile:

```bash
# Add to ~/.bashrc or ~/.zshrc
export NINJA_MCP_PROJECT_DIR="$HOME/Projects/ninja-mcp"
```

**Installation Script**:
```bash
cd /path/to/ninja-mcp
./scripts/install_claude_code_mcp.sh --all
```
The script auto-detects local mode and uses the project directory.

**Advantages**:
- ✅ Test changes immediately
- ✅ No reinstallation needed
- ✅ Still no user-specific hardcoded paths (uses environment variable)

### 3. One-off Execution (Advanced)

**Best for**: Testing without installation, or using different versions.

**MCP Configuration**:

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "uvx",
      "args": [
        "--from",
        "ninja-mcp[coder]",
        "ninja-coder"
      ],
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"
      }
    }
  }
}
```

**Advantages**:
- ✅ No installation needed
- ✅ Can specify versions: `uvx --from ninja-mcp==0.2.0[coder] ninja-coder`

**Disadvantages**:
- ⚠️ Slower startup (downloads on first run)
- ⚠️ Requires network access

## Environment Variables

All modes support these environment variables:

### Common Variables
- `OPENROUTER_API_KEY` - Required for all modules
- `NINJA_MCP_PROJECT_DIR` - Only needed for local dev mode

### Coder Module
- `NINJA_CODER_MODEL` - Model to use (default: `anthropic/claude-haiku-4.5-20250929`)
- `NINJA_CODE_BIN` - Code assistant CLI (default: `aider`)
- `NINJA_CODER_TIMEOUT` - Timeout in seconds (default: `600`)

### Researcher Module
- `NINJA_RESEARCHER_MODEL` - Model to use (default: `anthropic/claude-sonnet-4`)
- `SERPER_API_KEY` - Optional Serper.dev API key
- `NINJA_RESEARCHER_MAX_SOURCES` - Max sources per search (default: `20`)
- `NINJA_RESEARCHER_PARALLEL_AGENTS` - Parallel agents (default: `4`)

### Secretary Module
- `NINJA_SECRETARY_MODEL` - Model to use (default: `anthropic/claude-haiku-4.5-20250929`)
- `NINJA_SECRETARY_MAX_FILE_SIZE` - Max file size in bytes (default: `1048576`)

## Configuration Examples

See `examples/` directory for complete configuration templates:

- `mcp-config-template.json` - For global installation (production)
- `mcp-config-local-dev.json` - For local development
- `claude-code-mcp.json` - Full Claude Code example
- `vscode-cline-mcp.json` - Full VS Code Cline example

## Automated Installation

The automated installer script handles all modes:

```bash
# Run installer
./scripts/install_claude_code_mcp.sh --all

# Or select specific modules
./scripts/install_claude_code_mcp.sh --coder --researcher

# The script will:
# 1. Detect your installation mode (global vs local)
# 2. Generate the correct MCP configuration
# 3. Place it in the right location for your IDE
# 4. Validate the configuration
```

## Migration Between Modes

### From Hardcoded Paths to Global

```bash
# 1. Uninstall old configuration
rm ~/.config/claude/mcp.json

# 2. Install globally
uv tool install ninja-mcp[all]

# 3. Run installer
./scripts/install_claude_code_mcp.sh --all
```

### From Global to Local Dev

```bash
# 1. Uninstall global
uv tool uninstall ninja-mcp

# 2. Clone and sync
git clone https://github.com/yourusername/ninja-mcp
cd ninja-mcp
uv sync --all-extras

# 3. Set environment variable
export NINJA_MCP_PROJECT_DIR="$(pwd)"
echo 'export NINJA_MCP_PROJECT_DIR="'$(pwd)'"' >> ~/.bashrc

# 4. Run installer
./scripts/install_claude_code_mcp.sh --all
```

## Troubleshooting

### "Command not found: ninja-coder"

**Solution**: Either install globally with `uv tool install ninja-mcp[coder]` or use local dev mode configuration.

### "Wrong version is running"

**Solution**: Check which installation is active:
```bash
which ninja-coder
uv tool list | grep ninja-mcp
```

### "Still seeing hardcoded paths"

**Solution**: The installer script should auto-detect and fix this. If not:
1. Delete old configuration: `rm ~/.config/claude/mcp.json`
2. Re-run installer: `./scripts/install_claude_code_mcp.sh --all`
3. Verify: `cat ~/.config/claude/mcp.json` should not contain hardcoded paths

### "Environment variables not working"

Claude Code MCP supports `${VAR}` syntax in env fields. Make sure:
1. Variables are exported in your shell profile
2. Claude Code is restarted after setting variables
3. Check with: `echo $OPENROUTER_API_KEY`
