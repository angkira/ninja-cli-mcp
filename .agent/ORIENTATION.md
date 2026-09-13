# ORIENTATION.md - How this repo is organized

Quick orientation for agents working in this repository. Keep this file
short and factual. Read STATUS.md + ROADMAP.md for the current session state.

## What this is

Ninja MCP is a set of MCP servers + a CLI orchestrator for coding, research
and codebase analysis. Current version: see `pyproject.toml`.

## Layout (src/)

| Package | Purpose |
| --- | --- |
| `ninja_common/` | Shared CLI dispatch, daemon manager, config manager, defaults (SINGLE SOURCE OF TRUTH for defaults) |
| `ninja_coder/` | Coder MCP server, driver, CLI strategies (`strategies/`), model selector, multi-agent |
| `ninja_researcher/` | Web search / deep research MCP server |
| `ninja_secretary/` | File analysis / codebase report MCP server |
| `ninja_agent/` | Orchestrator CLI: plan/analyze/delegate/review |
| `ninja_config/` | Config TUI (Textual `modern_tui.py` + InquirerPy `interactive_configurator.py` + `ui/`), installer, updater (`auto_updater.py`) |

## Key entry points (pyproject `[project.scripts]`)

- `ninja-mcp` — unified CLI: `config`, `daemon`, `init`, `update`, `skill`, `agent`
- `ninja-config` — config CLI: `configure`, `install`, `models`, `doctor`, `update`
- `ninja-daemon` — daemon manager (start/stop/restart/status, `module enable/disable`)
- `ninja-coder` / `ninja-researcher` / `ninja-secretary` / `ninja-agent` — MCP servers

## Configuration

- `~/.ninja-mcp.env` — live env config (written by `ConfigManager`).
  NOTE: this file can contain BOTH `KEY=value` and `export KEY='value'` lines;
  daemon writes must update ALL matching lines (see `_save_enabled_modules`).
- `~/.ninja/config.json` — optional hierarchical Pydantic config.
- Model defaults live in `src/ninja_common/defaults.py` (import from there,
  never hardcode).

## Daemons

- `src/ninja_common/daemon.py` `DaemonManager` forks `python -m ninja_<module>.server
  --http --port <N>`. PID files/logs in `~/.cache/ninja-mcp/`.
- Modules: coder (8100), researcher (8101), secretary (8102), agent (8103).
- Enabled set from `NINJA_ENABLED_MODULES`.

## Coder CLI strategies

`src/ninja_coder/strategies/` — one strategy per CLI (Protocol, not ABC):
aider, opencode, gemini, claude, junie (host-auth), **codex** (host-auth,
native subagents). Selection by binary name in `registry.py`. A strategy
implements `build_command`, `parse_output`, `should_retry`, `get_timeout`,
plus optional `build_command_with_multi_agent`.

## Releases

- **`scripts/release.sh <version>`** — ONE command local release (bump, gate,
  build, commit, tag, publish to PyPI locally, verify). `--dry-run`,
  `--skip-tests`, `--skip-publish`, `--yes`.
- Make: `make release VERSION=x.y.z`; just: `just release-local x.y.z`.
- GitHub tag `v*` triggers the Release workflow. The GitHub `PYPI_API_TOKEN`
  secret is BROKEN (project-scoped) → always publish to PyPI **locally** with
  the all-projects token from `.env` (`PY_PI_TOKEN`). See `docs/RELEASING.md`.
- Version is mirrored across: `pyproject.toml`, `uv.lock` (ninja-mcp entry,
  edit directly — never `uv lock`, it reformats), `src/ninja_agent/__init__.py`,
  `tests/test_container_config.py`, `Makefile`, `install.sh`, `docker-compose.yml`.

## Testing / quality gates

- `uv run ruff check src/` · `uv run ruff format --check src/` ·
  `uv run mypy src/ --ignore-missing-imports` · `uv run pytest tests/ -x`.
- `tests/test_container_config.py` enforces version consistency across release files.
- Default-model VALUE assertions are forbidden in tests (structural checks only)
  — so model changes don't churn tests.

## Conventions / warnings

- `.gitlab-ci.yml`, `docs/superpowers/`, `training/` belong to OTHER
  agents/sessions — do not touch, do not commit.
- `.env` (repo root) holds `PY_PI_TOKEN` (PyPI all-projects token) — gitignored,
  never commit.
- `uv run` may modify `uv.lock` (reformat churn from local uv version); restore
  with `git checkout -- uv.lock` when it is unrelated to your change.
- Avoid a module-level `import subprocess` in `modern_tui.py`
  (`test_auto_updater` asserts it). Import locally inside the function.
- Read STATUS.md (current state) and ROADMAP.md (backlog) before starting work.