"""
MCP stdio server for ninja-secretary module.

This module implements the Model Context Protocol (MCP) server that
exposes tools for codebase exploration, documentation, and session tracking.

Usage:
    python -m ninja_secretary.server
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import TYPE_CHECKING, Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from ninja_common.logging_utils import get_logger, setup_logging
from ninja_secretary.models import (
    CodebaseReportRequest,
    DocumentSummaryRequest,
    FileSearchRequest,
    FileTreeRequest,
    GrepRequest,
    ReadFileRequest,
    SessionReportRequest,
    UpdateDocRequest,
)
from ninja_secretary.tools import get_executor

if TYPE_CHECKING:
    from collections.abc import Sequence


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="secretary_read_file",
        description=(
            "Read a file from the codebase. "
            "Can read entire file or specific line range. "
            "\n\n"
            "Use this for: Reading source code, documentation, configuration files."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to file (relative to repo root)",
                },
                "start_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "Start line (1-indexed, optional)",
                },
                "end_line": {
                    "type": "integer",
                    "minimum": 1,
                    "description": "End line (1-indexed, optional)",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="secretary_file_search",
        description=(
            "Search for files matching a glob pattern. "
            "\n\n"
            "Examples: '**/*.py', 'src/**/*.ts', '**/test_*.py'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to match files",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 100,
                    "description": "Maximum results to return",
                },
            },
            "required": ["pattern", "repo_root"],
        },
    ),
    Tool(
        name="secretary_grep",
        description=(
            "Search for content in files using regex patterns. "
            "Can filter by file pattern and include context lines. "
            "\n\n"
            "Use this for: Finding function definitions, searching for text, code analysis."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "file_pattern": {
                    "type": "string",
                    "description": "Glob pattern to filter files (optional)",
                },
                "context_lines": {
                    "type": "integer",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 2,
                    "description": "Lines of context before/after match",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 1000,
                    "default": 100,
                    "description": "Maximum results",
                },
            },
            "required": ["pattern", "repo_root"],
        },
    ),
    Tool(
        name="secretary_file_tree",
        description=(
            "Generate a detailed file tree structure. "
            "Includes file sizes, directory structure, and optional git status. "
            "\n\n"
            "Use this for: Understanding project structure, exploring codebases."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "max_depth": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 10,
                    "default": 3,
                    "description": "Maximum directory depth",
                },
                "include_sizes": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include file sizes",
                },
                "include_git_status": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include git status",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="secretary_codebase_report",
        description=(
            "Generate a comprehensive codebase analysis report. "
            "Includes metrics, structure, and dependency analysis. "
            "\n\n"
            "Use this for: Understanding project overview, documentation, onboarding."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "include_metrics": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include code metrics",
                },
                "include_dependencies": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include dependency analysis",
                },
                "include_structure": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include project structure",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="secretary_document_summary",
        description=(
            "Summarize documentation files in the repository. "
            "Automatically finds README, CONTRIBUTING, and markdown files. "
            "\n\n"
            "Use this for: Quick documentation overview, finding key information."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path",
                },
                "doc_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["**/*.md", "**/README*", "**/CONTRIBUTING*"],
                    "description": "Patterns to match documentation files",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="secretary_session_report",
        description=(
            "Track session activity with persistent reports. "
            "One report per session tracks tools used, files accessed, and summary. "
            "\n\n"
            "Actions: 'create', 'get', 'update'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier",
                },
                "action": {
                    "type": "string",
                    "enum": ["get", "update", "create"],
                    "default": "get",
                    "description": "Action to perform",
                },
                "updates": {
                    "type": "object",
                    "description": "Updates to apply (for update action)",
                },
            },
            "required": ["session_id"],
        },
    ),
    Tool(
        name="secretary_update_doc",
        description=(
            "Update module documentation (README, API, CHANGELOG). "
            "\n\n"
            "Modes: 'replace', 'append', 'prepend'"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "module_name": {
                    "type": "string",
                    "description": "Module name (coder, researcher, secretary)",
                },
                "doc_type": {
                    "type": "string",
                    "enum": ["readme", "api", "changelog"],
                    "description": "Type of documentation",
                },
                "content": {
                    "type": "string",
                    "description": "Content to add/replace",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append", "prepend"],
                    "default": "replace",
                    "description": "Update mode",
                },
            },
            "required": ["module_name", "doc_type", "content"],
        },
    ),
]


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(
        "ninja-secretary",
        version="0.2.0",
        instructions="""📋 Ninja Secretary: Codebase Explorer & Documentation Assistant

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📋 WHAT SECRETARY DOES:
   ✅ Read files from codebase (with line ranges)
   ✅ Search for files (glob patterns)
   ✅ Grep content (regex search with context)
   ✅ Generate file trees with details
   ✅ Create codebase analysis reports
   ✅ Summarize documentation
   ✅ Track session activity
   ✅ Update module documentation

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔧 AVAILABLE TOOLS:

• secretary_read_file
  Read file content (entire file or line range).
  Returns: File content with line count.

