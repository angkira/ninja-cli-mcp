# Automatic Safety

Ninja Coder `1.0.1` chooses isolation by task type. The important distinction
is not “safety on/off”, but whether a task is a quick in-place edit or a
complex plan that should leave the main checkout untouched.

## Default Worktree Policy

| Task type | Public route | Default | Result |
| --- | --- | --- | --- |
| `quick` | `coder_simple_task` | in place | An automatic `[ninja-auto-save]` commit protects the current branch |
| `sequential` | `coder_execute_plan_sequential` | isolated | A detached `ninja/*` worktree under the Ninja cache |
| `parallel` | `coder_execute_plan_parallel` | isolated | A detached `ninja/*` worktree under the Ninja cache |

Sequential and parallel worktrees create a snapshot commit inside the
worktree. Review the branch and merge it when ready. The main checkout is not
modified by the normal isolated path.

Parallel routing also has a complexity choice: `simple` is for independent
small work, while `complex` uses the full plan/worktree path.

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `NINJA_WORKTREE_MODE` | `on` | Global switch; `off` disables isolation for all task types |
| `NINJA_WORKTREE_QUICK` | `off` | `on`, `off`, or `auto` for quick tasks |
| `NINJA_WORKTREE_SEQUENTIAL` | `on` | Same values for sequential plans |
| `NINJA_WORKTREE_PARALLEL` | `on` | Same values for parallel plans |
| `NINJA_WORKTREE_MAX_AGE_DAYS` | `2` | Age threshold for automatic worktree pruning |
| `NINJA_SAFETY_MODE` | `auto` | Handling of dirty-check safety commits: `auto`, `strict`, `warn`, or `off` |

`auto` for a per-type worktree variable follows
`NINJA_WORKTREE_MODE`. Setting the global mode to `off` deliberately returns
all task types to the legacy current-branch safety-commit behavior.

```bash
ninja-mcp config
git worktree list
git merge ninja/<slug>-<timestamp>-<uid>
git worktree prune
```

The worktree root is under `$XDG_CACHE_HOME/ninja-mcp/worktrees/` when that
variable is set, otherwise under the platform cache directory.

## Inactivity-First Timeout

Task execution watches for output inactivity rather than treating a fixed wall
clock as the primary failure condition. CPU activity can extend the watchdog
while a CLI is computing. Output resets the inactivity timer; stderr is not
counted unless `NINJA_INACTIVITY_COUNT_STDERR=1`.

Defaults are:

| Task type | Inactivity threshold |
| --- | ---: |
| quick | 90 seconds |
| sequential | 180 seconds |
| parallel | 180 seconds |

Use `NINJA_INACTIVITY_TIMEOUT` for one value across task types, or use
`NINJA_INACTIVITY_TIMEOUT_QUICK`,
`NINJA_INACTIVITY_TIMEOUT_SEQUENTIAL`, and
`NINJA_INACTIVITY_TIMEOUT_PARALLEL`. Absolute deadlines and operator-specific
timeouts remain separate upper bounds; they are not replacements for the
inactivity watchdog.

## Recovery and Cleanup

For an in-place quick task, inspect the automatic commit:

```bash
git show --stat HEAD
```

For an isolated plan, inspect the worktree branch before merging:

```bash
git merge --no-ff ninja/<branch>
```

Pruning is safe only after the result has been reviewed or merged:

```bash
```

Ninja also creates safety tags where the configured safety path requires a
recovery point. Treat `git reset --hard` as a deliberate recovery operation,
not as a normal cleanup step.

## Deliberate Exceptions

These paths retain in-place behavior because moving them into a per-call
worktree would break their execution contract:

- OpenCode native session execution, which relies on `--session` or `--continue`;
- OpenCode serve-pool mode (`NINJA_OPENCODE_SERVE_MODE=1`), rooted at
  `repo_root`;
- synchronous `execute_sync`, which does not create worktrees.

## Host Authentication

Worktree isolation changes the checkout location, not the operator's host
authentication. `claude`, `junie`, and `opencode` inherit the host environment
and their own authenticated sessions; they do not require a duplicate API key
just because the task is isolated. Junie uses JetBrains Account authentication
and the `junie --model <id> ... --task <prompt>` command. Docker is different:
it intentionally does not mount host home directories or host CLI credentials.
