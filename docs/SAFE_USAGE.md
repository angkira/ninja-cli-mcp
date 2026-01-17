# Safe Usage Guide for Ninja-Coder

## 🎉 Automatic Safety (NEW!)

**Ninja-coder now has AUTOMATIC safety protection!** You no longer need to manually commit before tasks.

### How It Works

Ninja-coder automatically:
1. ✅ Detects uncommitted changes before running
2. ✅ Auto-commits your changes with a timestamped message
3. ✅ Creates recovery tags (`ninja-safety-TIMESTAMP`)
4. ✅ Validates task descriptions for dangerous patterns
5. ✅ Provides recovery commands if something goes wrong

**Default Mode: AUTO** - Automatically commits before running any task.

### Safety Modes

Set via `NINJA_SAFETY_MODE` environment variable:

| Mode | Behavior | Use When |
|------|----------|----------|
| `auto` (default) | Auto-commits uncommitted changes before tasks | Daily development |
| `strict` | Refuses to run with uncommitted changes | Critical projects |
| `warn` | Warns but allows execution | Testing/experimentation |
| `off` | Disables all safety checks | ⚠️ Not recommended |

**Examples:**

```bash
# Default: Auto-commit before running
ninja-coder simple_task ...

# Strict mode: Refuse to run if uncommitted changes
NINJA_SAFETY_MODE=strict ninja-coder simple_task ...

# Disable safety (NOT recommended)
NINJA_SAFETY_MODE=off ninja-coder simple_task ...
```

## The Problem

AI coding tools (Aider, OpenCode, etc.) can sometimes **overwrite entire files** instead of editing them. This happens when:

1. **No git history** - Tool can't see what changed
2. **Vague instructions** - "Update the file" without specifics
3. **No context** - Missing `context_paths` parameter
4. **Large files** - Tool decides rewriting is easier

## Prevention Strategies

### 1. Automatic Protection (Enabled by Default)

Ninja-coder now **automatically protects** your code:

```bash
# Just run your task - auto-commit happens automatically!
ninja-coder simple_task --task "Add error handling" --repo-root .

# Output:
# 🔒 AUTO MODE: Committing 5 uncommitted file(s)
# ✅ Auto-committed 5 file(s) for safety
# ✅ Safety tag created: ninja-safety-1737123456
# 🔖 Recovery point: git reset --hard ninja-safety-1737123456
```

**Manual commit (if you prefer):**

```bash
# Commit first, then run
git add .
git commit -m "Before ninja task: add error handling"

# Or use the safe wrapper script
./scripts/safe-ninja-task.sh
```

### 2. Use Specific Instructions

**❌ BAD (Vague):**
```python
task = "Update the authentication in user.py"
```

**✅ GOOD (Specific):**
```python
task = """
In src/auth/user.py, modify the existing authenticate() method:
- Keep the current signature
- Add email validation before password check
- Return detailed error messages
- DO NOT rewrite the entire file, ONLY edit the authenticate() method
"""
```

### 3. Always Provide Context Files

**❌ BAD (No context):**
```python
await ninja.simple_task({
    "task": "Add error handling",
    "repo_root": "/path/to/repo",
})
```

**✅ GOOD (With context):**
```python
await ninja.simple_task({
    "task": "Add try-except around API call in process_request()",
    "repo_root": "/path/to/repo",
    "context_paths": [
        "src/api/handlers.py",  # File to edit
        "src/api/errors.py",     # For reference
    ],
})
```

### 4. Use File Scope Restrictions

**✅ BETTER (Restricted scope):**
```python
await ninja.simple_task({
    "task": "Add validation to User.save() method",
    "repo_root": "/path/to/repo",
    "context_paths": ["src/models/user.py"],
    "allowed_globs": ["src/models/user.py"],  # ONLY this file
    "deny_globs": ["src/models/*.py"],        # Deny others
})
```

### 5. Review Before Committing

**ALWAYS:**
```bash
# After ninja-coder runs
git diff                    # Review ALL changes
git diff src/specific.py    # Review specific file

# If something was overwritten
git checkout src/file.py    # Restore single file
git reset --hard HEAD       # Restore everything (DANGER!)
```

