"""
Pydantic models for Ninja Secretary MCP tools.

These models define the API surface for the secretary module.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# ============================================================================
# Request Models
# ============================================================================


class AnalyseFileRequest(BaseModel):
    """Request to analyse a file."""

    file_path: str = Field(..., description="Path to file (relative to repo root)")
    search_pattern: str | None = Field(
        None, description="Optional regex pattern to search within the file"
    )
    include_structure: bool = Field(default=True, description="Include file structure analysis")
    include_preview: bool = Field(default=True, description="Include content preview")


class FileSearchRequest(BaseModel):
    """Request to search for files matching a pattern."""

    pattern: str = Field(..., description="Glob pattern to match files (e.g., '**/*.py')")
    repo_root: str = Field(..., description="Repository root path")
    max_results: int = Field(default=100, ge=1, le=1000, description="Maximum results")


class CodebaseReportRequest(BaseModel):
    """Request to generate a codebase analysis report."""

    repo_root: str = Field(..., description="Repository root path")
    include_metrics: bool = Field(default=True, description="Include code metrics")
    include_dependencies: bool = Field(default=True, description="Include dependency analysis")
    include_structure: bool = Field(default=True, description="Include project structure")


class DocumentSummaryRequest(BaseModel):
    """Request to summarize documentation files."""

    repo_root: str = Field(..., description="Repository root path")
    doc_patterns: list[str] = Field(
        default=["**/*.md", "**/README*", "**/CONTRIBUTING*"],
        description="Patterns to match documentation files",
    )


class SessionReportRequest(BaseModel):
    """Request to get or update session report."""

    session_id: str = Field(..., description="Session identifier")
    action: Literal["get", "update", "create"] = Field(
        default="get", description="Action to perform"
    )
    updates: dict | None = Field(default=None, description="Updates to apply (for update action)")


class UpdateDocRequest(BaseModel):
    """Request to update module documentation."""

    module_name: str = Field(..., description="Module name (coder, researcher, secretary)")
    doc_type: Literal["readme", "api", "changelog"] = Field(
        ..., description="Type of documentation to update"
    )
    content: str = Field(..., description="New content or updates")
    mode: Literal["replace", "append", "prepend"] = Field(
        default="replace", description="Update mode"
    )


class GitStatusRequest(BaseModel):
    """Request to get git repository status."""

    repo_root: str = Field(..., description="Repository root path")
    include_untracked: bool = Field(default=True, description="Include untracked files")


class GitDiffRequest(BaseModel):
    """Request to get git diff."""

    repo_root: str = Field(..., description="Repository root path")
    staged: bool = Field(default=False, description="Show staged changes vs unstaged")
    file_path: str | None = Field(default=None, description="Specific file to diff")


class GitCommitRequest(BaseModel):
    """Request to create a git commit."""

    repo_root: str = Field(..., description="Repository root path")
    message: str = Field(..., description="Commit message")
    files: list[str] = Field(
        default_factory=list, description="Specific files to commit (empty = all staged)"
    )
    author: str | None = Field(default=None, description="Override author")


class GitLogRequest(BaseModel):
    """Request to get git commit history."""

    repo_root: str = Field(..., description="Repository root path")
    max_count: int = Field(default=10, ge=1, le=1000, description="Number of commits to show")
    file_path: str | None = Field(default=None, description="Filter by file")


class SmartCommitRequest(BaseModel):
    """Request to intelligently group and commit changes."""

    repo_root: str = Field(..., description="Repository root path")
    include_untracked: bool = Field(
        default=False, description="Include untracked files in analysis"
    )
    dry_run: bool = Field(
        default=False, description="If True, only analyze and suggest, don't actually commit"
    )
    author: str | None = Field(default=None, description="Override commit author")


# ============================================================================
# Response Models
# ============================================================================


class AnalyseFileResult(BaseModel):
    """Result of file analysis."""

    status: Literal["ok", "error"]
    message: str = Field(default="")
    result: dict = Field(
        default_factory=dict
    )  # Contains: file, language, lines_total, structure, preview, search_results


class FileSearchResult(BaseModel):
    """Result of file search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    matches: list[FileMatch] = Field(default_factory=list, description="Matching files")
    total_count: int = Field(..., description="Total matches found")
    truncated: bool = Field(default=False, description="Results truncated to max_results")


