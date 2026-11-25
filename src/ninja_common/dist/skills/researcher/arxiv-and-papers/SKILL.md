---
name: arxiv-and-papers
description: Search arXiv with researcher_arxiv_search and extract sections or numbers from a paper with researcher_paper_fetch, using quiet queries and paced calls.
---

# arXiv search and paper extraction

`researcher_arxiv_search` talks to the public Atom API; `researcher_paper_fetch`
turns a paper or page into structured text. Both are read-only and honour the
server's rate limiter, but arXiv throttles by IP — pace yourself.

## When to use

- You need papers, not blog posts: literature checks, method provenance,
  "what does the state of the art report for X".
- You have a paper in hand and need one section, or the numbers in it.

## Searching

1. Build a quiet query: two to five meaningful terms, no site syntax, no
   `site:`, no boolean operators beyond what arXiv itself accepts. Quoting a
   phrase is allowed and useful for method names.
2. Set `categories` deliberately. The default is `["cs.RO", "cs.LG"]`, which
   silently excludes everything else — pass `["cs.CL"]`, `["cs.SE"]` or `[]`
   for a cross-category search. Categories are ANDed with the query.
3. Keep `max_results` small on the first pass (5-10 of the allowed 1-50). A
   broad query with 50 results is slower and mostly noise.
4. `sort_by` is `relevance` (default), `lastUpdatedDate` or `submittedDate`.
   Use `submittedDate` when recency is the point, `relevance` otherwise.
5. Set `full_metadata: true` only when you need `comment` or the full
   `categories` list. It costs tokens and is rarely needed to triage.
6. Read the payload: each paper has `id` (version-less), `title`, `authors`,
   `abstract`, `url`, `published`, `updated`, `primary_category`. Withdrawn
   entries are already excluded.

## Extracting from a paper

1. Call `researcher_paper_fetch` with `source` as an arXiv id (`2401.12345`), an
   `abs` / `pdf` / `ar5iv` URL, or any generic URL. It prefers the ar5iv HTML
   rendering and falls back to the abstract page.
2. Ask for only the sections you need via `sections` — case-insensitive
   headings such as `["Method", "Experiments", "Limitations"]`. An unmatched
   heading comes back absent, so check `paper.sections` before concluding the
   paper has no such section.
3. Set `extract_numbers: true` when the question is quantitative. It returns
   `paper.numbers` as `{value, context, section}` where `context` is the
   sentence containing the token. Always quote the sentence — a bare number is
   unattributable.
4. `paper.abstract` is the abstract, not a summary of the body. Do not infer
   results that appear only in the experiments from the abstract.

## Pacing

- One paper per call. Do not loop `researcher_paper_fetch` over twenty ids; ask
  for the abstract first and fetch full text only for the papers you will cite.
- Insert a pause between consecutive arXiv calls. If a call returns
  `error.kind == "rate_limited"`, wait `error.retry_after_s` (or tens of
  seconds) before the next one, and do not retry the same id more than twice.
- `error.kind == "parse"` on an ar5iv URL usually means no HTML rendering
  exists; retry the `abs` URL instead of the same source.

## Reporting

Cite the canonical `url` from the search result, and give the `id` so the reader
can resolve the version. State publication or update date when recency matters.
Separate what the abstract claims from what the numbers show.
