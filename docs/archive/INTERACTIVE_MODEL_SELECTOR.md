# Interactive Model Selector

The interactive model selector makes it easy to configure ninja-coder with your preferred operator and model. No manual JSON editing required!

## Quick Start

```bash
ninja-config select-model
```

That's it! The selector will guide you through:

1. **Operator Selection** - Choose from installed operators (OpenCode, Aider, Gemini CLI)
2. **Model Selection** - Pick a model based on provider authentication
3. **Auto-Configuration** - Updates ~/.ninja-mcp.env and ~/.claude.json

## Features

### 🔍 Automatic Detection

Detects which operators are installed on your system:
- **OpenCode** - 75+ providers, 11 models configured
- **Aider** - OpenRouter-based, 7 models configured
- **Gemini CLI** - Google native, 3 models configured

### 🔐 Authentication Status

Shows which providers are authenticated for each operator:

**OpenCode:**
- ✓/✗ Anthropic (API)
- ✓/✗ Google (API)
- ✓/✗ OpenAI (API)
- ✓/✗ GitHub Copilot (OAuth)

**Aider:**
- ✓/✗ OpenRouter (API key)

**Gemini CLI:**
- ✓/✗ Google (API key)

### 📋 Model Catalog

#### OpenCode Models (11 total)

**Anthropic:**
- Claude Sonnet 4.5 [RECOMMENDED] - Latest Claude, balanced
- Claude Opus 4.5 - Most powerful
- Claude Sonnet 3.5 - Previous generation, fast
- Claude Haiku 3.5 - Cost-effective for simple tasks

**Google:**
- Gemini 2.0 Flash - Experimental, very fast
- Gemini 1.5 Pro - Balanced
- Gemini 1.5 Flash - Fast

**OpenAI:**
- GPT-4o - Latest, multimodal
- GPT-4 Turbo - Fast variant
- o1-preview - Reasoning model

**GitHub:**
- GPT-4o (via GitHub) - Access via Copilot

#### Aider Models (7 total)

All models accessed via OpenRouter:
- Claude Sonnet 4.5 [RECOMMENDED]
- Claude Opus 4.5
- Claude Sonnet 3.5
- Gemini 2.0 Flash
- GPT-4o
- DeepSeek Coder - Specialized coding
- Qwen 2.5 Coder 32B - Open source coding

#### Gemini CLI Models (3 total)

Google-native models:
- Gemini 2.0 Flash [RECOMMENDED] - Latest experimental
- Gemini 1.5 Pro - Balanced
- Gemini 1.5 Flash - Fast & cost-effective

## Example Session

```bash
$ ninja-config select-model

======================================================================
  🥷 NINJA CODER - OPERATOR SELECTION
======================================================================

📦 Available Operators:

1. OpenCode
   Multi-provider CLI (75+ providers, native z.ai support)
   Binary: /Users/you/.opencode/bin/opencode
   Auth: 4 provider(s) authenticated
     ✓ anthropic
     ✓ google
     ✓ openai
     ✓ github

2. Aider
   OpenRouter-based CLI (requires OPENROUTER_API_KEY)
   Binary: /Users/you/.local/bin/aider
   Auth: 1 provider(s) authenticated
     ✓ openrouter

3. Gemini CLI
   Google Gemini native CLI
   Binary: /usr/local/bin/gemini
   Auth: 1 provider(s) authenticated
     ✓ google

Select operator [1-3] or 'q' to quit: 1

======================================================================
  🤖 MODEL SELECTION - OpenCode
======================================================================

📋 Available Models:

  ✓ ANTHROPIC
    1. Claude Sonnet 4.5 [RECOMMENDED]
       Latest Claude - Balanced performance & cost
       ID: anthropic/claude-sonnet-4-5

    2. Claude Opus 4.5
       Most powerful Claude model
       ID: anthropic/claude-opus-4-5

    3. Claude Sonnet 3.5
       Previous generation - Fast & capable
       ID: anthropic/claude-sonnet-3-5

    4. Claude Haiku 3.5
       Fast & cost-effective for simple tasks
       ID: anthropic/claude-haiku-3-5

  ✓ GOOGLE
    5. Gemini 2.0 Flash
       Fast, experimental, very cost-effective
       ID: google/gemini-2.0-flash-exp

    [...]

Select model [1-11] or 'q' to quit: 1

======================================================================
  🔍 CONFIRM SELECTION
======================================================================

Operator: OpenCode
Model:    Claude Sonnet 4.5 (anthropic/claude-sonnet-4-5)

Apply this configuration? [Y/n]: y

======================================================================
  💾 UPDATING CONFIGURATION
======================================================================

1. Updating /Users/you/.ninja-mcp.env...
   ✓ Updated .ninja-mcp.env

2. Updating /Users/you/.claude.json...
   ✓ Updated .claude.json

======================================================================
  ✅ CONFIGURATION COMPLETE
======================================================================

Operator: OpenCode
  Binary: /Users/you/.opencode/bin/opencode

Model: Claude Sonnet 4.5
  ID: anthropic/claude-sonnet-4-5
  Provider: anthropic
  Latest Claude - Balanced performance & cost

📝 Next Steps:
  1. Restart Claude Code (if running)
  2. Config will be automatically detected
  3. Test by asking Claude Code to write some code!

💡 To change later, run:
     ninja-config select-model
```

