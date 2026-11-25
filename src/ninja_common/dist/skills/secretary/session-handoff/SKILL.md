---
name: session-handoff
description: Close a working session with secretary_session_report and secretary_update_documentation so decisions, files and next steps survive into the next session.
---

# Session handoff

A session that ends without a written record costs the next one its whole
discovery phase. Two tools cover it: one reads what happened, one writes the
durable part.

## When to use

- The work is pausing: end of session, end of a task, before handing to a
  different agent or a human.
- A decision was made that is not visible in the diff — a rejected approach, a
  constraint, a deployment caveat.
- Someone will pick this up without the conversation.

Do not use it after a trivial question. A one-line answer needs no handoff.

## Step 1 — read the session back

`secretary_session_report` takes an optional `session_id` (defaults to
`default`) and returns:

- `session_id`, `started_at`, `last_updated`;
- `tools_used` — the tools called in this session;
- `files_accessed` — files read or written;
- `summary`, `metadata` — free-form context the server accumulated.

Use `tools_used` as a checklist of what actually got done, and
`files_accessed` as the candidate change set. It is evidence, not a substitute
for `git status`: verify the real diff before describing what changed.

## Step 2 — decide what to persist

Persist, in this order of importance:

1. **Decisions and why.** What was chosen, what was rejected, and the constraint
   that forced it. A future reader can recover *what* changed from git; they
   cannot recover *why*.
2. **State.** What is finished, what is half-finished and where it stops. Name
   the branch (`ninja/*` isolation branches in particular — unmerged work is
   invisible otherwise) and any job or task id still running.
3. **Next steps.** The specific next action, with the file or command to start
   from. "Continue the refactor" is not a next step.
4. **Verification.** What you ran and what it returned. "Tests pass" without the
   command is an assertion, not a record.
5. **Open questions for the user.** Anything you had to assume.

Leave out the narration of the session. The value is the residue.

## Step 3 — write it

`secretary_update_documentation` takes:

- `module_name` — the module the docs belong to (`coder`, `researcher`,
  `secretary`, `agent`);
- `doc_type` — `readme`, `api` or `changelog`;
- `content` — the text;
- `mode` — `replace` (default), `append` or `prepend`.

It writes to a fixed path derived from `module_name` and `doc_type`:
`docs/<module_name>/README.md`, `docs/<module_name>/API.md` or
`docs/<module_name>/CHANGELOG.md`. There is no path argument and no `repo_root`
argument, so the path resolves against the server's working directory — confirm
the returned `doc_path` is inside the repository before you report success.

Choose `mode: "append"` for a changelog entry or a new decision log section;
`replace` overwrites the whole file and will destroy history. Read the target
first if you intend to replace it.

The result gives `status`, `doc_path` and `changes_made` — quote `doc_path` when
you tell the user where the record landed.

## Step 4 — verify

1. Read `doc_path` back and confirm the new content is there. A `status: "ok"`
   is the write, not the proof.
2. Confirm the session report's `files_accessed` matches the real change set.
3. Give the user a short handoff in the reply: decisions, state, next action,
   and the doc path. That reply is what they will read first next time.
