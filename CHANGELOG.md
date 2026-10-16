# Changelog

## 1.7.0 - 2026-10-16

Researcher: fast + deep research with real report synthesis via Perplexity.

### Added
- **`researcher_quick_research`**: single-pass research. With Perplexity selected it
  returns Perplexity's cited answer directly; with other providers it gathers results
  and writes a short cited answer when a synthesis engine is configured.
- **Report synthesis engine** (`ninja_researcher.synthesis`): Perplexity-native answers
  plus an OpenRouter fallback, selected from `NINJA_RESEARCHER_LLM`
  (`off`/`auto`/`perplexity`/`openrouter`) and `NINJA_RESEARCHER_MODEL`.
- `researcher_deep_research` now resolves its provider per request
  (`search_provider`, else `NINJA_SEARCH_PROVIDER`, else auto) and, when synthesis is
  available, returns a written `report` synthesized from the gathered sources
  (`synthesize`, `report_type`).
- `researcher_generate_report` now synthesizes with an LLM when one is configured,
  falling back to the deterministic template (`use_llm` to force on/off).

### Fixed
- **Perplexity's answer was discarded**: the provider kept only citation URLs, so
  reports were bare link lists. The synthesized, cited answer is now preserved
  (`PerplexityProvider.research`).
- **Provider selection ignored `NINJA_SEARCH_PROVIDER`** for deep research; the factory
  now honours it when the named provider is available, and respects
  `NINJA_RESEARCHER_MODEL` for the Perplexity model.

### Tests
- Added `tests/test_researcher_quick.py` (quick research, Perplexity deep research,
  LLM report synthesis + fallbacks) and `tests/test_researcher_synthesis.py`
  (engine resolution and completion).

## 1.6.3 - 2026-10-16

OpenCode provider autocomplete robustness.

### Fixed
- **OpenCode provider models hidden when `opencode` is not on `PATH`**: the
  config TUI resolved the OpenCode binary with a plain
  `shutil.which("opencode")`. When the TUI/MCP host ran with a minimal `PATH`
  that omitted OpenCode's install dir (`~/.opencode/bin`, which the installer
  only exports on the interactive shell `PATH`), model discovery silently
  returned nothing while the provider dropdown still showed the static list
  (e.g. "OpenCode Go") — so typing `deep` in the model autocomplete found no
  models. `_run_opencode_models`/`get_provider_models` now resolve the binary
  via `_which_binary` (PATH → `~/.opencode/bin` → other common install dirs) and
  honour an explicit `OPENCODE_BIN` override.
- **Path-based `NINJA_CODE_BIN`**: `get_provider_models` accepted only the bare
  `opencode` id; a full binary path (e.g. `/home/…/.opencode/bin/opencode`)
  returned no models. Operator values are now normalized before dispatch.

### Tests
- Extended `tests/test_opencode_provider_autocomplete.py` (33 tests) with
  off-`PATH` discovery, the `OPENCODE_BIN` override, path-based operator
  resolution, and `_extra_bin_dirs` coverage.

## 1.6.2 - 2026-10-16

OpenCode model autocomplete & provider discovery fix.

### Fixed
- **OpenCode provider model autocomplete**: in OpenCode v2, `opencode models` rejects
  positional provider arguments (`opencode models <provider>` exited 1 with
  `Unexpected positional argument: "<provider>"`), which broke autocomplete for
  all OpenCode providers (including OpenCode Go, Anthropic, OpenAI, LiteLLM, Google).
  Now fetches the full catalog via `opencode models` once and filters by provider
  prefix in-process.
- **OpenCode Go provider coverage**: models under both `opencode-go/` and `opencode/`
  prefixes are matched when searching under the OpenCode Go provider in the config UI.

### Tests
- Added comprehensive unit and integration test suite (`tests/test_opencode_provider_autocomplete.py`,
  27 tests) covering dynamic provider discovery, model fetching for all canonical
  providers (`opencode`, `opencode-go`, `anthropic`, `openai`, `google`, `openrouter`,
  `litellm`, `github-copilot`, `gitlab`), search/filter queries, and failure/timeout handling.

