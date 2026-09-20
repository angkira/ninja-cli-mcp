# 2026-09-19 — ninja-researcher post-mortem intake + API improvement spec

Source: user-supplied usage post-mortem (visual-student research session) after an
analysis agent re-probed the live server. No code changed yet.

## Empirical verdicts (from probes + usage log)

- **H-rate CONFIRMED**: 2 simultaneous deep_research calls → 1 error + 1 ok (exact log
  pattern). Mechanism: N concurrent tool calls × `parallel_agents` internal searches
  overflow an upstream quota; ~1 survivor per burst.
- **H-topic REJECTED as error cause; CONFIRMED as quality degrader**: long topic alone →
  ok but 2/15 junk sources w/ synthesized snippets; short topic alone → 5/10 incl.
  correct paper.
- Artifact quality: `title` always "Search result N"; `snippet` = same synthesized answer
  copied to every source; `score` = fake ladder (1.0, 0.95, …); canonical arxiv.org rarely
  surfaces (mirrors instead).

## Code-level root causes (verified by explorer, file:line)

1. **bs4 missing in live env**: `beautifulsoup4`/`markdownify` only in `[researcher]`
   extra (`pyproject.toml:45-49`), NOT base deps. The live daemon runs from
   `~/.local/share/uv/tools/ninja-mcp/` — a bare editable install WITHOUT extras →
   `No module named 'bs4'` at `tools.py:487`.
2. **Error text leaks into result fields**: ImportError → outer except (`tools.py:582`)
   → `combined_summary=f"Summarization failed: {e}"` (`tools.py:587`). Same pattern in
   deep_research (`tools.py:189-195`, `sources_found=0`), fact_check (`tools.py:404-412`,
   `456-464`). No typed error structure anywhere.
3. **Providers swallow exceptions → return []** (`search_providers.py:94-96, 169-174,
   276-281`) — this is why bursts look like "topic too complex" instead of rate-limit
   errors. Server-side `@rate_balanced` exists (10/60s, 3 retries) but can't help once
   the provider returns [] silently; `client_id` hardcoded `"default"` (`server.py:286`).
4. **Fake artifacts**: Perplexity `title=f"Search result {idx+1}"`, snippet=answer[:200]
   copied per-row, score `1.0-(idx*0.05)` (`search_providers.py:251-256`); DDG same
   formula (`:87`); Serper position/100 (`:161-162`).
5. **No arXiv code** anywhere (only `docs/RESEARCHER_SPEC.md:385` mentions it as planned).
6. **Stale "coming soon"**: `server.py:215-232` instructions; `docs/RESEARCHER.md`
   (multiple); `docs/RESEARCHER_SPEC.md:21-22, 66-69`.

## Improvement spec (prioritized)

### P0 — session-killers
- **P0-1 Typed errors + concurrency guidance**: error payload →
  `{error_kind: rate_limited|upstream|parse|env, message, retry_after_s}`. Requires
  providers to STOP swallowing exceptions; classify at tools.py error paths; keep
  `client_id` per-connection if cheap.
- **P0-2 bs4 fix + docs**: promote `beautifulsoup4` (+`markdownify` if used) to base
  deps; reinstall live uv tool env; per-URL failures → error field, not
  `combined_summary`; strip all "(coming soon)" strings (server.py + docs).
  Note: summarize_sources IS implemented (`tools.py:470+`) — this is dependency
  packaging + error hygiene, not a rewrite.
- **P0-3 `researcher_arxiv_search(query, categories=["cs.RO","cs.LG"], max_results=10,
  sort_by, full_metadata)`** → structured papers (id/title/authors/abstract/url) via
  export.arxiv.org (Atom XML; stdlib xml.etree, no new dep). Replaces hand-rolled
  subagent path that produced all page-confirmed numbers.

### P1 — signal quality
- P1-1 `researcher_paper_fetch(source, sections[], extract_numbers)`.
- P1-2 `researcher_deep_research_batch(requests[], mode="serial", inter_call_delay_s=15,
  on_error="retry_backoff")` — server-side queue punishing today's natural client pattern.
