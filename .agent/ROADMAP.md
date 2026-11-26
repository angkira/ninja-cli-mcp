# ROADMAP.md - Development Roadmap

## Active Milestones

### Milestone: MCP 2.0 — SDK 2.3.0 / protocol 2026-07-28
**Priority:** High
**Status:** COMPLETED 2026-11-25 (released v2.0.0, commit `91ab555`, tag pushed, PyPI published)

**Description:**
Port all four servers to `mcp>=2.3.0` and serve protocol revision `2026-07-28`
alongside legacy revisions from one server object, implementing the four
capabilities shipped on that revision: Skills over MCP, the Tasks extension, MRTR
elicitation, and experimental inline file uploads.

**Files:**
- [x] `src/ninja_common/mcp_ext/` — `protocol.py`, `models.py`, `tasks_store.py`, `tasks.py`, `tasks_client.py`, `skills.py`, `apply.py`, `wiring.py`, `files.py`
- [x] `src/ninja_common/mcp_http.py` — `build_asgi_app`: `/mcp` Streamable HTTP + legacy `/sse`
- [x] `src/ninja_{coder,researcher,secretary,agent}/server.py` — v2 lowlevel constructor-registered handlers
- [x] `src/ninja_common/dist/skills/<module>/` — 11 `SKILL.md` bundles (coder 4, researcher 3, secretary 2, agent 2)
- [x] `tests/test_mcp_protocol_extensions.py`, `tests/test_mcp_elicitation.py`, `tests/test_common/mcp_ext/*`
- [x] `docs/MCP_PROTOCOL_2026.md`; `docs/MCP_TASKS.md` rewritten; `RESOURCES_API`/`PROMPTS_API`/secretary/researcher docs corrected

**Verification:** full suite 1953 passed / 26 skipped + 5 pre-existing environment
failures; `ruff`/`mypy` clean on `src`; live `/mcp` 2026-07-28 handshake; PyPI 2.0.0.

---

### Task: Pi (pi.dev) CLI operator & MCP init integration
**Priority:** High
**Status:** COMPLETED 2026-10-11

**Description:**
Add Pi (pi.dev) as a possible ninja CLI operator in ninja-coder (`pi` strategy, dynamic discovery, thinking levels) and as an MCP init target (`ninja-mcp init pi` merges ninja servers into `~/.pi/agent/mcp.json`).

**Files:**
- [x] `src/ninja_common/init_targets/pi.py` — `JsonMcpTarget` for `~/.pi/agent/mcp.json`
- [x] `src/ninja_common/init_cli.py` — registered `pi` target and detection
- [x] `src/ninja_coder/strategies/pi_strategy.py` — `PiStrategy` (JSONL events parsing, timeout, retryable errors)
- [x] `src/ninja_coder/strategies/__init__.py` & `registry.py` — strategy registration & detection
- [x] `src/ninja_coder/driver.py` — `resolve_pi_thinking` flag wiring
- [x] `src/ninja_common/defaults.py` — `PI_MODELS`, `PI_THINKING_LEVELS`, operator defaults
- [x] `src/ninja_common/pi_discovery.py` — dynamic discovery (`pi --list-models`, settings.json)
- [x] `src/ninja_common/operator_models.py` — operator model routing, normalizer, thinking resolution
- [x] `src/ninja_config/` (model_selector, config_shared, modern_tui, tui_installer, ui, settings_registry) — full config & UI integration
- [x] `tests/test_pi_strategy.py`, `tests/test_pi_discovery.py`, `tests/test_init_targets.py`, `tests/test_init_cli.py` — comprehensive test suite (all green)

---

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
- [x] Relax `test_no_old_servers_running` to allow the user's own uv/tools daemons (2.1.0: skips when an active `ninja-mcp@*` systemd user unit owns the process)
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

### [Bug] `daemon restart` is a silent no-op under systemd
**Priority:** HIGH
**Status:** FIXED (2.0.1) — commit `12c2e0a` (`fix(daemon): restart systemd-managed units and report stale code honestly`)

**Description:**
`src/ninja_common/daemon.py` `restart()` (≈:814) is `stop()` + `start()`. `stop()`
(≈:687) only acts on PID files; systemd-managed units (`ninja-mcp@<module>.service`)
have none, so it logs "not running" and returns `True` without doing anything.
`start()` (≈:547) then sees the port already served and returns immediately.

Observed 2026-11-25: `ninja-mcp daemon restart` printed `✓` for all four modules
while every MainPID stayed unchanged; the process kept running ~6-hour-old 1.9.x
code after an upgrade to 2.0.0. The only `systemctl` call in the codebase is
read-only `is-active` (≈:390); there is no systemd restart path in `ninja-mcp` or
`ninja-daemon`.

**Fix direction:**
Detect systemd ownership (unit active + MainPID present) and restart via the user
unit; otherwise fall back to the PID-file path. Add a test.

---

### [Bug] `ninja-mcp version` / `daemon status` report the wrong version for running daemons
**Priority:** Medium
**Status:** FIXED (2.0.1) — commit `12c2e0a`