## 1.6.1 - 2026-10-15

OpenCode v2 (2.0.x) integration.

### Changed
- **OpenCode v2 run flags**: `opencode run` uses `--auto` instead of the removed
  `--dangerously-skip-permissions`. Verified against `opencode` 2.0.28.
- **Model references**: bare model ids are no longer prefixed with
  `opencode-go/`. Ids are used as given (`provider/model[#variant]`). Set
  `NINJA_CODER_OPENCODE_PROVIDER` to prefix bare ids explicitly.
- **LiteLLM provider config**: written to the v2 global
  `~/.config/opencode/opencode.jsonc` (`providers.litellm` with `settings.baseURL`
  and `modelID`). Existing JSONC comments and other keys are preserved.

### Removed
- The project LSP-disabling override. It relied on `XDG_CONFIG_HOME`, which
  OpenCode v2 does not read, so it never took effect.

### Fixed
- Routing tests no longer depend on locally installed `codex`/`junie` catalogs.

### Verified
- Live task through LiteLLM via `opencode run` (`litellm/anthropic/claude-haiku-5-5`)
  returned `OK`.

### Known issue
- The LiteLLM model `Agentic-Models-Qwen3.6-27B-FP8` fails with `Jwt is expired`
  from the proxy backend. This is a server-side token issue, not a client change.

## 1.6.0 - 2026-10-15

Isolated-run cleanup, direct branch tools, and no safety commits.

### Added
- **Branch tools for isolated work**: `coder_branches_list`, `coder_branch_merge`
  and `coder_branch_discard` act on `ninja/*` branches only. A conflicting merge
  is aborted and leaves the repository unchanged; discard refuses unmerged work
  unless `force` is set.

### Changed
- **No safety commits**: AUTO mode never commits on the user's branch. Changes
  stay uncommitted and HEAD is tagged as the recovery point. The
  `[ninja-auto-save]` commit and its `auto_committed` action are removed.
- **Generated commit messages**: agent output commits use the task text as the
  subject and list the changed files in the body (no fixed placeholder).

### Fixed
- **Agent output commit failed without git identity**: every ninja commit now
  uses the fallback identity `ninja-coder <ninja@localhost>` when none is
  configured.
- **Worktree checkouts leaked disk space**: after each isolated run the leftover
  output is committed and the checkout directory is removed. The `ninja/*` branch
  is kept, so the work stays reachable. Previously each checkout (often with a
  multi-GB `node_modules`) stayed until the 2-day age prune.

## 1.5.1 - 2026-10-12

Pi coding agent (pi.dev) CLI operator & MCP init integration.

### Added
- **Pi init target (`ninja-mcp init pi`)**: Merge Ninja MCP servers directly into `~/.pi/agent/mcp.json` with `exposure: "direct"` and automatic host detection at `~/.pi/`.
- **Pi CLI strategy (`PiStrategy`)**: Native support for Pi as a coding operator in `ninja-coder` (`NINJA_CODE_BIN=pi`) using non-interactive JSON mode (`pi -p --mode json`), JSONL tool event parsing for `write` and `edit`, retryable error handling, and timeout configuration.
- **Pi thinking levels & dynamic discovery**: Supports `--thinking` (`off`, `minimal`, `low`, `medium`, `high`, `xhigh`, `max`) with per-task overrides, dynamic model discovery from `pi --list-models` and `~/.pi/agent/settings.json`, and full TUI model selection / autocomplete integration.

## 1.5.0 - 2026-10-09

Worktree transfer and job-status fidelity.

### Added
- **Post-run commit**: agent output in a worktree is committed to the `ninja/*`
  feature branch after each run, so `git merge ninja/<branch>` actually
  transfers the work (it previously carried only the pre-task snapshot).
