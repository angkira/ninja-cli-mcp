# Automatic Safety System

## Overview

Ninja-coder now includes **automatic safety protection** to prevent file overwrites and data loss. This system runs by default on every task execution.

## How It Works

Before executing any task, ninja-coder automatically:

1. **Checks for uncommitted changes** in the git repository
2. **Auto-commits changes** (in AUTO mode) with a timestamped message
3. **Creates recovery tags** (`ninja-safety-TIMESTAMP`) for easy rollback
4. **Validates task descriptions** for dangerous patterns
5. **Enforces safety rules** based on the configured mode

## Safety Modes

Configure via `NINJA_SAFETY_MODE` environment variable:

### AUTO (Default) ✅ Recommended

**Behavior**: Automatically commits uncommitted changes before running tasks.

```bash
# Default mode - no configuration needed
ninja-coder simple_task --task "Add feature" --repo-root .

# Output:
# 🔒 AUTO MODE: Committing 5 uncommitted file(s)
# ✅ Auto-committed 5 file(s) for safety
# ✅ Safety tag created: ninja-safety-1737123456
# 🔖 Recovery point: git reset --hard ninja-safety-1737123456
```

**When to use**: Daily development work where you want automatic protection.

### STRICT 🔒 Maximum Safety

**Behavior**: Refuses to run with uncommitted changes.

```bash
export NINJA_SAFETY_MODE=strict
ninja-coder simple_task --task "Add feature" --repo-root .

# Output:
# ❌ STRICT MODE: Refusing to run with 5 uncommitted file(s)
# 💡 Commit your changes first: git add . && git commit -m 'message'
# 💡 Or set NINJA_SAFETY_MODE=auto for automatic commits
```

**When to use**: Critical projects where you want full control over commits.

### WARN ⚠️ Minimal Protection

**Behavior**: Warns about uncommitted changes but allows execution.

```bash
export NINJA_SAFETY_MODE=warn
ninja-coder simple_task --task "Add feature" --repo-root .

# Output:
# ⚠️  16 uncommitted file(s) - consider committing before running tasks
# ✅ Safety tag created: ninja-safety-1737123456
# [task continues...]
```

**When to use**: Testing or experimentation where you don't want auto-commits.

### OFF 🚫 Disabled

**Behavior**: Disables all safety checks.

```bash
export NINJA_SAFETY_MODE=off
ninja-coder simple_task --task "Add feature" --repo-root .
```

**When to use**: ⚠️ Not recommended. Only use in non-git repositories or when you have external backup systems.

## Auto-Commit Format

When AUTO mode creates a commit, it uses this format:

```
[ninja-auto-save] Before task: <task description>

Timestamp: 2024-01-17 10:30:45
Automatic safety commit by ninja-coder
```

Example:
```bash
git log -1 --oneline
# c2920c0 [ninja-auto-save] Before task: Add error handling to API endpoint
```

## Recovery

If something goes wrong, you have multiple recovery options:

### 1. Use the Safety Tag

Every task creates a recovery tag:

```bash
# List all safety tags
git tag | grep ninja-safety

# Reset to a specific tag
git reset --hard ninja-safety-1737123456
```

### 2. Use Git Reflog

```bash
# View recent git history
git reflog

# Reset to a specific point
git reset --hard HEAD@{1}
```

### 3. Use the Recovery Script

```bash
# Interactive recovery menu
./scripts/ninja-recover.sh

# Options:
# 1. Show all changed files
# 2. Show diff for specific file
# 3. Restore specific file
# 4. Restore all changed files
# 5. List safety tags
# 6. Reset to safety tag
```

### 4. Restore Individual Files

```bash
# Restore a single file from last commit
git checkout HEAD -- path/to/file.py

# Restore from a specific tag
git checkout ninja-safety-1737123456 -- path/to/file.py
```

## Additional Safety Features

### Dangerous Keyword Detection

Ninja-coder warns about potentially destructive keywords in task descriptions:

- "rewrite"
- "replace entire"
- "start from scratch"
- "delete everything"
- "remove all"

```bash
# This will trigger a warning:
ninja-coder simple_task --task "Rewrite the authentication module"

# Output:
# ⚠️  Task contains potentially destructive keyword: 'rewrite'
# 💡 Consider using more specific edit instructions instead of full rewrites
```

