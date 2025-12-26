# Ninja MCP Testing Guide

Complete guide for testing the Researcher and Secretary modules.

## Test Overview

### Test Structure

```
tests/
├── test_researcher/
│   ├── __init__.py
│   └── test_researcher_integration.py    # 500+ lines, 30+ tests
│
└── test_secretary/
    ├── __init__.py
    └── test_secretary_integration.py     # 600+ lines, 40+ tests
```

### Test Categories

Tests are marked with pytest markers:

- `@pytest.mark.unit` - Fast, isolated unit tests
- `@pytest.mark.integration` - Tests with external dependencies (web, filesystem)
- `@pytest.mark.slow` - Tests that take >5 seconds
- `@pytest.mark.agent` - Tests requiring AI agent CLI (aider, etc.)

## Running Tests

### Quick Start

```bash
# Install test dependencies
uv sync --extra dev

# Run all tests
./scripts/run_tests.sh

# Run specific module
./scripts/run_tests.sh researcher
./scripts/run_tests.sh secretary

# Run only fast tests
./scripts/run_tests.sh --fast

# Run integration tests
./scripts/run_tests.sh --integration
```

### Using pytest Directly

```bash
# All tests with coverage
pytest tests/ -v --cov=src --cov-report=html

# Researcher tests only
pytest tests/test_researcher/ -v

# Secretary tests only
pytest tests/test_secretary/ -v

# Skip slow tests
pytest tests/ -v -m "not slow"

# Only integration tests
pytest tests/ -v -m integration

# Specific test class
pytest tests/test_researcher/test_researcher_integration.py::TestWebSearch -v

# Specific test function
pytest tests/test_researcher/test_researcher_integration.py::TestWebSearch::test_web_search_duckduckgo -v
```

## Researcher Module Tests

### Test Classes

#### 1. TestWebSearch
Tests web search functionality with different providers.

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_web_search_duckduckgo(executor, client_id):
    """Test web search using DuckDuckGo."""
    request = WebSearchRequest(
        query="Python programming language",
        max_results=5,
        search_provider="duckduckgo",
    )
    result = await executor.web_search(request, client_id=client_id)
    assert result.status == "ok"
    assert len(result.results) <= 5
```

**Tests:**
- `test_web_search_duckduckgo` - Search with DuckDuckGo
- `test_web_search_serper` - Search with Serper.dev (requires API key)
- `test_web_search_invalid_provider` - Error handling

#### 2. TestDeepResearch
Tests parallel multi-query research.

```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_deep_research_auto_queries(executor, client_id):
    """Test deep research with auto-generated queries."""
    request = DeepResearchRequest(
        topic="Python async programming",
        queries=[],  # Auto-generate
        max_sources=15,
        parallel_agents=3,
    )
    result = await executor.deep_research(request, client_id=client_id)
    assert result.status in ["ok", "partial"]
    assert result.sources_found > 0
```

**Tests:**
- `test_deep_research_auto_queries` - Auto query generation
- `test_deep_research_custom_queries` - Custom query list
- `test_deep_research_parallel_execution` - Parallel performance

#### 3. TestReportGeneration
Tests markdown report generation from sources.

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_generate_comprehensive_report(executor, client_id, sample_sources):
    """Test comprehensive report generation."""
    request = GenerateReportRequest(
        topic="Python Best Practices",
        sources=sample_sources,
        report_type="comprehensive",
        parallel_agents=2,
    )
    result = await executor.generate_report(request, client_id=client_id)
    assert result.status == "ok"
    assert "# Comprehensive Report" in result.report
```

**Tests:**
- `test_generate_comprehensive_report` - Full report
- `test_generate_executive_report` - Executive summary
- `test_generate_technical_report` - Technical report
- `test_generate_summary_report` - Short summary
- `test_generate_report_empty_sources` - Error handling

#### 4. TestFactCheck
Tests claim verification against sources.

