# Ninja MCP Quick Start Guide

Get up and running with Researcher and Secretary modules in 5 minutes.

## Installation (2 minutes)

```bash
# 1. Run interactive installer
./scripts/install_interactive.sh

# 2. Select modules (check all you want):
#    ✓ Researcher - Web search & reports
#    ✓ Secretary - Codebase exploration

# 3. Configure API keys:
#    • OpenRouter: https://openrouter.ai/keys
#    • Serper.dev (optional): https://serper.dev

# 4. Done! Configuration saved to ~/.ninja-mcp.env
```

## Test Installation (30 seconds)

```bash
# Load configuration
source ~/.ninja-mcp.env

# Run tests
./scripts/run_tests.sh --fast

# ✓ All tests should pass
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

### Tests fail?
```bash
# Install dependencies
uv sync --extra dev --extra researcher --extra secretary

# Try again
./scripts/run_tests.sh --fast
```

### Claude Code doesn't see tools?
```bash
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
  - Installation: `./scripts/install_interactive.sh --help`
  - Testing: `./scripts/run_tests.sh --help`
  - Daemon: `ninja-daemon --help`

---

**Happy researching and exploring! 🥷**
