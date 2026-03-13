"""
Ninja Secretary MCP Module.

Provides codebase exploration, documentation, and session tracking capabilities.
"""

from importlib.metadata import PackageNotFoundError, version


try:
    __version__ = version("ninja-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0-dev"

from ninja_secretary.models import (
    AnalyseFileRequest,
    AnalyseFileResult,
    CodebaseReportRequest,
    CodebaseReportResult,
    DocumentSummaryRequest,
    DocumentSummaryResult,
    FileSearchRequest,
    FileSearchResult,
    SessionReport,
    SessionReportRequest,
    UpdateDocRequest,
    UpdateDocResult,
)


__all__ = [
    "AnalyseFileRequest",
    "AnalyseFileResult",
    "CodebaseReportRequest",
    "CodebaseReportResult",
    "DocumentSummaryRequest",
    "DocumentSummaryResult",
    "FileSearchRequest",
    "FileSearchResult",
    "SessionReport",
    "SessionReportRequest",
    "UpdateDocRequest",
    "UpdateDocResult",
]
