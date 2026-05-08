# Universal Plugin Distribution + Secure Secret Storage

**Date:** 2026-05-08
**Status:** Approved scope, awaiting Phase 1 kickoff

## Goals

1. Ship ninja-mcp as a plugin for Claude Code, OpenAI Codex CLI, and any generic MCP client (Cursor/Windsurf/Claude Desktop) from a single repo.
2. Stop storing provider API keys (OpenRouter, Z.AI, Perplexity, Anthropic, OpenAI, Groq, DeepSeek, Mistral, Google) in plaintext at `~/.ninja-mcp.env`. Use OS keyring with an encrypted-file fallback.

## Non-goals

- No auth INTO ninja itself (none exists; none needed — stdio MCP runs as a local subprocess of the host CLI).
- No server refactoring — all 5 servers are already stdio-clean.
- No repo split — single repo, multiple manifests.

## Findings (audit summary)

- **5 stdio MCP servers** already exposed as pip console-scripts: `ninja-coder`, `ninja-researcher`, `ninja-secretary`, `ninja-prompts` (+ `ninja-daemon`, `ninja-config`).
- Same `{command, args, env}` block works verbatim across Claude Code (.mcp.json), Codex (`~/.codex/config.toml [mcp_servers]`), and any generic MCP client. Repackaging is manifests + docs, not refactoring.
- `CredentialManager` already exists at `src/ninja_config/credentials.py` — AES-256-GCM + PBKDF2 + SQLite (`~/.ninja-mcp.db`). **Not wired into TUI or ConfigManager yet.**
- Modern Textual TUI at `src/ninja_config/modern_tui.py` already has an "API Keys" tree branch (~line 730) and `RightPanel` extension point (~line 878).
- "Self-written auth" the user worried about: doesn't really exist. Just env-var loading + log redaction + in-process session state. Nothing to rip out.

## Phase 1 — Secure secret storage (the real work)

### 1.1 Add keyring backend
- New file: `src/ninja_config/secrets_store.py`
- `SecretStore` protocol: `get(name) -> str | None`, `set(name, value)`, `delete(name)`, `list_names() -> list[str]`, `backend_name() -> str`
- `KeyringBackend` — Python `keyring` lib, service name `ninja-mcp`
- `EncryptedFileBackend` — wraps existing `CredentialManager` (AES-256-GCM SQLite)
- `ChainBackend` — keyring first; fall back to encrypted-file if no keyring daemon (detected via `keyring.get_keyring()` type check, e.g. `fail.Keyring` or `chainer.ChainerBackend` with empty list)
- Whitelist of known secret names: `OPENROUTER_API_KEY`, `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `PERPLEXITY_API_KEY`, `ZAI_API_KEY`, `GROQ_API_KEY`, `DEEPSEEK_API_KEY`, `MISTRAL_API_KEY`, `GOOGLE_API_KEY`
- Add `keyring>=24` to `pyproject.toml`

### 1.2 Wire ConfigManager
- File: `src/ninja_common/config_manager.py`
- `export_env()` resolves known secrets in this order: ChainBackend → existing OS env vars → `~/.ninja-mcp.env` plaintext (legacy)
- Non-secret config (`NINJA_CODE_BIN`, `NINJA_USE_DIALOGUE_MODE`, `NINJA_DEDUP_TTL`, etc.) keeps using `.env` only — no behavior change.

### 1.3 Auto-migrate on first run
- On `ConfigManager.__init__`: if `~/.ninja-mcp.env` contains any whitelisted secret name with a non-empty value:
  1. Back up to `~/.ninja-mcp.env.pre-migration.bak` (idempotent — skip if backup exists).
  2. Move each secret value to `ChainBackend`.
  3. Rewrite `.env` without those lines (preserve comments + non-secret keys).
  4. Print one-line notice: `[ninja-mcp] migrated N API keys to <backend>; backup at ~/.ninja-mcp.env.pre-migration.bak`
- CI/Docker users who set env vars directly (no `.env` file) are unaffected — Phase 1.2's fallback chain handles them.

### 1.4 SecretsPanel in modern_tui
- File: `src/ninja_config/modern_tui.py`
- Reuse the existing "API Keys" tree branch (~line 730). Replace static listing with dynamic listing from `ChainBackend.list_names()`.
- New `SecretsPanel(RightPanel)` widget (~line 878 area):
  - List secrets (name + masked value preview, e.g. `sk-...abc1`)
  - Add / edit / delete
  - Show active backend at top (`Backend: OS keyring (libsecret)` or `Backend: encrypted file (~/.ninja-mcp.db)`)
- No CLI subcommands needed — TUI is the single UX. `ninja-config` already launches it.

## Phase 2 — Multi-host plugin manifests

### 2.1 Claude Code plugin
- `.claude-plugin/plugin.json` — name `ninja`, version from pyproject, description, repository
- `.mcp.json` at repo root — `mcpServers` block registering all 5 stdio servers via console-scripts
- Bundle existing `skills/`, `agents/`, `commands/` (already present in repo) as plugin assets
- `.claude-plugin/marketplace.json` so users can `/plugin install ninja@<git-url>`

### 2.2 Codex
- `dist/codex.toml` — copy-paste block with `[mcp_servers.ninja_coder]`, `[mcp_servers.ninja_researcher]`, etc.
- README section: "Add to `~/.codex/config.toml`:" + the block

### 2.3 Generic MCP
- `dist/mcp.json` — same `mcpServers` JSON; works for Cursor (`~/.cursor/mcp.json`), Windsurf, Claude Desktop, VS Code Copilot

### 2.4 README
- Single "Install" section with three subsections (Claude Code / Codex / Generic), each: `pip install ninja-mcp` + paste the matching snippet.

## Phase 3 — Optional polish

### 3.1 `ninja-mcp init <host>`
- New subcommand on existing `ninja-config` (or new `ninja-mcp` console-script) that writes the correct config block into the correct file:
  - `claude-code` → `~/.claude/plugins/...` or invokes `claude --plugin-dir`
  - `codex` → appends to `~/.codex/config.toml`
  - `cursor` → writes `~/.cursor/mcp.json`
  - `generic` → prints to stdout

### 3.2 PyPI release CI
- Confirm GitLab CI publishes to PyPI on tag. Add if missing.

## Risks / Open questions

- **Encrypted-file master password UX**: existing `CredentialManager` uses PBKDF2 — where does the password come from on headless machines? Options to confirm during 1.1: (a) prompt once, cache in memory per process; (b) derive from `/etc/machine-id` (no password, less secure if box compromised). Recommend (a) with optional (b) opt-in.
- **Keyring on headless Linux**: `python-keyring` falls back to `keyring.backends.fail.Keyring` when no daemon. ChainBackend must detect this and silently use encrypted-file instead (no error noise on Docker/CI).
- **Daemon-mode servers**: `ninja-daemon` runs servers as long-lived processes. If the encrypted-file master password is process-cached, the daemon must prompt at startup (blocks systemd-style auto-start). Mitigation: daemon mode prefers OS keyring; if not available, document that env vars or a startup keychain unlock are required.

## Task tracking

See task list (Tasks #1–6).

---

## Follow-up — ninja-prompts and ninja-resources removed (2026-05-08)

After this plan landed, both `ninja-prompts` and `ninja-resources` were removed (see commit "chore: remove deprecated ninja-prompts and ninja-resources servers"). Reference list of remaining servers exposed as console-scripts: `ninja-coder`, `ninja-researcher`, `ninja-secretary` (+ `ninja-daemon`, `ninja-config`).
