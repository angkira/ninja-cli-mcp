# Editor Integrations Guide

This guide explains how to integrate Ninja MCP modules with various editors and IDEs that support the Model Context Protocol (MCP).

## Supported Editors

| Editor | Status | Auto-Install | Notes |
|--------|--------|--------------|-------|
| **Claude Code** | ✅ Full Support | ✅ Yes | Native MCP support |
| **Zed** | ✅ Full Support | ✅ Yes | Context servers support |
| **VS Code (Cline)** | ✅ Full Support | ✅ Yes | Via Cline extension |
| **Cursor** | 🔄 Planned | ❌ No | Manual config needed |
| **VS Code (Copilot)** | 🔄 Planned | ❌ No | Waiting for native MCP |

## Quick Start

### Automatic Installation

The easiest way to configure editor integrations is through the interactive installer:

```bash
cd /path/to/ninja-cli-mcp
./scripts/install_interactive.sh
```

The installer will:
1. Detect installed editors automatically
2. Ask which editors you want to configure
3. Create proper configuration files
4. Set up environment variables
5. Backup existing configurations

### Manual Installation

If you prefer manual setup or need to reconfigure, follow the editor-specific guides below.

---

## Claude Code Integration

### Automatic Setup

```bash
./scripts/install_interactive.sh
# Select modules and choose "Register with Claude Code" when prompted
```

### Manual Setup

1. **Create MCP configuration directory:**
   ```bash
   mkdir -p ~/.config/claude
   ```

2. **Create or edit `~/.config/claude/mcp.json`:**
   ```json
   {
     "mcpServers": {
       "ninja-coder": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_coder.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929",
           "NINJA_CODE_BIN": "aider"
         }
       },
       "ninja-researcher": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_researcher.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_RESEARCHER_MODEL": "anthropic/claude-sonnet-4"
         }
       },
       "ninja-secretary": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_secretary.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_SECRETARY_MODEL": "anthropic/claude-haiku-4.5-20250929"
         }
       }
     }
   }
   ```

3. **Restart Claude Code:**
   ```bash
   # The changes will be picked up on next launch
   claude
   ```

4. **Verify installation:**
   - Open Claude Code
   - Type `/mcp` to list available MCP servers
   - You should see: `ninja-coder`, `ninja-researcher`, `ninja-secretary`

### Usage in Claude Code

```
# List available tools
/mcp list

# Use Coder module
Please use ninja_coder to implement user authentication

# Use Researcher module
Use researcher_web_search to find information about Python asyncio

# Use Secretary module
Use secretary_file_tree to show me the project structure
```

---

## Zed Editor Integration

### Automatic Setup

```bash
./scripts/install_interactive.sh
# Select modules and choose "Register with Zed" when prompted
```

### Manual Setup

1. **Open Zed settings:**
   ```bash
   # Edit settings directly
   vim ~/.config/zed/settings.json

   # Or open in Zed
   zed ~/.config/zed/settings.json
   ```

2. **Add context servers to your settings:**
   ```json
   {
     "context_servers": {
       "ninja-coder": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_coder.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929",
           "NINJA_CODE_BIN": "aider"
         }
       },
       "ninja-researcher": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_researcher.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_RESEARCHER_MODEL": "anthropic/claude-sonnet-4",
           "SERPER_API_KEY": "your-serper-key-here"
         }
       },
       "ninja-secretary": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_secretary.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_SECRETARY_MODEL": "anthropic/claude-haiku-4.5-20250929"
         }
       }
     },
     "assistant": {
       "version": "2",
       "default_model": {
         "provider": "anthropic",
         "model": "claude-sonnet-4"
       }
     }
   }
   ```

3. **Restart Zed:**
   - Quit Zed completely (Cmd+Q on Mac)
   - Reopen Zed
   - The context servers will be loaded automatically

4. **Verify installation:**
   - Open Zed Assistant (Cmd+Shift+A)
   - The assistant should have access to ninja tools
   - Try asking: "What tools are available?"

### Usage in Zed

```
# In the Zed Assistant panel:

"Please implement a login feature using the coder tool"

"Search for information about TypeScript best practices"

"Show me the file structure of this project"
```

---

## VS Code Integration (via Cline)

Cline is a VS Code extension that provides MCP support and AI coding assistance.

### Prerequisites

1. **Install VS Code:**
   - Download from: https://code.visualstudio.com/

2. **Install Cline extension:**
   - Open VS Code
   - Go to Extensions (Cmd+Shift+X)
   - Search for "Cline" or "roo-cline"
   - Click Install
   - Or install directly: https://marketplace.visualstudio.com/items?itemName=rooveterinaryinc.roo-cline

### Automatic Setup

```bash
./scripts/install_interactive.sh
# Select modules and choose "Register with VS Code (Cline)" when prompted
```

### Manual Setup

1. **Locate Cline settings directory:**

   **macOS:**
   ```bash
   ~/Library/Application Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/
   ```

   **Linux:**
   ```bash
   ~/.config/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/
   ```

   **Windows:**
   ```
   %APPDATA%\Code\User\globalStorage\rooveterinaryinc.roo-cline\settings\
   ```

