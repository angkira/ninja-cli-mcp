---
name: worktree-review-merge
description: Review, merge or discard the ninja/* isolation branches that coder plans leave behind, using coder_branches_list, coder_branch_merge and coder_branch_discard.
---

# Review and land a ninja/* branch

Multi-step coder work (`coder_execute_plan_sequential`,
`coder_execute_plan_parallel` with `complexity: "complex"`) does not touch your
checkout. It commits onto an isolation branch named `ninja/*`, then removes the
checkout. The branch is the deliverable; your working tree is unchanged until
you merge it.

`coder_simple_task` and `complexity: "simple"` edits run in place and produce no
branch.

## When to use

- A plan result came back with `patch_path` set, or `overall_status` of
  `success` / `partial` and you expected files to exist.
- You need to know whether earlier agent work is still unmerged.

## Procedure

1. List what exists: `coder_branches_list` with `{"repo_root": "<abs path>"}`.
   Each entry has `branch`, `head`, `committed_at` and `subject`; newest first.
2. Confirm the current checkout is where you want the merge to land. The merge
   targets whatever branch is checked out in `repo_root`; there is no target
   argument.
3. Review before merging. The branch is a normal git ref:
   `git -C <repo_root> log --oneline <main>..<branch>` and
   `git -C <repo_root> diff <main>...<branch>`. Check for stray files outside
   the planned scope, deleted tests, debug prints, secrets and lockfile churn.
   `agent_review` with `repo_root` and `file_paths` will flag syntax errors and
   swallowed exceptions without touching the tree.
4. Merge: `coder_branch_merge` with `{"repo_root": ..., "branch": "ninja/..."}`.
   It refuses anything that is not a `ninja/*` branch. A conflicting merge is
   aborted and the repository is left unchanged — resolve nothing by hand at
   that point, discard or re-plan instead.
5. Verify the merge actually landed: the result's `status` must be `ok`, and
   `head` is the new HEAD commit. Then run the tests yourself
   (`agent_run_and_diagnose`); a clean merge says nothing about a green build.

## Discarding

`coder_branch_discard` with `{"repo_root": ..., "branch": "ninja/..."}` deletes
the branch. Without `force` it refuses when the branch has commits that are not
in your current branch; that refusal is the safety net, not an error to route
around.

Only pass `"force": true` after you have decided the work is worthless and have
told the user which branch is about to be lost. On a legacy connection the
server may raise a confirmation prompt; on 2026-07-28 there is no back-channel
mid-call, so it simply keeps refusing until `force` is supplied.

Never discard a branch you have not listed, and never discard one whose name you
did not read from `coder_branches_list` in this session.

## Checklist before merging

- The branch name matches the plan you just ran, not an older run.
- The diff touches only files the plan claimed (`files_modified`).
- No `patch_path` is left unread — it is the same change as a patch file.
- Tests were run against the merged tree, not only inside the worktree.
- The user knows a merge is about to happen if their tree was dirty: a dirty
  working tree can block or complicate the merge, so check `git status` first.