## Integration Points

### Configuration Files Updated

1. **~/.ninja-mcp.env** - Environment variables
   ```bash
   NINJA_CODE_BIN=/Users/you/.opencode/bin/opencode
   NINJA_MODEL=anthropic/claude-sonnet-4-5
   ```

2. **~/.claude.json** - MCP server configuration
   ```json
   {
     "mcpServers": {
       "ninja-coder": {
         "type": "stdio",
         "command": "ninja-coder",
         "args": [],
         "env": {
           "NINJA_CODE_BIN": "/Users/you/.opencode/bin/opencode",
           "NINJA_MODEL": "anthropic/claude-sonnet-4-5"
         }
       }
     }
   }
   ```

### Automatic Detection

Thanks to the config change detection fix (commit 3eb8cb8), changes are automatically detected without restarting the entire system!

## Safety Features

- ✅ Detects if Claude Code is running (warns about restart needed)
- ✅ Only shows installed operators
- ✅ Filters models by authentication status
- ✅ Validates selections before applying
- ✅ Confirmation prompt before changing config
- ✅ Safe JSON patching (preserves file structure)

## Tips

### Choosing an Operator

**Choose OpenCode if:**
- You want access to multiple providers (Anthropic, Google, OpenAI, GitHub)
- You want the latest models (Claude Sonnet 4.5, Gemini 2.0)
- You want native provider authentication (no OpenRouter needed)
- You want built-in provider fallback

**Choose Aider if:**
- You have an OpenRouter API key
- You want access to more niche models (DeepSeek, Qwen)
- You prefer OpenRouter's unified API

**Choose Gemini CLI if:**
- You only use Google models
- You want the fastest, simplest setup
- You have a Google API key

### Choosing a Model

**For most coding tasks:**
- Claude Sonnet 4.5 (recommended balance)
- Gemini 2.0 Flash (cost-effective)

**For complex tasks:**
- Claude Opus 4.5 (most powerful)
- GPT-4o (multimodal capabilities)

**For simple tasks:**
- Claude Haiku 3.5 (fast & cheap)
- Gemini 1.5 Flash (fast & cheap)

**For specialized coding:**
- DeepSeek Coder (Aider only)
- Qwen 2.5 Coder (Aider only)

## Command Reference

```bash
# Interactive selection (recommended)
ninja-config select-model

# Manual configuration (old way)
ninja-config set NINJA_CODE_BIN /path/to/opencode
ninja-config set NINJA_MODEL anthropic/claude-sonnet-4-5

# View current config
ninja-config list

# Diagnose issues
ninja-config doctor
```

## Troubleshooting

### "No operators found"

Install an operator:
```bash
# OpenCode
# Visit: https://github.com/stackblitz/opencode

# Aider
uv tool install aider-chat

# Gemini CLI
npm install -g @google/generative-ai-cli
```

### "Some providers not authenticated"

Authenticate missing providers:
```bash
# OpenCode
opencode auth add anthropic
opencode auth add google
opencode auth add openai
opencode auth add github

# Aider (uses OpenRouter)
ninja-config api-key openrouter

# Gemini CLI
export GOOGLE_API_KEY=your_key
```

### "Claude Code is running" warning

The selector can still update config, but you need to restart Claude Code for changes to take effect.

### Changes not applied

1. Make sure Claude Code is fully restarted (not just window closed)
2. Check that config files were updated: `cat ~/.ninja-mcp.env | grep NINJA_`
3. Run `ninja-config doctor` to diagnose issues

## Related Documentation

- [OPENCODE_SETUP.md](./OPENCODE_SETUP.md) - OpenCode setup guide
- [INVESTIGATION_2026-01-26.md](./INVESTIGATION_2026-01-26.md) - All fixes and testing
- [README.md](./README.md) - Main documentation
