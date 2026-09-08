# Ninja MCP

[![CI](https://github.com/angkira/ninja-cli-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/angkira/ninja-cli-mcp/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](#requirements)

Ninja MCP is a set of MCP servers and a small command-line orchestrator for
coding, research, and codebase analysis. The current package and release are
`1.0.1`.

## What It Includes

- **Coder**: simple tasks plus sequential and parallel execution plans.
- **Researcher**: web search, deep research, source aggregation, and fact checks.
- **Secretary**: codebase reports, file analysis, search, and git-aware context.
- **Agent**: a CLI orchestrator for plan, analyze, delegate, review, and run.
- **Config TUI**: Nord-themed setup, model selection, host-auth detection, and
  IDE registration.

## TUI Preview

The configuration app uses a Nord palette, a block-letter NINJA logo, keyboard
navigation that works on RU and Latin layouts, and lazy model autocomplete.

![Ninja MCP TUI overview](docs/assets/tui-overview.svg)

![Model picker and autocomplete](docs/assets/tui-models.svg)

The Docker installer asks for workspace, profiles, ports, build/start, and
credentials in the same style. This preview is generated from the current
installer flow; it is not a live container session.

![Docker installer flow preview](docs/assets/tui-docker-installer.svg)

## Requirements

- Python 3.11 or newer for a native install.
- Docker Engine with Compose v2 for Docker mode.
- An authenticated host CLI or provider credentials for the operator you use.

## Quick Start

### Make quickstart

From a checkout, `make help` lists the available wrappers. Normal users should
run `make install` and choose `Native installation` or `Docker container
(isolated)` in the first TUI question. Do not run `make docker-up` before that
configuration exists; Docker targets use the TUI-generated
`~/.config/ninja-mcp/docker/.env`.

| Goal | Command | Notes |
| --- | --- | --- |
| Interactive install | `make install` | The normal Native/Docker TUI flow |
| Native guidance | `make install-native` | Native has no separate automation flow |
| Internal Docker automation | `make install-headless` | Hidden `NINJA_DOCKER_NONINTERACTIVE=1` backend; not public UX |
| Compose config | `make docker-config PROFILE=coder` | Resolves config only, does not start containers |
| Start services | `make docker-up PROFILE=coder` | Requires prior TUI-generated config |
| Stop services | `make docker-down PROFILE=coder` | Non-destructive stop |
| Quality checks | `make check` | CI-aligned lint, format, typecheck, and tests |
| Release validation | `make release-check` | Builds locally; never publishes |

The Make targets are thin wrappers around `install.sh`, `uv`, and Docker
Compose. `IMAGE`, `PROFILE`, `COMPOSE_PROJECT_NAME`, and `CONFIG_DIR` can be
overridden as Make variables. `make docker-clean` is explicit and removes
Compose volumes.

### Native TUI

The bootstrap installer opens the setup flow. It can install the package and
then configure the native runtime:

```bash
curl -fsSL https://raw.githubusercontent.com/angkira/ninja-cli-mcp/main/install.sh | bash
```

For an existing checkout or an already installed package:

```bash
ninja-mcp config install
# Equivalent entry point:
ninja-config install
```

The main TUI is also available with `ninja-mcp config` or
`ninja-config configure`. It writes native configuration to
`~/.ninja-mcp.env` and uses the OS keyring when available, with an encrypted
file fallback for headless environments.

### Deployment target

Use Docker when host isolation is more important than host CLI integration:

Run `./install.sh` and select `Native installation` or
`Docker container (isolated)` as the first TUI question. Docker then asks for
workspace, profiles, unique localhost ports, build/start, and credentials.

The interactive flow asks for an existing absolute workspace, one or more
Compose profiles, unique localhost ports, whether to build and start, and
whether to pass API credentials. It creates a project under
`~/.config/ninja-mcp/docker` and installs the `ninja-mcp-docker` wrapper in
`~/.local/bin`.

For internal automation only, the hidden backend accepts environment overrides:

```bash
NINJA_DOCKER_WORKSPACE="$PWD" \
NINJA_DOCKER_PROFILES=coder,agent \
NINJA_DOCKER_CODER_PORT=18100 \
NINJA_DOCKER_AGENT_PORT=18103 \
NINJA_DOCKER_NONINTERACTIVE=1 ./install.sh
```

The wrapper supports `start`, `stop`, `status`, `logs`, and `config`:

```bash
ninja-mcp-docker start
ninja-mcp-docker status
ninja-mcp-docker logs
ninja-mcp-docker stop
```

See [Docker Quickstart](docs/container-quickstart.md) for profiles, volumes,
runtime secrets, and troubleshooting.

## Unified CLI

Run `ninja-mcp <command> --help` for command-specific options.

| Command | Purpose | Example |
| --- | --- | --- |
| `config` | Launch or manage native configuration | `ninja-mcp config install` |
| `config install` | Run the initial TUI installer | `ninja-mcp config install --skip-keys` |
| `config configure` | Open the ongoing configuration manager | `ninja-mcp config configure` |
| `config models` | Configure models with provider/model picker | `ninja-mcp config models` |
| `init` | Install MCP servers into a host config | `ninja-mcp init detect` |
| `init <host>` | Configure Claude Code, Codex, Cursor, Antigravity, or generic MCP | `ninja-mcp init claude-code --direct` |
| `daemon` | Manage persistent HTTP/SSE module processes | `ninja-mcp daemon status` |
| `agent` | Plan, analyze, delegate, review, or run | `ninja-mcp agent analyze --repo-root .` |
| `update` | Update an installed checkout/package | `ninja-mcp update` |
| `version` | Print the installed version | `ninja-mcp version` |

The standalone server entry points remain available: `ninja-coder`,
`ninja-researcher`, `ninja-secretary`, and `ninja-agent`.

## Agent CLI

The agent CLI emits readable output by default and JSON with `--json`:

```bash
ninja-mcp agent plan --task "Add email validation" --repo-root .
ninja-mcp agent analyze --repo-root . --focus auth
ninja-mcp agent delegate --to coder --subtask "Implement the validator" --repo-root . --model-class smart
ninja-mcp agent review --repo-root . --files src/auth.py tests/test_auth.py
ninja-mcp agent run --task "Implement and review email validation" --repo-root .
```

`run` composes plan, delegate, and review. `delegate --to` accepts `coder`,
`researcher`, or `secretary`; coder model tiers are `smart`, `balanced`, and
`fast`.

## Coder Routing and Safety

Task type is part of the execution policy:

| Task | Public route | Default isolation |
| --- | --- | --- |
| Quick/simple | `coder_simple_task` | In place, with an automatic safety commit |
| Complex sequential | `coder_execute_plan_sequential` | Detached `ninja/*` worktree |
| Complex parallel | `coder_execute_plan_parallel` | Detached `ninja/*` worktree |

Parallel complexity is explicit: `simple` is suitable for independent small
work, while `complex` uses the heavier plan/worktree path. Long-running work is
protected by an inactivity-first watchdog, not only a wall-clock deadline.
Defaults are 90 seconds for quick tasks and 180 seconds for sequential and
parallel tasks. Override with `NINJA_INACTIVITY_TIMEOUT`, or the per-type
`NINJA_INACTIVITY_TIMEOUT_QUICK`, `..._SEQUENTIAL`, and `..._PARALLEL` variables.

See [Automatic Safety](docs/AUTOMATIC_SAFETY.md) for recovery, worktree
controls, and legacy paths that intentionally remain in place.

## Provider Authentication

Ninja does not require a new API key when the selected coding CLI is already
authenticated on the host:

- `claude` uses `claude auth status` and the host Claude Code session.
- `junie` uses JetBrains Account authentication and the `junie` binary.
- `opencode` uses its own provider configuration and authentication.

Junie uses a flat model id and runs commands shaped like:

```bash
junie --model deepseek-v4-flash --output-format text -p . \
  --skip-update-check --task "Review the authentication flow"
```

The TUI detects Junie and offers its static host-auth model list without a
network probe. API-backed operators such as Aider still need the credentials
required by that operator. Docker intentionally does not copy host `$HOME`,
host CLI credentials, or `docker.sock`; use runtime API variables or a protected
runtime env file instead.

## MCP Host Setup

Detect supported hosts and install their configuration with the unified CLI:

```bash
ninja-mcp init detect
ninja-mcp init claude-code --direct
ninja-mcp init codex
ninja-mcp init generic
```

Use `--dry-run` to preview a supported config change. See
[Editor Integrations](docs/EDITOR_INTEGRATIONS.md) and
[Installation Modes](docs/INSTALLATION_MODES.md).

## Documentation

- [Docker Quickstart](docs/container-quickstart.md)
- [Automatic Safety](docs/AUTOMATIC_SAFETY.md)
- [CLI Strategies and operators](docs/CLI_STRATEGIES.md)
- [Model selection](docs/MODEL_SELECTION.md)
- [TUI installer notes](docs/TUI_INSTALLER.md)
- [Configuration](docs/CONFIGURATION.md)
- [MCP architecture](docs/MCP_ARCHITECTURE.md)
- [Coder architecture](docs/coder/ARCHITECTURE.md)
- [Researcher](docs/researcher/README.md)
- [Secretary](docs/secretary/README.md)
- [Changelog](CHANGELOG.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)

## Development

```bash
uv sync --all-extras
uv run pytest tests/ -q
uv run ruff check src
uv run mypy src
```

Ninja MCP is released under the [MIT License](LICENSE).