## Recovery Strategies

### If File Was Overwritten

#### 1. Check git diff first

```bash
git diff src/overwritten-file.py
```

- If changes look good → keep them
- If file was rewritten → restore it

#### 2. Restore from git

```bash
# Restore single file
git checkout HEAD -- src/overwritten-file.py

# Or restore from specific commit
git checkout abc123 -- src/overwritten-file.py
```

#### 3. Use git reflog

```bash
# Find commit before ninja-coder ran
git reflog

# Restore from that point
git reset --hard HEAD@{1}
```

#### 4. Use safety tags

```bash
# List safety tags created by safe-ninja-task.sh
git tag | grep pre-ninja-task

# Restore from tag
git reset --hard pre-ninja-task-20260117-012345
```

## Best Practices Checklist

Before running ANY ninja-coder task:

- [ ] **Commit all changes** - `git status` should be clean
- [ ] **Use specific instructions** - Reference exact methods/lines
- [ ] **Provide context_paths** - List files to edit
- [ ] **Restrict scope** - Use allowed_globs for safety
- [ ] **Read instructions back** - Does the task make sense?

After ninja-coder completes:

- [ ] **Review changes** - `git diff` before committing
- [ ] **Test the code** - Run tests, check functionality
- [ ] **Commit separately** - Don't mix with other changes
- [ ] **Tag important points** - `git tag milestone-1`

## Aider-Specific Tips

### Tell Aider What NOT To Do

```python
task = """
Modify the calculate_total() function in src/billing.py:
- Add tax calculation
- DO NOT rewrite the entire file
- DO NOT change other methods
- ONLY edit calculate_total() function
- Keep existing imports and class structure
"""
```

### Use Line Number References

```python
task = """
In src/api.py, around line 145 in the process_request() method:
- Add error handling for the database call
- Wrap lines 147-150 in try-except
- Log errors to self.logger
"""
```

### Provide Examples

```python
task = """
Add type hints to the User class in src/models.py.
Example of the style to use:
    def save(self, force: bool = False) -> bool:
        ...
Apply this pattern to all methods in the User class.
"""
```

## When Things Go Wrong

### Scenario 1: File Completely Rewritten

```bash
# Immediately check what changed
git diff src/file.py | wc -l   # How many lines changed?

# If too many (> 50%), restore it
git checkout HEAD -- src/file.py

# Then try again with better instructions
```

### Scenario 2: Multiple Files Affected

```bash
# See all changed files
git status --short

# Restore specific files
git checkout HEAD -- src/unwanted-change.py

# Keep good changes, restore bad ones
```

### Scenario 3: Lost Work (No Commit)

```bash
# Check reflog for previous states
git reflog

# Check if files are in .git/objects (git may have staged them)
git fsck --lost-found

# Check editor backup files
ls -la .*.swp
ls -la *~
```

## Emergency Recovery

If you lost important uncommitted work:

1. **DON'T PANIC** - Git may have saved it
2. **DON'T COMMIT** - Don't overwrite history
3. **Check reflog** - `git reflog`
4. **Check fsck** - `git fsck --lost-found`
5. **Check editor backups** - Most editors save backups
6. **Check /tmp** - Some tools save temp files
7. **Check .git/COMMIT_EDITMSG** - May contain commit message drafts

## Configuration

### Enable Aider's Edit Mode (Safer)

Add to your ninja config or task instructions:

```python
# Prefer edits over rewrites
task = """
EDIT MODE: Make minimal changes only.
In src/file.py:
- Change line 42 from X to Y
- Add line after line 50
"""
```

### Use Read-Only Mode for Large Files

```python
# Don't let aider edit large files directly
context_paths = [
    "src/large-file.py",  # For reference only
]
allowed_globs = [
    "src/small-helper.py",  # Only edit this
]
```

## Summary

1. **ALWAYS commit before running ninja-coder**
2. **Use specific, detailed instructions**
3. **Provide context_paths**
4. **Restrict with allowed_globs**
5. **Review with git diff before committing**
6. **Keep safety tags for recovery**

**Remember**: It's easier to prevent overwrites than to recover from them!
