"""
MCP stdio server for ninja-researcher module.

This module implements the Model Context Protocol (MCP) server that
exposes tools for web search and research tasks.

Usage:
    python -m ninja_researcher.server
"""

from __future__ import annotations

import asyncio
import logging
import sys
from typing import Any

import anyio
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import CallToolResult, Tool, ToolAnnotations, ToolExecution

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
from ninja_common.mcp_tasks import (
    install_tasks,
    make_session_progress_callback,
    refresh_task_after_cancel,
    server_task_scope,
    task_scope,
)
from ninja_researcher.models import (
    ArxivSearchRequest,
    ArxivSearchResult,
    DeepResearchBatchRequest,
    DeepResearchBatchResult,
    DeepResearchRequest,
    FactCheckRequest,
    FactCheckResult,
    GenerateReportRequest,
    PaperFetchRequest,
    PaperFetchResult,
    QuickResearchRequest,
    QuickResearchResult,
    ReportResult,
    ResearchResult,
    SummarizeSourcesRequest,
    SummaryResult,
)
from ninja_researcher.tools import get_executor


# Set up logging to stderr (stdout is for MCP protocol)
setup_logging(level=logging.INFO)
logger = get_logger(__name__)


# Tool definitions
TOOLS: list[Tool] = [
    Tool(
        name="researcher_quick_research",
        execution=ToolExecution(taskSupport="optional"),
        description=(
            "Single-question research with cited answer. Use deep_research for multi-query reports."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Research question",
                },
                "search_provider": {
                    "type": "string",
                    "enum": ["duckduckgo", "serper", "perplexity"],
                    "description": "Provider to use (defaults to NINJA_SEARCH_PROVIDER, then auto)",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                    "description": "Maximum sources/citations to gather",
                },
                "enrich": {
                    "type": "boolean",
                    "default": True,
                    "description": "Fetch pages to replace provider snippets with real extracted text",
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "If set, keep only sources whose host matches one of these",
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Drop sources whose host matches any of these (subdomains too)",
                },
                "prefer_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Order matching sources first, preserving relative order",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="researcher_deep_research",
        execution=ToolExecution(taskSupport="optional"),
        description="Multi-query research with written report. Use quick_research for single questions; batch for multiple topics.",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Research topic",
                },
                "queries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Specific queries (auto-generated if empty)",
                },
                "search_provider": {
                    "type": "string",
                    "enum": ["duckduckgo", "serper", "perplexity"],
                    "description": "Provider to use (defaults to NINJA_SEARCH_PROVIDER, then auto)",
                },
                "max_sources": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 100,
                    "default": 20,
                    "description": "Maximum sources to gather",
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                    "description": "Number of parallel search agents",
                },
                "enrich": {
                    "type": "boolean",
                    "default": True,
                    "description": "Fetch pages to replace provider snippets with real extracted text",
                },
                "include_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "If set, keep only sources whose host matches one of these",
                },
                "exclude_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Drop sources whose host matches any of these (subdomains too)",
                },
                "prefer_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Order matching sources first, preserving relative order",
                },
                "synthesize": {
                    "type": "boolean",
                    "default": True,
                    "description": "Produce a written report when a synthesis engine is available",
                },
                "report_type": {
                    "type": "string",
                    "enum": ["comprehensive", "summary", "technical", "executive"],
                    "default": "comprehensive",
                    "description": "Report style when synthesize is enabled",
                },
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="researcher_generate_report",
        execution=ToolExecution(taskSupport="optional"),
        description="Synthesize provided sources into a cited report (comprehensive, summary, technical, executive).",
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Report topic",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": (
                        "Source documents to synthesize. Each object should have "
                        "'url' and 'title' fields. The text body may be provided "
                        "under any of: 'snippet', 'content', or 'description'."
                    ),
                },
                "report_type": {
                    "type": "string",
                    "enum": ["comprehensive", "summary", "technical", "executive"],
                    "default": "comprehensive",
                    "description": "Type of report to generate",
                },
                "parallel_agents": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 8,
                    "default": 4,
                    "description": "Number of parallel synthesis agents",
                },
                "use_llm": {
                    "type": "boolean",
                    "description": (
                        "Force LLM synthesis on/off. Omit to use an LLM when a "
                        "synthesis engine is configured, else the template."
                    ),
                },
            },
            "required": ["topic", "sources"],
        },
    ),
    Tool(
        name="researcher_fact_check",
        execution=ToolExecution(taskSupport="optional"),
        description=("Verify a claim via LLM verdict over sources (verified|disputed|uncertain)."),
        inputSchema={
            "type": "object",
            "properties": {
                "claim": {
                    "type": "string",
                    "description": "Claim to verify",
                },
                "sources": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "URLs to check against (auto-search if empty)",
                },
            },
            "required": ["claim"],
        },
    ),
    Tool(
        name="researcher_summarize_sources",
        execution=ToolExecution(taskSupport="optional"),
        description=("Summarize URLs into per-source plus combined summaries."),
        inputSchema={
            "type": "object",
            "properties": {
                "urls": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "URLs to summarize",
                },
                "max_length": {
                    "type": "integer",
                    "minimum": 100,
                    "maximum": 5000,
                    "default": 500,
                    "description": "Maximum summary length in words",
                },
            },
            "required": ["urls"],
        },
    ),
    Tool(
        name="researcher_arxiv_search",
        execution=ToolExecution(taskSupport="optional"),
        description="Search arXiv papers; categories default [cs.RO, cs.LG] ANDed with the query.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": ["cs.RO", "cs.LG"],
                    "description": "arXiv categories ANDed with the query",
                },
                "max_results": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                    "description": "Maximum number of papers",
                },
                "sort_by": {
                    "type": "string",
                    "enum": ["relevance", "lastUpdatedDate", "submittedDate"],
                    "default": "relevance",
                    "description": "arXiv sort order",
                },
                "full_metadata": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include optional fields such as comment and categories",
                },
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="researcher_paper_fetch",
        execution=ToolExecution(taskSupport="optional"),
        description="Fetch an arXiv paper or web page; extract sections and numbers with context.",
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "arXiv URL/id (abs, pdf, ar5iv) or a generic URL",
                },
                "sections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Section headings to extract (case-insensitive)",
                },
                "extract_numbers": {
                    "type": "boolean",
                    "default": False,
                    "description": "Extract numeric tokens with sentence context",
                },
            },
            "required": ["source"],
        },
    ),
    Tool(
        name="researcher_deep_research_batch",
        execution=ToolExecution(taskSupport="optional"),
        description="Batch up to 5 deep-research topics serially.",
        inputSchema={
            "type": "object",
            "properties": {
                "requests": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "topic": {"type": "string"},
                            "queries": {"type": "array", "items": {"type": "string"}},
                            "search_provider": {
                                "type": "string",
                                "enum": ["duckduckgo", "serper", "perplexity"],
                            },
                            "max_sources": {"type": "integer", "minimum": 1, "maximum": 100},
                            "parallel_agents": {"type": "integer", "minimum": 1, "maximum": 8},
                            "enrich": {"type": "boolean"},
                            "synthesize": {"type": "boolean"},
                            "report_type": {"type": "string"},
                        },
                        "required": ["topic"],
                    },
                    "minItems": 1,
                    "maxItems": 5,
                    "description": "Deep research requests (1..5)",
                },
                "mode": {
                    "type": "string",
                    "enum": ["serial"],
                    "default": "serial",
                    "description": "Execution mode",
                },
                "inter_call_delay_s": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 120,
                    "default": 15,
                    "description": "Delay between calls in seconds",
                },
                "on_error": {
                    "type": "string",
                    "enum": ["continue", "abort", "retry_backoff"],
                    "default": "retry_backoff",
                    "description": "Behavior when a request returns a typed error",
                },
            },
            "required": ["requests"],
        },
    ),
]

