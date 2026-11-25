---
name: sequential-plan-authoring
description: Write coder_execute_plan_sequential steps that actually succeed, covering step granularity, context_paths, allowed_globs and deny_globs, test_plan and ordering.
---

# Author a sequential plan that succeeds

A plan is a list of steps under `steps`. Each step is a separate CLI run, so
every step must be self-sufficient: the agent sees only the repository, the
step's `task`, and `context_paths`.

## When to use

Use `coder_execute_plan_sequential` (or `coder_submit_sequential`) when the work
is multi-file or order matters. Use `coder_execute_plan_parallel` only when the
steps touch disjoint files and would not read each other's output.

## Step shape

Each entry in `steps` accepts:

- `task` (required) — the specification for this step;
- `id` and `title` — optional labels, auto-generated when omitted;
- `context_paths` — files or directories the agent should read;
- `allowed_globs` / `deny_globs` — write scope for this step;
- `max_iterations` — test-fix loop budget in `full` mode (1-10, default 3);
- `test_plan` — `{"unit": [...], "e2e": [...]}` commands to run;
- `constraints` — `{"max_tokens": N, "time_budget_sec": N}`, `0` means unlimited.

Plan-level arguments are `repo_root`, `mode` (`quick` or `full`),
`use_dialogue_mode`, `global_allowed_globs` and `global_deny_globs`.

## Rules that prevent most failures

1. One concern per step. "Add the model, the migration, the route and the test"
   is four steps, not one. A step whose task spans unrelated files fails and
   takes the next steps down with it.
2. State behaviour, not keystrokes. Name the file, the symbol, the signature,
   the error case. "In `src/api/routes.py` add `POST /login` returning 401 on a
   bad password" beats "wire up login".
3. Every step must be verifiable. If you cannot describe how to check it, it is
   not a step yet. Put the command in `test_plan.unit` (or `test_plan.e2e`) and
   keep it fast and non-interactive.
4. `context_paths` is attention, not permission. Include the files the step must
   read and the ones it will edit. Do not dump the whole repository in — the
   agent will still write only inside the allowed globs.
5. Never mix directories and individual files in one step's `context_paths` when
   the configured CLI is Aider; give it all directories or all files.
6. `allowed_globs` is the only place writes are permitted. Set it to the
   smallest prefix that covers the step (`src/api/**/*.py`), not `**/*`.
7. `deny_globs` protects what must not move: migrations already applied,
   generated clients, lockfiles, vendored trees.
8. Order steps that share a file. Two steps editing the same module in sequence
   is fine; in parallel it is a merge conflict. The first step's change is
   visible to the second, so describe the second as a delta on the first.

## Procedure

1. Read the code the plan will change (`secretary_codebase_report`,
   `secretary_file_search`, or plain reads) so the `task` text can name real
   symbols.
2. Draft steps as a numbered list; split any step with more than one verb in its
   title.
3. Assign `context_paths` and `allowed_globs` per step; hoist anything shared
   into `global_allowed_globs` / `global_deny_globs`.
4. Attach a `test_plan` to every step that can be tested, plus one final
   integration step that runs the full suite.
5. Execute with `mode: "full"` when a review/fix loop is worth the time,
   `mode: "quick"` for mechanical edits.
6. Inspect the returned `overall_status` (`success`, `partial`, `failed`) and
   each step's `status` (`ok`, `fail`, `skipped`), plus `files_modified` and
   `patch_path`. A `partial` plan leaves the tree in an intermediate state —
   check `files_modified` before continuing.

An empty or whitespace-only `task` is rejected with an indexed validation error
(`InvalidPlanInput`); the schema is permissive on purpose so you see which step
is wrong.
