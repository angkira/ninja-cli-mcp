---
name: guarded-shell-operations
description: Run single shell commands with agent_exec_command under its mutation guard, triage with agent_tail_logs, agent_processes and agent_jobs_overview, and never touch the user's session.
---

# Guarded shell operations

`agent_exec_command` runs one command under a sandbox that refuses dangerous
patterns outright and refuses anything that looks like a write unless you opt
in.

## When to use

- One command: inspect state (`git status`, `ls`, `git log`), read a value,
  check a port, run one test.
- Triage: what is running, what is failing, what is queued.

Use `agent_run_and_diagnose` instead when the command is a test or lint run and
you want the failures distilled. Use `agent_exec_pipeline` when the steps must
happen in order.

## The mutation guard

Arguments: `command`, `repo_root` (required), `cwd`, `timeout`, `allow_write`.

Without `allow_write`:

- read-only commands run normally: `git status`, `git log`, `git diff`,
  `ls`, `cat`, `grep`, `rg`, `pytest --collect-only`, `ps`, `curl -s` reads;
- anything matching the write heuristics is refused with
  "Refused: command looks like it mutates files/state" — that includes `rm`,
  `mv`, `cp`, `mkdir`, `tee`, `sed -i`, `chmod`, file redirections to real
  paths, `git add|commit|push|checkout|reset|clean|merge|rebase|stash`,
  `pip|uv|npm|yarn install|add|remove`, and `docker|podman run|build|compose`.

With `allow_write: true` the write heuristics pass, but two things still apply:

1. the destructive deny-list is absolute — recursive removal of `/`, forks
   bombs, `mkfs`, `dd` onto a raw device, raw disk overwrites, and
   `shutdown|reboot|halt|poweroff|init 0|init 6` are refused regardless;
2. a safety dry-run may run first and return notes in `safety_warnings`. Read
   them before trusting the result.

Set `allow_write` only for the command that needs it, and scope `cwd` / 
`repo_root` to the project. Never pass `allow_write` to "make the error go
away"; a refused command is telling you the command is a write.

## Host safety — non-negotiable

The user is working on this machine, often inside a graphical session with this
agent in it. Never run, with or without `allow_write`:

- `pkill`, `killall`, `pgrep ... | xargs kill`, a negative PGID `kill`, or
  `kill -1`;
- `loginctl terminate-session`, `loginctl kill-session`, `systemctl --user
  stop` or `restart` of the session/display-manager/user units;
- `shutdown`, `reboot`, `poweroff`, `init 0`, `init 6`.

To act on a process inside a container, use `docker exec <container> kill ...`;
to act on a container, `docker stop|restart <container>`. If something outside
that needs killing, stop and ask the user — do not improvise.

## Triage before acting

1. `agent_processes` (no arguments) — daemon statuses plus host resource stats.
   Read-only; start here after "it stopped working".
2. `agent_jobs_overview` with an optional `limit` — pending background jobs and
   tasks. Read-only. Use it to see whether a run is queued, working or stuck.
3. `agent_tail_logs` with `module`, `level`, `limit` (capped at 200) and
   `session_id` — the last N entries. Use it for a quick look at one module.
4. Only then run a command to confirm a hypothesis.

## Reading the result

- `success` reflects exit code 0; `returncode` is the real code. A non-zero
  exit with `success: false` is a normal outcome, not a tool failure.
- `stdout` / `stderr` are capped and redacted; `truncated: true` means you are
  not seeing everything — narrow the command instead of raising the cap.
- `summary` is the one-line outcome; report it, plus the specific line from
  `stderr` that explains a failure.
- A refused command returns `success: false` with a `Refused: ...` summary.
  Change the command or ask; do not retry identically.
