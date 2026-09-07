---
name: code
description: Delegate code writing to Ninja Coder (Aider)
---

Use the ninja-coder MCP tools to implement the following task:

**Task**: $ARGUMENTS

## Instructions

1. **Analyze the request** - Understand what code needs to be written
2. **Choose the right tool**:
   - `coder_simple_task` - For REALLY simple edits ONLY: 1-2 lines, tiny fix in ONE file/function. In-place + safety-commit, WITHOUT worktree. NEVER for class rewrites or multi-file work.
   - `coder_execute_plan_sequential` - For LONG multi-step plans where order matters (multi-file features, class rewrites, big refactors). WITH `ninja/*` worktree, heavy model.
    - `coder_execute_plan_parallel` - For independent tasks at once (atomic steps, non-overlapping files). `complexity: simple` = trivial edits (1-2 lines), IN-PLACE without worktree; `complexity: complex` (default) = real work, WITH `ninja/*` worktree. Never mix — split into two calls.

3. **Write detailed specifications** - Be specific about:
   - What files to create/modify
   - What functions/classes to implement
   - Expected behavior and edge cases
   - Type hints and documentation requirements

4. **Execute and report** - Run the tool and report:
   - Files changed
   - Brief description of changes
   - Any issues encountered

## Example Specification Format

```
Create src/auth/user.py with:
- User class with email (str), password_hash (str) fields
- hash_password(password: str) -> str method using bcrypt
- verify_password(password: str) -> bool method
- Include type hints and docstrings
```

## Remember
- Ninja writes code DIRECTLY to files
- You receive a SUMMARY, not source code
- Run tests yourself after Ninja completes
- Use context_paths to give Ninja relevant file context