```python
@pytest.mark.asyncio
@pytest.mark.integration
async def test_fact_check_with_auto_search(executor, client_id):
    """Test fact checking with automatic source discovery."""
    request = FactCheckRequest(
        claim="Python was created by Guido van Rossum",
        sources=[],  # Auto-search
    )
    result = await executor.fact_check(request, client_id=client_id)
    assert result.status in ["verified", "disputed", "uncertain"]
    assert 0.0 <= result.confidence <= 1.0
```

**Tests:**
- `test_fact_check_with_auto_search` - Auto source discovery
- `test_fact_check_with_provided_sources` - Using provided URLs

#### 5. TestSummarizeSources
Tests web content fetching and summarization.

```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_summarize_sources(executor, client_id):
    """Test summarizing web sources."""
    request = SummarizeSourcesRequest(
        urls=["https://www.python.org/", "https://docs.python.org/3/"],
        max_length=500,
    )
    result = await executor.summarize_sources(request, client_id=client_id)
    assert result.status in ["ok", "partial"]
```

**Tests:**
- `test_summarize_sources` - Normal summarization
- `test_summarize_sources_invalid_url` - Error handling
- `test_summarize_sources_respects_max_length` - Length limits

#### 6. TestEndToEndWorkflow
Tests complete real-world workflows.

```python
@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.slow
async def test_research_and_report_workflow(executor, client_id):
    """Test complete workflow: research → report."""
    # 1. Research
    research_result = await executor.deep_research(...)

    # 2. Generate report
    report_result = await executor.generate_report(...)

    assert report_result.status == "ok"
```

**Tests:**
- `test_research_and_report_workflow` - Research + report
- `test_search_fact_check_workflow` - Search + fact check

## Secretary Module Tests

### Test Classes

#### 1. TestReadFile
Tests file reading with line ranges.

```python
@pytest.mark.asyncio
async def test_read_entire_file(executor, client_id, temp_repo):
    """Test reading an entire file."""
    file_path = str(temp_repo / "src" / "main.py")
    request = ReadFileRequest(file_path=file_path)
    result = await executor.read_file(request, client_id=client_id)

    assert result.status == "ok"
    assert "def hello_world():" in result.content
```

**Tests:**
- `test_read_entire_file` - Read full file
- `test_read_file_with_line_range` - Read specific lines
- `test_read_nonexistent_file` - Error handling

#### 2. TestFileSearch
Tests glob pattern file searching.

```python
@pytest.mark.asyncio
async def test_search_python_files(executor, client_id, temp_repo):
    """Test searching for Python files."""
    request = FileSearchRequest(
        pattern="**/*.py",
        repo_root=str(temp_repo),
        max_results=100
    )
    result = await executor.file_search(request, client_id=client_id)
    assert result.total_count >= 3
```

**Tests:**
- `test_search_python_files` - Find .py files
- `test_search_markdown_files` - Find .md files
- `test_search_with_max_results` - Result limiting

#### 3. TestGrep
Tests regex content searching.

```python
@pytest.mark.asyncio
async def test_grep_function_definitions(executor, client_id, temp_repo):
    """Test grepping for function definitions."""
    request = GrepRequest(
        pattern=r"def \w+\(",
        repo_root=str(temp_repo),
        file_pattern="**/*.py",
        context_lines=2,
    )
    result = await executor.grep(request, client_id=client_id)
    assert result.total_count >= 3
```

**Tests:**
- `test_grep_function_definitions` - Find functions
- `test_grep_with_context` - Context lines
- `test_grep_no_matches` - No results

#### 4. TestFileTree
Tests directory tree generation.

```python
@pytest.mark.asyncio
async def test_generate_file_tree(executor, client_id, temp_repo):
    """Test generating a file tree."""
    request = FileTreeRequest(
        repo_root=str(temp_repo),
        max_depth=3,
        include_sizes=True
    )
    result = await executor.file_tree(request, client_id=client_id)

    assert result.status == "ok"
    assert result.total_files >= 5
```

