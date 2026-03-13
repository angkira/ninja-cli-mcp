"""Ninja Researcher - Web search and report generation module for Ninja MCP."""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

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
