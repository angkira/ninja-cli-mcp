"""Tests for evaluating the researcher AI tools."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from ninja_researcher.models import (
    DeepResearchRequest,
    FactCheckRequest,
    GenerateReportRequest,
    ResearchResult,
    SummarizeSourcesRequest,
    SummaryResult,
    WebSearchRequest,
)
from ninja_researcher.tools import ResearchToolExecutor

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture
def mock_search_results():
    """Create mock search results for testing."""
    return [
        {
            "title": "Python Programming Tutorial",
            "url": "https://example.com/python-tutorial",
            "snippet": "Learn Python programming with this comprehensive tutorial covering basics to advanced topics.",
            "score": 0.95,
        },
        {
            "title": "Advanced Python Techniques",
            "url": "https://example.com/advanced-python",
            "snippet": "Explore advanced Python programming techniques and best practices.",
            "score": 0.85,
        },
        {
            "title": "Python Data Science Handbook",
            "url": "https://example.com/python-data-science",
            "snippet": "Essential tools and techniques for data science with Python.",
            "score": 0.90,
        },
    ]


@pytest.fixture
def mock_html_content():
    """Create mock HTML content for testing."""
    return """
    <html>
    <head><title>Test Article</title></head>
    <body>
    <h1>Main Topic Header</h1>
    <p>This is the key information that should be captured in the summary. 
    It contains important facts about the subject matter that are essential to understand.</p>
    <p>Secondary information that provides additional context to the main points 
    and helps to better understand the topic in depth.</p>
    <footer>Footer content that should be ignored</footer>
    </body>
    </html>
    """


class TestResearcherDeepResearch:
    """Evaluation tests for researcher_deep_research."""

    @pytest.mark.asyncio
    async def test_deep_research_returns_sources(self, mock_search_results) -> None:
        """Test that deep research returns populated sources list."""
        # Arrange
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = mock_search_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)
            
            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            assert len(result.sources) > 0
            assert result.sources_found > 0

    @pytest.mark.asyncio
    async def test_deep_research_deduplicates_sources(self, mock_search_results) -> None:
        """Test that deep research deduplicates sources by URL."""
        # Arrange
        executor = ResearchToolExecutor()
        # Create duplicate URLs
        duplicate_results = mock_search_results + [
            {
                "title": "Duplicate Python Tutorial",
                "url": "https://example.com/python-tutorial",  # Same URL as first result
                "snippet": "Another version of the Python tutorial.",
                "score": 0.80,
            }
        ]
        
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = duplicate_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)
            
            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            # Should only have 3 unique sources despite 4 results
            assert len(result.sources) == 3
            assert result.sources_found == 3

            # Verify no duplicate URLs
            urls = [source["url"] for source in result.sources]
            assert len(urls) == len(set(urls))

    @pytest.mark.asyncio
    async def test_deep_research_source_structure(self, mock_search_results) -> None:
        """Test that each source has required fields."""
        # Arrange
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = mock_search_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)
            
            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            assert len(result.sources) > 0

            # Check required fields in each source
            for source in result.sources:
                assert "url" in source
                assert "title" in source
                assert "snippet" in source
                assert "score" in source

    @pytest.mark.asyncio
    async def test_deep_research_respects_max_sources(self, mock_search_results) -> None:
        """Test that deep research respects max_sources parameter."""
        # Arrange
        executor = ResearchToolExecutor()
        # Create more sources than max_sources
        many_results = []
        for i in range(15):
            many_results.append({
                "title": f"Test Article {i}",
                "url": f"https://example.com/article{i}",
                "snippet": f"This is test article {i} snippet about Python programming.",
                "score": 1.0 - (i * 0.05),
            })
        
        request = DeepResearchRequest(topic="Python programming", max_sources=10)
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = many_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)
            
            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            # Should not exceed max_sources
            assert len(result.sources) <= 10
            assert result.sources_found <= 10

    @pytest.mark.asyncio
    async def test_deep_research_parallel_agents(self) -> None:
        """Test that parallel_agents parameter affects search operations."""
        # Arrange
        executor = ResearchToolExecutor()
        custom_queries = ["query1", "query2", "query3"]
        request = DeepResearchRequest(
            topic="Python programming", 
            parallel_agents=3,
            queries=custom_queries
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = [
                {
                    "title": "Test Article",
                    "url": "https://example.com/article",
                    "snippet": "This is a test article snippet.",
                    "score": 0.9,
                }
            ]
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            # Mock asyncio.Semaphore to track parallel_agents usage
            with patch("ninja_researcher.tools.asyncio.Semaphore") as mock_semaphore:
                await executor.deep_research(request)
                
                # Check that semaphore was created with correct value
                mock_semaphore.assert_called_with(3)

    @pytest.mark.asyncio
    async def test_deep_research_custom_queries(self, mock_search_results) -> None:
        """Test that custom queries are used instead of auto-generated."""
        # Arrange
        executor = ResearchToolExecutor()
        custom_queries = ["custom python query 1", "custom python query 2", "custom python query 3"]
        request = DeepResearchRequest(
            topic="Python programming",
            queries=custom_queries
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = mock_search_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            await executor.deep_research(request)
            
            # Verify that search was called for each custom query
            assert mock_provider.search.call_count == len(custom_queries)
            called_queries = [call[0][0] for call in mock_provider.search.call_args_list]
            assert called_queries == custom_queries


class TestResearcherSummarizeSources:
    """Evaluation tests for researcher_summarize_sources."""

    @pytest.mark.asyncio
    async def test_summarize_sources_extracts_key_points(self, mock_html_content) -> None:
        """Test that summarize sources extracts key information."""
        # Arrange
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://example.com/article"]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = mock_html_content
            mock_response.raise_for_status = MagicMock()
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "ok"
            assert len(result.summaries) == 1
            assert "key information" in result.summaries[0]["summary"]
            assert "important facts" in result.summaries[0]["summary"]

    @pytest.mark.asyncio
    async def test_summarize_sources_respects_max_length(self) -> None:
        """Test that summarize sources respects max_length parameter."""
        # Arrange
        executor = ResearchToolExecutor()
        # Create long content
        long_content = " ".join(["word"] * 500)  # 500 words
        html_content = f"""
        <html>
        <head><title>Test Article</title></head>
        <body>
        <p>{long_content}</p>
        </body>
        </html>
        """
        
        request = SummarizeSourcesRequest(
            urls=["https://example.com/article"],
            max_length=200
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = html_content
            mock_response.raise_for_status = MagicMock()
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "ok"
            # Check that summary is under the max length (allowing some buffer for processing)
            summary_words = result.summaries[0]["summary"].split()
            assert len(summary_words) <= 250  # Allow some buffer

    @pytest.mark.asyncio
    async def test_summarize_sources_multiple_sources(self, mock_html_content) -> None:
        """Test summarize sources with multiple URLs."""
        # Arrange
        executor = ResearchToolExecutor()
        html_content1 = mock_html_content.replace("Main Topic Header", "Python Basics")
        html_content2 = mock_html_content.replace("Main Topic Header", "Python Applications")
        html_content3 = mock_html_content.replace("Main Topic Header", "Python Libraries")
        
        # Mock responses for multiple URLs
        async def mock_get(url, follow_redirects=True):
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            if "article1" in url:
                mock_response.text = html_content1
            elif "article2" in url:
                mock_response.text = html_content2
            else:
                mock_response.text = html_content3
            return mock_response

        request = SummarizeSourcesRequest(
            urls=[
                "https://example.com/article1",
                "https://example.com/article2",
                "https://example.com/article3"
            ]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = mock_get
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "ok"
            assert len(result.summaries) == 3
            
            # Check that combined summary includes info from all sources
            assert "Python" in result.combined_summary
            # Should mention content from different sources
            assert "Basics" in result.combined_summary or "Applications" in result.combined_summary or "Libraries" in result.combined_summary

    @pytest.mark.asyncio
    async def test_summarize_sources_handles_invalid_urls(self) -> None:
        """Test that summarize sources handles invalid URLs gracefully."""
        # Arrange
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["https://invalid-url-that-does-not-exist.com"]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            # Mock an exception for invalid URL
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = Exception("Invalid URL")
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "error"  # All sources failed
            assert len(result.summaries) == 1
            assert result.summaries[0]["status"] == "error"

    @pytest.mark.asyncio
    async def test_summarize_sources_combined_vs_individual(self, mock_html_content) -> None:
        """Test that combined summary connects main themes from all sources."""
        # Arrange
        executor = ResearchToolExecutor()
        html_content1 = """
        <html>
        <head><title>Python Basics</title></head>
        <body>
        <p>Python is a high-level programming language known for its simplicity and readability.</p>
        </body>
        </html>
        """
        
        html_content2 = """
        <html>
        <head><title>Python Applications</title></head>
        <body>
        <p>Python is widely used in web development, data science, and automation tasks.</p>
        </body>
        </html>
        """
        
        # Mock responses
        async def mock_get(url, follow_redirects=True):
            mock_response = MagicMock()
            mock_response.raise_for_status = MagicMock()
            if "basics" in url:
                mock_response.text = html_content1
            else:
                mock_response.text = html_content2
            return mock_response

        request = SummarizeSourcesRequest(
            urls=[
                "https://example.com/python-basics",
                "https://example.com/python-applications"
            ]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = mock_get
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "ok"
            
            # Check that combined summary connects themes
            assert "Python" in result.combined_summary
            # Should mention both aspects (language characteristics and applications)
            assert ("high-level" in result.combined_summary and 
                   ("web development" in result.combined_summary or 
                    "data science" in result.combined_summary))


class TestResearcherErrorHandling:
    """Evaluation tests for error handling in researcher tools."""

    @pytest.mark.asyncio
    async def test_deep_research_api_timeout(self) -> None:
        """Test that deep research handles API timeout properly."""
        # Arrange
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.side_effect = asyncio.TimeoutError("Search timeout")
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)

            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "error"
            assert result.sources_found == 0
            assert "timeout" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_summarize_sources_invalid_urls(self) -> None:
        """Test that summarize sources handles completely invalid URLs."""
        # Arrange
        executor = ResearchToolExecutor()
        request = SummarizeSourcesRequest(
            urls=["not-a-valid-url", "also-invalid"]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.side_effect = Exception("DNS resolution failed")
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "error"
            assert len(result.summaries) == 2
            # All summaries should have error status
            assert all(s["status"] == "error" for s in result.summaries)

    @pytest.mark.asyncio
    async def test_deep_research_rate_limiting(self) -> None:
        """Test that deep research handles rate limiting without failures."""
        # Arrange
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = [
                {
                    "title": "Test Article",
                    "url": "https://example.com/article",
                    "snippet": "This is a test article snippet.",
                    "score": 0.9,
                }
            ]
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            # Mock rate limiting decorator to ensure it doesn't cause failures
            with patch("ninja_researcher.tools.rate_balanced") as mock_rate_balanced:
                mock_rate_balanced.return_value = lambda f: f  # No-op decorator

                result = await executor.deep_research(request)

                # Should still work even with rate limiting mocked
                assert isinstance(result, ResearchResult)
                assert result.status in ["ok", "error"]


class TestResearcherResultQualityMetrics:
    """Evaluation tests for result quality metrics."""

    @pytest.mark.asyncio
    async def test_deep_research_result_relevance(self, mock_search_results) -> None:
        """Test that research results are relevant to the topic."""
        # Arrange
        executor = ResearchToolExecutor()
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = mock_search_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)

            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            
            # Check that sources are relevant to the topic
            for source in result.sources:
                title_and_snippet = (source["title"] + " " + source["snippet"]).lower()
                assert "python" in title_and_snippet

    @pytest.mark.asyncio
    async def test_summarize_sources_factual_accuracy(self, mock_html_content) -> None:
        """Test that summaries don't hallucinate facts."""
        # Arrange
        executor = ResearchToolExecutor()
        factual_html = """
        <html>
        <head><title>Factual Article</title></head>
        <body>
        <p>According to official records, Python was created by Guido van Rossum in 1991.</p>
        <p>It is a high-level programming language with a focus on readability.</p>
        </body>
        </html>
        """
        
        request = SummarizeSourcesRequest(
            urls=["https://example.com/factual-article"]
        )
        
        # Act & Assert
        with patch("ninja_researcher.tools.httpx.AsyncClient") as mock_client:
            mock_response = MagicMock()
            mock_response.text = factual_html
            mock_response.raise_for_status = MagicMock()
            mock_client_instance = AsyncMock()
            mock_client_instance.__aenter__.return_value = mock_client_instance
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value = mock_client_instance

            result = await executor.summarize_sources(request)

            # Verify the result
            assert isinstance(result, SummaryResult)
            assert result.status == "ok"
            
            summary = result.summaries[0]["summary"]
            # Should contain key facts from source
            assert "Python" in summary
            assert "Guido van Rossum" in summary
            assert "1991" in summary
            # Should not contain made-up information
            assert "JavaScript" not in summary  # Not in original content

    @pytest.mark.asyncio
    async def test_deep_research_source_diversity(self, mock_search_results) -> None:
        """Test that sources come from different domains."""
        # Arrange
        executor = ResearchToolExecutor()
        diverse_results = [
            {
                "title": "Python on Wikipedia",
                "url": "https://wikipedia.org/wiki/Python_(programming_language)",
                "snippet": "Python programming language overview on Wikipedia.",
                "score": 0.9,
            },
            {
                "title": "Python on GitHub",
                "url": "https://github.com/python/cpython",
                "snippet": "Official Python repository on GitHub.",
                "score": 0.8,
            },
            {
                "title": "Python on Stack Overflow",
                "url": "https://stackoverflow.com/questions/tagged/python",
                "snippet": "Python programming questions and answers on Stack Overflow.",
                "score": 0.7,
            },
        ]
        
        request = DeepResearchRequest(topic="Python programming")
        
        # Act & Assert
        with patch("ninja_researcher.tools.SearchProviderFactory") as mock_factory:
            mock_provider = AsyncMock()
            mock_provider.search.return_value = diverse_results
            mock_factory.get_provider.return_value = mock_provider
            mock_factory.get_default_provider.return_value = "mock_provider"

            result = await executor.deep_research(request)

            # Verify the result
            assert isinstance(result, ResearchResult)
            assert result.status == "ok"
            
            # Extract domains
            domains = set()
            for source in result.sources:
                url = source["url"]
                # Simple domain extraction
                if "://" in url:
                    domain = url.split("/")[2]
                    domains.add(domain)
            
            # Should have sources from different domains
            assert len(domains) >= 2  # At least 2 different domains
