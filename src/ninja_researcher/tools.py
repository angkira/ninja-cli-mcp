"""
MCP tool implementations for the Researcher module.

This module contains the business logic for all research-related MCP tools.
"""

from __future__ import annotations

import asyncio
from typing import Any

from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored
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

    @rate_balanced(max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0)
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

    @rate_balanced(max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0)
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

    @rate_balanced(max_calls=5, time_window=60, max_retries=3, initial_backoff=2.0, max_backoff=60.0)
    @monitored
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

        try:
            if not request.sources:
                return ReportResult(
                    status="error",
                    report="",
                    sources_used=0,
                    word_count=0,
                )

            # Divide sources among parallel agents
            sources_per_agent = max(1, len(request.sources) // request.parallel_agents)
            source_chunks = [
                request.sources[i:i + sources_per_agent]
                for i in range(0, len(request.sources), sources_per_agent)
            ]

            # Process each chunk to extract key information
            async def analyze_chunk(chunk: list[dict]) -> str:
                """Analyze a chunk of sources."""
                analysis = []
                for source in chunk:
                    title = source.get("title", "Untitled")
                    url = source.get("url", "")
                    snippet = source.get("snippet", "No description available")
                    analysis.append(f"- **{title}**: {snippet}\n  Source: {url}")
                return "\n".join(analysis)

            # Analyze all chunks in parallel
            semaphore = asyncio.Semaphore(request.parallel_agents)

            async def analyze_with_semaphore(chunk: list[dict]) -> str:
                async with semaphore:
                    return await analyze_chunk(chunk)

            chunk_analyses = await asyncio.gather(
                *[analyze_with_semaphore(chunk) for chunk in source_chunks]
            )

            # Generate report based on type
            if request.report_type == "executive":
                report = self._generate_executive_report(request.topic, chunk_analyses, request.sources)
            elif request.report_type == "technical":
                report = self._generate_technical_report(request.topic, chunk_analyses, request.sources)
            elif request.report_type == "summary":
                report = self._generate_summary_report(request.topic, chunk_analyses, request.sources)
            else:  # comprehensive
                report = self._generate_comprehensive_report(request.topic, chunk_analyses, request.sources)

            word_count = len(report.split())

            return ReportResult(
                status="ok",
                report=report,
                sources_used=len(request.sources),
                word_count=word_count,
            )

        except Exception as e:
            logger.error(f"Report generation failed for client {client_id}: {e}")
            return ReportResult(
                status="error",
                report=f"Report generation failed: {e}",
                sources_used=0,
                word_count=0,
            )

    def _generate_executive_report(self, topic: str, analyses: list[str], sources: list[dict]) -> str:
        """Generate an executive summary report."""
        report = f"# Executive Summary: {topic}\n\n"
        report += "## Key Findings\n\n"
        report += "\n\n".join(analyses)
        report += f"\n\n## Sources\n\n{len(sources)} sources consulted\n"
        return report

    def _generate_technical_report(self, topic: str, analyses: list[str], sources: list[dict]) -> str:
        """Generate a technical report."""
        report = f"# Technical Report: {topic}\n\n"
        report += "## Overview\n\n"
        report += "This report provides a technical analysis based on available sources.\n\n"
        report += "## Detailed Findings\n\n"
        report += "\n\n".join(analyses)
        report += "\n\n## References\n\n"
        for i, source in enumerate(sources, 1):
            report += f"{i}. [{source.get('title', 'Source')}]({source.get('url', '')})\n"
        return report

    def _generate_summary_report(self, topic: str, analyses: list[str], sources: list[dict]) -> str:
        """Generate a summary report."""
        report = f"# Summary: {topic}\n\n"
        combined = " ".join(analyses)
        # Truncate to reasonable length for summary
        if len(combined) > 1000:
            combined = combined[:1000] + "..."
        report += combined
        report += f"\n\n*Based on {len(sources)} sources*\n"
        return report

    def _generate_comprehensive_report(self, topic: str, analyses: list[str], sources: list[dict]) -> str:
        """Generate a comprehensive report."""
        report = f"# Comprehensive Report: {topic}\n\n"
        report += "## Table of Contents\n\n"
        report += "1. [Overview](#overview)\n"
        report += "2. [Detailed Analysis](#detailed-analysis)\n"
        report += "3. [Sources](#sources)\n\n"
        report += "## Overview\n\n"
        report += f"This comprehensive report on {topic} synthesizes information from {len(sources)} sources.\n\n"
        report += "## Detailed Analysis\n\n"
        for i, analysis in enumerate(analyses, 1):
            report += f"### Section {i}\n\n{analysis}\n\n"
        report += "## Sources\n\n"
        for i, source in enumerate(sources, 1):
            title = source.get('title', 'Untitled')
            url = source.get('url', '')
            snippet = source.get('snippet', '')
            report += f"{i}. **{title}**\n   - URL: {url}\n   - Summary: {snippet}\n\n"
        return report

    @rate_balanced(max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0)
    @monitored
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

        try:
            sources = request.sources

            # If no sources provided, search for them
            if not sources:
                # Use default search provider
                provider_name = self.provider_factory.get_default_provider()
                provider = self.provider_factory.get_provider(provider_name)

                try:
                    search_results = await provider.search(request.claim, max_results=5)
                    sources = [r["url"] for r in search_results if r.get("url")]

                    if not sources:
                        return FactCheckResult(
                            status="error",
                            claim=request.claim,
                            verdict="Could not find sources to verify claim",
                            sources=[],
                            confidence=0.0,
                        )
                except Exception as e:
                    logger.error(f"Search failed during fact checking: {e}")
                    return FactCheckResult(
                        status="error",
                        claim=request.claim,
                        verdict=f"Search failed: {e}",
                        sources=[],
                        confidence=0.0,
                    )

            # Simple keyword matching approach for fact checking
            # In production, this would use LLM or more sophisticated NLP
            claim_lower = request.claim.lower()
            claim_keywords = set(claim_lower.split())

            # Analyze sources for supporting/contradicting evidence
            supporting_count = 0

            for url in sources[:10]:  # Limit to first 10 sources
                # This is a simplified implementation
                # In production, would fetch and analyze actual content
                if any(keyword in url.lower() for keyword in claim_keywords):
                    supporting_count += 1

            total_sources = len(sources[:10])

            # Determine verdict based on source analysis
            if total_sources == 0:
                status = "uncertain"
                verdict = "No sources found to verify the claim"
                confidence = 0.0
            elif supporting_count > total_sources * 0.6:
                status = "verified"
                verdict = f"The claim appears to be supported by {supporting_count}/{total_sources} sources found"
                confidence = supporting_count / total_sources
            elif supporting_count < total_sources * 0.3:
                status = "disputed"
                verdict = f"The claim is only supported by {supporting_count}/{total_sources} sources, suggesting it may be disputed"
                confidence = 1.0 - (supporting_count / total_sources)
            else:
                status = "uncertain"
                verdict = f"The claim has mixed support ({supporting_count}/{total_sources} sources), verification is uncertain"
                confidence = 0.5

            return FactCheckResult(
                status=status,
                claim=request.claim,
                verdict=verdict,
                sources=sources[:10],
                confidence=confidence,
            )

        except Exception as e:
            logger.error(f"Fact checking failed for client {client_id}: {e}")
            return FactCheckResult(
                status="error",
                claim=request.claim,
                verdict=f"Fact checking failed: {e}",
                sources=[],
                confidence=0.0,
            )

    @rate_balanced(max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0)
    @monitored
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

        try:
            import httpx  # noqa: PLC0415
            from bs4 import BeautifulSoup  # noqa: PLC0415

            async def fetch_and_summarize(url: str) -> dict[str, str]:
                """Fetch URL and create a summary."""
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()

                        # Parse HTML and extract text
                        soup = BeautifulSoup(response.text, 'html.parser')

                        # Remove script and style elements
                        for script in soup(["script", "style", "nav", "footer", "header"]):
                            script.decompose()

                        # Get text
                        text = soup.get_text(separator=' ', strip=True)

                        # Clean up text
                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = ' '.join(chunk for chunk in chunks if chunk)

                        # Create summary (first N words)
                        words = text.split()
                        summary_length = min(200, len(words))
                        summary = ' '.join(words[:summary_length])

                        if len(words) > summary_length:
                            summary += "..."

                        return {
                            "url": url,
                            "status": "ok",
                            "summary": summary,
                            "word_count": len(words)
                        }

                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")
                    return {
                        "url": url,
                        "status": "error",
                        "summary": f"Failed to fetch: {e}",
                        "word_count": 0
                    }

            # Fetch all sources in parallel (with limit)
            semaphore = asyncio.Semaphore(5)  # Max 5 concurrent fetches

            async def fetch_with_semaphore(url: str) -> dict[str, str]:
                async with semaphore:
                    return await fetch_and_summarize(url)

            summaries = await asyncio.gather(
                *[fetch_with_semaphore(url) for url in request.urls]
            )

            # Create combined summary
            successful_summaries = [s for s in summaries if s["status"] == "ok"]

            if not successful_summaries:
                return SummaryResult(
                    status="error",
                    summaries=summaries,
                    combined_summary="No sources could be fetched successfully",
                )

            # Combine summaries respecting max_length
            combined_parts = []
            total_words = 0

            for summary_data in successful_summaries:
                summary_text = summary_data["summary"]
                words = summary_text.split()

                # Calculate how many words we can add
                words_to_add = min(len(words), request.max_length - total_words)

                if words_to_add > 0:
                    combined_parts.append(' '.join(words[:words_to_add]))
                    total_words += words_to_add

                if total_words >= request.max_length:
                    break

            combined_summary = '\n\n'.join(combined_parts)

            status = "ok" if len(successful_summaries) == len(summaries) else "partial"

            return SummaryResult(
                status=status,
                summaries=summaries,
                combined_summary=combined_summary,
            )

        except Exception as e:
            logger.error(f"Source summarization failed for client {client_id}: {e}")
            return SummaryResult(
                status="error",
                summaries=[],
                combined_summary=f"Summarization failed: {e}",
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
