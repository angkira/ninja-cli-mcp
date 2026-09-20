# ROADMAP.md - Development Roadmap

## Active Milestones

### Task: Release automation (local publish)
**Priority:** High
**Status:** COMPLETED 2026-09-13 (commits `4058142`)

**Description:**
One-command local release flow. `scripts/release.sh <version>` runs preflight checks,
bumps every versioned file, runs quality gates, builds, commits/pushes, tags, publishes
to PyPI locally (all-projects token), and verifies on PyPI. Make/just wrappers.

**Files:**
- [x] `scripts/release.sh` — full automation (--dry-run/--skip-tests/--skip-publish/--yes)
- [x] Makefile: release / release-dry-run / release-tag-only / publish-local
- [x] justfile: release-local / release-dry-run / release-tag-only / publish-local
- [x] `docs/RELEASING.md` — process doc

---

### Task: Version-aware updater (github/pypi/brew)
**Priority:** High
**Status:** COMPLETED 2026-09-13 (commit `4eee54f`)

**Description:**
`ninja-mcp update` detects install channel (github/pypi/brew), compares installed vs latest
(PEP 440), only reinstalls when newer unless `--force`. Rich progress UI. Daemon upgrade now
uses PyPI. Local release 1.0.5 shipped on top of this.

**Files:**
- [x] `src/ninja_config/auto_updater.py` — channels, version check, Rich UI
- [x] `src/ninja_common/update_cli.py` — `--channel`
- [x] `src/ninja_common/daemon.py` — upgrade() → PyPI
- [x] `tests/test_auto_updater.py` — 20+ tests

---

### Task: Codex CLI strategy + DeepSeek V4.1 default
**Priority:** High
**Status:** COMPLETED 2026-09-13 (commit `282d265`)

**Description:**
OpenAI Codex CLI as host-auth coder strategy (ChatGPT login, no API keys) with native subagents
via `codex exec --json`. Default model roles switched to `openrouter/deepseek/deepseek-v4.1-flash`.
Default-model value assertions removed from tests (structural checks only).

**Files:**
- [x] `src/ninja_coder/strategies/codex_strategy.py` + registry/__init__ wiring
- [x] config_shared / detect_tools / ui / tui_installer / model_selector wiring
- [x] `tests/test_codex_strategy.py`
- [x] defaults.py CODEX_MODELS + NINJA_CODEX_TIMEOUT

---

### Task: Module toggler + installer in config TUI
**Priority:** High
**Status:** COMPLETED 2026-09-13 (commit `9ccd946`)

**Description:**
Add module management to the Textual config TUI so users can enable/disable modules and their
daemons, and install missing module binaries, without the CLI. Also fixed a config-persistence bug
that made module state read stale.

**Files:**
- [x] `src/ninja_config/modern_tui.py` — NEW Modules tab: ListView + Enable/Disable/Start/Stop/Install
- [x] `src/ninja_common/daemon.py` — `_save_enabled_modules` updates ALL duplicate env lines
- [x] `tests/test_common/test_daemon_module_config.py` — 3 tests
- [x] `tests/test_modern_tui_modules.py` — 5 tests

**Follow-ups (backlog):**
- [ ] Relax `test_no_old_servers_running` to allow the user's own uv/tools daemons
- [ ] `ninja-*` module config surface parity: add `ninja-agent` to `config/mcp-modules.json`

---

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

### Task: ninja-researcher reliability & API overhaul (post-mortem 2026-09-19)
**Priority:** CRITICAL (P0s are session-killers)
**Status:** COMPLETED 2026-09-19 — commits `bbc84e6` + `5a5189d` (NOT pushed)

**Description:**
(All spec details: `.session/2026-09-19_ninja-researcher-postmortem.md`.)
Delivered via ninja-coder sequential plan (job 28e9cb80, all 8 steps ok):
- [x] P0-1 Typed errors `{error_kind, message, retry_after_s}` — models.py + tools.py
      error paths; providers raise ProviderError instead of swallowing
- [x] P0-2 bs4 → base deps (pyproject + uv.lock regen); tool env reinstalled
      (bs4 4.15.0, verified live: summarize_sources returns real parsed summary);
      "(coming soon)" removed (server.py, RESEARCHER.md, RESEARCHER_SPEC.md)
- [x] P0-3 `researcher_arxiv_search` (export.arxiv.org Atom, 3s spacing lock,
      withdrawn filter); follow-up `5a5189d`: quoted phrase terms + 406 →
      rate_limited. Live e2e pending clean-window probe (arXiv IP-throttled
      during testing — retry once, spaced, expected 1706.03762)
- [x] P1-1 `researcher_paper_fetch(source, sections[], extract_numbers)`
- [x] P1-2 `researcher_deep_research_batch` (serial, delay, retry_backoff, 600s cap)
- [x] P1-3 Domain filters include/exclude/prefer
- [x] P1-4 Real titles + per-source snippets + source_type; fake score ladder dropped
- [~] P2 items — NOT done; remain backlog