_RO = ToolAnnotations(readOnlyHint=True, idempotentHint=True)
_RO_WEB = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)

# Tool metadata: titles, behavior hints, and result models for
# outputSchema + structuredContent.
_TOOL_META: dict[str, ToolMeta] = {
    "researcher_quick_research": ToolMeta(
        title="Quick research", annotations=_RO_WEB, result_model=QuickResearchResult
    ),
    "researcher_deep_research": ToolMeta(
        title="Deep research", annotations=_RO_WEB, result_model=ResearchResult
    ),
    "researcher_generate_report": ToolMeta(
        title="Generate report", annotations=_RO, result_model=ReportResult
    ),
    "researcher_fact_check": ToolMeta(
        title="Fact check", annotations=_RO_WEB, result_model=FactCheckResult
    ),
    "researcher_summarize_sources": ToolMeta(
        title="Summarize sources", annotations=_RO_WEB, result_model=SummaryResult
    ),
    "researcher_arxiv_search": ToolMeta(
        title="arXiv search", annotations=_RO_WEB, result_model=ArxivSearchResult
    ),
    "researcher_paper_fetch": ToolMeta(
        title="Fetch paper", annotations=_RO_WEB, result_model=PaperFetchResult
    ),
    "researcher_deep_research_batch": ToolMeta(
        title="Batch deep research",
        annotations=_RO_WEB,
        result_model=DeepResearchBatchResult,
    ),
}

TOOLS = apply_tool_meta(TOOLS, _TOOL_META, server_icon("researcher"))

# Look up tool definitions by name (used for task-mode validation).
_TOOLS_BY_NAME: dict[str, Tool] = {tool.name: tool for tool in TOOLS}


