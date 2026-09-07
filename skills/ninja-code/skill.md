# Ninja Code Skill

Delegate complex code writing tasks to a specialized AI coding agent (Aider) that writes directly to files.

## Overview

Ninja Coder is an MCP server that delegates code writing to AI assistants like Aider. Instead of generating code in the conversation, Ninja writes code directly to disk and returns only a summary.

## When to Use This Skill

- Multi-file implementations requiring coordinated changes
- Large refactoring tasks
- Feature implementations that touch many files
- When you want code written without cluttering the conversation

## How It Works

```
You (specification) -> Ninja Coder -> Aider -> Files Written -> Summary Returned
```

1. You provide a detailed code specification
2. Ninja Coder translates it to Aider instructions
3. Aider writes/modifies files directly
4. You receive a summary of changes (not source code)

## Available Tools

### `coder_simple_task`
REALLY simple edits ONLY: 1-2 lines, a tiny fix in ONE file/function
(add a field, fix a typo, small bugfix). Runs IN-PLACE with safety-commit,
WITHOUT worktree.

**⚠️ For REALLY simple tasks ONLY.** Runs on the fast `quick` model with a short timeout.
Do NOT send class rewrites, large multi-part features, MR stabilization, multi-file
work, or refactors here — they will time out.
Use `coder_execute_plan_sequential` instead.

Parameters:
- `task` (required): Detailed specification of what to code
- `repo_root` (required): Repository root path
- `context_paths`: Files to read for context
- `allowed_globs`: Files ninja can modify
- `deny_globs`: Files ninja cannot touch

### `coder_execute_plan_sequential`
Long multi-step plans where order matters. Runs ISOLATED in a `ninja/*`
worktree (heavy model). Use for multi-file features, class rewrites, big refactors.

### `coder_execute_plan_parallel`
Independent tasks at once (atomic steps, non-overlapping file scopes).
Two modes via `complexity`: `simple` = trivial edits (1-2 lines per step),
IN-PLACE without worktree; `complex` (default) = real implementation work,
ISOLATED in a `ninja/*` worktree. Never mix — split a mixed batch into two calls.

## Example Usage

### Simple Task
```
Use coder_simple_task for a tiny fix (1-2 lines, one file/function):

Task: "In src/models/user.py, fix the email regex in validate_email() to accept '+' in the local part"
```

### Multi-Step Implementation
```
Use coder_execute_plan_sequential for auth system:

Step 1: "Create src/auth/password.py with hash_password and verify_password functions using bcrypt"
Step 2: "Create src/auth/jwt.py with create_token and verify_token functions"
Step 3: "Create src/api/auth.py with /login and /register endpoints using the auth modules"
```

## Best Practices

1. **Be Specific**: Include file paths, function names, types, and expected behavior
2. **Use Context**: Provide `context_paths` for files Ninja should reference
3. **Scope Access**: Use `allowed_globs` to limit what Ninja can modify
4. **Test After**: Run your tests after Ninja completes - it only writes code

## Requirements

- Ninja MCP installed: `uv tool install ninja-mcp[coder]`
- OPENROUTER_API_KEY environment variable set
- Aider installed (auto-detected)
