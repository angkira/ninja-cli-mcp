---
name: citation-fact-check
description: Verify a claim with researcher_fact_check and report the verified, disputed or uncertain verdict honestly, without overclaiming from snippets.
---

# Citation and fact check

`researcher_fact_check` takes one claim and returns a verdict from an LLM pass
over sources: `verified`, `disputed` or `uncertain` — plus `error` when nothing
could be checked. The verdict is only as good as the sources it saw.

## When to use

- Before repeating a number, date, quote, benchmark or capability claim.
- Before asserting what a library "does not support".
- When two sources in your research disagree and you must pick a side.

Do not use it to answer an open question — that is `researcher_quick_research`.
Do not use it to settle a preference; "X is better than Y" is not a checkable
fact.

## Procedure

1. Write the claim as a single, falsifiable sentence. Split compound claims:
   "A is faster than B and uses less memory" is two checks. Include the
   qualifier that makes it true or false ("as of version 3.2", "on CPU").
2. Pass `sources` when you already trust specific pages — a list of URLs. Leave
   `sources` empty only when you want an automatic search, and accept that the
   verdict then depends on whatever the provider returned.
3. Read `status` and `verdict` together:
   - `verified` — the sources support the claim. Quote the supporting sentence,
     not just the verdict.
   - `disputed` — the sources contradict the claim. Report the contradiction and
     what the sources say instead.
   - `uncertain` — nothing decisive. Say "not established by the sources I
     checked", not "false".
   - `error` — no verdict was reached. Report the `error.kind`; do not convert a
     failed check into "uncertain" as if it were a finding.
4. Report `confidence` (0.0-1.0) as the tool's confidence, not yours. A
   high-confidence `uncertain` is still uncertain.
5. List the `sources` you actually consulted in the answer, so the reader can
   audit the check.

## What counts as a source

- A page the tool fetched or was given: its own words, not a search-result
  snippet.
- Primary material — the project's docs, the spec, the changelog, the paper.
  A forum post restating a doc is weaker evidence than the doc.
- Anything dated. A claim about current behaviour needs a source from the
  current version; a 2023 blog post cannot verify a 2026 capability.

## Avoiding overclaiming from snippets

- A snippet is a retrieval hint, not evidence. If the verdict rests on snippets
  only, say the check was snippet-level and downgrade your wording to "appears
  to" / "the search results suggest".
- Absence of evidence is not evidence. "I found no source stating X" supports
  `uncertain`, never `disputed`.
- Do not stack verdicts into a stronger claim. Three `uncertain` results do not
  add up to `verified`.
- Never cite a URL the tool did not return, and never paraphrase a source into a
  quotation.
- If the source is paywalled, login-gated or returns `error.kind == "parse"`,
  the claim stays unchecked — say so explicitly.
