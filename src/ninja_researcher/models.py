"""
Pydantic models for Ninja Researcher MCP tools.

These models define the API surface for the researcher module.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


def get_default_search_provider() -> str:
    """
    Get default search provider from environment or fallback to duckduckgo.

    Returns:
        Default search provider name.
    """
    return os.environ.get("NINJA_SEARCH_PROVIDER", "duckduckgo")


# ============================================================================
# Error Models
# ============================================================================


class ErrorKind(str, Enum):
    """Classification of an error surfaced by a researcher tool."""

    rate_limited = "rate_limited"
    upstream = "upstream"
    parse = "parse"
    env = "env"


class ErrorInfo(BaseModel):
    """Structured, machine-readable error payload embedded in tool results."""

    kind: ErrorKind = Field(..., description="Error classification")
    message: str = Field(..., description="Short, neutral human-readable message")
    retry_after_s: float | None = Field(
        default=None, description="Suggested retry delay in seconds, when known"
    )


# ============================================================================
# Request Models
# ============================================================================


class WebSearchRequest(BaseModel):
    """Request for web search."""

    query: str = Field(..., description="Search query")
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum number of results")
    search_provider: str = Field(
        default_factory=get_default_search_provider,
        description="Search provider to use (duckduckgo, serper, perplexity)",
    )


class DeepResearchRequest(BaseModel):
    """Request for deep research with multiple queries."""

    topic: str = Field(..., description="Research topic")
    queries: list[str] = Field(
        default_factory=list,
        description="Specific queries to research (auto-generated if empty)",
    )
    max_sources: int = Field(default=20, ge=1, le=100, description="Maximum sources to gather")
    parallel_agents: int = Field(
        default=4, ge=1, le=8, description="Number of parallel research agents"
    )
    enrich: bool = Field(
        default=True,
        description="Fetch pages to replace provider snippets with real extracted text",
    )
    include_domains: list[str] | None = Field(
        default=None, description="If set, keep only sources whose host matches one of these"
    )
    exclude_domains: list[str] | None = Field(
        default=None, description="Drop sources whose host matches any of these (subdomains too)"
    )
    prefer_domains: list[str] | None = Field(
        default=None, description="Order matching sources first, preserving relative order"
    )

    @field_validator("include_domains", "exclude_domains", "prefer_domains")
    @classmethod
    def _normalize_domains(cls, value: list[str] | None) -> list[str] | None:
        """Lowercase domain entries and drop empty strings."""
        if value is None:
            return None
        cleaned = [entry.strip().lower() for entry in value if entry and entry.strip()]
        return cleaned or None


class GenerateReportRequest(BaseModel):
    """Request for report generation from research."""

    topic: str = Field(..., description="Report topic")
    sources: list[dict] = Field(..., description="Source documents to synthesize")
    report_type: str = Field(
        default="comprehensive",
        description="Report type (comprehensive, summary, technical, executive)",
    )
    parallel_agents: int = Field(
        default=4, ge=1, le=8, description="Number of parallel synthesis agents"
    )


class FactCheckRequest(BaseModel):
    """Request for fact checking."""

    claim: str = Field(..., description="Claim to verify")
    sources: list[str] = Field(
        default_factory=list, description="URLs to check against (auto-search if empty)"
    )


class SummarizeSourcesRequest(BaseModel):
    """Request to summarize multiple sources."""

    urls: list[str] = Field(..., description="URLs to summarize")
    max_length: int = Field(
        default=500, ge=100, le=5000, description="Maximum summary length in words"
    )


class DeepResearchBatchRequest(BaseModel):
    """Request to run several deep-research requests strictly serially."""

    requests: list[DeepResearchRequest] = Field(
        ..., min_length=1, max_length=5, description="Deep research requests (1..5)"
    )
    mode: Literal["serial"] = Field(default="serial", description="Execution mode")
    inter_call_delay_s: float = Field(
        default=15.0, ge=0.0, le=120.0, description="Delay between calls in seconds"
    )
    on_error: Literal["continue", "abort", "retry_backoff"] = Field(
        default="retry_backoff", description="Behavior when a request returns a typed error"
    )


class ArxivSearchRequest(BaseModel):
    """Request for an arXiv search."""

    query: str = Field(..., description="Search query")
    categories: list[str] | None = Field(
        default=None, description="arXiv categories to AND with the query"
    )
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum papers to return")
    sort_by: Literal["relevance", "lastUpdatedDate", "submittedDate"] = Field(
        default="relevance", description="arXiv sort order"
    )
    full_metadata: bool = Field(
        default=False, description="Include all optional fields (comment, categories, ...)"
    )


class PaperFetchRequest(BaseModel):
    """Request to fetch the content of a paper or web page."""

    source: str = Field(..., description="arXiv URL/id or a generic URL")
    sections: list[str] | None = Field(
        default=None, description="Section headings to extract (case-insensitive)"
    )
    extract_numbers: bool = Field(
        default=False, description="Extract numeric tokens with sentence context"
    )


# ============================================================================
# Response Models
# ============================================================================


class SearchResult(BaseModel):
    """Single search result."""

    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    snippet: str = Field(..., description="Result snippet/description")
    score: float | None = Field(default=None, description="Relevance score when provided")
    source_type: str | None = Field(default=None, description="Classified source type")


class WebSearchResult(BaseModel):
    """Result of web search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    query: str = Field(..., description="Original query")
    results: list[SearchResult] = Field(default_factory=list, description="Search results")
    provider: str = Field(..., description="Search provider used")
    error_message: str = Field(default="", description="Error message if failed")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class ResearchResult(BaseModel):
    """Result of deep research."""

    status: Literal["ok", "partial", "error"] = Field(..., description="Research status")
    topic: str = Field(..., description="Research topic")
    sources_found: int = Field(..., description="Number of sources found")
    sources: list[dict] = Field(default_factory=list, description="Source documents")
    summary: str = Field(..., description="Brief summary of findings")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class DeepResearchBatchResult(BaseModel):
    """Result of a serial deep-research batch."""

    status: Literal["ok", "partial", "aborted", "timeout", "error"] = Field(
        ..., description="Batch status"
    )
    total: int = Field(..., description="Number of requests in the batch")
    completed: int = Field(..., description="Number of requests that produced a result")
    results: list[ResearchResult] = Field(
        default_factory=list, description="Per-request research results"
    )
    error: ErrorInfo | None = Field(default=None, description="Structured batch error, if any")


