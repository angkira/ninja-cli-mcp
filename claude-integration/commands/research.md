---
name: research
description: Deep web research with Ninja Researcher (Perplexity AI)
---

Use ninja-researcher MCP tools to research:

**Topic**: $ARGUMENTS

## Instructions

1. **Choose research approach**:
   - `researcher_deep_research` - Comprehensive multi-query research
   - `researcher_fact_check` - Verify specific claims
   - `researcher_summarize_sources` - Summarize given URLs

2. **For deep research**, consider:
   - Breaking topic into specific sub-queries
   - Setting appropriate `max_sources` (default: 20)
   - Using `parallel_agents` for faster results (default: 4)

3. **Synthesize findings**:
   - Organize by theme/category
   - Highlight key insights
   - Note conflicting information
   - Always cite sources with URLs

## Example Queries

```json
{
  "topic": "React Server Components best practices 2026",
  "queries": [
    "React Server Components performance optimization",
    "RSC vs Client Components when to use",
    "React 19 Server Components patterns"
  ],
  "max_sources": 25
}
```

## Output Format

Present findings as:
1. **Key Findings** - Bullet points of main insights
2. **Detailed Analysis** - Organized by theme
3. **Sources** - Full URLs for citation

**Always include source URLs in your response.**
