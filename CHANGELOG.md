# Changelog

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
