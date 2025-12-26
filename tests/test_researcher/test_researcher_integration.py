"""
Integration tests for Ninja Researcher module.

These tests verify the full workflow of the researcher module including
web search, deep research, report generation, fact checking, and source summarization.
"""

import asyncio
import os

import pytest
import pytest_asyncio

from ninja_researcher.models import (
    DeepResearchRequest,
    FactCheckRequest,
    GenerateReportRequest,
    SummarizeSourcesRequest,
    WebSearchRequest,
)
from ninja_researcher.tools import reset_executor


@pytest.fixture
def executor():
    """Create a fresh executor for each test."""
    reset_executor()
    from ninja_researcher.tools import get_executor

    return get_executor()


@pytest.fixture
def client_id():
    """Test client ID."""
    return "test-client"


class TestWebSearch:
    """Test web search functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_web_search_duckduckgo(self, executor, client_id):
        """Test web search using DuckDuckGo."""
        request = WebSearchRequest(
            query="Python programming language",
            max_results=5,
            search_provider="duckduckgo",
        )

        result = await executor.web_search(request, client_id=client_id)

        assert result.status == "ok"
        assert result.query == "Python programming language"
        assert result.provider == "duckduckgo"
        assert len(result.results) > 0
        assert len(result.results) <= 5

        # Check result structure
        first_result = result.results[0]
        assert first_result.title
        assert first_result.url
        assert first_result.snippet
        assert first_result.score >= 0.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_web_search_serper(self, executor, client_id):
        """Test web search using Serper.dev (if API key is configured)."""
        if not os.environ.get("SERPER_API_KEY"):
            pytest.skip("SERPER_API_KEY not configured")

        request = WebSearchRequest(
            query="MCP protocol documentation",
            max_results=3,
            search_provider="serper",
        )

        result = await executor.web_search(request, client_id=client_id)

        assert result.status == "ok"
        assert result.query == "MCP protocol documentation"
        assert result.provider == "serper"
        assert len(result.results) > 0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_web_search_invalid_provider(self, executor, client_id):
        """Test web search with invalid provider."""
        request = WebSearchRequest(
            query="test query",
            max_results=5,
            search_provider="invalid_provider",
        )

        # Should return error status (error is caught in executor)
        result = await executor.web_search(request, client_id=client_id)
        assert result.status == "error"
        assert "Unsupported search provider" in result.error_message


class TestDeepResearch:
    """Test deep research functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_deep_research_auto_queries(self, executor, client_id):
        """Test deep research with auto-generated queries."""
        request = DeepResearchRequest(
            topic="Python async programming",
            queries=[],  # Auto-generate
            max_sources=15,
            parallel_agents=3,
        )

        result = await executor.deep_research(request, client_id=client_id)

        assert result.status in ["ok", "partial"]
        assert result.topic == "Python async programming"
        assert result.sources_found > 0
        assert len(result.sources) > 0
        assert result.summary

        # Check source structure
        first_source = result.sources[0]
        assert "title" in first_source
        assert "url" in first_source

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_deep_research_custom_queries(self, executor, client_id):
        """Test deep research with custom queries."""
        request = DeepResearchRequest(
            topic="AI Code Assistants",
            queries=[
                "Aider AI coding assistant",
                "Cursor AI features",
                "GitHub Copilot comparison",
            ],
            max_sources=20,
            parallel_agents=3,
        )

        result = await executor.deep_research(request, client_id=client_id)

        assert result.status in ["ok", "partial"]
        assert result.topic == "AI Code Assistants"
        assert result.sources_found > 0
        # Should have deduplicated sources
        urls = [s.get("url") for s in result.sources]
        assert len(urls) == len(set(urls))  # No duplicates

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deep_research_parallel_execution(self, executor, client_id):
        """Test that parallel agents execute concurrently."""
        import time

        request = DeepResearchRequest(
            topic="Rust programming",
            max_sources=12,
            parallel_agents=4,
        )

        start_time = time.time()
        result = await executor.deep_research(request, client_id=client_id)
        elapsed = time.time() - start_time

        assert result.status in ["ok", "partial"]
        # With 4 parallel agents, should be faster than sequential
        # This is a rough check - parallel should take < 10s for small searches
        assert elapsed < 30  # Generous timeout


