# Ninja MCP + Claude Code 2026 Integration Roadmap

## Executive Summary

This document outlines a comprehensive plan to deeply integrate ninja-mcp with Claude Code's extensibility ecosystem in 2026. Based on research into Claude Code's latest features, we identify **5 major integration opportunities**:

1. **Custom Skills** - Package ninja modules as uploadable skills
2. **Hooks System** - Automated workflows triggered by Claude Code events
3. **Slash Commands** - Quick-access commands for ninja tools
4. **Custom Agents** - Specialized subagents using ninja-mcp
5. **Agent SDK** - Build standalone ninja-powered agents

---

## 1. Claude Code Skills Integration

### What Are Skills?
Skills are custom capabilities that extend Claude with specialized knowledge and code execution. They're packaged as markdown files with embedded code blocks.

**Official Docs**: https://code.claude.com/docs/en/skills

### Ninja Skills to Create

#### `/ninja-code` Skill
```markdown
# Ninja Code Skill

Delegate code writing tasks to a specialized AI agent (Aider) that writes
directly to files without returning source code to the conversation.

## When to Use
- Complex multi-file implementations
- Refactoring tasks
- Feature implementations with many files

## How It Works
1. User describes what code to write
2. Ninja Coder delegates to Aider
3. Aider writes code directly to disk
4. Summary returned (files changed, description)

## Usage
"Use ninja to implement user authentication with JWT tokens"
"Have ninja add pagination to the API endpoints"
```

#### `/ninja-research` Skill
```markdown
# Ninja Research Skill

Perform deep web research using Perplexity AI with parallel search agents.

## Capabilities
- Multi-query parallel research
- Source aggregation and deduplication
- Fact-checking claims
- Report generation

## Usage
"Research the latest React 19 features using ninja"
"Have ninja fact-check: 'Python 4.0 was released in 2025'"
```

#### `/ninja-explore` Skill
```markdown
# Ninja Explore Skill

Comprehensive codebase exploration and documentation.

## Capabilities
- File tree generation
- Regex content search (grep)
- Codebase analysis reports
- Documentation summarization

## Usage
"Use ninja to analyze this codebase structure"
"Have ninja search for all API endpoint definitions"
```

### Implementation Plan

```
skills/
├── ninja-code/
│   ├── skill.md           # Main skill definition
│   ├── examples/          # Usage examples
│   └── config.json        # Skill metadata
├── ninja-research/
│   ├── skill.md
│   └── config.json
└── ninja-explore/
    ├── skill.md
    └── config.json
```

### Skill Distribution
1. **GitHub Repository**: `anthropics/skills` style public repo
2. **ZIP Upload**: Packaged skills for Claude.ai upload
3. **NPM Package**: `@ninja-mcp/skills` for programmatic access

---

## 2. Hooks System Integration

### What Are Hooks?
Hooks are shell commands that execute at specific points in Claude Code's lifecycle, providing deterministic control.

**Official Docs**: https://code.claude.com/docs/en/hooks-guide

### Hook Integration Points

#### Pre-Tool Hooks
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-secretary validate-path ${file_path}"
      },
      {
        "matcher": "Bash",
        "command": "ninja-coder lint-check --staged"
      }
    ]
  }
}
```

#### Post-Tool Hooks
```json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-coder post-edit-hook --file ${file_path}"
      }
    ]
  }
}
```

#### Session Hooks
```json
{
  "hooks": {
    "SessionStart": [
      {
        "command": "ninja-daemon status --json"
      }
    ],
    "SessionEnd": [
      {
        "command": "ninja-secretary session-report --save"
      }
    ]
  }
}
```

### Ninja Hook Commands to Implement

| Command | Hook Type | Purpose |
|---------|-----------|---------|
| `ninja-coder lint-check` | PreToolUse | Lint before edits |
| `ninja-coder post-edit-hook` | PostToolUse | Format/test after edits |
| `ninja-secretary validate-path` | PreToolUse | Security path validation |
| `ninja-secretary session-report` | SessionEnd | Session summary |
| `ninja-daemon status` | SessionStart | Verify daemons running |
| `ninja-researcher fact-check` | PreToolUse | Validate claims |

---

## 3. Slash Commands

### What Are Slash Commands?
Custom markdown files that define frequently-used prompts.

**Location**: `.claude/commands/`

### Ninja Slash Commands

#### `/code` - Quick Code Task
```markdown
---
name: code
description: Delegate code writing to Ninja Coder
---

