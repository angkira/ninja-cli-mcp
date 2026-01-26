# Ninja MCP - Modern Interactive Installer & Configurator

## 🎯 Quick Start

### Installation
```bash
# Option 1: From PyPI (recommended)
pip install ninja-mcp[all]

# Option 2: From source
git clone https://github.com/angkira/ninja-cli-mcp
cd ninja-cli-mcp
uv tool install ".[all]"

# Option 3: Direct URL
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```

### Interactive Setup

After installation, run the interactive installer:
```bash
ninja-config install
```

## 📋 Available Commands

### 🛠️ Installation & Setup
- **`ninja-config install`** - Run interactive installer (first-time setup)
- **`ninja-config configure`** - Full configuration manager
- **`ninja-config auth`** - Quick API key setup

### 🎯 Operator & Model Selection  
- **`ninja-config select-model`** - Interactive operator and model selection

### 📊 Configuration Management
- **`ninja-config show`** - Show current configuration
- **`ninja-config list`** - List all config values  
- **`ninja-config get KEY`** - Get specific value
- **`ninja-config set KEY VALUE`** - Set specific value

### 🔍 Diagnostics
- **`ninja-config doctor`** - Diagnose issues
- **`ninja-config setup-claude`** - Configure Claude Code

## 🎨 Interactive Installer (`ninja-config install`)

Modern installation wizard with arrow-key navigation:

1. **Installation Type**
   - Full (all features)
   - Minimal (core only)
   - Custom (select modules)

2. **Module Selection** (if custom)
   - ☑️ coder - AI code assistant
   - ☑️ researcher - Web research  
   - ☑️ secretary - File operations
   - ☑️ resources - Templates
   - ☑️ prompts - Prompt management

3. **Dependencies**
   - Auto-install aider-chat
   - Prompt for OpenCode installation

4. **Verification**
   - Check all binaries installed
   - Show next steps

## ⚙️ Interactive Configurator (`ninja-config configure`)

Full configuration manager with persistent menu:

### 1. 🔑 Manage API Keys
Configure API keys with masked display:
- **OpenRouter** - For Aider (OpenRouter API)
- **Perplexity AI** - For researcher (best quality)
- **Serper/Google** - For researcher (Google search)
- **Google Gemini** - For Gemini CLI operator

### 2. 🎯 Configure Operators
Select and configure code operators:
- **OpenCode** - Multi-provider CLI (75+ LLMs)
- **Aider** - OpenRouter-based CLI
- **Gemini CLI** - Google Gemini native CLI

Auto-detects installed operators and shows authentication status.

### 3. 🌐 Manage Providers (OpenCode)
Authenticate OpenCode providers:
- ✓ **Anthropic** - Claude models
- ✓ **Google** - Gemini models
- ✓ **OpenAI** - GPT models
- ✓ **GitHub** - Copilot models

Runs `opencode auth <provider>` interactively.

### 4. 🔍 Search Settings
Configure researcher search provider:
- **DuckDuckGo** - Free, no API key
- **Perplexity AI** - Best quality, needs key
- **Serper/Google** - Good quality, needs key

### 5. 📋 Show Configuration
View current settings grouped by category:
- 🔑 API Keys (masked display)
- 🎯 Operator (NINJA_CODE_BIN, NINJA_MODEL)
- 🔍 Search (NINJA_SEARCH_PROVIDER)
- ⚙️  Other settings

### 6. 🗑️ Reset Configuration
Clear all configuration (with confirmation).

## 🎯 Model Selector (`ninja-config select-model`)

Interactive operator and model selection:

### Features:
- **Dynamic model loading** - Queries operators for available models
- **Arrow-key navigation** - ↑↓/j/k or type to filter
- **Intelligent filtering** - Only shows recent models (last 12 months)
- **Version-based sorting** - Latest versions first
- **Provider grouping** - Models grouped by provider
- **Auth status** - Shows authenticated providers

### Filtered Models:
- **Claude**: 4.x and 3.7+ (excludes 3.5 and older)
- **GPT**: 4o, 4.1+, 5.x, o1, o3 (excludes 3.x and basic gpt-4)
- **Gemini**: 2.x and 3.x (excludes 1.x)
- **DeepSeek**: v3+ only
- **Qwen**: 2.5+ only

### Example:
```
┌─────────────────────────────────────────┐
│  🤖 MODEL SELECTION - OpenCode          │
├─────────────────────────────────────────┤
│                                         │
│  ✓ ANTHROPIC (14 models)                │
│    ► Claude Sonnet 4 5 20250929         │
│      Claude 3 7 Sonnet Latest           │
│      Claude Haiku 4 5                   │
│      ...                                │
│                                         │
│  ✓ GOOGLE (18 models)                   │
│      Gemini 2.5 Flash                   │
│      Gemini 2.0 Flash                   │
│      ...                                │
│                                         │
│  ✓ OPENAI (30 models)                   │
│      GPT 5                              │
│      GPT 4o                             │
│      o1                                 │
│      ...                                │
└─────────────────────────────────────────┘
```

