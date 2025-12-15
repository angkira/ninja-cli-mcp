# ninja-cli-mcp

An MCP (Model Context Protocol) stdio server that delegates all code-level work to AI coding assistants via **OpenRouter**. This enables a clean separation between planning agents (like Claude Code or GitHub Copilot CLI) and the code executor.

**Supports any OpenRouter model** including Claude, GPT-4, Qwen, DeepSeek, Gemini, Llama, and many more.

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Planning Agent                            │
│              (Claude Code / Copilot CLI / etc.)                  │
│                                                                  │
│  Sees: Plans, metadata, status, summaries                       │
│  Never sees: Raw file contents (unless inspecting separately)   │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP Protocol (stdio)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ninja-cli-mcp Server                          │
│                   (This Project - Python)                        │
│                                                                  │
│  Role: Thin orchestrator                                         │
│  - Accepts plan steps from planner                              │
│  - Translates to structured tasks for AI code CLI               │
│  - Tracks status, logs, metadata                                │
│  - Returns only summaries and status                            │
│                                                                  │
│  DOES NOT: Read/write user project files directly               │
└────────────────────────────┬────────────────────────────────────┘
                             │ Subprocess (with instructions)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       AI Code CLI                                │
│               (Configurable via OpenRouter)                      │
│                                                                  │
│  Role: Full executor with filesystem access                      │
│  - Reads and writes source files                                │
│  - Creates new files                                            │
│  - Runs tests and linters                                       │
│  - Performs self-review                                         │
│  - Iterates until tests pass (in full mode)                     │
│                                                                  │
│  Backend: Any OpenRouter model                                  │
│  - anthropic/claude-sonnet-4 (default)                          │
│  - openai/gpt-4o                                                │
│  - qwen/qwen3-coder                                             │
│  - deepseek/deepseek-coder                                      │
│  - And 200+ more models                                         │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Principle

> **"The planner never sees code; the executor (AI code CLI) sees and edits everything within an allowed scope."**

This separation provides:
- **Security**: Main planning agents don't have direct filesystem access
- **Modularity**: Easy to swap out the executor backend or model
- **Auditability**: Clear logs of what was delegated and what changed
- **Flexibility**: Use any OpenRouter model for code generation

## Supported Models

ninja-cli-mcp supports **any model available on OpenRouter**. Recommended models for code tasks:

| Model | ID | Description |
|-------|-----|-------------|
| Claude Sonnet 4 | `anthropic/claude-sonnet-4` | Default - excellent for complex code |
| Claude 3.5 Sonnet | `anthropic/claude-3.5-sonnet` | Fast and capable |
| GPT-4o | `openai/gpt-4o` | OpenAI's flagship model |
| GPT-4 Turbo | `openai/gpt-4-turbo` | Fast GPT-4 variant |
| Qwen3 Coder | `qwen/qwen3-coder` | Optimized for code generation |
| Qwen 2.5 Coder 32B | `qwen/qwen-2.5-coder-32b-instruct` | Large coding model |
| DeepSeek Coder | `deepseek/deepseek-coder` | Specialized for code |
| Gemini Pro 1.5 | `google/gemini-pro-1.5` | Google's advanced model |
| Llama 3.1 70B | `meta-llama/llama-3.1-70b-instruct` | Meta's open model |

