# Ninja Researcher Module

The Researcher module provides web search and research capabilities for the Ninja MCP system.

## Overview

Ninja Researcher enables AI assistants to:
- Search the web using multiple providers (DuckDuckGo, Serper.dev)
- Perform deep research with parallel queries
- Generate comprehensive reports from sources (coming soon)
- Fact-check claims against web sources (coming soon)
- Summarize multiple web sources (coming soon)

## Features

### ✅ Available Now

- **Web Search** - Search using DuckDuckGo (free) or Serper.dev (Google Search)
- **Deep Research** - Multi-query research with parallel agents and deduplication
- **Rate Limiting** - 30 searches/minute, 10 deep research/minute
- **Security** - Input validation, resource monitoring

### 🚧 Coming Soon

- **Report Generation** - Synthesize sources into comprehensive reports
- **Fact Checking** - Verify claims against web sources
- **Source Summarization** - Summarize and extract key information
- **Citation Management** - Track and format citations

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
| `OPENROUTER_API_KEY` | Yes | - | OpenRouter API key (for report generation) |
| `SERPER_API_KEY` | No | - | Serper.dev API key (Google Search) |
| `NINJA_RESEARCHER_MODEL` | No | `anthropic/claude-sonnet-4` | Model for synthesis |
| `NINJA_RESEARCHER_MAX_SOURCES` | No | `20` | Max sources per research |
| `NINJA_RESEARCHER_PARALLEL_AGENTS` | No | `4` | Parallel search agents |

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

### researcher_deep_research

Perform comprehensive research with multiple queries.

**Parameters:**
- `topic` (string, required): Research topic
- `queries` (array, optional): Specific queries (auto-generated if empty)
- `max_sources` (integer, optional): Maximum sources (1-100, default: 20)
- `parallel_agents` (integer, optional): Parallel agents (1-8, default: 4)

**Returns:**
```json
{
  "status": "ok",
  "topic": "MCP protocol implementation",
  "sources_found": 25,
  "sources": [
    {
      "title": "MCP Protocol Specification",
      "url": "https://example.com/mcp-spec",
      "snippet": "The Model Context Protocol...",
      "score": 0.98
    }
  ],
  "summary": "Found 25 unique sources across 4 queries"
}
```

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

### researcher_generate_report *(Coming Soon)*

Generate a comprehensive report from research sources.

**Parameters:**
- `topic` (string, required): Report topic
- `sources` (array, required): Source documents
- `report_type` (string, optional): Report type ("comprehensive", "summary", "technical", "executive")
- `parallel_agents` (integer, optional): Parallel synthesis agents (1-8, default: 4)

### researcher_fact_check *(Coming Soon)*

Verify a claim against web sources.

**Parameters:**
- `claim` (string, required): Claim to verify
- `sources` (array, optional): URLs to check against (auto-search if empty)

### researcher_summarize_sources *(Coming Soon)*

Summarize multiple web sources.

**Parameters:**
- `urls` (array, required): URLs to summarize
- `max_length` (integer, optional): Max summary length in words (100-5000, default: 500)

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

# 3. Generate report (coming soon)
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
ninja-daemon start researcher

# Check status
ninja-daemon status researcher

# View logs
tail -f ~/.cache/ninja-mcp/logs/researcher.log

# Stop daemon
ninja-daemon stop researcher
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
- [ ] Report generation with LLM synthesis
- [ ] Fact checking
- [ ] Source summarization
- [ ] Citation management
- [ ] Additional providers (Brave Search, Bing)
- [ ] Caching and incremental research
- [ ] Research session management

## Contributing

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development guidelines.

## License

MIT License - see [LICENSE](../LICENSE) for details.