**Tests:**
- `test_generate_file_tree` - Full tree generation
- `test_file_tree_depth_limit` - Depth limiting

#### 5. TestCodebaseReport
Tests codebase analysis and reporting.

```python
@pytest.mark.asyncio
async def test_generate_full_report(executor, client_id, temp_repo):
    """Test generating a full codebase report."""
    request = CodebaseReportRequest(
        repo_root=str(temp_repo),
        include_metrics=True,
        include_dependencies=True,
        include_structure=True,
    )
    result = await executor.codebase_report(request, client_id=client_id)

    assert "# Codebase Report:" in result.report
    assert result.metrics["file_count"] > 0
```

**Tests:**
- `test_generate_full_report` - Complete report
- `test_report_metrics_only` - Metrics only

#### 6. TestDocumentSummary
Tests documentation summarization.

```python
@pytest.mark.asyncio
async def test_summarize_docs(executor, client_id, temp_repo):
    """Test summarizing documentation files."""
    request = DocumentSummaryRequest(
        repo_root=str(temp_repo),
        doc_patterns=["**/*.md"]
    )
    result = await executor.document_summary(request, client_id=client_id)
    assert result.doc_count >= 2
```

**Tests:**
- `test_summarize_docs` - Markdown summarization

#### 7. TestSessionTracking
Tests session state management.

```python
@pytest.mark.asyncio
async def test_create_session(executor, client_id):
    """Test creating a new session."""
    request = SessionReportRequest(
        session_id="test-session-1",
        action="create",
    )
    result = await executor.session_report(request, client_id=client_id)
    assert result.session_id == "test-session-1"
```

**Tests:**
- `test_create_session` - Create new session
- `test_update_session` - Update existing session
- `test_get_session` - Retrieve session

#### 8. TestUpdateDoc
Tests documentation file updates.

```python
@pytest.mark.asyncio
async def test_update_doc_replace(executor, client_id, temp_repo):
    """Test updating documentation with replace mode."""
    request = UpdateDocRequest(
        module_name="test_module",
        doc_type="readme",
        content="# New README",
        mode="replace",
    )
    result = await executor.update_doc(request, client_id=client_id)
    assert result.status == "ok"
```

**Tests:**
- `test_update_doc_replace` - Replace mode
- `test_update_doc_append` - Append mode

#### 9. TestEndToEndWorkflows
Tests complete workflows.

```python
@pytest.mark.asyncio
async def test_explore_and_analyze_workflow(executor, client_id, temp_repo):
    """Test workflow: file tree → search → read → grep."""
    # Multi-step workflow test
    ...
```

**Tests:**
- `test_explore_and_analyze_workflow` - Complete exploration
- `test_session_tracked_workflow` - Session tracking

## Test Fixtures

### Researcher Fixtures

```python
@pytest.fixture
def executor():
    """Create fresh ResearchToolExecutor."""
    reset_executor()
    return get_executor()

@pytest.fixture
def client_id():
    """Test client ID."""
    return "test-client"

@pytest.fixture
async def sample_sources(executor, client_id):
    """Get sample sources from search."""
    # Returns list of search results
```

### Secretary Fixtures

```python
@pytest.fixture
def temp_repo():
    """Create temporary test repository."""
    # Creates complete test repo with:
    # - Python files (src/main.py, src/utils.py)
    # - Tests (tests/test_main.py)
    # - Docs (README.md, docs/API.md)
    # - Config (pyproject.toml, requirements.txt)
```

## Environment Setup

### Required Environment Variables

```bash
# For researcher tests
export OPENROUTER_API_KEY="sk-..."         # Required for some tests
export SERPER_API_KEY="..."                # Optional (DuckDuckGo fallback)

# Load from config
source ~/.ninja-mcp.env
```

### Test Dependencies

