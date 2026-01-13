# Prompts API Documentation

## Overview

The Prompts module provides reusable prompt templates, suggestion engine, and multi-step workflow composition. Instead of re-writing prompts, you can define templates once and reuse them across projects.

**Key Concepts:**
- **Prompts**: Reusable templates with variables and structured guidance
- **Prompt Registry**: Manage user and built-in prompts
- **Prompt Suggestion**: AI-powered recommendations based on context
- **Prompt Chain**: Multi-step workflows that combine multiple prompts

---

## Tools

### 1. `prompt_registry`

Manage prompt templates: list, create, update, retrieve, and delete.

**Request - List Prompts:**
```json
{
  "action": "list",
  "scope": "all"
}
```

**Response - List:**
```json
{
  "status": "ok",
  "prompts": [
    {
      "id": "code-review-v1",
      "name": "Code Review",
      "description": "Professional code review with quality focus",
      "variables_count": 4,
      "tags": ["code-review", "quality"],
      "scope": "global",
      "created": "2026-01-13T10:30:00Z"
    },
    {
      "id": "bug-debugging-v1",
      "name": "Bug Debugging",
      "description": "Systematic bug investigation",
      "variables_count": 5,
      "tags": ["debugging", "bug-fix"],
      "scope": "global",
      "created": "2026-01-13T10:30:00Z"
    }
  ]
}
```

**Request - Get Specific Prompt:**
```json
{
  "action": "get",
  "prompt_id": "code-review-v1"
}
```

**Response - Get:**
```json
{
  "status": "ok",
  "prompts": [
    {
      "id": "code-review-v1",
      "name": "Code Review",
      "description": "Professional code review...",
      "template": "Please review this {{language}} code...",
      "variables": [
        {
          "name": "code",
          "required": true,
          "description": "The code to review"
        },
        {
          "name": "language",
          "required": false,
          "default": "python",
          "description": "Programming language"
        }
      ],
      "tags": ["code-review", "quality"],
      "scope": "global"
    }
  ]
}
```

**Request - Create Prompt:**
```json
{
  "action": "create",
  "name": "Security Review",
  "description": "Security-focused code review",
  "template": "Review this code for security issues: {{code}}",
  "variables": [
    {
      "name": "code",
      "required": true,
      "description": "Code to review"
    }
  ],
  "tags": ["security", "review"],
  "scope": "user"
}
```

**Request - Update/Delete:**
```json
{
  "action": "update|delete",
  "prompt_id": "custom-prompt-1"
}
```

**Parameters:**
- `action` (required): "list" | "get" | "create" | "update" | "delete"
- `prompt_id` (required for get/update/delete)
- `name`, `description`, `template`, `variables` (required for create)
- `scope` (optional): "user" (saved to ~/.ninja-mcp/prompts/) | "global" (built-in)

---

### 2. `prompt_suggest`

Get AI-powered suggestions for relevant prompts based on context.

**Request:**
```json
{
  "context": {
    "task": "code-review",
    "language": "python",
    "file_path": "src/auth.py",
    "file_type": "backend"
  },
  "max_suggestions": 5
}
```

**Response:**
```json
{
  "status": "ok",
  "suggestions": [
    {
      "prompt_id": "code-review-v1",
      "name": "Code Review",
      "relevance_score": 0.95,
      "reason": "Perfect match for Python code review",
      "suggested_variables": {
        "code": "[content of src/auth.py]",
        "language": "python",
        "focus_areas": "security, performance, maintainability"
      }
    },
    {
      "prompt_id": "security-review-custom",
      "name": "Security Review",
      "relevance_score": 0.88,
      "reason": "Auth code requires security focus",
      "suggested_variables": {
        "code": "[content of src/auth.py]"
      }
    }
  ]
}
```

**Context Fields:**
- `task`: What are you trying to do? (e.g., "code-review", "bug-debugging", "feature-implementation")
- `language`: Programming language (e.g., "python", "javascript")
- `file_path`: Path to file being worked on
- `file_type`: Type of code (e.g., "backend", "frontend", "test")
- `codebase_context`: Description of the project
- Any other contextual information

**Relevance Scoring:**
- 1.0 = Perfect match
- 0.7-0.99 = Highly relevant
- 0.5-0.69 = Somewhat relevant
- <0.5 = Not relevant

---

### 3. `prompt_chain`

Compose and execute multi-step workflows combining multiple prompts.

**Request - Create Chain:**
```json
{
  "action": "create",
  "chain_id": "feature-implementation",
  "name": "Feature Implementation Workflow",
  "steps": [
    {
      "name": "design",
      "prompt_id": "architecture-design-v1",
      "variables": {
        "problem_statement": "Add user authentication",
        "constraints": "Must work with existing database"
      }
    },
    {
      "name": "implement",
      "prompt_id": "code-generation-v1",
      "variables": {
        "design": "{{prev.design}}",
        "language": "python"
      }
    },
    {
      "name": "review",
      "prompt_id": "code-review-v1",
      "variables": {
        "code": "{{prev.implement}}",
        "focus_areas": "security, performance"
      }
    }
  ]
}
```

**Request - Execute Chain:**
```json
{
  "action": "execute",
  "chain_id": "feature-implementation",
  "steps": [
    {
      "name": "design",
      "prompt_id": "architecture-design-v1",
      "variables": {
        "problem_statement": "Add user authentication"
      }
    }
  ]
}
```

