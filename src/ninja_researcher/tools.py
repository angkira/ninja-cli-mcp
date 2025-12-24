"""
MCP tool implementations for the Researcher module.

This module contains the business logic for all research-related MCP tools.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ninja_common.logging_utils import get_logger
from ninja_common.security import monitored, rate_limited
from ninja_researcher.models import (
    DeepResearchRequest,
    FactCheckRequest,
    FactCheckResult,
    GenerateReportRequest,
    ReportResult,
    ResearchResult,
    SearchResult,
    SummarizeSourcesRequest,
    SummaryResult,
    WebSearchRequest,
    WebSearchResult,
)
from ninja_researcher.search_providers import SearchProviderFactory

logger = get_logger(__name__)


class ResearchToolExecutor:
    """Executor for research MCP tools."""

    def __init__(self):
        """Initialize the research tool executor."""
        self.provider_factory = SearchProviderFactory()

    @rate_limited(max_calls=30, time_window=60)
    @monitored
    async def web_search(
        self, request: WebSearchRequest, client_id: str = "default"
    ) -> WebSearchResult:
        """
        Search the web for information.

        Args:
            request: Web search request.
            client_id: Client identifier for rate limiting.

        Returns:
            Web search result with list of sources.
        """
        logger.info(
            f"Web search for '{request.query}' using {request.search_provider} (client: {client_id})"
        )

        try:
            # Get the search provider
            provider = self.provider_factory.get_provider(request.search_provider)

            if not provider.is_available():
                return WebSearchResult(
                    status="error",
                    query=request.query,
                    results=[],
                    provider=request.search_provider,
                    error_message=f"Provider {request.search_provider} is not available (missing API key?)",
                )

            # Perform search
            raw_results = await provider.search(request.query, request.max_results)

            # Convert to SearchResult models
            results = [
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["snippet"],
                    score=r.get("score", 0.0),
                )
                for r in raw_results
            ]

            return WebSearchResult(
                status="ok",
                query=request.query,
                results=results,
                provider=provider.get_name(),
            )

        except Exception as e:
            logger.error(f"Web search failed for client {client_id}: {e}")
            return WebSearchResult(
                status="error",
                query=request.query,
                results=[],
                provider=request.search_provider,
                error_message=str(e),
            )

    @rate_limited(max_calls=10, time_window=60)
    @monitored
    async def deep_research(
        self, request: DeepResearchRequest, client_id: str = "default"
    ) -> ResearchResult:
        """
        Perform deep research on a topic using multiple queries.

        Args:
            request: Deep research request.
            client_id: Client identifier for rate limiting.

        Returns:
            Research result with aggregated sources.
        """
        logger.info(f"Deep research on '{request.topic}' (client: {client_id})")

        try:
            # If no queries provided, generate them from the topic
            queries = request.queries
            if not queries:
                # Simple query generation - in production, use LLM to generate better queries
                queries = [
                    request.topic,
                    f"{request.topic} overview",
                    f"{request.topic} examples",
                    f"{request.topic} best practices",
                ]

            # Get default provider
            provider_name = self.provider_factory.get_default_provider()
            provider = self.provider_factory.get_provider(provider_name)

            # Create semaphore for parallel searches
            semaphore = asyncio.Semaphore(request.parallel_agents)

            async def search_query(query: str) -> list[dict[str, Any]]:
                """Search a single query with semaphore control."""
                async with semaphore:
                    return await provider.search(query, max_results=request.max_sources // len(queries))

            # Execute searches in parallel
            search_tasks = [search_query(q) for q in queries]
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            # Aggregate and deduplicate results
            seen_urls = set()
            sources = []

            for results in all_results:
                if isinstance(results, Exception):
                    logger.warning(f"Search query failed: {results}")
                    continue

                for result in results:
                    url = result.get("url", "")
                    if url and url not in seen_urls:
                        seen_urls.add(url)
                        sources.append(result)

                        if len(sources) >= request.max_sources:
                            break

                if len(sources) >= request.max_sources:
                    break

            # Create summary
            summary = f"Found {len(sources)} unique sources across {len(queries)} queries"

            return ResearchResult(
                status="ok" if sources else "error",
                topic=request.topic,
                sources_found=len(sources),
                sources=sources,
                summary=summary,
            )

        except Exception as e:
            logger.error(f"Deep research failed for client {client_id}: {e}")
            return ResearchResult(
                status="error",
                topic=request.topic,
                sources_found=0,
                sources=[],
                summary=f"Research failed: {e}",
            )

    async def generate_report(
        self, request: GenerateReportRequest, client_id: str = "default"
    ) -> ReportResult:
        """
        Generate a report from research sources.

        Args:
            request: Generate report request.
            client_id: Client identifier for rate limiting.

        Returns:
            Report result with generated markdown report.
        """
        logger.info(f"Generating {request.report_type} report on '{request.topic}' (client: {client_id})")

        # Placeholder implementation
        return ReportResult(
            status="error",
            report="",
            sources_used=0,
            word_count=0,
        )

    async def fact_check(
        self, request: FactCheckRequest, client_id: str = "default"
    ) -> FactCheckResult:
        """
        Fact check a claim against sources.

        Args:
            request: Fact check request.
            client_id: Client identifier for rate limiting.

        Returns:
            Fact check result with verdict.
        """
        logger.info(f"Fact checking claim (client: {client_id})")

        # Placeholder implementation
        return FactCheckResult(
            status="error",
            claim=request.claim,
            verdict="Fact checking not yet implemented",
            sources=[],
            confidence=0.0,
        )

    async def summarize_sources(
        self, request: SummarizeSourcesRequest, client_id: str = "default"
    ) -> SummaryResult:
        """
        Summarize multiple web sources.

        Args:
            request: Summarize sources request.
            client_id: Client identifier for rate limiting.

        Returns:
            Summary result with per-source and combined summaries.
        """
        logger.info(f"Summarizing {len(request.urls)} sources (client: {client_id})")

        # Placeholder implementation
        return SummaryResult(
            status="error",
            summaries=[],
            combined_summary="Source summarization not yet implemented",
        )


# Singleton executor instance
_executor: ResearchToolExecutor | None = None


def get_executor() -> ResearchToolExecutor:
    """Get the global research tool executor instance."""
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = ResearchToolExecutor()
    return _executor


def reset_executor() -> None:
    """Reset the global executor (for testing)."""
    global _executor  # noqa: PLW0603
    _executor = None
