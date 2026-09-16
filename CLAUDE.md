# CLAUDE.md - The Constitution

This file defines the operating principles for autonomous development sessions in this repository.

## The Anti-Amnesia Protocol

**MANDATORY STARTUP CHECKLIST:**
1. Read `.agent/STATUS.md` to understand current session context
2. Read `.agent/ROADMAP.md` to see active milestones and backlog
3. Read `.agent/ARCHITECT.md` to understand architectural patterns
4. Read `.agent/ORIENTATION.md` for a quick map of how the repo is organized
5. Check for recent commits or changes using `secretary_codebase_report`
6. Read any relevant session logs or notes

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
- All public functions must have docstrings
- All changes must be covered by tests

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

## Emergency Protocols

If context is lost or an architectural violation is found mid-session, see the `emergency-recovery` skill.

---

**REMEMBER:** This Constitution ensures continuity across sessions. Follow it faithfully to maintain project coherence.
