# OpenCode Setup Guide for Ninja MCP

This guide shows how to configure ninja-coder to use OpenCode with multiple AI providers (Anthropic, Google, OpenAI, GitHub Copilot).

## Quick Setup

### Option 1: Automatic (Recommended)

Run the update script, which will automatically detect and configure OpenCode:

```bash
./update.sh
```

This will:
- Update all ninja-mcp components
- Detect OpenCode installation
- Configure ninja-coder to use `anthropic/claude-sonnet-4-5`
- Preserve your existing configuration

### Option 2: Manual Configuration

If you need to configure manually (or reconfigure later):

```bash
# 1. Exit Claude Code completely
# 2. Run configuration script
./configure-opencode.sh

# 3. Restart Claude Code
```

## Supported Models

Once OpenCode is configured with multiple providers, you can use any of these models by editing `NINJA_MODEL` in `~/.claude.json`:

### Anthropic (Recommended)
```json
"NINJA_MODEL": "anthropic/claude-sonnet-4-5"     # Balanced, recommended
"NINJA_MODEL": "anthropic/claude-opus-4-5"       # Most powerful
"NINJA_MODEL": "anthropic/claude-sonnet-3-5"     # Previous generation
```

### Google
```json
"NINJA_MODEL": "google/gemini-2.0-flash-exp"     # Fast & cost-effective
"NINJA_MODEL": "google/gemini-1.5-pro"           # Balanced
```

### OpenAI
```json
"NINJA_MODEL": "openai/gpt-4o"                   # Latest GPT-4
"NINJA_MODEL": "openai/gpt-4-turbo"              # GPT-4 Turbo
```

### GitHub Copilot
```json
"NINJA_MODEL": "github/gpt-4o"                   # Via GitHub Copilot
```

## Verifying OpenCode Setup

Check that OpenCode is properly configured:

```bash
# Check OpenCode installation
opencode --version

# Check authenticated providers
opencode auth list

# Expected output:
# ●  Anthropic (api)
# ●  Google (api)
# ●  OpenAI (api)
# ●  GitHub Copilot (oauth)
```

## Configuration Files

### `~/.claude.json`
Claude Code's MCP server configuration:

```json
{
  "mcpServers": {
    "ninja-coder": {
      "type": "stdio",
      "command": "ninja-coder",
      "args": [],
      "env": {
        "NINJA_CODE_BIN": "/Users/YOUR_USER/.opencode/bin/opencode",
        "NINJA_MODEL": "anthropic/claude-sonnet-4-5"
      }
    }
  }
}
```

### `~/.ninja-mcp.env`
Ninja MCP environment configuration (preserved during updates):

```bash
# API Keys (optional if using OpenCode with authenticated providers)
OPENROUTER_API_KEY=your_key_here
SERPER_API_KEY=your_key_here
PERPLEXITY_API_KEY=your_key_here

# Daemon Ports
NINJA_CODER_PORT=8100
NINJA_RESEARCHER_PORT=8101
NINJA_SECRETARY_PORT=8102
NINJA_RESOURCES_PORT=8106
NINJA_PROMPTS_PORT=8107
```

## Benefits of OpenCode

✅ **Multiple Providers** - No dependency on single provider
✅ **No Credit Limits** - Use native provider authentication
✅ **Better Reliability** - Automatic fallback between providers
✅ **Latest Models** - Access to newest models (Claude Sonnet 4.5, Gemini 2.0, etc.)
✅ **Cost Effective** - Use Google Gemini for fast, cheap operations

## Automatic Config Detection

Thanks to the fixes implemented (commit 3eb8cb8), ninja-coder now automatically detects configuration changes:

- **No restart needed** - Config changes detected automatically
- **Dynamic switching** - Switch between models/providers on the fly
- **Better error messages** - Authentication and credit errors clearly reported

## Troubleshooting

### OpenCode Not Found

Install OpenCode:
```bash
# Visit: https://github.com/stackblitz/opencode
# Or use their installer
```

### Authentication Errors

Authenticate providers:
```bash
# Anthropic
opencode auth add anthropic

# Google
opencode auth add google

# OpenAI
opencode auth add openai

# GitHub Copilot
opencode auth add github
```

### Config Not Applied

1. Exit Claude Code completely
2. Run `./configure-opencode.sh`
3. Verify `~/.claude.json` has the env variables
4. Restart Claude Code

### Still Using Old Config

The ToolExecutor singleton now detects config changes, but if you're experiencing issues:

1. Check that Claude Code daemon has restarted:
   ```bash
   ps aux | grep ninja-coder
   ```

2. Kill old processes if needed:
   ```bash
   pkill -f ninja-coder
   ```

3. Restart Claude Code completely

## Testing the Setup

After configuration, test that it works:

```bash
# 1. Check ninja-coder can find OpenCode
ninja-coder --help

# 2. In Claude Code, try a simple code generation request:
# "Create a Python function that checks if a number is prime"

# 3. Check logs if there are issues
ls ~/.cache/ninja-mcp/*/logs/
```

## Related Documentation

- [INVESTIGATION_2026-01-26.md](./INVESTIGATION_2026-01-26.md) - All fixes and testing
- [README.md](./README.md) - Main ninja-mcp documentation
- [OpenCode GitHub](https://github.com/stackblitz/opencode) - OpenCode project

## Support

If you encounter issues:
1. Check logs: `~/.cache/ninja-mcp/*/logs/`
2. Run diagnostics: `ninja-config doctor`
3. Check MCP servers: `claude mcp list`
4. Open an issue with logs and error messages
