---
name: pipeline-diagnosis
description: Choose between agent_run_and_diagnose and agent_exec_pipeline, read distilled failure output, use agent_distill_logs for clustered errors, and escalate at the right point.
---

# Diagnose a failing build or test run

`agent_run_and_diagnose` runs one command and returns a distilled failure list;
`agent_exec_pipeline` runs several commands in order. They overlap, and picking
wrongly is why agents read raw logs for ten minutes.

## When to use which

| Situation | Tool |
| --- | --- |
| One test or lint command, you need the failures | `agent_run_and_diagnose` |
| Build then test, then a smoke check — order matters | `agent_exec_pipeline` |
| One command whose *output* you need verbatim | `agent_exec_command` |
| Noisy logs, repeated errors, tracebacks | `agent_distill_logs` |

Diagnose output is already condensed. Do not pipe it through `head`, and do not
re-run the same command with `agent_exec_command` to "see the real output" — you
will get the same failures with less structure.

## Run and diagnose

1. Pass the exact command and note the `framework_hint` (`pytest`, `ruff`,
   `mypy`, `jest`) so the parser picks the right failure shape.
2. Bound it: `timeout` in seconds, `cwd` if the project root is not the run
   directory. Mutating commands additionally need `allow_write`.
3. Read the counters first — `passed_count`, `failed_count`, `skipped_count`,
   `error_count`, and `success`. A run with `failed_count: 0` but
   `error_count > 0` failed during collection, not in a test.
4. Then read `failures`. Each entry has `test_name`, `file_path`, `line_number`,
   `error_message` and optionally `traceback`. That is the whole signal: fix
   from `error_message` and the location, not from `condensed_output`.
5. Only if the counters and `failures` disagree, look at `condensed_output`.
   `truncated: true` means the cap was hit — narrow the command to a subset
   (`-k`, one file, one package) rather than asking for more output.
6. Check `safety_warnings`; a dry-run note may explain a refused or surprising
   step.

## Pipelines

`agent_exec_pipeline` takes `steps` in order, each with `command`, optional
`name`, `cwd`, `timeout`, `allow_write` and `continue_on_error`, plus
plan-level `repo_root`, `cwd` and `fail_fast` (default true).

1. Order steps so the cheapest failure comes first: format check, lint, unit
   tests, integration, smoke.
2. Keep `fail_fast: true` unless you deliberately want a full sweep; a later
   step on a broken build produces noise, not information.
3. Set `continue_on_error: true` only on steps whose failure is expected or
   independent (a lint report you want in full).
4. Read each `steps[]` entry: `success`, `returncode`, `duration_seconds`,
   `skipped` and `condensed_output`. A skipped step is not a pass — with
   `fail_fast` the rest are skipped after the first failure.
5. Fix the first failing step only. Re-run the pipeline after the fix; do not
   patch a later step around an earlier failure.

## Distilling logs

When the question is "why did the daemon die" rather than "which test failed":

1. `agent_distill_logs` with `module`, optional `level`, `limit` (capped at 200)
   and `session_id`. It clusters repeated messages and isolates tracebacks.
2. Read the clusters: `pattern`, `count`, `level`, `first_seen`, `last_seen`,
   `sample_line`. The cluster with a high `count` is usually the cause; the
   identical messages at the end of a run are the symptom.
3. Use `agent_tail_logs` only when you need the literal surrounding lines of one
   cluster — it returns raw entries and does no clustering.
4. Prefer a `level` filter over a bigger `limit`. Two hundred unfiltered lines
   hide the one ERROR you need.

## Escalation

Stop and report when:

- the same command fails identically twice — the failure is deterministic and
  needs a code or environment change, not another run;
- the failure is outside the repository (missing binary, missing credential,
  unavailable service);
- the fix would require mutating infrastructure, killing a process or touching
  the user's session — ask first;
- the diagnosis is empty while the command clearly fails: say the parser did not
  recognise the output and paste the command you ran, rather than guessing.