class ReportResult(BaseModel):
    """Result of report generation."""

    status: Literal["ok", "error"] = Field(..., description="Generation status")
    report: str = Field(..., description="Generated report (markdown format)")
    sources_used: int = Field(..., description="Number of sources used")
    word_count: int = Field(..., description="Report word count")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class FactCheckResult(BaseModel):
    """Result of fact checking."""

    status: Literal["verified", "disputed", "uncertain", "error"] = Field(
        ..., description="Verification status"
    )
    claim: str = Field(..., description="Original claim")
    verdict: str = Field(..., description="Verdict explanation")
    sources: list[str] = Field(default_factory=list, description="Sources consulted")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class SourceSummary(BaseModel):
    """Per-source summarization outcome."""

    url: str = Field(..., description="Source URL")
    status: Literal["ok", "error"] = Field(..., description="Per-source status")
    summary: str = Field(default="", description="Extracted summary text")
    word_count: int = Field(default=0, description="Word count of the fetched source")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class SummaryResult(BaseModel):
    """Result of source summarization."""

    status: Literal["ok", "partial", "error"] = Field(..., description="Summarization status")
    summaries: list[dict[str, Any]] = Field(
        default_factory=list, description="Per-source summaries with URLs"
    )
    combined_summary: str = Field(default="", description="Combined summary of all sources")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class ArxivPaper(BaseModel):
    """A single arXiv paper entry."""

    id: str = Field(..., description="Version-less arXiv identifier (e.g. '2401.12345')")
    title: str = Field(..., description="Paper title")
    authors: list[str] = Field(default_factory=list, description="Author names")
    abstract: str = Field(default="", description="Paper abstract")
    url: str = Field(..., description="Canonical arXiv abstract URL")
    published: str = Field(default="", description="First submission timestamp")
    updated: str = Field(default="", description="Latest update timestamp")
    categories: list[str] = Field(default_factory=list, description="All category terms")
    primary_category: str = Field(default="", description="Primary category term")
    comment: str | None = Field(default=None, description="arXiv comment field, if any")


class ArxivSearchResult(BaseModel):
    """Result of an arXiv search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    query: str = Field(..., description="Original query")
    papers: list[dict[str, Any]] = Field(default_factory=list, description="Matching papers")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class ExtractedNumber(BaseModel):
    """A numeric token found in a document, with sentence context."""

    value: str = Field(..., description="The numeric token as text")
    context: str = Field(..., description="Sentence containing the token")
    section: str = Field(default="", description="Section the token was found in")


class PaperContent(BaseModel):
    """Extracted content of a paper or web page."""

    source: str = Field(..., description="Original source string")
    arxiv_id: str | None = Field(default=None, description="Normalized arXiv id, if any")
    title: str = Field(default="", description="Document title")
    abstract: str = Field(default="", description="Abstract / meta description")
    sections: dict[str, str] = Field(default_factory=dict, description="Requested section texts")
    numbers: list[ExtractedNumber] = Field(
        default_factory=list, description="Extracted numeric tokens"
    )
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")


class PaperFetchResult(BaseModel):
    """Result wrapper for paper fetching."""

    status: Literal["ok", "error"] = Field(..., description="Fetch status")
    paper: PaperContent | None = Field(default=None, description="Extracted paper content")
    error: ErrorInfo | None = Field(default=None, description="Structured error, if any")
