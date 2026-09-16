# Plan: Autonomous Compound Routines & Context Distillation for ninja-agent

Date: 2026-09-16
Status: In Progress
Author: Lead Architect

## 1. Objective
Transform `ninja-agent` from a low-level atomic command executor into an outcome-driven autonomous routine runner. Maximize throughput and token efficiency for leading reasoning models (e.g. Fable 5.1 / Claude 3.7) by executing compound tasks and distilling execution outputs locally.

## 2. Core Components

### A. Compound Task: `run_and_diagnose`
- **Goal**: Execute test suites or build commands, automatically extract failures, stack traces, and test counts (`passed`, `failed`, `skipped`, `errors`), stripping noisy passing logs and ANSI codes.
- **Tools**:
  - `agent_run_and_diagnose` (MCP tool + CLI subcommand `run-and-diagnose`)
- **Behavior**:
  - Zero-exit code: compact outcome (`OK, 1468 passed`).
  - Non-zero or failure: parses pytest/ruff/mypy/generic output, extracts failing tests, root cause, error message, and minimal clean traceback.

### B. Compound Task: `exec_pipeline`
- **Goal**: Run an ordered batch of commands (e.g. `["uv sync", "ruff check", "pytest tests/unit"]`) in a single round-trip.
- **Policy**: `fail_fast` (default True), step-level timing, step-level `allow_write` and `timeout`.
- **Tools**:
  - `agent_exec_pipeline` (MCP tool + CLI subcommand `pipeline`)

### C. Context Condensation: `distill_logs` / `compress_logs`
- **Goal**: Aggregate, cluster, and deduplicate repetitive log lines (e.g. repeated connection errors), extracting unique patterns, counts, and isolated error traces.
- **Tools**:
  - `agent_distill_logs` (MCP tool + CLI subcommand `distill-logs`)

## 3. Delegation Strategy & Architecture

1. **Phase 1: Implementation (py-developer)**
   - `src/ninja_agent/runner.py`: Add `DiagnosticsDistiller`, `LogDistiller`, `exec_pipeline`, `run_and_diagnose`, `distill_logs` to `RunnerToolExecutor`.
   - `src/ninja_agent/models.py`: Add Pydantic v2 schemas for all new requests and results.
   - `src/ninja_agent/tools.py`: Expose methods in `AgentToolExecutor` with `@rate_balanced` and `@monitored`.
   - `src/ninja_agent/server.py`: Register MCP tools with `execution=ToolExecution(taskSupport="optional")` and route in `call_tool`.
   - `src/ninja_agent/cli.py`: Implement CLI subcommands `run-and-diagnose`, `pipeline`, `distill-logs`.

2. **Phase 2: Test Suite (qa-engineer)**
   - Unit tests for `DiagnosticsDistiller` (pytest output parsing, ruff parsing, generic failures).
   - Unit tests for `LogDistiller` (clustering, deduplication, timestamp normalization).
   - Unit tests for `RunnerToolExecutor.run_and_diagnose` and `exec_pipeline` (fail-fast, timing, write guard).
   - Unit & CLI tests for new commands and MCP tool declarations.
   - Run full project test suite to ensure zero regressions.

3. **Phase 3: Documentation & Verification**
   - Record decisions in `.session/2026-09-16_ninja_agent_autonomous.md`.
