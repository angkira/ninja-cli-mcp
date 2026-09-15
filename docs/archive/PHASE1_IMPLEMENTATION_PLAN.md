# Phase 1 Implementation Plan - Resources & Prompts

**Target:** Complete in 4-5 days
**Approach:** Modular development with ninja-coder + ninja-secretary + testing
**Success Criteria:** All tools working, documented, tested, with example workflows

---

## Architecture Overview

### Current Structure
```
src/
├── ninja_coder/          (Code writing)
├── ninja_secretary/      (Codebase exploration)
├── ninja_researcher/     (Web search)
└── ninja_common/         (Shared utilities)
```

### New Structure (Phase 1)
```
src/
├── ninja_coder/          (Code writing) ✅
├── ninja_secretary/      (Codebase exploration) ✅
├── ninja_researcher/     (Web search) ✅
├── ninja_resources/      (NEW - Context sharing)
├── ninja_prompts/        (NEW - Workflow templates)
└── ninja_common/         (Shared utilities) ✅
```

---

## Part 1: Resources Module (High Priority)

### Purpose
Share structured data (codebases, configs, docs) with Claude as queryable context, not raw files.

### Tools to Implement

#### 1. `resource_codebase` (CRITICAL)
**Purpose:** Share entire codebase as structured context
**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "include_patterns": ["**/*.py", "**/*.js"],
  "exclude_patterns": ["**/node_modules/**", "**/__pycache__/**"],
  "max_files": 100,
  "summarize": true
}
```

**Output:**
```json
{
  "status": "ok",
  "resource_id": "codebase-2026-01-13-abc123",
  "summary": "Web app with FastAPI backend + React frontend",
  "structure": {
    "directories": ["src/", "tests/", "frontend/"],
    "languages": ["python", "javascript"],
    "file_count": 47,
    "total_size_mb": 2.3
  },
  "files": [
    {
      "path": "src/main.py",
      "language": "python",
      "lines": 150,
      "summary": "Main FastAPI application setup",
      "functions": ["create_app", "run_server"]
    }
  ],
  "context": "Full codebase context optimized for Claude"
}
```

**Implementation Strategy:**
- Use tree-sitter to parse files (like secretary does)
- Create file summaries (not full content)
- Return structured format MCP can handle as Resource
- Compress large codebases intelligently

#### 2. `resource_config`
**Purpose:** Share configuration files with safe redaction
**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "include": [".env.example", "config.yaml", "pyproject.toml"],
  "redact_patterns": ["password", "token", "secret", "api_key"]
}
```

**Output:**
```json
{
  "status": "ok",
  "resource_id": "config-2026-01-13-xyz789",
  "files": [
    {
      "path": ".env.example",
      "content": "DATABASE_URL=postgresql://...\nAPI_KEY=***REDACTED***\n..."
    }
  ]
}
```

#### 3. `resource_docs`
**Purpose:** Share documentation as queryable index
**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "doc_patterns": ["**/*.md", "**/docs/**"],
  "include_structure": true
}
```

**Output:**
```json
{
  "status": "ok",
  "resource_id": "docs-2026-01-13-def456",
  "docs": [
    {
      "path": "README.md",
      "title": "Project Overview",
      "sections": ["Installation", "Usage", "API Reference"],
      "summary": "Main project documentation"
    }
  ],
  "searchable_index": "Built-in search capability"
}
```

### Files to Create/Modify

```
NEW FILES:
├── src/ninja_resources/
│   ├── __init__.py
│   ├── server.py                (MCP server with Tools)
│   ├── models.py                (Request/Response models)
│   ├── tools.py                 (ResourceToolExecutor)
│   ├── resource_manager.py      (Core logic)
│   ├── cache.py                 (Caching layer)
│   └── security.py              (Redaction logic)
│
├── tests/test_resources/
│   ├── __init__.py
│   ├── test_tools.py            (Unit tests)
│   ├── test_integration.py      (Integration tests)
│   └── test_security.py         (Security tests)
│
└── docs/
    └── resources_guide.md        (User documentation)