## 🔐 Quick API Key Setup (`ninja-config auth`)

Shortcut to API key configuration menu.

Configures:
1. OpenRouter API key (for Aider)
2. Perplexity API key (for researcher)
3. Serper API key (for researcher)
4. Gemini API key (for Gemini CLI)

All keys stored in `~/.ninja-mcp.env` with masked display.

## 📁 Configuration Files

### ~/.ninja-mcp.env
Main configuration file:
```bash
# API Keys
OPENROUTER_API_KEY=sk-or-...
PERPLEXITY_API_KEY=pplx-...
SERPER_API_KEY=...
GEMINI_API_KEY=...

# Operator
NINJA_CODE_BIN=opencode
NINJA_MODEL=anthropic/claude-sonnet-4-5

# Search
NINJA_SEARCH_PROVIDER=perplexity

# Daemon Ports
NINJA_CODER_PORT=8100
NINJA_RESEARCHER_PORT=8101
NINJA_SECRETARY_PORT=8102
NINJA_RESOURCES_PORT=8106
NINJA_PROMPTS_PORT=8107
```

### ~/.claude.json
Claude Code MCP configuration (auto-generated):
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {
        "NINJA_CODE_BIN": "/path/to/opencode",
        "NINJA_MODEL": "anthropic/claude-sonnet-4-5"
      }
    }
  }
}
```

## 🎨 UI Features

All interactive tools use **InquirerPy** for modern CLI experience:

- **Arrow-key navigation** (↑↓) or vim keys (j/k)
- **Type to filter** - Fuzzy search in lists
- **Virtual scrolling** - Handles large lists (100+ models)
- **Custom styling** - Beautiful colors and indicators
- **Keyboard shortcuts** - Enter to select, Ctrl+C to cancel
- **Masked inputs** - API keys hidden as you type
- **Smart defaults** - Sensible defaults pre-selected

## 🚀 Complete Workflow Example

```bash
# 1. Install ninja-mcp
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash

# 2. Run interactive installer
ninja-config install
# Select: Full installation
# Auto-installs: aider, prompts for OpenCode

# 3. Configure API keys
ninja-config auth
# Enter: OpenRouter key, Perplexity key

# 4. Authenticate OpenCode providers (if using OpenCode)
ninja-config configure
# Select: Manage Providers → Anthropic → Follow prompts
# Select: Manage Providers → Google → Follow prompts

# 5. Select operator and model
ninja-config select-model
# Select: OpenCode
# Select: anthropic/claude-sonnet-4-5

# 6. Configure Claude Code
ninja-config setup-claude --all

# 7. Verify everything works
ninja-config doctor

# 8. View final configuration
ninja-config show
```

## 🔧 Troubleshooting

### Command not found
```bash
# Add to PATH
export PATH="$HOME/.local/bin:$PATH"

# Or reinstall
uv tool install --force ninja-mcp[all]
```

### InquirerPy not available
```bash
# Install InquirerPy
pip install InquirerPy

# Or reinstall with all extras
uv tool install --force ninja-mcp[all]
```

### Configuration not persisting
```bash
# Check config file
cat ~/.ninja-mcp.env

# Reset and reconfigure
ninja-config configure
# Select: Reset Configuration → Yes
# Then reconfigure
```

### Models not showing
```bash
# Check operator is installed
which opencode  # or: which aider, which gemini

# Try reloading
ninja-config select-model
# Select operator again
```

## 📚 Documentation

- **Full docs**: https://github.com/angkira/ninja-cli-mcp
- **Model selector**: docs/INTERACTIVE_MODEL_SELECTOR.md
- **OpenCode setup**: docs/OPENCODE_SETUP.md
- **Investigation**: INVESTIGATION_2026-01-26.md

## 🤝 Contributing

All configuration tools use InquirerPy for consistency. When adding new interactive features:

1. Import InquirerPy:
   ```python
   from InquirerPy import inquirer
   from InquirerPy.base.control import Choice
   ```

2. Use consistent patterns:
   ```python
   result = inquirer.select(
       message="Select option:",
       choices=[...],
       pointer="►",
   ).execute()
   ```

3. Handle Ctrl+C gracefully:
   ```python
   try:
       result = inquirer.select(...)
   except KeyboardInterrupt:
       print("\n✗ Cancelled")
       sys.exit(1)
   ```
