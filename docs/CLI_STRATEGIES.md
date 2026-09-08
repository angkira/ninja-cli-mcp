# CLI Strategies

Ninja Coder selects an operator strategy from `NINJA_CODE_BIN`. The strategy
builds the command, passes the selected model, inherits the appropriate
environment, and parses the result.

## Supported Operators

| Binary | Authentication | Model form | Notes |
| --- | --- | --- | --- |
| `opencode` | OpenCode/provider configuration | `provider/model` | Supports provider routing and native session flows |
| `claude` | Claude Code host session | Claude model id | `claude auth status` is used for a lightweight auth check |
| `junie` | JetBrains Account host session | flat id, default `deepseek-v4-flash` | No API key is required for the normal host-auth path |
| `aider` | API-backed provider, commonly OpenRouter | provider/model | Requires the credentials expected by Aider |
| `gemini` | Gemini CLI/provider credentials | provider model id | Uses the Gemini strategy |

The old “Aider is always the default” description is legacy documentation. The
TUI detects installed operators, stores the selected `NINJA_CODE_BIN`, and the
current configuration defaults are defined in the settings registry. Verify a
machine's choice with:

```bash
ninja-mcp config list
ninja-mcp config get NINJA_CODE_BIN
```

## Junie

Junie is host-authenticated through a JetBrains Account. Ninja checks that the
`junie` binary exists and that `junie --help` succeeds; it does not run a task
or make a network probe during discovery. The generated command is:

```bash
junie --model deepseek-v4-flash --output-format text -p . \
  --skip-update-check --task "Implement the requested change"
```

Set `NINJA_JUNIE_TIMEOUT` to change Junie's operator timeout. A caller may
explicitly supply `--auth`, but Ninja does not inject a secret into the normal
host-auth path.

## Host-Authenticated Operators

Claude Code, Junie, and OpenCode can use an existing host login. There is no
mandatory `OPENROUTER_API_KEY` when the selected operator does not need one.
The operator still needs to be installed and authenticated, and the TUI may
show a provider-specific model list. Docker does not copy these host sessions;
use an API-backed configuration or a deliberately extended image there.

## Models and Providers

Model ids are passed through to the selected strategy. OpenCode models normally
use `provider/model`; Junie models are flat ids; Claude maps short names such as
`sonnet` to the corresponding Claude Code model. The modern TUI loads providers
lazily when the Models tab opens and filters cached models after a short
debounce. Typing at least two characters shows suggestions; Enter also accepts
a custom model id.

```bash
NINJA_CODE_BIN=opencode NINJA_MODEL=opencode/glm-4.7 ninja-coder
NINJA_CODE_BIN=claude NINJA_MODEL=claude-sonnet-4 ninja-coder
NINJA_CODE_BIN=junie NINJA_MODEL=deepseek-v4-flash ninja-coder
```

Provider routing for Aider is still available with
`NINJA_OPENROUTER_PROVIDERS`. Operator-specific timeout settings include
`NINJA_OPENCODE_TIMEOUT`, `NINJA_CLAUDE_TIMEOUT`, and
`NINJA_JUNIE_TIMEOUT`.

## Routing and Timeouts

The public coder routes are `quick`, `sequential`, and `parallel`. Worktree
isolation is enabled by default for sequential and parallel plans, while quick
tasks are in place with an automatic safety commit. All routes use the
inactivity-first watchdog; see [Automatic Safety](AUTOMATIC_SAFETY.md).

## Legacy Notes

Older sections in this repository describe Ninja Coder 2.0 benchmarks, fixed
Aider defaults, or provider-specific model scores. They describe historical
experiments, not a guarantee of the `1.0.1` runtime. Prefer the current TUI,
`ninja-mcp config list`, and the source strategy registry when diagnosing a
machine-specific operator or model.