- P1-3 Domain filters: `include_domains/exclude_domains/prefer_domains`.
- P1-4 Real titles + per-source page-extract snippets (≥200 chars) + source_type; drop
  fake score ladder.

### P2 — polish
- P2-1 Cross-call dedup/cache (`cache_key`, `seen_urls[]`).
- P2-2 `researcher_extract_claims(url_or_id, claims[])` → per-claim verdict+quote+location.
- P2-3 fact_check source weighting (papers > blogs; per-source findings, not raw vote).
- P2-4 Doc/schema reconciliation at handshake.

## Operating rules until fixed (any agent using ninja-researcher)

1. ONE deep_research call at a time, ≥15 s spacing; never batch in a parallel block.
2. Topics <80 chars; long topics degrade quality, not errors.
3. URLs are identifiers; snippets are untrusted synthesized text.
4. fact_check usable but weight sources manually; summarize_sources broken until bs4
   ships in the live env.
5. Page-confirmed numbers → primary source (arXiv abs/ar5iv/export API) via webfetch;
   deep_research is discovery-only today.

## Estimated impact
P0s alone would have saved the analyzed session ~1.5–2.5 h and ~10 wasted calls.

## Decisions pending
- Implementation scope (P0 vs P0+P1) — asked user 2026-09-19.
- Live-env mutation approval: uv tool env reinstall + researcher daemon restart required
  for bs4 fix to take effect (restart, not reload).

## RESOLVED: user approved P0+P1 + env mutation (2026-09-19)

Implementation delegated to ninja-coder (8-step sequential plan, worktree-isolated,
dialogue mode). Tracked job `28e9cb80-c5d0-40ad-a75d-19cce24d0b21`, worktree
`ninja__sequential-plan-1789808108-557700`, branch `ninja/sequential-plan-1789808108-557700`.

## INCIDENT 2026-09-19 ~08:39–08:57 UTC: duplicate plan execution (diagnosed + resolved)

**What happened:** First `coder_execute_plan_sequential` call returned MCP `-32001
Request timed out` to the client, but the daemon HAD received it and started executing
(08:39:14 UTC, worktree `...46b3ea`). No job was registered (registry has no entry).
Resubmission via `coder_submit_sequential` (08:55:08) created a SECOND identical run
(`...557700`) — both running concurrently (`current_concurrent_tasks: 2`).

**Resolution:** Killed the unregistered orphan (PID 143212, SIGTERM to process group;
confirmed dead, exit -15; tracked run unaffected). Orphan had completed ~4 steps' worth
of edits (11 files incl. new arxiv.py + enrichment.py) before dying — partial work
quarantined on branch `ninja/sequential-plan-1789807154-46b3ea` (+ its worktree);
prune after the tracked run merges.

**Systemic bugs exposed (new backlog, coder/common MCP layer):**
1. **Registry-after-response**: job registry entry only written when/after the MCP
   response round-trip completes; execution continues after client disconnect →
   orphaned, invisible, un-cancellable runs. Fix: register BEFORE spawning execution.
2. **No submit idempotency**: client retry after timeout duplicates work. Fix:
   client-supplied request key + RequestDeduplicator pattern (as in 2026-07-19 hotfix)
   at the MCP tool level.
3. **Signal-kill misparse**: SIGTERM-killed opencode (exit -15) reported as
   "Authentication failed. Check OPENROUTER_API_KEY" — negative exit codes must map to
   cancelled/killed, not auth. Same failure class as researcher post-mortem item 1
   (zero-diagnostics errors → operator misdiagnosis).
4. **Zombie job across restart**: `e3a438da` stuck 'working' since 2026-09-18T16:22
   (registry not reconciled on daemon restart). Fix: persist registry or sweep stale
   'working' → 'lost' at startup.
5. Registry `last_updated_at` never refreshed during execution (no progress events).

**Unrelated noise:** system load 41 caused by another session's ML self-tests
(`visual_student_dagger --self-test`, 565%/517% CPU, cortex repo) — not ninja daemons.
3 opencode inactivity timeouts ("Process inactive for 90s") this morning on OTHER
agents' cortex tasks; one retried successfully. Noted, not acted on.
