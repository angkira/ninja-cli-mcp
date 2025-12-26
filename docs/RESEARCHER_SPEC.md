# Ninja Researcher Module - Complete Specification

## Module Overview

**Name**: ninja-researcher  
**Version**: 0.2.0  
**Purpose**: Web search and research report generation  
**Status**: Phase 1 Complete (Web Search), Phase 2 In Progress (Report Generation)

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Ninja Researcher MCP Server               │
│                                                              │
│  ┌────────────────────────────────────────────────────────┐ │
│  │                  MCP Tools Layer                       │ │
│  │  • researcher_web_search                               │ │
│  │  • researcher_deep_research                            │ │
│  │  • researcher_generate_report (planned)                │ │
│  │  • researcher_fact_check (planned)                     │ │
│  │  • researcher_summarize_sources (planned)              │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │              Research Tools Executor                   │ │
│  │  • Rate limiting (30/min search, 10/min research)      │ │
│  │  • Resource monitoring                                 │ │
│  │  • Parallel execution control                          │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│  ┌────────────────────────────────────────────────────────┐ │
│  │            Search Provider Factory                     │ │
│  │  • Provider selection                                  │ │
│  │  • Availability checking                               │ │
│  │  • Result normalization                                │ │
│  └────────────────────────────────────────────────────────┘ │
│                           │                                  │
│  ┌──────────────────┐  ┌──────────────────┐                │ │
│  │  DuckDuckGo      │  │  Serper.dev      │                │ │
│  │  Provider        │  │  Provider        │                │ │
│  │  (Free)          │  │  (Google Search) │                │ │
│  └──────────────────┘  └──────────────────┘                │ │
└─────────────────────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
┌─────────────────┐    ┌──────────────────┐
│  DuckDuckGo API │    │  Serper.dev API  │
│  (duckduckgo-   │    │  (Google Search) │
│   search lib)   │    │                  │
└─────────────────┘    └──────────────────┘
```

## Components

### 1. MCP Server (`server.py`)

**Responsibilities:**
- Expose MCP tools via stdio protocol
- Handle tool invocations
- Route requests to executor
- Serialize responses

**Tools Exposed:**
- `researcher_web_search` - Web search
- `researcher_deep_research` - Multi-query research
- `researcher_generate_report` - Report generation (planned)
- `researcher_fact_check` - Fact checking (planned)
- `researcher_summarize_sources` - Source summarization (planned)

**Configuration:**
- Server name: "ninja-researcher"
- Version: "0.2.0"
- Protocol: MCP stdio

### 2. Tools Executor (`tools.py`)

**Responsibilities:**
- Implement business logic for each tool
- Apply rate limiting and security
- Coordinate parallel operations
- Aggregate and deduplicate results

**Methods:**
- `web_search()` - Single web search
- `deep_research()` - Multi-query research
- `generate_report()` - Report generation (planned)
- `fact_check()` - Fact checking (planned)
- `summarize_sources()` - Summarization (planned)

**Security:**
- Rate limiting: `@rate_limited` decorator
- Resource monitoring: `@monitored` decorator
- Input validation: Query sanitization
- Client isolation: Per-client tracking

### 3. Search Providers (`search_providers.py`)

**Base Interface:**
```python
class SearchProvider(ABC):
    async def search(query: str, max_results: int) -> list[dict]
    def is_available() -> bool
    def get_name() -> str
```

**Implementations:**

#### DuckDuckGoProvider
- **Library**: `duckduckgo-search`
- **API Key**: Not required
- **Cost**: Free
- **Rate Limits**: Enforced by DuckDuckGo
- **Result Format**: Normalized to common schema

#### SerperProvider
- **API**: Serper.dev (Google Search)
- **API Key**: Required (`SERPER_API_KEY`)
- **Cost**: Free tier (2,500/month), $50/month for 5,000
- **Rate Limits**: Based on plan
- **Result Format**: Normalized to common schema

**Provider Factory:**
- Singleton pattern for provider instances
- Automatic provider selection based on availability
- Default provider: Serper if configured, else DuckDuckGo

### 4. Data Models (`models.py`)

**Request Models:**
- `WebSearchRequest` - Web search parameters
- `DeepResearchRequest` - Deep research parameters
- `GenerateReportRequest` - Report generation parameters
- `FactCheckRequest` - Fact checking parameters
- `SummarizeSourcesRequest` - Summarization parameters

**Response Models:**
- `SearchResult` - Single search result
- `WebSearchResult` - Web search response
- `ResearchResult` - Deep research response
- `ReportResult` - Report generation response
- `FactCheckResult` - Fact check response
- `SummaryResult` - Summarization response

**Common Schema:**
```python
SearchResult:
  - title: str
  - url: str
  - snippet: str
  - score: float (0.0-1.0)
