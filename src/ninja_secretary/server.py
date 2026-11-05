"""
MCP stdio server for ninja-secretary module.

This module implements the Model Context Protocol (MCP) server that
exposes tools for codebase analysis, file operations, and documentation management.

Usage:
    python -m ninja_secretary.server
"""

from __future__ import annotations

import argparse
import asyncio
import logging
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, ToolAnnotations

from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.mcp_meta import (
    ServerMeta,
    ToolMeta,
    apply_tool_meta,
    dict_result,
    model_result,
    server_icon,
    server_kwargs,
)
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
from ninja_secretary.tools import SecretaryToolExecutor


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="secretary_analyse_file",
        description="Analyze a file: structure, functions, classes, summary.",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to the file to analyze",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="secretary_file_search",
        description="Search files by glob pattern with optional content-regex filter.",
        inputSchema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern to search for files (e.g., '**/*.py', 'src/**/*.ts')",
                },
                "content_regex": {
                    "type": "string",
                    "description": "Optional regex pattern to filter file contents",
                },
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path (defaults to current directory)",
                },
            },
            "required": ["pattern"],
        },
    ),
    Tool(
        name="secretary_codebase_report",
        description="Report on codebase structure, file counts, languages, and metrics.",
        inputSchema={
            "type": "object",
            "properties": {
                "repo_root": {
                    "type": "string",
                    "description": "Repository root path to analyze",
                },
                "include_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patterns to include (e.g., ['**/*.py', '**/*.js'])",
                },
                "exclude_patterns": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patterns to exclude (e.g., ['**/node_modules/**', '**/__pycache__/**'])",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="secretary_document_summary",
        description="Summarize docs in a directory: headings, sections, key info.",
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
                    "description": "Documentation file patterns (default: ['**/*.md', '**/README*', '**/CONTRIBUTING*'])",
                },
            },
            "required": ["repo_root"],
        },
    ),
    Tool(
        name="secretary_update_documentation",
        description="Update or create project documentation files.",
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
                    "description": "Type of documentation to update",
                },
                "content": {
                    "type": "string",
                    "description": "New content or updates",
                },
                "mode": {
                    "type": "string",
                    "enum": ["replace", "append", "prepend"],
                    "description": "Update mode (default: replace)",
                    "default": "replace",
                },
            },
            "required": ["module_name", "doc_type", "content"],
        },
    ),
    Tool(
        name="secretary_session_report",
        description="Report current session: tracked ops, file accesses, metadata.",
        inputSchema={
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "string",
                    "description": "Session identifier (defaults to 'default')",
                },
            },
        },
    ),
]

# Tool metadata: titles, behavior hints, and result models for
# outputSchema + structuredContent.
_TOOL_META: dict[str, ToolMeta] = {
    "secretary_analyse_file": ToolMeta(
        title="Analyze file",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        result_model=AnalyseFileResult,
    ),
    "secretary_file_search": ToolMeta(
        title="Search files",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        result_model=FileSearchResult,
    ),
    "secretary_codebase_report": ToolMeta(
        title="Codebase report",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        result_model=CodebaseReportResult,
    ),
    "secretary_document_summary": ToolMeta(
        title="Summarize docs",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        result_model=DocumentSummaryResult,
    ),
    "secretary_update_documentation": ToolMeta(
        title="Update documentation",
        annotations=ToolAnnotations(destructiveHint=True),
        result_model=UpdateDocResult,
    ),
    "secretary_session_report": ToolMeta(
        title="Session report",
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True),
        result_model=SessionReport,
    ),
}

TOOLS = apply_tool_meta(TOOLS, _TOOL_META, server_icon("secretary"))


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(
        "ninja-secretary",
        **server_kwargs(
            ServerMeta(
                instructions="""Ninja Secretary: codebase analysis and documentation.
analyse_file: structure + summary of one file. file_search: glob + content regex.
codebase_report: structure, languages, metrics. document_summary: docs overview.
update_documentation: write docs (the only writing tool). session_report: tracked ops.""",
                kind="secretary",
            )
        ),
    )
    executor = SecretaryToolExecutor()

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: Any) -> Any:
        """Handle tool execution requests."""
        try:
            client_id = arguments.get("client_id", "default")

            if name == "secretary_analyse_file":
                request = AnalyseFileRequest(**arguments)
                result = await executor.analyse_file(request, client_id)
                return model_result(result)

            elif name == "secretary_file_search":
                request = FileSearchRequest(**arguments)
                result = await executor.file_search(request, client_id)
                return model_result(result)

            elif name == "secretary_codebase_report":
                request = CodebaseReportRequest(**arguments)
                result = await executor.codebase_report(request, client_id)
                return model_result(result)

            elif name == "secretary_document_summary":
                request = DocumentSummaryRequest(**arguments)
                result = await executor.document_summary(request, client_id)
                return model_result(result)

            elif name == "secretary_update_documentation":
                request = UpdateDocRequest(**arguments)
                result = await executor.update_doc(request, client_id)
                return model_result(result)

            elif name == "secretary_session_report":
                request = SessionReportRequest(**arguments)
                result = await executor.session_report(request, client_id)
                return model_result(result)

            else:
                raise ValueError(f"Unknown tool: {name}")

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return dict_result(
                {
                    "success": False,
                    "error": str(e),
                    "tool": name,
                }
            )

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
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response

    logger.info(f"Starting ninja-secretary server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    sse = SseServerTransport("/messages")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())
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
    """Run the server with command-line argument parsing."""
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

    if args.http:
        asyncio.run(main_http(args.host, args.port))
    else:
        asyncio.run(main_stdio())


if __name__ == "__main__":
    run()