- **Git-grounded results**: `files_modified` is computed from
  `git diff <baseline>..HEAD` instead of agent-claimed paths (fixes bare-path
  phantoms like `pytest.ini`); new `patch_path` artifact (`git diff --binary`
  under `<cache>/ninja-mcp/patches/`) attached to plan results.
- **`parse_output` baseline fix**: under worktree mode the diff baseline is the
  snapshot commit, not HEAD~1 (fixes snapshot files misattributed as agent
  output).

### Fixed
- **Status fidelity**: `run_tracked` marks a job `failed` (with reason in the
  list view) when the returned payload reports `overall_status: failed` or
  `status: error|failed` — jobs no longer list `completed` for failed runs.
- **Auth false positive**: error classification scans only the last 8000 chars
  of CLI output; agents grepping strategy sources no longer self-sabotage
  successful runs into "Authentication failed".

## 1.4.1 - 2026-10-01

Dynamic model discovery for OpenAI Codex CLI.

### Added
- **Codex dynamic discovery**: Multi-source model discovery for Codex operator:
  reads active model and NUX flags from `~/.codex/config.toml`, scans embedded
  JSON models from the `codex` binary, and queries recent models from SQLite history.
  Adds full native support for `gpt-6-luna`, `gpt-6.1-sol`, `gpt-6-sol`, `gpt-6-astra`.

## 1.4.0 - 2026-09-20

Researcher overhaul, coder robustness, and MCP efficiency.

### Added
- **Researcher overhaul (post-mortem)**: typed errors `{error_kind, message,
  retry_after_s}` with providers raising instead of returning silent `[]`;
  fixed `summarize_sources` (beautifulsoup4 now in base deps); new tools
  `researcher_arxiv_search`, `researcher_deep_research_batch`,
  `researcher_paper_fetch`; domain filters; real titles/snippets/source_type
  (fake score ladder removed); stale "coming soon" docs removed.

### Changed
- **Coder robustness**: durable job rows for sync tools (no orphan runs on
  client timeout); `request_key` idempotency; signal kills no longer misreported
  as auth failures; startup sweep of stale working jobs; progress refresh;
  `NINJA_FALLBACK_MODELS` chain for 429/503/quota/overload.
- **MCP efficiency**: handshake instructions and all tool descriptions trimmed
  (~30KB to ~4KB total); schemas and behavior unchanged.

### Tests
- New suites for errors/arxiv/enrichment/domain/batch/paper-fetch/fallback;
  hermetic model-routing test; basename touched-path assertions.

### Caveat
- export.arxiv.org throttles aggressively — space calls ≥3s; restart daemons
  to pick up; PyPI published locally (GitHub token broken, known).

## 1.3.1 - 2026-09-18

[1.3.1] - 2026-09-18: Native JetBrains Junie MCP host integration, CLI version flag support, and init target test coverage.

### Added
- **Native Junie MCP integration**: Added `ninja-mcp init junie` target with automated detection of `~/.junie` and configuration merge into `~/.junie/mcp/mcp.json` containing all 4 MCP servers (`ninja-coder`, `ninja-researcher`, `ninja-secretary`, `ninja-agent`).
- **CLI version flags**: Support for `--version` and `-v` flags in `ninja-mcp` CLI in addition to the `version` subcommand.
- **Init target test coverage**: Added comprehensive unit test suite in `tests/test_init_targets.py` verifying detection, installation, dry-run previews, and config merging for the Junie target.

### Verified (live)
- `tests/test_init_cli.py`, `tests/test_init_targets.py`, `tests/test_container_config.py`, and `tests/test_agent_e2e.py` passing 100%.

## 1.3.0 - 2026-09-16

Autonomous compound routines and context distillation for `ninja-agent`.

### Added
- **`run_and_diagnose` compound routine**: `agent_run_and_diagnose` (MCP) and
  `ninja-mcp agent run-and-diagnose` (CLI) execute test suites or build commands,
  automatically extracting failures, root causes, clean tracebacks, and test counts
  (`passed`, `failed`, `skipped`, `errors`), stripping noisy passing logs and ANSI codes.
