# ⚡ Ninja MCP Power Configurator

The Power Configurator is an advanced TUI (Text User Interface) tool that provides comprehensive configuration management for Ninja MCP with an intuitive, interactive experience.

## 🚀 Quick Start

```bash
# Run the powerful interactive configurator
ninja-config power-configure
```

## 🎯 Key Features

### Comprehensive Configuration Management
- **Configuration Overview**: See all settings at a glance with categorized views
- **API Key Management**: Securely manage all service API keys in one place
- **Operator Configuration**: Choose and configure AI coding assistants
- **Model Selection**: Set models for each module with validation
- **Search Provider Setup**: Configure web search capabilities
- **Daemon Settings**: Fine-tune performance and port configurations
- **IDE Integration**: Connect to multiple IDEs and editors
- **Advanced Settings**: Edit any configuration value directly

### Interactive Experience
- **Rich TUI Interface**: Modern, intuitive text-based interface
- **Context-Aware Navigation**: Smart menu organization based on current configuration
- **Real-Time Status**: Live system status and configuration validation
- **Step-by-Step Guidance**: Clear instructions for each configuration task
- **Safety Confirmation**: Protected actions with confirmation prompts

## 📋 Configuration Categories

### 🔑 API Key Management
Securely manage API keys for all supported services:
- **OpenRouter** - Primary API key for most AI features
- **Anthropic** - Direct Claude model access
- **OpenAI** - Direct GPT model access
- **Google** - Direct Gemini model access
- **Perplexity** - AI-powered research capabilities
- **Serper** - Google Search API integration

### 🎯 Operator Configuration
Choose your preferred AI coding assistant:
- **Aider** - OpenRouter-based CLI with excellent code editing
- **OpenCode** - Multi-provider CLI supporting 75+ models
- **Gemini CLI** - Native Google Gemini integration
- **Cursor** - IDE with built-in AI capabilities

### 🤖 Model Selection
Configure models for each Ninja MCP module:
- **Coder Module**: AI code assistant for writing and editing
- **Researcher Module**: Web research and information gathering
- **Secretary Module**: Documentation and codebase analysis
- **Resources Module**: Project context and template management
- **Prompts Module**: Workflow and prompt management

### 🔍 Search Provider
Configure web search capabilities for the Researcher module:
- **DuckDuckGo** - Free, no API key required (default)
- **Serper/Google** - Google Search API with better results
- **Perplexity AI** - AI-powered search with highest quality

### ⚙️ Daemon Settings
Optimize performance with daemon configuration:
- **Enable/Disable Daemon Mode**: Background service management
- **Port Configuration**: Custom port assignments for each module
- **Performance Tuning**: Resource allocation and optimization

### 🖥️ IDE Integration
Connect Ninja MCP to your favorite editors:
- **Claude Code** - Automatic MCP server registration
- **VS Code** - Manual configuration support
- **Zed** - Context server integration
- **OpenCode** - MCP server registration

### 🌐 OpenCode Authentication
Manage provider credentials for OpenCode:
- **Anthropic/Claude** - Direct Claude authentication
- **Google/Gemini** - Native Gemini integration
- **OpenAI/GPT** - Direct GPT model access
- **GitHub Copilot** - GitHub Copilot integration

### 🔧 Advanced Settings
Fine-tune all configuration options:
- **Direct Setting Edit**: Modify any configuration value
- **Configuration Pagination**: Navigate large configuration sets
- **System Status**: View daemon and tool status
- **Reset Configuration**: Clear all settings when needed

## 🎛️ Usage

### Run Power Configurator
```bash
# Run the powerful interactive configurator
ninja-config power-configure
```

### Navigation
1. **Main Menu**: Choose configuration category
2. **Category View**: See current settings and options
3. **Action Selection**: Choose specific configuration task
4. **Value Input**: Enter new values with validation
5. **Confirmation**: Review and confirm changes

### Configuration Workflow
1. **Overview**: Start with configuration overview to assess current state
2. **API Keys**: Set up required service credentials
3. **Operators**: Choose your preferred AI coding assistant
4. **Models**: Configure models for each module
5. **Search**: Set up web search capabilities
6. **Daemon**: Optimize performance settings
7. **IDE**: Connect to your preferred editors
8. **Advanced**: Fine-tune any additional settings

## 🛠️ Technical Details

### Requirements
- **InquirerPy** for rich TUI interface
- **Python 3.11+** for full compatibility
- **Internet connection** for API key validation

### Configuration Storage
- **File**: `~/.ninja-mcp.env`
- **Format**: Standard shell environment variables
- **Permissions**: 600 (read/write for owner only)
- **Backup**: Automatic preservation of existing settings

### Security Features
- **Key Masking**: API keys displayed as masked values
- **Secure Input**: Hidden password-style entry for sensitive data
- **File Permissions**: Automatic 600 permissions for config file
- **Validation**: Real-time validation of entered values

## 🤖 Advanced Usage

### Direct Setting Edit
Edit any configuration value directly:
```bash
# Navigate to Advanced Settings → Edit Setting
# Select any configuration key and modify its value
```

### Configuration Reset
Clear all configuration when needed:
```bash
# Navigate to Main Menu → Reset Configuration
# Confirm deletion of all settings
```

### System Status Monitoring
View real-time system status:
- **Daemon Status**: Running/stopped state
- **Tool Detection**: Installed operator detection
- **Authentication Status**: Provider authentication verification
- **Port Availability**: Network port status

## 📚 See Also

- [TUI Installer](TUI_INSTALLER.md)
- [Model Selection Guide](MODEL_SELECTION.md)
- [API Key Management](API_KEYS.md)
- [IDE Integration](IDE_INTEGRATION.md)
- [Configuration Reference](CONFIGURATION.md)