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

### `coder_quick_task`
Single code writing task. Best for focused implementations.

Parameters:
- `task` (required): Detailed specification of what to code
- `repo_root` (required): Repository root path
- `context_paths`: Files to read for context
- `allowed_globs`: Files ninja can modify
- `deny_globs`: Files ninja cannot touch

### `coder_execute_plan_sequential`
Multi-step implementation where order matters.

### `coder_execute_plan_parallel`
Independent tasks that can run simultaneously.

## Example Usage

### Simple Task
```
Use coder_quick_task to create a User model:

Task: "Create src/models/user.py with:
- User dataclass with fields: id (int), email (str), created_at (datetime)
- validate_email() method that checks email format
- to_dict() method for serialization
- Include type hints and docstrings"
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
