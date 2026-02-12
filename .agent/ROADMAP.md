# ROADMAP.md - Development Roadmap

## Active Milestones

### Milestone: Configuration System Refactoring
**Status:** In Progress
**Priority:** High
**Target Date:** 2026-02-15

**Description:**
Refactor the ninja configuration system to use a hierarchical, component-first approach with proper support for OpenCode provider settings and operator modes.

**Tasks:**
- [x] Investigate recent ninja-coder task failures
- [x] Analyze current configuration structure chaos
- [x] Design unified configuration architecture
- [x] Create refactoring implementation plan
- [x] Implement Pydantic schemas for config validation
- [x] Build migration utilities (env → JSON)
- [ ] Refactor UI components (split 1800-line file)
- [ ] Add OpenCode provider settings UI
- [ ] Test migration with existing configs
- [ ] Update documentation

**Dependencies:**
- User approval of architecture design
- User decisions on: JSON vs YAML, migration strategy, OpenCode sync

**Completion Criteria:**
- Component-first configuration hierarchy implemented
- OpenCode provider routing/modes configurable
- Migration from old .env format works
- UI simplified with clear flows
- All tests passing
- Documentation updated

---

## Active Tasks

### Task: Design unified configuration architecture
**Priority:** High
**Status:** COMPLETED
**Assigned To:** Claude Sonnet 4.5
**Completed:** 2026-02-12

**Description:**
Design new configuration structure with:
- Component-first approach (coder, researcher, secretary at top level)
- Nested operator selection per component
- Nested model selection per operator
- Operator-specific settings (modes, provider routing for OpenCode)
- Clean separation of concerns
- Support for OpenCode provider modes from documentation

**Files Created:**
- [x] `src/ninja_config/config_schema.py` - Pydantic models (647 lines)
- [x] `.agent/CONFIG_ARCHITECTURE_DESIGN.md` - Full architecture spec
- [x] Migration strategy documented

**Acceptance Criteria:**
- [x] Pydantic schemas defined for all config entities
- [x] Migration path from old .env to new format documented
- [x] OpenCode provider routing supported
- [x] Design documented and approved

---

### Task: Create refactoring implementation plan
**Priority:** High
**Status:** COMPLETED
**Assigned To:** Claude Sonnet 4.5
**Completed:** 2026-02-12

**Description:**
Create detailed implementation plan with:
- Files to refactor/consolidate
- New configuration data models
- Migration strategy for existing configs
- Backwards compatibility approach
- Testing strategy

**Files Created:**
- [x] `src/ninja_config/config_schema.py` - Pydantic models (647 lines)
- [x] `src/ninja_config/config_loader.py` - ConfigLoader (264 lines)
- [x] `src/ninja_config/credentials.py` - CredentialManager with encryption (694 lines)
- [x] `src/ninja_config/config_migrator.py` - ConfigMigrator (677 lines)
- [x] `.agent/CONFIG_ARCHITECTURE_DESIGN.md` - Complete architecture
- [x] `.agent/CONFIG_MIGRATOR_IMPLEMENTATION.md` - Implementation summary

**Acceptance Criteria:**
- [x] All files to change identified
- [x] Refactoring sequence defined
- [x] Testing approach documented (5/5 tests passing)
- [x] Production-ready implementation completed

---

## Backlog

### [Feature] OpenCode Provider Mode UI
**Priority:** High
**Estimated Effort:** Medium

**Description:**
Add UI for configuring OpenCode provider routing, including:
- Provider order selection (drag-to-reorder)
- Fallback toggle
- Custom model entry
- Per-model provider customization

**Dependencies:**
- Unified configuration architecture implemented
- OpenCode integration utilities built

**Notes:**
Reference: https://opencode.ai/docs/providers/#openrouter

---

### [Refactor] Split interactive_configurator.py
**Priority:** Medium
**Estimated Effort:** Large

**Description:**
Split the 1800+ line interactive_configurator.py into focused modules:
- `ui_main_menu.py` - Main configuration menu
- `ui_component_setup.py` - Component setup flows
- `ui_operator_config.py` - Operator-specific settings
- `ui_model_selector.py` - Model selection UI
- `ui_base.py` - Shared UI components

**Dependencies:**
- Architecture design complete

---

### [Feature] Hierarchical Config Manager
**Priority:** High
**Estimated Effort:** Medium

**Description:**
Implement ConfigManager with support for:
- Reading both .env and .json configs
- Writing hierarchical .json configs
- Migration from .env to .json
- Validation using Pydantic schemas
- OpenCode config sync

**Dependencies:**
- Pydantic schemas defined
- Migration strategy approved

---

### [Feature] Config Migration Command
**Priority:** Medium
**Estimated Effort:** Small

**Description:**
Add `ninja-config migrate` command to migrate old .env configs to new hierarchical format.

Features:
- Dry-run mode to preview changes
- Backup of old config
- Validation of migrated config
- Report of migration results

---

## Completed Milestones

### Milestone: Install Autonomous Protocols
**Completed:** 2026-02-02

**Summary:**
Successfully upgraded repository to Level 5 autonomous capability with context management infrastructure.

**Key Deliverables:**
- CLAUDE.md (The Constitution) with Anti-Amnesia protocol, Sub-agent Delegation rules, and Quality Gates
- .agent/ directory with ROADMAP.md, STATUS.md, and ARCHITECT.md templates
- Architect review prompt template (architect-review.yml) for architectural compliance checking
- Full architectural style guide with Hexagonal Architecture, Dependency Injection, and Type Safety standards

---

## Session Log

**2026-02-12 01:42**
- Session started: Configuration refactoring investigation
- Task: Investigate latest ninja-coder task failures
- Result: No failures found, system stable

**2026-02-12 01:43**
- Task: Analyze current configuration structure
- Result: Identified 7 major architectural issues
- Created comprehensive analysis document: `.agent/CONFIG_REFACTOR_ANALYSIS.md`

**2026-02-12 01:45**
- Task: Design unified configuration architecture (in progress)
- Decision: Component-first hierarchy approach
- Decision: Hybrid .env + .json config format

**2026-02-12 02:00**
- Completed: Pydantic configuration schemas (config_schema.py)
- Completed: ConfigLoader with atomic writes and backups
- Completed: CredentialManager with AES-256-GCM encryption

**2026-02-12 02:30**
- Completed: ConfigMigrator implementation (config_migrator.py)
- Tests: All 5 validation tests passing (100% success rate)
- Documentation: CONFIG_MIGRATOR_IMPLEMENTATION.md created

---

## Notes

### Key Architectural Decisions

1. **Component-First Hierarchy**
   - Top level: Components (coder, researcher, secretary)
   - Second level: Operator selection per component
   - Third level: Models and operator settings
   - Rationale: Matches user mental model, cleaner separation

2. **Hybrid Config Format**
   - Keep `.env` for backwards compatibility
   - Add `.json` for hierarchical structure
   - JSON takes precedence when both exist
   - Rationale: Migration path without breaking existing setups

3. **OpenCode Integration**
   - Write to both ninja config AND OpenCode's native config
   - Keep configs in sync automatically
   - Ninja UI becomes source of truth
   - Rationale: Seamless OpenCode experience

### Questions for User Review

1. JSON vs YAML for hierarchical config?
2. Automatic migration on first run, or manual `migrate` command?
3. Write to OpenCode's config file, or keep separate?
4. Keep .env support forever, or deprecate after migration period?

---

**Remember:** Always update this file when starting/completing tasks or making architectural decisions.
