# Configuration Examples

This directory contains example configuration files for various editors and IDEs.

## Quick Start

**Use the automatic installer** (recommended):
```bash
./scripts/install_interactive.sh
```

The installer will:
- Detect your installed editors
- Configure them automatically
- Set up environment variables
- Create backups of existing configs

## Manual Setup

If you prefer manual configuration, use these example files:

### Claude Code

**File**: [`claude-code-mcp.json`](./claude-code-mcp.json)
**Location**: `~/.config/claude/mcp.json`

```bash
# Copy example and edit
cp examples/claude-code-mcp.json ~/.config/claude/mcp.json

# Edit with your values
vim ~/.config/claude/mcp.json

# Update paths and API keys:
# - /path/to/ninja-cli-mcp → your actual path
# - sk-or-v1-... → your OpenRouter API key
```

### Zed Editor

**File**: [`zed-settings.json`](./zed-settings.json)
**Location**: `~/.config/zed/settings.json`

```bash
# Backup existing settings
cp ~/.config/zed/settings.json ~/.config/zed/settings.json.backup

# Merge with example (or copy if starting fresh)
# Note: Zed settings include other preferences, so merge carefully
vim ~/.config/zed/settings.json

# Add the context_servers section from the example
```

### VS Code (Cline Extension)

**File**: [`vscode-cline-mcp.json`](./vscode-cline-mcp.json)
**Location**:
- macOS: `~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
- Linux: `~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json`
- Windows: `%APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\cline_mcp_settings.json`

```bash
# macOS example
mkdir -p ~/Library/Application\ Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/
cp examples/vscode-cline-mcp.json ~/Library/Application\ Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json

# Edit with your values
vim ~/Library/Application\ Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json
```

## Configuration Values

### Required Changes

1. **Project Path**: Replace `/path/to/ninja-cli-mcp` with your actual path
   ```bash
   # Find your path
   pwd
   # Example: /Users/you/projects/ninja-cli-mcp
   ```

2. **API Keys**: Replace placeholder keys with your actual keys
   - `OPENROUTER_API_KEY`: Get from https://openrouter.ai/keys
   - `SERPER_API_KEY`: (Optional) Get from https://serper.dev

### Optional Customizations

**Model Selection**:
```json
{
  "env": {
    "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929",
    "NINJA_RESEARCHER_MODEL": "anthropic/claude-sonnet-4",
    "NINJA_SECRETARY_MODEL": "anthropic/claude-haiku-4.5-20250929"
  }
}
```

**Available models**:
- `anthropic/claude-haiku-4.5-20250929` - Fast, cost-effective
- `anthropic/claude-sonnet-4` - Best quality
- `anthropic/claude-opus-4` - Most capable (expensive)
- `openai/gpt-4o` - Alternative to Claude
- `qwen/qwen3-coder` - Free tier available

**Rate Limits**:
```json
{
  "env": {
    "NINJA_RESEARCHER_MAX_SOURCES": "50",
    "NINJA_RESEARCHER_PARALLEL_AGENTS": "8"
  }
}
```

**Logging**:
```json
{
  "env": {
    "NINJA_LOG_LEVEL": "DEBUG",
    "NINJA_LOG_FILE": "/tmp/ninja-coder.log"
  }
}
```

## Testing Configuration

After setting up, test each module:

### Test Coder Module

```bash
# In your editor's AI assistant:
Please use the coder tool to create a simple hello world function
```

### Test Researcher Module

```bash
# In your editor's AI assistant:
Use researcher to search for "Python asyncio best practices"
```

### Test Secretary Module

```bash
# In your editor's AI assistant:
Use secretary to show me the file tree of this project
```

## Troubleshooting

### Configuration Not Loading

1. **Check JSON syntax**:
   ```bash
   python -m json.tool < ~/.config/claude/mcp.json
   ```

2. **Check file permissions**:
   ```bash
   ls -la ~/.config/claude/mcp.json
   chmod 600 ~/.config/claude/mcp.json
   ```

3. **Restart editor completely**

### Servers Not Connecting

1. **Test server manually**:
   ```bash
   cd /path/to/ninja-cli-mcp
   source ~/.ninja-mcp.env
   uv run python -m ninja_coder.server
   ```

2. **Check uv installation**:
   ```bash
   which uv
   uv --version
   ```

3. **Check environment variables**:
   ```bash
   echo $OPENROUTER_API_KEY
   ```

### API Key Issues

1. **Verify API key**:
   ```bash
   curl https://openrouter.ai/api/v1/models \
     -H "Authorization: Bearer $OPENROUTER_API_KEY"
   ```

2. **Check key format**:
   - Should start with `sk-or-v1-`
   - No extra spaces or quotes
   - Not expired

## Support

For more help:
- Read the full guide: [EDITOR_INTEGRATIONS.md](../docs/EDITOR_INTEGRATIONS.md)
- Check documentation: [docs/](../docs/)
- Report issues: GitHub Issues

---

*Last updated: December 25, 2024*
