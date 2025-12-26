"""
MCP tool implementations for the Secretary module.

This module contains the business logic for all secretary-related MCP tools.
"""

from __future__ import annotations

import datetime
import re
from pathlib import Path

from ninja_common.logging_utils import get_logger
from ninja_common.rate_balancer import rate_balanced
from ninja_common.security import monitored
from ninja_secretary.models import (
    CodebaseReportRequest,
    CodebaseReportResult,
    DocumentSummaryRequest,
    DocumentSummaryResult,
    FileMatch,
    FileSearchRequest,
    FileSearchResult,
    FileTreeNode,
    FileTreeRequest,
    FileTreeResult,
    GrepMatch,
    GrepRequest,
    GrepResult,
    ReadFileRequest,
    ReadFileResult,
    SessionReport,
    SessionReportRequest,
    UpdateDocRequest,
    UpdateDocResult,
)


logger = get_logger(__name__)


class SecretaryToolExecutor:
    """Executor for secretary MCP tools."""

    def __init__(self):
        """Initialize the secretary tool executor."""
        self.sessions: dict[str, SessionReport] = {}

    @rate_balanced(max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0)
    @monitored
    async def read_file(
        self, request: ReadFileRequest, client_id: str = "default"
    ) -> ReadFileResult:
        """
        Read a file from the codebase.

        Args:
            request: Read file request.
            client_id: Client identifier for rate limiting.

        Returns:
            Read file result with content.
        """
        logger.info(f"Reading file '{request.file_path}' (client: {client_id})")

        try:
            file_path = Path(request.file_path)

            if not file_path.exists():
                return ReadFileResult(
                    status="error",
                    file_path=request.file_path,
                    error_message=f"File not found: {request.file_path}",
                )

            if not file_path.is_file():
                return ReadFileResult(
                    status="error",
                    file_path=request.file_path,
                    error_message=f"Not a file: {request.file_path}",
                )

            # Read file content
            with file_path.open(encoding='utf-8', errors='replace') as f:
                lines = f.readlines()

            total_lines = len(lines)

            # Apply line range if specified
            if request.start_line is not None or request.end_line is not None:
                start = (request.start_line or 1) - 1  # Convert to 0-indexed
                end = request.end_line if request.end_line else total_lines
                lines = lines[start:end]

            content = ''.join(lines)

            # Track file access
            await self._track_file_access(client_id, request.file_path)

            return ReadFileResult(
                status="ok",
                file_path=request.file_path,
                content=content,
                line_count=total_lines,
            )

        except UnicodeDecodeError:
            return ReadFileResult(
                status="error",
                file_path=request.file_path,
                error_message="File is not a text file (binary content)",
            )
        except Exception as e:
            logger.error(f"Failed to read file {request.file_path}: {e}")
            return ReadFileResult(
                status="error",
                file_path=request.file_path,
                error_message=str(e),
            )

    @rate_balanced(max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0)
    @monitored
    async def file_search(
        self, request: FileSearchRequest, client_id: str = "default"
    ) -> FileSearchResult:
        """
        Search for files matching a pattern.

        Args:
            request: File search request.
            client_id: Client identifier for rate limiting.

        Returns:
            File search result with matching files.
        """
        logger.info(f"Searching files with pattern '{request.pattern}' (client: {client_id})")

        try:
            repo_root = Path(request.repo_root)

            if not repo_root.exists():
                return FileSearchResult(
                    status="error",
                    matches=[],
                    total_count=0,
                    error_message=f"Repository root not found: {request.repo_root}",
                )

            # Use glob to find matching files
            matches: list[FileMatch] = []

            for path in repo_root.glob(request.pattern):
                if path.is_file():
                    stat = path.stat()
                    rel_path = str(path.relative_to(repo_root))

                    matches.append(
                        FileMatch(
                            path=rel_path,
                            size=stat.st_size,
                            modified=datetime.datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        )
                    )

                    if len(matches) >= request.max_results:
                        break

            # Sort by path
            matches.sort(key=lambda m: m.path)

            truncated = len(matches) >= request.max_results

            return FileSearchResult(
                status="ok",
                matches=matches,
                total_count=len(matches),
                truncated=truncated,
            )

        except Exception as e:
            logger.error(f"File search failed for client {client_id}: {e}")
            return FileSearchResult(
                status="error",
                matches=[],
                total_count=0,
                error_message=str(e),
            )

    @rate_balanced(max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0)
    @monitored
    async def grep(
        self, request: GrepRequest, client_id: str = "default"
    ) -> GrepResult:
        """
        Grep for content in files.

        Args:
            request: Grep request.
            client_id: Client identifier for rate limiting.

        Returns:
            Grep result with matches.
        """
        logger.info(f"Grepping for pattern '{request.pattern}' (client: {client_id})")

        try:
            repo_root = Path(request.repo_root)
            pattern = re.compile(request.pattern)
            matches: list[GrepMatch] = []

            # Determine which files to search
            file_pattern = request.file_pattern or "**/*"
            files_to_search = []

            for path in repo_root.glob(file_pattern):
                if path.is_file():
                    files_to_search.append(path)

            # Search each file
            for file_path in files_to_search:
                if len(matches) >= request.max_results:
                    break

                try:
                    with file_path.open(encoding='utf-8', errors='replace') as f:
                        lines = f.readlines()

                    for line_num, line in enumerate(lines, 1):
                        if pattern.search(line):
                            # Get context
                            context_before = []
                            context_after = []

                            if request.context_lines > 0:
                                start_idx = max(0, line_num - 1 - request.context_lines)
                                end_idx = min(len(lines), line_num + request.context_lines)

                                context_before = [
                                    line.rstrip() for line in lines[start_idx : line_num - 1]
                                ]
                                context_after = [line.rstrip() for line in lines[line_num:end_idx]]

                            rel_path = str(file_path.relative_to(repo_root))

                            matches.append(
                                GrepMatch(
                                    file_path=rel_path,
                                    line_number=line_num,
                                    line_content=line.rstrip(),
                                    context_before=context_before,
                                    context_after=context_after,
                                )
                            )

                            if len(matches) >= request.max_results:
                                break

                except (UnicodeDecodeError, PermissionError):
                    # Skip binary files or files we can't read
                    continue

            truncated = len(matches) >= request.max_results

            return GrepResult(
                status="ok",
                pattern=request.pattern,
                matches=matches,
                total_count=len(matches),
                truncated=truncated,
            )

        except Exception as e:
            logger.error(f"Grep failed for client {client_id}: {e}")
            return GrepResult(
                status="error",
                pattern=request.pattern,
                matches=[],
                total_count=0,
                error_message=str(e),
            )

    @rate_balanced(max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0)
    @monitored
    async def file_tree(
        self, request: FileTreeRequest, client_id: str = "default"
    ) -> FileTreeResult:
        """
        Generate a file tree with details.

        Args:
            request: File tree request.
            client_id: Client identifier for rate limiting.

        Returns:
            File tree result.
        """
        logger.info(f"Generating file tree for '{request.repo_root}' (client: {client_id})")

        try:
            repo_root = Path(request.repo_root)

            if not repo_root.exists():
                return FileTreeResult(
                    status="error",
                    error_message=f"Repository root not found: {request.repo_root}",
                )

            total_files = 0
            total_dirs = 0
            total_size = 0

            def build_tree(path: Path, current_depth: int = 0) -> FileTreeNode | None:
                """Recursively build file tree."""
                nonlocal total_files, total_dirs, total_size

                if current_depth >= request.max_depth:
                    return None

                # Skip hidden files and common ignored directories
                if path.name.startswith('.') or path.name in ['node_modules', '__pycache__', 'venv', '.git']:
                    return None

                rel_path = str(path.relative_to(repo_root))

                if path.is_file():
                    total_files += 1
                    size = path.stat().st_size if request.include_sizes else None
                    if size:
                        total_size += size

                    return FileTreeNode(
                        name=path.name,
                        path=rel_path,
                        type="file",
                        size=size,
                    )
                else:
                    total_dirs += 1
                    children = []

                    try:
                        for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name)):
                            child_node = build_tree(child, current_depth + 1)
                            if child_node:
                                children.append(child_node)
                    except PermissionError:
                        pass

                    return FileTreeNode(
                        name=path.name,
                        path=rel_path,
                        type="directory",
                        children=children,
                    )

            root_node = build_tree(repo_root)

            return FileTreeResult(
                status="ok",
                tree=root_node,
                total_files=total_files,
                total_dirs=total_dirs,
                total_size=total_size,
            )

        except Exception as e:
            logger.error(f"File tree generation failed for client {client_id}: {e}")
            return FileTreeResult(
                status="error",
                error_message=str(e),
            )

    @rate_balanced(max_calls=5, time_window=60, max_retries=3, initial_backoff=2.0, max_backoff=60.0)
    @monitored
    async def codebase_report(  # noqa: PLR0912, PLR0915
        self, request: CodebaseReportRequest, client_id: str = "default"
    ) -> CodebaseReportResult:
        """
        Generate a codebase analysis report.

        Args:
            request: Codebase report request.
            client_id: Client identifier for rate limiting.

        Returns:
            Codebase report result.
        """
        logger.info(f"Generating codebase report for '{request.repo_root}' (client: {client_id})")

        try:
            repo_root = Path(request.repo_root)
            metrics = {}
            report_parts = []

            report_parts.append(f"# Codebase Report: {repo_root.name}\n\n")
            report_parts.append(f"**Generated:** {datetime.datetime.now().isoformat()}\n\n")

            # File structure analysis
            if request.include_structure:
                tree_request = FileTreeRequest(repo_root=request.repo_root, max_depth=3)
                tree_result = await self.file_tree(tree_request, client_id)

                if tree_result.status == "ok":
                    report_parts.append("## Project Structure\n\n")
                    report_parts.append(f"- **Total Files:** {tree_result.total_files}\n")
                    report_parts.append(f"- **Total Directories:** {tree_result.total_dirs}\n")
                    report_parts.append(
                        f"- **Total Size:** {tree_result.total_size / 1024 / 1024:.2f} MB\n\n"
                    )

                    metrics["file_count"] = tree_result.total_files
                    metrics["dir_count"] = tree_result.total_dirs
                    metrics["total_size_mb"] = tree_result.total_size / 1024 / 1024

            # Code metrics
            if request.include_metrics:
                report_parts.append("## Code Metrics\n\n")

                # Count files by extension
                extensions: dict[str, int] = {}
                total_lines = 0

                for path in repo_root.rglob("*"):
                    if path.is_file() and not any(
                        p in path.parts for p in ['.git', 'node_modules', '__pycache__', 'venv']
                    ):
                        ext = path.suffix or "no_extension"
                        extensions[ext] = extensions.get(ext, 0) + 1

                        # Count lines for text files
                        if ext in ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs']:
                            try:
                                with path.open(encoding='utf-8', errors='replace') as f:
                                    total_lines += sum(1 for _ in f)
                            except Exception:
                                pass

                report_parts.append(f"- **Total Lines of Code:** ~{total_lines:,}\n")
                report_parts.append("\n### Files by Extension\n\n")

                for ext, count in sorted(extensions.items(), key=lambda x: x[1], reverse=True)[:10]:
                    report_parts.append(f"- `{ext}`: {count} files\n")

                metrics["total_lines"] = total_lines
                metrics["extensions"] = extensions

            # Dependencies analysis
            if request.include_dependencies:
                report_parts.append("\n## Dependencies\n\n")

                # Check for common dependency files
                dep_files = {
                    "requirements.txt": "Python (pip)",
                    "pyproject.toml": "Python (modern)",
                    "package.json": "Node.js",
                    "Cargo.toml": "Rust",
                    "go.mod": "Go",
                    "pom.xml": "Java (Maven)",
                    "build.gradle": "Java (Gradle)",
                }

                found_deps = []
                for dep_file, lang in dep_files.items():
                    if (repo_root / dep_file).exists():
                        found_deps.append(f"- **{lang}**: `{dep_file}` found")

                if found_deps:
                    report_parts.extend(found_deps)
                else:
                    report_parts.append("*No common dependency files found*\n")

                metrics["dependencies"] = found_deps

            report = ''.join(report_parts)

            return CodebaseReportResult(
                status="ok",
                report=report,
                metrics=metrics,
                file_count=metrics.get("file_count", 0),
            )

        except Exception as e:
            logger.error(f"Codebase report failed for client {client_id}: {e}")
            return CodebaseReportResult(
                status="error",
                report=f"Report generation failed: {e}",
                metrics={},
                file_count=0,
            )

    @rate_balanced(max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0)
    @monitored
    async def document_summary(
        self, request: DocumentSummaryRequest, client_id: str = "default"
    ) -> DocumentSummaryResult:
        """
        Summarize documentation files.

        Args:
            request: Document summary request.
            client_id: Client identifier for rate limiting.

        Returns:
            Document summary result.
        """
        logger.info(f"Summarizing documents in '{request.repo_root}' (client: {client_id})")

        try:
            repo_root = Path(request.repo_root)
            summaries = []

            for pattern in request.doc_patterns:
                for doc_path in repo_root.glob(pattern):
                    if doc_path.is_file():
                        try:
                            with doc_path.open(encoding='utf-8', errors='replace') as f:
                                content = f.read()

                            # Extract first paragraph or first 500 chars as summary
                            lines = content.split('\n')
                            summary_lines = []
                            for line in lines:
                                if line.strip():
                                    summary_lines.append(line.strip())
                                    if len(' '.join(summary_lines)) > 500:
                                        break
                                elif summary_lines:  # Stop at first empty line after content
                                    break

                            summary = ' '.join(summary_lines)[:500]

                            rel_path = str(doc_path.relative_to(repo_root))
                            summaries.append(
                                {
                                    "path": rel_path,
                                    "title": doc_path.name,
                                    "summary": summary,
                                    "size": len(content),
                                }
                            )

                        except Exception as e:
                            logger.warning(f"Failed to read {doc_path}: {e}")
                            continue

            # Create combined summary
            combined_parts = []
            for s in summaries:
                combined_parts.append(f"**{s['path']}**: {s['summary'][:200]}")

            combined_summary = '\n\n'.join(combined_parts)

            return DocumentSummaryResult(
                status="ok",
                summaries=summaries,
                combined_summary=combined_summary,
                doc_count=len(summaries),
            )

        except Exception as e:
            logger.error(f"Document summary failed for client {client_id}: {e}")
            return DocumentSummaryResult(
                status="error",
                summaries=[],
                combined_summary=f"Summary failed: {e}",
                doc_count=0,
            )

    async def session_report(
        self, request: SessionReportRequest, client_id: str = "default"  # noqa: ARG002
    ) -> SessionReport:
        """
        Get or update session report.

        Args:
            request: Session report request.
            client_id: Client identifier.

        Returns:
            Session report.
        """
        session_id = request.session_id

        if request.action == "create":
            # Create new session
            now = datetime.datetime.now().isoformat()

            # Extract metadata from updates if provided
            metadata = {}
            if request.updates and "metadata" in request.updates:
                metadata = request.updates["metadata"]

            session = SessionReport(
                session_id=session_id,
                started_at=now,
                last_updated=now,
                tools_used=[],
                files_accessed=[],
                summary="Session started",
                metadata=metadata,
            )
            self.sessions[session_id] = session
            return session

        elif request.action == "get":
            # Get existing session
            return self.sessions.get(
                session_id,
                SessionReport(
                    session_id=session_id,
                    started_at=datetime.datetime.now().isoformat(),
                    last_updated=datetime.datetime.now().isoformat(),
                    summary="No session data",
                ),
            )

        else:  # update
            # Update session
            session = self.sessions.get(session_id)
            if not session:
                # Create if doesn't exist
                now = datetime.datetime.now().isoformat()
                session = SessionReport(
                    session_id=session_id,
                    started_at=now,
                    last_updated=now,
                )
                self.sessions[session_id] = session

            # Apply updates
            if request.updates:
                session.last_updated = datetime.datetime.now().isoformat()
                if "tools_used" in request.updates:
                    session.tools_used.extend(request.updates["tools_used"])
                if "files_accessed" in request.updates:
                    session.files_accessed.extend(request.updates["files_accessed"])
                if "summary" in request.updates:
                    session.summary = request.updates["summary"]
                if "metadata" in request.updates:
                    session.metadata.update(request.updates["metadata"])

            return session

    async def update_doc(
        self, request: UpdateDocRequest, client_id: str = "default"
    ) -> UpdateDocResult:
        """
        Update module documentation.

        Args:
            request: Update doc request.
            client_id: Client identifier.

        Returns:
            Update result.
        """
        logger.info(
            f"Updating {request.doc_type} for module {request.module_name} (client: {client_id})"
        )

        try:
            # Determine doc path
            doc_paths = {
                "readme": f"docs/{request.module_name}/README.md",
                "api": f"docs/{request.module_name}/API.md",
                "changelog": f"docs/{request.module_name}/CHANGELOG.md",
            }

            doc_path = doc_paths.get(request.doc_type)
            if not doc_path:
                return UpdateDocResult(
                    status="error",
                    doc_path="",
                    changes_made=f"Unknown doc type: {request.doc_type}",
                )

            full_path = Path(doc_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Read existing content
            existing_content = ""
            if full_path.exists():
                with full_path.open(encoding='utf-8') as f:
                    existing_content = f.read()

            # Apply updates based on mode
            if request.mode == "replace":
                new_content = request.content
                changes = "Replaced entire document"
            elif request.mode == "append":
                new_content = existing_content + "\n\n" + request.content
                changes = "Appended content to document"
            else:  # prepend
                new_content = request.content + "\n\n" + existing_content
                changes = "Prepended content to document"

            # Write updated content
            with full_path.open('w', encoding='utf-8') as f:
                f.write(new_content)

            return UpdateDocResult(
                status="ok",
                doc_path=str(full_path),
                changes_made=changes,
            )

        except Exception as e:
            logger.error(f"Doc update failed for client {client_id}: {e}")
            return UpdateDocResult(
                status="error",
                doc_path="",
                changes_made=f"Update failed: {e}",
            )

    async def _track_file_access(self, client_id: str, file_path: str) -> None:
        """Track file access in session."""
        # This could be enhanced to use actual session tracking
        pass


# Singleton executor instance
_executor: SecretaryToolExecutor | None = None


def get_executor() -> SecretaryToolExecutor:
    """Get the global secretary tool executor instance."""
    global _executor  # noqa: PLW0603
    if _executor is None:
        _executor = SecretaryToolExecutor()
    return _executor


def reset_executor() -> None:
    """Reset the global executor (for testing)."""
    global _executor  # noqa: PLW0603
    _executor = None