```

---

## Part 2: Prompts Module (High Priority)

### Purpose
Reusable prompt templates with variables, suggestions, and composition.

### Tools to Implement

#### 1. `prompt_registry`
**Purpose:** List, create, store prompts
**Input:**
```json
{
  "action": "list|get|create|update|delete",
  "prompt_id": "code-review-v1",
  "name": "Code Review Template",
  "description": "Review code for quality issues",
  "template": "Review this code:\n\n{code}\n\nFocus on:\n{focus_areas}",
  "variables": [
    {"name": "code", "required": true, "description": "Code to review"},
    {"name": "focus_areas", "required": false, "default": "performance, security"}
  ],
  "tags": ["code-review", "quality"],
  "scope": "user|global"  # user = ~/.ninja-mcp/prompts, global = built-in
}
```

**Output:**
```json
{
  "status": "ok",
  "prompts": [
    {
      "id": "code-review-v1",
      "name": "Code Review",
      "description": "Review code for issues",
      "variables_count": 2,
      "tags": ["code-review", "quality"],
      "created": "2026-01-13T10:30:00Z",
      "scope": "user"
    }
  ]
}
```

#### 2. `prompt_suggest`
**Purpose:** Suggest relevant prompts based on context
**Input:**
```json
{
  "context": {
    "task": "review code",
    "language": "python",
    "file_path": "src/utils.py",
    "content_preview": "def optimize()..."
  },
  "max_suggestions": 5
}
```

**Output:**
```json
{
  "status": "ok",
  "suggestions": [
    {
      "prompt_id": "code-review-v1",
      "name": "Code Review",
      "relevance_score": 0.95,
      "reason": "Matches code review context",
      "suggested_variables": {
        "code": "src/utils.py content",
        "focus_areas": "performance, maintainability"
      }
    }
  ]
}
```

#### 3. `prompt_chain`
**Purpose:** Compose multi-step workflows from prompts
**Input:**
```json
{
  "action": "list|create|execute",
  "chain_id": "feature-implementation",
  "name": "Feature Implementation Workflow",
  "steps": [
    {
      "name": "Design",
      "prompt_id": "architecture-design",
      "variables": {"feature": "user_authentication"}
    },
    {
      "name": "Implement",
      "prompt_id": "code-generation",
      "variables": {"language": "python", "architecture": "{prev.design}"}
    },
    {
      "name": "Review",
      "prompt_id": "code-review-v1",
      "variables": {"code": "{prev.implementation}"}
    }
  ]
}
```

### Files to Create/Modify

```
NEW FILES:
├── src/ninja_prompts/
│   ├── __init__.py
│   ├── server.py                (MCP server with Tools)
│   ├── models.py                (Request/Response models)
│   ├── tools.py                 (PromptToolExecutor)
│   ├── prompt_manager.py        (Core logic)
│   ├── template_engine.py       (Variable substitution)
│   ├── chain_executor.py        (Multi-step workflows)
│   ├── ai_suggester.py          (AI-powered suggestions)
│   └── builtin_prompts.py       (Default templates)
│
├── tests/test_prompts/
│   ├── __init__.py
│   ├── test_tools.py            (Unit tests)
│   ├── test_integration.py      (Integration tests)
│   └── test_chains.py           (Workflow tests)
│
├── data/builtin_prompts/
│   ├── code-review.yml
│   ├── bug-debugging.yml
│   ├── feature-implementation.yml
│   ├── architecture-design.yml
│   ├── api-documentation.yml
│   └── performance-optimization.yml
│
└── docs/
    └── prompts_guide.md         (User documentation)
```

---

## Part 3: Integration & AI Workflows

### AI Agent Role Templates

#### 1. "Code Reviewer" Role
```yaml
# ~/.ninja-mcp/workflows/code-reviewer.yml
name: Code Reviewer
description: Professional code review assistant

system_prompt: |
  You are an expert code reviewer with 10+ years of experience.
  Focus on: readability, performance, security, maintainability.
  Provide specific, actionable feedback.

tools:
  - resource_codebase    # Access full codebase for context
  - prompt_chain         # Use code-review workflow
  - secretary_analyse_file

workflow:
  - step: "Load context"
    tools: [resource_codebase]

  - step: "Suggest review prompt"
    tools: [prompt_suggest]

  - step: "Execute code review"
    tools: [prompt_chain: "code-review-workflow"]
```

#### 2. "Feature Developer" Role
```yaml
# ~/.ninja-mcp/workflows/feature-developer.yml
name: Feature Developer
description: Full-stack feature implementation

system_prompt: |
  You are a senior full-stack developer.
  Implement features end-to-end: design, code, test, document.
  Follow best practices and project conventions.

tools:
  - resource_codebase
  - resource_config
  - resource_docs
  - prompt_chain
  - coder_simple_task
  - test_runner
  - git operations (coming)

workflow:
  - step: "Understand project"
    tools: [resource_codebase, resource_docs]

  - step: "Execute feature workflow"
    tools: [prompt_chain: "feature-implementation"]
```

#### 3. "Bug Debugger" Role
```yaml
# ~/.ninja-mcp/workflows/bug-debugger.yml
name: Bug Debugger
description: Systematic bug investigation and fixing

system_prompt: |
  You are an expert debugger. Follow scientific method:
  1. Understand the bug (reproduce, isolate)
  2. Form hypothesis
  3. Test hypothesis
  4. Implement fix
  5. Verify solution

tools:
  - resource_codebase
  - prompt_chain
  - secretary_analyse_file
  - test_runner (coming)