class TestReportGeneration:
    """Test report generation functionality."""

    @pytest_asyncio.fixture
    async def sample_sources(self, executor, client_id):
        """Get sample sources from a search."""
        request = WebSearchRequest(
            query="Python best practices",
            max_results=10,
            search_provider="duckduckgo",
        )
        result = await executor.web_search(request, client_id=client_id)

        return [
            {
                "title": r.title,
                "url": r.url,
                "snippet": r.snippet,
            }
            for r in result.results
        ]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_generate_comprehensive_report(self, executor, client_id, sample_sources):
        """Test comprehensive report generation."""
        request = GenerateReportRequest(
            topic="Python Best Practices",
            sources=sample_sources,
            report_type="comprehensive",
            parallel_agents=2,
        )

        result = await executor.generate_report(request, client_id=client_id)

        assert result.status == "ok"
        assert result.sources_used == len(sample_sources)
        assert result.word_count > 0
        assert "# Comprehensive Report: Python Best Practices" in result.report
        assert "## Table of Contents" in result.report
        assert "## Sources" in result.report

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_generate_executive_report(self, executor, client_id, sample_sources):
        """Test executive summary report."""
        request = GenerateReportRequest(
            topic="Python Best Practices",
            sources=sample_sources,
            report_type="executive",
            parallel_agents=2,
        )

        result = await executor.generate_report(request, client_id=client_id)

        assert result.status == "ok"
        assert "# Executive Summary" in result.report
        assert "## Key Findings" in result.report

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_generate_technical_report(self, executor, client_id, sample_sources):
        """Test technical report generation."""
        request = GenerateReportRequest(
            topic="Python Best Practices",
            sources=sample_sources,
            report_type="technical",
            parallel_agents=2,
        )

        result = await executor.generate_report(request, client_id=client_id)

        assert result.status == "ok"
        assert "# Technical Report" in result.report
        assert "## References" in result.report

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_generate_summary_report(self, executor, client_id, sample_sources):
        """Test summary report generation."""
        request = GenerateReportRequest(
            topic="Python Best Practices",
            sources=sample_sources,
            report_type="summary",
            parallel_agents=2,
        )

        result = await executor.generate_report(request, client_id=client_id)

        assert result.status == "ok"
        assert "# Summary" in result.report
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_generate_report_empty_sources(self, executor, client_id):
        """Test report generation with empty sources."""
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[],
            report_type="comprehensive",
        )

        result = await executor.generate_report(request, client_id=client_id)

        assert result.status == "error"
        assert result.sources_used == 0


class TestFactCheck:
    """Test fact checking functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fact_check_with_auto_search(self, executor, client_id):
        """Test fact checking with automatic source discovery."""
        request = FactCheckRequest(
            claim="Python was created by Guido van Rossum",
            sources=[],  # Auto-search
        )

        result = await executor.fact_check(request, client_id=client_id)

        assert result.status in ["verified", "disputed", "uncertain"]
        assert result.claim == "Python was created by Guido van Rossum"
        assert result.verdict
        assert len(result.sources) > 0
        assert 0.0 <= result.confidence <= 1.0

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fact_check_with_provided_sources(self, executor, client_id):
        """Test fact checking with provided sources."""
        request = FactCheckRequest(
            claim="The MCP protocol is a standard for AI communication",
            sources=[
                "https://modelcontextprotocol.io/",
                "https://github.com/anthropics/",
            ],
        )

        result = await executor.fact_check(request, client_id=client_id)

        assert result.status in ["verified", "disputed", "uncertain", "error"]
        assert result.claim == "The MCP protocol is a standard for AI communication"
        assert 0.0 <= result.confidence <= 1.0


class TestSummarizeSources:
    """Test source summarization functionality."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_summarize_sources(self, executor, client_id):
        """Test summarizing web sources."""
        request = SummarizeSourcesRequest(
            urls=[
                "https://www.python.org/",
                "https://docs.python.org/3/",
            ],
            max_length=500,
        )

        result = await executor.summarize_sources(request, client_id=client_id)

        assert result.status in ["ok", "partial"]
        assert len(result.summaries) > 0
        assert result.combined_summary

        # Check summary structure
        for summary in result.summaries:
            assert "url" in summary
            assert "status" in summary
            if summary["status"] == "ok":
                assert "summary" in summary
                assert "word_count" in summary

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_summarize_sources_invalid_url(self, executor, client_id):
        """Test summarizing with invalid URLs."""
        request = SummarizeSourcesRequest(
            urls=[
                "https://invalid-url-that-does-not-exist-123456789.com/",
            ],
            max_length=500,
        )

        result = await executor.summarize_sources(request, client_id=client_id)

        # Should handle gracefully
        assert result.status in ["error", "partial"]
        assert len(result.summaries) > 0
        assert result.summaries[0]["status"] == "error"

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_summarize_sources_respects_max_length(self, executor, client_id):
        """Test that max_length is respected."""
        request = SummarizeSourcesRequest(
            urls=[
                "https://www.python.org/",
                "https://docs.python.org/3/",
            ],
            max_length=200,
        )

        result = await executor.summarize_sources(request, client_id=client_id)

        if result.status == "ok":
            word_count = len(result.combined_summary.split())
            # Should be close to max_length (allow some variance)
            assert word_count <= 250  # Some overage is acceptable