```

## Data Flow

### Web Search Flow

```
User Request
    │
    ├─> Validate inputs
    │
    ├─> Check rate limit
    │
    ├─> Get search provider
    │   ├─> Check availability
    │   └─> Select provider
    │
    ├─> Execute search
    │   ├─> Call provider API
    │   └─> Normalize results
    │
    ├─> Return results
    │
    └─> Log metrics
```

### Deep Research Flow

```
User Request
    │
    ├─> Validate inputs
    │
    ├─> Check rate limit
    │
    ├─> Generate queries (if not provided)
    │   └─> Use topic to create sub-queries
    │
    ├─> Parallel search execution
    │   ├─> Create semaphore (limit concurrency)
    │   ├─> Execute searches in parallel
    │   │   ├─> Query 1 → Provider
    │   │   ├─> Query 2 → Provider
    │   │   ├─> Query 3 → Provider
    │   │   └─> Query 4 → Provider
    │   └─> Gather results
    │
    ├─> Aggregate results
    │   ├─> Deduplicate by URL
    │   ├─> Limit to max_sources
    │   └─> Sort by relevance
    │
    ├─> Create summary
    │
    └─> Return research result
```

## Configuration

### Environment Variables

```bash
# Required for report generation (LLM synthesis)
OPENROUTER_API_KEY='sk-or-...'

# Optional - Serper.dev for Google Search
SERPER_API_KEY='your-serper-key'

# Model for synthesis (report generation)
NINJA_RESEARCHER_MODEL='anthropic/claude-sonnet-4'

# Research parameters
NINJA_RESEARCHER_MAX_SOURCES=20
NINJA_RESEARCHER_PARALLEL_AGENTS=4
```

### Provider Selection Logic

```python
def get_default_provider():
    if SERPER_API_KEY is configured:
        return "serper"  # Prefer Google Search
    else:
        return "duckduckgo"  # Free fallback
```

## Rate Limiting

### Limits

- **Web Search**: 30 calls/minute per client
- **Deep Research**: 10 calls/minute per client
- **Report Generation**: 5 calls/minute per client (planned)

### Implementation

```python
@rate_limited(max_calls=30, time_window=60)
async def web_search(request, client_id):
    # Implementation
    pass
```

### Per-Client Tracking

- Each IDE/session gets unique `client_id`
- Rate limits tracked separately per client
- Persistent across server restarts

## Error Handling

### Search Failures

```python
try:
    results = await provider.search(query, max_results)
except Exception as e:
    logger.error(f"Search failed: {e}")
    return WebSearchResult(
        status="error",
        query=query,
        results=[],
        provider=provider_name,
        error_message=str(e)
    )
```

### Provider Unavailable

```python
if not provider.is_available():
    return WebSearchResult(
        status="error",
        query=query,
        results=[],
        provider=provider_name,
        error_message=f"Provider {provider_name} not available (missing API key?)"
    )
```

### Rate Limit Exceeded

```python
@rate_limited(max_calls=30, time_window=60)
async def web_search(request, client_id):
    # If rate limit exceeded, decorator raises PermissionError
    # Caught by server and returned as error response
    pass
