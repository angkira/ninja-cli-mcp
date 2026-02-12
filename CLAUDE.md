# CLAUDE.md - The Constitution

This file defines the operating principles for autonomous development sessions in this repository.

## The Anti-Amnesia Protocol

**MANDATORY STARTUP CHECKLIST:**
1. Read `.agent/STATUS.md` to understand current session context
2. Read `.agent/ROADMAP.md` to see active milestones and backlog
3. Read `.agent/ARCHITECT.md` to understand architectural patterns
4. Check for recent commits or changes using `secretary_codebase_report`
5. Read any relevant session logs or notes

**MANDATORY SHUTDOWN PROCEDURES:**
1. Update `.agent/STATUS.md` with current session state
2. Update `.agent/ROADMAP.md` with any completed tasks or new backlog items
3. Log all significant decisions or architectural choices made
4. Mark completed tasks with `[x]`

## Sub-agent Delegation Rules

**WHEN TO DELEGATE:**
- Complex multi-step implementation tasks
- Large refactoring requiring careful coordination
- Tasks requiring specialized tools (e.g., `coder_execute_plan_sequential`)
- Analysis tasks requiring multiple passes

**DELEGATION PROTOCOL:**
1. Use `coder_execute_plan_sequential` for dependent tasks
2. Use `coder_execute_plan_parallel` for independent tasks
3. Always provide detailed specifications to sub-agents
4. Include context from `.agent/` files in delegation prompts
5. Verify sub-agent outputs against `.agent/ARCHITECT.md` standards

**SUB-AGENT COMMUNICATION:**
- Always reference file locations with `file_path:line_number` format
- Provide clear acceptance criteria for each task
- Include error handling strategies
- Set expectations for verification steps

## Quality Gates

**ARCHITECTURAL COMPLIANCE:**
- All code must follow Hexagonal Architecture principles
- Dependency Injection is mandatory (no direct instantiation of dependencies)
- Type safety is required (use pydantic models, type hints)
- No circular dependencies allowed
- Clear separation between domain logic and infrastructure

**CODE REVIEW GATES:**
- All code must pass linting (ruff)
- All code must pass type checking (mypy)
- All public functions must have docstrings
- All changes must be covered by tests
- No commented-out code allowed

**ARCHITECTURAL REVIEW:**
- Use architect review prompt to grade all new code
- PASS criteria:
  - **Isolation**: Domain logic independent of external concerns
  - **Dependency Injection**: All dependencies injected, not instantiated
  - **Type Safety**: Full type coverage, no `Any` or `ignore` comments

## Session Management

**SESSION CONTEXT:**
- Always maintain `.agent/STATUS.md` as the source of truth
- Update ROADMAP when priorities change
- Document blockers or dependencies clearly
- Log architectural decisions with rationale

**CONTINUITY PROTOCOL:**
- When resuming work, always start with Anti-Amnesia Protocol
- If context is unclear, ask for clarification before proceeding
- Never assume previous session's state without verification
- Use `secretary_file_tree` to verify codebase state

## Tool Usage Guidelines

**SECRETARY MODULE:**
- Use `secretary_codebase_report` for initial analysis
- Use `secretary_analyse_file` to understand specific files
- Use `secretary_file_search` to locate relevant code
- Use `secretary_file_tree` for project structure overview

**CODER MODULE:**
- Use `coder_execute_plan_sequential` for complex implementation
- Use `coder_execute_plan_parallel` for independent tasks
- Always specify files to modify explicitly
- Include test steps in execution plans

**PROMPTS MODULE:**
- Use `prompt_registry` to find relevant templates
- Use `prompt_chain` for multi-step workflows
- Always validate prompt variables before execution

## Emergency Protocols

**IF CONTEXT IS LOST:**
1. Run full codebase analysis
2. Re-read all `.agent/` files
3. Check git history for recent changes
4. Reconstruct session state from available information

**IF ARCHITECTURAL VIOLATIONS FOUND:**
1. Document the violation in STATUS.md
2. Create refactoring task in ROADMAP.md
3. Use architect review to assess impact
4. Schedule remediation in backlog

## Success Metrics

- All tasks in `.agent/ROADMAP.md` have clear acceptance criteria
- All code passes architectural review gates
- Session state is recoverable after interruption
- Zero architectural violations in new code
- All documentation is up-to-date

---

**REMEMBER:** This Constitution ensures continuity across sessions. Follow it faithfully to maintain project coherence.