**Description:**
The reported version comes from `__import__(module).__version__` inside the CLI
process, so after an upgrade it reports the new version while the running daemon
is still the old code. Report the version the live process actually loaded (or
clearly label it as the on-disk version).

---

### [Bug] QA model routing resolves `quick` to `qwen/qwen3-coder` (rejected by operator)
**Priority:** HIGH
**Status:** FIXED (2.1.0) — commit `d8bdb0d` (`fix(coder): resolve task models from config when the env var is absent`)

**Description:**
QA model routing resolved `task_type=quick` to `qwen/qwen3-coder`, which the
operator rejects: `exit_code 1`, 173-byte stdout, 0.2s runtime. This broke
`tests/test_integration.py::test_structured_logging_integration` and
`tests/test_integration.py::test_multi_agent_task_execution` on **every** commit,
including pre-2.0.0 commits.

**Root cause:** two independent causes stacked.
1. The operator shell exported an ambient `NINJA_MODEL=qwen/qwen3-coder` (pinned for a
   different integration in `~/.config/zed/settings.json:56`). `ModelSelector` read only
   `os.environ`, and `NinjaConfig.from_env()` prefers `NINJA_MODEL` for direct-driver
   callers, so an unset/inherited task model silently became that unrelated id.
2. Task-specific keys (`NINJA_MODEL_QUICK` / `_SEQUENTIAL` / `_PARALLEL`, `MODEL_CLASS_*`)
   were only read from the environment; the persisted `~/.ninja-mcp.env` fallback that
   server entry points get from `ConfigManager.export_env()` never applied to direct
   callers.

**Fix:** `ModelSelector` now falls back to the persisted config for per-task and
model-class keys, so a `quick` task resolves to the configured quick model
(`opencode-go/deepseek-v4.1-flash`) even with an ambient `NINJA_MODEL` present. Covered by
`tests/test_coder/test_model_config_fallback.py`; the two integration tests now pass
(`test_multi_agent_task_execution` additionally fixed its worktree assertion — see its own entry below).

**Residual action for the operator (not a code issue):**
- `unset NINJA_MODEL` in the operator shell so direct-driver runs stop inheriting a model
  pinned for another integration.
- `~/.config/zed/settings.json:56` still pins `NINJA_MODEL=qwen/qwen3-coder` for the Zed
  MCP entry. That server now resolves task models from config, but the ambient value should
  be removed there too if the provider is unavailable.

---

### [Bug] `test_multi_agent_task_execution` asserted on the wrong tree (worktree isolation)
**Priority:** Medium
**Status:** FIXED (2.1.0) — `tests/test_integration.py`

**Description:**
The task itself succeeded, but the test read `test_repo/calculator.py`. Sequential tasks
run in an isolated `ninja/*` worktree and the agent's output is committed on the branch
there, so the file is deliberately absent from the caller's working tree. The assertion
could never pass in worktree mode.

**Fix:** the test now resolves the artifact from the driver's structured result
(`suspected_touched_paths`, git-derived in worktree mode) and reads the file from the
reported `worktree_branch` with `git show <branch>:<path>`, falling back to the working
tree only for an in-place run. Isolation behaviour remains covered by
`tests/test_worktree.py`; `NINJA_WORKTREE_MODE` is not overridden, so the real multi-agent
path is exercised.

---

### [Bug] `test_find_editable_repo_detects_real_layout` is checkout-name dependent
**Priority:** Low
**Status:** RESOLVED (2.1.0) — no code change needed; test already tolerant

**Description:**
`tests/test_auto_updater.py::test_find_editable_repo_detects_real_layout` asserted on
the real repository layout and failed in any worktree whose directory name differed
from the expected checkout name.

**Resolution (verified 2026-11-26):** the assertion is now
`found is None or found.name == "ninja-cli-mcp"`, so a checkout under any other name
(e.g. an OpenCode worktree) passes via the `None` branch. Green in this worktree
(`mcp-2026-07-28`); nothing to fix.

---

### [Bug] `test_no_old_servers_running` conflicts with the user's own daemons
**Priority:** Low
**Status:** FIXED (2.1.0) — `tests/test_ninja_fixed.py`

**Description:**
`tests/test_ninja_fixed.py::test_no_old_servers_running` treated the operator's
`uv/tools/ninja-mcp` daemons (ports 8100/8101/8106/8107) as "old servers" and failed
whenever they were running. Environment conflict, not a code regression.

**Fix:** the test now inspects processes with psutil and skips (with the offending PIDs
and unit names in the reason) when a `uv/tools` server is owned by an **active**
`ninja-mcp@<module>.service` user unit or by a process whose cgroup belongs to one.
Servers with no active unit are still genuinely stale and still fail the assertion.
Read-only checks only (`systemctl --user is-active`, `/proc/<pid>/cgroup`).

---

### [Bug] `test_opencode_e2e` fails only in full-suite order
**Priority:** Low
**Status:** OPEN (verified 2026-11-25)

