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
    AnalyseFileRequest,
    AnalyseFileResult,
    CodebaseReportRequest,
    CodebaseReportResult,
    DocumentSummaryRequest,
    DocumentSummaryResult,
    FileMatch,
    FileSearchRequest,
    FileSearchResult,
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

    @rate_balanced(
        max_calls=60, time_window=60, max_retries=3, initial_backoff=0.5, max_backoff=30.0
    )
    @monitored
    async def analyse_file(
        self, request: AnalyseFileRequest, client_id: str = "default"
    ) -> AnalyseFileResult:
        """
        Analyse a file from the codebase.

        Args:
            request: Analyse file request.
            client_id: Client identifier for rate limiting.

        Returns:
            Analyse file result with content analysis.
        """
        logger.info(f"Analysing file '{request.file_path}' (client: {client_id})")

        try:
            file_path = Path(request.file_path)

            if not file_path.exists():
                return AnalyseFileResult(
                    status="error",
                    message=f"File not found: {request.file_path}",
                    result={}
                )

            if not file_path.is_file():
                return AnalyseFileResult(
                    status="error",
                    message=f"Not a file: {request.file_path}",
                    result={}
                )

            # Read file content
            with file_path.open(encoding="utf-8", errors="replace") as f:
                lines = f.readlines()

            total_lines = len(lines)
            
            # Get file language from extension
            language = self._detect_language(file_path.suffix)

            # Build result structure
            result = {
                "file": request.file_path,
                "language": language,
                "lines_total": total_lines
            }

            # Add structure analysis if requested
            if request.include_structure:
                structure = self._analyse_file_structure(lines, language)
                result["structure"] = structure
                result["summary"] = self._generate_file_summary(structure, language)

            # Add preview if requested
            if request.include_preview:
                preview_lines = lines[:30]
                result["preview"] = "".join(preview_lines)

            # Add search results if pattern provided
            if request.search_pattern:
                pattern = re.compile(request.search_pattern)
                search_results = []
                for line_num, line in enumerate(lines, 1):
                    if pattern.search(line):
                        search_results.append({
                            "line_number": line_num,
                            "line_content": line.rstrip()
                        })
                result["search_results"] = search_results

            # Track file access
            await self._track_file_access(client_id, request.file_path)

            return AnalyseFileResult(
                status="ok",
                message="File analysis completed successfully",
                result=result
            )

        except UnicodeDecodeError:
            return AnalyseFileResult(
                status="error",
                message="File is not a text file (binary content)",
                result={}
            )
        except Exception as e:
            logger.error(f"Failed to analyse file {request.file_path}: {e}")
            return AnalyseFileResult(
                status="error",
                message=str(e),
                result={}
            )

    def _detect_language(self, extension: str) -> str:
        """Detect programming language from file extension."""
        lang_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".jsx": "jsx",
            ".tsx": "tsx",
            ".java": "java",
            ".go": "go",
            ".rs": "rust",
            ".cpp": "cpp",
            ".c": "c",
            ".cs": "csharp",
            ".php": "php",
            ".rb": "ruby",
            ".swift": "swift",
            ".kt": "kotlin",
            ".scala": "scala",
            ".md": "markdown",
            ".html": "html",
            ".css": "css",
            ".sql": "sql",
            ".sh": "shell",
            ".yaml": "yaml",
            ".yml": "yaml",
            ".json": "json",
            ".xml": "xml"
        }
        return lang_map.get(extension.lower(), "unknown")

    def _analyse_file_structure(self, lines: list[str], language: str) -> dict:
        """Analyse file structure to extract functions, classes, and imports."""
        structure = {
            "functions": [],
            "classes": [],
            "imports": []
        }
        
        # Language-specific patterns
        patterns = {
            "python": {
                "function": r"^def\s+(\w+)",
                "class": r"^class\s+(\w+)",
                "import": r"^(import\s+|from\s+\w+\s+import)"
            },
            "javascript": {
                "function": r"^function\s+(\w+)|(\w+)\s*=\s*function|\b(\w+)\s*=>",
                "class": r"^class\s+(\w+)",
                "import": r"^(import\s+|from\s+['\"].*['\"]\s+import)"
            },
            "typescript": {
                "function": r"^function\s+(\w+)|(\w+)\s*=\s*function|\b(\w+)\s*=>",
                "class": r"^class\s+(\w+)",
                "import": r"^(import\s+|from\s+['\"].*['\"]\s+import)"
            },
            "java": {
                "function": r"^\s*(public|private|protected).*\s+(\w+)\s*\(",
                "class": r"^\s*(public\s+)?(class|interface)\s+(\w+)",
                "import": r"^import\s+"
            }
        }
        
        # Default to generic patterns if language not specifically handled
        lang_patterns = patterns.get(language, {
            "function": r"function\s+(\w+)",
            "class": r"class\s+(\w+)",
            "import": r"import\s+"
        })
        
        function_pattern = re.compile(lang_patterns["function"])
        class_pattern = re.compile(lang_patterns["class"])
        import_pattern = re.compile(lang_patterns["import"])
        
        for line in lines:
            # Check for functions
            func_match = function_pattern.search(line)
            if func_match:
                func_name = next((group for group in func_match.groups() if group), None)
                if func_name:
                    structure["functions"].append(func_name)
            
            # Check for classes
            class_match = class_pattern.search(line)
            if class_match:
                class_name = next((group for group in class_match.groups() if group), None)
                if class_name:
                    structure["classes"].append(class_name)
            
            # Check for imports
            if import_pattern.search(line):
                structure["imports"].append(line.strip())
        
        return structure

    def _generate_file_summary(self, structure: dict, language: str) -> str:
        """Generate a brief summary of the file based on its structure."""
        functions_count = len(structure["functions"])
        classes_count = len(structure["classes"])
        imports_count = len(structure["imports"])
        
        summary_parts = []
        if classes_count > 0:
            summary_parts.append(f"{classes_count} class{'es' if classes_count > 1 else ''}")
        if functions_count > 0:
            summary_parts.append(f"{functions_count} function{'s' if functions_count > 1 else ''}")
        if imports_count > 0:
            summary_parts.append(f"{imports_count} import{'s' if imports_count > 1 else ''}")
            
        if summary_parts:
            return f"A {language} file containing {', '.join(summary_parts)}."
        else:
            return f"A {language} file."

    @rate_balanced(
        max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0
    )
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
                    message=f"Repository root not found: {request.repo_root}",
                    result={}
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
            
            result = {
                "matches": [match.dict() for match in matches],
                "total_count": len(matches),
                "truncated": truncated
            }

            return FileSearchResult(
                status="ok",
                message="File search completed successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"File search failed for client {client_id}: {e}")
            return FileSearchResult(
                status="error",
                message=str(e),
                result={}
            )

    @rate_balanced(
        max_calls=10, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0
    )
    @monitored
    async def codebase_report(
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
                        p in path.parts for p in [".git", "node_modules", "__pycache__", "venv"]
                    ):
                        ext = path.suffix or "no_extension"
                        extensions[ext] = extensions.get(ext, 0) + 1

                        # Count lines for text files
                        if ext in [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs"]:
                            try:
                                with path.open(encoding="utf-8", errors="replace") as f:
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

            report = "".join(report_parts)
            
            result = {
                "report": report,
                "metrics": metrics,
                "file_count": metrics.get("file_count", 0)
            }

            return CodebaseReportResult(
                status="ok",
                message="Codebase report generated successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"Codebase report failed for client {client_id}: {e}")
            return CodebaseReportResult(
                status="error",
                message=f"Report generation failed: {e}",
                result={}
            )

    @rate_balanced(
        max_calls=5, time_window=60, max_retries=3, initial_backoff=2.0, max_backoff=60.0
    )
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
                            with doc_path.open(encoding="utf-8", errors="replace") as f:
                                content = f.read()

                            # Extract first paragraph or first 500 chars as summary
                            lines = content.split("\n")
                            summary_lines = []
                            for line in lines:
                                if line.strip():
                                    summary_lines.append(line.strip())
                                    if len(" ".join(summary_lines)) > 500:
                                        break
                                elif summary_lines:  # Stop at first empty line after content
                                    break

                            summary = " ".join(summary_lines)[:500]

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

            combined_summary = "\n\n".join(combined_parts)
            
            result = {
                "summaries": summaries,
                "combined_summary": combined_summary,
                "doc_count": len(summaries)
            }

            return DocumentSummaryResult(
                status="ok",
                message="Document summary completed successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"Document summary failed for client {client_id}: {e}")
            return DocumentSummaryResult(
                status="error",
                message=f"Summary failed: {e}",
                result={}
            )

    async def session_report(
        self,
        request: SessionReportRequest,
        client_id: str = "default",  # noqa: ARG002
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
                    message=f"Unknown doc type: {request.doc_type}",
                    result={}
                )

            full_path = Path(doc_path)
            full_path.parent.mkdir(parents=True, exist_ok=True)

            # Read existing content
            existing_content = ""
            if full_path.exists():
                with full_path.open(encoding="utf-8") as f:
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
            with full_path.open("w", encoding="utf-8") as f:
                f.write(new_content)
            
            result = {
                "doc_path": str(full_path),
                "changes_made": changes
            }

            return UpdateDocResult(
                status="ok",
                message="Document updated successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"Doc update failed for client {client_id}: {e}")
            return UpdateDocResult(
                status="error",
                message=f"Update failed: {e}",
                result={}
            )

    async def _track_file_access(self, client_id: str, file_path: str) -> None:
        """Track file access in session."""
        # This could be enhanced to use actual session tracking
        pass

    @rate_balanced(
        max_calls=30, time_window=60, max_retries=3, initial_backoff=1.0, max_backoff=30.0
    )
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
                    message=f"Repository root not found: {request.repo_root}",
                    result={}
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
                if path.name.startswith(".") or path.name in [
                    "node_modules",
                    "__pycache__",
                    "venv",
                    ".git",
                ]:
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
            
            result = {
                "tree": root_node.dict() if root_node else None,
                "total_files": total_files,
                "total_dirs": total_dirs,
                "total_size": total_size
            }

            return FileTreeResult(
                status="ok",
                message="File tree generated successfully",
                result=result
            )

        except Exception as e:
            logger.error(f"File tree generation failed for client {client_id}: {e}")
            return FileTreeResult(
                status="error",
                message=str(e),
                result={}
            )


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
