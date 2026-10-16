# Ninja Researcher Module

The Researcher module provides web search and research capabilities for the Ninja MCP system.

## Overview

Ninja Researcher enables AI assistants to:
- Search the web using multiple providers (DuckDuckGo, Serper.dev)
- Perform deep research with parallel queries
- Generate comprehensive reports from sources
- Fact-check claims against web sources
- Summarize multiple web sources
- Search arXiv for structured papers
- Fetch paper/page content and extract numbers with context
- Run deep-research batches serially to respect upstream quotas

## Features

### ✅ Available Now

- **Web Search** - Search using DuckDuckGo (free) or Serper.dev (Google Search)
- **Quick Research** - Single-pass cited answer (Perplexity-native when selected)
- **Deep Research** - Multi-query research with parallel agents, deduplication, real
  page-extracted snippets, domain filters and a written report
- **Report Synthesis** - LLM-written reports (Perplexity or OpenRouter), with a
  deterministic template fallback
- **Report Generation** - Synthesize sources into comprehensive reports
- **Fact Checking** - Verify claims against web sources
- **Source Summarization** - Summarize and extract key information
- **arXiv Search** - Structured paper search via the public Atom API
- **Paper Fetch** - Extract sections and numbers with context from papers/pages
- **Batch Research** - Serial deep-research batches with retry/backoff
- **Typed Errors** - Machine-readable error payloads (`rate_limited`, `upstream`,
  `parse`, `env`)
- **Rate Limiting** - 30 searches/minute, 10 deep research/minute
- **Security** - Input validation, resource monitoring

## Installation

```bash
# Install researcher module
uv sync --extra researcher

# Or install all modules
uv sync --all-extras
```

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `PERPLEXITY_API_KEY` | No | - | Perplexity key (native cited answers + synthesis) |
| `OPENROUTER_API_KEY` | No | - | OpenRouter key (synthesis fallback) |
| `SERPER_API_KEY` | No | - | Serper.dev API key (Google Search) |
| `NINJA_SEARCH_PROVIDER` | No | auto | Search provider: `perplexity`, `serper`, `duckduckgo` |
| `NINJA_RESEARCHER_MODEL` | No | `sonar-pro` | Synthesis model (`sonar*` for Perplexity, `vendor/model` for OpenRouter) |
| `NINJA_RESEARCHER_LLM` | No | `auto` | Synthesis engine: `auto`, `perplexity`, `openrouter`, `off` |
| `NINJA_RESEARCHER_MAX_SOURCES` | No | `20` | Max sources per research |
| `NINJA_RESEARCHER_PARALLEL_AGENTS` | No | `4` | Parallel search agents |

**Synthesis:** when `NINJA_RESEARCHER_LLM=auto` (default), reports and answers are
written by Perplexity when a Perplexity key is present, otherwise by OpenRouter using
`NINJA_RESEARCHER_MODEL`. Set `NINJA_RESEARCHER_LLM=off` to use the deterministic
template only. When neither engine is available the tools still return sources and a
template report.

### Configuration File

Create or update `~/.ninja-mcp.env`:

```bash
# OpenRouter API key (for report generation)
export OPENROUTER_API_KEY='your-key'

# Serper.dev API key (optional - DuckDuckGo is free fallback)
export SERPER_API_KEY='your-key'

# Researcher model
export NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'

# Max sources per research
export NINJA_RESEARCHER_MAX_SOURCES=20

# Parallel research agents
export NINJA_RESEARCHER_PARALLEL_AGENTS=4
```

Load configuration:
```bash
source ~/.ninja-mcp.env
```

## Search Providers

### DuckDuckGo (Default)

- **Cost**: Free
- **API Key**: Not required
- **Rate Limits**: Enforced by DuckDuckGo
- **Quality**: Good for general searches
- **Privacy**: Privacy-focused

**Usage:**
```json
{
  "query": "Python async best practices",
  "max_results": 10,
  "search_provider": "duckduckgo"
}
```

### Serper.dev (Google Search)

- **Cost**: Free tier (2,500 searches/month), then $50/month for 5,000 searches
- **API Key**: Required - get from https://serper.dev
- **Rate Limits**: Based on your plan
- **Quality**: High (Google Search results)
- **Features**: Organic results, knowledge graph, related searches

**Setup:**
```bash
# Get API key from https://serper.dev
export SERPER_API_KEY='your-key'
```

**Usage:**
```json
{
  "query": "Python async best practices",
  "max_results": 10,
  "search_provider": "serper"
}
```

## MCP Tools

### researcher_web_search

Search the web for information.

**Parameters:**
- `query` (string, required): Search query
- `max_results` (integer, optional): Maximum results (1-50, default: 10)
- `search_provider` (string, optional): Provider to use ("duckduckgo" or "serper", default: "duckduckgo")

**Returns:**
```json
{
  "status": "ok",
  "query": "Python async best practices",
  "results": [
    {
      "title": "Async Python Best Practices",
      "url": "https://example.com/async-python",
      "snippet": "Learn the best practices for async Python...",
      "score": 0.95
    }
  ],
  "provider": "duckduckgo"
}
```

