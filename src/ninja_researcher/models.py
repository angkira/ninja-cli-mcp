"""
Pydantic models for Ninja Researcher MCP tools.

These models define the API surface for the researcher module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================


class WebSearchRequest(BaseModel):
    """Request for web search."""

    query: str = Field(..., description="Search query")
    max_results: int = Field(default=10, ge=1, le=50, description="Maximum number of results")
    search_provider: str = Field(
        default="duckduckgo",
        description="Search provider to use (duckduckgo, serper)",
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


# ============================================================================
# Response Models
# ============================================================================


class SearchResult(BaseModel):
    """Single search result."""

    title: str = Field(..., description="Result title")
    url: str = Field(..., description="Result URL")
    snippet: str = Field(..., description="Result snippet/description")
    score: float = Field(default=0.0, description="Relevance score")


class WebSearchResult(BaseModel):
    """Result of web search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    query: str = Field(..., description="Original query")
    results: list[SearchResult] = Field(default_factory=list, description="Search results")
    provider: str = Field(..., description="Search provider used")
    error_message: str = Field(default="", description="Error message if failed")


class ResearchResult(BaseModel):
    """Result of deep research."""

    status: Literal["ok", "partial", "error"] = Field(..., description="Research status")
    topic: str = Field(..., description="Research topic")
    sources_found: int = Field(..., description="Number of sources found")
    sources: list[dict] = Field(default_factory=list, description="Source documents")
    summary: str = Field(..., description="Brief summary of findings")


class ReportResult(BaseModel):
    """Result of report generation."""

    status: Literal["ok", "error"] = Field(..., description="Generation status")
    report: str = Field(..., description="Generated report (markdown format)")
    sources_used: int = Field(..., description="Number of sources used")
    word_count: int = Field(..., description="Report word count")


class FactCheckResult(BaseModel):
    """Result of fact checking."""

    status: Literal["verified", "disputed", "uncertain", "error"] = Field(
        ..., description="Verification status"
    )
    claim: str = Field(..., description="Original claim")
    verdict: str = Field(..., description="Verdict explanation")
    sources: list[str] = Field(default_factory=list, description="Sources consulted")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Confidence score")


class SummaryResult(BaseModel):
    """Result of source summarization."""

    status: Literal["ok", "partial", "error"] = Field(..., description="Summarization status")
    summaries: list[dict] = Field(
        default_factory=list, description="Per-source summaries with URLs"
    )
    combined_summary: str = Field(default="", description="Combined summary of all sources")