**Description:**
`tests/test_coder/test_opencode_e2e.py::TestMetadata::test_metadata_structure` and
`::TestCommandStructure::test_command_order` pass in isolation but fail in full-suite
order — cross-test pollution (leaked env/config from earlier tests).

---

### [Bug] `secretary_file_search` schema under-declares required fields
**Priority:** Medium
**Status:** FIXED (2.0.2) — commit `009864e` (schema + structural guard)

**Description:**
The `secretary_file_search` tool schema marks only `pattern` as required while the
request model also requires `repo_root`, so a schema-valid call fails validation at
runtime.

**Fix:** the schema and description now declare `repo_root` required, matching the
request model, and a structural test asserts schema/model agreement for every tool so
this class of drift fails in CI instead of at call time.

---

### [Bug] Secretary schemas under-expose model capabilities
**Priority:** Medium
**Status:** FIXED (2.1.0) — commit `1f86894` (`feat(secretary): honour include/exclude globs in codebase_report and expose implemented options`)

**Description:**
- `secretary_codebase_report` advertises `include_patterns` / `exclude_patterns` that the
  request model does not declare **and** that the executor ignores — the arguments are
  accepted by the schema and silently discarded.
- `secretary_session_report` schema exposes only `session_id`, while the model also
  accepts `action` / `updates` — those paths are unreachable from MCP clients.
- `secretary_analyse_file` exposes fewer optional properties than its model accepts.
- `secretary_file_search` exposes fewer optional properties than its model accepts
  (`max_results`).
- `coder_multi_agent_task` exposes fewer optional properties than its model accepts
  (`allowed_globs` / `deny_globs`).

**Fix:** the globs are now applied (gitignore-style, via `pathspec`) and every aggregate in
the report is derived from the filtered set; the schemas now advertise the options the
executors already implemented (`analyse_file`: `search_pattern`, `include_structure`,
`include_preview`; `file_search`: `max_results`; `codebase_report`: `include_metrics`,
`include_dependencies`, `include_structure`; `session_report`: `action`, `updates`;
`multi_agent_task`: `allowed_globs`, `deny_globs`). `session_report` now rejects
`action=update|create` without `session_id` instead of silently returning the index.
Covered by `tests/test_secretary/test_codebase_filters.py`.

**Description:**
- `secretary_codebase_report` advertises `include_patterns` / `exclude_patterns` that the
  request model does not declare **and** that the executor ignores — the arguments are
  accepted by the schema and silently discarded.
- `secretary_session_report` schema exposes only `session_id`, while the model also
  accepts `action` / `updates` — those paths are unreachable from MCP clients.
- `secretary_analyse_file` exposes fewer optional properties than its model accepts.
- `secretary_file_search` exposes fewer optional properties than its model accepts
  (`max_results`).
- `coder_multi_agent_task` exposes fewer optional properties than its model accepts
  (`allowed_globs` / `deny_globs`).

---

### [Bug] Tasks extension interop footgun — advertising `io.modelcontextprotocol/tasks` without a claim resolver makes the SDK reject the task handle
**Priority:** Medium
**Status:** OPEN (client-side; documented 2026-11-25 in `docs/MCP_PROTOCOL_2026.md` §4)

**Description:**
A client that merely advertises `io.modelcontextprotocol/tasks` (e.g.
`mcp.client.advertise(TASKS_EXTENSION_ID)`) but does not register a claim resolver
receives the task handle envelope and then errors out when the SDK tries to claim it —
the call appears to fail even though the server-side task is running and will complete.
Only `ninja_common.mcp_ext.tasks_client.TasksClient` wires the resolver and is safe to
use as-is; everyone else must implement the resolver themselves.

**Fix direction:**
Keep the warning in `docs/MCP_PROTOCOL_2026.md` §4 next to the client helpers, and
consider failing fast with an actionable message when the extension is advertised
without a resolver.

---

### [Refactor] Deduplicate stdio + `/sse` + `/mcp` wiring; legacy-only daemon bridge
**Priority:** Medium
**Status:** OPEN (verified 2026-11-25)

**Description:**
The module stdio + `/sse` + `/mcp` transport stack is duplicated per server through
`mcp_http.build_asgi_app`. The daemon bridge still speaks legacy SSE, so the
daemon-served path does not expose `2026-07-28`-only features (Skills, Tasks, MRTR
elicitation, file uploads) to clients routed through it.

---

### [Ops] Upgrade the live `uv/tools/ninja-mcp` install from 1.9.2 to 2.0.0
**Priority:** Medium
**Status:** DONE 2026-11-25 — the install was actually 1.9.0 before the upgrade, not 1.9.2, and it is an editable install of the local checkout

**Description:**
The live uv-tool install (`~/.local/share/uv/tools/ninja-mcp`, ports
8100/8101/8106/8107) is still 1.9.2 and serves the pre-2.0 code. It needs a manual
`uv tool upgrade ninja-mcp` plus a daemon restart by the user; the release itself did
not touch running processes.

---

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