**Example:**
```python
result = await client.call_tool("researcher_web_search", {
    "query": "MCP protocol specification",
    "max_results": 10,
    "search_provider": "serper"
})
```

### researcher_quick_research

Fast single-pass research. With Perplexity selected it returns Perplexity's cited
answer directly; with other providers it gathers results and writes a short cited
answer when a synthesis engine is configured.

**Parameters:**
- `query` (string, required): Research question
- `search_provider` (string, optional): `duckduckgo`, `serper` or `perplexity` (defaults to `NINJA_SEARCH_PROVIDER`, then auto)
- `max_results` (integer, optional): Maximum sources/citations (1-50, default: 10)
- `enrich` (boolean, optional): Fetch pages for real extracted snippets (default: true)
- `include_domains` / `exclude_domains` / `prefer_domains` (array, optional): Domain filters

**Returns:** `status`, `query`, `provider`, `model`, `answer`, `sources`, `error`.

### researcher_deep_research

Perform comprehensive research with multiple queries and produce a written report.

**Parameters:**
- `topic` (string, required): Research topic
- `queries` (array, optional): Specific queries (auto-generated if empty)
- `search_provider` (string, optional): Provider override
- `max_sources` (integer, optional): Maximum sources (1-100, default: 20)
- `parallel_agents` (integer, optional): Parallel agents (1-8, default: 4)
- `synthesize` (boolean, optional): Produce a written report when an engine is available (default: true)
- `report_type` (string, optional): Report style when synthesizing

**Returns:** `status`, `topic`, `sources_found`, `sources`, `summary`, `report`, `provider`.

**Example:**
```python
result = await client.call_tool("researcher_deep_research", {
    "topic": "AI code assistants comparison",
    "max_sources": 30,
    "parallel_agents": 4
})
```

**With custom queries:**
```python
result = await client.call_tool("researcher_deep_research", {
    "topic": "AI code assistants",
    "queries": [
        "Aider vs Cursor comparison",
        "GitHub Copilot alternatives",
        "AI code assistant benchmarks"
    ],
    "max_sources": 40
})
```

### researcher_generate_report

Generate a comprehensive report from research sources.

**Parameters:**
- `topic` (string, required): Report topic
- `sources` (array, required): Source documents
- `report_type` (string, optional): Report type ("comprehensive", "summary", "technical", "executive")
- `parallel_agents` (integer, optional): Parallel synthesis agents (1-8, default: 4)
- `use_llm` (boolean, optional): Force LLM synthesis on/off (omit for auto: LLM when an engine is configured, else the template)

### researcher_fact_check

Verify a claim against web sources.

**Parameters:**
- `claim` (string, required): Claim to verify
- `sources` (array, optional): URLs to check against (auto-search if empty)

### researcher_summarize_sources

Summarize multiple web sources.

**Parameters:**
- `urls` (array, required): URLs to summarize
- `max_length` (integer, optional): Max summary length in words (100-5000, default: 500)

### researcher_arxiv_search

Structured arXiv search via the public Atom API.

**Parameters:**
- `query` (string, required): Search query
- `categories` (array, optional): arXiv categories ANDed with the query (default `["cs.RO", "cs.LG"]`)
- `max_results` (integer, optional): Maximum papers (1-50, default: 10)
- `sort_by` (string, optional): `relevance` | `lastUpdatedDate` | `submittedDate`
- `full_metadata` (boolean, optional): Include optional fields such as `comment` and `categories`

Returns papers with `id`, `title`, `authors`, `abstract`, `url` and timestamps, excluding
withdrawn entries.

### researcher_paper_fetch

Fetch and parse an arXiv paper or web page.

**Parameters:**
- `source` (string, required): arXiv URL/id (abs, pdf, ar5iv) or a generic URL
- `sections` (array, optional): Section headings to extract (case-insensitive)
- `extract_numbers` (boolean, optional): Extract numeric tokens with sentence context

Prefers the ar5iv HTML rendering for arXiv papers, falling back to the abstract page.

### researcher_deep_research_batch

Run up to 5 deep-research requests strictly serially.

**Parameters:**
- `requests` (array, required): 1-5 deep-research requests
- `mode` (string, optional): Only `serial` is supported
- `inter_call_delay_s` (number, optional): Delay between calls (0-120, default: 15)
- `on_error` (string, optional): `continue` | `abort` | `retry_backoff` (default)

### Deep research parameters

- `enrich` (boolean, optional): Fetch pages to replace provider snippets with real
  extracted text (default: true)
- `include_domains` (array, optional): Keep only hosts matching these
- `exclude_domains` (array, optional): Drop hosts matching these (subdomains too)
- `prefer_domains` (array, optional): Order matching hosts first, preserving relative order

## Usage Examples

### Basic Web Search