- **`exec_pipeline` compound routine**: `agent_exec_pipeline` (MCP) and
  `ninja-mcp agent pipeline` (CLI) run an ordered batch of commands in a single
  round-trip with configurable `fail_fast` policy, per-step timing, and write guards.
- **`distill_logs` context condensation**: `agent_distill_logs` (MCP) and
  `ninja-mcp agent distill-logs` (CLI) tail, cluster, and deduplicate repetitive log lines,
  extracting unique patterns, recurrence counts, and isolated error traces.
- **End-to-end test suite**: `tests/test_agent_e2e.py` covering in-process
  executor operations, live stdio JSON-RPC MCP ClientSession calling autonomous routines,
  and real-world smoke scenarios.

### Changed
- **`ninja-agent` autonomous runner**: Transformed from atomic command executor
  into an outcome-driven autonomous runner tool with rate balancing and telemetry monitoring.
- JetBrains Junie CLI model discovery and effort configuration support.

### Verified (live)
- `tests/test_agent.py`, `tests/test_agent_cli.py`, `tests/test_agent_runner.py`,
  `tests/test_agent_e2e.py`, and `tests/test_container_config.py` passing with 100% pass rate.

## 1.2.0 - 2026-09-15

Background jobs that work in **every** MCP host, not just Tasks-capable ones.

### Added
- **submit/poll job tools** (coder): `coder_submit_simple`,
  `coder_submit_sequential`, `coder_submit_parallel` return
  `{job_id, status:"working", poll_interval_ms}` immediately and run in the
  background; `coder_job_status`, `coder_job_result`, `coder_job_cancel`,
  `coder_jobs_list` inspect/stop them. Runs on ordinary tool calls, so it works
  in opencode, Claude Code, Codex, Antigravity and anything else.
- `ninja_common.jobs.JobManager` — background runner built on the durable
  `SqliteTaskStore`: jobs survive restarts and are visible across sessions;
  `coder_job_cancel` actually interrupts the CLI process group.

### Why
- Verified via client handshake that opencode 1.18, Claude Code 2.1, Codex 0.154
  and Antigravity v1.0 all initialize with `capabilities.tasks = null` — the
  standard MCP Tasks path stays implemented and will light up automatically, but
  submit/poll is what makes background execution usable today.

### Verified (live)
- `NINJA_CODE_BIN=codex`: submit → `working` → poll → `completed` → result
  (file written); a second job `coder_job_cancel` → `cancelled` (process group
  terminated) with the server still serving calls.
- `tests/test_mcp_jobs.py` + `tests/test_mcp_tasks.py` — 17 passed.

## 1.1.0 - 2026-09-15

Background execution: long-running tools now run as **standard MCP Tasks** —
start a run, get a task id, keep working, and fetch or cancel the result later.

### Added
- **MCP Tasks across coder, agent and researcher.** Long tools advertise
  `execution.taskSupport = "optional"`; a task-augmented `tools/call` returns a
  task handle (`CreateTaskResult`), and the client follows up with `tasks/get`,
  `tasks/result`, `tasks/list`, `tasks/cancel`. Clients without the capability
  keep the exact synchronous behavior.
- **Durable task store** (`SqliteTaskStore`, `NINJA_TASKS_DB`, default
  `~/.ninja/tasks.db`): tasks survive restarts and are shared across sessions.
- **Real cancellation**: `tasks/cancel` interrupts the running work by
  terminating the CLI subprocess group (SIGTERM → SIGKILL), and safely no-ops for
  unknown/terminal tasks.
- **Progress notifications** (`notifications/progress`) emitted from the CLI
  streaming loop (~every 10s), best-effort.
- Docs: [docs/MCP_TASKS.md](docs/MCP_TASKS.md).

### Fixed
- Guarded the SDK's stale-completion race so a cancelled task can no longer tear
  down the server's task support.

