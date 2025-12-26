# Ninja Secretary Module

📋 Codebase exploration, documentation, and session tracking via MCP.

## Overview

The Secretary module provides comprehensive codebase exploration and documentation capabilities through the Model Context Protocol (MCP). It enables AI assistants to read files, search codebases, generate reports, track sessions, and manage documentation.

## Features

### ✅ File Reading
- Read entire files or specific line ranges
- UTF-8 with error handling for binary files
- Relative path support
- File access tracking

### ✅ File Search
- Glob pattern matching (`**/*.py`, `src/**/*.ts`)
- File metadata (size, modified time)
- Result limiting and sorting
- Fast recursive search

### ✅ Content Search (Grep)
- Regex pattern matching
- Context lines before/after matches
- File pattern filtering
- Line number tracking

### ✅ File Tree Generation
- Hierarchical directory structure
- File sizes and metadata
- Configurable depth (1-10 levels)
- Auto-filters hidden files and common directories

### ✅ Codebase Reports
- Project structure analysis
- Code metrics (lines, file types)
- Dependency detection
- Markdown formatted output

### ✅ Documentation Summary
- Auto-discover README, CONTRIBUTING, markdown files
- Per-document summaries
- Combined overview
- Configurable patterns

### ✅ Session Tracking
- One report per session
- Track tools used and files accessed
- Persistent session state
- Summary updates

### ✅ Documentation Management
- Update README, API docs, CHANGELOG
- Three modes: replace, append, prepend
- Auto-create directories
- Module-specific paths

## Installation

```bash
# Install with secretary dependencies
pip install -e ".[secretary]"

# Or install all modules
pip install -e ".[all]"
```

## Usage

### Start the Server

```bash
# Run as standalone server
python -m ninja_secretary.server

# Or use the entry point
ninja-secretary
```

### MCP Tools

#### 1. Read File

```python
{
  "tool": "secretary_read_file",
  "arguments": {
    "file_path": "src/main.py",
    "start_line": 10,  # Optional
    "end_line": 50     # Optional
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "file_path": "src/main.py",
  "content": "...",
  "line_count": 234
}
```

#### 2. File Search

```python
{
  "tool": "secretary_file_search",
  "arguments": {
    "pattern": "**/test_*.py",
    "repo_root": "/path/to/repo",
    "max_results": 100
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "matches": [
    {
      "path": "tests/test_main.py",
      "size": 4567,
      "modified": "2024-01-15T10:30:00"
    }
  ],
  "total_count": 23,
  "truncated": false
}
```

#### 3. Grep

```python
{
  "tool": "secretary_grep",
  "arguments": {
    "pattern": "def \\w+\\(",
    "repo_root": "/path/to/repo",
    "file_pattern": "**/*.py",
    "context_lines": 2,
    "max_results": 100
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "pattern": "def \\w+\\(",
  "matches": [
    {
      "file_path": "src/main.py",
      "line_number": 42,
      "line_content": "def process_data(input):",
      "context_before": ["", "    # Process the input data"],
      "context_after": ["    result = transform(input)", "    return result"]
    }
  ],
  "total_count": 87,
  "truncated": false
}
```

#### 4. File Tree

```python
{
  "tool": "secretary_file_tree",
  "arguments": {
    "repo_root": "/path/to/repo",
    "max_depth": 3,
    "include_sizes": true,
    "include_git_status": false
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "tree": {
    "name": "repo",
    "path": ".",
    "type": "directory",
    "children": [...]
  },
  "total_files": 234,
  "total_dirs": 45,
  "total_size": 1234567
}
```

#### 5. Codebase Report

```python
{
  "tool": "secretary_codebase_report",
  "arguments": {
    "repo_root": "/path/to/repo",
    "include_metrics": true,
    "include_dependencies": true,
    "include_structure": true
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "report": "# Codebase Report: repo\n\n...",
  "metrics": {
    "file_count": 234,
    "total_lines": 15234,
    "extensions": {".py": 120, ".js": 45}
  },
  "file_count": 234
}
```

#### 6. Document Summary

```python
{
  "tool": "secretary_document_summary",
  "arguments": {
    "repo_root": "/path/to/repo",
    "doc_patterns": ["**/*.md", "**/README*", "**/CONTRIBUTING*"]
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "summaries": [
    {
      "path": "README.md",
      "title": "README.md",
      "summary": "...",
      "size": 4567
    }
  ],
  "combined_summary": "...",
  "doc_count": 12
}
```

#### 7. Session Report

```python
# Create new session
{
  "tool": "secretary_session_report",
  "arguments": {
    "session_id": "my-session-123",
    "action": "create",
    "updates": {
      "metadata": {"user": "alice", "task": "code-review"}
    }
  }
}

# Update session
{
  "tool": "secretary_session_report",
  "arguments": {
    "session_id": "my-session-123",
    "action": "update",
    "updates": {
      "tools_used": ["read_file", "grep"],
      "files_accessed": ["src/main.py", "tests/test_main.py"],
      "summary": "Reviewed authentication implementation"
    }
  }
}

# Get session
{
  "tool": "secretary_session_report",
  "arguments": {
    "session_id": "my-session-123",
    "action": "get"
  }
}
```