### Vague Instruction Detection

Warns about vague instructions that might lead to rewrites:

```bash
# Vague (triggers warning):
ninja-coder simple_task --task "Fix and update user.py"

# Specific (no warning):
ninja-coder simple_task --task "In src/auth/user.py, add email validation to the authenticate() method on line 145"
```

### Context Path Validation

Warns if no `context_paths` are provided:

```bash
# Will trigger warning:
ninja-coder simple_task --task "Add error handling"

# Better:
ninja-coder simple_task --task "Add error handling" --context-paths "src/api/handlers.py"
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `NINJA_SAFETY_MODE` | `auto` | Safety enforcement mode (auto/strict/warn/off) |

## Integration with MCP

When using ninja-coder via MCP tools:

```python
# MCP automatically uses AUTO mode
await tools.simple_task({
    "task": "Add validation to User class",
    "repo_root": "/path/to/repo",
    "context_paths": ["src/models/user.py"],
})

# Output in logs:
# ✅ Auto-committed 3 file(s) for safety
# ✅ Safety tag created: ninja-safety-1737123456
```

To override:

```bash
# Set environment variable before starting MCP server
export NINJA_SAFETY_MODE=strict

# Or in your MCP configuration
{
  "env": {
    "NINJA_SAFETY_MODE": "strict"
  }
}
```

## Best Practices

1. **Use AUTO mode** (default) for most work - it's safe and convenient
2. **Use STRICT mode** for critical production code
3. **Always provide context_paths** - helps prevent full file rewrites
4. **Use specific task descriptions** - avoid vague keywords
5. **Review commits** before pushing to remote
6. **Keep safety tags** - don't delete them immediately

## Disabling Safety (Not Recommended)

If you absolutely must disable safety:

```bash
# Temporarily disable for one task
NINJA_SAFETY_MODE=off ninja-coder simple_task ...

# Or globally in your shell profile
export NINJA_SAFETY_MODE=off
```

⚠️ **Warning**: Disabling safety removes all protection against file overwrites. Only do this if you have external backup systems in place.

## FAQ

**Q: Will auto-commits clutter my git history?**

A: Auto-commits use the `[ninja-auto-save]` prefix, making them easy to identify and squash later if needed:

```bash
# Squash auto-commits before pushing
git rebase -i origin/main
# Mark all [ninja-auto-save] commits as 'fixup'
```

**Q: What if auto-commit fails?**

A: Ninja-coder will refuse to run the task and show an error:

```
❌ Failed to auto-commit changes - cannot proceed safely
💡 Commit manually: git add . && git commit -m 'message'
```

**Q: Can I customize the auto-commit message?**

A: Currently no, but the message includes the task description and timestamp for context.

**Q: Does this work in non-git repositories?**

A: Safety checks only work in git repositories. In non-git repos, you'll see:

```
⚠️  Not a git repository - cannot track changes or recover from overwrites
```

Consider initializing git: `git init`

**Q: What's the difference from manual commits?**

A: Auto-commits happen automatically before each task. Manual commits give you more control but require discipline. Use AUTO mode for convenience with safety.

## Troubleshooting

### Safety check failed

If you see safety errors:

```bash
# Check git status
git status

# Manually commit
git add .
git commit -m "Prepare for ninja task"

# Or switch to AUTO mode
export NINJA_SAFETY_MODE=auto
```

### Too many auto-commits

If you're running many tasks and getting too many auto-commits:

```bash
# Option 1: Commit manually before task batch
git add . && git commit -m "Before batch of tasks"

# Option 2: Squash auto-commits later
git rebase -i HEAD~10
```

### Recovery not working

If recovery fails:

```bash
# Use git reflog to find the right state
git reflog

# Look for commits before ninja-coder ran
git show HEAD@{5}

# Reset to that point
git reset --hard HEAD@{5}
```

## See Also

- [SAFE_USAGE.md](SAFE_USAGE.md) - Comprehensive guide on preventing file overwrites
- [CLI_STRATEGIES.md](CLI_STRATEGIES.md) - CLI abstraction architecture
- [MODEL_SELECTION.md](MODEL_SELECTION.md) - Intelligent model selection
