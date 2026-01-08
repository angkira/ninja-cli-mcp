---
name: explore
description: Explore codebase structure with Ninja Secretary
---

Use ninja-secretary MCP tools to explore:

**Query**: $ARGUMENTS

## Available Tools

### `secretary_file_tree`
Generate project structure:
```json
{
  "repo_root": "/path/to/repo",
  "max_depth": 3,
  "include_sizes": true,
  "include_git_status": true
}
```

### `secretary_grep`
Search code content:
```json
{
  "pattern": "def authenticate",
  "repo_root": "/path/to/repo",
  "file_pattern": "**/*.py",
  "context_lines": 3
}
```

### `secretary_file_search`
Find files by glob pattern:
```json
{
  "pattern": "**/test_*.py",
  "repo_root": "/path/to/repo"
}
```

### `secretary_codebase_report`
Comprehensive analysis:
```json
{
  "repo_root": "/path/to/repo",
  "include_metrics": true,
  "include_dependencies": true,
  "include_structure": true
}
```

### `secretary_document_summary`
Summarize documentation:
```json
{
  "repo_root": "/path/to/repo",
  "doc_patterns": ["**/*.md", "**/README*"]
}
```

## Common Exploration Tasks

- "Show me the project structure" -> `secretary_file_tree`
- "Find all API endpoints" -> `secretary_grep` with pattern `@app\.(get|post|put|delete)`
- "What tests exist?" -> `secretary_file_search` with pattern `**/test_*.py`
- "Analyze this codebase" -> `secretary_codebase_report`
