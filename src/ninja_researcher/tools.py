"""
MCP tool implementations for the Researcher module.

This module contains the business logic for all research-related MCP tools.
Failures are surfaced as structured :class:`~ninja_researcher.models.ErrorInfo`
payloads embedded in results; raw exception text is never written into the
human-readable text fields.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored
from ninja_researcher.arxiv import arxiv_search as arxiv_search_infra
from ninja_researcher.arxiv import fetch_paper as fetch_paper_infra
from ninja_researcher.arxiv import parse_arxiv_id
from ninja_researcher.enrichment import enrich_sources
from ninja_researcher.models import (
    ArxivSearchRequest,
    ArxivSearchResult,
    DeepResearchBatchRequest,
    DeepResearchBatchResult,
    DeepResearchRequest,
    ErrorInfo,
    ErrorKind,
    FactCheckRequest,
    FactCheckResult,
    GenerateReportRequest,
    PaperFetchRequest,
    PaperFetchResult,
    ReportResult,
    ResearchResult,
    SearchResult,
    SummarizeSourcesRequest,
    SummaryResult,
    WebSearchRequest,
    WebSearchResult,
)
from ninja_researcher.search_providers import ProviderError, SearchProviderFactory


logger = get_logger(__name__)


_ARXIV_MIN_SPACING_S = 3.0
_ARXIV_MAX_BACKOFF_S = 120.0
_BATCH_WALL_LIMIT_S = 600.0

_arxiv_gate_lock: asyncio.Lock | None = None
_last_arxiv_call = 0.0

_ERROR_SEVERITY: dict[ErrorKind, int] = {
    ErrorKind.rate_limited: 0,
    ErrorKind.upstream: 1,
    ErrorKind.parse: 2,
    ErrorKind.env: 3,
}


def _env_error(exc: BaseException) -> ErrorInfo:
    """Build an ``env`` :class:`ErrorInfo` for a missing optional dependency."""
    missing = getattr(exc, "name", None) or "optional dependency"
    return ErrorInfo(
        kind=ErrorKind.env,
        message=(
            f"Missing optional dependency '{missing}'. Install it with the "
            "researcher/runtime extra."
        ),
    )


def _error_from_exception(exc: BaseException) -> ErrorInfo:
    """
    Classify an arbitrary exception into a structured :class:`ErrorInfo`.

    Args:
        exc: The exception to classify.

    Returns:
        A classified error payload whose message never contains raw traceback
        or exception text.
    """
    if isinstance(exc, ProviderError):
        return ErrorInfo(
            kind=exc.kind,
            message=exc.message,
            retry_after_s=exc.retry_after_s,
        )
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return _env_error(exc)
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            retry_after: float | None = None
            header = exc.response.headers.get("Retry-After")
            if header:
                try:
                    retry_after = max(0.0, float(header.strip()))
                except (TypeError, ValueError):
                    retry_after = None
            return ErrorInfo(
                kind=ErrorKind.rate_limited,
                message=f"Provider rate limited the request (HTTP {status})",
                retry_after_s=retry_after,
            )
        return ErrorInfo(kind=ErrorKind.upstream, message=f"Provider returned HTTP {status}")
    if isinstance(exc, httpx.TimeoutException):
        return ErrorInfo(kind=ErrorKind.upstream, message="Provider request timed out")
    if isinstance(exc, ValueError):
        detail = str(exc).strip()[:200]
        return ErrorInfo(
            kind=ErrorKind.parse,
            message=detail or "Response could not be parsed",
        )
    if isinstance(exc, KeyError):
        return ErrorInfo(kind=ErrorKind.parse, message="Response could not be parsed")
    return ErrorInfo(kind=ErrorKind.upstream, message="Provider request failed")


def _most_severe(errors: list[ErrorInfo]) -> ErrorInfo:
    """Return the most severe error from a list (rate-limit preferred)."""
    return min(errors, key=lambda info: _ERROR_SEVERITY.get(info.kind, 99))


def _host_of(url: str) -> str:
    """Return the lowercased hostname of a URL."""
    host = (urlparse(url).netloc or "").lower()
    return host[4:] if host.startswith("www.") else host


def _host_matches(host: str, domains: list[str]) -> bool:
    """Return True if *host* equals or is a subdomain of any domain entry."""
    return any(host == domain or host.endswith(f".{domain}") for domain in domains)


def _apply_domain_filters(
    sources: list[dict[str, Any]],
    include_domains: list[str] | None,
    exclude_domains: list[str] | None,
    prefer_domains: list[str] | None,
) -> list[dict[str, Any]]:
    """
    Apply include/exclude/prefer domain filters to a source list.

    Exclusion always wins over inclusion. ``prefer_domains`` performs a stable
    sort so matching sources come first while relative order is preserved.

    Args:
        sources: Deduplicated source dicts.
        include_domains: Keep only hosts matching these, when set.
        exclude_domains: Drop hosts matching these.
        prefer_domains: Order matching hosts first.

    Returns:
        The filtered and ordered source list.
    """
    filtered = sources
    if exclude_domains:
        filtered = [
            s for s in filtered if not _host_matches(_host_of(s.get("url", "")), exclude_domains)
        ]
    if include_domains:
        filtered = [
            s for s in filtered if _host_matches(_host_of(s.get("url", "")), include_domains)
        ]
    if prefer_domains:
        filtered = sorted(
            filtered,
            key=lambda s: 0 if _host_matches(_host_of(s.get("url", "")), prefer_domains) else 1,
        )
    return filtered


def _get_arxiv_lock() -> asyncio.Lock:
    """Return the lazily created module-level arXiv spacing lock."""
    global _arxiv_gate_lock
    if _arxiv_gate_lock is None:
        _arxiv_gate_lock = asyncio.Lock()
    return _arxiv_gate_lock


async def _await_arxiv_slot() -> None:
    """Enforce at least 3 seconds of spacing between arXiv API calls."""
    global _last_arxiv_call
    async with _get_arxiv_lock():
        elapsed = time.monotonic() - _last_arxiv_call
        wait = _ARXIV_MIN_SPACING_S - elapsed
        if wait > 0:
            await asyncio.sleep(wait)
        _last_arxiv_call = time.monotonic()


class ResearchToolExecutor:
    """Executor for research MCP tools."""

    def __init__(self) -> None:
        """Initialize the research tool executor."""
        self.provider_factory = SearchProviderFactory()

    @rate_balanced(
        max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0
    )
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
            provider = self.provider_factory.get_provider(request.search_provider)

            if not provider.is_available():
                return WebSearchResult(
                    status="error",
                    query=request.query,
                    results=[],
                    provider=request.search_provider,
                    error_message=f"Provider {request.search_provider} is not available (missing API key?)",
                    error=ErrorInfo(
                        kind=ErrorKind.env,
                        message=f"Provider {request.search_provider} is not available",
                    ),
                )

            raw_results = await provider.search(request.query, request.max_results)

            results = [
                SearchResult(
                    title=r["title"],
                    url=r["url"],
                    snippet=r["snippet"],
                    score=r.get("score"),
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
                error_message="",
                error=_error_from_exception(e),
            )

    @rate_balanced(
        max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0
    )
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
            Research result with aggregated sources and a typed error, if any.
        """
        logger.info(f"Deep research on '{request.topic}' (client: {client_id})")

        try:
            queries = request.queries
            if not queries:
                queries = [
                    request.topic,
                    f"{request.topic} overview",
                    f"{request.topic} examples",
                    f"{request.topic} best practices",
                ]

            provider_name = self.provider_factory.get_default_provider()
            provider = self.provider_factory.get_provider(provider_name)

            semaphore = asyncio.Semaphore(request.parallel_agents)
            per_query = max(1, request.max_sources // len(queries))

            async def search_query(query: str) -> list[dict[str, Any]]:
                """Search a single query with semaphore control."""
                async with semaphore:
                    return await provider.search(query, max_results=per_query)

            search_tasks = [search_query(q) for q in queries]
            all_results = await asyncio.gather(*search_tasks, return_exceptions=True)

            errors: list[ErrorInfo] = []
            seen_urls: set[str] = set()
            sources: list[dict[str, Any]] = []

            for results in all_results:
                if isinstance(results, BaseException):
                    logger.warning(f"Search query failed: {results}")
                    errors.append(_error_from_exception(results))
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

            sources = _apply_domain_filters(
                sources,
                request.include_domains,
                request.exclude_domains,
                request.prefer_domains,
            )

            if request.enrich and sources:
                sources = await enrich_sources(sources)

            if sources:
                return ResearchResult(
                    status="ok",
                    topic=request.topic,
                    sources_found=len(sources),
                    sources=sources,
                    summary=f"Found {len(sources)} unique sources across {len(queries)} queries",
                )

            if errors:
                return ResearchResult(
                    status="error",
                    topic=request.topic,
                    sources_found=0,
                    sources=[],
                    summary="",
                    error=_most_severe(errors),
                )

            return ResearchResult(
                status="ok",
                topic=request.topic,
                sources_found=0,
                sources=[],
                summary="No sources found",
            )

        except Exception as e:
            logger.error(f"Deep research failed for client {client_id}: {e}")
            return ResearchResult(
                status="error",
                topic=request.topic,
                sources_found=0,
                sources=[],
                summary="",
                error=_error_from_exception(e),
            )

    @monitored
    async def arxiv_search(
        self, request: ArxivSearchRequest, client_id: str = "default"
    ) -> ArxivSearchResult:
        """
        Search arXiv via the public Atom API.

        Args:
            request: arXiv search request.
            client_id: Client identifier (unused, kept for executor symmetry).

        Returns:
            Structured arXiv search result with a typed error, if any.
        """
        logger.info(f"arXiv search for '{request.query}' (client: {client_id})")

        try:
            await _await_arxiv_slot()
            papers = await arxiv_search_infra(
                request.query,
                categories=request.categories,
                max_results=request.max_results,
                sort_by=request.sort_by,
                full_metadata=request.full_metadata,
            )
            paper_dicts = [
                paper.model_dump(exclude_none=not request.full_metadata) for paper in papers
            ]
            return ArxivSearchResult(
                status="ok",
                query=request.query,
                papers=paper_dicts,
            )
        except Exception as e:
            logger.error(f"arXiv search failed: {e}")
            return ArxivSearchResult(
                status="error",
                query=request.query,
                papers=[],
                error=_error_from_exception(e),
            )

    @monitored
    async def paper_fetch(
        self, request: PaperFetchRequest, client_id: str = "default"
    ) -> PaperFetchResult:
        """
        Fetch and parse a paper or web page.

        Args:
            request: Paper fetch request.
            client_id: Client identifier (unused, kept for executor symmetry).

        Returns:
            Extracted paper content with a typed error, if any.
        """
        logger.info(f"Paper fetch for '{request.source}' (client: {client_id})")

        try:
            if parse_arxiv_id(request.source) is not None:
                await _await_arxiv_slot()
            paper = await fetch_paper_infra(
                request.source, request.sections, request.extract_numbers
            )
            if paper.error is not None:
                return PaperFetchResult(status="error", paper=paper, error=paper.error)
            return PaperFetchResult(status="ok", paper=paper)
        except Exception as e:
            logger.error(f"Paper fetch failed: {e}")
            return PaperFetchResult(status="error", paper=None, error=_error_from_exception(e))

    @monitored
    async def deep_research_batch(
        self, request: DeepResearchBatchRequest, client_id: str = "default"
    ) -> DeepResearchBatchResult:
        """
        Run several deep-research requests strictly serially.

        Args:
            request: Batch request.
            client_id: Client identifier passed to each sub-request.

        Returns:
            Aggregated batch result; each element is a normal ``ResearchResult``.
        """
        logger.info(f"Deep research batch of {len(request.requests)} (client: {client_id})")

        started = time.monotonic()
        total = len(request.requests)
        results: list[ResearchResult] = []

        try:
            for index, sub_request in enumerate(request.requests):
                if time.monotonic() - started > _BATCH_WALL_LIMIT_S:
                    return DeepResearchBatchResult(
                        status="timeout",
                        total=total,
                        completed=len(results),
                        results=results,
                        error=ErrorInfo(
                            kind=ErrorKind.upstream,
                            message="Batch wall-clock limit exceeded",
                        ),
                    )

                result = await self._run_batch_request(sub_request, request, client_id)
                results.append(result)

                if result.error is not None and request.on_error == "abort":
                    return DeepResearchBatchResult(
                        status="aborted",
                        total=total,
                        completed=len(results),
                        results=results,
                        error=result.error,
                    )

                if index < total - 1 and request.inter_call_delay_s > 0:
                    await asyncio.sleep(request.inter_call_delay_s)

            status = "ok" if all(r.error is None for r in results) else "partial"
            return DeepResearchBatchResult(
                status=status,
                total=total,
                completed=len(results),
                results=results,
            )

        except Exception as e:
            logger.error(f"Deep research batch failed: {e}")
            return DeepResearchBatchResult(
                status="error",
                total=total,
                completed=len(results),
                results=results,
                error=_error_from_exception(e),
            )

    async def _run_batch_request(
        self,
        sub_request: DeepResearchRequest,
        batch: DeepResearchBatchRequest,
        client_id: str,
    ) -> ResearchResult:
        """
        Run one batch sub-request, applying the configured error policy.

        Args:
            sub_request: The individual deep-research request.
            batch: The enclosing batch request (policy source).
            client_id: Client identifier.

        Returns:
            The (possibly retried) research result.
        """
        result = await self.deep_research(sub_request, client_id=client_id)

        if (
            batch.on_error != "retry_backoff"
            or result.error is None
            or result.error.kind != ErrorKind.rate_limited
        ):
            return result

        for attempt in range(1, 3):
            delay = max(result.error.retry_after_s or 0.0, (2**attempt) * 10)
            delay = min(delay, _ARXIV_MAX_BACKOFF_S)
            await asyncio.sleep(delay)
            result = await self.deep_research(sub_request, client_id=client_id)
            if result.error is None or result.error.kind != ErrorKind.rate_limited:
                break
        return result

    @rate_balanced(
        max_calls=5, time_window=60, max_retries=3, initial_backoff=2.0, max_backoff=60.0
    )
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
        logger.info(
            f"Generating {request.report_type} report on '{request.topic}' (client: {client_id})"
        )

        try:
            if not request.sources:
                return ReportResult(
                    status="error",
                    report="",
                    sources_used=0,
                    word_count=0,
                )

            sources_per_agent = max(1, len(request.sources) // request.parallel_agents)
            source_chunks = [
                request.sources[i : i + sources_per_agent]
                for i in range(0, len(request.sources), sources_per_agent)
            ]

            async def analyze_chunk(chunk: list[dict]) -> str:
                """Analyze a chunk of sources.

                Each source dict may contain the text body under any of:
                ``snippet``, ``content``, or ``description``.
                """
                analysis = []
                for source in chunk:
                    title = source.get("title", "Untitled")
                    url = source.get("url", "")
                    snippet = (
                        source.get("snippet")
                        or source.get("content")
                        or source.get("description")
                        or "No description available"
                    )
                    analysis.append(f"- **{title}**: {snippet}\n  Source: {url}")
                return "\n".join(analysis)

            semaphore = asyncio.Semaphore(request.parallel_agents)

            async def analyze_with_semaphore(chunk: list[dict]) -> str:
                async with semaphore:
                    return await analyze_chunk(chunk)

            chunk_analyses = await asyncio.gather(
                *[analyze_with_semaphore(chunk) for chunk in source_chunks]
            )

            if request.report_type == "executive":
                report = self._generate_executive_report(
                    request.topic, chunk_analyses, request.sources
                )
            elif request.report_type == "technical":
                report = self._generate_technical_report(
                    request.topic, chunk_analyses, request.sources
                )
            elif request.report_type == "summary":
                report = self._generate_summary_report(
                    request.topic, chunk_analyses, request.sources
                )
            else:  # comprehensive
                report = self._generate_comprehensive_report(
                    request.topic, chunk_analyses, request.sources
                )

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
                report="",
                sources_used=0,
                word_count=0,
                error=_error_from_exception(e),
            )

    def _generate_executive_report(
        self, topic: str, analyses: list[str], sources: list[dict]
    ) -> str:
        """Generate an executive summary report."""
        report = f"# Executive Summary: {topic}\n\n"
        report += "## Key Findings\n\n"
        report += "\n\n".join(analyses)
        report += f"\n\n## Sources\n\n{len(sources)} sources consulted\n"
        return report

    def _generate_technical_report(
        self, topic: str, analyses: list[str], sources: list[dict]
    ) -> str:
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
        if len(combined) > 1000:
            combined = combined[:1000] + "..."
        report += combined
        report += f"\n\n*Based on {len(sources)} sources*\n"
        return report

    def _generate_comprehensive_report(
        self, topic: str, analyses: list[str], sources: list[dict]
    ) -> str:
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
            title = source.get("title", "Untitled")
            url = source.get("url", "")
            snippet = (
                source.get("snippet") or source.get("content") or source.get("description") or ""
            )
            report += f"{i}. **{title}**\n   - URL: {url}\n   - Summary: {snippet}\n\n"
        return report

    @rate_balanced(
        max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0
    )
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
            Fact check result with verdict and a typed error, if any.
        """
        logger.info(f"Fact checking claim (client: {client_id})")

        try:
            sources = request.sources

            if not sources:
                provider_name = self.provider_factory.get_default_provider()
                provider = self.provider_factory.get_provider(provider_name)

                try:
                    search_results = await provider.search(request.claim, max_results=5)
                except Exception as e:
                    logger.error(f"Search failed during fact checking: {e}")
                    return FactCheckResult(
                        status="error",
                        claim=request.claim,
                        verdict="",
                        sources=[],
                        confidence=0.0,
                        error=_error_from_exception(e),
                    )

                sources = [r["url"] for r in search_results if r.get("url")]

                if not sources:
                    return FactCheckResult(
                        status="error",
                        claim=request.claim,
                        verdict="Could not find sources to verify claim",
                        sources=[],
                        confidence=0.0,
                    )

            claim_lower = request.claim.lower()
            claim_keywords = set(claim_lower.split())

            supporting_count = 0

            for url in sources[:10]:
                if any(keyword in url.lower() for keyword in claim_keywords):
                    supporting_count += 1

            total_sources = len(sources[:10])

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
                verdict="",
                sources=[],
                confidence=0.0,
                error=_error_from_exception(e),
            )

    @rate_balanced(
        max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=60.0
    )
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
            import httpx

            try:
                from bs4 import BeautifulSoup
            except ImportError as e:
                return SummaryResult(
                    status="error",
                    summaries=[],
                    combined_summary="",
                    error=_error_from_exception(e),
                )

            async def fetch_and_summarize(url: str) -> dict[str, Any]:
                """Fetch URL and create a summary."""
                try:
                    async with httpx.AsyncClient(timeout=30.0) as client:
                        response = await client.get(url, follow_redirects=True)
                        response.raise_for_status()

                        soup = BeautifulSoup(response.text, "html.parser")

                        for script in soup(["script", "style", "nav", "footer", "header"]):
                            script.decompose()

                        text = soup.get_text(separator=" ", strip=True)

                        lines = (line.strip() for line in text.splitlines())
                        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                        text = " ".join(chunk for chunk in chunks if chunk)

                        words = text.split()
                        summary_length = min(200, len(words))
                        summary = " ".join(words[:summary_length])

                        if len(words) > summary_length:
                            summary += "..."

                        return {
                            "url": url,
                            "status": "ok",
                            "summary": summary,
                            "word_count": len(words),
                            "error": None,
                        }

                except Exception as e:
                    logger.warning(f"Failed to fetch {url}: {e}")
                    return {
                        "url": url,
                        "status": "error",
                        "summary": "",
                        "word_count": 0,
                        "error": _error_from_exception(e).model_dump(mode="json"),
                    }

            semaphore = asyncio.Semaphore(5)

            async def fetch_with_semaphore(url: str) -> dict[str, Any]:
                async with semaphore:
                    return await fetch_and_summarize(url)

            summaries = await asyncio.gather(*[fetch_with_semaphore(url) for url in request.urls])

            successful_summaries = [s for s in summaries if s["status"] == "ok"]

            combined_parts = []
            total_words = 0

            for summary_data in successful_summaries:
                summary_text = summary_data["summary"]
                words = summary_text.split()
                words_to_add = min(len(words), request.max_length - total_words)
                if words_to_add > 0:
                    combined_parts.append(" ".join(words[:words_to_add]))
                    total_words += words_to_add
                if total_words >= request.max_length:
                    break

            combined_summary = "\n\n".join(combined_parts)

            if not successful_summaries:
                return SummaryResult(
                    status="error",
                    summaries=summaries,
                    combined_summary="",
                    error=ErrorInfo(
                        kind=ErrorKind.upstream,
                        message="No sources could be fetched successfully",
                    ),
                )

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
                combined_summary="",
                error=_error_from_exception(e),
            )


# Singleton executor instance
_executor: ResearchToolExecutor | None = None


def get_executor() -> ResearchToolExecutor:
    """Get the global research tool executor instance."""
    global _executor
    if _executor is None:
        _executor = ResearchToolExecutor()
    return _executor


def reset_executor() -> None:
    """Reset the global executor (for testing)."""
    global _executor
    _executor = None
