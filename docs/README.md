# Documentation Index

Start here for the current `1.3.1` behavior:

- [Project quickstart](../README.md)
- [Docker quickstart](container-quickstart.md)
- [Background execution with MCP Tasks](MCP_TASKS.md)
- [Automatic safety, worktrees, and timeouts](AUTOMATIC_SAFETY.md)
- [CLI strategies and host authentication](CLI_STRATEGIES.md)
- [Model selection and autocomplete](MODEL_SELECTION.md)
- [TUI installer](TUI_INSTALLER.md)
- [Configuration reference](CONFIGURATION.md)
- [Secrets & API keys](SECRETS.md)
- [Installation modes](INSTALLATION_MODES.md)
- [MCP architecture](MCP_ARCHITECTURE.md)
- [Editor integrations](EDITOR_INTEGRATIONS.md)
- [Coder architecture](coder/ARCHITECTURE.md)
- [Researcher guide](researcher/README.md)
- [Secretary guide](secretary/README.md)
- [Release history](../CHANGELOG.md)

### Agent CLI Commands and Tools

| Command | MCP Tool | Purpose |
| --- | --- | --- |
| `run-and-diagnose` | `agent_run_and_diagnose` | Execute test/build commands and distill diagnostic outcomes |
| `pipeline` | `agent_exec_pipeline` | Execute ordered sequence of commands with fail-fast policy |
| `distill-logs` | `agent_distill_logs` | Cluster and deduplicate logs into tracebacks and patterns |
| `analyze` | `agent_analyze` | Analyze repository codebase and structure |
| `review` | `agent_review` | Review changed files without modifications |
| `exec-command` | `agent_exec_command` | Execute guarded shell command |
| `tail-logs` | `agent_tail_logs` | Query and tail structured logs |
| `processes` | `agent_processes` | Snapshot daemon status and host resources |
| `jobs-overview` | `agent_jobs_overview` | Summarize background jobs and tasks |

Some files under `docs/` describe historical experiments or migration paths.
When a historical document conflicts with the current CLI, prefer the README,
the files above, and `ninja-mcp <command> --help`.
