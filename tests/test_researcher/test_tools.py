"""
Integration tests for researcher tools.

Tests for deep_research, generate_report, fact_check, and summarize_sources.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ninja_researcher.models import (
    DeepResearchRequest,
    FactCheckRequest,
    GenerateReportRequest,
    SummarizeSourcesRequest,
)
from ninja_researcher.tools import ResearchToolExecutor


class TestDeepResearch:
    """Tests for deep_research tool."""

    @pytest.mark.asyncio
    async def test_deep_research_success(self):
        """Test successful deep research."""
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(
            topic="Python async best practices",
            max_sources=10,
            parallel_agents=2,
        )

        with patch.object(
            executor.provider_factory, "get_default_provider", return_value="duckduckgo"
        ), patch.object(
            executor.provider_factory, "get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search = AsyncMock(
                return_value=[
                    {
                        "title": "Test Result 1",
                        "url": "https://example.com/1",
                        "snippet": "Test snippet 1",
                        "score": 1.0,
                    },
                    {
                        "title": "Test Result 2",
                        "url": "https://example.com/2",
                        "snippet": "Test snippet 2",
                        "score": 0.95,
                    },
                ]
            )
            mock_get_provider.return_value = mock_provider

            result = await executor.deep_research(request, client_id="test")

            assert result.status == "ok"
            assert result.topic == "Python async best practices"
            assert result.sources_found > 0
            assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_deep_research_with_custom_queries(self):
        """Test deep research with custom queries."""
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(
            topic="Python async",
            queries=["asyncio tutorial", "async/await guide"],
            max_sources=5,
        )

        with patch.object(
            executor.provider_factory, "get_default_provider", return_value="duckduckgo"
        ), patch.object(
            executor.provider_factory, "get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search = AsyncMock(
                return_value=[
                    {
                        "title": "Result",
                        "url": "https://example.com",
                        "snippet": "Snippet",
                        "score": 1.0,
                    }
                ]
            )
            mock_get_provider.return_value = mock_provider

            result = await executor.deep_research(request, client_id="test")

            assert result.status == "ok"
            # Should have called search for each custom query
            assert mock_provider.search.call_count == 2

    @pytest.mark.asyncio
    async def test_deep_research_deduplication(self):
        """Test that deep research deduplicates URLs."""
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(
            topic="Test topic",
            max_sources=10,
        )

        with patch.object(
            executor.provider_factory, "get_default_provider", return_value="duckduckgo"
        ), patch.object(
            executor.provider_factory, "get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            # Return duplicate URLs
            mock_provider.search = AsyncMock(
                return_value=[
                    {
                        "title": "Result 1",
                        "url": "https://example.com/same",
                        "snippet": "Snippet 1",
                        "score": 1.0,
                    },
                    {
                        "title": "Result 2",
                        "url": "https://example.com/same",
                        "snippet": "Snippet 2",
                        "score": 0.9,
                    },
                ]
            )
            mock_get_provider.return_value = mock_provider

            result = await executor.deep_research(request, client_id="test")

            # Should deduplicate - only one source despite multiple searches
            unique_urls = {s["url"] for s in result.sources}
            assert len(unique_urls) == len(result.sources)


class TestGenerateReport:
    """Tests for generate_report tool."""

    @pytest.mark.asyncio
    async def test_generate_comprehensive_report(self):
        """Test generating comprehensive report."""
        executor = ResearchToolExecutor()
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[
                {
                    "title": "Source 1",
                    "url": "https://example.com/1",
                    "snippet": "Content from source 1",
                },
                {
                    "title": "Source 2",
                    "url": "https://example.com/2",
                    "snippet": "Content from source 2",
                },
            ],
            report_type="comprehensive",
        )

        result = await executor.generate_report(request, client_id="test")

        assert result.status == "ok"
        assert "Comprehensive Report: Test Topic" in result.report
        assert result.sources_used == 2
        assert result.word_count > 0

    @pytest.mark.asyncio
    async def test_generate_executive_report(self):
        """Test generating executive summary report."""
        executor = ResearchToolExecutor()
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[
                {"title": "Source", "url": "https://example.com", "snippet": "Content"}
            ],
            report_type="executive",
        )

        result = await executor.generate_report(request, client_id="test")

        assert result.status == "ok"
        assert "Executive Summary" in result.report
        assert result.sources_used == 1

    @pytest.mark.asyncio
    async def test_generate_technical_report(self):
        """Test generating technical report."""
        executor = ResearchToolExecutor()
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[
                {"title": "Source", "url": "https://example.com", "snippet": "Content"}
            ],
            report_type="technical",
        )

        result = await executor.generate_report(request, client_id="test")

        assert result.status == "ok"
        assert "Technical Report" in result.report
        assert "References" in result.report

    @pytest.mark.asyncio
    async def test_generate_summary_report(self):
        """Test generating summary report."""
        executor = ResearchToolExecutor()
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[
                {"title": "Source", "url": "https://example.com", "snippet": "Content"}
            ],
            report_type="summary",
        )

        result = await executor.generate_report(request, client_id="test")

        assert result.status == "ok"
        assert "Summary: Test Topic" in result.report

    @pytest.mark.asyncio
    async def test_generate_report_empty_sources(self):
        """Test report generation with empty sources."""
        executor = ResearchToolExecutor()
        request = GenerateReportRequest(
            topic="Test Topic",
            sources=[],
            report_type="comprehensive",
        )

        result = await executor.generate_report(request, client_id="test")

        assert result.status == "error"
        assert result.sources_used == 0


class TestFactCheck:
    """Tests for fact_check tool."""

    @pytest.mark.asyncio
    async def test_fact_check_with_sources(self):
        """Test fact checking with provided sources."""
        executor = ResearchToolExecutor()
        request = FactCheckRequest(
            claim="Python is a programming language",
            sources=["https://python.org", "https://docs.python.org"],
        )

        result = await executor.fact_check(request, client_id="test")

        assert result.claim == "Python is a programming language"
        assert result.status in ["verified", "disputed", "uncertain"]
        assert 0.0 <= result.confidence <= 1.0
        assert len(result.sources) > 0

    @pytest.mark.asyncio
    async def test_fact_check_auto_search(self):
        """Test fact checking with automatic source search."""
        executor = ResearchToolExecutor()
        request = FactCheckRequest(
            claim="Test claim",
            sources=[],  # Empty - should trigger auto-search
        )

        with patch.object(
            executor.provider_factory, "get_default_provider", return_value="duckduckgo"
        ), patch.object(
            executor.provider_factory, "get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search = AsyncMock(
                return_value=[
                    {
                        "title": "Result",
                        "url": "https://example.com/test",
                        "snippet": "Test claim information",
                        "score": 1.0,
                    }
                ]
            )
            mock_get_provider.return_value = mock_provider

            result = await executor.fact_check(request, client_id="test")

            assert result.claim == "Test claim"
            assert len(result.sources) > 0
            # Should have searched for sources
            mock_provider.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_fact_check_search_failure(self):
        """Test fact checking when search fails."""
        executor = ResearchToolExecutor()
        request = FactCheckRequest(
            claim="Test claim",
            sources=[],
        )

        with patch.object(
            executor.provider_factory, "get_default_provider", return_value="duckduckgo"
        ), patch.object(
            executor.provider_factory, "get_provider"
        ) as mock_get_provider:
            mock_provider = MagicMock()
            mock_provider.search = AsyncMock(side_effect=Exception("Search failed"))
            mock_get_provider.return_value = mock_provider

            result = await executor.fact_check(request, client_id="test")

            assert result.status == "error"
            assert "Search failed" in result.verdict


class TestSummarizeSources:
    """Tests for summarize_sources tool."""

    @pytest.mark.asyncio
    async def test_summarize_sources_success(self):
        """Test successful source summarization."""
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://example.com/1", "https://example.com/2"],
            max_length=500,
        )

        with patch("httpx.AsyncClient") as mock_client:
            # Mock HTTP responses
            mock_response = MagicMock()
            mock_response.text = "<html><body><p>This is test content from the webpage.</p></body></html>"
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await executor.summarize_sources(request, client_id="test")

            assert result.status in ["ok", "partial"]
            assert len(result.summaries) == 2
            assert result.combined_summary != ""

    @pytest.mark.asyncio
    async def test_summarize_sources_handles_failures(self):
        """Test summarization when some URLs fail."""
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://example.com/1", "https://example.com/2"],
            max_length=500,
        )

        with patch("httpx.AsyncClient") as mock_client:

            async def mock_get(url, **kwargs):
                if "1" in url:
                    mock_response = MagicMock()
                    mock_response.text = "<html><body><p>Success content</p></body></html>"
                    mock_response.raise_for_status = MagicMock()
                    return mock_response
                else:
                    raise Exception("Failed to fetch")

            mock_client.return_value.__aenter__.return_value.get = mock_get

            result = await executor.summarize_sources(request, client_id="test")

            # Should still work with partial success
            assert len(result.summaries) == 2
            # Check that one succeeded and one failed
            statuses = [s["status"] for s in result.summaries]
            assert "ok" in statuses
            assert "error" in statuses

    @pytest.mark.asyncio
    async def test_summarize_sources_respects_max_length(self):
        """Test that summarization respects max_length."""
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://example.com"],
            max_length=150,  # Short limit (minimum is 100)
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            # Long content
            mock_response.text = "<html><body><p>" + " ".join(
                ["word"] * 1000
            ) + "</p></body></html>"
            mock_response.raise_for_status = MagicMock()

            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                return_value=mock_response
            )

            result = await executor.summarize_sources(request, client_id="test")

            # Combined summary should respect max_length
            word_count = len(result.combined_summary.split())
            assert word_count <= 150

    @pytest.mark.asyncio
    async def test_summarize_sources_all_failures(self):
        """Test summarization when all URLs fail."""
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://example.com/1", "https://example.com/2"],
            max_length=500,
        )

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.get = AsyncMock(
                side_effect=Exception("Failed")
            )

            result = await executor.summarize_sources(request, client_id="test")

            assert result.status == "error"
            assert "No sources could be fetched successfully" in result.combined_summary