def create_server() -> Server:
    """Create and configure the MCP server."""
    server = Server(
        "ninja-researcher",
        version="0.3.0",
        **server_kwargs(
            ServerMeta(
                instructions="""Ninja Researcher: cited web research.
quick_research: single question + cited answer. deep_research: multi-query + report. generate_report: synthesize given sources. fact_check: LLM verdict. arxiv_search/paper_fetch: papers. batch: up to 5 topics serially.""",
                kind="researcher",
            )
        ),
    )

    # Enable standard MCP Tasks (background/asynchronous tool execution) with a
    # durable store and real cancellation of running work.
    install_tasks(server)

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """Return the list of available tools."""
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> Any:
        """Handle tool invocations, synchronously or as a background task."""
        request_ctx = server.request_context
        experimental = request_ctx.experimental
        tool_definition = _TOOLS_BY_NAME.get(name)
        if tool_definition is not None:
            experimental.validate_for_tool(tool_definition)

        async def _invoke() -> tuple[list, dict[str, Any]]:
            client_id = "default"
            logger.info(f"[{client_id}] Tool called: {name}")

            executor = get_executor()

            try:
                if name == "researcher_quick_research":
                    request = QuickResearchRequest(**arguments)
                    result = await executor.quick_research(request, client_id=client_id)

                elif name == "researcher_deep_research":
                    request = DeepResearchRequest(**arguments)
                    result = await executor.deep_research(request, client_id=client_id)

                elif name == "researcher_generate_report":
                    request = GenerateReportRequest(**arguments)
                    result = await executor.generate_report(request, client_id=client_id)

                elif name == "researcher_fact_check":
                    request = FactCheckRequest(**arguments)
                    result = await executor.fact_check(request, client_id=client_id)

                elif name == "researcher_summarize_sources":
                    request = SummarizeSourcesRequest(**arguments)
                    result = await executor.summarize_sources(request, client_id=client_id)

                elif name == "researcher_arxiv_search":
                    request = ArxivSearchRequest(**arguments)
                    result = await executor.arxiv_search(request, client_id=client_id)

                elif name == "researcher_paper_fetch":
                    request = PaperFetchRequest(**arguments)
                    result = await executor.paper_fetch(request, client_id=client_id)

                elif name == "researcher_deep_research_batch":
                    request = DeepResearchBatchRequest(**arguments)
                    result = await executor.deep_research_batch(request, client_id=client_id)

                else:
                    return dict_result({"error": f"Unknown tool: {name}"})

                # Serialize result to JSON
                result_json = result.model_dump()
                logger.info(
                    f"[{client_id}] Tool {name} completed with status: {result_json.get('status', 'unknown')}"
                )

                return model_result(result)

            except Exception as e:
                logger.error(f"[{client_id}] Tool {name} failed: {e}", exc_info=True)
                return dict_result(
                    {
                        "status": "error",
                        "error": str(e),
                        "error_type": type(e).__name__,
                    }
                )

        if experimental.is_task:
            session = request_ctx.session
            progress_token = request_ctx.meta.progressToken if request_ctx.meta else None

            async def _work(task: Any) -> CallToolResult:
                async with server_task_scope(
                    task, session=session, progress_token=progress_token
                ) as cancellation:
                    texts, structured = await _invoke()
                    if cancellation.is_set():
                        await refresh_task_after_cancel(task)
                    return CallToolResult(
                        content=list(texts), structuredContent=structured, isError=False
                    )

            return await experimental.run_task(_work)

        # Sync path heartbeat: forward progress as notifications/progress
        # when the client passed a progressToken (keeps long runs alive).
        progress_token = request_ctx.meta.progressToken if request_ctx.meta else None
        if progress_token is not None:
            session = request_ctx.session
            callback = make_session_progress_callback(session, progress_token)
            async with task_scope(f"sync-{name}", progress=callback):
                return await _invoke()

        return await _invoke()

    return server


def _is_client_disconnect(exc: BaseException) -> bool:
    """Return True if *exc* (or all leaves of an ExceptionGroup) are stream-closed errors."""
    _disconnect_types = (anyio.ClosedResourceError, anyio.BrokenResourceError)
    if isinstance(exc, BaseExceptionGroup):
        return all(_is_client_disconnect(e) for e in exc.exceptions)
    return isinstance(exc, _disconnect_types)


async def main_stdio() -> None:
    """Run the MCP server over stdio."""
    logger.info("Starting ninja-researcher server (stdio mode)")

    server = create_server()

    try:
        async with stdio_server() as (read_stream, write_stream):
            logger.info("Server ready, waiting for requests")
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )
    except BaseException as exc:
        if _is_client_disconnect(exc):
            logger.warning("Client disconnected during server run (stream closed)")
        else:
            raise


async def main_http(host: str, port: int) -> None:
    """Run the MCP server over HTTP with SSE."""
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.requests import Request
    from starlette.responses import Response

    logger.info(f"Starting ninja-researcher server (HTTP/SSE mode) on {host}:{port}")

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
    """Entry point for running the server."""
    import argparse

    parser = argparse.ArgumentParser(description="Ninja Researcher MCP Server")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Run server in HTTP/SSE mode (default: stdio)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8101,
        help="Port for HTTP server (default: 8101)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind to (default: 127.0.0.1)",
    )

    args = parser.parse_args()

    # Load config from ~/.ninja-mcp.env into environment variables
    try:
        from ninja_common.config_manager import ConfigManager

        ConfigManager().export_env()
    except Exception:
        pass  # Config file may not exist, continue with env vars

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
