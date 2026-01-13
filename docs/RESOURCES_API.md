# Resources API Documentation

## Overview

The Resources module enables sharing structured project data with Claude as queryable context. Instead of copying-pasting raw files, you can load entire codebases, configurations, and documentation as resources that Claude can understand and reference.

**Key Concepts:**
- **Resources**: Structured data representations of project components
- **Resource ID**: Unique identifier for loaded resource (cached for 1 hour)
- **Caching**: Automatic caching of expensive operations
- **Redaction**: Automatic removal of sensitive data (API keys, passwords)

---

## Tools

### 1. `resource_codebase`

Load your project's codebase as a queryable resource, with file structure, language detection, and function/class extraction.

**Request:**
```json
{
  "repo_root": "/path/to/project",
  "include_patterns": ["**/*.py", "**/*.js"],
  "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**"],
  "max_files": 1000,
  "summarize": true
}
```

**Parameters:**
- `repo_root` (required): Path to project root
- `include_patterns` (optional): File patterns to include (default: all)
- `exclude_patterns` (optional): File patterns to exclude (default: common build/cache dirs)
- `max_files` (optional): Maximum files to analyze (default: 1000)
- `summarize` (optional): Generate summaries (default: true)

**Response:**
```json
{
  "status": "ok",
  "resource_id": "codebase-2026-01-13-abc123",
  "summary": "FastAPI web application with React frontend",
  "structure": {
    "directories": ["src/", "tests/", "frontend/", "docs/"],
    "languages": ["python", "javascript", "markdown"],
    "file_count": 47,
    "total_size_mb": 2.3
  },
  "files": [
    {
      "path": "src/main.py",
      "language": "python",
      "lines": 150,
      "summary": "Main FastAPI application setup",
      "functions": ["create_app", "run_server"],
      "classes": []
    }
  ]
}
```

**Use Cases:**
- "Load my project so you understand the structure"
- "Analyze the codebase to suggest architecture improvements"
- "Review code quality across the entire project"

---

### 2. `resource_config`

Load configuration files with automatic redaction of sensitive data.

**Request:**
```json
{
  "repo_root": "/path/to/project",
  "include": [".env.example", "config.yaml", "settings.json"],
  "redact_patterns": ["password", "token", "secret", "api_key"]
}
```

**Parameters:**
- `repo_root` (required): Path to project root
- `include` (required): List of config files to load
- `redact_patterns` (optional): Patterns to redact (default: password, token, secret, api_key)

**Response:**
```json
{
  "status": "ok",
  "resource_id": "config-2026-01-13-xyz789",
  "files": [
    {
      "path": ".env.example",
      "content": "DATABASE_URL=postgresql://...\nAPI_KEY=***REDACTED***\nDEBUG=true\n..."
    },
    {
      "path": "config.yaml",
      "content": "server:\n  port: 8000\n  secret: ***REDACTED***\n..."
    }
  ]
}
```

**Use Cases:**
- "Show me the project configuration (without exposing secrets)"
- "What environment variables does the project need?"
- "Help me understand the deployment configuration"

**Security Note:** Sensitive data matching `password`, `token`, `secret`, or `api_key` patterns is automatically redacted as `***REDACTED***`.

---

### 3. `resource_docs`

Load documentation files as a queryable resource with section extraction.

**Request:**
```json
{
  "repo_root": "/path/to/project",
  "doc_patterns": ["**/*.md", "docs/**"],
  "include_structure": true
}
```

**Parameters:**
- `repo_root` (required): Path to project root
- `doc_patterns` (optional): Markdown patterns to include
- `include_structure` (optional): Extract sections from markdown (default: true)

**Response:**
```json
{
  "status": "ok",
  "resource_id": "docs-2026-01-13-def456",
  "docs": [
    {
      "path": "README.md",
      "title": "Project Overview",
      "sections": ["Installation", "Usage", "API Reference", "Contributing"],
      "summary": "Main project documentation with setup and usage instructions"
    },
    {
      "path": "docs/architecture.md",
      "title": "Architecture Guide",
      "sections": ["Overview", "Components", "Data Flow"],
      "summary": "System architecture and design decisions"
    }
  ]
}
```

**Use Cases:**
- "Reference the project documentation while implementing features"
- "Ensure my implementation follows the documented architecture"
- "Help me understand the project's API from its docs"