### Verified (live)
- Task mode end-to-end with real operators **codex, claude, opencode and agy**:
  handle → poll → `completed` → `tasks/result`, expected files written.
- Cancellation interrupts in-flight work; a task is still queryable via
  `tasks/get`/`tasks/result` after a server restart.

### Notes
- The MCP Tasks capability is experimental in the SDK/protocol; live result
  waiters are in-process, and the store is local (not distributed).

## 1.0.17 - 2026-09-15

- **Replaced the deprecated Gemini CLI operator with Antigravity (`agy`).**
  New `AgyStrategy` runs `agy --add-dir <repo> --dangerously-skip-permissions
  --output-format stream-json -p <prompt>` (stream-json keeps the watchdog alive
  and yields a structured result). Models are discovered dynamically via `agy
  models` (no hardcoded list); the default omits `--model` and lets agy choose.
  Operator detection, config UI, operator/default/compatibility maps and the
  settings registry all switched gemini → agy; the MCP-host target is
  Antigravity.
- **Fixed the Claude Code operator:** pass the prompt via `-p` (a bare
  positional was dropped) and use version aliases (`sonnet`/`opus`/`haiku`)
  instead of expired dated model ids.
- Verified live: with `agy` (e.g. model `claude-sonnet-4-6`) the sequential,
  parallel and delegate flows all succeed and write the expected files; Claude
  sequential also passes.

## 1.0.16 - 2026-09-15

- **OpenCode provider sub-selection (dynamic, OpenCode only).** The model picker
  now exposes a provider dropdown for OpenCode — the one operator with many
  providers (Anthropic, OpenAI, Google, Z.AI, OpenRouter, …). Providers are
  discovered from `opencode models` (no hardcoded list; the previous Anthropic
  exclusion is removed) and models per provider from `opencode models
  <provider>`. The dropdown is hidden for native operators and Aider, which have
  a single provider. Configure a provider (e.g. `opencode auth`) and it shows up
  automatically; you can also type any `provider/model` id directly.

## 1.0.15 - 2026-09-14

- **Model list follows the selected operator.** For a native operator
  (codex/junie/claude/gemini) the picker shows that operator's provider even if
  the stored model still carries another operator's prefix (e.g. an OpenRouter
  id under codex); Aider is pinned to OpenRouter.
- Fixed Aider model parsing (`- provider/model` rows yielded `-` as the id) —
  deduped chat models now list correctly; Gemini/Claude catalogues come from the
  single source of truth and match the operator-compatible ids.

## 1.0.14 - 2026-09-14

- **Config TUI: no more "ended queue object" I/O error when enabling a module.**
  The TUI started/stopped daemons via an in-process `os.fork()` while Textual's
  event loop and worker threads were running, corrupting their queues. Daemon
  start/stop now go through `ninja-mcp daemon …` in a background worker, and
  worker→UI posts become no-ops once the app stops.
- **Config TUI: the operator picker now lists every operator, not just those on
  the TUI process's PATH.** CLIs are also discovered in common install dirs
  (`~/.local/bin`, npm/bun/cargo globals, nvm, Homebrew, `/usr/local/bin`), so
  claude/junie/gemini/aider show up even under a minimal service PATH;
  uninstalled ones are labelled and selecting them is refused with a clear
  message (and the picker resets).

## 1.0.13 - 2026-09-14

- **Fix `ninja-mcp update` hanging on the encrypted-store password.** With a
  password-protected store the daemon restart inherited the updater's TTY,
  found no password, and blocked on a `getpass` prompt until the subprocess
  timeout — surfacing as "Daemon restart timed out". The updater now resolves
  (and prompts once for) the store password itself and hands it to the restart
  via `NINJA_CREDENTIAL_PASSWORD`; the daemon strips it from its child env and
  passes it through an inherited fd. Restart stdin is closed and the timeout is
  120s.
- `secrets_store.ensure_store_unlocked()` added (absent/passwordless/prompt
  aware) and the updater reuses the resolved password when rewriting MCP config.