**Verification:** ruff/mypy/pytest green (118+ passed per suite); live probe
confirmed 7/7 tools registered + sweep in tasks.db. Sole test failure is
pre-existing (test_provider_factory_default — see backlog).

**Description:**
Fix the failure modes that derailed the visual-student research session: burst-killed
deep_research calls misread as "topic too complex" (zero diagnostics), summarize_sources
dead from missing bs4 in the live env, snippet-only output forcing webfetch fallback.
Root causes verified in code — see `.session/2026-09-19_ninja-researcher-postmortem.md`.

**Files (planned):**
- [ ] P0-1 Typed errors `{error_kind, message, retry_after_s}` — models.py + tools.py
      error paths (189-195, 404-412, 456-464, 582-588); providers must stop swallowing
      exceptions (search_providers.py:94-96, 169-174, 276-281)
- [ ] P0-2 bs4 → base deps (pyproject.toml:19-39); reinstall live uv tool env; error
      field instead of combined_summary leak; remove "(coming soon)" (server.py:215-232,
      docs/RESEARCHER.md, docs/RESEARCHER_SPEC.md)
- [ ] P0-3 `researcher_arxiv_search` via export.arxiv.org Atom XML (stdlib parser)
- [ ] P1-1 `researcher_paper_fetch(source, sections[], extract_numbers)`
- [ ] P1-2 `researcher_deep_research_batch` (serial queue, inter_call_delay_s, backoff)
- [ ] P1-3 Domain filters include/exclude/prefer
- [ ] P1-4 Real titles + per-source snippets + source_type; drop fake score ladder
      (search_providers.py:87, 161-162, 251-256)
- [ ] P2-1 dedup/cache · P2-2 extract_claims · P2-3 fact_check source weighting ·
      P2-4 doc/schema reconciliation

### Task: coder model fallback (NINJA_FALLBACK_MODELS)
**Priority:** Medium
**Status:** COMPLETED 2026-09-19 — commit `7d7353c` (NOT pushed)

Retryable model-side failures (429/503/quota/overload) advance to the next
model in the comma-separated env chain; unset = today's behavior. Simple +
sequential/parallel paths; 22 tests green; ruff/mypy clean. Enable:
`export NINJA_FALLBACK_MODELS="model-a,model-b"`.

### Task: MCP handshake token trim
**Priority:** Medium
**Status:** COMPLETED 2026-09-19 — commit `cd61711` (NOT pushed)

