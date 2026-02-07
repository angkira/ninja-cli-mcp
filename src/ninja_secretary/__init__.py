"""
Ninja Secretary MCP Module.

Provides codebase exploration, documentation, and session tracking capabilities.
"""

__version__ = "0.2.0"

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
