# Model Selection

Ninja MCP `1.0.1` treats model selection as configuration, not as a promise of
a fixed benchmark ranking. Provider availability and operator capabilities can
change, so the TUI discovers models lazily and keeps a configured model id as
the source of truth.

## TUI Model Picker

Open the picker with:

```bash
ninja-mcp config models
```

### Operator vs. model (per module)

The **operator** is the coding CLI ninja delegates to (Opencode, Codex, Claude,
Aider, …). It is configured **per module**:

| Module | Setting | Runs through its operator |
| --- | --- | --- |
| Coder (quick/sequential/parallel) | `NINJA_CODE_BIN` | yes — writes/edits code |
| Secretary | `NINJA_SECRETARY_OPERATOR` | yes — `codebase_report` AI insights, `analyse_file` summary |
| Agent (orchestrator) | `NINJA_AGENT_OPERATOR` | yes — `plan` rationale, `review` summary |
| Researcher | `NINJA_RESEARCHER_OPERATOR` | search **engine** (perplexity/serper/duckduckgo), not a coding CLI |

Each module executes through its **own** operator + model. Text-only operations
(plan/review/analysis) run the CLI in a throwaway temp directory with the needed
context embedded in the prompt, so they can never modify your repository. If the
operator or its key is unavailable, they fall back to the built-in
heuristic/static output instead of failing.

Pick each module's operator from the dropdown in its **Models** tab section (the
coder one is at the top of the tab). Only operators actually installed on the
host are offered; changing one refreshes that module's provider list. **Settings
→ Detected Operators** is a shortcut for the coder operator.

The **model** is chosen per role (see the table below) and is scoped to that
role's operator (e.g. `opencode/...` vs `codex` flat ids). Researcher uses its
own engines — set the provider in **Settings → Search Provider**.

In the modern Textual UI, provider discovery begins when the Models tab opens.
Each role has a provider selector and a debounced autocomplete input. Type at
least two characters, choose a suggestion with Up/Down and Enter, or press
Enter on a custom id. `Esc` closes suggestions and returns focus to the input.
The picker is keyboard-driven and supports the RU layout bindings used by the
rest of the TUI.

The configured roles include coder, researcher, secretary, and agent. Task
models are stored separately:

| Setting | Meaning |
| --- | --- |
| `NINJA_MODEL_QUICK` | Fast/simple coder tasks |
| `NINJA_MODEL_SEQUENTIAL` | Dependent multi-step plans |
| `NINJA_MODEL_PARALLEL` | Independent parallel work |
| `NINJA_AGENT_MODEL` | Agent orchestration |

Inspect the effective values with:

```bash
ninja-mcp config list
ninja-mcp config get NINJA_MODEL_QUICK
```

## Operator-Aware Model IDs

The model format follows the selected operator:

- OpenCode and OpenRouter commonly use `provider/model`.
- Claude Code accepts names such as `claude-sonnet-4` and maps supported short
  names to Claude Code model ids.
- Junie uses a flat id, for example `deepseek-v4-flash`.
- Research providers may expose ids such as `sonar-reasoning`.

Junie is host-authenticated through JetBrains Account and does not require an
API key for the normal CLI path. Claude Code uses its host authentication;
OpenCode uses its own provider configuration. An API-backed operator still
requires the credentials expected by that operator.

## Task Routing

Model choice and isolation are related but separate settings:

| Route | Task shape | Default isolation |
| --- | --- | --- |
| Quick | One small, focused change | In place with safety commit |
| Sequential | Dependent steps | Detached worktree |
| Parallel | Independent steps; complexity may be `simple` or `complex` | Detached worktree |

The inactivity-first watchdog defaults to 90 seconds for quick tasks and 180
seconds for sequential and parallel tasks. See
[Automatic Safety](AUTOMATIC_SAFETY.md) for overrides.

## Configuration Examples

```bash
# Select an OpenCode model for a quick task.
NINJA_MODEL_QUICK=opencode/glm-4.7

# Select a host-authenticated Junie model.
NINJA_CODE_BIN=junie
NINJA_MODEL=deepseek-v4-flash

# Use a specific provider/model with OpenCode.
NINJA_CODE_BIN=opencode
NINJA_MODEL=opencode/glm-4.7
```

Do not copy old LiveBench scores or historical cost tables into operational
configuration. If a provider's catalog changes, use the live picker or enter
the provider's current model id explicitly.

## Legacy Documentation

Earlier versions of this file described hard-coded “default” models and exact
concurrency/cost claims. Those claims are historical and are intentionally not
used as `1.0.1` selection guarantees. The source of truth is the current
settings registry, provider discovery, and the installed operator.
