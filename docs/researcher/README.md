# Ninja Researcher Module

🔍 Web search, deep research, and report generation capabilities via MCP.

## Overview

The Researcher module provides powerful web search and research capabilities through the Model Context Protocol (MCP). It enables AI assistants to search the web, perform comprehensive research on topics, generate reports, fact-check claims, and summarize sources.

## Features

### ✅ Search-backed answers
- **DuckDuckGo** (free, no API key required)
- **Serper.dev** (Google Search API, requires `SERPER_API_KEY`)
- Optional **Perplexity** answers when configured
- `researcher_quick_research` returns a cited answer plus its sources

### ✅ Deep Research
- Multi-query research with parallel agents
- Automatic query generation from topics
- Source aggregation and deduplication
- Configurable parallelism (1-8 agents)

### ✅ Report Generation
- Four report types: comprehensive, summary, technical, executive
- Parallel source analysis
- Markdown formatted output
- Automatic citations and references

### ✅ Fact Checking
- Verify claims against web sources
- Automatic source discovery
- Confidence scoring (0.0-1.0)
- Verdict: verified, disputed, uncertain, error

### ✅ Source Summarization
- Fetch and parse web content
- Extract main text (HTML cleaning)
- Per-source and combined summaries
- Respects max_length parameter

## Installation

```bash
# Install with researcher dependencies
pip install -e ".[researcher]"

# Or install all modules
pip install -e ".[all]"
```

### API Keys (Optional)

For better search results using Google Search via Serper.dev:

```bash
export SERPER_API_KEY="your-api-key-here"
```

Get a free API key at [serper.dev](https://serper.dev) (2,500 searches/month free tier).

## Usage

### Start the Server

```bash
# Run as standalone server
python -m ninja_researcher.server

# Or use the entry point
ninja-researcher
```

### MCP Tools

#### 1. Quick Research (search + cited answer)

```python
{
  "tool": "researcher_quick_research",
  "arguments": {
    "query": "Python async best practices",
    "max_results": 10,
    "search_provider": "duckduckgo"  # or "serper", "perplexity"; defaults to NINJA_SEARCH_PROVIDER
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "query": "Python async best practices",
  "provider": "duckduckgo",
  "model": "…",
  "answer": "Use asyncio.gather for independent coroutines …",
  "sources": [
    { "title": "…", "url": "…", "snippet": "…" }
  ]
}
```

There is no separate raw "web search" tool: `researcher_quick_research` is the
single-question entry point, and `researcher_deep_research` is the multi-query
one.

#### 2. Deep Research

```python
{
  "tool": "researcher_deep_research",
  "arguments": {
    "topic": "MCP protocol implementation",
    "max_sources": 20,
    "parallel_agents": 4,
    "queries": []  # Auto-generated if empty
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "topic": "MCP protocol implementation",
  "sources_found": 18,
  "sources": [...],
  "summary": "Found 18 unique sources across 4 queries",
  "report": "# MCP protocol implementation\n\n…",
  "provider": "duckduckgo"
}
```

#### 3. Generate Report

```python
{
  "tool": "researcher_generate_report",
  "arguments": {
    "topic": "AI Code Assistants",
    "sources": [...],  # From deep_research
    "report_type": "comprehensive",  # or "summary", "technical", "executive"
    "parallel_agents": 4
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "report": "# Comprehensive Report: AI Code Assistants\n\n...",
  "sources_used": 20,
  "word_count": 1523
}
```

#### 4. Fact Check

```python
{
  "tool": "researcher_fact_check",
  "arguments": {
    "claim": "Python was created in 1991",
    "sources": []  # Auto-search if empty
  }
}
```

**Returns:**
```json
{
  "status": "verified",
  "claim": "Python was created in 1991",
  "verdict": "The claim appears to be supported by 4/5 sources found",
  "sources": [...],
  "confidence": 0.8
}
```

#### 5. Summarize Sources

```python
{
  "tool": "researcher_summarize_sources",
  "arguments": {
    "urls": [
      "https://example.com/article1",
      "https://example.com/article2"
    ],
    "max_length": 500
  }
}
```

**Returns:**
```json
{
  "status": "ok",
  "summaries": [
    {
      "url": "...",
      "status": "ok",
      "summary": "...",
      "word_count": 1234
    }
  ],
  "combined_summary": "..."
}
```

## Rates and pacing

See the bundled `deep-research-playbook` skill for provider rate-limit handling
(typed rate-limit errors surface as a structured `error` with a retry hint).
`researcher_deep_research_batch` paces its up-to-5 topics serially
(`inter_call_delay_s`).

## Architecture

```
ninja_researcher/
├── __init__.py          # Module exports
├── models.py            # Pydantic models for requests/responses
├── server.py            # MCP server implementation
├── tools.py             # Tool execution logic
└── search_providers.py  # Search provider implementations
```

### Search Providers

- **DuckDuckGoProvider**: Uses `duckduckgo-search` library, always available
- **SerperProvider**: Uses Serper.dev API for Google Search results
- **SearchProviderFactory**: Factory pattern for provider management

### Parallel Processing

The module uses `asyncio` for parallel processing:
- Deep research runs multiple queries in parallel (configurable)
- Report generation analyzes sources in parallel chunks
- Source summarization fetches URLs concurrently (max 5 at a time)

## Dependencies

```toml
researcher = [
    "duckduckgo-search>=6.0.0",
    "beautifulsoup4>=4.12.0",
    "markdownify>=0.13.0",
]
```

## Examples

### Example 1: Research and Report

```python
# 1. Perform deep research
research_result = await researcher_deep_research({
    "topic": "Rust async programming",
    "max_sources": 30,
    "parallel_agents": 6
})

# 2. Generate comprehensive report
report_result = await researcher_generate_report({
    "topic": "Rust async programming",
    "sources": research_result["sources"],
    "report_type": "technical",
    "parallel_agents": 4
})

# report_result["report"] contains markdown report
```

### Example 2: Fact Check with Auto-Search

```python
fact_check_result = await researcher_fact_check({
    "claim": "Claude Code is built on the MCP protocol"
    # sources auto-discovered via search
})

print(fact_check_result["verdict"])
print(f"Confidence: {fact_check_result['confidence']}")
```

## Development

### Running Tests

```bash
pytest tests/test_researcher.py -v
```

### Type Checking

```bash
mypy src/ninja_researcher --strict
```

### Linting

```bash
ruff check src/ninja_researcher
```

## Troubleshooting

### Issue: "Provider not available"

**Solution**: For Serper provider, set `SERPER_API_KEY` environment variable.

### Issue: Search returns no results

**Solutions**:
- Check internet connection
- Try different search provider
- Simplify search query
- Check rate limits

### Issue: Report generation fails

**Solutions**:
- Ensure sources list is not empty
- Check that sources have required fields (title, url, snippet)
- Reduce parallel_agents if hitting memory limits

## License

MIT License - see main project LICENSE file.
