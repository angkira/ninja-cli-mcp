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


class ReadFileRequest(BaseModel):
    """Request to read a file from the codebase."""

    file_path: str = Field(..., description="Path to file to read (relative to repo root)")
    start_line: int | None = Field(default=None, description="Start line (1-indexed, optional)")
    end_line: int | None = Field(default=None, description="End line (1-indexed, optional)")


class FileSearchRequest(BaseModel):
    """Request to search for files matching a pattern."""

    pattern: str = Field(..., description="Glob pattern to match files (e.g., '**/*.py')")
    repo_root: str = Field(..., description="Repository root path")
    max_results: int = Field(default=100, ge=1, le=1000, description="Maximum results")


class GrepRequest(BaseModel):
    """Request to grep for content in files."""

    pattern: str = Field(..., description="Regex pattern to search for")
    repo_root: str = Field(..., description="Repository root path")
    file_pattern: str | None = Field(default=None, description="Glob pattern to filter files")
    context_lines: int = Field(default=2, ge=0, le=10, description="Lines of context")
    max_results: int = Field(default=100, ge=1, le=1000, description="Maximum results")


class FileTreeRequest(BaseModel):
    """Request to generate a file tree with details."""

    repo_root: str = Field(..., description="Repository root path")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum directory depth")
    include_sizes: bool = Field(default=True, description="Include file sizes")
    include_git_status: bool = Field(default=False, description="Include git status")


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
    files: list[str] = Field(default_factory=list, description="Specific files to commit (empty = all staged)")
    author: str | None = Field(default=None, description="Override author")


class GitLogRequest(BaseModel):
    """Request to get git commit history."""

    repo_root: str = Field(..., description="Repository root path")
    max_count: int = Field(default=10, ge=1, le=1000, description="Number of commits to show")
    file_path: str | None = Field(default=None, description="Filter by file")


class SmartCommitRequest(BaseModel):
    """Request to intelligently group and commit changes."""

    repo_root: str = Field(..., description="Repository root path")
    include_untracked: bool = Field(default=False, description="Include untracked files in analysis")
    dry_run: bool = Field(default=False, description="If True, only analyze and suggest, don't actually commit")
    author: str | None = Field(default=None, description="Override commit author")


# ============================================================================
# Response Models
# ============================================================================


class ReadFileResult(BaseModel):
    """Result of reading a file."""

    status: Literal["ok", "error"] = Field(..., description="Operation status")
    file_path: str = Field(..., description="File path that was read")
    content: str = Field(default="", description="File content")
    line_count: int = Field(default=0, description="Total line count")
    error_message: str = Field(default="", description="Error message if failed")


class FileMatch(BaseModel):
    """A file that matches a search pattern."""

    path: str = Field(..., description="Relative file path")
    size: int = Field(default=0, description="File size in bytes")
    modified: str = Field(default="", description="Last modified timestamp")


class FileSearchResult(BaseModel):
    """Result of file search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    matches: list[FileMatch] = Field(default_factory=list, description="Matching files")
    total_count: int = Field(..., description="Total matches found")
    truncated: bool = Field(default=False, description="Results truncated to max_results")


class GrepMatch(BaseModel):
    """A grep match."""

    file_path: str = Field(..., description="File containing match")
    line_number: int = Field(..., description="Line number of match")
    line_content: str = Field(..., description="Content of matching line")
    context_before: list[str] = Field(default_factory=list, description="Lines before match")
    context_after: list[str] = Field(default_factory=list, description="Lines after match")


class GrepResult(BaseModel):
    """Result of grep search."""

    status: Literal["ok", "error"] = Field(..., description="Search status")
    pattern: str = Field(..., description="Pattern that was searched")
    matches: list[GrepMatch] = Field(default_factory=list, description="Matches found")
    total_count: int = Field(..., description="Total matches")
    truncated: bool = Field(default=False, description="Results truncated")


class FileTreeNode(BaseModel):
    """Node in file tree."""

    name: str = Field(..., description="File/directory name")
    path: str = Field(..., description="Relative path")
    type: Literal["file", "directory"] = Field(..., description="Node type")
    size: int | None = Field(default=None, description="Size in bytes (files only)")
    children: list[FileTreeNode] = Field(default_factory=list, description="Child nodes")
    git_status: str | None = Field(default=None, description="Git status if requested")


class FileTreeResult(BaseModel):
    """Result of file tree generation."""

    status: Literal["ok", "error"] = Field(..., description="Generation status")
    tree: FileTreeNode | None = Field(default=None, description="Root tree node")
    total_files: int = Field(default=0, description="Total files")
    total_dirs: int = Field(default=0, description="Total directories")
    total_size: int = Field(default=0, description="Total size in bytes")


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
    suggestions: list[CommitSuggestion] = Field(default_factory=list, description="Suggested/created commits")
    commits_created: int = Field(default=0, description="Number of commits actually created (0 if dry_run)")
    error_message: str = Field(default="", description="Error message if failed")
