# Log Location Change - Centralized Cache Directory

## Summary

Changed log and metadata storage from project directory (`.ninja-cli-mcp/`) to centralized cache directory (`~/.cache/ninja-cli-mcp/`) to avoid polluting project repositories.

## Problem

Previously, ninja-cli-mcp created a `.ninja-cli-mcp/` directory in every project:
```
<project>/.ninja-cli-mcp/
├── logs/
├── tasks/
├── metadata/
└── metrics/
```

This caused:
- ❌ Project directories cluttered with logs
- ❌ Need to add `.ninja-cli-mcp/` to every `.gitignore`
- ❌ Logs scattered across multiple projects
- ❌ Difficult to find logs for a specific task

## Solution

Now all logs and metadata are stored in a centralized cache directory:

```
~/.cache/ninja-cli-mcp/<repo_hash>-<repo_name>/
├── logs/           # Execution logs
├── tasks/          # Task instruction files
├── metadata/       # Additional metadata
└── metrics/        # Task metrics (CSV)
```

### Benefits

✅ **Clean Projects** - No files created in project directories
✅ **Centralized** - All logs in one place
✅ **Easy to Find** - Logs organized by repository
✅ **XDG Compliant** - Follows Linux/macOS standards
✅ **Cross-Platform** - Works on Windows, Linux, macOS

## Technical Details

### Path Generation

Each repository gets a unique cache directory based on:
1. **Hash**: First 16 chars of SHA256(repo_absolute_path)
2. **Name**: Repository directory name

Example:
```
Repository: /home/user/projects/my-app
Cache dir:  ~/.cache/ninja-cli-mcp/a1b2c3d4e5f6g7h8-my-app/
```

###  XDG Base Directory Specification

Follows XDG standards:
- **Linux/macOS**: `~/.cache/ninja-cli-mcp/` (or `$XDG_CACHE_HOME/ninja-cli-mcp/`)
- **Windows**: `%LOCALAPPDATA%\ninja-cli-mcp\`

### Code Changes

**Modified Files:**
1. `src/ninja_cli_mcp/path_utils.py` - Updated `get_internal_dir()` function
2. `src/ninja_cli_mcp/metrics.py` - Updated to use centralized cache
3. `src/ninja_cli_mcp/logging_utils.py` - Updated docstrings
4. `README.md` - Updated documentation

## Usage

### Finding Logs

List all cached repositories:
```bash
ls -la ~/.cache/ninja-cli-mcp/
```

View logs for a specific repository:
```bash
# List logs
ls -la ~/.cache/ninja-cli-mcp/*/logs/

# View latest log
cat ~/.cache/ninja-cli-mcp/*/logs/$(ls -t ~/.cache/ninja-cli-mcp/*/logs/ | head -1)
```

### Cleaning Up

Remove logs for a specific repository:
```bash
rm -rf ~/.cache/ninja-cli-mcp/<hash>-<repo_name>/
```

Remove all ninja-cli-mcp logs:
```bash
rm -rf ~/.cache/ninja-cli-mcp/
```

## Migration

No action needed! The new system works immediately:
- Old `.ninja-cli-mcp/` directories in projects can be safely deleted
- New logs will go to the cache directory automatically

Clean up old project directories:
```bash
# In your project
rm -rf .ninja-cli-mcp/
```

## Verification

Test the new log location:
```bash
# Run a quick task
uv run python -m ninja_cli_mcp.cli quick-task \
  --repo-root /path/to/repo \
  --task "Add a comment"

# Check project directory is clean
ls -la /path/to/repo/.ninja-cli-mcp  # Should not exist

# Check cache directory has logs
ls -la ~/.cache/ninja-cli-mcp/
```

## Backwards Compatibility

✅ **Fully compatible** - No breaking changes
- Old logs in `.ninja-cli-mcp/` are ignored (safe to delete)
- New logs go to cache directory
- All existing functionality works the same

## Related Issues

This change fixes the issue where running ninja-cli-mcp in multiple projects would create `.ninja-cli-mcp/` directories everywhere, requiring manual cleanup and `.gitignore` entries.

---

**Implementation Date:** December 18, 2025
**Status:** ✅ Complete and Tested
