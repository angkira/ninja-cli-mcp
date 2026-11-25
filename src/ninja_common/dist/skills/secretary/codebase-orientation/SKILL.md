---
name: codebase-orientation
description: Orient yourself in an unfamiliar repository using secretary_codebase_report, then narrow with secretary_file_search and read one file with secretary_analyse_file.
---

# Orient in a codebase

Three read-only tools, in this order: report → search → analyse. Using them out
of order is why agents grep a whole tree for a symbol they could have found from
the layout.

## When to use

- First contact with a repository, or after a long gap.
- Before planning any change: you need to know the languages, entry points and
  where tests live.
- When a file search returns too much and you need to narrow it.

## Step 1 — the report

`secretary_codebase_report` takes `repo_root` (absolute path) plus optional
`include_patterns` (e.g. `["**/*.py", "**/*.ts"]`) and `exclude_patterns` (e.g.
`["**/node_modules/**", "**/dist/**"]`).

It returns:

- `report` — markdown: project structure, per-extension counts and lines, and a
  dependency section;
- `metrics` — the same numbers as data, so you can compare directories without
  parsing prose;
- `file_count` — total files analysed;
- `status` — `ok` or `error`.

Always exclude vendored and generated trees. An unfiltered report on a
repository with `node_modules` is a report about `node_modules`.

Read the report for three things: the top-level layout, which extensions
dominate, and where the tests are. Then stop reading and go narrower.

## Step 2 — narrow with search

`secretary_file_search` takes `pattern` (glob, required), optional
`content_regex` and optional `repo_root` (defaults to the current directory).

- Start with the narrowest pattern that could match: `src/api/**/*.py` before
  `**/*.py`.
- Use `content_regex` to filter by content, not by name: `pattern:
  "src/**/*.py"` with `content_regex: "class .*Service"`. This is the cheap
  substitute for a symbol search.
- Read `total_count` and `truncated` before working from `matches`. `truncated:
  true` means results were cut at the server's maximum — narrow the pattern
  rather than paging, because there is no cursor.
- Each match carries `path` (relative), `size` and `modified`. Use `modified`
  to spot the files someone touched recently.
- `message` explains an empty result set when there is a reason (bad root, bad
  regex). An empty `matches` with `status: "ok"` means "no match", not "error".

## Step 3 — read one file

`secretary_analyse_file` takes `file_path`. The server-side request also accepts
`search_pattern`, `include_structure` and `include_preview`; the exposed tool
schema sends `file_path`, so pass an absolute or root-relative path that the
server can resolve.

The result carries `status`, `message` and `result`, whose keys are `file`,
`language`, `lines_total`, `structure`, `preview` and `search_results`. Use it
when you need the shape of one file — its classes, functions and imports —
rather than the whole contents. For a full read, read the file directly.

## Sequence that works

1. `secretary_codebase_report` with excludes → identify the module you care
   about.
2. `secretary_file_search` with a scoped glob and a `content_regex` → the two or
   three candidate files.
3. `secretary_analyse_file` on the main candidate → its structure and preview.
4. Then plan or delegate. If you find yourself searching a fourth time, the
   question is wrong, not the pattern.
