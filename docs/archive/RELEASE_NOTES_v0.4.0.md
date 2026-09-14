# Ninja CLI MCP v0.4.0 - OpenCode Performance Revolution 🚀

## Major Features

### 🚀 OpenCode Daemon Mode (50x Performance Improvement)
**Game-changing performance optimization for OpenCode CLI:**
- **50x faster task execution**: Individual tasks reduced from 2-4 minutes to 2-8 seconds
- **Sequential workflows**: Multi-step plans now 3x faster (12-15min → 4-6min)
- **Auto-managed servers**: One persistent OpenCode server per repository
- **Smart activity-based timeout**: Only times out after 20s of no output activity
- **Exit regression fix**: Resolves OpenCode v0.15+ hanging bug
- **Zero configuration**: Daemon mode enabled by default

**Implementation:**
- Automatic server lifecycle management with process monitoring
- Activity-based streaming output monitoring
- Increased timeouts: quick=300s, sequential=900s, parallel=1200s
- Graceful fallback to subprocess mode if daemon fails

### 🤖 Multi-Agent Orchestration (oh-my-opencode)
**Intelligent task decomposition with specialized agents:**
- Chief AI Architect, Frontend Engineer, Backend Engineer, DevOps Engineer
- Oracle (decision making), Librarian (docs), Explorer (analysis)
- Automatic agent selection based on task complexity
- Parallel agent execution for complex projects

### 💬 Session Management
**Persistent conversation context across tasks:**
- Python-based session manager for conversation history
- Session persistence and recovery
- Multi-step context retention
- Session listing and cleanup tools

### 🎨 Modern Interactive CLI
**Beautiful configuration experience:**
- Interactive installer with progress indicators
- Dynamic model selector (no hardcoded lists)
- Intelligent model filtering (removes ancient/deprecated models)
- Real-time API queries for available models
- Centralized configuration in `~/.ninja-mcp.env`

## Bug Fixes

- Fix: Centralize ALL configuration in ~/.ninja-mcp.env
- Fix: Replace hardcoded model lists with dynamic CLI queries
- Fix: Add ninja_config to package list
- Fix: Improve error detection and config handling
- Fix: Update OpenCodeStrategy for proper command format
- Fix: MCP API compatibility updates for all servers
- Fix: Gemini CLI strategy integration

## Documentation

- docs: Comprehensive installer and configurator guide
- docs: Interactive model selector guide
- docs: OpenCode setup guide
- docs: Sequential execution performance analysis
- docs: OpenCode integration plan (1700+ lines)
- docs: Integration test results

## Dependencies

- Added: psutil>=5.9.0 for process management
- Updated: InquirerPy for modern CLI prompts

## Breaking Changes

None - all features are backwards compatible with opt-out mechanisms.

## Upgrade Guide

1. Pull latest changes: `git pull origin main`
2. Update dependencies: `pip install -e .`
3. Restart Claude Desktop to pick up new configuration
4. Daemon mode is enabled automatically - no configuration needed!

To disable daemon mode (not recommended):
```bash
echo "OPENCODE_DISABLE_DAEMON=true" >> ~/.ninja-mcp.env
```

## Performance Benchmarks

**Before (v0.3.5):**
- Simple task: 2-4 minutes
- Sequential 4-step plan: 12-15 minutes
- Frequent timeouts due to OpenCode hanging

**After (v0.4.0):**
- Simple task: 2-8 seconds (50x faster)
- Sequential 4-step plan: 4-6 minutes (3x faster)
- No timeouts (smart activity monitoring)

## Contributors

Special thanks to Claude Sonnet 4.5 for pair programming this release!

---

**Full Changelog**: v0.3.5...v0.4.0