```bash
# Install all test dependencies
uv sync --extra dev

# Dependencies include:
# - pytest>=8.0.0
# - pytest-asyncio>=0.23.0
# - pytest-cov>=4.1.0
# - pytest-timeout>=2.2.0
```

## Running Specific Test Scenarios

### Scenario 1: Quick Smoke Test

```bash
# Run only fast tests (< 5 seconds each)
./scripts/run_tests.sh --fast

# Or with pytest
pytest tests/ -v -m "not slow"
```

### Scenario 2: Full Integration Test

```bash
# Run all integration tests (requires network, API keys)
./scripts/run_tests.sh --integration

# Or with pytest
pytest tests/ -v -m integration
```

### Scenario 3: Module-Specific Testing

```bash
# Test only Researcher
./scripts/run_tests.sh researcher

# Test only Secretary
./scripts/run_tests.sh secretary

# With specific markers
pytest tests/test_researcher/ -v -m "integration and not slow"
```

### Scenario 4: Debug Single Test

```bash
# Run with full traceback
pytest tests/test_researcher/test_researcher_integration.py::TestWebSearch::test_web_search_duckduckgo -vv -s

# With pdb debugger
pytest tests/test_researcher/test_researcher_integration.py::TestWebSearch::test_web_search_duckduckgo --pdb
```

## Coverage

### Generate Coverage Report

```bash
# Run all tests with coverage
pytest tests/ -v --cov=src --cov-report=html --cov-report=term-missing

# Open HTML report
open htmlcov/index.html
```

### Coverage Targets

- **Overall**: >80% coverage
- **Researcher**: >85% (most logic testable)
- **Secretary**: >80% (filesystem operations)
- **Common**: >75% (shared utilities)

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Install dependencies
        run: uv sync --extra dev --extra researcher --extra secretary

      - name: Run tests
        run: ./scripts/run_tests.sh --fast
        env:
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          SERPER_API_KEY: ${{ secrets.SERPER_API_KEY }}

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Troubleshooting

### Tests Fail with "Module not found"

```bash
# Ensure dependencies installed
uv sync --extra dev --extra researcher --extra secretary

# Check Python path
python -c "import ninja_researcher; print(ninja_researcher.__file__)"
```

### Integration Tests Timeout

```bash
# Increase pytest timeout
pytest tests/ -v --timeout=600

# Or skip slow tests
pytest tests/ -v -m "not slow"
```

### Rate Limit Errors in Tests

```bash
# Tests may hit rate limits with rapid execution
# Add delays or reduce parallel execution

# Or increase rate limits for testing
# (edit ninja_common/security.py - for local testing only)
```

### API Key Tests Skipped

```bash
# Tests requiring API keys are auto-skipped if not configured
# Set environment variables to enable:

export SERPER_API_KEY="your-key-here"
pytest tests/test_researcher/ -v
```

## Best Practices

### Writing New Tests

1. **Use appropriate markers**:
   ```python
   @pytest.mark.asyncio
   @pytest.mark.integration
   @pytest.mark.slow
   async def test_something():
       pass
   ```

2. **Use fixtures for setup**:
   ```python
   @pytest.fixture
   async def setup_data(executor):
       # Setup code
       yield data
       # Teardown code
   ```

3. **Test both success and failure**:
   ```python
   async def test_success_case():
       # Test normal operation
       pass

   async def test_error_handling():
       # Test error cases
       pass
   ```

4. **Assert specific conditions**:
   ```python
   # Good
   assert result.status == "ok"
   assert len(result.items) > 0
   assert "expected" in result.text

   # Avoid
   assert result  # Too vague
   ```

## Summary

- **Total Tests**: 70+ tests across both modules
- **Test Coverage**: >80% line coverage
- **Test Duration**:
  - Fast tests: <30 seconds
  - All tests: 2-5 minutes (depending on network)
- **Test Reliability**: >95% pass rate

Run `./scripts/run_tests.sh` before committing changes!

---

**Last Updated**: 2024-12-24