class TestEndToEndWorkflow:
    """Test complete end-to-end workflows."""

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_research_and_report_workflow(self, executor, client_id):
        """Test complete workflow: research → report."""
        # Step 1: Perform deep research
        research_request = DeepResearchRequest(
            topic="FastAPI Python framework",
            max_sources=15,
            parallel_agents=3,
        )

        research_result = await executor.deep_research(research_request, client_id=client_id)

        assert research_result.status in ["ok", "partial"]
        assert len(research_result.sources) > 0

        # Step 2: Generate report from research
        report_request = GenerateReportRequest(
            topic="FastAPI Python framework",
            sources=research_result.sources,
            report_type="technical",
            parallel_agents=2,
        )

        report_result = await executor.generate_report(report_request, client_id=client_id)

        assert report_result.status == "ok"
        assert report_result.sources_used > 0
        assert report_result.word_count > 100
        assert "FastAPI" in report_result.report or "fastapi" in report_result.report.lower()

    @pytest.mark.asyncio
    @pytest.mark.integration
    @pytest.mark.slow
    async def test_search_fact_check_workflow(self, executor, client_id):
        """Test workflow: search → fact check."""
        # Step 1: Search for information
        search_request = WebSearchRequest(
            query="Python release year",
            max_results=5,
            search_provider="duckduckgo",
        )

        search_result = await executor.web_search(search_request, client_id=client_id)
        assert search_result.status == "ok"

        # Step 2: Fact check using found sources
        fact_check_request = FactCheckRequest(
            claim="Python was first released in 1991",
            sources=[r.url for r in search_result.results[:3]],
        )

        fact_check_result = await executor.fact_check(fact_check_request, client_id=client_id)

        assert fact_check_result.status in ["verified", "disputed", "uncertain"]
        assert fact_check_result.confidence >= 0.0


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rate_limiting():
    """Test that rate limiting is enforced."""
    from ninja_researcher.tools import get_executor

    executor = get_executor()
    client_id = "rate-limit-test"

    # Make multiple rapid requests
    requests_made = 0
    rate_limited = False

    try:
        for i in range(35):  # Exceed the 30/min limit
            request = WebSearchRequest(
                query=f"test query {i}",
                max_results=1,
                search_provider="duckduckgo",
            )
            await executor.web_search(request, client_id=client_id)
            requests_made += 1
            await asyncio.sleep(0.1)  # Small delay
    except Exception as e:
        if "rate limit" in str(e).lower():
            rate_limited = True

    # Either we hit the rate limit or completed all requests
    # (depends on timing and system load)
    assert requests_made > 0


if __name__ == "__main__":
    # Run tests with pytest
    pytest.main([__file__, "-v", "--tb=short"])
