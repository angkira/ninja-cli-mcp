# 🥷 Ninja MCP - Your AI Development Swiss Knife

[![CI](https://github.com/angkira/ninja-cli-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/angkira/ninja-cli-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12%20%7C%203.13-blue)](#requirements)
[![Tests](https://img.shields.io/badge/tests-400%2B%20passing-brightgreen)](#)
[![Coverage](https://img.shields.io/badge/MCP%20Modules-5%20Ready-blue)](#modules)

> **The complete MCP toolkit for AI-powered development.** Write code, research anything, explore codebases, and manage projects—all from your favorite AI assistant.

---

## Why Ninja MCP? 🎯

**Stop context-switching. Start shipping.** Ninja MCP is a unified development platform that gives Claude, ChatGPT, and other AI assistants **superpowers** to:

- 💻 **Write & modify code** with AI agents (via Aider, OpenRouter)
- 🔍 **Research topics** with web search and report generation
- 📂 **Understand projects** instantly with codebase analysis
- ⚡ **Generate prompts** and build workflows with reusable templates
- 🗂️ **Manage context** across large projects effortlessly
- 🚀 **Automate workflows** with composable, chainable tools

**One install. Five modules. Unlimited possibilities.**

---

## 📊 What You Get

| Feature | Status | Capability |
|---------|--------|-----------|
| **🥷 Coder** | ✅ Ready | AI code execution, multi-step planning, parallel tasks |
| **🔍 Researcher** | ✅ Ready | Web search, deep research, report generation |
| **📋 Secretary** | ✅ Ready | Codebase analysis, git management, documentation |
| **🧠 Resources** | ✅ Ready | Project context loading, config/docs parsing, caching |
| **✨ Prompts** | ✅ Ready | Reusable templates, AI suggestions, workflow chains |

### 🚀 New in v2.0: Ninja Coder Refactored

Ninja Coder 2.0 introduces a **major architecture overhaul** with dramatic performance improvements:

- **47% faster** sequential execution (15m → 8m)
- **50% faster** parallel execution (20m → 10m)
- **67% memory reduction** (450 MB → 150 MB)
- **100% stability** (vs 67% before - zero hangs!)

**Key Changes:**
- Single-process execution (vs multi-process orchestration)
- Prompt-based control (AI handles sequencing)
- Structured JSON output (reliable parsing)
- Zero session management complexity

See [REFACTORING_SUMMARY.md](./docs/coder/REFACTORING_SUMMARY.md) for details.

---

## Quick Look

### Use Ninja Coder to Write Code

```python
# Tell Claude what to do
"Create a Python API endpoint that validates emails with regex and stores them in SQLite"

# Ninja does it automatically
# ✅ Creates /api/users.py with validation
# ✅ Sets up database schema
# ✅ Adds error handling & tests
```

### Use Ninja Researcher to Find Answers

```python
# Ask Claude complex questions
"Research the latest AI advancements in 2026 and compare different approaches"

# Ninja searches the web, gathers sources, generates a report
# ✅ 20+ sources analyzed
# ✅ Structured report generated
# ✅ Fact-checked and deduplicated
```

### Use Ninja Secretary to Understand Code

```python
# Let Claude explore your project
"Analyze the authentication system in this project"

# Ninja loads structure, functions, imports, config
# ✅ Project context in seconds
# ✅ Git history available
# ✅ Documentation indexed
```

### Use Ninja Resources for Context

```python
# Give Claude the full project picture
resource_codebase()  # → File structure + functions/classes
resource_config()    # → Configs with secrets redacted ✓
resource_docs()      # → Markdown files parsed into sections
```

### Use Ninja Prompts for Workflows

```python
# Build multi-step AI workflows
prompt_chain([
    "design-architecture",      # Step 1: Design
    "implement-feature",        # Step 2: Code (uses Step 1 output)
    "write-tests",             # Step 3: Test (uses Step 2 output)
    "generate-docs"            # Step 4: Document
])
```

---

## 🚀 Installation

Choose your preferred installation method:

### One-Line Install (Recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```

**What happens:**
- ✅ Detects your OS (macOS/Linux/Windows)
- ✅ Installs dependencies (Python, Aider, etc.)
- ✅ Collects all API keys interactively
- ✅ Configures default models for all modules
- ✅ Sets up daemon mode for better performance
- ✅ Integrates with Claude Code / VS Code / Zed
- ✅ Ready to use in 2 minutes

### Advanced TUI Installer

For a more comprehensive setup experience, use the new TUI (Text User Interface) installer:

```bash
# Run the advanced TUI installer
ninja-config tui-install
```

**Features:**
- 🎯 Interactive module selection (coder, researcher, secretary, resources, prompts)
- 🔑 Secure API key collection for all services (OpenRouter, Serper, Perplexity, Google)
- 🤖 Model selection with LiveBench recommendations
- 💻 AI Code CLI selection (Aider, OpenCode, Gemini, Cursor)
- ⚙️ Daemon configuration for background services
- 🖥️ Multi-IDE integration setup (Claude Code, VS Code, Zed, OpenCode)
- 📋 Comprehensive configuration generation

[→ TUI Installer Documentation](docs/TUI_INSTALLER.md)

### Installation Modes

#### Standard Install (Recommended)
```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```

#### Non-Interactive Install (CI/Scripts)
```bash
OPENROUTER_API_KEY='your-key' curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash -s -- --auto
```

#### Full Install (Installs all dependencies automatically)
```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash -s -- --full
```

**Environment variables supported:**
- `OPENROUTER_API_KEY` - Primary API key for AI models
- `SERPER_API_KEY` - For Google Search integration
- `PERPLEXITY_API_KEY` - For AI-powered search
- `GOOGLE_API_KEY` - For native Gemini integration

### Update (Automatic Migration)

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/update.sh | bash
```

**Intelligent configuration migration:**
- ✅ Searches old configs in 10+ locations
- ✅ Preserves API keys, models, providers, ports
- ✅ Migrates old variable names to new format
- ✅ Creates timestamped backups
- ✅ Zero configuration loss guaranteed

**Migrates from:**
- Legacy config files (`~/.config/ninja/*`, etc.)
- Shell RC files (`.bashrc`, `.zshrc`)
- Environment variables
- Old variable names (`OPENAI_API_KEY` → `OPENROUTER_API_KEY`)

[→ Migration Guide](MIGRATION.md)

### Development Setup

```bash
git clone https://github.com/angkira/ninja-cli-mcp.git
cd ninja-cli-mcp
uv sync --all-extras
just install
```

---

## 📦 Modules Deep Dive

### 🥷 Coder Module - AI Code Assistant

**Delegate code writing to AI agents with full control and safety.**

```bash
# Simple single-file tasks
coder_simple_task("Create a login form component with email validation")

# Complex multi-step projects
coder_execute_plan_sequential([
    "Design database schema",
    "Implement API endpoints",
    "Write integration tests",
    "Generate API documentation"
])

# Parallel independent tasks
coder_execute_plan_parallel([
    "Build frontend components",
    "Build backend APIs",
    "Set up CI/CD",
    "Configure monitoring"
], fanout=4)
```

**Features:**
- 🎯 Simple specification-based execution
- 📋 Multi-step sequential planning
- ⚡ Parallel execution with fanout control
- 🔒 File-level access control via glob patterns
- 💾 Token usage tracking & cost analysis
- 🧪 150+ tests (unit, integration, evaluation)

**Supports:** Aider, Claude, Cursor, and any OpenRouter-compatible AI

[→ Full Coder Documentation](docs/CODER.md)

---

### 🔍 Researcher Module - Web Intelligence

**Research anything. Generate comprehensive reports. Verify facts.**

```bash
# Single search query
researcher_web_search("latest AI breakthroughs in 2026")
# → Results from multiple providers (DuckDuckGo, Serper, Perplexity)

# Deep multi-query research
researcher_deep_research(
    topic="AI agent frameworks",
    queries=[
        "Best AI agent architectures 2026",
        "CrewAI vs AutoGen vs LangChain comparison",
        "Building autonomous agents",
        "Agent orchestration patterns"
    ],
    max_sources=30
)
# → Aggregated, deduplicated, synthesized report

# Fact-check claims
researcher_fact_check("Claude 3 has 200K token context window")
# → Verdict with confidence score and sources
```

**Features:**
- 🌐 Multi-provider web search (DuckDuckGo, Serper.dev, Perplexity)
- 🔄 Parallel multi-query research with intelligent agents
- 📊 Report generation with sources
- ✅ Fact-checking with confidence scores
- 📝 Source summarization & deduplication

[→ Full Researcher Documentation](docs/RESEARCHER.md)

---

### 📋 Secretary Module - Codebase Intelligence

**Instantly understand any codebase. Manage documentation. Track changes.**

```bash
# Analyze a file with AI
secretary_analyse_file("src/main.py")
# → Summary + structure (functions/classes/imports) + preview

# Search code
secretary_file_search("src/**/*.py", "auth.*class")

# Get codebase report
secretary_codebase_report("/repo")
# → Structure, metrics, dependencies

# Git operations
secretary_git_status("/repo")                    # Current branch, staged/unstaged files
secretary_git_diff("/repo", since="1 hour ago") # Recent changes
secretary_git_log("/repo", limit=50)            # Commit history
secretary_git_commit("/repo", message=msg)      # Smart commit suggestions

# Documentation management
secretary_document_summary("docs/")
secretary_update_documentation("docs/API.md", content)

# Session tracking
secretary_start_session("/repo")
secretary_log_event("Implemented authentication")
session_report = secretary_get_session_report()
```

**Features:**
- 🎯 Unified file analysis (content + structure + search)
- 📊 Codebase metrics & dependency graphs
- 🌳 Project structure visualization
- 🔧 Git integration (status, diff, log, commits)
- 📚 Documentation indexing & management
- 📝 Session tracking for work logs
- ⚡ 400+ tests (unit, integration, evaluation)

[→ Full Secretary Documentation](docs/SECRETARY.md)

---

### 🧠 Resources Module - Project Context

**Load your entire project as queryable, cached resources.**

```bash
# Load codebase structure + analysis
resource_codebase(
    repo_root="/project",
    include_patterns=["**/*.py"],
    max_files=1000
)
# → Files, functions, classes, structure, metrics

# Load configs (with security redaction)
resource_config(
    repo_root="/project",
    include=[".env.example", "config.yaml"]
)
# → All passwords/tokens automatically become ***REDACTED***

# Load documentation
resource_docs(
    repo_root="/project",
    doc_patterns=["**/*.md", "docs/**"]
)
# → Markdown parsed into sections with hierarchy
```

**Features:**
- 🚀 Smart caching (1-hour TTL, 50x faster on repeats)
- 🔒 Automatic security redaction (passwords, API keys, tokens)
- 📂 File structure analysis & extraction
- 🎯 Pattern-based inclusion/exclusion
- 📊 Metrics & statistics
- ⚙️ Structured response format

[→ Full Resources Documentation](docs/RESOURCES_API.md)

---

### ✨ Prompts Module - AI Workflow Engine

**Build intelligent, composable prompt workflows.**

```bash
# List available prompts
prompts = prompt_registry(action="list")

# Get AI suggestions for your task
suggestions = prompt_suggest(
    context={
        "task": "code-review",
        "language": "python",
        "file_type": "api"
    },
    max_suggestions=5
)
# → Returns ranked prompts with relevance scores

# Execute multi-step workflows with output passing
result = prompt_chain([
    {
        "name": "design",
        "prompt_id": "architecture-design",
        "variables": {
            "problem": "Build a real-time chat system"
        }
    },
    {
        "name": "implement",
        "prompt_id": "feature-implementation",
        "variables": {
            "design": "{{prev.design}}"  # ← Uses previous step output!
        }
    },
    {
        "name": "review",
        "prompt_id": "code-review",
        "variables": {
            "code": "{{prev.implement}}"
        }
    }
])
```

**Built-in Prompt Templates:**
- 📝 `code-review` - Professional code review
- 🐛 `bug-debugging` - Systematic debugging workflow
- ✨ `feature-implementation` - Complete feature flow
- 🏗️ `architecture-design` - System architecture

**Features:**
- 🎯 Registry management (CRUD operations)
- 💡 Context-aware prompt suggestions (relevance scoring)
- 🔗 Multi-step workflows with output passing
- 📋 YAML-based templates for easy customization
- 🧠 Built-in prompt library + user prompts
- ⚙️ Variable substitution & validation

[→ Full Prompts Documentation](docs/PROMPTS_API.md)

---

## 🔧 Configuration

### Configuration

For ongoing management of your Ninja MCP setup:

```bash
# Run the comprehensive installer for initial setup
ninja-config install-full

# Run the interactive configurator for ongoing management
ninja-config configure
```

These tools provide:
- **API Key Management**: Secure collection for all services
- **Operator Selection**: Choose between Aider, OpenCode, Gemini, Cursor
- **Model Configuration**: Set optimal models for each module
- **Search Provider Setup**: Configure DuckDuckGo, Serper, or Perplexity
- **Daemon Configuration**: Performance tuning and port management
- **IDE Integration**: Connect to Claude Code, VS Code, Zed, OpenCode
- **Advanced Settings**: Fine-tune any configuration value

### Environment Variables

```bash
# Required
export OPENROUTER_API_KEY='your-key'

# Optional but recommended
export NINJA_CODER_MODEL='anthropic/claude-haiku-4.5-20250929'
export NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'
export NINJA_SECRETARY_MODEL='anthropic/claude-haiku-4.5-20250929'

# Optional
export SERPER_API_KEY='your-serper-key'  # For better search
export NINJA_CODE_BIN='aider'             # AI code CLI to use
export NINJA_CODER_TIMEOUT=600            # Timeout in seconds
```

### IDE Integration

#### Claude Code (Recommended)

```bash
# Automatic configuration
ninja-config setup-claude

# Or manual
claude mcp add --scope user --transport stdio ninja-coder -- ninja-coder
claude mcp add --scope user --transport stdio ninja-researcher -- ninja-researcher
claude mcp add --scope user --transport stdio ninja-secretary -- ninja-secretary
```

#### VS Code

Edit `~/.config/Code/User/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-coder": { "command": "ninja-coder" },
    "ninja-researcher": { "command": "ninja-researcher" },
    "ninja-secretary": { "command": "ninja-secretary" }
  }
}
```

#### Zed

Edit `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "ninja-coder": { "command": "ninja-coder" },
    "ninja-researcher": { "command": "ninja-researcher" },
    "ninja-secretary": { "command": "ninja-secretary" }
  }
}
```

---

## 📊 Architecture

```
┌──────────────────────────────────────────────────────────────┐
│            AI Assistants (Your IDE/Editor)                   │
│    Claude Code, VS Code, Zed, ChatGPT, etc.                 │
└────────────────┬────────────┬────────────┬───────────────────┘
                 │            │            │
        ┌────────▼──┐  ┌──────▼──┐  ┌─────▼──────┐
        │   Coder   │  │Research │  │ Secretary  │
        │   MCP     │  │  MCP    │  │    MCP     │
        └────┬──────┘  └──┬──────┘  └─────┬──────┘
             │            │              │
        ┌────▼────────────▼──────────────▼────┐
        │   Ninja Common (Shared Library)     │
        │   ├─ Security (rate limiting, etc)  │
        │   ├─ Logging & Metrics              │
        │   ├─ Configuration Management       │
        │   └─ Daemon Infrastructure          │
        └────────────────────────────────────┘
             │
        ┌────▼──────────────────────────┐
        │   External Services           │
        │   ├─ OpenRouter (AI models)   │
        │   ├─ Web Search (Serper, etc) │
        │   ├─ Git (local repos)        │
        │   └─ AI Code CLI (Aider)      │
        └───────────────────────────────┘
```

---

## 💡 Use Cases

### Building a Web App
```
1. Use Researcher to understand best practices
2. Use Resources to load existing project structure
3. Use Coder to write components in parallel
4. Use Secretary to track changes with git
5. Use Prompts to run code-review chain
```

### Debugging Production Issues
```
1. Use Secretary to search error logs
2. Use Resources to load relevant code sections
3. Use Prompts to run debugging workflow
4. Use Coder to implement fixes
5. Use Researcher to find similar issues/solutions
```

### Learning a New Codebase
```
1. Use Resources to load entire project as context
2. Use Secretary to analyze architecture
3. Use Prompts to get architecture explanation
4. Use Secretary to find specific components
5. Ask questions backed by full context
```

### Code Review & Refactoring
```
1. Use Secretary to find code patterns
2. Use Prompts to run code-review workflow
3. Use Coder to implement improvements
4. Use Secretary to verify changes with git
5. Use Researcher to find best practices
```

---

## 🧪 Quality & Testing

- **400+ Tests** - Unit, integration, and evaluation tests
- **CI/CD Pipeline** - Every commit tested automatically
- **Security Scanning** - Rate limiting, input validation, resource monitoring
- **Performance** - Caching, async/await, parallel execution
- **Documentation** - Comprehensive API docs and examples

```bash
# Run all tests
pytest tests/ -v

# Run specific module tests
pytest tests/test_coder/
pytest tests/test_researcher/
pytest tests/test_secretary/
```

---

## 🔐 Security

- 🔒 **Rate Limiting** - Prevent abuse and API quota exhaustion
- 🛡️ **Input Validation** - Sanitize all inputs
- 🚫 **Secret Redaction** - Automatic masking of sensitive data (API keys, passwords)
- 📊 **Token Tracking** - Monitor and limit token usage
- 🔑 **Scoped Execution** - File access control via patterns
- 📝 **Audit Logging** - Track all operations

See [SECURITY.md](SECURITY.md) for details.

---

## 📚 Documentation

- **[Quick Start](README.md)** - Getting started in 2 minutes
- **[Architecture](ARCHITECTURE.md)** - System design & internals
- **[Coder Module](docs/CODER.md)** - Code writing agent
- **[Researcher Module](docs/RESEARCHER.md)** - Web intelligence
- **[Secretary Module](docs/SECRETARY.md)** - Codebase analysis
- **[Resources API](docs/RESOURCES_API.md)** - Project context
- **[Prompts API](docs/PROMPTS_API.md)** - Workflow templates
- **[Migration Guide](MIGRATION.md)** - Upgrading from v0.1
- **[Contributing](CONTRIBUTING.md)** - How to contribute

---

## Install — MCP Host Integration

Install the package first, then configure your host:

```bash
pip install ninja-mcp
```

API keys (OpenRouter, Anthropic, etc.) are managed via the `ninja-config` TUI and stored in the OS keyring (with an encrypted-file fallback on headless machines):

```bash
ninja-config
```

### Claude Code

After `pip install ninja-mcp`, install the plugin from this repository:

```bash
/plugin install ninja@https://git.mcp-test.dev/hars/ninja-cli-mcp
```

Or, if you have a local clone:

```bash
/plugin install ninja@/path/to/ninja-cli-mcp
```

Claude Code reads `.mcp.json` at the repo root automatically. All four MCP servers (`ninja-coder`, `ninja-researcher`, `ninja-secretary`, `ninja-prompts`) will be registered.

### OpenAI Codex CLI

After `pip install ninja-mcp`, paste the contents of `dist/codex.toml` into `~/.codex/config.toml`:

```toml
[mcp_servers.ninja_coder]
command = "ninja-coder"
args = []
startup_timeout_sec = 30

[mcp_servers.ninja_researcher]
command = "ninja-researcher"
args = []
startup_timeout_sec = 30

[mcp_servers.ninja_secretary]
command = "ninja-secretary"
args = []
startup_timeout_sec = 30

[mcp_servers.ninja_prompts]
command = "ninja-prompts"
args = []
startup_timeout_sec = 30
```

### Generic MCP (Cursor / Windsurf / Claude Desktop)

After `pip install ninja-mcp`, paste the contents of `dist/mcp.json` into your host's MCP config file:

- **Cursor**: `~/.cursor/mcp.json`
- **Windsurf**: `~/.windsurf/mcp.json`
- **Claude Desktop**: `claude_desktop_config.json` (under `mcpServers`)

```json
{
  "mcpServers": {
    "ninja-coder":      { "command": "ninja-coder",      "args": [], "env": {} },
    "ninja-researcher": { "command": "ninja-researcher", "args": [], "env": {} },
    "ninja-secretary":  { "command": "ninja-secretary",  "args": [], "env": {} },
    "ninja-prompts":    { "command": "ninja-prompts",    "args": [], "env": {} }
  }
}
```

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for:
- Development workflow
- Code style guidelines
- How to add new modules
- Testing requirements

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

## 🚀 What's Next?

- [ ] Advanced prompt optimization & caching
- [ ] Extended built-in prompt library
- [ ] Agent orchestration framework
- [ ] Real-time collaboration features
- [ ] Custom module marketplace
- [ ] Enterprise features (audit logging, SSO, etc)

---

**Made with 🥷 by developers, for developers.**

**Start using Ninja MCP today:**

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```