2. **Create or edit `cline_mcp_settings.json`:**
   ```json
   {
     "mcpServers": {
       "ninja-coder": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_coder.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_CODER_MODEL": "anthropic/claude-haiku-4.5-20250929",
           "NINJA_CODE_BIN": "aider"
         }
       },
       "ninja-researcher": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_researcher.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_RESEARCHER_MODEL": "anthropic/claude-sonnet-4"
         }
       },
       "ninja-secretary": {
         "command": "uv",
         "args": ["--directory", "/path/to/ninja-cli-mcp", "run", "python", "-m", "ninja_secretary.server"],
         "env": {
           "OPENROUTER_API_KEY": "your-key-here",
           "NINJA_SECRETARY_MODEL": "anthropic/claude-haiku-4.5-20250929"
         }
       }
     }
   }
   ```

3. **Restart VS Code:**
   - Quit VS Code completely
   - Reopen VS Code
   - Open Cline panel (Cmd+Shift+P → "Cline: Open")

4. **Verify installation:**
   - Open Cline sidebar
   - The MCP servers should connect automatically
   - Check status in Cline settings

### Usage in VS Code (Cline)

1. **Open Cline panel:**
   - Click Cline icon in sidebar
   - Or: Cmd+Shift+P → "Cline: Open"

2. **Use the tools:**
   ```
   "Use the coder tool to add user authentication"

   "Search for React hooks best practices using researcher"

   "Show me the project structure using secretary"
   ```

3. **Monitor tool usage:**
   - Cline will show which MCP tools it's calling
   - Tool outputs appear in the chat
   - Files modified by coder will be shown in the diff view

---

## Configuration Options

### Environment Variables

All modules support these environment variables:

#### Common Variables
```bash
# OpenRouter API Key (required for all modules)
OPENROUTER_API_KEY="sk-or-..."

# Alternative: Use OpenAI API key
OPENAI_API_KEY="sk-..."
```

#### Coder Module
```bash
# Model for code generation
NINJA_CODER_MODEL="anthropic/claude-haiku-4.5-20250929"

# Path to AI code CLI (aider, cursor, etc.)
NINJA_CODE_BIN="aider"

# Execution timeout (seconds)
NINJA_CODER_TIMEOUT=600
```

#### Researcher Module
```bash
# Model for research synthesis
NINJA_RESEARCHER_MODEL="anthropic/claude-sonnet-4"

# Serper.dev API key (optional - DuckDuckGo fallback)
SERPER_API_KEY="your-serper-key"

# Max sources per research
NINJA_RESEARCHER_MAX_SOURCES=20

# Parallel research agents
NINJA_RESEARCHER_PARALLEL_AGENTS=4
```

#### Secretary Module
```bash
# Model for summarization
NINJA_SECRETARY_MODEL="anthropic/claude-haiku-4.5-20250929"

# Max file size to analyze (bytes)
NINJA_SECRETARY_MAX_FILE_SIZE=1048576

# Cache directory
NINJA_SECRETARY_CACHE_DIR="~/.cache/ninja-secretary"
```

### Model Selection

**Recommended models by use case:**

| Use Case | Recommended Model | Reason |
|----------|------------------|--------|
| **Fast code generation** | `anthropic/claude-haiku-4.5-20250929` | Fastest, cost-effective |
| **Complex code** | `anthropic/claude-sonnet-4` | Best reasoning |
| **Research synthesis** | `anthropic/claude-sonnet-4` | Best comprehension |
| **Quick summaries** | `anthropic/claude-haiku-4.5-20250929` | Fast, good enough |
| **Free tier** | `qwen/qwen3-coder` | Free on OpenRouter |

---

## Troubleshooting

### MCP Servers Not Showing Up

**Claude Code:**
```bash
# Check config syntax
cat ~/.config/claude/mcp.json | python -m json.tool

# Check logs
tail -f ~/.config/claude/logs/mcp.log
```

**Zed:**
```bash
# Check config syntax
cat ~/.config/zed/settings.json | python -m json.tool

# View Zed logs
# In Zed: View → Toggle Debug Info
```

**VS Code (Cline):**
```bash
# Check config syntax
cat ~/Library/Application\ Support/Code/User/globalStorage/rooveterinaryinc.roo-cline/settings/cline_mcp_settings.json | python -m json.tool

# View Cline logs
# In VS Code: Output panel → Select "Cline" from dropdown
```

### Connection Errors

1. **Check Python/uv installation:**
   ```bash
   which python3
   which uv
   uv --version
   ```

2. **Test MCP server manually:**
   ```bash
   cd /path/to/ninja-cli-mcp
   source ~/.ninja-mcp.env
   uv run python -m ninja_coder.server
   # Should output: {"jsonrpc":"2.0",...}
   ```

3. **Check environment variables:**
   ```bash
   source ~/.ninja-mcp.env
   echo $OPENROUTER_API_KEY
   echo $NINJA_CODER_MODEL
   ```

### Tools Not Working