```

## Testing Strategy

### Unit Tests

- Provider availability checks
- Factory pattern functionality
- Request/response model validation
- Rate limiter behavior

### Integration Tests

- DuckDuckGo search (no API key required)
- Serper search (requires `SERPER_API_KEY`)
- Deep research with parallel agents
- Error handling and retries

### E2E Tests

- Full research workflow
- Multi-provider fallback
- Rate limit enforcement
- Concurrent request handling

## Performance

### Benchmarks

- **Single search**: ~1-3 seconds (DuckDuckGo), ~0.5-1 second (Serper)
- **Deep research (4 queries, 4 agents)**: ~2-5 seconds
- **Memory usage**: ~50-100 MB per search
- **Concurrent searches**: Up to 8 parallel (configurable)

### Optimization

- Async/await for non-blocking I/O
- Semaphore for concurrency control
- Result deduplication to reduce redundancy
- Provider caching (singleton pattern)

## Security

### Input Validation

- Query length: Max 10,000 characters
- URL validation: Regex pattern matching
- Sanitization: Remove dangerous patterns

### API Key Protection

- Stored in `~/.ninja-mcp.env` (600 permissions)
- Never logged or exposed
- Filtered from error messages

### Resource Limits

- Max concurrent searches: 8
- Max results per search: 50
- Max sources per research: 100
- Timeout per search: 30 seconds

## Future Enhancements

### Phase 2: Report Generation

- LLM-based synthesis of sources
- Parallel sub-agent analysis
- Citation management
- Multiple report formats (comprehensive, summary, technical, executive)

### Phase 3: Advanced Features

- Fact checking with source verification
- Source summarization and extraction
- Research session management
- Incremental research (build on previous results)
- Vector search for semantic similarity
- Source quality scoring

### Phase 4: Additional Providers

- Brave Search API
- Bing Search API
- Custom search engines
- Academic search (Google Scholar, arXiv)

## Dependencies

### Required

- `duckduckgo-search>=6.0.0` - DuckDuckGo search
- `httpx>=0.27.0` - HTTP client for Serper
- `pydantic>=2.0.0` - Data validation
- `mcp>=1.1.2` - MCP protocol

### Optional

- `beautifulsoup4>=4.12.0` - HTML parsing (for future features)
- `markdownify>=0.13.0` - HTML to Markdown (for future features)

## Metrics

### Tracked Metrics

- Search count per provider
- Average search latency
- Success/failure rates
- Sources found per research
- API costs (for Serper)

### Storage

Metrics stored in `~/.cache/ninja-mcp/researcher/metrics/`:
- `searches.csv` - Search metrics
- `research.csv` - Research session metrics

## API Costs

### DuckDuckGo

- **Cost**: $0 (free)
- **Limits**: Rate limited by DuckDuckGo

### Serper.dev

- **Free Tier**: 2,500 searches/month
- **Paid Plans**: 
  - $50/month for 5,000 searches
  - $200/month for 25,000 searches
- **Cost per search**: ~$0.01 (paid plans)

### OpenRouter (for report generation)

- **Model**: `anthropic/claude-sonnet-4`
- **Input**: $3.00 per million tokens
- **Output**: $15.00 per million tokens
- **Estimated cost per report**: $0.05-$0.20 (depending on sources)

## Comparison with Other Solutions

### vs. Tavily

| Feature | Ninja Researcher | Tavily |
|---------|------------------|--------|
| Cost | Free (DuckDuckGo) or $0.01/search (Serper) | $0.005/search |
| API Key | Optional (Serper) | Required |
| Providers | DuckDuckGo, Serper | Tavily only |
| Quality | High (Google via Serper) | High (optimized for AI) |
| Rate Limits | 30/min | Based on plan |

**Recommendation**: Use Ninja Researcher with DuckDuckGo for free searches, or Serper for higher quality. Tavily is good if you want AI-optimized results and don't mind the cost.

### vs. Direct API Usage

| Feature | Ninja Researcher | Direct API |
|---------|------------------|------------|
| Setup | Simple (installer) | Manual integration |
| Multiple Providers | Yes (2+) | One at a time |
| Rate Limiting | Built-in | Manual implementation |
| Deduplication | Automatic | Manual implementation |
| MCP Integration | Native | Requires wrapper |

## Implementation Checklist

### Phase 1: Web Search ✅

- [x] DuckDuckGo provider
- [x] Serper.dev provider
- [x] Provider factory pattern
- [x] Web search tool
- [x] Deep research tool
- [x] Rate limiting
- [x] Security and validation
- [x] Unit tests
- [x] Integration tests
- [x] Documentation

### Phase 2: Report Generation 🚧

- [ ] Source fetching and parsing
- [ ] Content extraction (BeautifulSoup)
- [ ] LLM-based synthesis
- [ ] Parallel sub-agent analysis
- [ ] Report formatting (Markdown)
- [ ] Citation management
- [ ] Multiple report types
- [ ] Tests and documentation

### Phase 3: Advanced Features 📋

- [ ] Fact checking
- [ ] Source summarization
- [ ] Research sessions
- [ ] Incremental research
- [ ] Source quality scoring
- [ ] Additional providers (Brave, Bing)

## Usage Examples

### Example 1: Simple Web Search

```python
# Search with DuckDuckGo (free)
result = await client.call_tool("researcher_web_search", {
    "query": "Python async best practices",
    "max_results": 10,
    "search_provider": "duckduckgo"
})

