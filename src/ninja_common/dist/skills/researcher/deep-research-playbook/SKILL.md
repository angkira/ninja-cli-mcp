---
name: deep-research-playbook
description: Sequence researcher_quick_research, researcher_deep_research, researcher_deep_research_batch, researcher_summarize_sources and researcher_generate_report, and handle typed rate-limit errors.
---

# Deep research playbook

The researcher server has one tool per shape of question. Picking the wrong one
wastes minutes or returns an answer too thin to cite.

## When to use which

| Need | Tool | Main arguments |
| --- | --- | --- |
| One question, one answer, with citations | `researcher_quick_research` | `query` |
| A topic that needs several angles and a written report | `researcher_deep_research` | `topic`, `queries` |
| Several unrelated topics in one call | `researcher_deep_research_batch` | `requests` |
| Summaries of URLs you already have | `researcher_summarize_sources` | `urls`, `max_length` |
| A report from sources you already have | `researcher_generate_report` | `topic`, `sources`, `report_type` |

Rule of thumb: one sentence of question → quick; comparison across subtopics →
deep; sources already in hand → never search again, summarize or generate.

## Procedure for a research task

1. Sharpen the question before searching. "State of MCP 2026-07-28 adoption"
   produces better sub-queries than "MCP".
2. For deep research, pass `queries` explicitly when you know the angles; leave
   `queries` empty only when you trust auto-generation. Keep `max_sources`
   (1-100, default 20) proportional to the report: 10-20 for a summary, 30+ for
   a technical report.
3. Constrain sources rather than post-filtering: `include_domains`,
   `exclude_domains`, `prefer_domains` are applied to hosts during gathering, and
   `enrich: true` (the default) replaces provider snippets with extracted page
   text. Turn `enrich` off only when speed matters more than fidelity.
4. Choose the report shape with `report_type`: `comprehensive`, `summary`,
   `technical`, `executive`. Set `synthesize: false` when you only want sources
   and a summary and will write the report yourself.
5. Read `status` first: `ok`, `partial` or `error`. `partial` means some
   providers or pages failed — the report is still usable but should be labelled
   as incomplete. Check `sources_found` / `sources_used` before quoting counts.
6. Cite from `sources`, never from memory, and never invent a URL that is not in
   the payload.

## Summarize vs generate a report

- `researcher_summarize_sources` fetches each URL and returns per-source
  summaries plus one `combined_summary`. It does not argue a thesis and does not
  take a topic. Use it to compress a source list you already collected, or to
  check that your sources are on topic before writing.
- `researcher_generate_report` synthesizes the `sources` you pass into a cited
  markdown report with a `topic`, `report_type` and `parallel_agents`. Each
  source object needs `url` and `title`; the body may be under `snippet`,
  `content` or `description`.
- `use_llm` is a tri-state: omit it to use an LLM when a synthesis engine is
  configured and fall back to the template otherwise, `true` to require the LLM,
  `false` to force the deterministic template. The response's `model` field is
  empty when the template produced the report — say so rather than implying a
  model wrote it.

## Batching

`researcher_deep_research_batch` runs 1-5 requests strictly serially (`mode` is
only `serial`). Keep `inter_call_delay_s` at its default 15: the delay is what
keeps providers from throttling you. `on_error` decides what happens on a typed
error — `continue` records the failure, `abort` stops the batch, `retry_backoff`
(default) retries only `rate_limited` failures with exponential backoff. A batch
reports `total` and `completed`, so `partial` with `completed < total` tells you
how many topics are missing.

## Rate limits and error envelopes

Every researcher tool may return `status: "error"`, or a partial payload with an
`error` object such as `{"kind": "rate_limited", "message": "...",
"retry_after_s": 30.0}`.

`kind` is one of `rate_limited`, `upstream`, `parse`, `env`.

- `rate_limited` — wait `retry_after_s` when present, otherwise back off tens of
  seconds. Do not retry in a tight loop; reduce `parallel_agents` on the retry.
- `upstream` — the provider failed. Try a different `search_provider`
  (`duckduckgo`, `serper`, `perplexity`) rather than repeating the same call.
- `parse` — the page or feed could not be understood. Try another URL for the
  same fact.
- `env` — configuration is missing (for example an absent `SERPER_API_KEY`).
  Report it; retrying will not help.

Limits are per client and per window, search and deep research counted
separately, so a burst of parallel work is the usual cause.
