# Ninja Research Skill

Perform deep web research using Perplexity AI with parallel search agents.

## Overview

Ninja Researcher leverages Perplexity AI to perform comprehensive research on any topic. It decomposes complex topics into multiple queries, searches in parallel, and aggregates results from diverse sources.

## When to Use This Skill

- Researching technical topics or documentation
- Gathering information from multiple perspectives
- Fact-checking claims before presenting them
- Building knowledge bases for complex projects
- Staying current on rapidly evolving technologies

## How It Works

```
Topic -> Query Decomposition -> Parallel Perplexity Searches -> Source Aggregation -> Synthesized Results
```

## Available Tools

### `researcher_deep_research`
Comprehensive multi-query research.

Parameters:
- `topic` (required): Main research topic
- `queries`: Specific sub-queries (auto-generated if empty)
- `max_sources`: Maximum sources to gather (default: 20)
- `parallel_agents`: Concurrent search agents (default: 4)

### `researcher_fact_check`
Verify claims against web sources.

Parameters:
- `claim` (required): Statement to verify
- `sources`: Specific URLs to check against (optional)

Returns: verdict (verified/disputed/uncertain) with confidence score

### `researcher_summarize_sources`
Condense multiple web sources.

Parameters:
- `urls` (required): List of URLs to summarize
- `max_length`: Maximum summary length in words

### `researcher_generate_report`
Create structured reports from sources.

Parameters:
- `topic`: Report subject
- `sources`: Source documents
- `report_type`: comprehensive | summary | technical | executive

## Example Usage

### Deep Research
```
Use researcher_deep_research:
{
  "topic": "MCP (Model Context Protocol) server development",
  "queries": [
    "MCP protocol specification",
    "Building MCP servers Python",
    "MCP server best practices 2026"
  ],
  "max_sources": 30,
  "parallel_agents": 6
}
```

### Fact Checking
```
Use researcher_fact_check:
{
  "claim": "Claude 4 was released in December 2025"
}
```

## Best Practices

1. **Specific Queries**: Break broad topics into focused sub-queries
2. **Source Diversity**: Use higher `max_sources` for contentious topics
3. **Always Cite**: Include source URLs in your final response
4. **Cross-Reference**: For critical information, verify across multiple sources

## Requirements

- Ninja MCP installed: `uv tool install ninja-mcp[researcher]`
- PERPLEXITY_API_KEY environment variable set