```

### Built-in Prompt Templates

**Location:** `data/builtin_prompts/*.yml`

#### code-review.yml
```yaml
id: code-review-v1
name: Code Review
description: Professional code review workflow

variables:
  code:
    required: true
    description: Code to review
  focus_areas:
    default: "performance, security, maintainability"
    description: Areas to focus review on
  context:
    description: Additional context about the code

template: |
  Review this {language} code for quality issues:

  {code}

  Focus on: {focus_areas}
  {context}

  Provide:
  1. Issues found (severity: critical/major/minor)
  2. Specific improvement suggestions
  3. Positive observations
  4. Overall assessment
```

#### feature-implementation.yml
```yaml
id: feature-implementation-v1
name: Feature Implementation Workflow
description: Complete feature from design to docs

steps:
  - name: Design
    prompt: architecture-design
    variables:
      feature: "{{feature_name}}"
      context: "{{codebase_context}}"

  - name: Implement
    prompt: code-generation
    variables:
      language: "{{language}}"
      design: "{{steps[0].output}}"

  - name: Test
    prompt: test-generation
    variables:
      code: "{{steps[1].output}}"

  - name: Review
    prompt: code-review-v1
    variables:
      code: "{{steps[1].output}}"

  - name: Document
    prompt: api-documentation
    variables:
      code: "{{steps[1].output}}"
```

---

## Part 4: Testing Strategy

### Unit Tests (Per Module)
- Resources: File parsing, caching, redaction
- Prompts: Template rendering, variable substitution, chain execution

### Integration Tests
- Resources + Secretary: Share codebase, then explore it
- Prompts + Coder: Use prompt to generate code, execute it
- Full workflow: Load context → suggest prompts → execute chain

### Example Tests
```python
# test_resources_integration.py
def test_full_workflow():
    # 1. Load codebase resource
    resource = await resource_codebase(...)

    # 2. Query file from resource
    file_info = await secretary_analyse_file(
        file_path="src/main.py",
        resource_context=resource.resource_id
    )

    # 3. Suggest relevant prompts
    suggestions = await prompt_suggest(
        context=file_info,
        max_suggestions=3
    )

    # 4. Execute code review workflow
    result = await prompt_chain(
        chain_id="code-review",
        variables={"code": file_info.content}
    )

    assert result.status == "ok"
```

---

## Implementation Order

### Day 1: Foundation
1. ✅ Create module structures (ninja_resources, ninja_prompts)
2. ✅ Create models and servers
3. ✅ Implement resource_codebase (core tool)
4. Create basic tests

### Day 2: Resources Completion
5. Implement resource_config + resource_docs
6. Create caching layer
7. Implement security redaction
8. Complete unit tests

### Day 3: Prompts Core
9. Implement prompt_registry
10. Implement prompt_suggest (with basic AI)
11. Create test coverage

### Day 4: Prompts & Workflows
12. Implement prompt_chain
13. Create builtin prompt templates
14. Create AI role templates

### Day 5: Integration & Polish
15. Create integration tests
16. Documentation and examples
17. Example workflows
18. Merge-ready code

---

## Success Criteria

### Functional
- [ ] Resources module loads and caches codebases
- [ ] Prompts module stores and retrieves templates
- [ ] prompt_suggest works with AI
- [ ] prompt_chain executes multi-step workflows
- [ ] All 16 tests passing (unit + integration)

### Quality
- [ ] 90%+ test coverage
- [ ] All tools documented
- [ ] Example workflows functional
- [ ] Security: API keys redacted, no PII exposure

### UX
- [ ] Clear decision tree for tool selection
- [ ] Example prompts immediately useful
- [ ] Workflows reduce manual work by 50%

---

## Git Workflow

```bash
# Current branch: feature/phase1-resources-prompts

# Commits pattern:
# feat: Add ninja-resources module with resource_codebase
# feat: Implement resource_config and resource_docs tools
# feat: Add ninja-prompts module with prompt management
# feat: Create builtin prompt templates
# test: Add comprehensive test coverage
# docs: Complete user and API documentation

# Final: Create PR to main with all features
```

---

## Key Integration Points

### With ninja-secretary
- Use secretary's file parsing logic
- Leverage tree-sitter language support
- Share similar output structures

### With ninja-coder
- Resources provide context for code writing
- Prompts guide code generation
- Output flows into coder tasks

### With MCP Core
- Resources become MCP Resources type
- Prompts integrate with MCP sampling
- Full MCP feature parity

---

## Timeline & Milestones

- **Day 1 End:** Resources module structure + resource_codebase working
- **Day 2 End:** All resources tools implemented and tested
- **Day 3 End:** Prompts core functionality working
- **Day 4 End:** Full workflows operational
- **Day 5 End:** Production-ready, documented, tested

---

## Next Steps After Phase 1

Once complete, Phase 2 adds:
- Version Control (git operations)
- Testing integration
- Full dev cycle automation

Total: Complete development cycle without leaving Claude.
