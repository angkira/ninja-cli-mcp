# Claude Code Hooks CLI Commands - Architecture Specification

## Overview

This specification defines new CLI commands for ninja-mcp modules that are designed to be used as Claude Code hooks. These commands provide deterministic, fast operations that integrate with Claude Code's hook system.

## Design Principles

1. **Fast Execution**: Hook commands must complete in < 500ms
2. **Single Purpose**: Each command does one thing well
3. **JSON Output**: All commands support `--json` for machine-readable output
4. **Exit Codes**: 0 = success, 1 = failure, 2 = warning (non-blocking)
5. **No Side Effects**: Commands should not modify files unless explicitly designed to

## Module: ninja-coder

### Entry Point
```
ninja-coder-hooks <command> [options]
```

### Commands

#### `format-file`
Format a file after it's been edited.

```bash
ninja-coder-hooks format-file <file_path> [--check] [--json]
```

**Arguments:**
- `file_path`: Path to the file to format

**Options:**
- `--check`: Only check if formatting is needed, don't modify
- `--json`: Output JSON result

**Behavior:**
1. Detect file type from extension
2. Run appropriate formatter (ruff for Python, prettier for JS/TS, etc.)
3. Return status

**Output (JSON):**
```json
{
  "status": "formatted|unchanged|error",
  "file": "/path/to/file.py",
  "formatter": "ruff",
  "changes": true
}
```

#### `lint-check`
Check files for linting issues before commit.

```bash
ninja-coder-hooks lint-check [--staged] [--fix] [--json]
```

**Options:**
- `--staged`: Only check git staged files
- `--fix`: Auto-fix issues where possible
- `--json`: Output JSON result

**Output (JSON):**
```json
{
  "status": "pass|fail|fixed",
  "issues": [
    {"file": "src/foo.py", "line": 10, "message": "..."}
  ],
  "total_issues": 3,
  "fixed": 0
}
```

#### `pre-commit`
Run pre-commit checks (lint + type check).

```bash
ninja-coder-hooks pre-commit [--json]
```

**Output (JSON):**
```json
{
  "status": "pass|fail",
  "checks": {
    "lint": {"status": "pass", "issues": 0},
    "typecheck": {"status": "pass", "issues": 0}
  }
}
```

---

## Module: ninja-secretary

### Entry Point
```
ninja-secretary-hooks <command> [options]
```

### Commands

#### `validate-path`
Validate a file path for security (path traversal prevention).

```bash
ninja-secretary-hooks validate-path <file_path> [--repo-root <path>] [--json]
```

**Arguments:**
- `file_path`: Path to validate

**Options:**
- `--repo-root`: Repository root for scope validation
- `--json`: Output JSON result

**Behavior:**
1. Check for path traversal attempts (`..`, absolute paths outside repo)
2. Check against deny patterns (`.git`, `node_modules`, etc.)
3. Return validation result

**Output (JSON):**
```json
{
  "status": "valid|invalid",
  "path": "/path/to/file",
  "reason": null,
  "resolved_path": "/absolute/path/to/file"
}
```

#### `session-report`
Generate or update session activity report.

```bash
ninja-secretary-hooks session-report [--save] [--format <fmt>] [--json]
```

**Options:**
- `--save`: Save report to file
- `--format`: Output format (json|markdown|text)
- `--json`: Output JSON result

**Output (JSON):**
```json
{
  "status": "ok",
  "session_id": "abc123",
  "started_at": "2026-01-07T10:00:00Z",
  "duration_sec": 3600,
  "tools_used": ["Edit", "Bash", "Read"],
  "files_accessed": 15,
  "summary": "..."
}
```

#### `analyze-changes`
Analyze recent file changes for review.

```bash
ninja-secretary-hooks analyze-changes [--since <commit>] [--json]
```

**Options:**
- `--since`: Analyze changes since commit/ref
- `--json`: Output JSON result

**Output (JSON):**
```json
{
  "status": "ok",
  "files_changed": 5,
  "lines_added": 150,
  "lines_removed": 30,
  "changes": [
    {"file": "src/foo.py", "type": "modified", "additions": 50, "deletions": 10}
  ]
}
```

