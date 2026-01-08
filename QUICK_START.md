# Ninja MCP Quick Start Guide

Get up and running with Researcher and Secretary modules in 5 minutes.

## Installation (2 minutes)

```bash
# One-line install (fully autonomous)
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```

The installer will:
1. Install dependencies (uv, aider)
2. Install ninja-mcp globally
3. Prompt for your OpenRouter API key
4. Let you choose search provider (DuckDuckGo/Serper/Perplexity)
5. Auto-configure Claude Code (if detected)

**Get your API key**: https://openrouter.ai/keys

## Test Installation (30 seconds)

```bash
# Verify commands are available
ninja-config doctor

# Check Claude Code integration
claude mcp list
```

## Use with Claude Code (1 minute)

MCP servers are automatically configured. Just use them:

```
# In Claude Code:
"Search for Python async patterns using researcher"
"Analyze this codebase using secretary"
```

## Quick Reference

### Researcher Tools

| Tool | What It Does | Example |
|------|--------------|---------|
| `researcher_web_search` | Search the web | Search for "Python tutorials" |
| `researcher_deep_research` | Multi-query parallel research | Research "FastAPI framework" with 20 sources |
| `researcher_generate_report` | Create markdown reports | Generate technical report from sources |
| `researcher_fact_check` | Verify claims | Check if "Python was released in 1991" |
| `researcher_summarize_sources` | Summarize web pages | Summarize python.org and docs.python.org |

### Secretary Tools

| Tool | What It Does | Example |
|------|--------------|---------|
| `secretary_read_file` | Read files | Read src/main.py lines 10-50 |
| `secretary_file_search` | Find files | Find all `**/*.py` files |
| `secretary_grep` | Search content | Find all `def .*async` functions |
| `secretary_file_tree` | Directory tree | Show project structure (depth 3) |
| `secretary_codebase_report` | Analyze codebase | Generate full metrics report |
| `secretary_document_summary` | Summarize docs | Summarize all .md files |
| `secretary_session_report` | Track sessions | Track files accessed and tools used |
| `secretary_update_doc` | Update docs | Update README.md |

## Example Workflows

### Research → Report

```
1. "Research Python async programming with 20 sources"
   → Uses researcher_deep_research

2. "Generate a technical report from those sources"
   → Uses researcher_generate_report

Result: Comprehensive markdown report with citations
```

### Codebase Analysis

```
1. "Show me the file structure of this project"
   → Uses secretary_file_tree

2. "Find all async functions in the codebase"
   → Uses secretary_grep

3. "Generate a codebase analysis report"
   → Uses secretary_codebase_report

Result: Complete understanding of the project
```

## Run as Daemons (Optional)

For faster response times:

```bash
# Start daemons
ninja-daemon start researcher
ninja-daemon start secretary

# Check status
ninja-daemon status

# Now tools respond instantly (no startup time)
```

## Troubleshooting

### Commands not found?
```bash
# Reload your shell config
source ~/.bashrc  # or ~/.zshrc

# Verify PATH
echo $PATH | grep ".local/bin"
```

### Claude Code doesn't see tools?
```bash
# Re-configure Claude Code
ninja-config setup-claude --force

# Check MCP config
cat ~/.config/claude/mcp.json

# Restart Claude Code
# Tools should appear in tool list
```

### Rate limit errors?
```bash
# Wait 60 seconds and try again
# Or use daemon mode for better rate limit handling
```

## Learn More

- **Full Documentation**:
  - Researcher: `docs/researcher/README.md`
  - Secretary: `docs/secretary/README.md`
  - MCP Architecture: `docs/MCP_ARCHITECTURE.md`
  - Testing: `docs/TESTING_GUIDE.md`

- **Example Usage**:
  - See test files for 70+ real examples
  - `tests/test_researcher/test_researcher_integration.py`
  - `tests/test_secretary/test_secretary_integration.py`

- **Get Help**:
  - Configuration: `ninja-config --help`
  - Claude Code setup: `ninja-config setup-claude --help`
  - Daemon: `ninja-daemon --help`

---

**Happy researching and exploring! 🥷**