• secretary_file_search
  Search for files matching glob patterns.
  Returns: List of matching files with metadata.

• secretary_grep
  Search content using regex with context.
  Returns: Matches with surrounding lines.

• secretary_file_tree
  Generate detailed file tree structure.
  Returns: Hierarchical tree with sizes and metadata.

• secretary_codebase_report
  Comprehensive codebase analysis.
  Returns: Markdown report with metrics, structure, dependencies.

• secretary_document_summary
  Summarize documentation files.
  Returns: Per-document and combined summaries.

• secretary_session_report
  Track session activity (one report per session).
  Returns: Session report with tools used, files accessed.

• secretary_update_doc
  Update module documentation files.
  Returns: Status and changes made.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 USAGE EXAMPLES:

1. Read a specific file:
   secretary_read_file({
     "file_path": "src/main.py"
   })

2. Search for Python test files:
   secretary_file_search({
     "pattern": "**/test_*.py",
     "repo_root": "/path/to/repo",
     "max_results": 50
   })

3. Find function definitions:
   secretary_grep({
     "pattern": "def \\w+\\(",
     "repo_root": "/path/to/repo",
     "file_pattern": "**/*.py",
     "context_lines": 3
   })

4. Generate project tree:
   secretary_file_tree({
     "repo_root": "/path/to/repo",
     "max_depth": 3,
     "include_sizes": true
   })

5. Analyze codebase:
   secretary_codebase_report({
     "repo_root": "/path/to/repo",
     "include_metrics": true,
     "include_dependencies": true
   })

6. Track session:
   secretary_session_report({
     "session_id": "my-session-id",
     "action": "update",
     "updates": {
       "tools_used": ["read_file", "grep"],
       "summary": "Analyzed authentication code"
     }
   })

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ RATE LIMITS:
   • Read file: 60 calls/minute
   • File search/grep: 30 calls/minute
   • Reports: 5-10 calls/minute
   • Per-client tracking

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━""",
    )

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Sequence[TextContent]:
        """Handle tool invocations."""
        client_id = "default"
        logger.info(f"[{client_id}] Tool called: {name}")

        executor = get_executor()

        try:
            if name == "secretary_read_file":
                request = ReadFileRequest(**arguments)
                result = await executor.read_file(request, client_id=client_id)

            elif name == "secretary_file_search":
                request = FileSearchRequest(**arguments)
                result = await executor.file_search(request, client_id=client_id)

            elif name == "secretary_grep":
                request = GrepRequest(**arguments)
                result = await executor.grep(request, client_id=client_id)

            elif name == "secretary_file_tree":
                request = FileTreeRequest(**arguments)
                result = await executor.file_tree(request, client_id=client_id)

            elif name == "secretary_codebase_report":
                request = CodebaseReportRequest(**arguments)
                result = await executor.codebase_report(request, client_id=client_id)

            elif name == "secretary_document_summary":
                request = DocumentSummaryRequest(**arguments)
                result = await executor.document_summary(request, client_id=client_id)

            elif name == "secretary_session_report":
                request = SessionReportRequest(**arguments)
                result = await executor.session_report(request, client_id=client_id)

            elif name == "secretary_update_doc":
                request = UpdateDocRequest(**arguments)
                result = await executor.update_doc(request, client_id=client_id)

            else:
                return [
                    TextContent(
                        type="text",
                        text=json.dumps({"error": f"Unknown tool: {name}"}),
                    )
                ]

            # Serialize result to JSON
            result_json = result.model_dump()
            logger.info(
                f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
            )

            return [
                TextContent(
                    type="text",
                    text=json.dumps(result_json, indent=2),
                )
            ]

        except Exception as e:
            logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
            return [
                TextContent(
                    type="text",
                    text=json.dumps(
                        {
                            "status": "error",
                            "error": str(e),
                            "error_type": type(e).__name__,
                        }
                    ),
                )
            ]

    return server


async def main_stdio() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting ninja-secretary server (stdio mode)")

    server = create_server()

    async with stdio_server() as (read_stream, write_stream):
        logger.info("Server ready, waiting for requests")
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


async def main_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP with SSE."""
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response
    import uvicorn

    logger.info(f"Starting ninja-secretary server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            await server.run(
                streams[0], streams[1], server.create_initialization_options()
            )
        return Response()

    async def handle_messages(scope, receive, send):
        await sse.handle_post_message(scope, receive, send)

    async def app(scope, receive, send):
        path = scope.get("path", "")
        if path == "/sse":
            request = Request(scope, receive, send)
            await handle_sse(request)
        elif path == "/messages" and scope.get("method") == "POST":
            await handle_messages(scope, receive, send)
        else:
            await Response("Not Found", status_code=404)(scope, receive, send)

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server_instance = uvicorn.Server(config)
    await server_instance.serve()


def run() -> None:
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ninja Secretary MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8102,
        help="Port for HTTP server (default: 8102)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    try:
        if args.http:
            asyncio.run(main_http(args.host, args.port))
        else:
            asyncio.run(main_stdio())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    run()