## 1.0.12 - 2026-09-14

- **Models auto-route to the active operator.** A single source of truth
  (`ninja_common.operator_models`) knows what each coding CLI can run. The model
  selector and `NinjaConfig.from_env` now fall back to the operator's own
  default instead of leaking an OpenRouter id into Codex/Claude/Gemini/Junie;
  text tasks (agent/secretary) pin a compatible model too.
- **Operator-relative model autocomplete.** The config picker shows only the
  selected operator's catalogue: native operators expose a single provider
  (codex, junie, claude, gemini), Aider lists OpenRouter, and static fallbacks
  never suggest another operator's ids.
- CI: repaired stale Modules/API-Keys TUI tests (moved to the inline
  `ModuleRow`/`DaemonRow`/`APIKeyRow` API) and made search-provider tests
  hermetic so a developer keyring can't leak in. Lint and all test jobs pass.

## 1.0.11 - 2026-09-14

- Fix text tasks (agent `plan`/`review`, secretary `codebase_report`/summary)
  ignoring the module's operator/model: provider-specific model-class/task env
  vars were sent to a different operator (e.g. an OpenRouter id to codex),
  failing the call. The module model is now pinned for text tasks.
- Parse codex assistant output (`item.completed`/`agent_message`) in addition to
  opencode's `text` parts. Verified live end-to-end through codex + gpt-5.6-luna.

## 1.0.10 - 2026-09-14

- **Per-module operators.** The coding CLI is now configurable per module —
  coder (`NINJA_CODE_BIN`, shared by quick/sequential/parallel), secretary
  (`NINJA_SECRETARY_OPERATOR`), agent (`NINJA_AGENT_OPERATOR`, new). Researcher
  keeps its own search engines. Pick each in its Models-tab section; changing one
  refreshes only that module's providers.
- **Secretary and agent execute through their own operator.** `agent.plan`
  (rationale), `agent.review` (summary), `secretary.codebase_report` (AI
  Insights) and `analyse_file` (summary) now run the module's operator + model;
  text tasks run in a throwaway git dir with context embedded, so the real repo
  is never modified. Heuristic/static fallback when the operator is unavailable.
- **Config TUI:** the Docker installer creates the workspace directory instead
  of rejecting a missing path; module/daemon toggles no longer crash when a
  daemon fails (clear notification + log path); operator pickers verified.
- Fixes and tests for the above.

## 1.0.9 - 2026-09-14

- **`ninja-mcp update` no longer silently no-ops.** The uv reinstall now passes
  `--refresh`, so a stale local index cache can no longer make `update` report
  success while leaving the old version installed (the failure seen on some
  machines).
- Bootstrap note: versions **≤ 1.0.8** carry the no-op bug, so a machine on an
  older build may need one manual `uv tool install --force --refresh ninja-mcp`
  before `ninja-mcp update` starts working.

## 1.0.8 - 2026-09-14

- **Keys: our key if present, otherwise the operator's own auth.** The child
  coding CLI is spawned with a sanitized environment — inherited API keys are
  stripped (a stale shell key can no longer leak in or shadow), ninja's key from
  the encrypted store is injected when available, and host-auth operators
  (Codex/Claude/Junie) never receive a key. So you are not prompted and not
  blocked when relying on the operator's login.
- **Encrypted store is primary** (OS keychain is the fallback, no shadowing);
  passwordless stores open without a prompt; the TUI key save reports real
  errors instead of silently falling back to plaintext.
- **`ninja-mcp update` robustness:** detects the install method (uv tool / pipx /
  pip) and upgrades that environment; pip retries with `--break-system-packages`
  on PEP 668 (externally-managed) hosts; clearer failure output. Fixes updates
  that failed or were a no-op on other machines.
- Tests isolate the encrypted store from the real HOME (`NINJA_CREDENTIALS_DB`).

## 1.0.7 - 2026-09-14