class FileMatch(BaseModel):
    """A file that matches a search pattern."""

    path: str = Field(..., description="Relative file path")
    size: int = Field(default=0, description="File size in bytes")
    modified: str = Field(default="", description="Last modified timestamp")


class CodebaseReportResult(BaseModel):
    """Result of codebase analysis."""

    status: Literal["ok", "error"] = Field(..., description="Analysis status")
    report: str = Field(..., description="Markdown report")
    metrics: dict = Field(default_factory=dict, description="Code metrics")
    file_count: int = Field(default=0, description="Total files analyzed")


class DocumentSummaryResult(BaseModel):
    """Result of documentation summary."""

    status: Literal["ok", "error"] = Field(..., description="Summary status")
    summaries: list[dict] = Field(default_factory=list, description="Per-document summaries")
    combined_summary: str = Field(default="", description="Combined summary")
    doc_count: int = Field(default=0, description="Documents summarized")


class SessionReport(BaseModel):
    """Session tracking report."""

    session_id: str = Field(..., description="Session identifier")
    started_at: str = Field(..., description="Session start time")
    last_updated: str = Field(..., description="Last update time")
    tools_used: list[str] = Field(default_factory=list, description="Tools called in session")
    files_accessed: list[str] = Field(default_factory=list, description="Files read/written")
    summary: str = Field(default="", description="Session summary")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class UpdateDocResult(BaseModel):
    """Result of documentation update."""

    status: Literal["ok", "error"] = Field(..., description="Update status")
    doc_path: str = Field(..., description="Path to updated documentation")
    changes_made: str = Field(default="", description="Description of changes")


class GitStatusResult(BaseModel):
    """Result of git status query."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    branch: str = Field(..., description="Current branch name")
    staged: list[str] = Field(default_factory=list, description="Staged files")
    unstaged: list[str] = Field(default_factory=list, description="Modified but unstaged files")
    untracked: list[str] = Field(default_factory=list, description="Untracked files")
    ahead: int = Field(default=0, description="Commits ahead of remote")
    behind: int = Field(default=0, description="Commits behind remote")
    error_message: str = Field(default="", description="Error message if failed")


class GitDiffResult(BaseModel):
    """Result of git diff."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    diff: str = Field(..., description="The diff output")
    files_changed: int = Field(default=0, description="Number of files changed")
    insertions: int = Field(default=0, description="Number of insertions")
    deletions: int = Field(default=0, description="Number of deletions")
    error_message: str = Field(default="", description="Error message if failed")


class GitCommitResult(BaseModel):
    """Result of git commit."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    commit_hash: str = Field(default="", description="The new commit hash")
    message: str = Field(default="", description="Commit message used")
    files_committed: list[str] = Field(default_factory=list, description="Files committed")
    error_message: str = Field(default="", description="Error message if failed")


class GitLogEntry(BaseModel):
    """A single entry in git commit history."""

    hash: str = Field(..., description="Commit hash (short)")
    author: str = Field(..., description="Author name")
    date: str = Field(..., description="Commit date")
    message: str = Field(..., description="Commit message (first line)")


class GitLogResult(BaseModel):
    """Result of git log query."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    commits: list[GitLogEntry] = Field(default_factory=list, description="Commit history")
    error_message: str = Field(default="", description="Error message if failed")


class CommitSuggestion(BaseModel):
    """A suggested commit grouping."""

    files: list[str] = Field(..., description="Files to include in this commit")
    message: str = Field(..., description="Suggested commit message")
    reasoning: str = Field(..., description="Why these files are grouped together")


class SmartCommitResult(BaseModel):
    """Result of smart commit operation."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    suggestions: list[CommitSuggestion] = Field(
        default_factory=list, description="Suggested/created commits"
    )
    commits_created: int = Field(
        default=0, description="Number of commits actually created (0 if dry_run)"
    )
    error_message: str = Field(default="", description="Error message if failed")
