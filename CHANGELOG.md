# Changelog

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