- **Secrets: the encrypted store is now the single source of truth.** API keys
  (`*_API_KEY`) are never written to `~/.ninja-mcp.env` and never exported into
  the process environment; they are read on demand from the AES-256-GCM store.
  Existing plaintext secrets are migrated in and scrubbed.
- **Cross-platform store-password delivery — never via env:** inherited fd from
  `daemon start`, systemd `LoadCredential` (Linux), password file (launchd),
  OS keychain/keyring (macOS Keychain / Secret Service), or interactive prompt.
  Added `scripts/provision_systemd_credential.sh`.
- **Config TUI is more compact** — borderless tables, underline inputs, chip
  buttons, fewer nested borders/paddings — with inline, keyboard-focusable
  module and daemon toggles and a per-provider inline API-key editor
  (↑/↓ navigation). Includes encrypted-store password set/change/reset controls.
- Archived stale report/investigation markdown into `docs/archive/`.

## 1.0.6 - 2026-09-13

- **Coder plan input is tolerant and self-explanatory.** `PlanStep.id` and
  `title` are now optional and auto-generated (`step_N` / first task line);
  only `task` is required. Malformed plans now return an indexed, model-readable
  error (e.g. `steps[0] is missing the required 'task' field …`) instead of the
  opaque client-side `Input validation error: 'id' is a required property`.
- **Codex models now appear in the config model picker**, the operator list
  shows installed/available status, and switching operator refreshes providers.
  Also fixed a Textual 7.5 crash (`Select.NULL` → `Select.BLANK`).
- **Daemons autostart with the system.** New systemd user unit for the module
  daemons plus `scripts/run_daemons.sh` (PATH + env bootstrap) and
  `scripts/install_service.sh`.
- Added local release automation (`scripts/release.sh`, make/just targets,
  `docs/RELEASING.md`) and live battle E2E scripts
  (`scripts/e2e_live.sh` / `scripts/e2e_live.py`).

## 1.0.5 - 2026-09-13

- Reworked `ninja-mcp update`: version-aware with channel detection
  (github / pypi / brew), PEP 440 comparison, Rich progress UI, and a
  `--channel` override. The daemon upgrade path now installs from PyPI.
- Added OpenAI Codex CLI as a host-auth coder strategy (ChatGPT login, no API
  keys) with native subagent orchestration via `codex exec --json`.
- Switched the default model roles to `openrouter/deepseek/deepseek-v4.1-flash`.

## 1.0.3 - 2026-09-13

- Added a Modules tab to the Textual config TUI (`ninja-config configure`, press `7`):
  enable/disable/start/stop per-module, plus a uv-based installer for missing
  module binaries.
- Fixed `DaemonManager._save_enabled_modules` so it rewrites every matching
  `NINJA_ENABLED_MODULES` line (plain and `export` forms) in `~/.ninja-mcp.env`,
  eliminating stale duplicate values.
- Enabled the `ninja-agent` module on the host (`NINJA_ENABLED_MODULES=coder,researcher,agent`)
  with its daemon running on port 8103.

## 1.0.1 - 2026-09-08

- Fixed the GitHub release workflow to publish to PyPI with the configured API
  token secret.
- Updated Docker image defaults and package metadata for the 1.0.1 release.

## 1.0.0 - 2026-09-08

- Added a non-root Python 3.12 container image with local package installation.
- Added Compose profiles for coder, researcher, secretary, and agent services.
- Added local-only port bindings, read-only mounts where safe, named config and
  cache volumes, and HTTP/SSE healthchecks.
- Documented runtime-only credentials and the limitation that host-authenticated
  coding CLIs are not included in the image.

### Security and migration notes

- Do not put API keys in the Dockerfile, Compose file, image, or build context.
- Existing host configuration is not automatically mounted; use the named
  volumes or pass `NINJA_CREDENTIAL_PASSWORD` at runtime.
- Coder worktrees are stored under the Ninja cache volume and must be merged or
  pruned deliberately.
