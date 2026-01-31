# 🥷 Ninja MCP TUI Installer

The Advanced TUI (Text User Interface) Installer provides a comprehensive setup experience for Ninja MCP with all configuration options in a single interactive session.

## 🚀 Quick Start

```bash
# Run the advanced TUI installer
ninja-config tui-install
```

## 🎯 Features

### Comprehensive Setup
- **Installation Type Selection**: Full, Minimal, or Custom module selection
- **Module Selection**: Choose specific modules to install (coder, researcher, secretary, resources, prompts)
- **API Key Collection**: Securely collect all required API keys in one session
- **Model Selection**: Interactive model selection with recommendations for each module
- **AI Code CLI Selection**: Choose your preferred AI coding assistant (aider, opencode, gemini, cursor)
- **Daemon Configuration**: Enable/disable daemon mode for background services
- **IDE Integration**: Configure multiple IDEs (Claude Code, VS Code, Zed, OpenCode) in one step

### Key Collection
The TUI installer collects all required API keys:
- **OpenRouter API Key** (primary) - Required for most AI features
- **Serper.dev API Key** (optional) - For Google Search integration
- **Perplexity API Key** (optional) - For AI-powered search
- **Google API Key** (optional) - For native Gemini integration

### Model Selection
Interactive model selection with live recommendations from LiveBench benchmarks:
- **Coder Module**: Models optimized for code generation and editing
- **Researcher Module**: Models optimized for web research and synthesis
- **Secretary Module**: Models optimized for documentation and analysis

### IDE Integration
Configure multiple IDEs in a single session:
- **Claude Code** - Automatic MCP server registration
- **VS Code** - Configuration file updates
- **Zed** - Context server integration
- **OpenCode** - MCP server registration

## 📋 Usage

### Run the TUI Installer
```bash
# Run the advanced TUI installer
ninja-config tui-install
```

### Installation Types
1. **Full Installation**: All modules with advanced features
2. **Minimal Installation**: Core modules only (coder, resources)
3. **Custom Installation**: Select specific modules

### Module Selection
Choose which Ninja MCP modules to install:
- **🤖 Coder**: AI code assistant with Aider/OpenCode/Gemini support
- **🔍 Researcher**: Web research with DuckDuckGo/Perplexity
- **📝 Secretary**: File operations and codebase analysis
- **📚 Resources**: Resource templates and prompts
- **💡 Prompts**: Prompt management and chaining

### API Key Management
The installer securely collects and stores API keys in `~/.ninja-mcp.env`:
```bash
# Example configuration file
export OPENROUTER_API_KEY="sk-or-..."
export NINJA_SEARCH_PROVIDER="serper"
export SERPER_API_KEY="..."
export GOOGLE_API_KEY="..."  # Optional for Gemini
```

### Model Selection Process
1. **LiveBench Recommendations**: Fetches latest model benchmarks
2. **Price/Performance Trade-offs**: Shows cost and speed information
3. **Custom Model Support**: Enter any model name for advanced users

### AI Code CLI Selection
Choose your preferred AI coding assistant:
- **Aider** - OpenRouter integration (installed automatically)
- **OpenCode** - Multi-provider CLI (manual installation)
- **Gemini CLI** - Google models (manual installation)
- **Cursor** - IDE with AI (manual installation)
- **Custom Path** - Enter path to any AI coding assistant

## ⚙️ Configuration Options

### Daemon Mode
Enable daemon mode for better performance:
- **Background Services**: Modules run as persistent background processes
- **Faster Response**: No startup delay for subsequent requests
- **Resource Management**: Automatic process lifecycle management

### IDE Configuration
Configure multiple IDEs simultaneously:
- **Automatic Registration**: One-click setup for supported IDEs
- **Config File Updates**: Direct modification of IDE configuration files
- **Verification**: Confirm successful integration

## 🛠️ Technical Details

### Requirements
- **Python 3.11+**
- **uv package manager**
- **InquirerPy** for TUI interface
- **Internet connection** for API key validation

### Configuration Storage
- **File**: `~/.ninja-mcp.env`
- **Permissions**: 600 (read/write for owner only)
- **Format**: Standard shell environment variables

### Installation Process
1. **System Detection**: OS, architecture, shell
2. **Dependency Check**: Python, uv, required tools
3. **Module Installation**: ninja-mcp with selected extras
4. **Tool Installation**: aider, opencode, etc.
5. **Configuration Collection**: API keys, models, preferences
6. **IDE Integration**: Automatic configuration
7. **Verification**: Component testing and validation

## 🤖 Advanced Usage

### Custom Model Selection
Enter any model name supported by your provider:
```bash
# Examples
anthropic/claude-opus-4
openai/gpt-4o
google/gemini-2.0-flash-exp
qwen/qwen-2.5-coder-32b-instruct
```

### Environment Variables
The installer respects existing environment variables:
```bash
# Pre-set API keys are detected automatically
export OPENROUTER_API_KEY="sk-or-..."
ninja-config tui-install
```

### Non-Interactive Mode
For automated deployments, use the standard installer:
```bash
# Standard installer with basic prompts
ninja-config install
```

## 📚 See Also

- [Model Selection Guide](MODEL_SELECTION.md)
- [API Key Management](API_KEYS.md)
- [IDE Integration](IDE_INTEGRATION.md)
- [Configuration Reference](CONFIGURATION.md)