```python
# Search with DuckDuckGo (free)
result = await client.call_tool("researcher_web_search", {
    "query": "Python asyncio tutorial",
    "max_results": 10
})

# Search with Serper.dev (Google Search)
result = await client.call_tool("researcher_web_search", {
    "query": "Python asyncio tutorial",
    "max_results": 10,
    "search_provider": "serper"
})
```

### Deep Research Workflow

```python
# 1. Perform deep research
research = await client.call_tool("researcher_deep_research", {
    "topic": "MCP protocol best practices",
    "max_sources": 30,
    "parallel_agents": 4
})

# 2. Review sources
sources = research["sources"]
print(f"Found {len(sources)} sources")

# 3. Generate report
# report = await client.call_tool("researcher_generate_report", {
#     "topic": "MCP protocol best practices",
#     "sources": sources,
#     "report_type": "technical"
# })
```

### Custom Query Research

```python
# Define specific queries for targeted research
result = await client.call_tool("researcher_deep_research", {
    "topic": "AI code quality",
    "queries": [
        "AI code review tools",
        "automated code quality metrics",
        "AI-powered refactoring",
        "code quality best practices AI"
    ],
    "max_sources": 40,
    "parallel_agents": 4
})
```

## Running the Server

### Direct Execution

```bash
# Load configuration
source ~/.ninja-mcp.env

# Run server
ninja-researcher
```

### Daemon Mode

```bash
# Start daemon
ninja-mcp daemon start researcher

# Check status
ninja-mcp daemon status researcher

# View logs
tail -f ~/.cache/ninja-mcp/logs/researcher.log

# Stop daemon
ninja-mcp daemon stop researcher
```

## IDE Integration

### Claude Code

The installer automatically configures Claude Code. Manual configuration:

```json
{
  "mcpServers": {
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    }
  }
}
```

### VS Code

Create or update `~/.config/Code/User/mcp.json`:

```json
{
  "mcpServers": {
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    }
  }
}
```

### Zed

Update `~/.config/zed/settings.json`:

```json
{
  "context_servers": {
    "ninja-researcher": {
      "command": "uv",
      "args": ["run", "python", "-m", "ninja_researcher.server"]
    }
  }
}
```

## Rate Limits

To prevent abuse and respect API limits:

- **Web Search**: 30 calls/minute per client
- **Deep Research**: 10 calls/minute per client
- **Per-client tracking**: Each IDE/session tracked separately
- **Persistent state**: Rate limits persist across restarts

## Security

### API Key Storage

- API keys stored in `~/.ninja-mcp.env` with 600 permissions (user-only)
- Never logged or transmitted except to search APIs
- Redacted in all log files

### Input Validation

- Query length limits (max 10,000 characters)
- URL validation for source requests
- Sanitization of all user inputs

### Resource Monitoring

- Concurrent request limits
- Memory and CPU monitoring
- Automatic throttling under high load

## Troubleshooting

### "Provider not available" error

```bash
# Check if Serper API key is configured
echo $SERPER_API_KEY

# If empty, either:
# 1. Configure Serper key
export SERPER_API_KEY='your-key'

# 2. Or use DuckDuckGo (free)
# Change search_provider to "duckduckgo" in your request
```

### Rate limit exceeded

```bash
# Wait 60 seconds for rate limit window to reset
# Or use a different client_id (if applicable)
```

### No results returned

```bash
# Check logs
tail -f ~/.cache/ninja-mcp/logs/researcher.log

# Try different search provider
# If using Serper, try DuckDuckGo
# If using DuckDuckGo, try Serper (if configured)
```

### DuckDuckGo rate limiting

DuckDuckGo may rate limit aggressive usage. If you encounter this:

1. Add delays between searches
2. Use Serper.dev instead (requires API key)
3. Reduce `parallel_agents` in deep research

## Development

### Adding a New Search Provider

1. Create provider class in `src/ninja_researcher/search_providers.py`:

```python
class NewProvider(SearchProvider):
    async def search(self, query: str, max_results: int) -> list[dict]:
        # Implementation
        pass
    
    def is_available(self) -> bool:
        # Check API key
        pass
    
    def get_name(self) -> str:
        return "new_provider"
```

2. Register in `SearchProviderFactory`:

```python
if provider_name == "new_provider":
    cls._providers[provider_name] = NewProvider()
```

3. Update tool schema to include new provider in enum

### Testing

```bash
# Unit tests
pytest tests/researcher/test_search_providers.py

# Integration tests (requires API keys)
RUN_INTEGRATION_TESTS=1 pytest tests/researcher/test_integration.py

# Test specific provider
pytest tests/researcher/test_search_providers.py::test_duckduckgo_search
```

## API Reference

See [API.md](API.md) for complete API reference.

## Roadmap

- [x] Web search (DuckDuckGo, Serper.dev)
- [x] Deep research with parallel agents
- [x] Quick single-pass research
- [x] Report generation with LLM synthesis (Perplexity / OpenRouter)
- [ ] Citation management
- [ ] Additional providers (Brave Search, Bing)
- [ ] Caching and incremental research
- [ ] Research session management

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.

## License

MIT License - see [LICENSE](../LICENSE) for details.