**Response:**
```json
{
  "status": "ok",
  "chain_id": "feature-implementation",
  "executed_steps": [
    {
      "step_name": "design",
      "output": "## Design\n\n### Architecture\n- Use OAuth2 for authentication\n- Store tokens in database...",
      "prompt_id": "architecture-design-v1"
    },
    {
      "step_name": "implement",
      "output": "```python\nclass AuthService:\n    def authenticate(self, credentials):\n        ...\n```",
      "prompt_id": "code-generation-v1"
    },
    {
      "step_name": "review",
      "output": "## Code Review Results\n\n### Strengths\n- Proper error handling\n...",
      "prompt_id": "code-review-v1"
    }
  ]
}
```

**Chain Features:**
- **Sequential execution**: Steps run in order
- **Output passing**: `{{prev.step_name}}` references previous output
- **Variable inheritance**: Later steps can use all previous outputs
- **Flexible composition**: Combine any prompts in any order

---

## Built-in Prompts

### code-review-v1
Professional code review focused on quality, security, maintainability.

**Variables:**
- `code` (required): Code to review
- `language` (optional): Programming language
- `focus_areas` (optional): Areas to focus on
- `context` (optional): Additional context

### bug-debugging-v1
Systematic bug investigation and fixing.

**Variables:**
- `bug_description` (required): What's the bug?
- `error_message` (optional): Error stack trace
- `code_context` (optional): Relevant code
- `reproduction_steps` (optional): How to reproduce

### feature-implementation-v1
Complete feature workflow: design, implement, test, document.

**Variables:**
- `feature_name` (required): Feature name
- `feature_description` (required): What does it do?
- `requirements` (optional): Acceptance criteria
- `technical_context` (optional): Architecture info

### architecture-design-v1
Design system architecture and components.

**Variables:**
- `problem_statement` (required): What problem are we solving?
- `constraints` (optional): Technical constraints
- `existing_architecture` (optional): Current architecture
- `considerations` (optional): What matters?

---

## Usage Patterns

### Pattern 1: Quick Prompt Use

```
User: "Review this code"
1. Suggest prompts: prompt_suggest({task: "code-review"})
2. Get suggested prompt: prompt_registry({action: "get", prompt_id: "code-review-v1"})
3. Fill variables with code
4. Execute prompt
```

### Pattern 2: Multi-Step Workflow

```
User: "Implement authentication feature"
1. Create chain: feature-implementation workflow
2. Execute chain with feature description
3. Get design output
4. Get implementation code
5. Get code review
6. All in one workflow
```

### Pattern 3: Custom Prompt

```
User: "Create custom security review prompt"
1. Create custom prompt: prompt_registry({action: "create", ...})
2. Save to ~/.ninja-mcp/prompts/
3. Use in chains
4. Share with team
```

### Pattern 4: Context-Aware Suggestions

```
User: "What prompts should I use?"
1. Load codebase resource
2. Analyze file with secretary
3. Get suggestions: prompt_suggest({context: analysis_result})
4. Get most relevant prompt
5. Execute with pre-filled variables
```

---

## Template Variables

### Variable Syntax
- `{{variable_name}}`: Simple substitution
- `{{prev.step_name}}`: Access previous step output
- `{{env.VARIABLE}}`: Environment variables (future)

### Variable Types

**Required Variables:**
Must be provided when using the prompt.

**Optional Variables:**
Can be omitted, use `default` value if provided.

**Variable Validation:**
Templates are validated before execution. Missing required variables return error.

---

## Error Handling

**Errors:**

```json
{
  "status": "error",
  "message": "Prompt not found: code-review-v2"
}
```

**Common Errors:**
- Prompt not found: Specify correct `prompt_id`
- Missing required variables: Provide all required vars
- Invalid chain: Check step order and variable references
- File not found: Config/save location issue

---

## Performance

**Typical Times:**
- List prompts: 10ms
- Get prompt: 5ms
- Suggest prompts: 100-200ms (with AI)
- Execute 3-step chain: 2-5 seconds (depends on Claude)

---

## Storage

**Built-in Prompts:**
- Location: `data/builtin_prompts/` (in package)
- Format: YAML files
- Scope: "global" (read-only)

**User Prompts:**
- Location: `~/.ninja-mcp/prompts/`
- Format: YAML files
- Scope: "user" (read-write)

---

## Integration with Other Modules

### With Resources
```
1. Load codebase resource
2. prompt_suggest uses resource context
3. Execute prompt with resource as context
```

### With Secretary
```
1. Analyze file with secretary
2. Get prompts for analyzed file
3. Execute prompts using file content
```

### With Coder
```
1. Design with prompt chain
2. Generate code with prompt
3. Use coder_simple_task to implement
```

---

## Best Practices

1. **Use suggestions first**: Don't guess - use `prompt_suggest`
2. **Create custom prompts**: Save reusable workflows
3. **Chain related prompts**: Multi-step workflows are powerful
4. **Reference documentation**: Include context in variables
5. **Test chains**: Verify steps work before committing
6. **Share templates**: Team can reuse your prompts

---

## Examples

### Example 1: Code Review
```bash
prompt_registry({
  "action": "get",
  "prompt_id": "code-review-v1"
})

# Fill variables:
# - code: [paste your code]
# - language: python
# - focus_areas: security, performance
```

### Example 2: Suggest Prompts
```bash
prompt_suggest({
  "context": {
    "task": "fix-bug",
    "language": "javascript",
    "file_type": "react-component"
  },
  "max_suggestions": 3
})

# Returns: debugging, testing, react-specific prompts
```

### Example 3: Execute Workflow
```bash
prompt_chain({
  "action": "execute",
  "chain_id": "feature-implementation",
  "steps": [...]
})

# Returns: Design, Code, Review all in sequence
```

---

## Related Documentation

- [Resources API](./RESOURCES_API.md) - Load project context
- [Secretary API](./SECRETARY_API.md) - Analyze files
- [Integration Guide](./INTEGRATION_GUIDE.md) - Combine everything