Use the ninja-coder MCP tools to implement the following:

$ARGUMENTS

Requirements:
- Write detailed specifications
- Use coder_quick_task for single tasks
- Use coder_execute_plan_sequential for multi-step tasks
- Report files changed when done
```

#### `/research` - Deep Research
```markdown
---
name: research
description: Perform deep research with Ninja Researcher
---

Use ninja-researcher tools to research:

$ARGUMENTS

Steps:
1. Use researcher_deep_research with appropriate queries
2. Synthesize findings into actionable insights
3. Cite sources with URLs
```

#### `/explore` - Codebase Exploration
```markdown
---
name: explore
description: Explore codebase with Ninja Secretary
---

Use ninja-secretary tools to explore:

$ARGUMENTS

Available tools:
- secretary_file_tree for structure
- secretary_grep for content search
- secretary_codebase_report for analysis
```

#### `/ninja-setup` - Setup All MCP Servers
```markdown
---
name: ninja-setup
description: Setup and verify all Ninja MCP servers
---

1. Check if ninja-mcp is installed: `which ninja-coder`
2. If not installed, suggest: `uv tool install ninja-mcp[all]`
3. Verify MCP configuration in settings
4. Test each server with a simple operation
5. Report status of all three modules
```

---

## 4. Custom Agents

### What Are Custom Agents?
Subagents with specific configurations stored in `.claude/agents/`.

**Official Docs**: https://code.claude.com/docs/en/skills (subagent section)

### Ninja Custom Agents

#### `.claude/agents/ninja-architect.md`
```markdown
---
name: ninja-architect
model: claude-sonnet-4-20250514
skills:
  - ninja-code
  - ninja-explore
---

You are a software architect agent with access to Ninja MCP tools.

Your role:
1. Analyze existing codebase structure using ninja-secretary
2. Design implementation plans for new features
3. Delegate code writing to ninja-coder
4. Ensure architectural consistency

Always:
- Read existing code before proposing changes
- Use ninja-secretary for codebase analysis
- Break down large tasks into steps
- Validate changes don't break existing patterns
```

#### `.claude/agents/ninja-researcher.md`
```markdown
---
name: ninja-researcher
model: claude-haiku-4-20250514
skills:
  - ninja-research
---

You are a research agent specialized in gathering technical information.

Your role:
1. Perform deep research using ninja-researcher tools
2. Verify facts and cite sources
3. Synthesize findings into actionable reports
4. Cross-reference multiple sources

Always cite your sources with full URLs.
```

#### `.claude/agents/ninja-reviewer.md`
```markdown
---
name: ninja-reviewer
model: claude-sonnet-4-20250514
skills:
  - ninja-explore
---

You are a code review agent.

Your role:
1. Use ninja-secretary to analyze code changes
2. Check for security issues, bugs, and style violations
3. Provide constructive feedback
4. Suggest improvements with specific code examples
```

---

## 5. Agent SDK Integration

### What Is the Agent SDK?
The Claude Agent SDK provides programmatic access to build custom agents on top of Claude Code's harness.

**Official Docs**: https://docs.claude.com/en/api/agent-sdk/overview

### SDK Integration Opportunities

#### NinjaAgent Class
```python
from claude_agent_sdk import Agent, Tool
from ninja_coder import CoderServer
from ninja_researcher import ResearcherServer
from ninja_secretary import SecretaryServer

class NinjaAgent(Agent):
    """Full-featured agent with all Ninja MCP capabilities."""

    def __init__(self):
        super().__init__(
            name="ninja-agent",
            tools=[
                # Coder tools
                Tool("coder_quick_task", CoderServer.quick_task),
                Tool("coder_execute_plan", CoderServer.execute_plan),

                # Researcher tools
                Tool("researcher_deep_research", ResearcherServer.deep_research),
                Tool("researcher_fact_check", ResearcherServer.fact_check),

                # Secretary tools
                Tool("secretary_file_tree", SecretaryServer.file_tree),
                Tool("secretary_grep", SecretaryServer.grep),
            ]
        )
```

#### Standalone Ninja CLI Agent
```python
#!/usr/bin/env python3
"""Standalone Ninja-powered agent using Claude Agent SDK."""

import asyncio
from claude_agent_sdk import create_agent, run_agent

