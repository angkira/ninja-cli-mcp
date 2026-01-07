# Ninja MCP + Claude Code Integration

This directory contains all the integration assets for deeply integrating ninja-mcp with Claude Code in 2026.

## Directory Structure

```
claude-integration/
├── commands/           # Custom slash commands for Claude Code
│   ├── code.md        # /code - Delegate code writing
│   ├── research.md    # /research - Deep web research
│   └── explore.md     # /explore - Codebase exploration
├── skills/            # Packaged skills for Claude.ai and Claude Code
│   ├── ninja-code/    # Ninja Coder skill
│   └── ninja-research/# Ninja Researcher skill
├── agents/            # Custom subagent definitions
│   ├── ninja-architect.md  # Software architect agent
│   └── ninja-reviewer.md   # Code review agent
├── hooks/             # Claude Code hooks configuration
│   └── hooks.json     # Pre/post tool hooks
└── README.md          # This file
```

## Quick Setup

### 1. Install Slash Commands

Copy commands to your project's `.claude/commands/` directory:

```bash
mkdir -p .claude/commands
cp claude-integration/commands/*.md .claude/commands/
```

Or to your global Claude Code config:

```bash
mkdir -p ~/.claude/commands
cp claude-integration/commands/*.md ~/.claude/commands/
```

### 2. Install Custom Agents

Copy agents to your project:

```bash
mkdir -p .claude/agents
cp claude-integration/agents/*.md .claude/agents/
```

### 3. Configure Hooks

Add hooks to your Claude Code settings. Edit `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [
      {"command": "ninja-daemon status --json 2>/dev/null || true"}
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-coder format-file \"${file_path}\" 2>/dev/null || true"
      }
    ]
  }
}
```

### 4. Upload Skills (Claude.ai)

For Claude.ai with code execution enabled:

1. Zip the skill folder: `cd skills && zip -r ninja-code.zip ninja-code/`
2. Go to Claude.ai Settings > Skills
3. Click "Upload skill" and select the ZIP file

## Usage Examples

### Slash Commands

```
/code Create a REST API for user management with CRUD operations

/research Latest React 19 Server Components best practices

/explore Find all database models and their relationships
```

### Custom Agents

In Claude Code, spawn a subagent:

```
Use the ninja-architect agent to design and implement a caching layer for the API
```

### With MCP Tools Directly

```
Use coder_quick_task to implement:
- File: src/cache/redis_cache.py
- Class: RedisCache with get, set, delete methods
- Use redis-py library
- Include TTL support
```

## Integration Roadmap

See [docs/CLAUDE_CODE_2026_INTEGRATION.md](../docs/CLAUDE_CODE_2026_INTEGRATION.md) for the full integration roadmap.

## Requirements

- ninja-mcp >= 0.2.0
- Claude Code CLI (latest)
- API keys configured:
  - `OPENROUTER_API_KEY` for Ninja Coder
  - `PERPLEXITY_API_KEY` for Ninja Researcher

## Resources

- [Claude Code Skills Docs](https://code.claude.com/docs/en/skills)
- [Claude Code Hooks Guide](https://code.claude.com/docs/en/hooks-guide)
- [Claude Code Slash Commands](https://code.claude.com/docs/en/slash-commands)
- [Ninja MCP Documentation](../docs/)
