# ninja-mcp

[![Tests](https://github.com/angkira/ninja-mcp/actions/workflows/tests.yml/badge.svg)](https://github.com/angkira/ninja-mcp/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](#requirements)

A multi-module MCP (Model Context Protocol) server system for AI-powered development workflows. Ninja MCP consists of three specialized modules:

- **🥷 Coder** - AI code execution and modification
- **🔍 Researcher** - Web search and report generation
- **📋 Secretary** - Codebase exploration and documentation *(coming soon)*

Each module runs as an independent MCP server and can be used standalone or together.

## Table of Contents

- [Architecture](#architecture)
- [Features](#features)
- [Requirements](#requirements)
- [Quick Start](#quick-start)
- [Modules](#modules)
- [Usage](#usage)
- [Configuration](#configuration)
- [Development](#development)
- [Migration from v0.1](#migration-from-v01)
- [Contributing](#contributing)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        IDE / AI Assistant                        │
│              (Claude Code, VS Code, Zed, etc.)                   │
└────────────┬──────────────┬──────────────┬─────────────────────┘
             │              │              │
             │ MCP          │ MCP          │ MCP
             │              │              │
┌────────────▼─────┐ ┌──────▼──────┐ ┌────▼──────────────┐
│  Ninja Coder     │ │  Ninja      │ │  Ninja Secretary  │
│  MCP Server      │ │  Researcher │ │  MCP Server       │
│                  │ │  MCP Server │ │                   │
│  Tools:          │ │             │ │  Tools:           │
│  - quick_task    │ │  Tools:     │ │  - explore_code   │
│  - execute_plan  │ │  - search   │ │  - session_log    │
│  - run_tests     │ │  - research │ │  - manage_docs    │
└────────┬─────────┘ │  - report   │ └────┬──────────────┘
         │           └──────┬──────┘      │
         │                  │             │
┌────────▼──────────────────▼─────────────▼──────────────────────┐
│                    Ninja Common Library                         │
│  - Security  - Metrics  - Logging  - Daemon Management          │
└─────────────────────────────────────────────────────────────────┘
```

## Features

### Coder Module (Available Now)

- 🧠 **Planner/Executor Separation** – MCP planner delegates to AI code CLI
- 🔒 **Scoped Execution** – File access control with glob patterns
- 🔐 **Security** – Rate limiting, input validation, resource monitoring
- 🧩 **Multiple Execution Modes** – Quick tasks, sequential plans, parallel execution
- 🤖 **Multi-CLI Support** – Works with Aider, Claude, Cursor, and more
- 📊 **Metrics Tracking** – Token usage and cost analysis
- 🧪 **Full Test Suite** – 149+ tests

### Researcher Module (Available Now)

- 🔍 **Web Search** – Multiple providers (DuckDuckGo, Serper.dev)
- 📊 **Deep Research** – Multi-query research with parallel agents
- 📝 **Report Generation** – Synthesize sources into comprehensive reports *(coming soon)*
- ✅ **Fact Checking** – Verify claims against sources *(coming soon)*

### Secretary Module (Coming Soon)

- 📂 **Codebase Explorer** – Analyze and summarize large codebases
- 🔎 **Code Search** – Fast grep-like search with tree-sitter
- 📋 **Session Tracking** – Keep protocol of work sessions
- 📚 **Documentation** – Read, update, and generate documentation

## Requirements

- **Python 3.11+**
- **uv** (package manager - auto-installed by quick installer)
- **OpenRouter API key** (for Coder and Researcher)
- (Optional) **Serper API key** (for Researcher - DuckDuckGo is free fallback)
- (Optional) AI Code CLI binary (for Coder - e.g., Aider)

## Quick Start

### One-Line Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash
```

Or with wget:
```bash
wget -qO- https://raw.githubusercontent.com/angkira/ninja-mcp/main/install.sh | bash
```

This interactive installer will:
- ✅ Auto-detect your OS and install dependencies
- ✅ Let you choose installation method (interactive/quick/development)
- ✅ Configure API keys securely
- ✅ Set up IDE integrations (Claude Code, VS Code, Zed)
- ✅ No hardcoded paths - works for everyone!

### Platform-Specific Installation

#### macOS (Homebrew)

```bash
# Once published to Homebrew
brew install angkira/tap/ninja-mcp

# Or install from source
brew install --build-from-source packaging/homebrew/ninja-mcp.rb
```

#### Ubuntu/Debian

```bash
# Once published to PPA
sudo add-apt-repository ppa:angkira/ninja-mcp
sudo apt update
sudo apt install ninja-mcp

# Or install .deb directly
wget https://github.com/angkira/ninja-mcp/releases/latest/download/ninja-mcp_0.2.0_all.deb
sudo dpkg -i ninja-mcp_0.2.0_all.deb
```

#### Arch Linux (AUR)

```bash
# Coming soon
yay -S ninja-mcp
```

### Quick Install (Global Tool)

```bash
# Install from PyPI (once published)
uv tool install ninja-mcp[all]

# Configure
export OPENROUTER_API_KEY='your-key'
ninja-config  # Interactive configuration wizard
```

### Development Installation

```bash
# Clone repository
git clone https://github.com/angkira/ninja-mcp.git
cd ninja-mcp

# Install just (modern task runner)
curl --proto '=https' --tlsv1.2 -sSf https://just.systems/install.sh | bash -s -- --to /usr/local/bin

# Run interactive installer
just install

# Or install manually
uv sync --all-extras

# Available commands
just --list              # Show all commands
just setup-ide           # Configure IDE integration
just test                # Run tests
just daemon-start        # Start all daemons
```

### Using `just` (Modern Task Automation)

Once installed for development, use `just` for common tasks:

```bash
just install             # Interactive installation
just install-dev         # Development setup
just setup-claude-code   # Configure Claude Code
just test                # Run tests
just daemon-start        # Start daemons
just build               # Build package
just build-homebrew      # Build Homebrew formula
just build-deb           # Build Debian package
```

See [`justfile`](justfile) for all available commands.

## Modules

### Coder Module

Delegates code writing tasks to AI code assistants via OpenRouter.

**Tools:**
- `coder_quick_task` - Single-pass code changes
- `coder_execute_plan_sequential` - Multi-step sequential execution
- `coder_execute_plan_parallel` - Parallel execution with fanout
- `coder_run_tests` - Test execution (deprecated)
- `coder_apply_patch` - Patch application (not supported)

**Configuration:**
```bash
export NINJA_CODER_MODEL='anthropic/claude-haiku-4.5-20250929'
export NINJA_CODE_BIN='aider'
export NINJA_CODER_TIMEOUT=600
```

**Usage:**
```bash
# Run directly
ninja-coder

# Or as daemon
ninja-daemon start coder
ninja-daemon status coder
ninja-daemon stop coder
```

See [docs/CODER.md](docs/CODER.md) for detailed documentation.

### Researcher Module

Web search and research report generation.

**Tools:**
- `researcher_web_search` - Search the web (DuckDuckGo or Serper.dev)
- `researcher_deep_research` - Multi-query research with parallel agents
- `researcher_generate_report` - Generate reports *(coming soon)*
- `researcher_fact_check` - Verify claims *(coming soon)*
- `researcher_summarize_sources` - Summarize sources *(coming soon)*

**Configuration:**
```bash
export NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'
export SERPER_API_KEY='your-key'  # Optional
export NINJA_RESEARCHER_MAX_SOURCES=20
export NINJA_RESEARCHER_PARALLEL_AGENTS=4
```

See [docs/RESEARCHER.md](docs/RESEARCHER.md) for detailed documentation.

### Secretary Module *(Coming Soon)*

Codebase exploration and documentation management.

**Tools:**
- `secretary_explore_codebase` - Analyze codebase
- `secretary_find_files` - Find files by pattern
- `secretary_search_code` - Grep-like search
- `secretary_start_session` - Start session tracking
- `secretary_log_event` - Log session events
- `secretary_read_docs` - Read documentation
- `secretary_update_docs` - Update documentation

**Configuration:**
```bash
export NINJA_SECRETARY_MODEL='anthropic/claude-haiku-4.5-20250929'
export NINJA_SECRETARY_MAX_FILE_SIZE=1048576
export NINJA_SECRETARY_CACHE_DIR=~/.cache/ninja-secretary
```

See [docs/SECRETARY.md](docs/SECRETARY.md) for detailed documentation.

## Usage

### Running Modules

#### Direct Execution

```bash
# Run coder module
ninja-coder

# Run researcher module
ninja-researcher

# Run secretary module
ninja-secretary
```

#### Daemon Mode

```bash
# Start daemons
ninja-daemon start coder
ninja-daemon start researcher
ninja-daemon start secretary

# Check status
ninja-daemon status
ninja-daemon status coder

# Stop daemons
ninja-daemon stop coder
ninja-daemon stop researcher
ninja-daemon stop secretary

# Restart
ninja-daemon restart coder
```

### IDE Integration

#### Claude Code

```bash
# Register all modules
claude mcp add --scope user --transport stdio ninja-coder -- ninja-daemon connect coder
claude mcp add --scope user --transport stdio ninja-researcher -- ninja-daemon connect researcher
claude mcp add --scope user --transport stdio ninja-secretary -- ninja-daemon connect secretary

# Verify
claude mcp list
```

#### VS Code

Create or update `~/.config/Code/User/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    },
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    },
    "ninja-secretary": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_secretary.server"]
    }
  }
}
```

#### Zed

Update `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "ninja-coder": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_coder.server"]
    }
  }
}
```

## Configuration

### Environment Variables

| Variable | Module | Required | Default | Description |
|----------|--------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | All | Yes* | - | OpenRouter API key |
| `NINJA_CODER_MODEL` | Coder | No | `anthropic/claude-haiku-4.5-20250929` | Coder model |
| `NINJA_CODE_BIN` | Coder | No | `aider` | AI Code CLI path |
| `NINJA_CODER_TIMEOUT` | Coder | No | `600` | Timeout in seconds |
| `NINJA_RESEARCHER_MODEL` | Researcher | No | `anthropic/claude-sonnet-4` | Researcher model |
| `SERPER_API_KEY` | Researcher | No | - | Serper.dev API key |
| `NINJA_SECRETARY_MODEL` | Secretary | No | `anthropic/claude-haiku-4.5-20250929` | Secretary model |

*At least one of `OPENROUTER_API_KEY` or `OPENAI_API_KEY` must be set.

### Configuration File

All configuration is stored in `~/.ninja-mcp.env`:

```bash
# Load configuration
source ~/.ninja-mcp.env

# View configuration
cat ~/.ninja-mcp.env
```

### Directory Layout

```
~/.cache/ninja-mcp/
├── <repo-hash>-<repo-name>/    # Per-repository cache
│   ├── logs/                   # Execution logs
│   ├── tasks/                  # Task instruction files
│   ├── metadata/               # Additional metadata
│   ├── metrics/                # Task metrics (CSV)
│   └── work/                   # Isolated work directories
├── daemons/                    # Daemon PID and socket files
│   ├── coder.pid
│   ├── coder.sock
│   ├── researcher.pid
│   └── researcher.sock
└── logs/                       # Daemon logs
    ├── coder.log
    ├── researcher.log
    └── secretary.log
```

## Development

### Running Tests

```bash
# All tests
./scripts/dev.sh test

# Module-specific tests
pytest tests/coder/
pytest tests/researcher/
pytest tests/secretary/

# Integration tests
./scripts/run_integration_tests.sh
```

### Code Quality

```bash
# Lint
./scripts/dev.sh lint

# Format
./scripts/dev.sh format

# Type check
./scripts/dev.sh typecheck
```

### Adding a New Module

See [docs/ADDING_MODULES.md](docs/ADDING_MODULES.md) for instructions on adding new modules.

## Migration from v0.1

If you're upgrading from `ninja-cli-mcp` v0.1, see [MIGRATION.md](MIGRATION.md) for detailed migration instructions.

**Quick migration:**

```bash
# Backup old config
cp ~/.ninja-cli-mcp.env ~/.ninja-cli-mcp.env.backup

# Run new installer
./scripts/install_interactive.sh

# Update IDE configs (see MIGRATION.md)
```

**Breaking changes:**
- Tool names now prefixed: `ninja_quick_task` → `coder_quick_task`
- Separate servers for each module
- New configuration structure

**Backward compatibility:**
- Old `ninja-cli-mcp` module still available with `--extra legacy`
- Will be removed in v0.3.0

## Contributing

We welcome contributions! Please read:

- [CONTRIBUTING.md](CONTRIBUTING.md) – Development workflow
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) – Community guidelines
- [ARCHITECTURE.md](ARCHITECTURE.md) – System architecture

## Security

See [SECURITY.md](SECURITY.md) for security policy and vulnerability reporting.

## Documentation

- **[Architecture](ARCHITECTURE.md)** - System architecture and design
- **[Migration Guide](MIGRATION.md)** - Migrating from v0.1 to v0.2
- **[Coder Module](docs/CODER.md)** - Coder module documentation
- **[Researcher Module](docs/RESEARCHER.md)** - Researcher module documentation
- **[Secretary Module](docs/SECRETARY.md)** - Secretary module documentation
- **[MCP Best Practices](docs/MCP_BEST_PRACTICES.md)** - Security and testing
- **[Contributing](CONTRIBUTING.md)** - How to contribute

## License

MIT License - see [LICENSE](LICENSE) for details.

---

## Legacy Support (v0.1)

The old `ninja-cli-mcp` module is still available for backward compatibility:

```bash
# Install legacy support
uv sync --extra legacy

# Run old server
python -m ninja_cli_mcp.server
```

**Note:** Legacy support will be removed in v0.3.0. Please migrate to the new multi-module architecture.

See [MIGRATION.md](MIGRATION.md) for migration instructions.