---

## Module: ninja-daemon

### Entry Point
```
ninja-daemon <command> [options]
```

### Commands (additions)

#### `ensure-running`
Ensure all daemons are running, start if not.

```bash
ninja-daemon ensure-running [--modules <list>] [--json]
```

**Options:**
- `--modules`: Comma-separated list of modules (coder,researcher,secretary)
- `--json`: Output JSON result

**Output (JSON):**
```json
{
  "status": "ok|started|error",
  "modules": {
    "coder": {"status": "running", "pid": 12345},
    "researcher": {"status": "started", "pid": 12346},
    "secretary": {"status": "running", "pid": 12347}
  }
}
```

---

## File Structure

```
src/
├── ninja_coder/
│   ├── hooks_cli.py          # NEW: Hook CLI commands
│   └── ...
├── ninja_secretary/
│   ├── hooks_cli.py          # NEW: Hook CLI commands
│   └── ...
└── ninja_common/
    ├── daemon.py             # MODIFY: Add ensure-running
    └── hooks_base.py         # NEW: Shared hook utilities
```

## pyproject.toml Additions

```toml
[project.scripts]
# Existing
ninja-coder = "ninja_coder.server:run"
ninja-researcher = "ninja_researcher.server:run"
ninja-secretary = "ninja_secretary.server:run"
ninja-daemon = "ninja_common.daemon:main"
ninja-config = "ninja_common.config_cli:main"

# NEW: Hook CLIs
ninja-coder-hooks = "ninja_coder.hooks_cli:main"
ninja-secretary-hooks = "ninja_secretary.hooks_cli:main"
```

---

## Implementation Notes

### Shared Base Class

```python
# src/ninja_common/hooks_base.py

from abc import ABC, abstractmethod
import json
import sys
from typing import Any

class HookCommand(ABC):
    """Base class for hook commands."""

    def __init__(self, json_output: bool = False):
        self.json_output = json_output

    @abstractmethod
    def execute(self) -> dict[str, Any]:
        """Execute the hook command and return result dict."""
        pass

    def run(self) -> int:
        """Run command and handle output."""
        try:
            result = self.execute()
            if self.json_output:
                print(json.dumps(result, indent=2))
            else:
                self._print_human_readable(result)
            return 0 if result.get("status") in ("ok", "pass", "valid", "formatted", "unchanged") else 1
        except Exception as e:
            error_result = {"status": "error", "message": str(e)}
            if self.json_output:
                print(json.dumps(error_result, indent=2))
            else:
                print(f"Error: {e}", file=sys.stderr)
            return 1

    def _print_human_readable(self, result: dict[str, Any]) -> None:
        """Print human-readable output. Override in subclasses."""
        for key, value in result.items():
            print(f"{key}: {value}")
```

### Error Handling

- All commands catch exceptions and return proper exit codes
- Error messages are written to stderr
- JSON output includes error details

### Performance Requirements

- Commands should import lazily to minimize startup time
- No network calls in hook commands (use cached data where possible)
- Target < 500ms execution time

---

## Test Requirements

Each command must have:

1. **Unit tests** for core logic
2. **Integration tests** for CLI interface
3. **Edge case tests** for error handling
4. **Performance tests** to verify < 500ms execution

### Test File Structure

```
tests/
├── test_coder_hooks/
│   ├── test_format_file.py
│   ├── test_lint_check.py
│   └── test_pre_commit.py
├── test_secretary_hooks/
│   ├── test_validate_path.py
│   ├── test_session_report.py
│   └── test_analyze_changes.py
└── test_daemon_hooks/
    └── test_ensure_running.py
```

---

## Claude Code Hook Configuration

Example hooks configuration for users:

```json
{
  "hooks": {
    "SessionStart": [
      {"command": "ninja-daemon ensure-running --json"}
    ],
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-secretary-hooks validate-path \"${file_path}\" --json"
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write",
        "command": "ninja-coder-hooks format-file \"${file_path}\" --json"
      }
    ],
    "SessionEnd": [
      {"command": "ninja-secretary-hooks session-report --save --json"}
    ]
  }
}
```