**Returns:**
```json
{
  "session_id": "my-session-123",
  "started_at": "2024-01-15T10:00:00",
  "last_updated": "2024-01-15T10:30:00",
  "tools_used": ["read_file", "grep", "file_search"],
  "files_accessed": ["src/main.py", "tests/test_main.py"],
  "summary": "Reviewed authentication implementation",
  "metadata": {"user": "alice", "task": "code-review"}
}
```

#### 8. Update Documentation

```python
{
  "tool": "secretary_update_doc",
  "arguments": {
    "module_name": "coder",
    "doc_type": "readme",  # or "api", "changelog"
    "content": "# New Content\n\nUpdated documentation...",
    "mode": "replace"  # or "append", "prepend"
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "doc_path": "docs/coder/README.md",
  "changes_made": "Replaced entire document"
}
```

## Rate Limits

- **Read file**: 60 calls/minute
- **File search**: 30 calls/minute
- **Grep**: 30 calls/minute
- **File tree**: 10 calls/minute
- **Codebase report**: 5 calls/minute
- **Document summary**: 10 calls/minute
- **Session report**: No limit (in-memory)
- **Update doc**: No limit

Rate limits are per-client and use token bucket algorithm.

## Architecture

```
ninja_secretary/
├── __init__.py     # Module exports
├── models.py       # Pydantic models for requests/responses
├── server.py       # MCP server implementation
└── tools.py        # Tool execution logic
```

### Key Components

- **SecretaryToolExecutor**: Main executor class with all tool implementations
- **Session tracking**: In-memory dict, indexed by session_id
- **File operations**: Uses pathlib for cross-platform compatibility
- **Pattern matching**: Uses glob for file search, re for grep

## Dependencies

```toml
secretary = [
    "tree-sitter>=0.21.0",
    "tree-sitter-python>=0.21.0",
    "tree-sitter-javascript>=0.21.0",
    "pygments>=2.17.0",
]
```

Note: Tree-sitter dependencies are installed but not yet utilized in current implementation. Future versions will include AST-based code analysis.

## Examples

### Example 1: Explore New Codebase

```python
# 1. Get project structure
tree = await secretary_file_tree({
    "repo_root": "/path/to/new/project",
    "max_depth": 3
})

# 2. Find main entry points
main_files = await secretary_file_search({
    "pattern": "**/main.*",
    "repo_root": "/path/to/new/project"
})

# 3. Read primary file
content = await secretary_read_file({
    "file_path": main_files["matches"][0]["path"]
})

# 4. Generate codebase report
report = await secretary_codebase_report({
    "repo_root": "/path/to/new/project",
    "include_metrics": true,
    "include_dependencies": true
})
```

### Example 2: Find and Analyze Functions

```python
# Find all async function definitions
functions = await secretary_grep({
    "pattern": "async def \\w+",
    "repo_root": "/path/to/project",
    "file_pattern": "**/*.py",
    "context_lines": 5
})

# Read each function's file
for match in functions["matches"]:
    file_content = await secretary_read_file({
        "file_path": match["file_path"],
        "start_line": match["line_number"],
        "end_line": match["line_number"] + 20
    })
```

### Example 3: Session Tracking

```python
# Start session
session = await secretary_session_report({
    "session_id": "code-review-123",
    "action": "create"
})

# During work, update session
await secretary_session_report({
    "session_id": "code-review-123",
    "action": "update",
    "updates": {
        "tools_used": ["read_file"],
        "files_accessed": ["src/auth.py"],
        "summary": "Started reviewing authentication module"
    }
})

# Later, get full session report
final_report = await secretary_session_report({
    "session_id": "code-review-123",
    "action": "get"
})
```

### Example 4: Documentation Discovery

```python
# Find all documentation
docs = await secretary_document_summary({
    "repo_root": "/path/to/project",
    "doc_patterns": ["**/*.md", "**/docs/**/*"]
})

# docs["summaries"] contains per-file summaries
# docs["combined_summary"] contains overview
```

## Best Practices

### File Reading
- Use line ranges for large files to reduce memory usage
- Check file existence before reading (errors handled gracefully)
- Binary files return error status with appropriate message

### Pattern Matching
- Use specific patterns to reduce results: `src/**/*.py` vs `**/*.py`
- Combine file_search with read_file for efficient exploration
- Use max_results to limit memory usage

### Session Tracking
- Create session at start of task
- Update incrementally during work
- Include meaningful summaries for later reference
- Use metadata for task-specific information

### Codebase Reports
- Generate once per session for overview
- Include all sections (metrics, dependencies, structure)
- Use for onboarding, documentation, or analysis

## Development

### Running Tests

```bash
pytest tests/test_secretary.py -v
```

### Type Checking

```bash
mypy src/ninja_secretary --strict
```

### Linting

```bash
ruff check src/ninja_secretary
```

## Troubleshooting

### Issue: "File not found"

**Solution**: Check that file_path is relative to repo_root, not absolute.

### Issue: Grep returns too many results

**Solutions**:
- Make regex pattern more specific
- Use file_pattern to filter files
- Reduce max_results parameter

### Issue: File tree too large

**Solutions**:
- Reduce max_depth parameter
- Filter results after generation
- Use file_search for specific patterns instead

### Issue: Binary file error

**Solution**: Secretary auto-detects binary files and returns error status. This is expected behavior.

## Future Enhancements

- AST-based code analysis using tree-sitter
- Git integration for file status
- Code quality metrics
- Dependency graph generation
- Persistent session storage

## License

MIT License - see main project LICENSE file.
