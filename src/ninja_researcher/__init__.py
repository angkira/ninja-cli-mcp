"""Ninja Researcher - Web search and report generation module for Ninja MCP."""

__version__ = "0.2.0"

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

__all__ = [
    "DeepResearchRequest",
    "FactCheckRequest",
    "FactCheckResult",
    "GenerateReportRequest",
    "ReportResult",
    "ResearchResult",
    "SearchResult",
    "SummarizeSourcesRequest",
    "SummaryResult",
    "WebSearchRequest",
    "WebSearchResult",
]