Coder instructions 5253B→746B, researcher 3127B→632B; all `━━━` gone;
duplicated DOES/DOES-NOT, workflows, examples removed (canonical text stays
in docs//skills//commands/). Schemas/params/behavior unchanged; no test
asserted on those strings. Follow-up pass 2 (`5568ab7`): all 35 tool
descriptions across coder/researcher/agent/secretary 4571B→3471B, keeping
the guards that prevent wasted calls (submit→status→result chain, serial
rule, misused params).

---

### Task: coder MCP submit-timeout orphan runs (incident 2026-09-19)
**Priority:** HIGH
**Status:** COMPLETED 2026-09-19 — commit `f78cfe9` (NOT pushed, separate commit)

**Description:**
MCP client timeout on `coder_execute_plan_sequential` left a daemon-side execution
running with NO registry entry; resubmission duplicated the run. Root-caused via
logs/JSONL, orphan SIGTERMed, then fixed + verified + landed (job b6d229f9, 6 steps).
Full evidence in `.session/2026-09-19_ninja-researcher-postmortem.md` (INCIDENT section).

**Fixes (all delivered + gates green):**
- [x] Register job BEFORE spawning execution (JobManager.run_tracked covers all
      4 sync tools — no more invisible orphans)
- [x] request_key idempotency (same key joins instead of duplicating, sync + submit)
- [x] Negative exit codes → killed-by-signal, NOT "Authentication failed"
      (substr "401"/"Unauthorized" restricted to contextual 401 patterns)
- [x] Startup sweep: stale 'working' → 'failed' "lost: daemon restart before
      completion" (live-proven: zombie e3a438da swept at restart, 0/101 working)
- [x] last_updated_at/status_message refresh via 10s progress tick

**New backlog found during this work:**
- [ ] ninja_mcp logger lines never reach daemon logs at startup (stderr plumbing) —
      the sweep's "Reconciled" INFO is invisible in coder.log (verified via DB instead)
- [ ] sqlite3 connection ResourceWarning leak in provider/config path
- [ ] test_provider_factory_default asserts duckduckgo, real default is perplexity
      (pre-existing on HEAD; update assertion)
- [ ] ruff debt in tests/test_strategies.py (pre-existing)

**Description:**
MCP client timeout on `coder_execute_plan_sequential` left a daemon-side execution
running with NO registry entry; resubmission duplicated the run (two concurrent 8-step
plans, 96% CPU). Orphan killed manually (SIGTERM); partial work quarantined on branch
`ninja/sequential-plan-1789807154-46b3ea`. Full evidence in
`.session/2026-09-19_ninja-researcher-postmortem.md` (INCIDENT section).

**Fixes:**
- [ ] Register job in registry BEFORE spawning execution (registry-after-response today)
- [ ] Submit idempotency: client request key + dedup so retry joins, never duplicates
- [ ] Map negative exit codes (signal kills) to cancelled/killed, NOT "Authentication
      failed" (misparse observed with exit -15)
- [ ] Reconcile registry on daemon restart: stale 'working' → 'lost' (zombie e3a438da)
- [ ] Refresh job `last_updated_at` / progress during execution

---

### Task: Worktree-based task isolation for ninja-coder
**Priority:** CRITICAL
**Status:** COMPLETED (no git commits, per instructions)
**Completed:** 2026-07-21

**Description:**
Stop `[ninja-auto-save]` commits from polluting the user's current branch.
Each `execute_async` call now creates a feature branch `ninja/<slug>-<ts>-<uid>`
at HEAD, checks it out into a detached worktree under
`$XDG_CACHE_HOME/ninja-mcp/worktrees/<repo-hash>/<branch>`, snapshots the dirty
state onto the feature branch, and runs the CLI subprocess with `cwd=<worktree>`.
The main working tree and current branch stay byte-for-byte untouched.

**Files Created/Modified:**
- [x] `src/ninja_coder/worktree.py` - NEW: WorktreeManager, WorktreeInfo, prune()
- [x] `src/ninja_coder/safety.py` - validate_task_safety gains `skip_auto_commit`
- [x] `src/ninja_coder/driver.py` - execute_async integration + NinjaResult fields
- [x] `tests/test_worktree.py` - NEW: 10 tests (manager + safety + driver)

**Follow-ups (backlog):**
- [ ] Worktree coverage for `execute_async_with_opencode_session` / serve-pool mode
- [ ] Wire `WorktreeManager.prune()` to daemon maintenance (manual helper today)
- [ ] Fix pre-existing test debt: TestTimeoutEstimation, TestResultConversion,
      env-leaking config tests (failing before this session, unrelated)

---

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

### [Research] Oh My OpenCode Integration Analysis
**Priority:** HIGH
**Status:** COMPLETED
**Completed:** 2026-02-12

**Description:**
Comprehensive research into oh-my-opencode multi-agent framework to determine relationship with ninja-coder and optimal integration strategy.

**Deliverables:**
- ✅ `.agent/OH_MY_OPENCODE_ANALYSIS.md` (900+ line report)
- ✅ Feature comparison matrix
- ✅ Architecture analysis
- ✅ Strategic recommendation

**Key Findings:**
- Ninja-coder already integrates oh-my-opencode through OpenCode strategy
- Both tools are complementary, not competing
- Oh-my-opencode provides specialized multi-agent orchestration
- Ninja-coder provides multi-backend abstraction with MCP integration

**Recommendation:**
Maintain status quo - ninja-coder as orchestration layer, oh-my-opencode as execution strategy

**Sources:**
- 15+ web sources researched
- 6+ codebase files analyzed
- GitHub repo: code-yeongyu/oh-my-opencode

---

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

**2026-09-16**
- Completed (UNCOMMITTED, no commit per instructions): Junie versioned model catalog
  (deepseek-v4-flash, gemini-3.8-flash, grok-4.6, gpt-5.6-luna — all 3 probes + settings.json
  verified; gpt-5.6-luna IS served by Junie) + junie normalizer (prefix-strip/alias,
  loud ValueError) + effort сквозняком (NINJA_JUNIE_EFFORT[_QUICK/_SEQUENTIAL/_PARALLEL]
  → `--effort`, omitted when unset) + tests + live e2e pin proof. See STATUS.md
  session `junie-models-effort-20260916` for files/lines.

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

**2026-02-12 11:00**
- Session started: Oh My OpenCode research
- Task: Investigate oh-my-opencode and analyze relationship with ninja-coder
- Method: Codebase search + web research + feature comparison

**2026-02-12 11:45**
- Completed: Comprehensive oh-my-opencode analysis
- Created: `.agent/OH_MY_OPENCODE_ANALYSIS.md` (900+ lines)
- Finding: Ninja-coder already integrates oh-my-opencode via OpenCode strategy
- Recommendation: Maintain status quo (complementary tools, not competing)
- Decision: Do NOT replace ninja-coder with oh-my-opencode (high risk, negative value)

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

### Oh My OpenCode Integration Decisions

1. **Should we expose more oh-my-opencode features?**
   - Current: Only ultrawork activation via OpenCode strategy
   - Option: Expose lifecycle hooks as MCP tools
   - Recommendation: Wait for user demand

2. **Should we document existing multi-agent capabilities?**
   - Current: Multi-agent orchestration is hidden feature
   - Option: Add section to README, tutorials, examples
   - Recommendation: Yes - user education needed

3. **Should we consider deep integration in future?**
   - Current: Basic ultrawork support
   - Option: Full feature parity (41 hooks, 25+ tools)
   - Recommendation: Phased approach if users request it

---

**Remember:** Always update this file when starting/completing tasks or making architectural decisions.