---

## Usage Patterns

### Pattern 1: Full Project Context

```
User: "Review my project structure and suggest improvements"

1. Load codebase resource: resource_codebase({repo_root})
2. Load docs resource: resource_docs({repo_root})
3. Claude understands full project
4. Provides structure and architecture feedback
```

### Pattern 2: Feature Implementation with Context

```
User: "Implement authentication following project conventions"

1. Load codebase: Understand existing code patterns
2. Load config: Know environment requirements
3. Load docs: Reference API design decisions
4. Implement feature following conventions
```

### Pattern 3: Configuration Review

```
User: "Verify my deployment configuration"

1. Load config resource
2. Claude reviews configuration
3. Suggests improvements and highlights issues
4. All without exposing secrets
```

### Pattern 4: Documentation-Driven Development

```
User: "Build the API as documented"

1. Load docs resource
2. Load existing implementation
3. Claude ensures implementation matches docs
4. Highlights discrepancies
```

---

## Resource Caching

Resources are cached for **1 hour** in memory. Subsequent requests for the same `repo_root` return immediately without re-parsing files.

**Cache Behavior:**
- First call: ~500ms (parses files)
- Subsequent calls: ~10ms (from cache)
- Cache invalidates after 1 hour
- Modify file → new resource needed

---

## Error Handling

**Common Errors:**

```json
{
  "status": "error",
  "message": "Repository not found at /invalid/path"
}
```

**Error Cases:**
- Invalid `repo_root`: Returns error with helpful message
- Too many files: Truncates to `max_files`, returns what could be loaded
- Unreadable files: Skips unreadable files, includes readable ones
- Permission denied: Returns error with specific path

---

## Performance

**Typical Response Times:**
- Small project (<100 files): 100-200ms
- Medium project (100-500 files): 300-500ms
- Large project (500+ files): 500ms - 2s (cached after first load)

**Optimization Tips:**
1. Use `include_patterns` to limit files processed
2. Use `exclude_patterns` for build/cache directories
3. Reuse `resource_id` in multiple operations (hits cache)
4. Set `summarize=false` if you only need file listing

---

## Integration with Other Tools

### With Secretary Module
```
1. Load codebase resource
2. Use secretary_analyse_file on specific file
3. Secretary gets full context from resource
```

### With Prompts Module
```
1. Load codebase resource
2. prompt_suggest uses resource to suggest relevant prompts
3. Execute prompt chain with resource as context
```

### With Coder Module
```
1. Load codebase resource (understand conventions)
2. Load config resource (understand constraints)
3. Use coder_simple_task to implement feature
4. Coder follows patterns established in resource
```

---

## Best Practices

1. **Always load context first** when working with unfamiliar projects
2. **Use resource_config** to understand deployment requirements
3. **Reference docs resource** when implementing features
4. **Reuse resource_ids** instead of reloading (hits cache)
5. **Exclude build directories** with `exclude_patterns`
6. **Set reasonable max_files** limit to avoid timeout

---

## Examples

### Example 1: Understand New Project
```bash
resource_codebase({
  "repo_root": "/home/user/new-project",
  "include_patterns": ["**/*.py"],
  "exclude_patterns": ["**/test*", "**/__pycache__"]
})

# Result: Understanding of Python project structure and main components
```

### Example 2: Config Review with Redaction
```bash
resource_config({
  "repo_root": "/home/user/project",
  "include": [".env.example", "docker-compose.yml", "kubernetes/values.yaml"]
})

# Result: Config files with all secrets safely redacted
```

### Example 3: API Documentation
```bash
resource_docs({
  "repo_root": "/home/user/api-project",
  "doc_patterns": ["docs/api/**/*.md"]
})

# Result: Structured access to API documentation by endpoint
```

---

## Limitations

- **File size**: Individual files >10MB are truncated
- **Total size**: Projects >100MB load slower (consider filtering)
- **Cache duration**: 1 hour (design constraint, not a limitation)
- **Pattern complexity**: Basic glob patterns (not full regex)

---

## Related Documentation

- [Prompts API](./PROMPTS_API.md) - Use resources in prompt workflows
- [Secretary API](./SECRETARY_API.md) - Analyze individual files from resources
- [Integration Guide](./INTEGRATION_GUIDE.md) - Combine modules for full workflows