# Result:
{
  "status": "ok",
  "query": "Python async best practices",
  "results": [
    {
      "title": "Async Python Best Practices",
      "url": "https://example.com/async",
      "snippet": "Learn the best practices...",
      "score": 0.95
    }
  ],
  "provider": "duckduckgo"
}
```

### Example 2: Deep Research

```python
# Comprehensive research on a topic
result = await client.call_tool("researcher_deep_research", {
    "topic": "MCP protocol implementation",
    "max_sources": 30,
    "parallel_agents": 4
})

# Result:
{
  "status": "ok",
  "topic": "MCP protocol implementation",
  "sources_found": 28,
  "sources": [
    {
      "title": "MCP Specification",
      "url": "https://spec.modelcontextprotocol.io",
      "snippet": "The Model Context Protocol...",
      "score": 0.98
    },
    // ... more sources
  ],
  "summary": "Found 28 unique sources across 4 queries"
}
```

### Example 3: Custom Queries

```python
# Research with specific queries
result = await client.call_tool("researcher_deep_research", {
    "topic": "AI code assistants",
    "queries": [
        "Aider vs Cursor comparison 2024",
        "GitHub Copilot alternatives",
        "AI code assistant benchmarks",
        "Best AI coding tools"
    ],
    "max_sources": 40,
    "parallel_agents": 4
})
```

## Error Scenarios

### Scenario 1: No API Key for Serper

```python
Request:
{
  "query": "test",
  "search_provider": "serper"
}

Response:
{
  "status": "error",
  "query": "test",
  "results": [],
  "provider": "serper",
  "error_message": "Provider serper is not available (missing API key?)"
}
```

### Scenario 2: Rate Limit Exceeded

```python
# After 30 searches in 60 seconds
Response:
{
  "status": "error",
  "error": "Rate limit exceeded for client default: maximum 30 calls per 60s",
  "error_type": "PermissionError"
}
```

### Scenario 3: Search Provider Failure

```python
# If DuckDuckGo or Serper API fails
Response:
{
  "status": "error",
  "query": "test",
  "results": [],
  "provider": "duckduckgo",
  "error_message": "Search failed: Connection timeout"
}
```

## Deployment

### Standalone

```bash
# Load config
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

### Docker (Future)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install -e ".[researcher]"
CMD ["ninja-researcher"]
```

## Monitoring

### Logs

- Location: `~/.cache/ninja-mcp/logs/researcher.log`
- Format: Structured logging with timestamps
- Levels: INFO, WARNING, ERROR, DEBUG
- Rotation: Manual (future: automatic rotation)

### Metrics

- Search count by provider
- Average latency
- Success/failure rates
- Rate limit hits
- API costs

### Health Checks

```bash
# Check if server is running
ninja-daemon status researcher

# Check resource usage
# (via ResourceMonitor in ninja_common)
```

## Maintenance

### Updating Search Providers

1. Update provider implementation in `search_providers.py`
2. Update tests
3. Update documentation
4. Bump version

### Adding New Provider

1. Implement `SearchProvider` interface
2. Add to `SearchProviderFactory`
3. Update tool schema (add to enum)
4. Add tests
5. Update documentation

### Deprecating Provider

1. Mark as deprecated in documentation
2. Add deprecation warning in code
3. Provide migration path
4. Remove in next major version

## License

MIT License - see [LICENSE](../../LICENSE) for details.