1. **Check API key:**
   ```bash
   # Test OpenRouter API
   curl https://openrouter.ai/api/v1/models \
     -H "Authorization: Bearer $OPENROUTER_API_KEY"
   ```

2. **Check rate limits:**
   - All modules have built-in rate balancing
   - Check logs for rate limit messages
   - Wait and retry

3. **Enable debug logging:**
   ```bash
   export NINJA_LOG_LEVEL=DEBUG
   ```

### Path Issues

If you get "command not found" errors:

1. **Use absolute paths:**
   ```json
   {
     "command": "/Users/you/.cargo/bin/uv",
     "args": ["--directory", "/Users/you/projects/ninja-cli-mcp", ...]
   }
   ```

2. **Check uv installation:**
   ```bash
   which uv
   # Add to PATH if needed:
   export PATH="$HOME/.cargo/bin:$PATH"
   ```

---

## Advanced Configuration

### Per-Project Settings

You can override global settings per project:

**Create `.ninja-mcp.env` in project root:**
```bash
# Project-specific configuration
export NINJA_CODER_MODEL="anthropic/claude-sonnet-4"
export NINJA_RESEARCHER_MAX_SOURCES=50
```

**Update editor config to use project env:**
```json
{
  "command": "bash",
  "args": ["-c", "source .ninja-mcp.env && uv run python -m ninja_coder.server"]
}
```

### Multiple API Keys

Use different API keys for different modules:

```json
{
  "ninja-coder": {
    "env": {
      "OPENROUTER_API_KEY": "sk-or-coder-key"
    }
  },
  "ninja-researcher": {
    "env": {
      "OPENROUTER_API_KEY": "sk-or-researcher-key"
    }
  }
}
```

### Custom Search Providers

**Add Tavily for Researcher:**
```bash
export TAVILY_API_KEY="your-tavily-key"
```

**Configure in settings:**
```json
{
  "ninja-researcher": {
    "env": {
      "TAVILY_API_KEY": "your-tavily-key"
    }
  }
}
```

### Logging Configuration

**Enable detailed logging:**
```json
{
  "ninja-coder": {
    "env": {
      "NINJA_LOG_LEVEL": "DEBUG",
      "NINJA_LOG_FILE": "/tmp/ninja-coder.log"
    }
  }
}
```

---

## Security Best Practices

### 1. Protect API Keys

**Never commit API keys to git:**
```bash
# Add to .gitignore
echo ".ninja-mcp.env" >> .gitignore
echo "**/cline_mcp_settings.json" >> .gitignore
```

**Use environment variables:**
```bash
# Store in shell profile
echo 'export OPENROUTER_API_KEY="sk-or-..."' >> ~/.zshrc
```

### 2. File Permissions

**Restrict config file access:**
```bash
chmod 600 ~/.ninja-mcp.env
chmod 600 ~/.config/claude/mcp.json
chmod 600 ~/.config/zed/settings.json
```

### 3. Rate Limiting

All modules have built-in rate limiting:
- Prevents API abuse
- Automatic retry with exponential backoff
- Configurable limits per tool

### 4. Sandboxing

**For Coder module, use restricted mode:**
```json
{
  "env": {
    "NINJA_CODER_SAFE_MODE": "true",
    "NINJA_CODER_ALLOWED_PATHS": "/path/to/project"
  }
}
```

---

## Updating Configuration

### After Updating Ninja MCP

```bash
cd /path/to/ninja-cli-mcp
git pull
uv sync --all-extras

# Rerun installer to update editor configs
./scripts/install_interactive.sh
```

### Switching Models

**Update config file:**
```bash
# Edit environment
vim ~/.ninja-mcp.env

# Change model
NINJA_CODER_MODEL="anthropic/claude-sonnet-4"
```

**Or update editor config directly:**
```json
{
  "env": {
    "NINJA_CODER_MODEL": "anthropic/claude-sonnet-4"
  }
}
```

**Restart editor** to apply changes.

---

## FAQ

**Q: Can I use multiple editors at the same time?**
A: Yes! Each editor runs its own MCP server instance.

**Q: Do I need internet connection?**
A: Yes, for API calls to OpenRouter and search providers.

**Q: What's the cost?**
A: Depends on usage and models. Haiku is ~$0.25 per 1M tokens, Sonnet is ~$3 per 1M tokens.

**Q: Can I use local models?**
A: Yes! Use Ollama with OpenRouter-compatible endpoint or configure directly.

**Q: How do I uninstall?**
A: Remove the config files:
```bash
rm ~/.config/claude/mcp.json
rm ~/.config/zed/settings.json
rm ~/Library/Application\ Support/Code/.../cline_mcp_settings.json
rm ~/.ninja-mcp.env
```

**Q: Can I contribute new editor integrations?**
A: Yes! See [CONTRIBUTING.md](../CONTRIBUTING.md) for guidelines.

---

## Getting Help

- **Documentation**: [docs/](.)
- **Issues**: https://github.com/your-org/ninja-cli-mcp/issues
- **Discussions**: https://github.com/your-org/ninja-cli-mcp/discussions

---

*Last updated: December 25, 2024*