async def main():
    agent = await create_agent(
        system_prompt="""You are a Ninja-powered development agent.

        You have access to:
        - Ninja Coder: Delegate code writing to Aider
        - Ninja Researcher: Deep web research
        - Ninja Secretary: Codebase exploration

        Use these tools to help with software development tasks.""",
        mcp_servers=[
            "ninja-coder",
            "ninja-researcher",
            "ninja-secretary"
        ]
    )

    await run_agent(agent)

if __name__ == "__main__":
    asyncio.run(main())
```

---

## 6. Implementation Roadmap

### Phase 1: Q1 2026 - Foundation
- [ ] Create `/ninja-code`, `/ninja-research`, `/ninja-explore` slash commands
- [ ] Package ninja modules as installable skills
- [ ] Document skill installation process
- [ ] Add hook commands to ninja CLIs

### Phase 2: Q2 2026 - Deep Integration
- [ ] Create custom agents (`ninja-architect`, `ninja-reviewer`)
- [ ] Implement session hooks for automatic reporting
- [ ] Build skill distribution system (GitHub + ZIP)
- [ ] Add Agent SDK support to ninja-mcp

### Phase 3: Q3 2026 - Advanced Features
- [ ] Multi-agent orchestration with ninja tools
- [ ] Automated codebase documentation generation
- [ ] Integration with Claude.ai skills marketplace
- [ ] CI/CD pipeline integration hooks

### Phase 4: Q4 2026 - Polish & Scale
- [ ] Performance optimization for large codebases
- [ ] Enterprise features (audit logs, access control)
- [ ] Community skill contributions
- [ ] Benchmarking and metrics dashboard

---

## 7. Configuration Files

### Recommended `.mcp.json` with Ninja
```json
{
  "mcpServers": {
    "ninja-coder": {
      "command": "ninja-coder",
      "env": {
        "OPENROUTER_API_KEY": "${OPENROUTER_API_KEY}"
      }
    },
    "ninja-researcher": {
      "command": "ninja-researcher",
      "env": {
        "PERPLEXITY_API_KEY": "${PERPLEXITY_API_KEY}"
      }
    },
    "ninja-secretary": {
      "command": "ninja-secretary"
    }
  }
}
```

### Recommended Hooks Configuration
```json
{
  "hooks": {
    "SessionStart": [
      {"command": "ninja-daemon ensure-running"}
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-coder format-file ${file_path}"
      }
    ],
    "SessionEnd": [
      {"command": "ninja-secretary save-session-report"}
    ]
  }
}
```

---

## 8. Key Resources

### Claude Code Documentation
- Skills: https://code.claude.com/docs/en/skills
- Hooks: https://code.claude.com/docs/en/hooks-guide
- Slash Commands: https://code.claude.com/docs/en/slash-commands
- MCP: https://code.claude.com/docs/en/mcp
- Agent SDK: https://docs.claude.com/en/api/agent-sdk/overview

### Community Resources
- Anthropic Skills Repo: https://github.com/anthropics/skills
- Claude Code Best Practices: https://www.anthropic.com/engineering/claude-code-best-practices
- MCP Server Directory: https://mcpcat.io/

### Ninja MCP Resources
- GitHub: https://github.com/angkira/ninja-mcp
- Documentation: See `/docs` directory
- Examples: See `/examples` directory

---

## 9. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Skill Downloads | 1000/month | GitHub releases |
| Active Users | 500 | MCP server connections |
| Community Skills | 10 | Contributed skills |
| Integration Time | <5 min | Time to full setup |
| Token Savings | 40%+ | Delegation vs inline code |

---

## Appendix A: Skill Packaging Format

```
skill-name/
├── skill.md           # Main skill definition (required)
├── config.json        # Metadata and dependencies
├── examples/          # Usage examples
│   ├── basic.md
│   └── advanced.md
├── tools/             # Custom tool definitions
│   └── my-tool.py
└── README.md          # Documentation
```

### config.json Schema
```json
{
  "name": "ninja-code",
  "version": "1.0.0",
  "description": "Delegate code writing to Ninja Coder",
  "author": "ninja-mcp contributors",
  "requires": ["ninja-mcp>=0.2.0"],
  "mcp_servers": ["ninja-coder"],
  "permissions": ["code_execution", "file_write"]
}
```

---

*Last Updated: January 2026*
*Version: 1.0.0*