See [OpenRouter Models](https://openrouter.ai/models) for the full list.

## Requirements

- **Python 3.11+**
- **uv** (Python package manager) - [Installation guide](https://docs.astral.sh/uv/getting-started/installation/)
- **git**
- **OpenRouter API key** - [Get one here](https://openrouter.ai/keys)
- **AI Code CLI** (optional) - The code executor binary

## Installation

### Quick Start (Recommended)

**The interactive installer is the single entry point** - it handles everything automatically:

```bash
git clone https://github.com/anthropics/ninja-cli-mcp.git
cd ninja-cli-mcp
./scripts/install_interactive.sh
```

The interactive installer will:
- 🐍 Check Python 3.11+ (prefers 3.12) and install `uv` if needed
- 📦 Install all dependencies automatically
- 🔑 Prompt for your OpenRouter API key (with secure hidden input)
- 🤖 Let you choose your preferred AI model interactively
- 🔍 **Auto-detect AI code assistants** (aider, cursor, continue, etc.)
- 🎯 **Automatically register with Claude Code** if installed
- ✅ Verify the installation with comprehensive checks
- ⚙️  Save configuration to `~/.ninja-cli-mcp.env`
- 🚀 Optionally add to your shell startup

**That's it!** If you have Claude Code installed, ninja-cli-mcp will be automatically registered and ready to use. No additional steps needed.

### Manual Installation

If you prefer manual setup:

#### 1. Clone the repository

```bash
git clone https://github.com/anthropics/ninja-cli-mcp.git
cd ninja-cli-mcp
```

#### 2. Run the basic installer

```bash
./scripts/install.sh
```

This will:
- Verify Python 3.11+ is installed
- Install uv if not present
- Install all dependencies
- Make scripts executable

#### 3. Set environment variables

```bash
# Required: OpenRouter API key
export OPENROUTER_API_KEY='your-api-key-here'

# Optional: Choose a model (default: anthropic/claude-sonnet-4)
export NINJA_MODEL='anthropic/claude-sonnet-4'

# Or use any OpenRouter model:
export NINJA_MODEL='openai/gpt-4o'
export NINJA_MODEL='qwen/qwen3-coder'
export NINJA_MODEL='deepseek/deepseek-coder'

# Optional: Custom AI Code CLI path (default: ninja-code)
export NINJA_CODE_BIN='/path/to/ninja-code'
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `OPENROUTER_API_KEY` | Yes* | - | OpenRouter API key |
| `OPENAI_API_KEY` | Yes* | - | Alternative to OPENROUTER_API_KEY |
| `NINJA_MODEL` | No | `anthropic/claude-sonnet-4` | Model to use (highest priority) |
| `OPENROUTER_MODEL` | No | - | Alternative model setting |
| `OPENAI_MODEL` | No | - | Alternative model setting (lowest priority) |
| `OPENAI_BASE_URL` | No | `https://openrouter.ai/api/v1` | API endpoint |
| `NINJA_CODE_BIN` | No | `ninja-code` | Path to AI Code CLI |
| `NINJA_TIMEOUT_SEC` | No | `600` | Default timeout in seconds |

*At least one of `OPENROUTER_API_KEY` or `OPENAI_API_KEY` must be set.

### Model Selection Priority

The model is selected in this order:
1. `NINJA_MODEL` (highest priority)
2. `OPENROUTER_MODEL`
3. `OPENAI_MODEL`
4. Default: `anthropic/claude-sonnet-4`

### Directory Layout

When the server runs, it creates a `.ninja-cli-mcp/` directory in the repository root:

```
.ninja-cli-mcp/
├── logs/           # Execution logs
├── tasks/          # Task instruction files (JSON)
└── metadata/       # Additional metadata
```

This is the **only** directory the MCP server writes to. All actual code changes are made by the AI code CLI.

## Running the Server

### Direct execution

```bash
./scripts/run_server.sh
```

Or using Python directly:

```bash
python -m ninja_cli_mcp.server
```

The server communicates via stdin/stdout using the MCP protocol.

## Connecting to Claude Code

### Automatic Registration (Recommended)

If you used the interactive installer (`./scripts/install_interactive.sh`), ninja-cli-mcp is **already registered** with Claude Code automatically! Just start using it:

```bash
claude
```

Then check available MCP tools with `/mcp` and look for ninja-cli-mcp tools.

### Manual Registration

If you need to register manually (or re-register):

```bash
./scripts/install_claude_code_mcp.sh
```

Or use the Claude Code CLI directly:

```bash
claude mcp add --transport stdio ninja-cli-mcp -- /path/to/ninja-cli-mcp/scripts/run_server.sh
```

### Verify the Connection

1. Start Claude Code: `claude`
2. Check MCP tools: `/mcp`
3. Look for ninja-cli-mcp tools in the list (ninja_quick_task, execute_plan_sequential, etc.)

## Connecting to Copilot CLI

### Setup script

```bash
./scripts/install_copilot_cli_mcp.sh
```

This creates a configuration file at `~/.config/copilot-cli/mcp-servers.json`.

### Prerequisites

Install GitHub Copilot CLI:

```bash
# Option 1: GitHub CLI extension
gh extension install github/gh-copilot

# Option 2: npm package
npm install -g @githubnext/github-copilot-cli
```

Note: MCP integration with Copilot CLI is evolving. Check the current documentation for the latest configuration method.

## MCP Tools

### ninja_quick_task

Execute a quick single-pass task using any OpenRouter model.

**Input:**
```json
{
  "task": "Add a hello() function that prints 'Hello World'",
  "repo_root": "/path/to/repo",
  "context_paths": ["src/"],
  "allowed_globs": ["src/**/*.py"],
  "deny_globs": ["**/__pycache__/**"]
}
```

**Output:**
```json
{
  "status": "ok",
  "summary": "Added hello() function to src/main.py",
  "notes": "Also added docstring",
  "logs_ref": ".ninja-cli-mcp/logs/20240101_120000_quick_task.log",
  "suspected_touched_paths": ["src/main.py"]
}
```

### execute_plan_sequential

Execute multiple plan steps in order.

**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "mode": "full",
  "global_allowed_globs": ["**/*.py"],
  "global_deny_globs": ["**/venv/**"],
  "steps": [
    {
      "id": "step-001",
      "title": "Add hello function",
      "task": "Create a hello() function",
      "context_paths": ["src/"],
      "allowed_globs": ["src/**/*.py"],
      "max_iterations": 3,
      "test_plan": {
        "unit": ["pytest tests/test_hello.py"],
        "e2e": []
      }
    }
  ]
}
```

**Modes:**
- `quick`: Single pass execution
- `full`: Includes coder → reviewer → tester → fix loop → final review

### execute_plan_parallel

Execute plan steps concurrently with a configurable fanout limit.

**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "mode": "quick",
  "fanout": 4,
  "global_allowed_globs": ["**/*.py"],
  "steps": [
    {"id": "1", "title": "Feature A", "task": "Implement A", "allowed_globs": ["src/a/**"]},
    {"id": "2", "title": "Feature B", "task": "Implement B", "allowed_globs": ["src/b/**"]}
  ]
}
```

**Output includes merge report:**
```json
{
  "status": "ok",
  "results": [...],
  "merge_report": {
    "strategy": "scope_isolation",
    "notes": "Steps executed with isolated scopes. Manual review recommended if scopes overlapped."
  }
}
```

### run_tests

Run test commands via the AI code CLI.

**Input:**
```json
{
  "repo_root": "/path/to/repo",
  "commands": ["pytest tests/", "npm test"],
  "timeout_sec": 600
}
```

### apply_patch

**Note:** This tool returns `not_supported` status. In this architecture, patches are created and applied by the AI code CLI, not by this server. Include patch instructions in task descriptions for other tools.

## Usage Scenarios

### Simple Quick Task

Ask the planner to implement a feature:

```
"Use ninja_quick_task to add a validate_email() function to src/utils.py that uses regex to validate email addresses."
```

The planner calls the tool, the AI code CLI implements it, and the planner receives only the status and summary.

### Sequential Plan Execution

For larger features requiring multiple steps:

```
"Use execute_plan_sequential with these steps:
1. Create the UserService class in src/services/
2. Add unit tests in tests/test_user_service.py
3. Update the API routes to use UserService"
```

### Parallel Plan Execution

For independent tasks that can run concurrently:

```
"Use execute_plan_parallel to implement these independent components:
- Authentication module (src/auth/)
- Logging module (src/logging/)
- Configuration module (src/config/)
Use fanout=3 to run all in parallel."
```

### Switching Models

Use different models for different tasks:

```bash
# Use Claude for complex architecture
export NINJA_MODEL='anthropic/claude-sonnet-4'

# Use GPT-4 for quick fixes
export NINJA_MODEL='openai/gpt-4o'

# Use Qwen for Python-specific tasks
export NINJA_MODEL='qwen/qwen3-coder'
```

## Security Notes

### Filesystem Access

- **AI Code CLI** has direct read/write access within the declared `repo_root`
- **MCP Server** only reads/writes to `.ninja-cli-mcp/` for logs and metadata
- **Planning Agents** never receive raw file contents from this server

### Path Traversal Protection

The server validates all paths to prevent escaping the repo root:
- Absolute paths must be within repo_root
- Relative paths are resolved against repo_root
- `..` components are rejected

### Scope Constraints

Use `allowed_globs` and `deny_globs` to restrict AI code CLI's access:

```json
{
  "allowed_globs": ["src/**/*.py", "tests/**/*.py"],
  "deny_globs": ["**/secrets/**", "**/.env*", "**/node_modules/**"]
}
```

## Development

### Run linter and tests

```bash
./scripts/dev.sh
```

### Individual commands

```bash
./scripts/dev.sh lint      # Run ruff linter
./scripts/dev.sh format    # Format code
./scripts/dev.sh typecheck # Run mypy
./scripts/dev.sh test      # Run pytest
```

### Smoke test

```bash
./scripts/smoke_test.sh
```

### Integration tests

Run integration tests with real API calls (uses minimal tokens):

```bash
./scripts/run_integration_tests.sh
```

**Note**: These tests make real API calls to verify end-to-end functionality. They're designed to use minimal tokens (estimated cost: $0.01-$0.05 per run). You'll need your OpenRouter API key configured.

The integration tests verify:
- ✅ Quick task execution with real AI models
- ✅ Metrics tracking and CSV generation
- ✅ Token usage and cost calculation
- ✅ CLI commands (list-models, show-config, etc.)
- ✅ OpenRouter API pricing fetch

## CLI Interface

For testing without MCP protocol:

```bash
# Quick task
python -m ninja_cli_mcp.cli quick-task \
  --repo-root /path/to/repo \
  --task "Add a hello function"

# Run tests
python -m ninja_cli_mcp.cli run-tests \
  --repo-root /path/to/repo \
  --commands "pytest tests/"

# Execute plan from file
python -m ninja_cli_mcp.cli execute-plan \
  --repo-root /path/to/repo \
  --plan-file plan.json \
  --full

# List available models
python -m ninja_cli_mcp.cli list-models

# Show current configuration
python -m ninja_cli_mcp.cli show-config

# View metrics summary
python -m ninja_cli_mcp.cli metrics-summary \
  --repo-root /path/to/repo

# View recent tasks
python -m ninja_cli_mcp.cli metrics-recent \
  --repo-root /path/to/repo \
  --limit 20

# Export metrics to CSV
python -m ninja_cli_mcp.cli metrics-export \
  --repo-root /path/to/repo \
  --output my_metrics.csv
```

## Metrics and Cost Tracking

ninja-cli-mcp automatically tracks token usage and estimated costs for every task execution. Metrics are stored in CSV format within your repository at `.ninja-cli-mcp/metrics/tasks.csv`.

### 📊 Experiment Notebooks

Want to compare models and analyze costs? Check out the **interactive Jupyter notebooks** in `notebooks/`:

- **[Model Comparison](notebooks/01_model_comparison.ipynb)** - Compare Qwen, Claude, Gemini on real tasks
  - 💰 Cost per task
  - ⚡ Speed benchmarks  
  - ✅ Success rates
  - 💎 Value scores
  
- **[Cost Analysis](notebooks/02_cost_analysis.ipynb)** - Deep dive into pricing
  - 🔄 Real-time OpenRouter pricing
  - 📅 Monthly cost projections
  - 💡 Cache savings analysis (~90% off!)
  - 🎯 Workload scenarios

Install notebook dependencies:
```bash
uv sync --extra notebooks
# or
uv pip install jupyter matplotlib seaborn pandas
```

See [notebooks/README.md](notebooks/README.md) for details.

### What's Tracked

For each task execution, the following metrics are recorded:

- **Task Information**: Task ID, timestamp, tool name, description
- **Model**: Which OpenRouter model was used
- **Token Usage**: Input tokens, output tokens, cache read tokens, cache write tokens, total tokens
- **Costs**: Real-time costs from OpenRouter API (input cost, output cost, cache costs, total cost in USD)
- **Performance**: Execution duration in seconds
- **Status**: Success/failure status
- **Context**: Repository root, file scope patterns, error messages (if any)

### Cost Tracking with Real-Time Pricing

ninja-cli-mcp automatically fetches **real-time pricing from the OpenRouter API** for accurate cost tracking. Pricing is cached for 24 hours to minimize API calls.

#### Pricing Features

- **Automatic API Fetching**: Pricing is retrieved from OpenRouter's `/api/v1/models` endpoint
- **Cache Support**: Tracks cache read/write tokens for models that support prompt caching (Claude, GPT-4, DeepSeek)
- **Fallback Pricing**: If API fetch fails, falls back to static pricing table
- **24-Hour Cache**: Pricing data is cached locally to reduce API calls

#### Cache Token Savings

Models that support [prompt caching](https://openrouter.ai/docs/prompt-caching) (Anthropic Claude, OpenAI, DeepSeek) can significantly reduce costs:

- **Cache Read**: ~90% cheaper than regular input tokens
- **Cache Write**: Slightly more expensive than input tokens (one-time cost)
- **Example**: Claude Sonnet 4 cache read tokens cost ~$0.03/M vs $3/M for regular input

The metrics system automatically tracks cache tokens when they appear in CLI output.

### Viewing Metrics

#### Summary View

Get an overview of all tasks:

```bash
python -m ninja_cli_mcp.cli metrics-summary --repo-root /path/to/repo
```

Output:
```
Metrics Summary
============================================================
  Total tasks:        42
  Successful tasks:   38
  Failed tasks:       4
  Total tokens:       156,234
  Total cost:         $1.8750

Model Usage:
------------------------------------------------------------
  anthropic/claude-sonnet-4: 30 tasks
  openai/gpt-4o: 8 tasks
  qwen/qwen3-coder: 4 tasks
```

#### Recent Tasks

View detailed information about recent task executions:

```bash
python -m ninja_cli_mcp.cli metrics-recent --repo-root /path/to/repo --limit 5
```

Output:
```
Recent Tasks (last 5)
================================================================================

✓ 2024-01-15T14:23:45
  Tool:     ninja_quick_task
  Model:    anthropic/claude-sonnet-4
  Tokens:   2,345 (1,500 in, 845 out)
  Cost:     $0.017175
  Duration: 12.34s
  Task:     Add user authentication middleware to API routes

✗ 2024-01-15T14:20:12
  Tool:     ninja_run_tests
  Model:    openai/gpt-4o
  Tokens:   1,234 (800 in, 434 out)
  Cost:     $0.006340
  Duration: 8.76s
  Task:     Run test suite
  Error:    Test failed: 3 assertions failed in test_auth.py
```

#### Export Metrics

Export all metrics to a CSV file for analysis:

```bash
python -m ninja_cli_mcp.cli metrics-export --repo-root /path/to/repo --output analysis.csv
```

You can then analyze the CSV with tools like Excel, Python pandas, or R.

### Metrics CSV Format

The metrics CSV file contains the following columns:

| Column | Description |
|--------|-------------|
| `task_id` | Unique identifier for the task |
| `timestamp` | ISO 8601 timestamp |
| `model` | OpenRouter model ID |
| `tool_name` | MCP tool that was called |
| `task_description` | Brief description of the task |
| `input_tokens` | Number of input tokens |
| `output_tokens` | Number of output tokens |
| `total_tokens` | Total tokens (input + output + cache) |
| `cache_read_tokens` | Number of cache read tokens |
| `cache_write_tokens` | Number of cache write tokens |
| `input_cost` | Input cost from OpenRouter pricing (USD) |
| `output_cost` | Output cost from OpenRouter pricing (USD) |
| `cache_read_cost` | Cache read cost (USD) |
| `cache_write_cost` | Cache write cost (USD) |
| `total_cost` | Total cost (USD) |
| `duration_sec` | Execution duration in seconds |
| `success` | Whether the task succeeded (True/False) |
| `execution_mode` | Mode: quick, full, test, etc. |
| `repo_root` | Repository root path |
| `file_scope` | File glob patterns |
| `error_message` | Error message (if failed) |

### Privacy and Data Storage

- Metrics are stored locally in your repository under `.ninja-cli-mcp/metrics/`
- Token counts and costs are tracked, but **actual code and prompts are NOT stored in metrics**
- Only task descriptions, status, and metadata are saved
- Add `.ninja-cli-mcp/` to your `.gitignore` if you don't want to commit metrics

### Cost Optimization Tips

1. **Choose the right model**: Use lighter models like Qwen Coder or DeepSeek for simpler tasks
2. **Use quick mode**: Avoid full mode (with review/test loops) when unnecessary
3. **Limit scope**: Use `allowed_globs` to restrict the AI's context to relevant files only
4. **Monitor metrics**: Regularly check `metrics-summary` to identify expensive operations
5. **Batch tasks**: Combine related changes into a single task when possible

Example of switching to a cost-effective model:

```bash
# Use free Qwen model for simple refactoring
export NINJA_MODEL='qwen/qwen3-coder'
python -m ninja_cli_mcp.cli quick-task --repo-root . --task "Add docstrings to utils.py"

# Use Claude for complex architecture changes
export NINJA_MODEL='anthropic/claude-sonnet-4'
python -m ninja_cli_mcp.cli quick-task --repo-root . --task "Refactor authentication system"
```

## Limitations & Assumptions

### AI Code CLI Interface

This implementation assumes the AI code CLI supports:
- `--prompt "..."` for passing task instructions
- `--cwd /path` for setting working directory
- `--yes` for non-interactive mode

If the actual interface differs, adjust `ninja_driver.py`:
- `_build_command()` method constructs the CLI invocation
- `_write_task_file()` creates instruction documents

### Parallel Execution

Parallel steps run against the same repository. For stronger isolation:
- Use non-overlapping `allowed_globs` for each step
- Consider implementing git worktrees for full isolation (noted in merge_report)

### Windows Support

Currently optimized for Linux and macOS. For Windows:
- Use WSL (Windows Subsystem for Linux)
- Run the server within WSL
- Adjust paths accordingly

## Troubleshooting

### "AI Code CLI not found"

```bash
# Check if it's installed
which ninja-code

# Or set the path explicitly
export NINJA_CODE_BIN=/path/to/ninja-code
```

### "API key not set"

```bash
export OPENROUTER_API_KEY='your-key-here'
```

### View execution logs

Logs are stored in `.ninja-cli-mcp/logs/`:

```bash
ls -la .ninja-cli-mcp/logs/
cat .ninja-cli-mcp/logs/latest.log
```

### MCP connection issues

1. Verify the server starts correctly:
   ```bash
   ./scripts/run_server.sh
   ```
   
2. Check Claude Code MCP registration:
   ```bash
   claude mcp list
   ```

### Check current model

```bash
python -m ninja_cli_mcp.cli show-config
```

## License

MIT License - see [LICENSE](LICENSE) for details.
