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
from typing import TYPE_CHECKING, Any, Final

from mcp.server import Server, ServerRequestContext
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    PaginatedRequestParams,
    ResourceLink,
    TextContent,
    Tool,
    ToolAnnotations,
)

from ninja_common.logging_utils import get_logger, setup_logging
from ninja_common.mcp_ext.apply import apply_extensions
from ninja_common.mcp_ext.files import (
    FileArgumentError,
    FilesExtension,
    decode_files,
    sha256_digest,
    x_mcp_file_schema,
)
from ninja_common.mcp_ext.files import is_enabled as files_enabled
from ninja_common.mcp_ext.wiring import build_protocol_extensions
from ninja_common.mcp_meta import (
    ServerMeta,
    ToolMeta,
    apply_tool_meta,
    dict_result,
    model_result,
    server_icon,
    server_kwargs,
)
from ninja_common.mcp_tasks import SqliteTaskStore
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


if TYPE_CHECKING:
    from mcp.server.extension import Extension


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="secretary_analyse_file",
        description="Analyze a file: structure, functions, classes, summary.",
        input_schema={
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
        input_schema={
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
        input_schema={
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
        input_schema={
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
        input_schema={
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
        input_schema={
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
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        result_model=AnalyseFileResult,
    ),
    "secretary_file_search": ToolMeta(
        title="Search files",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        result_model=FileSearchResult,
    ),
    "secretary_codebase_report": ToolMeta(
        title="Codebase report",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        result_model=CodebaseReportResult,
    ),
    "secretary_document_summary": ToolMeta(
        title="Summarize docs",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        result_model=DocumentSummaryResult,
    ),
    "secretary_update_documentation": ToolMeta(
        title="Update documentation",
        annotations=ToolAnnotations(destructive_hint=True),
        result_model=UpdateDocResult,
    ),
    "secretary_session_report": ToolMeta(
        title="Session report",
        annotations=ToolAnnotations(read_only_hint=True, idempotent_hint=True),
        result_model=SessionReport,
    ),
}

TOOLS = apply_tool_meta(TOOLS, _TOOL_META, server_icon("secretary"))

#: Tools a 2026-07-28 client that declared ``io.modelcontextprotocol/tasks``
#: receives a task handle for instead of a blocking result. Every other client
#: keeps the synchronous behaviour described by the tool schema.
TASK_TOOLS: frozenset[str] = frozenset({"secretary_codebase_report", "secretary_analyse_file"})

#: Files extension (experimental, default off): the single inline-ingest tool.
_INGEST_FILE_TOOL: Final[str] = "secretary_ingest_file"

#: Types the ingest tool advertises as acceptable.
_INGEST_FILE_ACCEPT: Final[tuple[str, ...]] = (
    "application/pdf",
    "text/csv",
    "text/plain",
    "image/png",
    "image/jpeg",
)


def _ingest_file_tool(files_ext: FilesExtension) -> Tool:
    """Build ``secretary_ingest_file`` for *files_ext*'s inline budget.

    The single ``file`` argument is a ``FileInput`` object carrying
    ``x-mcp-file``; the tool accepts inline bytes only.
    """
    tool = Tool(
        name=_INGEST_FILE_TOOL,
        description=(
            "Validate an inline file upload (Files extension). Returns its name, MIME type, "
            "size, SHA-256 digest and the first 32 bytes in hex; the content is never echoed."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "file": x_mcp_file_schema(
                    accept=list(_INGEST_FILE_ACCEPT),
                    max_size=files_ext.max_inline_bytes,
                ),
            },
            "required": ["file"],
        },
    )
    meta = {
        _INGEST_FILE_TOOL: ToolMeta(
            title="Ingest file",
            annotations=ToolAnnotations(
                read_only_hint=True, idempotent_hint=True, open_world_hint=False
            ),
        )
    }
    return apply_tool_meta([tool], meta, server_icon("secretary"))[0]


def _as_call_result(
    built: tuple[list[TextContent | ResourceLink], dict[str, Any]],
) -> CallToolResult:
    """Wrap a ``model_result``/``dict_result`` tuple in a ``CallToolResult``."""
    texts, structured = built
    return CallToolResult(content=list(texts), structured_content=structured, is_error=False)


def create_server() -> Server:
    """Create and configure the MCP server."""
    executor = SecretaryToolExecutor()

    # Durable task store for the Tasks extension; one instance per server.
    store = SqliteTaskStore()
    # Skills advertise ``skills/*`` and serve skill files through Resources;
    # Tasks turns the long-running tools into durable task handles for clients
    # that declared it. Both are 2026-07-28 only.
    extensions = build_protocol_extensions("secretary", store, TASK_TOOLS)

    # Files is experimental and opt-in. With the flag off, both the tool list
    # and ``capabilities.extensions`` stay exactly what they were before.
    files_ext = FilesExtension() if files_enabled() else None
    active_tools: list[Tool] = list(TOOLS)
    extension_list: list[Extension] = [extensions.skills_ext, extensions.tasks_ext]
    if files_ext is not None:
        active_tools.append(_ingest_file_tool(files_ext))
        extension_list.append(files_ext)

    async def list_tools(
        _ctx: ServerRequestContext[Any, Any],
        _params: PaginatedRequestParams | None,
    ) -> ListToolsResult:
        """List available tools."""
        return ListToolsResult(tools=active_tools)

    async def call_tool(
        _ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult:
        """Handle tool execution requests synchronously."""
        name = params.name
        arguments: dict[str, Any] = dict(params.arguments or {})

        try:
            client_id = arguments.get("client_id", "default")

            if name == "secretary_analyse_file":
                analyse_request = AnalyseFileRequest(**arguments)
                analyse_result: AnalyseFileResult = await executor.analyse_file(
                    analyse_request, client_id
                )
                return _as_call_result(model_result(analyse_result))

            elif name == "secretary_file_search":
                search_request = FileSearchRequest(**arguments)
                search_result: FileSearchResult = await executor.file_search(
                    search_request, client_id
                )
                return _as_call_result(model_result(search_result))

            elif name == "secretary_codebase_report":
                report_request = CodebaseReportRequest(**arguments)
                report_result: CodebaseReportResult = await executor.codebase_report(
                    report_request, client_id
                )
                return _as_call_result(model_result(report_result))

            elif name == "secretary_document_summary":
                summary_request = DocumentSummaryRequest(**arguments)
                summary_result: DocumentSummaryResult = await executor.document_summary(
                    summary_request, client_id
                )
                return _as_call_result(model_result(summary_result))

            elif name == "secretary_update_documentation":
                update_request = UpdateDocRequest(**arguments)
                update_result: UpdateDocResult = await executor.update_doc(
                    update_request, client_id
                )
                return _as_call_result(model_result(update_result))

            elif name == "secretary_session_report":
                session_request = SessionReportRequest(**arguments)
                session_result: SessionReport = await executor.session_report(
                    session_request, client_id
                )
                return _as_call_result(model_result(session_result))

            elif name == _INGEST_FILE_TOOL and files_ext is not None:
                payload, file = decode_files(arguments, max_inline_bytes=files_ext.max_inline_bytes)
                body = payload or b""
                return _as_call_result(
                    dict_result(
                        {
                            "name": file.name or file.id,
                            "mime_type": file.mime_type,
                            "size": file.size,
                            "digest": sha256_digest(body),
                            "first_bytes_hex": body[:32].hex(),
                        }
                    )
                )

            else:
                raise ValueError(f"Unknown tool: {name}")

        except FileArgumentError as e:
            # The message is user-safe (no ``data``, no bytes) and the tool did
            # not run, as the Files extension requires.
            logger.warning(f"Rejected file argument for {name}: {e}")
            return CallToolResult(
                content=[TextContent(type="text", text=f"Invalid file argument: {e}")],
                is_error=True,
            )

        except Exception as e:
            logger.error(f"Error executing tool {name}: {e}", exc_info=True)
            return _as_call_result(
                dict_result(
                    {
                        "success": False,
                        "error": str(e),
                        "tool": name,
                    }
                )
            )

    # The lowlevel server runs no extension interceptors, so the Tasks
    # ``tools/call`` interceptor is composed here. ``call_tool`` itself is left
    # untouched: it is the straight-through path for every non-declaring client.
    async def call_tool_with_tasks(
        ctx: ServerRequestContext[Any, Any],
        params: CallToolRequestParams,
    ) -> CallToolResult | dict[str, Any] | None:
        """Run ``call_tool`` behind the Tasks extension's interceptor."""

        async def call_next(_ctx: ServerRequestContext[Any, Any]) -> CallToolResult:
            return await call_tool(ctx, params)

        return await extensions.tasks_ext.intercept_tool_call(params, ctx, call_next)

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
        on_list_tools=list_tools,
        on_call_tool=call_tool_with_tasks,
        on_list_resources=extensions.on_list_resources,
        on_read_resource=extensions.on_read_resource,
    )
    apply_extensions(server, extension_list)
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
    """Run the MCP server over HTTP (SSE at /sse, streamable HTTP at /mcp)."""
    import uvicorn

    from ninja_common.mcp_http import build_asgi_app

    logger.info(f"Starting ninja-secretary server (HTTP/SSE mode) on {host}:{port}")

    server = create_server()
    app = build_asgi_app(server, host=host)

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
